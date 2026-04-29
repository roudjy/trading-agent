# JvR Trading Agent — Master Context

## Project
Eigenaar: Joery van Rooij
Doel: Volledig autonoom trading systeem
Startkapitaal: €1.000 | Max drawdown: 50%
Financieel resultaat is een GEVOLG — nooit een sturing
De agent mag NOOIT risico verhogen om een doel te halen

Authority doctrine: `docs/adr/ADR-014-truth-authority-settlement.md` — canonical mapping of which subsystem owns truth for each domain (registry / presets / catalog / candidate lifecycle / paper readiness / live governance).

## Server
VPS: Hetzner CX22 | IP: 23.88.110.92
OS: Ubuntu 24.04 | Project: /root/trading-agent/
Dashboard: http://23.88.110.92:8050

---

## Claude Code Optimalisatie Protocol

SESSIE START — altijd:
- Lees eerst CLAUDE.md volledig
- Analyseer alleen bestanden relevant voor de taak
- Ga direct over tot actie zonder uitleg vooraf
- Toon alleen diffs, niet hele bestanden
- Plan eerst, dan pas uitvoeren

TIJDENS SESSIE:
- Gebruik /compact na grote wijzigingen of 10 berichten
- Meld als context boven 60% komt
- Splits grote refactors in kleine stappen
- Test na elke stap voordat je doorgaat
- Gebruik claude-3-5-sonnet — alleen Opus na 2 mislukte pogingen

SESSIE EINDE:
- Gebruik /clear bij nieuw onderdeel
- Commit altijd: git add . && git commit -m "beschrijving"

---

## Architectuur

Multi-agent systeem onder één orchestrator.
Elke agent heeft één edge en maximaal 3 parameters.
Nieuwe edge = nieuwe agent, nooit meer parameters.
Backtest eerst — win rate >52% en Sharpe >1.0 vereist.

## Agents

| Agent | Edge | Kapitaal | Parameters |
|---|---|---|---|
| RSI Agent | RSI extremen crypto | €300 | RSI drempel, stop-loss, cooldown |
| EMA Agent | Trend crossover aandelen | €300 | EMA periodes, volume, cooldown |
| Bot Agent | Bot patronen Polymarket | €200 | Max inzet, force exit, cooldown |
| Sentiment Agent | Nieuws sentiment | €100 | Sentiment drempel, RSI filter, cooldown |
| Data Arbitrage | Publieke data vs marktprijs | €100 | Zekerheid, mispricing%, max inzet |

Kapitaalregels:
- Min per agent: €30 | Max per agent: €400
- Totaal altijd: €1.000
- Dagelijkse herbalancering: ±5% op prestaties
- UCB1 formule bepaalt verdeling

## Assets

Crypto: BTC/EUR, ETH/EUR, SOL/EUR, BNB/EUR,
        ADA/EUR, DOT/EUR, MATIC/EUR, LINK/EUR
Aandelen: NVDA, AMD, ASML, AAPL, MSFT,
          GOOGL, META, TSLA, AMZN, TSM
Polymarket: sport, weer, economie, politiek

---

## Kernprincipes — NOOIT SCHENDEN

1. Simpliciteit: max 3 parameters per agent
2. Één edge per agent
3. Nooit Martingale — nooit positie vergroten na verlies
4. Geen stop-loss op Polymarket (binaire markten)
5. Force exit bij 75% winst — geen verdere checks
6. Stop-loss maximaal 8% — nooit hoger
7. Paper trading aan — Joery beslist over live
8. Drawdown limiet 50% — agent stopt zichzelf
9. Backtest eerst — Deflated Sharpe >1.0 vereist
10. Nooit hardcoded prijzen — altijd marktdata
11. Financieel doel is gevolg — nooit sturing
12. Nieuwe edge = nieuwe agent, nooit meer parameters

---

## Geleerde Lessen — Eigen Bugs

