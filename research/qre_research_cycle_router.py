from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_research.research_memory import retrieve
from research.qre_behavior_catalog import list_behavior_families
from research.qre_failure_to_action_mapper import map_failure_to_action
from research.qre_hypothesis_disposition_memory import evaluate_revisit_eligibility
from research.qre_preset_feasibility_mapper import evaluate_preset_feasibility_for_hypothesis
from research.qre_routing_score import evaluate_routing_score


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_cycle_router"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_cycle_router")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_research_cycle_router/"
DEFAULT_DISPOSITION_MEMORY_PATH: Final[Path] = Path("logs/qre_hypothesis_disposition_memory/latest.json")
DEFAULT_RESEARCH_MEMORY_PATH: Final[Path] = Path("logs/qre_research_memory/latest.json")
TIMEFRAME_ALIASES: Final[dict[str, str]] = {
    "daily_v1": "1d",
    "daily": "1d",
    "weekly_v1": "1w",
    "weekly": "1w",
    "hourly_v1": "1h",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _scope_signature(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": _text(scope.get("hypothesis_id")),
        "behavior_id": _text(scope.get("behavior_id")),
        "preset_id": _text(scope.get("preset_id")),
        "timeframe": _text(scope.get("timeframe")),
        "universe_or_basket_scope": _text(scope.get("universe_or_basket_scope")),
        "region": _text(scope.get("region")),
    }


def _preset_family(preset_id: str) -> str:
    parts = [part for part in _text(preset_id).split("_") if part]
    if not parts:
        return ""
    if len(parts) >= 3 and parts[-2].lower() in {"daily", "weekly", "monthly"} and parts[-1].lower().startswith("v"):
        return "_".join(parts[:-2])
    if len(parts) >= 2 and parts[-1].lower().startswith("v"):
        return "_".join(parts[:-1])
    return "_".join(parts)


def _normalize_timeframe(value: Any) -> str:
    text = _text(value)
    return TIMEFRAME_ALIASES.get(text, text)


def _default_hypothesis(
    *,
    source_record: Mapping[str, Any],
    target_behavior_id: str,
    title_suffix: str,
    universe_ref: str,
    universe_description: str,
    timeframe: str,
) -> dict[str, Any]:
    behavior = next(
        behavior for behavior in list_behavior_families() if behavior.behavior_id == target_behavior_id
    )
    source_hypothesis_id = _text(source_record.get("hypothesis_id")) or "rejected_hypothesis"
    return {
        "hypothesis_id": f"{source_hypothesis_id}__{target_behavior_id}__{title_suffix}",
        "behavior_id": target_behavior_id,
        "title": f"{behavior.display_name} follow-up for rejected scope",
        "description": behavior.description,
        "universe_ref": universe_ref,
        "universe_description": universe_description,
        "preset_id": None,
        "timeframe": timeframe,
        "expected_mechanism": behavior.description,
        "expected_observables": list(behavior.expected_observables),
        "falsification_criteria": list(behavior.common_failure_modes),
        "required_evidence_types": list(behavior.evidence_requirements),
        "required_data_capabilities": list(behavior.required_data_capabilities),
        "known_risks": list(behavior.common_failure_modes),
        "status": "research_ready",
        "created_at_utc": _text(source_record.get("disposition_timestamp")),
        "source": "qre_research_cycle_router_context_only",
        "reason_record_refs": list(source_record.get("reason_record_refs") or []),
        "symbols": [],
    }


def _research_memory_context(research_memory: Mapping[str, Any] | None, query: str) -> dict[str, Any]:
    if not isinstance(research_memory, Mapping):
        return {
            "status": "missing_research_memory",
            "retrieval_query": query,
            "retrieval_matches": [],
            "retrieval_match_count": 0,
        }
    return {
        "status": _text((research_memory.get("summary") or {}).get("status")) or "unknown",
        "retrieval_query": query,
        "retrieval_matches": retrieve(research_memory, query, limit=5),
        "retrieval_match_count": len(retrieve(research_memory, query, limit=5)),
    }


def _routing_context(
    *,
    target_behavior_id: str,
    source_behavior_id: str,
    research_memory_ready: bool,
    accepted_lineage_count: int,
    accepted_oos_count: int,
    prior_failure_penalty: float,
    information_gain_proxy: float,
    compute_budget_proxy: float,
) -> dict[str, Any]:
    return {
        "evidence_gap_information": {
            "missing_evidence_count": max(1, accepted_lineage_count + 1 - accepted_oos_count),
            "visible_gap_count": max(1, accepted_lineage_count),
        },
        "blocker_severity": {"max_severity": "high"},
        "source_cache_readiness": {
            "ready_count": 1 if research_memory_ready else 0,
            "blocked_count": 0 if research_memory_ready else 1,
        },
        "prior_failure_density": prior_failure_penalty,
        "expected_information_gain_proxy": information_gain_proxy,
        "compute_budget_proxy": compute_budget_proxy,
        "behavior_diversity_proxy": 1.0 if target_behavior_id != source_behavior_id else 0.3,
        "provisional_evidence_visibility_context": {
            "provisional_artifacts_visible": False,
        },
    }


def _direction_result(
    *,
    direction_id: str,
    direction_type: str,
    label: str,
    route_status: str,
    rationale: str,
    proposed_scope: Mapping[str, Any],
    novelty_requirements: Sequence[str],
    evidence_requirements: Sequence[str],
    eligibility_reasons: Sequence[str],
    feasibility: Mapping[str, Any] | None = None,
    routing: Mapping[str, Any] | None = None,
    target_hypothesis: Mapping[str, Any] | None = None,
    authority_flags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "direction_id": direction_id,
        "direction_type": direction_type,
        "label": label,
        "route_status": route_status,
        "rationale": rationale,
        "proposed_scope": dict(proposed_scope),
        "novelty_requirements": list(_unique_in_order(novelty_requirements)),
        "evidence_requirements": list(_unique_in_order(evidence_requirements)),
        "eligibility_reasons": list(_unique_in_order(eligibility_reasons)),
        "target_hypothesis": dict(target_hypothesis or {}),
        "preset_feasibility": dict(feasibility or {}),
        "routing_context_only": dict(routing or {}),
        "authority_flags": {
            "non_authoritative": True,
            "operator_review_required": True,
            "can_execute": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            **dict(authority_flags or {}),
        },
    }


def _suppressed_scopes(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    disposition_scope = record.get("disposition_scope") if isinstance(record.get("disposition_scope"), Mapping) else {}
    signature = _scope_signature(disposition_scope)
    return [
        {
            "scope_kind": "exact_failed_scope",
            "scope_signature": signature,
            "suppression_reason": "same_failed_scope_suppressed",
        },
        {
            "scope_kind": "materially_equivalent_retry",
            "scope_signature": signature,
            "suppression_reason": "insufficient_scope_novelty",
            "requires_material_change": list(record.get("retry_policy", {}).get("material_change_keys") or []),
        },
    ]


def build_research_cycle_router(
    *,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    disposition_memory_path: Path = DEFAULT_DISPOSITION_MEMORY_PATH,
    research_memory_path: Path = DEFAULT_RESEARCH_MEMORY_PATH,
) -> dict[str, Any]:
    disposition_memory = _read_json(repo_root / disposition_memory_path)
    research_memory = _read_json(repo_root / research_memory_path)
    if not isinstance(disposition_memory, Mapping):
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": generated_at_utc or "",
            "status": "blocked_missing_disposition_memory",
            "summary": {
                "router_ready": False,
                "eligible_direction_count": 0,
                "ineligible_direction_count": 0,
                "suppressed_scope_count": 0,
                "recommended_research_action": "route_to_operator_review",
            },
            "safety_invariants": {
                "read_only": True,
                "uses_network": False,
                "uses_subprocess": False,
                "can_execute_research_cycle": False,
                "can_register_strategy": False,
                "can_promote_candidate": False,
                "paper_shadow_live_forbidden": True,
                "broker_risk_execution_forbidden": True,
            },
        }

    record = disposition_memory.get("record") if isinstance(disposition_memory.get("record"), Mapping) else {}
    disposition_scope = record.get("disposition_scope") if isinstance(record.get("disposition_scope"), Mapping) else {}
    source_behavior_id = _text(record.get("behavior_id"))
    source_preset_id = _text(record.get("preset_id"))
    source_timeframe = _text(record.get("timeframe"))
    source_timeframe_normalized = _normalize_timeframe(source_timeframe)
    source_universe = _text(record.get("universe_or_basket_scope"))
    source_region = _text(disposition_scope.get("region")) or "unjustified_region"
    source_hypothesis_id = _text(record.get("hypothesis_id"))
    generated = generated_at_utc or _text(disposition_memory.get("generated_at_utc")) or _text(record.get("disposition_timestamp"))
    source_disposition_ref = f"{disposition_memory_path.as_posix()}#record::{_text(record.get('memory_record_id')) or 'unknown'}"
    failure_classes = _unique_in_order(record.get("failure_classes") or [])
    failure_actions = [
        map_failure_to_action(failure_class=failure_class)
        for failure_class in failure_classes
    ]
    accepted_lineage_count = len(record.get("accepted_lineage_refs") or [])
    accepted_oos_count = len(record.get("accepted_oos_refs") or [])
    research_query = " ".join([source_hypothesis_id, *failure_classes]).strip()
    research_context = _research_memory_context(research_memory, research_query)
    research_memory_ready = research_context["status"] == "ready"

    directions: list[dict[str, Any]] = []
    disposition_payload = {"record": record}

    for behavior in list_behavior_families():
        if behavior.behavior_id == source_behavior_id:
            continue
        proposed_scope = {
            **dict(disposition_scope),
            "behavior_id": behavior.behavior_id,
            "behavior_family": behavior.behavior_id,
            "preset_family": "",
            "operator_approved_new_research_rationale": f"rotate_to_{behavior.behavior_id}",
            "new_research_rationale": f"rotate_to_{behavior.behavior_id}",
        }
        novelty = evaluate_revisit_eligibility(disposition_payload, proposed_scope=proposed_scope)
        target_hypothesis = _default_hypothesis(
            source_record=record,
            target_behavior_id=behavior.behavior_id,
            title_suffix="behavior_rotation",
            universe_ref=source_universe,
            universe_description=source_universe,
            timeframe=source_timeframe_normalized,
        )
        feasibility = evaluate_preset_feasibility_for_hypothesis(target_hypothesis)
        routing = evaluate_routing_score(
            behavior_id=behavior.behavior_id,
            hypothesis=target_hypothesis,
            preset_feasibility_result=feasibility,
            **_routing_context(
                target_behavior_id=behavior.behavior_id,
                source_behavior_id=source_behavior_id,
                research_memory_ready=research_memory_ready,
                accepted_lineage_count=accepted_lineage_count,
                accepted_oos_count=accepted_oos_count,
                prior_failure_penalty=0.15 if behavior.status == "active" else 0.35,
                information_gain_proxy=0.9 if behavior.status == "active" else 0.6,
                compute_budget_proxy=0.35,
            ),
        )
        route_status = "eligible_context_only"
        reasons = ["materially_new_behavior_direction", novelty["reason"], f"behavior_status:{behavior.status}"]
        if not novelty["eligible"]:
            route_status = "ineligible_missing_novelty"
        elif not feasibility.get("feasible_mappings"):
            route_status = "ineligible_missing_preset_feasibility"
            reasons.extend(feasibility.get("blocker_reasons", []))
        elif routing.get("routing_status") not in {"routable_context_only", "provisional"}:
            route_status = "ineligible_missing_routing_context"
            reasons.extend(routing.get("blocked_reasons", []))
        directions.append(
            _direction_result(
                direction_id=f"behavior_rotation::{behavior.behavior_id}",
                direction_type="different_behavior_family",
                label=f"Rotate to {behavior.display_name}",
                route_status=route_status,
                rationale=behavior.description,
                proposed_scope=proposed_scope,
                novelty_requirements=record.get("revisit_requirements") or [],
                evidence_requirements=list(behavior.evidence_requirements),
                eligibility_reasons=reasons,
                feasibility=feasibility,
                routing=routing,
                target_hypothesis=target_hypothesis,
            )
        )

    same_behavior_same_timeframe = _default_hypothesis(
        source_record=record,
        target_behavior_id=source_behavior_id,
        title_suffix="timeframe_shift",
        universe_ref=source_universe,
        universe_description=source_universe,
        timeframe="4h" if source_timeframe_normalized != "4h" else "1w",
    )
    timeframe_scope = {
        **dict(disposition_scope),
        "timeframe": _text(same_behavior_same_timeframe.get("timeframe")),
        "operator_approved_new_research_rationale": "new_timeframe_rationale_required",
        "new_research_rationale": "new_timeframe_rationale_required",
    }
    timeframe_novelty = evaluate_revisit_eligibility(disposition_payload, proposed_scope=timeframe_scope)
    timeframe_feasibility = evaluate_preset_feasibility_for_hypothesis(same_behavior_same_timeframe)
    directions.append(
        _direction_result(
            direction_id="timeframe_shift",
            direction_type="different_justified_timeframe",
            label="Change timeframe with new rationale",
            route_status=(
                "eligible_context_only"
                if timeframe_novelty["eligible"] and timeframe_feasibility.get("feasible_mappings")
                else "ineligible_missing_timeframe_feasibility"
            ),
            rationale="A timeframe change is only safe when it is preregistered and structurally feasible.",
            proposed_scope=timeframe_scope,
            novelty_requirements=[
                "new justified timeframe",
                "new preregistered regime rationale",
                "operator-approved research rationale",
            ],
            evidence_requirements=["screening_evidence", "oos_evidence", "lineage_evidence"],
            eligibility_reasons=[
                timeframe_novelty["reason"],
                *list(timeframe_feasibility.get("blocker_reasons", [])),
            ],
            feasibility=timeframe_feasibility,
            target_hypothesis=same_behavior_same_timeframe,
        )
    )

    universe_scope = {
        **dict(disposition_scope),
        "universe_or_basket_scope": "new_justified_universe_required",
        "region": "new_justified_region_required",
        "operator_approved_new_research_rationale": "new_universe_or_region_rationale_required",
        "new_research_rationale": "new_universe_or_region_rationale_required",
    }
    universe_novelty = evaluate_revisit_eligibility(disposition_payload, proposed_scope=universe_scope)
    directions.append(
        _direction_result(
            direction_id="universe_or_region_shift",
            direction_type="different_justified_universe_or_region",
            label="Expand to a different justified universe or region",
            route_status="eligible_context_only" if universe_novelty["eligible"] else "ineligible_missing_novelty",
            rationale="Breadth expansion is only allowed when the universe or region rationale is materially new.",
            proposed_scope=universe_scope,
            novelty_requirements=[
                "materially different universe or basket scope",
                "new region rationale",
                "operator-approved research rationale",
            ],
            evidence_requirements=[
                "source_identity_for_new_universe",
                "screening_evidence",
                "oos_evidence",
                "lineage_evidence",
            ],
            eligibility_reasons=[universe_novelty["reason"], "requires_new_universe_contract_context"],
        )
    )

    preset_scope = {
        **dict(disposition_scope),
        "preset_family": "new_preset_family_required",
        "preset_id": "new_preset_family_required",
        "operator_approved_new_research_rationale": "new_preset_family_rationale_required",
        "new_research_rationale": "new_preset_family_rationale_required",
    }
    preset_novelty = evaluate_revisit_eligibility(disposition_payload, proposed_scope=preset_scope)
    directions.append(
        _direction_result(
            direction_id="preset_family_shift",
            direction_type="different_preset_family",
            label="Use a materially different preset family",
            route_status="eligible_context_only" if preset_novelty["eligible"] else "ineligible_missing_novelty",
            rationale="A preset-family change is eligible only when it is structurally different from the rejected setup.",
            proposed_scope=preset_scope,
            novelty_requirements=[
                "materially different preset family",
                "new hypothesis rationale",
                "operator-approved research rationale",
            ],
            evidence_requirements=["preset_feasibility_mapping", "screening_evidence", "oos_evidence"],
            eligibility_reasons=[preset_novelty["reason"], f"rejected_preset_family:{_preset_family(source_preset_id)}"],
        )
    )

    directions.append(
        _direction_result(
            direction_id="null_control_investigation",
            direction_type="null_control_investigation",
            label="Plan preregistered null-control investigation",
            route_status="eligible_context_only" if accepted_lineage_count > 0 else "ineligible_missing_lineage",
            rationale="Null controls can test whether the rejected scope failed because the behavior has no edge versus a control.",
            proposed_scope={
                "hypothesis_id": source_hypothesis_id,
                "behavior_id": source_behavior_id,
                "control_family": "preregistered_null_controls_required",
            },
            novelty_requirements=["controls locked before evaluation", "operator-reviewed follow-up scope"],
            evidence_requirements=["accepted_lineage_present", "null_control_contract", "sampling_plan_contract"],
            eligibility_reasons=[
                "accepted_lineage_present" if accepted_lineage_count > 0 else "accepted_lineage_missing",
                "null_control_execution_not_automatic",
            ],
        )
    )

    directions.append(
        _direction_result(
            direction_id="evidence_breadth_expansion",
            direction_type="data_or_evidence_breadth_expansion",
            label="Plan breadth expansion across baskets, windows, regions, and regimes",
            route_status="eligible_context_only",
            rationale="The rejected exact scope does not forbid broader evidence planning when the next scope is justified and preregistered.",
            proposed_scope={
                "source_hypothesis_id": source_hypothesis_id,
                "breadth_dimensions": [
                    "symbols",
                    "baskets",
                    "regions",
                    "timeframes",
                    "regimes",
                    "independent_windows",
                ],
            },
            novelty_requirements=[
                "materially new scope dimensions",
                "new sampling-plan contract",
                "new universe or region rationale where changed",
            ],
            evidence_requirements=[
                "coverage_matrix",
                "accepted_lineage_tracking",
                "independent_oos_window_tracking",
                "reproducibility_tracking",
            ],
            eligibility_reasons=["breadth_is_planning_only", "profitability_not_used_for_priority"],
        )
    )

    directions.append(
        _direction_result(
            direction_id="hypothesis_retirement",
            direction_type="hypothesis_retirement",
            label="Retire the rejected exact hypothesis scope",
            route_status="eligible_context_only",
            rationale="Retirement is an eligible fail-closed outcome when all preregistered windows are exhausted and accepted OOS remains absent.",
            proposed_scope={"hypothesis_id": source_hypothesis_id, "disposition": "retired_exact_scope_only"},
            novelty_requirements=["retirement applies only to the rejected exact scope"],
            evidence_requirements=["reason_record_preserved", "disposition_memory_preserved"],
            eligibility_reasons=[
                *(action.get("recommended_action") for action in failure_actions if action.get("recommended_action")),
                "accepted_oos_count_zero",
            ],
        )
    )

    eligible_directions = [row for row in directions if row["route_status"] == "eligible_context_only"]
    ineligible_directions = [row for row in directions if row["route_status"] != "eligible_context_only"]
    eligible_directions.sort(
        key=lambda row: (
            -float((row.get("routing_context_only") or {}).get("routing_score", 0.0)),
            str(row["direction_id"]),
        )
    )
    ineligible_directions.sort(key=lambda row: str(row["direction_id"]))

    recommended = eligible_directions[0]["direction_id"] if eligible_directions else "route_to_operator_review"
    if "hypothesis_retirement" in recommended:
        recommended_action = "retire_rejected_exact_scope"
    elif recommended.startswith("behavior_rotation::"):
        recommended_action = "propose_materially_new_behavior_family"
    elif recommended == "evidence_breadth_expansion":
        recommended_action = "plan_evidence_breadth_expansion"
    else:
        recommended_action = "route_to_operator_review"

    summary = {
        "router_ready": True,
        "eligible_direction_count": len(eligible_directions),
        "ineligible_direction_count": len(ineligible_directions),
        "suppressed_scope_count": len(_suppressed_scopes(record)),
        "recommended_research_action": recommended_action,
        "operator_summary": (
            "The rejected exact scope remains suppressed. Only materially novel, read-only next-cycle "
            "directions are eligible for operator review."
        ),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "status": "ready",
        "research_cycle_id": "qrc_" + _digest(
            {
                "generated_at_utc": generated,
                "source_disposition_ref": source_disposition_ref,
                "recommended_research_action": recommended_action,
            }
        ).split(":", 1)[1][:16],
        "source_disposition_ref": source_disposition_ref,
        "summary": summary,
        "suppressed_scopes": _suppressed_scopes(record),
        "eligible_directions": eligible_directions,
        "ineligible_directions": ineligible_directions,
        "novelty_requirements": list(record.get("revisit_requirements") or []),
        "evidence_requirements": _unique_in_order(
            [
                "screening_evidence",
                "oos_evidence",
                "lineage_evidence",
                *[
                    requirement
                    for direction in directions
                    for requirement in direction.get("evidence_requirements", [])
                ],
            ]
        ),
        "recommended_research_action": recommended_action,
        "operator_review_required": True,
        "authority_flags": {
            "non_authoritative": True,
            "safe_to_execute": False,
            "can_execute_research_cycle": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "failure_action_context": failure_actions,
        "research_memory_context": research_context,
        "source_scope": _scope_signature(disposition_scope),
    }
    canonical = {
        key: report[key]
        for key in (
            "schema_version",
            "report_kind",
            "research_cycle_id",
            "source_disposition_ref",
            "summary",
            "suppressed_scopes",
            "eligible_directions",
            "ineligible_directions",
            "novelty_requirements",
            "evidence_requirements",
            "recommended_research_action",
            "operator_review_required",
            "authority_flags",
            "failure_action_context",
            "research_memory_context",
            "source_scope",
        )
    }
    report["deterministic_hash"] = _digest(canonical)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    eligible = report.get("eligible_directions") if isinstance(report.get("eligible_directions"), Sequence) else []
    ineligible = report.get("ineligible_directions") if isinstance(report.get("ineligible_directions"), Sequence) else []
    lines = [
        "# QRE Research Cycle Router",
        "",
        f"- research_cycle_id: {report.get('research_cycle_id', '')}",
        f"- source_disposition_ref: {report.get('source_disposition_ref', '')}",
        f"- recommended_research_action: {report.get('recommended_research_action', '')}",
        f"- operator_review_required: {report.get('operator_review_required', True)}",
        f"- eligible_direction_count: {len(eligible)}",
        f"- ineligible_direction_count: {len(ineligible)}",
        "",
        "## Suppressed Scope",
    ]
    for scope in report.get("suppressed_scopes", []):
        if not isinstance(scope, Mapping):
            continue
        lines.append(
            f"- {scope.get('scope_kind')}: {scope.get('suppression_reason')}"
        )
    lines.extend(["", "## Eligible Directions"])
    for direction in eligible:
        if not isinstance(direction, Mapping):
            continue
        lines.append(
            f"- {direction.get('direction_id')}: {direction.get('route_status')} "
            f"({', '.join(direction.get('eligibility_reasons', []))})"
        )
    lines.extend(["", "## Ineligible Directions"])
    for direction in ineligible:
        if not isinstance(direction, Mapping):
            continue
        lines.append(
            f"- {direction.get('direction_id')}: {direction.get('route_status')} "
            f"({', '.join(direction.get('eligibility_reasons', []))})"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def read_research_cycle_router_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_research_cycle_router",
            "router_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_research_cycle_router",
            "router_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, Mapping) else {}
    ready = bool(summary.get("router_ready")) if isinstance(summary, Mapping) else False
    return {
        "status": "ready" if ready else "not_ready",
        "router_ready": ready,
        "path": latest.relative_to(repo_root).as_posix(),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_research_cycle_router",
        description="Build a deterministic read-only next-cycle research router from rejected hypothesis memory.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_research_cycle_router_status(), indent=2, sort_keys=True))
        return 0
    report = build_research_cycle_router(generated_at_utc=args.frozen_utc)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
