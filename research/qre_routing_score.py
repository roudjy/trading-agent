"""Context-only QRE routing score scaffold.

This module ranks potential research next-actions from non-authoritative
context. It does not execute campaigns, synthesize strategies, clear
evidence blockers, or promote candidates.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterable, Literal, Mapping

from research.qre_behavior_catalog import get_behavior_family
from research.qre_hypothesis_model import validate_hypothesis
from research.qre_preset_feasibility_mapper import validate_feasibility_result


RoutingStatus = Literal[
    "routable_context_only",
    "provisional",
    "blocked_missing_feasibility",
    "blocked_unknown_behavior",
    "blocked_missing_hypothesis",
    "blocked_missing_required_context",
    "blocked_not_evidence_authoritative",
]

ROUTING_SCORE_SCHEMA_VERSION: Final[str] = "1.0"
NON_AUTHORITATIVE_FLAG: Final[bool] = True
EVIDENCE_AUTHORITY: Final[str] = "context_only"
CAN_AUTHORIZE_EXECUTION: Final[bool] = False
CAN_CLEAR_EVIDENCE_BLOCKERS: Final[bool] = False
CAN_PROMOTE_CANDIDATE: Final[bool] = False
VALID_ROUTING_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "routable_context_only",
        "provisional",
        "blocked_missing_feasibility",
        "blocked_unknown_behavior",
        "blocked_missing_hypothesis",
        "blocked_missing_required_context",
        "blocked_not_evidence_authoritative",
    }
)
SCORE_COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "evidence_gap_reduction_score",
    "source_cache_readiness_score",
    "blocker_severity_score",
    "information_gain_proxy_score",
    "prior_failure_penalty",
    "compute_cost_penalty",
    "behavior_diversity_score",
    "feasibility_score",
)
REQUIRED_CONTEXT_FIELDS: Final[tuple[str, ...]] = (
    "evidence_gap_information",
    "blocker_severity",
    "source_cache_readiness",
    "expected_information_gain_proxy",
    "compute_budget_proxy",
    "behavior_diversity_proxy",
)


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _bounded_float(value: Any, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return round(number, 6)


def _canonicalize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": result.get("schema_version", ROUTING_SCORE_SCHEMA_VERSION),
        "behavior_id": result.get("behavior_id"),
        "hypothesis_id": result.get("hypothesis_id"),
        "routing_status": result.get("routing_status"),
        "routing_score": result.get("routing_score"),
        "score_components": dict(result.get("score_components", {})),
        "recommended_next_action": result.get("recommended_next_action"),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "non_authoritative": bool(result.get("non_authoritative", NON_AUTHORITATIVE_FLAG)),
        "evidence_authority": result.get("evidence_authority", EVIDENCE_AUTHORITY),
        "can_authorize_execution": bool(
            result.get("can_authorize_execution", CAN_AUTHORIZE_EXECUTION)
        ),
        "can_clear_evidence_blockers": bool(
            result.get("can_clear_evidence_blockers", CAN_CLEAR_EVIDENCE_BLOCKERS)
        ),
        "can_promote_candidate": bool(result.get("can_promote_candidate", CAN_PROMOTE_CANDIDATE)),
    }


def compute_routing_hash(payload: Mapping[str, Any]) -> str:
    canonical = _canonicalize_result(payload)
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def _base_result(
    *,
    behavior_id: str,
    hypothesis_id: str | None,
    routing_status: RoutingStatus,
    recommended_next_action: str,
    blocked_reasons: Iterable[str] = (),
    score_components: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    components = {
        component_name: round(float((score_components or {}).get(component_name, 0.0)), 6)
        for component_name in SCORE_COMPONENT_NAMES
    }
    positive_score = (
        components["evidence_gap_reduction_score"]
        + components["source_cache_readiness_score"]
        + components["blocker_severity_score"]
        + components["information_gain_proxy_score"]
        + components["behavior_diversity_score"]
        + components["feasibility_score"]
    )
    penalty = components["prior_failure_penalty"] + components["compute_cost_penalty"]
    routing_score = round(max(0.0, min(1.0, (positive_score / 6.0) - (penalty / 2.0))), 6)
    if routing_status.startswith("blocked_"):
        routing_score = 0.0

    result = {
        "schema_version": ROUTING_SCORE_SCHEMA_VERSION,
        "behavior_id": behavior_id,
        "hypothesis_id": hypothesis_id,
        "routing_status": routing_status,
        "routing_score": routing_score,
        "score_components": components,
        "recommended_next_action": recommended_next_action,
        "blocked_reasons": list(_unique_in_order(blocked_reasons)),
        "non_authoritative": NON_AUTHORITATIVE_FLAG,
        "evidence_authority": EVIDENCE_AUTHORITY,
        "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
        "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
        "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
    }
    result["hash"] = compute_routing_hash(result)
    return result


def _missing_required_context(context: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        f"missing_required_context:{field_name}"
        for field_name in REQUIRED_CONTEXT_FIELDS
        if field_name not in context or context[field_name] is None
    )


def _feasibility_score(feasibility_result: Mapping[str, Any]) -> float:
    feasible_count = len(list(feasibility_result.get("feasible_mappings") or []))
    blocked_count = len(list(feasibility_result.get("blocked_mappings") or []))
    total = feasible_count + blocked_count
    if total == 0:
        return 0.0
    return round(feasible_count / total, 6)


def _score_components(
    *,
    feasibility_result: Mapping[str, Any],
    evidence_gap_information: Mapping[str, Any],
    blocker_severity: Mapping[str, Any],
    source_cache_readiness: Mapping[str, Any],
    prior_failure_density: Any,
    expected_information_gain_proxy: Any,
    compute_budget_proxy: Any,
    behavior_diversity_proxy: Any,
) -> dict[str, float]:
    missing_gap_count = float(evidence_gap_information.get("missing_evidence_count", 0) or 0)
    visible_gap_count = float(evidence_gap_information.get("visible_gap_count", 0) or 0)
    total_gap_count = max(1.0, missing_gap_count + visible_gap_count)
    evidence_gap_reduction_score = min(1.0, missing_gap_count / total_gap_count)

    ready_fraction = source_cache_readiness.get("ready_fraction")
    if ready_fraction is None:
        ready = float(source_cache_readiness.get("ready_count", 0) or 0)
        total = max(1.0, ready + float(source_cache_readiness.get("blocked_count", 0) or 0))
        ready_fraction = ready / total

    severity_score = blocker_severity.get("severity_score")
    if severity_score is None:
        severity_score = {
            "low": 0.25,
            "medium": 0.5,
            "high": 0.75,
            "critical": 1.0,
        }.get(str(blocker_severity.get("max_severity") or "").lower(), 0.0)

    return {
        "evidence_gap_reduction_score": _bounded_float(evidence_gap_reduction_score),
        "source_cache_readiness_score": _bounded_float(ready_fraction),
        "blocker_severity_score": _bounded_float(severity_score),
        "information_gain_proxy_score": _bounded_float(expected_information_gain_proxy),
        "prior_failure_penalty": _bounded_float(prior_failure_density),
        "compute_cost_penalty": _bounded_float(compute_budget_proxy),
        "behavior_diversity_score": _bounded_float(behavior_diversity_proxy),
        "feasibility_score": _bounded_float(_feasibility_score(feasibility_result)),
    }


def evaluate_routing_score(
    *,
    behavior_id: str,
    hypothesis: Mapping[str, Any] | None = None,
    hypothesis_ref: str | None = None,
    preset_feasibility_result: Mapping[str, Any] | None = None,
    evidence_gap_information: Mapping[str, Any] | None = None,
    blocker_severity: Mapping[str, Any] | None = None,
    source_cache_readiness: Mapping[str, Any] | None = None,
    prior_failure_density: Any = 0.0,
    expected_information_gain_proxy: Any = None,
    compute_budget_proxy: Any = None,
    behavior_diversity_proxy: Any = None,
    provisional_evidence_visibility_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_behavior_id = str(behavior_id or "").strip()
    hypothesis_id = str((hypothesis or {}).get("hypothesis_id") or hypothesis_ref or "").strip() or None

    try:
        behavior = get_behavior_family(normalized_behavior_id)
    except KeyError:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=hypothesis_id,
            routing_status="blocked_unknown_behavior",
            recommended_next_action="keep_fail_closed",
            blocked_reasons=("unknown_behavior_id",),
        )

    if hypothesis is None and not hypothesis_ref:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=None,
            routing_status="blocked_missing_hypothesis",
            recommended_next_action="route_to_operator_review",
            blocked_reasons=("missing_hypothesis_or_ref",),
        )

    if hypothesis is not None:
        validation = validate_hypothesis(hypothesis)
        if not validation.valid:
            return _base_result(
                behavior_id=normalized_behavior_id,
                hypothesis_id=hypothesis_id,
                routing_status="blocked_missing_hypothesis",
                recommended_next_action="route_to_operator_review",
                blocked_reasons=validation.rejection_reasons,
            )

    if preset_feasibility_result is None:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=hypothesis_id,
            routing_status="blocked_missing_feasibility",
            recommended_next_action="evaluate_preset_feasibility",
            blocked_reasons=("missing_preset_feasibility_result",),
        )

    feasibility_validation = validate_feasibility_result(preset_feasibility_result)
    if not feasibility_validation["valid"]:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=hypothesis_id,
            routing_status="blocked_missing_feasibility",
            recommended_next_action="evaluate_preset_feasibility",
            blocked_reasons=feasibility_validation["rejection_reasons"],
        )

    if preset_feasibility_result.get("evidence_authority") != EVIDENCE_AUTHORITY:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=hypothesis_id,
            routing_status="blocked_not_evidence_authoritative",
            recommended_next_action="keep_fail_closed",
            blocked_reasons=("routing_requires_context_only_feasibility",),
        )

    required_context = {
        "evidence_gap_information": evidence_gap_information,
        "blocker_severity": blocker_severity,
        "source_cache_readiness": source_cache_readiness,
        "expected_information_gain_proxy": expected_information_gain_proxy,
        "compute_budget_proxy": compute_budget_proxy,
        "behavior_diversity_proxy": behavior_diversity_proxy,
    }
    missing_context = _missing_required_context(required_context)
    if missing_context:
        return _base_result(
            behavior_id=normalized_behavior_id,
            hypothesis_id=hypothesis_id,
            routing_status="blocked_missing_required_context",
            recommended_next_action="collect_required_context",
            blocked_reasons=missing_context,
        )

    blocked_reasons: list[str] = []
    if provisional_evidence_visibility_context:
        if provisional_evidence_visibility_context.get("provisional_artifacts_visible"):
            blocked_reasons.append("provisional_artifacts_visible_context_only")

    components = _score_components(
        feasibility_result=preset_feasibility_result,
        evidence_gap_information=evidence_gap_information or {},
        blocker_severity=blocker_severity or {},
        source_cache_readiness=source_cache_readiness or {},
        prior_failure_density=prior_failure_density,
        expected_information_gain_proxy=expected_information_gain_proxy,
        compute_budget_proxy=compute_budget_proxy,
        behavior_diversity_proxy=behavior_diversity_proxy,
    )
    status: RoutingStatus = "routable_context_only"
    if behavior.status != "active" or blocked_reasons:
        status = "provisional"
    if not preset_feasibility_result.get("feasible_mappings"):
        status = "blocked_missing_feasibility"
        blocked_reasons.extend(
            str(reason) for reason in preset_feasibility_result.get("blocker_reasons", ())
        )

    return _base_result(
        behavior_id=normalized_behavior_id,
        hypothesis_id=hypothesis_id,
        routing_status=status,
        recommended_next_action="build_sampling_plan_context_only"
        if status in {"routable_context_only", "provisional"}
        else "evaluate_preset_feasibility",
        blocked_reasons=blocked_reasons,
        score_components=components,
    )


def validate_routing_result(result: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    canonical = _canonicalize_result(result)

    for field_name in (
        "behavior_id",
        "routing_status",
        "routing_score",
        "score_components",
        "recommended_next_action",
        "blocked_reasons",
        "non_authoritative",
        "evidence_authority",
        "can_authorize_execution",
        "can_clear_evidence_blockers",
        "can_promote_candidate",
    ):
        if field_name not in canonical:
            rejection_reasons.append(f"missing_field:{field_name}")

    if canonical["routing_status"] not in VALID_ROUTING_STATUSES:
        rejection_reasons.append(f"invalid_routing_status:{canonical['routing_status']}")

    for component_name in SCORE_COMPONENT_NAMES:
        if component_name not in canonical["score_components"]:
            rejection_reasons.append(f"missing_score_component:{component_name}")

    if canonical["non_authoritative"] is not True:
        rejection_reasons.append("non_authoritative_must_be_true")

    if canonical["evidence_authority"] != EVIDENCE_AUTHORITY:
        rejection_reasons.append("invalid_evidence_authority")

    if canonical["can_authorize_execution"] is not False:
        rejection_reasons.append("can_authorize_execution_must_be_false")

    if canonical["can_clear_evidence_blockers"] is not False:
        rejection_reasons.append("can_clear_evidence_blockers_must_be_false")

    if canonical["can_promote_candidate"] is not False:
        rejection_reasons.append("can_promote_candidate_must_be_false")

    computed_hash = compute_routing_hash(result)
    if str(result.get("hash") or "") and str(result.get("hash")) != computed_hash:
        rejection_reasons.append("hash_mismatch")

    return {
        "valid": not rejection_reasons,
        "rejection_reasons": list(_unique_in_order(rejection_reasons)),
        "hash": computed_hash,
        "schema_version": ROUTING_SCORE_SCHEMA_VERSION,
    }