KRITIEK — nooit meer:
- Hardcoded prijzen → phantom verliezen van 43-52%
- Cooldown in memory → reset bij Docker herstart
- str(None) slaat "None" op als tekst → gebruik _fmt_dt()
- if trade.pnl faalt bij pnl=0.0 → gebruik is not None
- SignalAggregator mag nooit lege lijst teruggeven
- Stop-loss te groot ingesteld (was 43%, max is 8%)
- Drawdown limiet moet triggeren voor 56%
- Trades elke 60 seconden herhalen zonder positie check
- Dockerfile CMD verkeerd → altijd python run.py
- Executor gebruikt globale kapitaal ipv agent-pool → geef max_bedrag mee

FIXES GEÏMPLEMENTEERD:
- WAL mode + busy_timeout=5000 voor database
- _fmt_dt() helper voor datetime naar SQL
- Cooldown persistent in database
- Retry logica bij OperationalError: locked
- Dockerfile CMD = python run.py (niet agent.brain.agent)
- executor.voer_uit(signaal, markt_data=markt_data, max_bedrag=max_bedrag)
- DataArbitrageAgent injecteert Polymarket prijzen in markt_data via run_cyclus override

---

## Tech Stack

- Python 3.11
- Docker + docker-compose
- Flask dashboard op poort 8050
- SQLite: logs/agent_geheugen.db
- ta library (NIET pandas-ta)
- ccxt voor exchange connecties
- yfinance voor marktdata (auto_adjust=True)
- pytest voor tests

## ta Library — altijd zo gebruiken

RSI: ta.momentum.RSIIndicator(close, window=14).rsi()
MACD: ta.trend.MACD(close, window_slow=26,
      window_fast=12, window_sign=9).macd()
Bollinger: ta.volatility.BollingerBands(close,
      window=20, window_dev=2)
      .bollinger_hband/mavg/lband()
EMA: ta.trend.ema_indicator(close, window=20)

---

## Database Schema

trades: id, symbool, richting, strategie_type,
  entry_prijs, exit_prijs, hoeveelheid, euro_bedrag,
  pnl, pnl_pct, entry_tijdstip, exit_tijdstip,
  reden_entry, reden_exit, geleerd, regime,
  sentiment_score, exchange

cooldowns: symbool, agent_naam,
  laatste_trade, cooldown_uren

Database regels:
- Altijd WAL mode + busy_timeout=5000
- _fmt_dt() voor datetime naar SQL NULL conversie
- is not None voor pnl checks
- Retry logica bij OperationalError: locked

## Test Framework

pytest — 5 suites: smoke, unit, regressie,
integratie, resilience
Altijd draaien: bash tests/run_tests.sh
Alle tests moeten slagen voor elke deployment
Statische analyse: mypy, flake8, bandit

---

## Code Kwaliteitsregels

- Max 50 regels per functie
- Max 300 regels per bestand
- Elke functie heeft één verantwoordelijkheid
- Geen magic numbers — altijd constanten met naam
- Elke nieuwe functie heeft een docstring
- Typed hints altijd gebruiken
- Geen TODO comments in productie code

## Foutafhandeling Standaard

ALTIJD zo voor externe API calls:
try:
    resultaat = api_call()
except RateLimitError:
    wacht(60); retry()
except NetworkError:
    log_warning(); return None
except Exception as e:
    log_error(e); stuur_alert(); return None

NOOIT:
- Bare except zonder type
- Pass in except blok
- Crash zonder logging

---

## Data Validatie Regels

VERWERP data als:
- Prijs is 0 of negatief
- Prijs wijkt >20% af van vorige waarde in 1 minuut
- Volume is 0 tijdens handelsuren
- Timestamp meer dan 5 minuten oud

YAHOO FINANCE:
- Gebruik altijd auto_adjust=True
- Adjusted close, nooit gewone close
- Weekend data aandelen is altijd nul — skip

## Backtesting Valkuilen — Altijd Vermijden

LOOK-AHEAD BIAS:
Gebruik slotkoers dag X-1 om te handelen op dag X
Nooit slotkoers dag X gebruiken voor trade op dag X

SURVIVORSHIP BIAS:
Yahoo toont alleen bestaande bedrijven
Gebruik brede indices als benchmark

TRANSACTION COSTS — altijd includeren:
- Bitvavo: 0.25% per kant = 0.5% round trip
- IBKR: €1 per order
- Polymarket: 2% spread gemiddeld
- Slippage simulatie: 0.1% extra

---

## Portfolio Limieten

