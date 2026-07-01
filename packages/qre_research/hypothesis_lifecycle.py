from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research.generated_hypothesis_paths import (
    EVIDENCE_UPDATES_PATH,
    FAILURE_ACTIONS_PATH,
    FEASIBILITY_PATH,
    REASON_RECORDS_PATH,
    REPO_ROOT,
    RESEARCH_MEMORY_PATH,
    ROUTING_PATH,
    SAMPLING_PATH,
    TRUSTED_LOOP_SUMMARY_PATH,
    repo_relative,
    validate_write_target,
)


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-027.1"
MAX_HYPOTHESES_PER_CYCLE: Final[int] = 10
EMPIRICAL_EVIDENCE_PACK_PATH: Final[Path] = Path(
    "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{stable_digest(payload)[:16]}"


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ade_qre_027.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _read_empirical_pack(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / EMPIRICAL_EVIDENCE_PACK_PATH)
    return payload if isinstance(payload, dict) else {}


def _identity_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("source_hypothesis_id") or ""): row
        for row in _read_rows(
            repo_root / "logs" / "qre_identity_ambiguity_resolution" / "latest.json"
        )
        if str(row.get("source_hypothesis_id") or "")
    }


def _source_quality_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("source_hypothesis_id") or row.get("candidate_id") or ""): row
        for row in _read_rows(repo_root / "logs" / "qre_source_usefulness" / "latest.json")
        if str(row.get("source_hypothesis_id") or row.get("candidate_id") or "")
    }


def _candidate_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    compiled = a20.compile_candidate_theses(repo_root=repo_root)
    return {
        str(row.get("thesis_id") or ""): row
        for row in compiled.get("rows", [])
        if str(row.get("thesis_id") or "")
    }


def _candidate_index_by_source(repo_root: Path) -> dict[str, dict[str, Any]]:
    compiled = a20.compile_candidate_theses(repo_root=repo_root)
    return {
        str(row.get("source_hypothesis_id") or ""): row
        for row in compiled.get("rows", [])
        if str(row.get("source_hypothesis_id") or "")
    }


