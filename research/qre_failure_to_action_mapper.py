from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal


FailureClass = Literal[
    "non_positive_oos_trade_count",
    "missing_oos_trade_count",
    "missing_oos_window",
    "missing_oos_metrics",
    "missing_cost_slippage_refs",
    "campaign_lineage_missing",
    "candidate_lineage_missing",
    "scope_mismatch",
    "no_safe_local_source",
    "no_safe_local_bounded_command",
    "operator_approval_required",
    "external_fetch_approval_required",
    "insufficient_window_length",
    "insufficient_trades_across_windows",
    "regime_specific_no_trade_result",
    "all_preregistered_windows_failed",
    "null_control_failed",
    "evidence_acceptance_failed",
    "hypothesis_not_supported",
]

ActionAuthority = Literal["report_only", "approval_required", "forbidden_without_approval"]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_failure_to_action_mapper"
FAILURE_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "non_positive_oos_trade_count",
        "missing_oos_trade_count",
        "missing_oos_window",
        "missing_oos_metrics",
        "missing_cost_slippage_refs",
        "campaign_lineage_missing",
        "candidate_lineage_missing",
        "scope_mismatch",
        "no_safe_local_source",
        "no_safe_local_bounded_command",
        "operator_approval_required",
        "external_fetch_approval_required",
        "insufficient_window_length",
        "insufficient_trades_across_windows",
        "regime_specific_no_trade_result",
        "all_preregistered_windows_failed",
        "null_control_failed",
        "evidence_acceptance_failed",
        "hypothesis_not_supported",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def compute_failure_action_hash(payload: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": payload.get("schema_version", SCHEMA_VERSION),
        "report_kind": payload.get("report_kind", REPORT_KIND),
        "failure_class": payload.get("failure_class", ""),
        "recommended_action": payload.get("recommended_action", ""),
        "action_authority": payload.get("action_authority", ""),
        "reason_codes": list(payload.get("reason_codes", [])),
        "prerequisites": list(payload.get("prerequisites", [])),
        "can_execute": bool(payload.get("can_execute", False)),
        "can_mutate_queue": bool(payload.get("can_mutate_queue", False)),
        "can_clear_blocker": bool(payload.get("can_clear_blocker", False)),
        "can_redefine_window": bool(payload.get("can_redefine_window", False)),
        "can_tune_strategy": bool(payload.get("can_tune_strategy", False)),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _result(
    *,
    failure_class: str,
    recommended_action: str,
    action_authority: ActionAuthority,
    reason_codes: Sequence[str],
    prerequisites: Sequence[str],
) -> dict[str, Any]:
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "failure_class": failure_class,
        "recommended_action": recommended_action,
        "action_authority": action_authority,
        "reason_codes": _unique_in_order(reason_codes),
        "prerequisites": _unique_in_order(prerequisites),
        "can_execute": False,
        "can_mutate_queue": False,
        "can_clear_blocker": False,
        "can_redefine_window": False,
        "can_tune_strategy": False,
    }
    report["hash"] = compute_failure_action_hash(report)
    return report


