"""Fail-closed fundamental readiness gate for equity-factor research intake."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.data_readiness.factor_field_coverage import build_factor_field_coverage
from research.equity_factors.factor_catalog import build_equity_factor_catalog
from research.equity_factors.recipe_catalog import build_equity_factor_recipe_catalog
from research.equity_universe_catalog import build_equity_universe_catalog
from research.equity_universe_quality import build_equity_universe_quality


SCHEMA_VERSION: Final[str] = "1.0"
READINESS_VOCABULARY: Final[tuple[str, ...]] = ("READY", "NOT_READY", "PARTIAL", "UNKNOWN")
BLOCK_REASON_VOCABULARY: Final[tuple[str, ...]] = (
    "MISSING_SOURCE_MANIFEST",
    "MISSING_POINT_IN_TIME_POLICY",
    "MISSING_REQUIRED_FIELD",
    "MISSING_CURRENCY_NORMALIZATION",
    "MISSING_REPORT_LAG_POLICY",
    "MISSING_RESTATEMENT_POLICY",
    "FACTOR_FIELD_COVERAGE_UNKNOWN",
    "UNIVERSE_IDENTITY_NOT_READY",
    "SOURCE_LICENSE_UNKNOWN",
    "SOURCE_QUALITY_UNKNOWN",
    "UNKNOWN",
)


def _factor_row(
    factor_row: dict[str, object],
    coverage_row: dict[str, object],
) -> dict[str, object]:
    block_reasons = [
        "MISSING_SOURCE_MANIFEST",
        "MISSING_REQUIRED_FIELD",
        "SOURCE_LICENSE_UNKNOWN",
        "SOURCE_QUALITY_UNKNOWN",
    ]
    if factor_row["point_in_time_required"]:
        block_reasons.extend(
            ["MISSING_POINT_IN_TIME_POLICY", "MISSING_REPORT_LAG_POLICY", "MISSING_RESTATEMENT_POLICY"]
        )
    if coverage_row["currency_normalization_required"]:
        block_reasons.append("MISSING_CURRENCY_NORMALIZATION")
    return {
        "factor_id": factor_row["factor_id"],
        "required_fields": list(factor_row["required_fields"]),
        "point_in_time_required": bool(factor_row["point_in_time_required"]),
        "report_lag_required": bool(factor_row["point_in_time_required"]),
        "restatement_risk": factor_row["restatement_risk"],
        "currency_normalization_required": bool(coverage_row["currency_normalization_required"]),
        "source_manifest_required": True,
        "field_coverage_status": coverage_row["field_coverage_status"],
        "readiness_status": "NOT_READY",
        "readiness_block_reasons": sorted(set(block_reasons)),
    }


def build_fundamental_readiness() -> dict[str, object]:
    factor_catalog = build_equity_factor_catalog()["rows"]
    factor_coverage_rows = {
        row["factor_id"]: row for row in build_factor_field_coverage()["rows"]
    }
    quality_rows = build_equity_universe_quality()["rows"]
    recipe_rows = build_equity_factor_recipe_catalog()["rows"]
    instrument_universes = {
        instrument["symbol"]: list(instrument["universe_ids"])
        for instrument in build_equity_universe_catalog()["instruments"]
    }
    universe_quality_by_universe: dict[str, str] = {}
    for quality_row in quality_rows:
        readiness = str(quality_row["universe_readiness_status"])
        for universe_id in instrument_universes.get(str(quality_row["symbol"]), []):
            previous = universe_quality_by_universe.get(universe_id, "OK")
            universe_quality_by_universe[universe_id] = "WARN" if "WARN" in {previous, readiness} else previous
            if readiness == "FAIL":
                universe_quality_by_universe[universe_id] = "FAIL"
    factor_rows = [
        _factor_row(row, factor_coverage_rows[str(row["factor_id"])]) for row in factor_catalog
    ]
    factor_rows.sort(key=lambda item: str(item["factor_id"]))
    factor_readiness = {row["factor_id"]: row for row in factor_rows}

    recipe_readiness_rows: list[dict[str, object]] = []
    for row in recipe_rows:
        block_reasons = {"MISSING_SOURCE_MANIFEST", "SOURCE_LICENSE_UNKNOWN", "SOURCE_QUALITY_UNKNOWN"}
        if any(
            factor_readiness[factor_id]["point_in_time_required"] for factor_id in row["required_factor_ids"]
        ):
            block_reasons.update(
                {"MISSING_POINT_IN_TIME_POLICY", "MISSING_REPORT_LAG_POLICY", "MISSING_RESTATEMENT_POLICY"}
            )
        if any(
            factor_readiness[factor_id]["currency_normalization_required"]
            for factor_id in row["required_factor_ids"]
        ):
            block_reasons.add("MISSING_CURRENCY_NORMALIZATION")
        if any(
            universe_quality_by_universe.get(universe_id, "UNKNOWN") != "OK"
            for universe_id in row["target_universe_ids"]
        ):
            block_reasons.add("UNIVERSE_IDENTITY_NOT_READY")
        block_reasons.add("MISSING_REQUIRED_FIELD")
        recipe_readiness_rows.append(
            {
                "recipe_id": row["recipe_id"],
                "target_universe_ids": list(row["target_universe_ids"]),
                "required_factor_ids": list(row["required_factor_ids"]),
                "source_manifest_dependency": True,
                "universe_identity_dependency": True,
                "point_in_time_required": any(
                    factor_readiness[factor_id]["point_in_time_required"]
                    for factor_id in row["required_factor_ids"]
                ),
                "report_lag_required": any(
                    factor_readiness[factor_id]["report_lag_required"]
                    for factor_id in row["required_factor_ids"]
                ),
                "restatement_risk": "present",
                "currency_normalization_required": any(
                    factor_readiness[factor_id]["currency_normalization_required"]
                    for factor_id in row["required_factor_ids"]
                ),
                "field_coverage_status": "MISSING",
                "readiness_status": "NOT_READY",
                "readiness_block_reasons": sorted(block_reasons),
            }
        )
    recipe_readiness_rows.sort(key=lambda item: str(item["recipe_id"]))
    readiness_counts = Counter(row["readiness_status"] for row in factor_rows + recipe_readiness_rows)
    block_counts = Counter(reason for row in recipe_readiness_rows + factor_rows for reason in row["readiness_block_reasons"])
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "fundamental_readiness",
        "readiness_status_vocabulary": list(READINESS_VOCABULARY),
        "block_reason_vocabulary": list(BLOCK_REASON_VOCABULARY),
        "summary": {
            "factor_rows": len(factor_rows),
            "recipe_rows": len(recipe_readiness_rows),
            "ready_count": readiness_counts.get("READY", 0),
            "partial_count": readiness_counts.get("PARTIAL", 0),
            "not_ready_count": readiness_counts.get("NOT_READY", 0),
            "unknown_count": readiness_counts.get("UNKNOWN", 0),
            "top_block_reasons": dict(sorted(block_counts.items())),
            "operator_summary": (
                "Fundamental readiness is fail-closed until source manifests, point-in-time policy, report-lag policy, "
                "and field coverage manifests exist."
            ),
        },
        "factor_rows": factor_rows,
        "recipe_rows": recipe_readiness_rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
