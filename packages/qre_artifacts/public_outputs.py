"""Read-only public output artifact contracts.

This module owns the frozen public research output schema and repo-relative
output paths. It contains no artifact writers, readers, dashboard wiring, or
execution-sensitive behavior.
"""

from __future__ import annotations

# Frozen public output contracts. Do NOT edit without an approved
# artifact-contract change. Writers import these constants; this package does
# not import writer modules.
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

CSV_PATH = "research/strategy_matrix.csv"
JSON_PATH = "research/research_latest.json"

__all__ = [
    "CSV_PATH",
    "JSON_PATH",
    "JSON_SUMMARY_SCHEMA",
    "JSON_TOP_LEVEL_SCHEMA",
    "ROW_SCHEMA",
]