def map_failure_to_action(
    *,
    failure_class: str,
    remaining_preregistered_window_count: int = 0,
    remaining_preregistered_regime_count: int = 0,
) -> dict[str, Any]:
    normalized = _text(failure_class)
    if normalized not in FAILURE_CLASSES:
        return _result(
            failure_class=normalized or "unknown_failure",
            recommended_action="route_to_operator_review",
            action_authority="report_only",
            reason_codes=["unknown_failure_fail_closed"],
            prerequisites=["operator_review_required"],
        )

    if normalized == "non_positive_oos_trade_count":
        if remaining_preregistered_window_count > 0:
            return _result(
                failure_class=normalized,
                recommended_action="run_next_preregistered_window",
                action_authority="approval_required",
                reason_codes=["non_positive_oos_trade_count", "next_preregistered_window_available"],
                prerequisites=["existing_preregistered_sampling_plan", "valid_exact_scope_approval"],
            )
        if remaining_preregistered_regime_count > 0:
            return _result(
                failure_class=normalized,
                recommended_action="run_next_preregistered_regime",
                action_authority="approval_required",
                reason_codes=["non_positive_oos_trade_count", "next_preregistered_regime_available"],
                prerequisites=["existing_preregistered_sampling_plan", "valid_exact_scope_approval"],
            )
        return _result(
            failure_class=normalized,
            recommended_action="reject_hypothesis",
            action_authority="report_only",
            reason_codes=["non_positive_oos_trade_count", "no_remaining_preregistered_windows"],
            prerequisites=["all_preregistered_windows_exhausted"],
        )

    direct_map: dict[str, tuple[str, ActionAuthority, list[str], list[str]]] = {
        "missing_oos_trade_count": (
            "repair_metadata_mapping",
            "report_only",
            ["missing_oos_trade_count", "metadata_repair_required"],
            ["structured_source_artifact_ref"],
        ),
        "missing_oos_window": (
            "repair_metadata_mapping",
            "report_only",
            ["missing_oos_window", "metadata_repair_required"],
            ["structured_source_artifact_ref"],
        ),
        "missing_oos_metrics": (
            "repair_metadata_mapping",
            "report_only",
            ["missing_oos_metrics", "metadata_repair_required"],
            ["structured_source_artifact_ref"],
        ),
        "missing_cost_slippage_refs": (
            "repair_metadata_mapping",
            "report_only",
            ["missing_cost_slippage_refs", "metadata_repair_required"],
            ["structured_source_artifact_ref"],
        ),
        "campaign_lineage_missing": (
            "repair_scope_matching",
            "report_only",
            ["campaign_lineage_missing", "lineage_scope_repair_required"],
            ["accepted_lineage_artifact_or_structured_source"],
        ),
        "candidate_lineage_missing": (
            "repair_scope_matching",
            "report_only",
            ["candidate_lineage_missing", "lineage_scope_repair_required"],
            ["accepted_lineage_artifact_or_structured_source"],
        ),
        "scope_mismatch": (
            "repair_scope_matching",
            "report_only",
            ["scope_mismatch", "exact_scope_repair_required"],
            ["exact_scope_reason_record"],
        ),
        "no_safe_local_source": (
            "stop_no_safe_next_action",
            "report_only",
            ["no_safe_local_source"],
            ["operator_review_required"],
        ),
        "no_safe_local_bounded_command": (
            "stop_no_safe_next_action",
            "report_only",
            ["no_safe_local_bounded_command"],
            ["operator_review_required"],
        ),
        "operator_approval_required": (
            "request_exact_operator_approval",
            "approval_required",
            ["operator_approval_required"],
            ["exact_scope_manifest"],
        ),
        "external_fetch_approval_required": (
            "request_external_fetch_approval",
            "approval_required",
            ["external_fetch_approval_required"],
            ["exact_scope_external_fetch_manifest"],
        ),
        "insufficient_window_length": (
            "create_preregistered_sampling_plan",
            "report_only",
            ["insufficient_window_length"],
            ["larger_preregistered_local_range"],
        ),
        "insufficient_trades_across_windows": (
            "reject_hypothesis",
            "report_only",
            ["insufficient_trades_across_windows"],
            ["all_preregistered_windows_completed"],
        ),
        "regime_specific_no_trade_result": (
            "run_next_preregistered_regime",
            "approval_required",
            ["regime_specific_no_trade_result"],
            ["remaining_preregistered_regime"],
        ),
        "all_preregistered_windows_failed": (
            "reject_hypothesis",
            "report_only",
            ["all_preregistered_windows_failed"],
            ["all_preregistered_windows_completed"],
        ),
        "null_control_failed": (
            "reject_hypothesis",
            "report_only",
            ["null_control_failed"],
            ["null_control_result_recorded"],
        ),
        "evidence_acceptance_failed": (
            "keep_fail_closed",
            "report_only",
            ["evidence_acceptance_failed"],
            ["verifier_rejection_reasons_preserved"],
        ),
        "hypothesis_not_supported": (
            "reject_hypothesis",
            "report_only",
            ["hypothesis_not_supported"],
            ["reason_record_preserved"],
        ),
    }
    action, authority, reasons, prerequisites = direct_map[normalized]
    return _result(
        failure_class=normalized,
        recommended_action=action,
        action_authority=authority,
        reason_codes=reasons,
        prerequisites=prerequisites,
    )


def validate_failure_action_mapping(report: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    if report.get("can_execute") is not False:
        rejection_reasons.append("can_execute_must_be_false")
    if report.get("can_mutate_queue") is not False:
        rejection_reasons.append("can_mutate_queue_must_be_false")
    if report.get("can_clear_blocker") is not False:
        rejection_reasons.append("can_clear_blocker_must_be_false")
    if report.get("can_redefine_window") is not False:
        rejection_reasons.append("can_redefine_window_must_be_false")
    if report.get("can_tune_strategy") is not False:
        rejection_reasons.append("can_tune_strategy_must_be_false")
    recomputed_hash = compute_failure_action_hash(report)
    if _text(report.get("hash")) and _text(report.get("hash")) != recomputed_hash:
        rejection_reasons.append("hash_mismatch")
    return {
        "valid": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "hash": recomputed_hash,
        "schema_version": SCHEMA_VERSION,
    }
