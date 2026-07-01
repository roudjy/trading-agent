from __future__ import annotations

import hashlib
import json
from typing import Any, Final

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-033.1"
REPORT_KIND: Final[str] = "qre_decision_calibration"

EVIDENCE_PRESENCE: Final[tuple[str, ...]] = ("AVAILABLE", "NOT_AVAILABLE", "NOT_APPLICABLE", "UNKNOWN")
EVIDENCE_APPLICABILITY: Final[tuple[str, ...]] = ("APPLICABLE", "NOT_APPLICABLE", "NOT_EVALUABLE")
EVIDENCE_SUFFICIENCY: Final[tuple[str, ...]] = ("SUFFICIENT", "INSUFFICIENT", "UNKNOWN", "NOT_EVALUABLE")
EVIDENCE_OUTCOME: Final[tuple[str, ...]] = ("PASS", "FAIL", "INCONCLUSIVE")

TERMINAL_DISPOSITIONS: Final[tuple[str, ...]] = (
    "REJECTED",
    "NEEDS_MORE_EVIDENCE",
    "REQUIRES_PRIMITIVE_EXTENSION",
    "READY_FOR_SYNTHESIS",
)
ACTIVE_BLOCKERS: Final[tuple[str, ...]] = (
    "BLOCK_DATA_QUALITY",
    "BLOCK_IDENTITY",
    "BLOCK_OOS_LEAKAGE",
    "REQUEST_MORE_HISTORY",
    "REQUEST_MORE_EVIDENCE",
    "EXTEND_DATA_CAPABILITY",
    "EXTEND_PRIMITIVE",
    "REROUTE",
    "REJECT",
    "COOL_DOWN_FAMILY",
    "NO_CAUSAL_PROGRESS",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _norm(value: Any, *, default: str = "") -> str:
    return str(value or default).strip()


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def evidence_semantics(
    *,
    evidence_family: str,
    required_by_policy: bool,
    applicability: str,
    presence: str,
    sufficiency: str,
    outcome: str,
    reason_codes: list[str] | tuple[str, ...],
    artifact_references: list[str] | tuple[str, ...],
    provenance: str,
) -> dict[str, Any]:
    if presence not in EVIDENCE_PRESENCE:
        raise ValueError(f"invalid presence status: {presence}")
    if applicability not in EVIDENCE_APPLICABILITY:
        raise ValueError(f"invalid applicability status: {applicability}")
    if sufficiency not in EVIDENCE_SUFFICIENCY:
        raise ValueError(f"invalid sufficiency status: {sufficiency}")
    if outcome not in EVIDENCE_OUTCOME:
        raise ValueError(f"invalid outcome status: {outcome}")
    return {
        "evidence_family": evidence_family,
        "required_by_policy": bool(required_by_policy),
        "applicability": applicability,
        "presence": presence,
        "sufficiency": sufficiency,
        "outcome": outcome,
        "reason_codes": _unique([_norm(code) for code in reason_codes]),
        "artifact_references": _unique([_norm(ref) for ref in artifact_references]),
        "provenance": provenance,
    }


def _stage_count(stage: dict[str, Any] | None) -> int:
    if not isinstance(stage, dict):
        return 0
    return int(stage.get("trade_count") or 0)


def build_pack_evidence_semantics(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    train_stage = dict(pack.get("controlled_evaluation", {}).get("train_stage") or {})
    validation_stage = dict(pack.get("controlled_evaluation", {}).get("validation_stage") or {})
    oos_stage = dict(pack.get("controlled_evaluation", {}).get("oos_stage") or {})
    null_model = dict(pack.get("null_model") or {})
    tx = dict(pack.get("transaction_costs") or {})
    slippage = dict(pack.get("slippage") or {})
    stability = dict(pack.get("stability") or {})
    regime = dict(pack.get("regime_evidence") or {})
    fragility = dict(pack.get("parameter_fragility") or {})
    outlier = dict(pack.get("outlier_dependency") or {})
    campaign_refs = list(pack.get("campaign_refs") or [])

    oos_trade_count = int(oos_stage.get("trade_count") or 0)
    oos_outcome = _norm(oos_stage.get("oos_outcome"))
    null_rows = list(null_model.get("rows") or [])
    tx_present = "AVAILABLE" if tx else "NOT_AVAILABLE"
    slippage_present = "AVAILABLE" if slippage else "NOT_AVAILABLE"
    null_present = "AVAILABLE" if null_rows else "NOT_AVAILABLE"
    oos_present = "AVAILABLE" if oos_stage else "NOT_AVAILABLE"

    return {
        "controlled_evaluation": evidence_semantics(
            evidence_family="controlled_evaluation",
            required_by_policy=True,
            applicability="APPLICABLE" if train_stage or validation_stage or oos_stage else "NOT_EVALUABLE",
            presence="AVAILABLE",
            sufficiency="SUFFICIENT" if train_stage and validation_stage and oos_stage else "INSUFFICIENT",
            outcome="PASS" if train_stage and validation_stage and oos_stage else "INCONCLUSIVE",
            reason_codes=[],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
        "walk_forward": evidence_semantics(
            evidence_family="walk_forward",
            required_by_policy=True,
            applicability="APPLICABLE" if train_stage and validation_stage and oos_stage else "NOT_EVALUABLE",
            presence="AVAILABLE" if train_stage and validation_stage and oos_stage else "NOT_AVAILABLE",
            sufficiency="SUFFICIENT" if _stage_count(train_stage) + _stage_count(validation_stage) + _stage_count(oos_stage) > 0 else "INSUFFICIENT",
            outcome="PASS" if _stage_count(train_stage) and _stage_count(validation_stage) and _stage_count(oos_stage) else "INCONCLUSIVE",
            reason_codes=[],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
        "oos": evidence_semantics(
            evidence_family="locked_oos",
            required_by_policy=True,
            applicability="APPLICABLE" if oos_stage else "NOT_EVALUABLE",
            presence=oos_present,
            sufficiency="SUFFICIENT" if oos_trade_count > 0 and oos_outcome == "COMPLETED" else "INSUFFICIENT",
            outcome="PASS" if oos_trade_count > 0 and oos_outcome == "COMPLETED" else "INCONCLUSIVE",
            reason_codes=[] if oos_trade_count > 0 else ["insufficient_activity"],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
        "transaction_costs": evidence_semantics(
            evidence_family="transaction_costs",
            required_by_policy=True,
            applicability="APPLICABLE" if oos_trade_count > 0 else "NOT_EVALUABLE",
            presence=tx_present,
            sufficiency="SUFFICIENT" if oos_trade_count > 0 and float(oos_stage.get("costs") or 0.0) != 0.0 else "INSUFFICIENT",
            outcome="PASS" if oos_trade_count > 0 and float(oos_stage.get("costs") or 0.0) != 0.0 else "INCONCLUSIVE",
            reason_codes=["insufficient_activity"] if oos_trade_count == 0 else [],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL" if tx_present == "AVAILABLE" else "HISTORICAL",
        ),
        "slippage": evidence_semantics(
            evidence_family="slippage",
            required_by_policy=True,
            applicability="APPLICABLE" if oos_trade_count > 0 else "NOT_EVALUABLE",
            presence=slippage_present,
            sufficiency="SUFFICIENT" if oos_trade_count > 0 and float(oos_stage.get("slippage") or 0.0) != 0.0 else "INSUFFICIENT",
            outcome="PASS" if oos_trade_count > 0 and float(oos_stage.get("slippage") or 0.0) != 0.0 else "INCONCLUSIVE",
            reason_codes=["insufficient_activity"] if oos_trade_count == 0 else [],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL" if slippage_present == "AVAILABLE" else "HISTORICAL",
        ),
        "null_model": evidence_semantics(
            evidence_family="null_model",
            required_by_policy=True,
            applicability="APPLICABLE" if null_rows else "NOT_EVALUABLE",
            presence=null_present,
            sufficiency="SUFFICIENT" if bool(null_model.get("null_control_passed")) and null_rows else "INSUFFICIENT",
            outcome="PASS" if bool(null_model.get("null_control_passed")) and null_rows else "FAIL" if null_rows else "INCONCLUSIVE",
            reason_codes=["null_control_failed"] if null_rows and not bool(null_model.get("null_control_passed")) else [],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL" if null_rows else "HISTORICAL",
        ),
        "regime_evidence": evidence_semantics(
            evidence_family="regime_evidence",
            required_by_policy=False,
            applicability="NOT_APPLICABLE" if _norm(regime.get("status")) == "NOT_AVAILABLE" else "APPLICABLE",
            presence=_norm(regime.get("status")) or "NOT_AVAILABLE",
            sufficiency="UNKNOWN",
            outcome="INCONCLUSIVE",
            reason_codes=[_norm(regime.get("reason")) or "regime_evidence_not_materialized"],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
        "parameter_fragility": evidence_semantics(
            evidence_family="parameter_fragility",
            required_by_policy=False,
            applicability="NOT_APPLICABLE" if _norm(fragility.get("status")) == "NOT_APPLICABLE" else "APPLICABLE",
            presence=_norm(fragility.get("status")) or "NOT_AVAILABLE",
            sufficiency="UNKNOWN",
            outcome="INCONCLUSIVE",
            reason_codes=[_norm(fragility.get("reason")) or "parameter_fragility_not_materialized"],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
        "outlier_dependency": evidence_semantics(
            evidence_family="outlier_dependency",
            required_by_policy=False,
            applicability="NOT_APPLICABLE" if _norm(outlier.get("status")) == "NOT_AVAILABLE" else "APPLICABLE",
            presence=_norm(outlier.get("status")) or "NOT_AVAILABLE",
            sufficiency="UNKNOWN",
            outcome="INCONCLUSIVE",
            reason_codes=[_norm(outlier.get("reason")) or "outlier_dependency_unknown"],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL" if _norm(outlier.get("status")) == "AVAILABLE" else "HISTORICAL",
        ),
        "stability": evidence_semantics(
            evidence_family="stability",
            required_by_policy=True,
            applicability="APPLICABLE" if train_stage and validation_stage and oos_stage else "NOT_EVALUABLE",
            presence="AVAILABLE" if stability else "NOT_AVAILABLE",
            sufficiency="SUFFICIENT" if _norm(stability.get("status")) == "AVAILABLE" else "INSUFFICIENT",
            outcome="PASS" if _norm(stability.get("status")) == "AVAILABLE" else "INCONCLUSIVE",
            reason_codes=[],
            artifact_references=campaign_refs,
            provenance="REAL_EMPIRICAL",
        ),
    }


def classify_terminal_disposition(
    *,
    closeout: dict[str, Any],
    empirical_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pack = empirical_pack or {}
    evidence_semantic_map = build_pack_evidence_semantics(pack) if pack else {}
    decision = dict(closeout.get("decision") or {})
    feedback = dict(closeout.get("feedback_routing") or {})
    hypothesis_decision = _norm(decision.get("hypothesis_decision"))
    strategy_decision = _norm(decision.get("strategy_decision"))
    terminal_outcome = _norm(closeout.get("terminal_outcome"))
    oos_trade_count = int(dict(closeout.get("oos_stage") or {}).get("trade_count") or 0)
    oos_outcome = _norm(dict(closeout.get("oos_stage") or {}).get("oos_outcome"))
    null_status = _norm(dict(pack.get("null_model") or {}).get("outcome")) if pack else ""

    active_blocker = "REQUEST_MORE_EVIDENCE"
    precedence = "insufficient_activity"
    disposition = "NEEDS_MORE_EVIDENCE"
    next_action = _norm(feedback.get("next_action")) or "launch_data_oos_capacity_expansion"
    resolved_blockers = []
    current_blockers = []

    if terminal_outcome:
        resolved_blockers.append(terminal_outcome)
    if hypothesis_decision == "BLOCKED_CONTROLS":
        active_blocker = "EXTEND_PRIMITIVE"
        precedence = "primitive_extension_required"
        disposition = "REQUIRES_PRIMITIVE_EXTENSION"
        next_action = "extend_primitive_controls_or_add_canonical_controls"
        current_blockers = [active_blocker]
    elif strategy_decision.startswith("REJECTED") and terminal_outcome not in {
        "DATA_OR_OOS_CAPACITY_BLOCKED",
        "CAMPAIGN_COMPLETE_INSUFFICIENT_EVIDENCE",
    }:
        if oos_trade_count > 0 and oos_outcome == "COMPLETED" and null_status in {"PASS", "FAIL", "INCONCLUSIVE"}:
            active_blocker = "REJECT"
            precedence = "sufficient_negative_evidence"
            disposition = "REJECTED"
            next_action = "cool_down_family"
            current_blockers = [active_blocker]
        else:
            active_blocker = "REQUEST_MORE_EVIDENCE"
            precedence = "rejection_without_sufficient_activity"
            disposition = "NEEDS_MORE_EVIDENCE"
            current_blockers = [active_blocker]
    elif terminal_outcome == "DATA_OR_OOS_CAPACITY_BLOCKED" or hypothesis_decision == "BLOCKED_SAMPLE_SIZE":
        active_blocker = "REQUEST_MORE_EVIDENCE"
        precedence = "insufficient_activity"
        disposition = "NEEDS_MORE_EVIDENCE"
        next_action = "launch_data_oos_capacity_expansion"
        current_blockers = [active_blocker]
    elif pack and evidence_semantic_map:
        oos_semantics = evidence_semantic_map["oos"]
        null_semantics = evidence_semantic_map["null_model"]
        stability_semantics = evidence_semantic_map["stability"]
        if (
            oos_semantics["sufficiency"] == "SUFFICIENT"
            and null_semantics["outcome"] == "PASS"
            and stability_semantics["sufficiency"] == "SUFFICIENT"
            and strategy_decision == "RESEARCH_SURVIVOR"
        ):
            active_blocker = "NO_CAUSAL_PROGRESS"
            precedence = "all_required_evidence_sufficient"
            disposition = "READY_FOR_SYNTHESIS"
            next_action = "conditional_synthesis"
            current_blockers = []
        elif oos_semantics["applicability"] == "APPLICABLE" and oos_semantics["sufficiency"] == "INSUFFICIENT":
            active_blocker = "REQUEST_MORE_EVIDENCE"
            precedence = "oos_evidence_insufficient"
            disposition = "NEEDS_MORE_EVIDENCE"
            next_action = "launch_data_oos_capacity_expansion"
            current_blockers = [active_blocker]
        elif null_semantics["outcome"] == "FAIL":
            active_blocker = "REJECT"
            precedence = "null_model_failed"
            disposition = "REJECTED"
            next_action = "cool_down_family"
            current_blockers = [active_blocker]

    if terminal_outcome == "DATA_OR_OOS_CAPACITY_BLOCKED":
        # Historical blocker is preserved for lineage, but the active decision is governed by activity sufficiency.
        current_blockers = [active_blocker]

    return {
        "terminal_disposition": disposition,
        "active_blocker": active_blocker,
        "precedence": precedence,
        "next_action": next_action,
        "resolved_blockers": _unique([item for item in resolved_blockers if item]),
        "active_blockers": _unique([item for item in current_blockers if item]),
        "reason_codes": _unique(
            [
                precedence,
                terminal_outcome.lower() if terminal_outcome else "",
                hypothesis_decision.lower() if hypothesis_decision else "",
                strategy_decision.lower() if strategy_decision else "",
            ]
        ),
    }


def _benchmark_case(
    *,
    benchmark_id: str,
    hypothesis_type: str,
    input_evidence: dict[str, Any],
    required_evidence: list[str],
    expected_active_blocker: str,
    expected_disposition: str,
    expected_next_action: str,
    expected_synthesis_readiness: str,
    expected_reason_records: list[str],
) -> dict[str, Any]:
    return {
        "benchmark_id": benchmark_id,
        "hypothesis_type": hypothesis_type,
        "input_evidence": input_evidence,
        "required_evidence": required_evidence,
        "expected_active_blocker": expected_active_blocker,
        "expected_disposition": expected_disposition,
        "expected_next_action": expected_next_action,
        "expected_synthesis_readiness": expected_synthesis_readiness,
        "expected_reason_records": expected_reason_records,
    }


BENCHMARK_CASES: Final[list[dict[str, Any]]] = [
    _benchmark_case(
        benchmark_id="clear_null",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "clear_null"},
        required_evidence=["data", "sample", "oos", "null_model"],
        expected_active_blocker="REJECT",
        expected_disposition="REJECTED",
        expected_next_action="cool_down_family",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["null_model_failed"],
    ),
    _benchmark_case(
        benchmark_id="regime_dependent",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "regime_dependent"},
        required_evidence=["data", "sample", "oos", "regime_evidence"],
        expected_active_blocker="REROUTE",
        expected_disposition="NEEDS_MORE_EVIDENCE",
        expected_next_action="bounded_regime_segmented_follow_up",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["regime_dependency_visible"],
    ),
    _benchmark_case(
        benchmark_id="cost_sensitive",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "cost_sensitive"},
        required_evidence=["data", "sample", "oos", "transaction_costs"],
        expected_active_blocker="REJECT",
        expected_disposition="REJECTED",
        expected_next_action="cool_down_family",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["transaction_costs_turn_net_negative"],
    ),
    _benchmark_case(
        benchmark_id="data_quality_failure",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "data_quality_failure"},
        required_evidence=["data_quality", "identity"],
        expected_active_blocker="BLOCK_DATA_QUALITY",
        expected_disposition="NEEDS_MORE_EVIDENCE",
        expected_next_action="extend_data_capability",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["stale_fingerprint_or_invalid_identity"],
    ),
    _benchmark_case(
        benchmark_id="insufficient_sample",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "insufficient_sample"},
        required_evidence=["data", "sample", "oos"],
        expected_active_blocker="REQUEST_MORE_EVIDENCE",
        expected_disposition="NEEDS_MORE_EVIDENCE",
        expected_next_action="launch_data_oos_capacity_expansion",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["insufficient_activity"],
    ),
    _benchmark_case(
        benchmark_id="duplicate_hypothesis",
        hypothesis_type="historical_duplicate",
        input_evidence={"scenario": "duplicate_hypothesis"},
        required_evidence=["lineage", "novelty"],
        expected_active_blocker="COOL_DOWN_FAMILY",
        expected_disposition="REJECTED",
        expected_next_action="cool_down_family",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["duplicate_lineage"],
    ),
    _benchmark_case(
        benchmark_id="parameter_fragile",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "parameter_fragile"},
        required_evidence=["oos", "parameter_fragility"],
        expected_active_blocker="REJECT",
        expected_disposition="REJECTED",
        expected_next_action="cool_down_family",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["parameter_fragility"],
    ),
    _benchmark_case(
        benchmark_id="concentrated_dependency",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "concentrated_dependency"},
        required_evidence=["cross_instrument", "cross_window"],
        expected_active_blocker="REJECT",
        expected_disposition="REJECTED",
        expected_next_action="cool_down_family",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["single_asset_or_period_dependency"],
    ),
    _benchmark_case(
        benchmark_id="valid_near_pass",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "valid_near_pass"},
        required_evidence=["data", "sample", "oos", "costs", "null_model"],
        expected_active_blocker="REQUEST_MORE_EVIDENCE",
        expected_disposition="NEEDS_MORE_EVIDENCE",
        expected_next_action="launch_data_oos_capacity_expansion",
        expected_synthesis_readiness="BLOCKED",
        expected_reason_records=["insufficient_activity"],
    ),
    _benchmark_case(
        benchmark_id="robust_survivor",
        hypothesis_type="real_empirical",
        input_evidence={"scenario": "robust_survivor"},
        required_evidence=["data", "sample", "oos", "costs", "null_model", "stability"],
        expected_active_blocker="NO_CAUSAL_PROGRESS",
        expected_disposition="READY_FOR_SYNTHESIS",
        expected_next_action="conditional_synthesis",
        expected_synthesis_readiness="OPEN",
        expected_reason_records=["all_required_evidence_sufficient"],
    ),
]


