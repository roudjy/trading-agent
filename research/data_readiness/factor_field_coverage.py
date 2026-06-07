"""Deterministic fail-closed factor field coverage projection."""

from __future__ import annotations

from typing import Final

from research.equity_factors.factor_catalog import build_equity_factor_calculation_contracts


SCHEMA_VERSION: Final[str] = "1.0"
FIELD_COVERAGE_VOCABULARY: Final[tuple[str, ...]] = ("COVERED", "MISSING", "PARTIAL", "UNKNOWN")


def build_factor_field_coverage() -> dict[str, object]:
    contracts = build_equity_factor_calculation_contracts()["rows"]
    rows: list[dict[str, object]] = []
    for row in contracts:
        required_fields = [str(field) for field in row["required_fields"]]
        rows.append(
            {
                "factor_id": row["factor_id"],
                "required_fields": required_fields,
                "field_coverage": [
                    {"field_name": field_name, "coverage_status": "MISSING"}
                    for field_name in required_fields
                ],
                "field_coverage_status": "MISSING",
                "source_manifest_required": True,
                "point_in_time_required": bool(row["point_in_time_required"]),
                "report_lag_required": bool(row["point_in_time_required"]),
                "currency_normalization_required": "currency_consistent"
                in row["quality_gate_requirements"],
            }
        )
    rows.sort(key=lambda item: str(item["factor_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "factor_field_coverage",
        "summary": {
            "factor_count": len(rows),
            "covered_count": sum(row["field_coverage_status"] == "COVERED" for row in rows),
            "missing_count": sum(row["field_coverage_status"] == "MISSING" for row in rows),
            "partial_count": sum(row["field_coverage_status"] == "PARTIAL" for row in rows),
            "unknown_count": sum(row["field_coverage_status"] == "UNKNOWN" for row in rows),
            "operator_summary": (
                "Field coverage is fail-closed until a deterministic source manifest exists. "
                "This report does not claim any real fundamental field availability."
            ),
        },
        "field_coverage_status_vocabulary": list(FIELD_COVERAGE_VOCABULARY),
        "rows": rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
