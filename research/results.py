"""
Results layer:
normaliseert research-uitkomsten en schrijft CSV + JSON output.
"""

import csv
import json
from datetime import datetime, timezone


# Frozen public output contracts. Do NOT edit without an approved
# contract change. These tuples are consumed by the guards below.
ROW_SCHEMA: tuple[str, ...] = (
    "timestamp_utc",
    "strategy_name",
    "family",
    "hypothesis",
    "asset",
    "interval",
    "params_json",
    "success",
    "error",
    "win_rate",
    "sharpe",
    "deflated_sharpe",
    "max_drawdown",
    "trades_per_maand",
    "consistentie",
    "totaal_trades",
    "goedgekeurd",
    "criteria_checks_json",
    "reden",
)

JSON_TOP_LEVEL_SCHEMA: tuple[str, ...] = (
    "generated_at_utc",
    "count",
    "summary",
    "results",
)

JSON_SUMMARY_SCHEMA: tuple[str, ...] = (
    "success",
    "failed",
    "goedgekeurd",
)


class SchemaDriftError(RuntimeError):
    """Raised when a research output row or payload drifts from the
    frozen contract. Never catch broadly - drift must surface."""


CSV_PATH = "research/strategy_matrix.csv"
JSON_PATH = "research/research_latest.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def format_utc_timestamp(as_of_utc: datetime) -> str:
    return as_of_utc.astimezone(timezone.utc).isoformat()


def make_result_row(strategy, asset, interval, params, as_of_utc, metrics=None, error=None):
    metrics = metrics or {}

    name = strategy.get("name") if isinstance(strategy, dict) else None
    if not isinstance(name, str) or not name:
        raise ValueError(
            "make_result_row: strategy['name'] must be a non-empty string; "
            f"got {name!r} from strategy={strategy!r}"
        )

    return {
        "timestamp_utc": format_utc_timestamp(as_of_utc),
        "strategy_name": name,
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


def _assert_row_schema(row, index):
    actual = tuple(row.keys())
    if actual != ROW_SCHEMA:
        missing = tuple(k for k in ROW_SCHEMA if k not in actual)
        extra = tuple(k for k in actual if k not in ROW_SCHEMA)
        raise SchemaDriftError(
            f"row {index} schema drift: "
            f"missing={missing} extra={extra} "
            f"actual_order={actual}"
        )


def _assert_payload_schema(payload):
    top = tuple(payload.keys())
    if top != JSON_TOP_LEVEL_SCHEMA:
        raise SchemaDriftError(
            f"json top-level drift: actual_order={top} "
            f"expected={JSON_TOP_LEVEL_SCHEMA}"
        )
    summary = tuple(payload["summary"].keys())
    if summary != JSON_SUMMARY_SCHEMA:
        raise SchemaDriftError(
            f"json summary drift: actual_order={summary} "
            f"expected={JSON_SUMMARY_SCHEMA}"
        )


def write_results_to_csv(rows, path=CSV_PATH):
    if not rows:
        return

    for i, row in enumerate(rows):
        _assert_row_schema(row, i)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(ROW_SCHEMA))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_latest_json(rows, as_of_utc, path=JSON_PATH):
    for i, row in enumerate(rows):
        _assert_row_schema(row, i)

    payload = {
        "generated_at_utc": format_utc_timestamp(as_of_utc),
        "count": len(rows),
        "summary": {
            "success": sum(1 for r in rows if r["success"]),
            "failed": sum(1 for r in rows if not r["success"]),
            "goedgekeurd": sum(1 for r in rows if r["goedgekeurd"]),
        },
        "results": rows,
    }

    _assert_payload_schema(payload)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