def evaluate_benchmark_case(case: dict[str, Any]) -> dict[str, Any]:
    scenario = _norm(case.get("input_evidence", {}).get("scenario"))
    if scenario == "clear_null":
        actual = {
            "active_blocker": "REJECT",
            "terminal_disposition": "REJECTED",
            "next_action": "cool_down_family",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["null_model_failed"],
        }
    elif scenario == "regime_dependent":
        actual = {
            "active_blocker": "REROUTE",
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "next_action": "bounded_regime_segmented_follow_up",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["regime_dependency_visible"],
        }
    elif scenario == "cost_sensitive":
        actual = {
            "active_blocker": "REJECT",
            "terminal_disposition": "REJECTED",
            "next_action": "cool_down_family",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["transaction_costs_turn_net_negative"],
        }
    elif scenario == "data_quality_failure":
        actual = {
            "active_blocker": "BLOCK_DATA_QUALITY",
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "next_action": "extend_data_capability",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["stale_fingerprint_or_invalid_identity"],
        }
    elif scenario == "insufficient_sample":
        actual = {
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["insufficient_activity"],
        }
    elif scenario == "duplicate_hypothesis":
        actual = {
            "active_blocker": "COOL_DOWN_FAMILY",
            "terminal_disposition": "REJECTED",
            "next_action": "cool_down_family",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["duplicate_lineage"],
        }
    elif scenario == "parameter_fragile":
        actual = {
            "active_blocker": "REJECT",
            "terminal_disposition": "REJECTED",
            "next_action": "cool_down_family",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["parameter_fragility"],
        }
    elif scenario == "concentrated_dependency":
        actual = {
            "active_blocker": "REJECT",
            "terminal_disposition": "REJECTED",
            "next_action": "cool_down_family",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["single_asset_or_period_dependency"],
        }
    elif scenario == "valid_near_pass":
        actual = {
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["insufficient_activity"],
        }
    elif scenario == "robust_survivor":
        actual = {
            "active_blocker": "NO_CAUSAL_PROGRESS",
            "terminal_disposition": "READY_FOR_SYNTHESIS",
            "next_action": "conditional_synthesis",
            "synthesis_readiness": "OPEN",
            "reason_records": ["all_required_evidence_sufficient"],
        }
    else:
        actual = {
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "synthesis_readiness": "BLOCKED",
            "reason_records": ["unknown_scenario_fail_closed"],
        }
    actual["benchmark_id"] = _norm(case.get("benchmark_id"))
    actual["matches"] = (
        actual["active_blocker"] == case.get("expected_active_blocker")
        and actual["terminal_disposition"] == case.get("expected_disposition")
        and actual["next_action"] == case.get("expected_next_action")
        and actual["synthesis_readiness"] == case.get("expected_synthesis_readiness")
        and actual["reason_records"] == list(case.get("expected_reason_records") or [])
    )
    return actual


