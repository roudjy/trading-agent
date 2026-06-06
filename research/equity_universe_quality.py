"""Read-only quality checks for the static equity universe."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.equity_universe_catalog import list_equity_instruments
from research.equity_universe_identity import build_instrument_identity_report


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "equity_universe_quality"
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "canonical_id",
    "symbol",
    "display_name",
    "country",
    "exchange",
    "currency",
    "sector",
    "size_bucket",
    "liquidity_tier",
    "identity_confidence",
)


def _row_status(item: object) -> tuple[str, list[str]]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = getattr(item, field)
        if not str(value or "").strip():
            missing.append(f"missing_{field}")
    if missing:
        return "FAIL", missing
    if getattr(item, "ambiguous_mapping_warning"):
        return "WARN", ["ambiguous_mapping_warning"]
    if getattr(item, "identity_confidence") != "high":
        return "WARN", ["identity_confidence_not_high"]
    return "OK", []


def build_equity_universe_quality() -> dict[str, object]:
    instruments = list_equity_instruments()
    canonical_counts = Counter(item.canonical_id for item in instruments)
    symbol_counts = Counter(item.symbol for item in instruments)
    identity_report = build_instrument_identity_report()
    identity_rows = {
        str(row["canonical_id"]): row
        for row in identity_report["rows"]
        if isinstance(row, dict) and "canonical_id" in row
    }
    rows: list[dict[str, object]] = []
    for item in instruments:
        status, issues = _row_status(item)
        duplicate_canonical = canonical_counts[item.canonical_id] > 1
        duplicate_symbol = symbol_counts[item.symbol] > 1
        if duplicate_canonical:
            status = "FAIL"
            issues = [*issues, "duplicate_canonical_id"]
        if duplicate_symbol and "duplicate_symbol" not in issues:
            issues = [*issues, "duplicate_symbol"]
            if status == "OK":
                status = "WARN"
        rows.append(
            {
                "canonical_id": item.canonical_id,
                "symbol": item.symbol,
                "country": item.country,
                "exchange": item.exchange,
                "currency": item.currency,
                "identity_confidence": item.identity_confidence,
                "status": status,
                "issues": issues,
                "ambiguous_mapping_warning": item.ambiguous_mapping_warning,
                "identity_status": identity_rows.get(item.canonical_id, {}).get("identity_status", "UNKNOWN"),
                "eligible_for_hypothesis_seed": bool(
                    identity_rows.get(item.canonical_id, {}).get("eligible_for_hypothesis_seed")
                )
                and status == "OK",
                "universe_readiness_status": "OK"
                if status == "OK" and identity_rows.get(item.canonical_id, {}).get("identity_status") == "OK"
                else "FAIL"
                if status == "FAIL"
                or identity_rows.get(item.canonical_id, {}).get("identity_status") == "FAIL"
                else "WARN",
            }
        )
    status_counts = Counter(str(row["status"]) for row in rows)
    readiness_counts = Counter(str(row["universe_readiness_status"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "instrument_count": len(rows),
            "ok_instruments": status_counts.get("OK", 0),
            "warn_instruments": status_counts.get("WARN", 0),
            "fail_instruments": status_counts.get("FAIL", 0),
            "unknown_instruments": status_counts.get("UNKNOWN", 0),
            "ambiguous_mappings": sum(bool(row["ambiguous_mapping_warning"]) for row in rows),
            "duplicate_canonical_ids": sum("duplicate_canonical_id" in row["issues"] for row in rows),
            "duplicate_symbols": sum("duplicate_symbol" in row["issues"] for row in rows),
            "universe_readiness_counts": dict(sorted(readiness_counts.items())),
            "eligible_for_hypothesis_seed": sum(bool(row["eligible_for_hypothesis_seed"]) for row in rows),
            "blocked_for_hypothesis_seed": sum(not bool(row["eligible_for_hypothesis_seed"]) for row in rows),
            "operator_summary": (
                "Universe quality is metadata-only and fail-closed for ambiguity. "
                "Warnings and failures do not authorize any trading or strategy output."
            ),
        },
        "rows": rows,
        "status_vocabulary": ["OK", "WARN", "FAIL", "UNKNOWN"],
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }

