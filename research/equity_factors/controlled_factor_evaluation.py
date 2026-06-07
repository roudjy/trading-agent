"""Read-only controlled factor evaluation readiness scaffold."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.data_readiness.fundamental_readiness import build_fundamental_readiness
from research.equity_factors.factor_catalog import build_equity_factor_calculation_contracts
from research.hypothesis_discovery.equity_factor_hypothesis_adapter import (
    build_equity_factor_hypothesis_seeds,
)


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "controlled_factor_evaluation_readiness"
READINESS_VOCABULARY: Final[tuple[str, ...]] = (
    "READY_FOR_CONTROLLED_EVAL",
    "NOT_READY",
    "BLOCKED",
)
FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "trade",
    "buy_list",
    "sell_list",
    "strategy_registration",
    "candidate_promotion",
    "paper",
    "shadow",
    "live",
    "capital_allocation",
)


def _map_seed_block_reasons(seed_reasons: list[str]) -> list[str]:
    mapped: list[str] = []
    for reason in seed_reasons:
        mapped_reason = {
            "BLOCKED_DATA_READINESS_MISSING": "BLOCKED_DATA_READINESS",
            "MISSING_SOURCE_MANIFEST": "BLOCKED_SOURCE_MANIFEST",
            "MISSING_POINT_IN_TIME_POLICY": "BLOCKED_POINT_IN_TIME_POLICY",
            "MISSING_REQUIRED_FIELD": "BLOCKED_FIELD_COVERAGE",
            "FACTOR_FIELD_COVERAGE_UNKNOWN": "BLOCKED_FIELD_COVERAGE",
            "BLOCKED_IDENTITY_AMBIGUITY": "BLOCKED_IDENTITY_AMBIGUITY",
            "UNIVERSE_IDENTITY_NOT_READY": "BLOCKED_IDENTITY_AMBIGUITY",
            "MISSING_CURRENCY_NORMALIZATION": "BLOCKED_CURRENCY_NORMALIZATION",
        }.get(reason, reason)
        if mapped_reason not in mapped:
            mapped.append(mapped_reason)
    return mapped


def _allowed_next_action(blocked_reason_codes: list[str], readiness_status: str) -> str:
    if "BLOCKED_SOURCE_MANIFEST" in blocked_reason_codes:
        return "add_source_manifest"
    if "BLOCKED_FIELD_COVERAGE" in blocked_reason_codes:
        return "add_field_coverage_manifest"
    if "BLOCKED_POINT_IN_TIME_POLICY" in blocked_reason_codes:
        return "add_point_in_time_policy"
    if "BLOCKED_CURRENCY_NORMALIZATION" in blocked_reason_codes:
        return "add_currency_normalization_policy"
    if "BLOCKED_OOS_POLICY" in blocked_reason_codes:
        return "add_oos_policy"
    if "BLOCKED_COST_MODEL" in blocked_reason_codes:
        return "add_cost_model"
    if "BLOCKED_NULL_MODEL" in blocked_reason_codes:
        return "add_null_model"
    return "operator_review" if readiness_status != "READY_FOR_CONTROLLED_EVAL" else "operator_review"


def build_controlled_factor_evaluation_readiness() -> dict[str, object]:
    seed_report = build_equity_factor_hypothesis_seeds()
    readiness_report = build_fundamental_readiness()
    factor_contracts = {
        str(row["factor_id"]): row
        for row in build_equity_factor_calculation_contracts().get("rows", [])
    }
    factor_readiness = {
        str(row["factor_id"]): row for row in readiness_report.get("factor_rows", [])
    }

    rows: list[dict[str, object]] = []
    for seed in seed_report.get("rows", []):
        factor_ids = [str(item) for item in seed["factor_ids"]]
        required_fields = sorted(
            {
                str(field)
                for factor_id in factor_ids
                for field in factor_contracts.get(factor_id, {}).get("required_fields", [])
            }
        )
        point_in_time_required = any(
            bool(factor_contracts.get(factor_id, {}).get("point_in_time_required"))
            for factor_id in factor_ids
        )
        currency_normalization_required = any(
            bool(factor_readiness.get(factor_id, {}).get("currency_normalization_required"))
            for factor_id in factor_ids
        )
        blocked_reason_codes = _map_seed_block_reasons(
            [str(reason) for reason in seed.get("blocked_reason_codes", [])]
        )
        if str(seed["feasibility_status"]) == "BLOCKED":
            readiness_status = "BLOCKED"
        else:
            if point_in_time_required and "BLOCKED_POINT_IN_TIME_POLICY" not in blocked_reason_codes:
                blocked_reason_codes.append("BLOCKED_POINT_IN_TIME_POLICY")
            if currency_normalization_required and "BLOCKED_CURRENCY_NORMALIZATION" not in blocked_reason_codes:
                blocked_reason_codes.append("BLOCKED_CURRENCY_NORMALIZATION")
            for reason in ("BLOCKED_OOS_POLICY", "BLOCKED_COST_MODEL", "BLOCKED_NULL_MODEL"):
                if reason not in blocked_reason_codes:
                    blocked_reason_codes.append(reason)
            readiness_status = "READY_FOR_CONTROLLED_EVAL" if not blocked_reason_codes else "NOT_READY"

        operator_explanation = (
            "Controlled factor evaluation remains blocked until source manifests, field coverage, "
            "point-in-time policy, OOS policy, cost model, and null model are all explicitly present."
            if readiness_status != "READY_FOR_CONTROLLED_EVAL"
            else "Controlled factor evaluation scaffold is ready for bounded read-only evaluation only."
        )
        rows.append(
            {
                "evaluation_id": f"controlled_factor_eval::{seed['hypothesis_seed_id']}",
                "source_hypothesis_seed_id": seed["hypothesis_seed_id"],
                "source_recipe_id": seed["source_recipe_id"],
                "target_universe_ids": list(seed["target_universe_ids"]),
                "factor_ids": factor_ids,
                "readiness_status": readiness_status,
                "blocked_reason_codes": blocked_reason_codes,
                "required_data_fields": required_fields,
                "required_source_manifests": ["fundamental_source_manifest_v1"],
                "required_point_in_time_policy": point_in_time_required,
                "required_currency_normalization": currency_normalization_required,
                "required_oos_policy": True,
                "required_cost_model": True,
                "required_null_model": True,
                "allowed_next_action": _allowed_next_action(blocked_reason_codes, readiness_status),
                "forbidden_actions": list(FORBIDDEN_ACTIONS),
                "operator_explanation": operator_explanation,
            }
        )

    rows.sort(key=lambda row: str(row["evaluation_id"]))
    readiness_counts = Counter(str(row["readiness_status"]) for row in rows)
    block_counts = Counter(reason for row in rows for reason in row["blocked_reason_codes"])
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "readiness_status_vocabulary": list(READINESS_VOCABULARY),
        "summary": {
            "evaluation_count": len(rows),
            "ready_for_controlled_eval_count": readiness_counts.get("READY_FOR_CONTROLLED_EVAL", 0),
            "not_ready_count": readiness_counts.get("NOT_READY", 0),
            "blocked_count": readiness_counts.get("BLOCKED", 0),
            "top_block_reasons": dict(sorted(block_counts.items())),
            "operator_summary": (
                "Controlled factor evaluation is architecture-only at this stage. "
                "Rows stay blocked or not-ready until data and policy manifests are explicitly present."
            ),
        },
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