def _readiness_rows_by_strategy(
    repo_root: Path,
    relative_path: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = _read_rows(repo_root / Path(relative_path))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        strategy_id = str(row.get("generated_strategy_id") or "")
        if not strategy_id:
            continue
        grouped.setdefault(strategy_id, []).append(row)
    return grouped


def _strategy_index_by_source(repo_root: Path) -> dict[str, dict[str, Any]]:
    rows = _read_rows(
        repo_root
        / "generated_research"
        / "registry"
        / "generated_strategy_registry.v1.json"
    )
    return {
        str(row.get("source_hypothesis_id") or ""): row
        for row in rows
        if str(row.get("source_hypothesis_id") or "")
    }


def _spec_by_strategy(repo_root: Path, strategy_row: dict[str, Any]) -> dict[str, Any]:
    spec_id = str(strategy_row.get("strategy_spec_id") or "")
    if not spec_id:
        return {}
    payload = _read_json(repo_root / "generated_research" / "specs" / f"{spec_id}.json")
    return payload if isinstance(payload, dict) else {}


def _select_portfolio_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    order = {
        "READY_FOR_PREREGISTRATION": 0,
        "BLOCKED_WINDOWS": 1,
        "BLOCKED_DATA": 2,
    }
    selected = sorted(
        rows,
        key=lambda row: (
            order.get(str(row.get("status") or ""), 99),
            str(row.get("timeframe") or ""),
            str(row.get("campaign_cell_id") or ""),
        ),
    )
    return dict(selected[0])


def _required_primitives_ready(
    repo_root: Path,
    *,
    candidate: dict[str, Any],
    strategy_row: dict[str, Any],
    strategy_spec: dict[str, Any],
) -> bool:
    primitive_rows = _read_rows(
        repo_root
        / "generated_research"
        / "primitives"
        / "registry"
        / "generated_primitive_registry.v1.json"
    )
    available = {
        str(row.get("primitive_id") or "")
        for row in primitive_rows
        if str(row.get("state") or "") == "PRIMITIVE_REGISTERED_AUTOMATED"
    }
    required = list(candidate.get("required_features") or [])
    required.extend(list(strategy_spec.get("required_feature_primitives") or []))
    if strategy_row:
        required.extend(list(strategy_spec.get("required_feature_primitives") or []))
    normalized = {
        item
        for item in required
        if item and item not in {"relative_strength_spread"}
    }
    return normalized.issubset(available)


def _falsification_criteria(candidate: dict[str, Any], strategy_spec: dict[str, Any]) -> list[str]:
    criteria = [
        item
        for item in list(candidate.get("falsification_criteria") or [])
        if not str(item).startswith("blocked:")
    ]
    if criteria:
        return criteria
    return list(strategy_spec.get("expected_failure_modes") or [])


def _expected_observables(candidate: dict[str, Any], strategy_spec: dict[str, Any]) -> list[str]:
    observables = [
        item
        for item in list(candidate.get("entry_relevant_observations") or [])
        if item
    ]
    if observables:
        return observables
    expected_behavior = str(strategy_spec.get("expected_behavior") or "")
    if not expected_behavior:
        return []
    return [part.strip() for part in expected_behavior.split(";") if part.strip()]


def _selected_generated_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows = _read_rows(
        repo_root
        / "generated_research"
        / "hypotheses"
        / "registry"
        / "generated_thesis_registry.v1.json"
    )
    candidates = [
        row
        for row in rows
        if str(row.get("lifecycle_state") or "")
        in {"HYPOTHESIS_ADMITTED_AUTOMATED", "ADMITTED_GENERATION_BLOCKED", "BLOCKED_IDENTITY"}
    ]
    candidates.sort(
        key=lambda row: (
            0
            if str(row.get("lifecycle_state") or "") == "HYPOTHESIS_ADMITTED_AUTOMATED"
            else 1,
            str(row.get("thesis_id") or ""),
        )
    )
    return candidates[:MAX_HYPOTHESES_PER_CYCLE]


def build_feasibility_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    identities = _identity_index(repo_root)
    source_quality = _source_quality_index(repo_root)
    candidates = _candidate_index_by_source(repo_root)
    strategy_index = _strategy_index_by_source(repo_root)
    data_bindings = _readiness_rows_by_strategy(
        repo_root,
        "generated_research/readiness/data_bindings/autonomous_strategy_data_bindings.v1.json",
    )
    universe_authority = _readiness_rows_by_strategy(
        repo_root,
        "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
    )
    portfolio_rows = _readiness_rows_by_strategy(
        repo_root,
        "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
    )
    rows: list[dict[str, Any]] = []
    for generated_row in _selected_generated_rows(repo_root):
        thesis_id = str(generated_row.get("thesis_id") or "")
        source_hypothesis_id = str(generated_row.get("source_hypothesis_id") or "")
        candidate = candidates.get(source_hypothesis_id, {})
        strategy_row = strategy_index.get(source_hypothesis_id, {})
        strategy_spec = _spec_by_strategy(repo_root, strategy_row)
        strategy_id = str(strategy_row.get("generated_strategy_id") or "")
        identity_row = identities.get(source_hypothesis_id, {})
        quality_row = source_quality.get(source_hypothesis_id, {})
        lifecycle_state = str(generated_row.get("lifecycle_state") or "")
        identity_state = str(identity_row.get("resolution_state") or "UNKNOWN")
        falsification_criteria = _falsification_criteria(candidate, strategy_spec)
        expected_observables = _expected_observables(candidate, strategy_spec)
        required_data = list(candidate.get("required_data") or [])
        binding_rows = data_bindings.get(strategy_id, [])
        authority_rows = universe_authority.get(strategy_id, [])
        portfolio_row = _select_portfolio_row(portfolio_rows.get(strategy_id, []))
        blockers: list[str] = []
        primitive_ready = _required_primitives_ready(
            repo_root,
            candidate=candidate,
            strategy_row=strategy_row,
            strategy_spec=strategy_spec,
        )
        data_ready = any(
            str(row.get("outcome") or "") == "DATA_BINDING_READY"
            for row in binding_rows
        )
        identity_ready = bool(authority_rows) or identity_state in {"RESOLVED", "RESOLVED_UNIQUE_AUTHORITATIVE"}
        if not strategy_row:
            blockers.append("generated_strategy_missing")
        if not primitive_ready:
            blockers.append("required_primitives_missing")
        if not identity_ready:
            blockers.append("identity_unresolved")
        if portfolio_row and str(portfolio_row.get("status") or "") == "BLOCKED_DATA":
            blockers.extend(list(portfolio_row.get("blockers") or ["data_binding_not_ready"]))
        elif not data_ready:
            blockers.append("data_binding_not_ready")
        if not falsification_criteria:
            blockers.append("missing_falsification_criteria")
        if not expected_observables:
            blockers.append("missing_expected_observables")
        if quality_row and str(quality_row.get("status") or "").lower() in {"blocked", "failed"}:
            blockers.append("source_quality_failed")
        ready = not blockers
        rows.append(
            {
                "feasibility_id": _content_id("qhf", {"thesis_id": thesis_id, "ready": ready}),
                "thesis_id": thesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "behavior_family": str(generated_row.get("behavior_family") or ""),
                "status": "ready" if ready else "blocked",
                "identity_status": identity_state,
                "lifecycle_state": lifecycle_state,
                "primitive_compatibility": (
                    "COMPILABLE_WITH_CURRENT_PRIMITIVES"
                    if primitive_ready
                    else str(generated_row.get("primitive_compatibility") or "UNKNOWN")
                ),
                "required_data_capabilities": required_data,
                "falsification_criteria": falsification_criteria,
                "expected_observables": expected_observables,
                "generated_strategy_id": strategy_id,
                "portfolio_status": str(portfolio_row.get("status") or ""),
                "portfolio_blockers": list(portfolio_row.get("blockers") or []),
                "missing_prerequisites": blockers,
                "policy_denial": False,
                "duplicate_active_research_path": False,
                "next_action": (
                    str(portfolio_row.get("next_action") or "route_hypothesis_for_sampling")
                    if ready
                    else (blockers[0] if blockers else "collect_missing_prerequisites")
                ),
            }
        )
    summary = {
        "selected_hypothesis_count": len(rows),
        "feasibility_ready_count": sum(1 for row in rows if row["status"] == "ready"),
        "blocked_count": sum(1 for row in rows if row["status"] != "ready"),
        "max_hypotheses_per_cycle": MAX_HYPOTHESES_PER_CYCLE,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_feasibility",
        "rows": rows,
        "summary": summary,
    }


def build_routing_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    feasibility = build_feasibility_snapshot(repo_root=repo_root)
    candidates = _candidate_index_by_source(repo_root)
    rows: list[dict[str, Any]] = []
    for row in feasibility["rows"]:
        source_hypothesis_id = str(row.get("source_hypothesis_id") or "")
        thesis_id = str(row.get("thesis_id") or "")
        candidate = candidates.get(source_hypothesis_id, {})
        ready = str(row.get("status") or "") == "ready"
        portfolio_status = str(row.get("portfolio_status") or "")
        blocker_count = len(list(row.get("portfolio_blockers") or []))
        score_tuple = (
            1 if ready else 0,
            1 if str(candidate.get("novelty_outcome") or "") == "NOVEL_WITH_OVERLAP" else 2,
            0 if portfolio_status == "READY_FOR_PREREGISTRATION" else 1,
            blocker_count,
            1 if str(candidate.get("testability_state") or "") in {"WINDOW_CAPACITY_BLOCKED", "TESTABLE_WITH_LIMITATIONS"} else 2,
            thesis_id,
        )
        decision = "prioritize" if ready else "blocked"
        rows.append(
            {
                "routing_id": _content_id("qhr", {"thesis_id": thesis_id, "score": score_tuple}),
                "thesis_id": thesis_id,
                "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                "routing_status": "ready" if ready else "blocked",
                "decision": decision,
                "score_tuple": list(score_tuple[:-1]),
                "expected_information_gain": "high" if ready else "blocked",
                "orthogonality": "bounded_novel_mechanism",
                "prior_failure_similarity": "lineage_aware",
                "dead_zone_risk": str(candidate.get("testability_state") or portfolio_status or ""),
                "data_readiness": "data_binding_ready" if ready else "blocked",
                "source_quality": "authoritative_or_not_materialized",
                "primitive_readiness": str(row.get("primitive_compatibility") or ""),
                "compute_cost": "low",
                "campaign_overlap": "none",
                "reason_codes": list(row.get("portfolio_blockers") or []),
                "next_action": (
                    "materialize_sampling_plan"
                    if ready
                    else str((row.get("missing_prerequisites") or ["blocked"])[0])
                ),
            }
        )
    rows.sort(key=lambda item: (0 if item["decision"] == "prioritize" else 1, item["thesis_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_routing",
        "rows": rows,
        "summary": {
            "routing_ready_count": sum(1 for row in rows if row["routing_status"] == "ready"),
            "blocked_count": sum(1 for row in rows if row["routing_status"] != "ready"),
            "selected_count": len(rows),
        },
        "final_recommendation": (
            "ready_for_sampling"
            if any(row["routing_status"] == "ready" for row in rows)
            else "blocked_by_prerequisites"
        ),
    }


def build_sampling_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    routing = build_routing_snapshot(repo_root=repo_root)
    candidates = _candidate_index_by_source(repo_root)
    portfolio_rows = _readiness_rows_by_strategy(
        repo_root,
        "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
    )
    strategy_index = _strategy_index_by_source(repo_root)
    rows: list[dict[str, Any]] = []
    for routing_row in routing["rows"]:
        thesis_id = str(routing_row.get("thesis_id") or "")
        source_hypothesis_id = str(routing_row.get("source_hypothesis_id") or "")
        candidate = candidates.get(source_hypothesis_id, {})
        ready = str(routing_row.get("routing_status") or "") == "ready"
        strategy_row = strategy_index.get(source_hypothesis_id, {})
        strategy_id = str(strategy_row.get("generated_strategy_id") or "")
        portfolio_row = _select_portfolio_row(portfolio_rows.get(strategy_id, []))
        timeframe = str(candidate.get("timeframe") or portfolio_row.get("timeframe") or "")
        timeframes = [part for part in timeframe.split("|") if part]
        sampled_timeframes = [str(portfolio_row.get("timeframe") or "")] if str(portfolio_row.get("timeframe") or "") else timeframes
        actionable = ready and str(portfolio_row.get("status") or "") == "READY_FOR_PREREGISTRATION"
        coverage = {
            "timeframe_count": len(sampled_timeframes or timeframes),
            "regime_count": len(candidate.get("regimes") or []),
            "expected_observable_count": len(candidate.get("entry_relevant_observations") or []),
        }
        rows.append(
            {
                "sampling_id": _content_id("qhs", {"thesis_id": thesis_id, "coverage": coverage}),
                "thesis_id": thesis_id,
                "source_hypothesis_id": str(routing_row.get("source_hypothesis_id") or ""),
                "sampling_status": "ready" if actionable else "blocked",
                "coverage": coverage,
                "selected_universe": str(candidate.get("universe") or ""),
                "sampled_timeframes": sampled_timeframes or timeframes,
                "train_window": dict(portfolio_row.get("train_window") or {}),
                "validation_window": dict(portfolio_row.get("validation_window") or {}),
                "oos_window": dict(portfolio_row.get("oos_window") or {}),
                "regime_coverage": list(candidate.get("regimes") or []),
                "control_null_samples": list(candidate.get("null_control_requirements") or []),
                "compute_estimate": "low",
                "sampling_reason_codes": list(portfolio_row.get("blockers") or []),
                "null_control_support": bool(candidate.get("null_control_requirements")),
                "oos_conservation": "preserved",
                "next_action": (
                    "evaluate_exact_blocker_or_empirical_campaign_gap"
                    if actionable
                    else str(
                        portfolio_row.get("next_action")
                        or routing_row.get("next_action")
                        or "blocked"
                    )
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_sampling",
        "rows": rows,
        "summary": {
            "sampling_ready_count": sum(1 for row in rows if row["sampling_status"] == "ready"),
            "blocked_count": sum(1 for row in rows if row["sampling_status"] != "ready"),
            "selected_count": len(rows),
        },
        "final_recommendation": (
            "ready_for_evaluation"
            if any(row["sampling_status"] == "ready" for row in rows)
            else "blocked_by_sampling_prerequisites"
        ),
    }


def build_reason_records_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    feasibility = build_feasibility_snapshot(repo_root=repo_root)
    routing = build_routing_snapshot(repo_root=repo_root)
    sampling = build_sampling_snapshot(repo_root=repo_root)
    empirical_pack = _read_empirical_pack(repo_root)
    reason_rows: list[dict[str, Any]] = []
    routing_index = {str(row.get("thesis_id") or ""): row for row in routing["rows"]}
    sampling_index = {str(row.get("thesis_id") or ""): row for row in sampling["rows"]}
    for row in feasibility["rows"]:
        thesis_id = str(row.get("thesis_id") or "")
        routing_row = routing_index.get(thesis_id, {})
        sampling_row = sampling_index.get(thesis_id, {})
        source_hypothesis_id = str(row.get("source_hypothesis_id") or "")
        empirical_match = (
            empirical_pack
            if str(empirical_pack.get("source_hypothesis_id") or "") == source_hypothesis_id
            else {}
        )
        for stage, status, refs in (
            ("generated", "completed", ["generated_research/hypotheses/registry/generated_thesis_registry.v1.json"]),
            ("feasible" if row["status"] == "ready" else "not_feasible", row["status"], row.get("missing_prerequisites") or []),
            ("routed" if routing_row.get("routing_status") == "ready" else "not_routed", str(routing_row.get("routing_status") or ""), [str(routing_row.get("next_action") or "")]),
            ("sampled" if sampling_row.get("sampling_status") == "ready" else "not_sampled", str(sampling_row.get("sampling_status") or ""), [str(sampling_row.get("next_action") or "")]),
            (
                "campaign_admitted" if empirical_match else "campaign_blocked",
                "completed" if empirical_match else "blocked",
                [str(empirical_match.get("campaign_identity") or sampling_row.get("next_action") or "campaign_not_materialized")],
            ),
            (
                "evidence_complete" if empirical_match and str(empirical_match.get("disposition") or "") == "READY_FOR_SYNTHESIS" else "evidence_incomplete",
                "completed" if empirical_match else "open",
                [str(empirical_match.get("disposition") or "empirical_evidence_not_materialized")],
            ),
            ("synthesis_eligible" if empirical_match and str(empirical_match.get("disposition") or "") == "READY_FOR_SYNTHESIS" else "synthesis_ineligible", "open", ["readiness_not_evidence_complete"]),
        ):
            reason_rows.append(
                {
                    "reason_record_id": _content_id("qrr", {"thesis_id": thesis_id, "stage": stage}),
                    "thesis_id": thesis_id,
                    "source_hypothesis_id": source_hypothesis_id,
                    "stage": stage,
                    "status": status,
                    "evidence_refs": [ref for ref in refs if ref],
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_reason_records",
        "rows": reason_rows,
        "summary": {"reason_record_count": len(reason_rows)},
    }


def build_evidence_updates_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    candidates = _candidate_index_by_source(repo_root)
    sampling = build_sampling_snapshot(repo_root=repo_root)
    empirical_pack = _read_empirical_pack(repo_root)
    rows: list[dict[str, Any]] = []
    for row in sampling["rows"]:
        thesis_id = str(row.get("thesis_id") or "")
        source_hypothesis_id = str(row.get("source_hypothesis_id") or "")
        candidate = candidates.get(source_hypothesis_id, {})
        contradictions = list(candidate.get("strongest_contradicting_evidence") or [])
        supporting = list(candidate.get("strongest_supporting_evidence") or [])
        empirical_match = (
            empirical_pack
            if str(empirical_pack.get("source_hypothesis_id") or "") == source_hypothesis_id
            else {}
        )
        decision = str(empirical_match.get("disposition") or "evidence_incomplete")
        missing_evidence = list(empirical_match.get("missing_evidence") or [])
        if not empirical_match:
            missing_evidence = [
                "controlled_evaluation",
                "transaction_cost_evidence",
                "null_model_evidence",
                "stability_evidence",
                "oos_evidence",
                str(row.get("next_action") or "campaign_not_materialized"),
            ]
        rows.append(
            {
                "evidence_update_id": _content_id("qhe", {"thesis_id": thesis_id, "decision": decision}),
                "thesis_id": thesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "decision": decision,
                "supporting_evidence": list(empirical_match.get("supporting_evidence") or supporting),
                "contradicting_evidence": list(empirical_match.get("contradicting_evidence") or contradictions),
                "missing_evidence": missing_evidence,
                "campaign_refs": list(empirical_match.get("campaign_refs") or []),
                "validation_refs": list(empirical_match.get("validation_refs") or []),
                "next_action": str(empirical_match.get("recommended_next_action") or row.get("next_action") or ""),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_evidence_updates",
        "rows": rows,
        "summary": {
            "evidence_update_count": len(rows),
            "contradiction_count": sum(1 for row in rows if row["contradicting_evidence"]),
        },
    }


def build_failure_actions_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    feasibility = build_feasibility_snapshot(repo_root=repo_root)
    sampling = build_sampling_snapshot(repo_root=repo_root)
    sampling_index = {str(row.get("thesis_id") or ""): row for row in sampling["rows"]}
    rows: list[dict[str, Any]] = []
    mapping = {
        "admitted_generation_blocked": "request_bounded_primitive_extension",
        "compilable_after_bounded_primitive_extension": "request_bounded_primitive_extension",
        "blocked_identity": "resolve_identity_before_replay",
        "identity_unresolved": "resolve_identity_before_replay",
        "missing_falsification_criteria": "materialize_falsification_criteria",
        "missing_expected_observables": "materialize_expected_observables",
        "usable_history_below_minimum_policy_span": "launch_data_oos_capacity_expansion",
        "cache_row_missing": "launch_data_oos_capacity_expansion",
    }
    for row in feasibility["rows"]:
        blockers = list(row.get("missing_prerequisites") or [])
        sampling_row = sampling_index.get(str(row.get("thesis_id") or ""), {})
        sampling_blockers = list(sampling_row.get("sampling_reason_codes") or [])
        if not blockers and sampling_blockers:
            blockers = sampling_blockers
        action = mapping.get(blockers[0], str(sampling_row.get("next_action") or "collect_empirical_validation_evidence")) if blockers else str(sampling_row.get("next_action") or "collect_empirical_validation_evidence")
        rows.append(
            {
                "failure_action_id": _content_id("qhfa", {"thesis_id": row["thesis_id"], "action": action}),
                "thesis_id": str(row.get("thesis_id") or ""),
                "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                "failure_codes": blockers,
                "next_action": action,
                "actionable": bool(blockers) or action == "collect_empirical_validation_evidence",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_failure_actions",
        "rows": rows,
        "summary": {
            "failure_action_count": len(rows),
            "actionable_failure_count": sum(1 for row in rows if row["actionable"]),
        },
    }


def build_research_memory_snapshot(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    routing = build_routing_snapshot(repo_root=repo_root)
    sampling = build_sampling_snapshot(repo_root=repo_root)
    evidence = build_evidence_updates_snapshot(repo_root=repo_root)
    failures = build_failure_actions_snapshot(repo_root=repo_root)
    empirical_pack = _read_empirical_pack(repo_root)
    routing_index = {str(row.get("thesis_id") or ""): row for row in routing["rows"]}
    sampling_index = {str(row.get("thesis_id") or ""): row for row in sampling["rows"]}
    evidence_index = {str(row.get("thesis_id") or ""): row for row in evidence["rows"]}
    failure_index = {str(row.get("thesis_id") or ""): row for row in failures["rows"]}
    rows: list[dict[str, Any]] = []
    for thesis_id, routing_row in routing_index.items():
        sampling_row = sampling_index.get(thesis_id, {})
        evidence_row = evidence_index.get(thesis_id, {})
        failure_row = failure_index.get(thesis_id, {})
        empirical_match = (
            empirical_pack
            if str(empirical_pack.get("source_hypothesis_id") or "") == str(routing_row.get("source_hypothesis_id") or "")
            else {}
        )
        rows.append(
            {
                "memory_id": _content_id("qhm", {"thesis_id": thesis_id}),
                "thesis_id": thesis_id,
                "source_hypothesis_id": str(routing_row.get("source_hypothesis_id") or ""),
                "routing_decision": str(routing_row.get("decision") or ""),
                "sampling_status": str(sampling_row.get("sampling_status") or ""),
                "evidence_decision": str(evidence_row.get("decision") or ""),
                "contradiction_count": len(evidence_row.get("contradicting_evidence") or []),
                "campaign": str(empirical_match.get("campaign_identity") or ""),
                "evidence_disposition": str(empirical_match.get("disposition") or ""),
                "failure_reason": str(empirical_match.get("terminal_outcome") or ""),
                "next_action": str(failure_row.get("next_action") or evidence_row.get("next_action") or ""),
                "disposition": "preserve_for_replay",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_research_memory",
        "rows": rows,
        "summary": {"memory_update_count": len(rows)},
    }


def run_trusted_hypothesis_loop(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
) -> dict[str, Any]:
    feasibility = build_feasibility_snapshot(repo_root=repo_root)
    routing = build_routing_snapshot(repo_root=repo_root)
    sampling = build_sampling_snapshot(repo_root=repo_root)
    reason_records = build_reason_records_snapshot(repo_root=repo_root)
    evidence_updates = build_evidence_updates_snapshot(repo_root=repo_root)
    failure_actions = build_failure_actions_snapshot(repo_root=repo_root)
    research_memory = build_research_memory_snapshot(repo_root=repo_root)
    empirical_pack = _read_empirical_pack(repo_root)
    empirical_materialized = bool(empirical_pack)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_trusted_loop_summary",
        "selected_hypotheses": feasibility["summary"]["selected_hypothesis_count"],
        "feasibility_ready_count": feasibility["summary"]["feasibility_ready_count"],
        "routing_ready_count": routing["summary"]["routing_ready_count"],
        "sampling_ready_count": sampling["summary"]["sampling_ready_count"],
        "campaigns_admitted": 1 if empirical_materialized else 0,
        "reason_record_count": reason_records["summary"]["reason_record_count"],
        "evidence_update_count": evidence_updates["summary"]["evidence_update_count"],
        "contradiction_count": evidence_updates["summary"]["contradiction_count"],
        "failure_action_count": failure_actions["summary"]["failure_action_count"],
        "memory_update_count": research_memory["summary"]["memory_update_count"],
        "unknown_failure_rate": None,
        "actionable_failure_rate": (
            round(
                failure_actions["summary"]["actionable_failure_count"]
                / max(failure_actions["summary"]["failure_action_count"], 1),
                6,
            )
            if failure_actions["summary"]["failure_action_count"]
            else None
        ),
        "causal_next_action_rate": (
            round(
                sum(1 for row in failure_actions["rows"] if row.get("next_action"))
                / max(len(failure_actions["rows"]), 1),
                6,
            )
            if failure_actions["rows"]
            else None
        ),
        "next_action": (
            str(
                empirical_pack.get("recommended_next_action")
                or failure_actions["rows"][0].get("next_action")
                or ""
            )
            if failure_actions["rows"]
            else "no_hypothesis_selected"
        ),
        "fixture_evidence_is_empirical": False,
        "empirical_research_evidence_materialized": empirical_materialized,
    }
    artifacts = {
        FEASIBILITY_PATH: feasibility,
        ROUTING_PATH: routing,
        SAMPLING_PATH: sampling,
        REASON_RECORDS_PATH: reason_records,
        EVIDENCE_UPDATES_PATH: evidence_updates,
        FAILURE_ACTIONS_PATH: failure_actions,
        RESEARCH_MEMORY_PATH: research_memory,
        TRUSTED_LOOP_SUMMARY_PATH: summary,
    }
    if write_outputs:
        for path, payload in artifacts.items():
            _atomic_write(repo_root / path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    summary["artifact_paths"] = {
        key: repo_relative(repo_root / key)
        for key in artifacts
    }
    return summary


__all__ = [
    "MAX_HYPOTHESES_PER_CYCLE",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "build_evidence_updates_snapshot",
    "build_failure_actions_snapshot",
    "build_feasibility_snapshot",
    "build_reason_records_snapshot",
    "build_research_memory_snapshot",
    "build_routing_snapshot",
    "build_sampling_snapshot",
    "run_trusted_hypothesis_loop",
    "stable_digest",
]
