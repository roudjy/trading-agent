"""
TRADING AGENT DASHBOARD
=======================
Flask-gebaseerd dashboard voor de JvR Trading Agent.
Alle data via /api/ endpoints, geen extra packages.
"""

from flask import (
    Flask,
    send_from_directory,
    request,
    Response,
    jsonify,
    session,
    g,
    render_template,
)
from functools import wraps
import hmac
import os
import secrets
import sqlite3
import time
import json
import threading
import time
from pathlib import Path
from datetime import datetime

from data.contracts import Instrument
from data.repository import MarketRepository
from dashboard import research_artifacts, research_runner
from reporting import audit_log

app = Flask(__name__, template_folder="templates")
BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_SECRET_PATH = BASE_DIR / "state" / "operator_token.secret"
SESSION_SECRET_PATH = BASE_DIR / "state" / "dashboard_session.secret"


def _read_or_create_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    path.write_text(secret, encoding="utf-8")
    return secret


app.secret_key = _read_or_create_secret(SESSION_SECRET_PATH)


@app.errorhandler(Exception)
def _api_error(e):
    """Geef altijd geldige JSON terug, nooit een crash."""
    app.logger.error(f"API fout: {e}", exc_info=True)
    return jsonify({"error": str(e), "data": []}), 500


# ──────────────────────────────────────────────
# Authenticatie (Basic Auth)
# ──────────────────────────────────────────────
PW_HASH = "1589467012acf3e137fd8ba1b6822dcb942bb003c1cd96b10c5cad340a507a7d"
SALT    = "6bff887d02d28e60299f53d77a3a1246"


def _operator_token_secret() -> str:
    return _read_or_create_secret(TOKEN_SECRET_PATH)

def check_auth(username, password):
    import hashlib
    h = hashlib.sha256((SALT + password).encode()).hexdigest()
    return username == "joery" and h == PW_HASH

