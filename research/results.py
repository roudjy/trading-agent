"""
Results layer:
normaliseert research-uitkomsten en schrijft CSV + JSON output.
"""

import csv
import json
from datetime import datetime, timezone


CSV_PATH = "research/strategy_matrix.csv"
JSON_PATH = "research/research_latest.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def make_result_row(strategy, asset, interval, params, metrics=None, error=None):
    metrics = metrics or {}

    return {
        "timestamp_utc": utc_now(),
        "strategy_name": strategy["name"],
        "family": strategy["family"],
        "hypothesis": strategy["hypothesis"],
        "asset": asset,
        "interval": interval,
        "params_json": json.dumps(params, sort_keys=True),
        "success": error is None,
        "error": error or "",
        "win_rate": metrics.get("win_rate", 0.0),
        "sharpe": metrics.get("sharpe", 0.0),
        "deflated_sharpe": metrics.get("deflated_sharpe", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "trades_per_maand": metrics.get("trades_per_maand", 0.0),
        "consistentie": metrics.get("consistentie", 0.0),
        "totaal_trades": metrics.get("totaal_trades", 0),
        "goedgekeurd": metrics.get("goedgekeurd", False),
        "criteria_checks_json": json.dumps(metrics.get("criteria_checks", {}), sort_keys=True),
        "reden": metrics.get("reden", ""),
    }


def append_results_to_csv(rows, path=CSV_PATH):
    if not rows:
        return

    fieldnames = list(rows[0].keys())

    try:
        with open(path, "r", encoding="utf-8") as f:
            has_header = f.read(1) != ""
    except FileNotFoundError:
        has_header = False

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not has_header:
            writer.writeheader()

        for row in rows:
            writer.writerow(row)


def write_latest_json(rows, path=JSON_PATH):
    payload = {
        "generated_at_utc": utc_now(),
        "count": len(rows),
        "summary": {
            "success": sum(1 for r in rows if r["success"]),
            "failed": sum(1 for r in rows if not r["success"]),
            "goedgekeurd": sum(1 for r in rows if r["goedgekeurd"]),
        },
        "results": rows,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