CORRELATIE:
- Max 40% kapitaal in assets met correlatie >0.7
- BTC en ETH tellen als één positie

CONCENTRATIE:
- Max 50% kapitaal in crypto
- Max 50% kapitaal in aandelen
- Max 30% per sector (bijv. semiconductors)

POSITIEGROOTTE:
positie = (doel_risico / asset_volatiliteit) × kapitaal
doel_risico = 0.01 (1% van kapitaal per trade)

---

## Trading Domeinkennis

CRYPTO:
- Handelt 24/7
- Weekend volumes 40% lager dan weekdagen
- Asia sessie 02:00-08:00 NL andere patronen
- Funding rates beïnvloeden spotprijs

AANDELEN:
- Handelsuren: 15:30-22:00 NL tijd
- Eerste 30 min na open (15:30-16:00): te volatiel
- Pre-market 15:00-15:30: vroege signalen
- Derde vrijdag van de maand: optieverval, hoge volatiliteit
- Earnings seizoen: feb, mei, aug, nov
- Dividenddata: dag voor ex-dividend kleine stijging

POLYMARKET:
- Meeste liquiditeit 18:00-24:00 NL
- Sport markten scherp geprijsd vlak na wedstrijd
- Politieke markten manipulatiegevoelig bij lage liquiditeit
- Geen stop-loss op binaire markten
- Max instapprijs: 60 cent
- Prijzen via Chainlink op Polygon, niet Gamma API
- Force exit bij 80% winst

---

## Wiskundige Principes — Zelfleren

PRIORITEIT 1 — Dag 1-7:
Fractional Kelly:
  f_safe = f* x (1 - 1/aantal_trades^0.5)
  Voorzichtig bij weinig data, zekerder bij meer

UCB1 kapitaalverdeling:
  Score = rendement + (2 x ln(totaal) / agent_trades)^0.5
  Agents met weinig data krijgen onzekerheidsbonus

Sortino Ratio:
  Sortino = rendement / standaarddeviatie_negatief
  Straft alleen neerwaartse volatiliteit

Bayesiaans updaten:
  Prior uit backtest, update op elke live trade
  Agent houdt onzekerheid bij, niet alleen win rate

PRIORITEIT 2 — Dag 7-14:
ATR stop-loss:
  stop = entry - (ATR x 1.5)
  Automatisch groter bij volatiele markt

Sentiment momentum:
  momentum = sentiment_vandaag - sentiment_gisteren

Calmar Ratio:
  Calmar = jaarlijks_rendement / max_drawdown

Deflated Sharpe:
  Corrigeert voor aantal geteste strategieen
  Alleen Deflated Sharpe >1.0 wordt goedgekeurd

PRIORITEIT 3 — Dag 21-30 (min 500 trades):
Hurst Exponent:
  H >0.5 trending, H <0.5 mean-reverting, H=0.5 random

Ensemble weighting:
  gewicht = Sharpe_agent / som Sharpe_alle_agents

Q-learning:
  staat = (regime, RSI_zone, sentiment_zone)
  actie = (long, short, niets)
  beloning = gerealiseerde PnL

HMM regime detectie:
  Probabilistische schatting marktregime

VADER sentiment:
  Speciaal getraind op financiele teksten

KERNREGEL ZELFLEREN:
- Max 3 parameters per agent — altijd
- Optimaliseer op drie metrics: win rate + Sortino + Calmar
- Walk-forward validatie — nooit trainen en testen op zelfde data
- Meer trades = meer zekerheid = hogere Kelly factor
- Nieuwe edge = nieuwe agent, nooit meer parameters
- Simpler is always better — Minimum Description Length

---

## API Keys (in config/config.yaml — nooit in code)

- Bitvavo: actief en bevestigd
- Anthropic: actief, $10 credit, cap $5/maand
- Alchemy: Polygon PoS endpoint actief
- MetaMask: 0xc9F8323e5124cd09B907abd744Df455482F7807B
- IBKR: account ID ingevoerd, TWS nog te koppelen
- Polymarket: private key ingevoerd
- Telegram: nog in te voeren na monitoring build

---

## ROADMAP — Maximaal 1 maand

WEEK 1 — Fundament (Dag 1-7):