def authenticate():
    return Response("Login vereist", 401, {"WWW-Authenticate": 'Basic realm="JvR Agent"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("operator_authenticated"):
            g.operator_actor = session.get("operator_actor", "session")
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        session["operator_authenticated"] = True
        session["operator_actor"] = auth.username
        g.operator_actor = auth.username
        return f(*args, **kwargs)
    return decorated


def require_operator_auth():
    """Bescherm side-effect endpoints via sessiecookie of operator-token."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("operator_authenticated"):
                g.operator_actor = session.get("operator_actor", "session")
                return f(*args, **kwargs)

            token = request.headers.get("X-Operator-Token", "")
            secret = _operator_token_secret()
            if token and hmac.compare_digest(token, secret):
                g.operator_actor = "operator_token"
                return f(*args, **kwargs)

            return jsonify({"error": "operator authentication required"}), 401
        return decorated
    return decorator


def _operator_actor() -> str:
    return getattr(g, "operator_actor", "unknown")

# ──────────────────────────────────────────────
# Paden
# ──────────────────────────────────────────────
DB_PAD       = Path("logs/agent_geheugen.db")
LOG_PAD      = Path("logs/agent.log")
AUDIT_LOG    = Path("logs/zelfverbeteringen.log")
PAUSE_FLAG   = Path("logs/agent_pause.flag")
CONFIG_PAD   = Path("config/config.yaml")
RAPPORT_MAP  = Path("reports")

# Geladen config (optioneel, voor start_kapitaal fallback)
_config = {}
try:
    import yaml
    with open(CONFIG_PAD, encoding="utf-8") as f:
        _config = yaml.safe_load(f) or {}
except Exception:
    pass

START_KAPITAAL = float(_config.get("kapitaal", {}).get("start", 1000.0))

# ──────────────────────────────────────────────
# Prijzen cache (achtergrond thread)
# ──────────────────────────────────────────────
_prijzen_cache: dict = {}
_prijzen_cache_tijd: float = 0.0
_PRIJS_TTL = 60  # seconden

CRYPTO_YAHOO = {
    "BTC/EUR": "BTC-EUR",
    "ETH/EUR": "ETH-EUR",
    "SOL/EUR": "SOL-EUR",
    "BNB/EUR": "BNB-EUR",
}
STOCK_SYMBOLEN = ["NVDA", "AAPL", "MSFT", "ASML", "AMD"]
MARKET_REPOSITORY = MarketRepository()


def _price_instruments() -> list[Instrument]:
    instruments = [
        Instrument(
            id=sym,
            asset_class="equity",
            venue="yahoo",
            native_symbol=sym,
            quote_ccy="USD",
        )
        for sym in STOCK_SYMBOLEN
    ]
    instruments.extend(
        Instrument(
            id=sym,
            asset_class="crypto",
            venue="yahoo",
            native_symbol=yahoo_sym,
            quote_ccy="EUR",
        )
        for sym, yahoo_sym in CRYPTO_YAHOO.items()
    )
    return instruments


def _start_daemon_timer(delay: float, callback) -> None:
    """Start achtergrondtimers als daemon zodat ze geen shutdown blokkeren."""
    timer = threading.Timer(delay, callback)
    timer.daemon = True
    timer.start()


def _ververs_prijzen():
    """Achtergrondthread: haalt live koersen op en slaat ze op in cache."""
    global _prijzen_cache, _prijzen_cache_tijd
    result = {}
    try:
        result = MARKET_REPOSITORY.get_latest_prices(_price_instruments())
    except Exception:
        pass

    _prijzen_cache = result
    _prijzen_cache_tijd = time.time()
    # Plan volgende refresh
    _start_daemon_timer(_PRIJS_TTL, _ververs_prijzen)


# Start eerste prijsrefresh na 2 seconden (laat Flask opstarten)
_start_daemon_timer(2, _ververs_prijzen)


# ──────────────────────────────────────────────
# Hulpfuncties
# ──────────────────────────────────────────────
def _db_connect():
    """SQLite connectie met WAL mode en locking-parameters."""
    conn = sqlite3.connect(
        str(DB_PAD),
        timeout=30,
        check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _db_query(sql, params=()):
    """Voer een SELECT query uit met retry bij database locked."""
    if not DB_PAD.exists():
        return []
    wacht = 0.2
    for poging in range(1, 6):
        try:
            with _db_connect() as conn:
                cursor = conn.execute(sql, params)
                return [dict(r) for r in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and poging < 5:
                app.logger.warning(f"DB locked (dashboard), poging {poging}/5, wacht {wacht:.1f}s")
                time.sleep(wacht)
                wacht *= 2
            else:
                app.logger.error(f"DB fout: {e}")
                return []


def _table_bestaat(conn, naam):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (naam,)
    ).fetchone()
    return r is not None


# ──────────────────────────────────────────────
# Hoofdpagina
# ──────────────────────────────────────────────
@app.route("/")
@requires_auth
def index():
    html_pad = Path("dashboard/templates/dashboard.html")
    if not html_pad.exists():
        html_pad = Path("templates/dashboard.html")
    return open(html_pad, encoding="utf-8").read()


@app.route("/research")
@requires_auth
def research_control_surface():
    return render_template("research_control_surface.html")


@app.route("/api/research/run-status")
@requires_auth
def api_research_run_status():
    return jsonify(research_runner.build_run_status_response())


@app.route("/api/research/latest")
@requires_auth
def api_research_latest():
    return jsonify(research_artifacts.load_research_latest_artifact())


@app.route("/api/research/empty-run-diagnostics")
@requires_auth
def api_research_empty_run_diagnostics():
    return jsonify(research_artifacts.load_empty_run_diagnostics_artifact())


@app.route("/api/research/universe")
@requires_auth
def api_research_universe():
    return jsonify(research_artifacts.load_universe_snapshot_artifact())


@app.route("/api/research/run", methods=["POST"])
@require_operator_auth()
def api_research_run():
    payload, status_code = research_runner.launch_research_run()
    return jsonify(payload), status_code


# ──────────────────────────────────────────────
# API — Status
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/status")
def api_status():
    # Haal kapitaal op uit DB
    rijen = _db_query(
        "SELECT bedrag FROM kapitaal_geschiedenis ORDER BY tijdstip DESC LIMIT 1"
    )
    huidig = rijen[0]["bedrag"] if rijen else START_KAPITAAL
    totaal_rendement = round((huidig - START_KAPITAAL) / START_KAPITAAL * 100, 2)

    # Dag P&L (trades gesloten vandaag)
    dag_rijen = _db_query(
        """
        SELECT COALESCE(SUM(pnl), 0) as dag_pnl
        FROM trades
        WHERE pnl IS NOT NULL
          AND date(exit_tijdstip, 'localtime') = date('now', 'localtime')
        """
    )
    dag_pnl = round(dag_rijen[0]["dag_pnl"], 2) if dag_rijen else 0.0

    # Win rate (30 dagen)
    wr_rijen = _db_query(
        """
        SELECT COUNT(*) as totaal,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winsten
        FROM trades
        WHERE pnl IS NOT NULL
          AND exit_tijdstip > datetime('now', '-30 days', 'localtime')
        """
    )
    totaal = wr_rijen[0]["totaal"] if wr_rijen else 0
    winsten = wr_rijen[0]["winsten"] if wr_rijen else 0
    win_rate = round(winsten / totaal * 100, 1) if totaal > 0 else 0.0

    # Open posities
    open_rijen = _db_query(
        "SELECT COUNT(*) as n FROM trades WHERE exit_tijdstip IS NULL OR exit_tijdstip = ''"
    )
    open_posities = open_rijen[0]["n"] if open_rijen else 0

    # Agent actief = geen pause flag
    agent_actief = not PAUSE_FLAG.exists()

    return jsonify({
        "huidig_kapitaal":  round(huidig, 2),
        "dag_pnl":          dag_pnl,
        "totaal_rendement": totaal_rendement,
        "win_rate_30d":     win_rate,
        "open_posities":    open_posities,
        "agent_actief":     agent_actief,
        "laatste_update":   datetime.now().strftime("%H:%M:%S"),
    })


# ──────────────────────────────────────────────
# API — Trades
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/trades/recent")
def api_trades_recent():
    rijen = _db_query(
        """
        SELECT id, symbool, richting, strategie_type,
               entry_prijs, exit_prijs, euro_bedrag,
               pnl, pnl_pct,
               entry_tijdstip, exit_tijdstip,
               reden_entry, reden_exit, geleerd, regime
        FROM trades
        ORDER BY entry_tijdstip DESC
        LIMIT 50
        """
    )
    return jsonify(rijen)


# ──────────────────────────────────────────────
# API — Kapitaalgroei
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/performance")
def api_performance():
    if not DB_PAD.exists():
        return jsonify([])

    with _db_connect() as conn:
        # Primair: kapitaal_geschiedenis tabel
        if _table_bestaat(conn, "kapitaal_geschiedenis"):
            cursor = conn.execute(
                """
                SELECT date(tijdstip, 'localtime') as datum,
                       MAX(bedrag) as kapitaal
                FROM kapitaal_geschiedenis
                GROUP BY date(tijdstip, 'localtime')
                ORDER BY datum ASC
                """
            )
            rijen = cursor.fetchall()
            if rijen:
                return jsonify([{"datum": r[0], "kapitaal": round(r[1], 2)} for r in rijen])

        # Fallback: cumulatieve PnL uit trades
        cursor = conn.execute(
            """
            SELECT date(exit_tijdstip, 'localtime') as datum,
                   SUM(pnl) as dag_pnl
            FROM trades
            WHERE exit_tijdstip IS NOT NULL AND pnl IS NOT NULL
            GROUP BY date(exit_tijdstip, 'localtime')
            ORDER BY datum ASC
            """
        )
        rijen = cursor.fetchall()

    lopend = START_KAPITAAL
    resultaat = [{"datum": datetime.now().strftime("%Y-%m-%d"), "kapitaal": round(lopend, 2)}]
    for datum, dag_pnl in rijen:
        lopend += (dag_pnl or 0)
        resultaat.append({"datum": datum, "kapitaal": round(lopend, 2)})

    return jsonify(sorted(resultaat, key=lambda x: x["datum"]))


# ──────────────────────────────────────────────
# API — Strategie prestaties
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/strategie/prestaties")
def api_strategie_prestaties():
    rijen = _db_query(
        """
        SELECT strategie_type,
               COUNT(*) as totaal,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winst,
               ROUND(AVG(pnl_pct) * 100, 2) as gem_rendement_pct,
               ROUND(SUM(pnl), 2) as totaal_pnl
        FROM trades
        WHERE pnl IS NOT NULL
        GROUP BY strategie_type
        ORDER BY totaal_pnl DESC
        """
    )
    return jsonify(rijen)


# ──────────────────────────────────────────────
# API — Win/verlies per week
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/stats/per-week")
def api_stats_per_week():
    rijen = _db_query(
        """
        SELECT strftime('%Y-W%W', exit_tijdstip, 'localtime') as week,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winsten,
               SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as verliezen,
               ROUND(SUM(pnl), 2) as week_pnl
        FROM trades
        WHERE exit_tijdstip IS NOT NULL AND pnl IS NOT NULL
        GROUP BY week
        ORDER BY week ASC
        LIMIT 12
        """
    )
    return jsonify(rijen)


# ──────────────────────────────────────────────
# API — Top 3 assets
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/stats/top-assets")
def api_stats_top_assets():
    rijen = _db_query(
        """
        SELECT symbool,
               COUNT(*) as totaal_trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winsten,
               ROUND(SUM(pnl), 2) as totaal_pnl,
               ROUND(AVG(pnl_pct) * 100, 2) as gem_rendement_pct
        FROM trades
        WHERE pnl IS NOT NULL
        GROUP BY symbool
        ORDER BY totaal_pnl DESC
        LIMIT 3
        """
    )
    return jsonify(rijen)


# ──────────────────────────────────────────────
# API — Heatmap per uur
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/stats/heatmap")
def api_stats_heatmap():
    rijen = _db_query(
        """
        SELECT CAST(strftime('%H', entry_tijdstip, 'localtime') AS INTEGER) as uur,
               COUNT(*) as trades,
               ROUND(SUM(pnl), 2) as totaal_pnl,
               ROUND(AVG(pnl_pct) * 100, 2) as gem_rendement_pct
        FROM trades
        WHERE pnl IS NOT NULL
        GROUP BY uur
        ORDER BY uur ASC
        """
    )
    uur_map = {r["uur"]: r for r in rijen}
    resultaat = []
    for h in range(24):
        resultaat.append(uur_map.get(h, {
            "uur": h, "trades": 0,
            "totaal_pnl": 0.0, "gem_rendement_pct": 0.0
        }))
    return jsonify(resultaat)


# ──────────────────────────────────────────────
# API — Live koersen
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/prices/live")
def api_prices_live():
    ouderdom = int(time.time() - _prijzen_cache_tijd) if _prijzen_cache_tijd else -1
    return jsonify({
        "prijzen": _prijzen_cache,
        "cache_ouderdom_sec": ouderdom,
    })


# ──────────────────────────────────────────────
# API — Regime per asset
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/regime/huidig")
def api_regime_huidig():
    if not DB_PAD.exists():
        return jsonify({})
    with _db_connect() as conn:
        cursor = conn.execute(
            """
            SELECT symbool, regime, MAX(entry_tijdstip) as laatste
            FROM trades
            WHERE regime IS NOT NULL AND regime != ''
            GROUP BY symbool
            ORDER BY symbool
            """
        )
        rows = cursor.fetchall()
    result = {r[0]: {"regime": r[1], "vanaf": r[2]} for r in rows}
    return jsonify(result)


# ──────────────────────────────────────────────
# API — Sentiment
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/sentiment/huidig")
def api_sentiment_huidig():
    if not DB_PAD.exists():
        return jsonify({"beschikbaar": False, "data": []})
    with _db_connect() as conn:
        if not _table_bestaat(conn, "sentiment_effectiviteit"):
            return jsonify({"beschikbaar": False, "data": []})
        cursor = conn.execute(
            """
            SELECT bron,
                   ROUND(AVG(voorspelling_correct), 3) as score,
                   MAX(datum) as laatste
            FROM sentiment_effectiviteit
            GROUP BY bron
            ORDER BY score DESC
            """
        )
        kolommen = [d[0] for d in cursor.description]
        data = [dict(zip(kolommen, r)) for r in cursor.fetchall()]
    return jsonify({"beschikbaar": bool(data), "data": data})


# ──────────────────────────────────────────────
# API — Live log feed
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/logs/recent")
def api_logs_recent():
    if not LOG_PAD.exists():
        return jsonify([])
    with open(LOG_PAD, encoding="utf-8", errors="replace") as f:
        regels = f.readlines()
    return jsonify([r.rstrip("\n") for r in regels[-50:]])


# ──────────────────────────────────────────────
# API — Audit log (zelfverbeteringen)
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/audit/log")
def api_audit_log():
    if not AUDIT_LOG.exists():
        return jsonify([])
    entries = []
    with open(AUDIT_LOG, encoding="utf-8", errors="replace") as f:
        for regel in f:
            regel = regel.strip()
            if not regel:
                continue
            try:
                entries.append(json.loads(regel))
            except json.JSONDecodeError:
                entries.append({"raw": regel, "tijdstip": "", "status": "?", "uitleg": regel})
    return jsonify(entries[-50:])


# ──────────────────────────────────────────────
# API — Pauze
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/agent/pauze/status")
def api_pauze_status():
    return jsonify({"gepauzeerd": PAUSE_FLAG.exists()})


@app.route("/api/agent/pauze", methods=["POST"])
@require_operator_auth()
def api_pauze_toggle():
    actor = _operator_actor()
    data = request.get_json(silent=True) or {}
    actie = data.get("actie", "toggle")
    audit_log.append(
        event="dashboard_pause_requested",
        actor=actor,
        payload={"actie": actie, "gepauzeerd": PAUSE_FLAG.exists()},
    )
    try:
        if actie == "pauze" or (actie == "toggle" and not PAUSE_FLAG.exists()):
            PAUSE_FLAG.parent.mkdir(exist_ok=True)
            PAUSE_FLAG.touch()
            response = {"gepauzeerd": True}
        else:
            PAUSE_FLAG.unlink(missing_ok=True)
            response = {"gepauzeerd": False}

        audit_log.append(
            event="dashboard_pause_succeeded",
            actor=actor,
            payload={"actie": actie, **response},
        )
        return jsonify(response)
    except Exception as e:
        audit_log.append(
            event="dashboard_pause_failed",
            actor=actor,
            payload={"actie": actie, "error": str(e)},
        )
        raise


# ──────────────────────────────────────────────
# API — Drawdown
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/stats/drawdown")
def api_stats_drawdown():
    if not DB_PAD.exists():
        return jsonify({"drawdown_pct": 0, "waarschuwing": False, "huidig": START_KAPITAAL})

    with _db_connect() as conn:
        if _table_bestaat(conn, "kapitaal_geschiedenis"):
            cursor = conn.execute(
                "SELECT bedrag FROM kapitaal_geschiedenis ORDER BY tijdstip ASC"
            )
            bedragen = [r[0] for r in cursor.fetchall()]
        else:
            bedragen = []

    if not bedragen:
        # Fallback: bereken uit trades
        rijen = _db_query(
            "SELECT pnl FROM trades WHERE pnl IS NOT NULL ORDER BY exit_tijdstip ASC"
        )
        lopend = START_KAPITAAL
        bedragen = [START_KAPITAAL]
        for r in rijen:
            lopend += r["pnl"]
            bedragen.append(lopend)

    piek = max(bedragen)
    huidig = bedragen[-1]
    drawdown = max(0.0, (piek - huidig) / piek * 100) if piek > 0 else 0.0

    return jsonify({
        "drawdown_pct": round(drawdown, 2),
        "piek":         round(piek, 2),
        "huidig":       round(huidig, 2),
        "waarschuwing": drawdown > 25,
        "kritiek":      drawdown > 40,
    })


# ──────────────────────────────────────────────
# API — Reeks verliezen
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/stats/reeks-verliezen")
def api_reeks_verliezen():
    rijen = _db_query(
        """
        SELECT pnl FROM trades
        WHERE exit_tijdstip IS NOT NULL AND pnl IS NOT NULL
        ORDER BY exit_tijdstip DESC
        LIMIT 10
        """
    )
    reeks = 0
    for r in rijen:
        if r["pnl"] < 0:
            reeks += 1
        else:
            break
    return jsonify({"reeks": reeks, "waarschuwing": reeks >= 3})


# ──────────────────────────────────────────────
# API — Laatste dagrapport
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/rapport/laatste")
def api_rapport_laatste():
    if not RAPPORT_MAP.exists():
        return jsonify({"rapport": "Nog geen rapporten beschikbaar."})
    bestanden = sorted(RAPPORT_MAP.glob("rapport_*.md"), reverse=True)
    if not bestanden:
        return jsonify({"rapport": "Agent draait. Eerste rapport verschijnt om 07:00."})
    try:
        tekst = bestanden[0].read_text(encoding="utf-8")
        return jsonify({"rapport": tekst, "bestand": bestanden[0].name})
    except Exception:
        return jsonify({"rapport": "Fout bij laden rapport."})




# ──────────────────────────────────────────────
# API — Sub-agent overzicht
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/agents/overzicht")
def api_agents_overzicht():
    """Statistieken per sub-agent (RSI, EMA, Bot, Sentiment)."""
    agents = [
        {"naam": "rsi",            "label": "RSI Mean Reversion",  "kapitaal_doel": 300},
        {"naam": "ema",            "label": "EMA Crossover",        "kapitaal_doel": 300},
        {"naam": "bot",            "label": "Bot Exploiter",        "kapitaal_doel": 200},
        {"naam": "sentiment",      "label": "Sentiment",            "kapitaal_doel": 100},
        {"naam": "data_arbitrage", "label": "Data Arbitrage",       "kapitaal_doel": 100},
    ]
    resultaat = []
    for agent in agents:
        rijen = _db_query(
            """
            SELECT COUNT(*) as n,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(pnl) as totaal_pnl,
                   AVG(pnl) as gem_pnl
            FROM trades
            WHERE strategie_type LIKE ? AND pnl IS NOT NULL
            """,
            (f"%{agent['naam']}%",)
        )
        r = rijen[0] if rijen else {}
        n = r.get("n") or 0
        wins = r.get("wins") or 0
        win_rate = (wins / n * 100) if n > 0 else 0
        resultaat.append({
            "naam":           agent["naam"],
            "label":          agent["label"],
            "kapitaal_doel":  agent["kapitaal_doel"],
            "totaal_trades":  n,
            "win_rate":       round(win_rate, 1),
            "totaal_pnl":     round(r.get("totaal_pnl") or 0, 2),
            "gem_pnl":        round(r.get("gem_pnl") or 0, 2),
        })
    return jsonify(resultaat)


# ──────────────────────────────────────────────
# API — Test status
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/tests/status")
def api_tests_status():
    """Lees laatste test resultaat uit logs/test_resultaat.log."""
    log_pad = Path("logs/test_resultaat.log")
    if not log_pad.exists():
        return jsonify({
            "beschikbaar": False,
            "bericht": "Nog geen tests gedraaid. Draai: ./tests/run_tests.sh"
        })
    try:
        regels = log_pad.read_text(encoding="utf-8").strip().splitlines()
        return jsonify({
            "beschikbaar": True,
            "regels": regels[-50:],   # Laatste 50 regels
            "geslaagd": any("ALLE TESTS GESLAAGD" in r for r in regels),
        })
    except Exception as e:
        return jsonify({"beschikbaar": False, "bericht": str(e)})



# ──────────────────────────────────────────────
# API — Run tests (POST)
# ──────────────────────────────────────────────
@app.route("/api/tests/run", methods=["POST"])
@require_operator_auth()
def api_tests_run():
    """Start run_tests.sh in achtergrond en sla output op in logs/test_resultaat.log."""
    import subprocess

    actor = _operator_actor()
    audit_log.append(
        event="dashboard_tests_run_requested",
        actor=actor,
        payload={},
    )

    def _run(run_actor: str):
        try:
            log_pad = Path("logs/test_resultaat.log")
            result = subprocess.run(
                ["bash", "tests/run_tests.sh"],
                capture_output=True, text=True, timeout=120
            )
            output = result.stdout + result.stderr
            log_pad.write_text(output, encoding="utf-8")
            audit_log.append(
                event="dashboard_tests_run_finished",
                actor=run_actor,
                payload={"returncode": result.returncode},
            )
        except Exception as e:
            Path("logs/test_resultaat.log").write_text(str(e))
            audit_log.append(
                event="dashboard_tests_run_failed",
                actor=run_actor,
                payload={"error": str(e)},
            )

    threading.Thread(target=_run, args=(actor,), daemon=True).start()
    audit_log.append(
        event="dashboard_tests_run_queued",
        actor=actor,
        payload={},
    )
    return jsonify({"status": "gestart"})


# ──────────────────────────────────────────────
# API — Live koersen (alias)
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/prijzen")
def api_prijzen():
    """Eenvoudige alias: [{naam, prijs, valuta}]"""
    live = api_prices_live().get_json()
    if not live or "prijzen" not in live:
        return jsonify([])
    result = []
    for sym, info in live["prijzen"].items():
        result.append({
            "naam": sym,
            "prijs": info.get("prijs"),
            "valuta": "EUR" if info.get("type") == "crypto" else "USD"
        })
    return jsonify(result)


# ──────────────────────────────────────────────
# API — Kapitaal geschiedenis
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/kapitaal/geschiedenis")
def api_kapitaal_geschiedenis():
    return api_performance()



# ──────────────────────────────────────────────
# API — Backtest resultaten
# ──────────────────────────────────────────────
# AUDIT: read-only
@app.route("/api/backtests")
def api_backtests():
    import json as _json
    results_path = BASE_DIR / "reports" / "backtest_resultaten.json"
    if not os.path.exists(results_path):
        return jsonify({"error": "Nog geen backtest resultaten"}), 404
    with open(results_path, encoding="utf-8") as f:
        data = _json.load(f)
    strategieen = []
    for key, s in data.get("strategieen", {}).items():
        strategieen.append({
            "id": key,
            "naam": s.get("strategie", key),
            "goedgekeurd": s.get("goedgekeurd", False),
            "reden": s.get("reden", ""),
            "win_rate": round(s.get("win_rate", 0) * 100, 1),
            "deflated_sharpe": round(s.get("deflated_sharpe", 0), 3),
            "max_drawdown": round(s.get("max_drawdown", 0) * 100, 1),
            "trades_per_maand": round(s.get("trades_per_maand", 0), 1),
            "consistentie": round(s.get("consistentie", 0) * 100, 1),
            "totaal_trades": int(s.get("totaal_trades", 0)),
            "beste_params": s.get("beste_params", {}),
            "assets": s.get("assets", []),
            "criteria_checks": s.get("criteria_checks", {}),
        })
    return jsonify({
        "gegenereerd_op": data.get("gegenereerd_op", ""),
        "strategieen": strategieen,
    })

# ──────────────────────────────────────────────
# PWA — manifest + service worker
# ──────────────────────────────────────────────
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json",
                               mimetype="application/manifest+json")

@app.route("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js",
                               mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp

# ──────────────────────────────────────────────
# Start
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