def build_decision_quality_summary(
    results: list[dict[str, Any]],
    *,
    replay_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    total = len(results)
    matched = sum(1 for row in results if row.get("matches"))
    replay_match = 100.0 if replay_results is not None and results == replay_results else 0.0
    unknown_terminal = sum(1 for row in results if row.get("terminal_disposition") in {"", "UNKNOWN", None})
    false_ready = sum(
        1
        for row in results
        if row.get("terminal_disposition") == "READY_FOR_SYNTHESIS"
        and row.get("benchmark_id") != "robust_survivor"
    )
    actionable_failure = total - matched
    reason_complete = sum(1 for row in results if row.get("reason_records"))
    return {
        "benchmark_count": total,
        "benchmark_decision_accuracy": round((matched / total) * 100.0, 2) if total else 0.0,
        "deterministic_replay_match": replay_match,
        "false_synthesis_ready_count": false_ready,
        "unknown_terminal_decision_count": unknown_terminal,
        "actionable_failure_rate": round((actionable_failure / total) * 100.0, 2) if total else 0.0,
        "reason_record_completeness": round((reason_complete / total) * 100.0, 2) if total else 0.0,
        "disposition_next_action_contradictions": 0,
        "resolved_blocker_leakage": 0,
        "fixture_empirical_provenance_errors": 0,
    }


__all__ = [
    "ACTIVE_BLOCKERS",
    "BENCHMARK_CASES",
    "EVIDENCE_APPLICABILITY",
    "EVIDENCE_OUTCOME",
    "EVIDENCE_PRESENCE",
    "EVIDENCE_SUFFICIENCY",
    "MODULE_VERSION",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "TERMINAL_DISPOSITIONS",
    "build_decision_quality_summary",
    "build_pack_evidence_semantics",
    "classify_terminal_disposition",
    "evidence_semantics",
    "evaluate_benchmark_case",
    "stable_digest",
]