Dag 1-2: Agent stabiel zonder bugs
  - Cooldown persistent in database ✓
  - Orphan trades verwijderd ✓
  - Dashboard data laadt correct ✓
  - Sub-agents zichtbaar in logs ✓
  - Dockerfile CMD correct (run.py) ✓
  - executor.voer_uit met max_bedrag ✓
  - DataArbitrage prijs injectie ✓
  - PWA op iPhone werkend
  - Statische analyse: mypy, flake8, bandit
  - Canary trade 08:00 actief
  - Fractional Kelly geimplementeerd
  - Bayesiaans updaten actief

Dag 2-3: Server robuust
  - SSH key ingesteld
  - Git geinitialiseerd
  - Watchdog script actief
  - Docker log limieten ingesteld
  - Hetzner backups aan
  - Anthropic cap $5/maand
  - check.sh script
  - Pre-commit hooks

Dag 3-4: Monitoring actief
  - Telegram bot aangemaakt
  - Kritieke alerts werkend
  - Server monitoring RAM/CPU/schijf
  - Auto recovery bij storingen
  - Backup systeem 02:00
  - Structured logging JSON
  - UCB1 kapitaalverdeling actief
  - Sortino Ratio in self_improver

Dag 4-7: Backtesting + bewezen strategieen
  - Backtesting engine met walk-forward
  - Deflated Sharpe voor goedkeuring
  - Alle 6 strategieen gebacktest
  - Goedgekeurde agents live
  - ATR dynamische stop-loss
  - Calmar Ratio toegevoegd
  - Chaos testing module

WEEK 2 — Uitbreiding (Dag 7-14):

Dag 6-8: Data Arbitrage Agent
  - Agent gebouwd ✓
  - Databronnen gekoppeld ✓
  - Kelly Criterion per trade ✓
  - Geintegreerd in orchestrator ✓

Dag 7-10: Eerste analyse
  - 50+ trades bereikt
  - Win rate per agent zichtbaar
  - Trade forensics actief
  - Sentiment momentum actief
  - Wekelijkse code review door Claude

Dag 10-14: Zelfleren verfijnd
  - Bayesiaans updaten geconvergeerd
  - Walk-forward validatie actief
  - Ensemble weighting op Sharpe
  - Hurst Exponent regime detectie
  - VADER sentiment analyse
  - Anomalie detectie actief

WEEK 3-4 — Geavanceerd (Dag 14-30):

Dag 14-21: Diep leren
  - 200+ trades bereikt
  - Walk-forward optimalisatie zinvol
  - Q-learning geimplementeerd
  - HMM regime detectie
  - Regression trend monitoring
  - Maandelijkse CSV belasting export

Dag 21-30: Volledig autonoom
  - 500+ trades bereikt
  - Q-learning geconvergeerd
  - Alle wiskundige lagen actief
  - Self_improver draait dagelijks
  - Systeem volledig autonoom

DAG 30: SYSTEEM VOLLEDIG AUTONOOM

NA DAG 30:
- Agent draait volledig autonoom
- Self_improver verfijnt wekelijks
- Nieuwe agents alleen bij bewezen backtest edge
- Wekelijks rapport met Claude analyse
- Maandelijks CSV voor belastingaangifte

---

## Financieel Principe

Het financiele resultaat is een GEVOLG van:
- Correcte implementatie
- Robuuste werking
- Bewezen strategieen
- Discipline om niet in te grijpen

De agent mag NOOIT:
- Risico verhogen om een financieel doel te halen
- Drawdown limiet aanpassen
- Paper trading uitzetten zonder Joery
- Martingale gebruiken
- Stop-loss verwijderen (behalve Polymarket)

---

## Aliases

VPS (toevoegen aan ~/.bashrc):
alias agent="cd /root/trading-agent && docker compose"
alias errors="cd /root/trading-agent && docker compose logs agent -f | grep ERROR"
alias trades="cd /root/trading-agent && docker compose logs agent -f | grep Trade"
alias btc="cd /root/trading-agent && docker compose logs agent -f | grep BTC"
alias check="bash /root/check.sh"

Mac (toevoegen aan ~/.zprofile):
alias vps="ssh root@23.88.110.92"
