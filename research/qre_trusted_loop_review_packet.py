"""QRE final trusted-loop review packet.

This module materializes a deterministic, read-only review packet for the
Roadmap v6 trusted-loop state. It summarizes available capabilities, report
surfaces, safety invariants, and remaining authority boundaries.

It does not mutate candidates, campaigns, strategies, presets, frozen contracts,
broker/risk/execution state, or paper/shadow/live activation.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import qre_trusted_loop_readiness as trusted_readiness
from research import qre_evidence_complete_basket_closure as basket_closure
from research import qre_failure_action_from_basket as failure_action
from research import qre_first_batch_evidence_recovery_cascade as first_batch_cascade
from research import qre_first_batch_evidence_recovery_readiness as first_batch_readiness
from research import qre_basket_operator_action_plan as basket_action_plan
from research import qre_reason_records_v1 as reason_records
from research import qre_research_memory_current_artifacts as research_memory
from research import qre_routing_calibration_report as routing_calibration
from research import qre_sampling_calibration_report as sampling_calibration


REPORT_KIND: Final[str] = "qre_trusted_loop_review_packet"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_trusted_loop_review")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_trusted_loop_review/"


CAPABILITY_ROWS: tuple[dict[str, Any], ...] = (
    {
        "capability_id": "A",
        "name": "source_identity_and_data_readiness_foundation",
        "status": "implemented",
        "authority": "read_only_context_and_fail_closed_readiness",
    },
    {
        "capability_id": "B",
        "name": "controlled_grid_and_evidence_closure",
        "status": "implemented",
        "authority": "read_only_artifact_materialization_and_diagnostics",
    },
    {
        "capability_id": "C",
        "name": "research_memory_ontology_entity_failure_context",
        "status": "implemented",
        "authority": "context_only_memory_and_retrieval_enrichment",
    },
    {
        "capability_id": "D",
        "name": "null_model_state_transition_tail_entropy_hardening",
        "status": "implemented",
        "authority": "context_only_diagnostics_and_report_surfaces",
    },
    {
        "capability_id": "E",
        "name": "sampling_and_routing_calibration",
        "status": "implemented",
        "authority": "context_only_calibration_no_queue_or_campaign_mutation",
    },
    {
        "capability_id": "F",
        "name": "trusted_loop_review_packet",
        "status": "implemented_by_this_packet",
        "authority": "operator_review_only",
    },
)


REPORT_SURFACES: tuple[dict[str, str], ...] = (
    {
        "report_kind": "qre_research_memory_coverage",
        "path_hint": "logs/qre_research_memory_coverage/",
        "purpose": "research memory coverage and ontology/entity context",
    },
    {
        "report_kind": "qre_null_model_baseline_report",
        "path_hint": "logs/qre_null_model_baseline/",
        "purpose": "null-model baseline diagnostics",
    },
    {
        "report_kind": "qre_state_transition_diagnostics_report",
        "path_hint": "logs/qre_state_transition_diagnostics/",
        "purpose": "state-transition diagnostics",
    },
    {
        "report_kind": "qre_tail_entropy_hardening_report",
        "path_hint": "logs/qre_tail_entropy_hardening/",
        "purpose": "tail/entropy hardening diagnostics",
    },
    {
        "report_kind": "qre_sampling_calibration_report",
        "path_hint": "logs/qre_sampling_calibration/",
        "purpose": "sampling calibration context",
    },
    {
        "report_kind": "qre_routing_calibration_report",
        "path_hint": "logs/qre_routing_calibration/",
        "purpose": "routing calibration context",
    },
    {
        "report_kind": "qre_first_batch_evidence_recovery_readiness",
        "path_hint": "logs/qre_first_batch_evidence_recovery_readiness/",
        "purpose": "bounded first-batch evidence recovery readiness plan",
    },
    {
        "report_kind": "qre_first_batch_evidence_recovery_cascade",
        "path_hint": "logs/qre_first_batch_evidence_recovery_cascade/",
        "purpose": "bounded first-batch recovery cascade with legacy artifact boundary analysis",
    },
    {
        "report_kind": "qre_guarded_alias_bounded_generation_cascade",
        "path_hint": "logs/qre_guarded_alias_bounded_generation_cascade/",
        "purpose": "guarded alias policy, bounded generation decision, and acceptance/verifier packet",
    },
    {
        "report_kind": "qre_trusted_loop_review_packet",
        "path_hint": "logs/qre_trusted_loop_review/",
        "purpose": "final trusted-loop operator review packet",
    },
)


def _path_state(repo_root: Path, relative_path: str) -> dict[str, Any]:
    path = repo_root / relative_path
    return {
        "path": relative_path,
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _guarded_alias_bounded_generation_snapshot(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(
        repo_root / "logs" / "qre_guarded_alias_bounded_generation_cascade" / "latest.json"
    )
    if isinstance(payload, dict) and str(payload.get("report_kind") or "") == "qre_guarded_alias_bounded_generation_cascade":
        return payload
    return {
        "report_kind": "qre_guarded_alias_bounded_generation_cascade_unavailable",
        "overall_result": "guarded_alias_bounded_generation_cascade_unavailable",
        "summary": {"current_top_blocker": "guarded_alias_bounded_generation_cascade_unavailable"},
    }


def _truthy(summary: Mapping[str, Any], key: str) -> bool:
    return bool(summary.get(key))


def _trusted_loop_level(
    *,
    readiness_state: str,
    readiness_summary: Mapping[str, Any],
    reason_summary: Mapping[str, Any],
    failure_summary: Mapping[str, Any],
    basket_summary: Mapping[str, Any],
    routing_summary: Mapping[str, Any],
    sampling_summary: Mapping[str, Any],
    memory_summary: Mapping[str, Any],
) -> tuple[str, str, list[str], str]:
    blockers: list[str] = []
    if readiness_state != "operator_trusted":
        blockers.append(f"readiness_state:{readiness_state}")
    if int(reason_summary.get("record_count") or 0) == 0:
        blockers.append("reason_records_missing")
    if int(basket_summary.get("evidence_complete_count") or 0) == 0:
        blockers.append("evidence_complete_basket_missing")
    if int(failure_summary.get("actionable_count") or 0) == 0:
        blockers.append("failure_actionable_context_missing")
    if str(routing_summary.get("final_recommendation") or "") != "routing_calibration_evidence_ready":
        blockers.append("routing_calibration_not_evidence_ready")
    if str(sampling_summary.get("final_recommendation") or "") != "sampling_calibration_evidence_ready":
        blockers.append("sampling_calibration_not_evidence_ready")
    if str(memory_summary.get("summary", {}).get("final_recommendation") or "") != "research_memory_current_artifacts_ready":
        blockers.append("research_memory_not_ready")
    if not _truthy(readiness_summary, "operator_report_available"):
        blockers.append("operator_report_missing")
    if str(readiness_summary.get("contradiction_visibility", {}).get("status") or "") != "visible":
        blockers.append("contradiction_visibility_incomplete")
    if str(readiness_summary.get("source_lineage", {}).get("status") or "") != "complete":
        blockers.append("source_lineage_incomplete")
    if str(readiness_summary.get("repeatability_status") or "") != "operator_approved_repeatability_evidence_present":
        blockers.append("repeatability_or_operator_approval_missing")

    if blockers:
        if readiness_state == "operator_trusted_candidate":
            level = "2"
            verdict = "evidence_backed_operator_review_required"
            exact_next_action = "refresh_missing_trusted_loop_evidence"
        elif readiness_state == "working_capability":
            level = "1"
            verdict = "read_only_context_fail_closed"
            exact_next_action = "restore_trusted_loop_readiness_evidence"
        elif readiness_state == "scaffold":
            level = "1"
            verdict = "scaffold_fail_closed"
            exact_next_action = "materialize_trusted_loop_evidence_chain"
        else:
            level = "2"
            verdict = "operator_trust_review_required"
            exact_next_action = "refresh_trusted_loop_evidence"
        return level, verdict, blockers, exact_next_action

    return "3", "operator_trusted", [], "maintain_operator_trusted_read_only_mode"


def build_trusted_loop_review_packet(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    readiness_packet = trusted_readiness.collect_snapshot()
    reason_snapshot = reason_records.build_reason_records_snapshot(repo_root=repo_root)
    failure_packet = failure_action.build_failure_action_from_basket(repo_root=repo_root)
    closure_packet = basket_closure.build_evidence_complete_basket_closure(repo_root=repo_root)
    routing_packet = routing_calibration.build_routing_calibration_report(repo_root=repo_root)
    sampling_packet = sampling_calibration.build_sampling_calibration_report(repo_root=repo_root)
    memory_packet = research_memory.build_research_memory_current_artifacts(repo_root=repo_root)
    action_plan_packet = basket_action_plan.build_basket_operator_action_plan(repo_root=repo_root)
    first_batch_readiness_packet = first_batch_readiness.build_first_batch_evidence_recovery_readiness(
        repo_root=repo_root
    )
    first_batch_cascade_packet = first_batch_cascade.build_first_batch_evidence_recovery_cascade(
        repo_root=repo_root
    )
    guarded_cascade_packet = _guarded_alias_bounded_generation_snapshot(repo_root)

    protected_artifacts = [
        _path_state(repo_root, "research/research_latest.json"),
        _path_state(repo_root, "research/strategy_matrix.csv"),
    ]

    implemented_count = sum(1 for row in CAPABILITY_ROWS if str(row.get("status", "")).startswith("implemented"))
    readiness_summary = readiness_packet if isinstance(readiness_packet, Mapping) else {}
    reason_summary = reason_snapshot.get("meta") if isinstance(reason_snapshot.get("meta"), Mapping) else {}
    failure_summary = failure_packet.get("summary") if isinstance(failure_packet.get("summary"), Mapping) else {}
    basket_summary = closure_packet.get("summary") if isinstance(closure_packet.get("summary"), Mapping) else {}
    routing_summary = routing_packet.get("summary") if isinstance(routing_packet.get("summary"), Mapping) else {}
    sampling_summary = sampling_packet.get("summary") if isinstance(sampling_packet.get("summary"), Mapping) else {}
    memory_summary = memory_packet if isinstance(memory_packet, Mapping) else {}
    action_plan_summary = action_plan_packet.get("summary") if isinstance(action_plan_packet.get("summary"), Mapping) else {}
    trust_level, trust_verdict, trust_blockers, exact_next_action = _trusted_loop_level(
        readiness_state=str(readiness_summary.get("readiness_state") or "scaffold"),
        readiness_summary=readiness_summary,
        reason_summary=reason_summary,
        failure_summary=failure_summary,
        basket_summary=basket_summary,
        routing_summary=routing_summary,
        sampling_summary=sampling_summary,
        memory_summary=memory_summary,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "trusted_loop_review_ready": trust_verdict == "operator_trusted",
            "trust_level": trust_level,
            "trust_verdict": trust_verdict,
            "trust_blocker_count": len(trust_blockers),
            "trust_blockers": trust_blockers,
            "exact_next_action": exact_next_action,
            "readiness_state": str(readiness_summary.get("readiness_state") or "scaffold"),
            "reason_record_count": int(reason_summary.get("record_count") or 0),
            "failure_actionable_count": int(failure_summary.get("actionable_count") or 0),
            "evidence_complete_basket_count": int(basket_summary.get("evidence_complete_count") or 0),
            "routing_evidence_ready": str(routing_summary.get("final_recommendation") or "")
            == "routing_calibration_evidence_ready",
            "sampling_evidence_ready": str(sampling_summary.get("final_recommendation") or "")
            == "sampling_calibration_evidence_ready",
            "research_memory_ready": str(
                (memory_summary.get("summary") or {}).get("final_recommendation") or ""
            )
            == "research_memory_current_artifacts_ready",
            "basket_operator_action_plan_ready": str(action_plan_summary.get("final_recommendation") or "")
            == "basket_operator_action_plan_ready",
            "basket_operator_action_plan_first_batch": list(
                action_plan_summary.get("first_batch_candidate_symbols") or []
            ),
            "first_batch_readiness_available": str(first_batch_readiness_packet.get("report_kind") or "")
            == "qre_first_batch_evidence_recovery_readiness",
            "first_batch_recovery_cascade_available": str(first_batch_cascade_packet.get("report_kind") or "")
            == "qre_first_batch_evidence_recovery_cascade",
            "first_batch_recovery_cascade_result": str(first_batch_cascade_packet.get("overall_result") or ""),
            "first_batch_recovery_cascade_top_blocker": str(
                (first_batch_cascade_packet.get("first_batch_summary") or {}).get("current_top_blocker") or ""
            ),
            "guarded_alias_bounded_generation_cascade_result": str(guarded_cascade_packet.get("overall_result") or ""),
            "guarded_alias_bounded_generation_top_blocker": str(
                (guarded_cascade_packet.get("summary") or {}).get("current_top_blocker") or ""
            ),
            "contradiction_visibility": (
                readiness_summary.get("contradiction_visibility")
                if isinstance(readiness_summary.get("contradiction_visibility"), Mapping)
                else {}
            ),
            "source_lineage": (
                readiness_summary.get("source_lineage")
                if isinstance(readiness_summary.get("source_lineage"), Mapping)
                else {}
            ),
            "repeatability_status": str(readiness_summary.get("repeatability_status") or "unknown"),
            "capability_count": len(CAPABILITY_ROWS),
            "implemented_capability_count": implemented_count,
            "report_surface_count": len(REPORT_SURFACES),
            "final_recommendation": (
                "trusted_loop_operator_trusted"
                if trust_verdict == "operator_trusted"
                else "trusted_loop_operator_review_required"
            ),
            "operator_summary": (
                "Roadmap A-F trusted-loop scaffolds and report surfaces are present as "
                "deterministic, read-only/context-only diagnostics. The packet now requires "
                "durable reason records, closure evidence, calibrated routing/sampling, and "
                "trusted-loop readiness before it will report operator trust."
            ),
        },
        "capabilities": list(CAPABILITY_ROWS),
        "report_surfaces": list(REPORT_SURFACES),
        "evidence_inputs": {
            "trusted_loop_readiness": readiness_packet,
            "reason_records": reason_snapshot,
            "failure_action": failure_packet,
            "basket_closure": closure_packet,
            "first_batch_readiness": first_batch_readiness_packet,
            "first_batch_recovery_cascade": first_batch_cascade_packet,
            "guarded_alias_bounded_generation_cascade": guarded_cascade_packet,
            "routing_calibration": routing_packet,
            "sampling_calibration": sampling_packet,
            "research_memory": memory_packet,
        },
        "protected_artifacts": protected_artifacts,
        "current_scope_policy": {
            "crypto_legacy": "excluded_from_current_research_scope_and_archive_only",
            "preferred_sampling_axes": [
                "equity",
                "fundamental_equity",
                "index",
                "target_equity_research",
                "target_source_data_research",
                "target_factor_research",
                "netherlands",
                "europe",
                "united_states",
                "asia",
            ],
            "routing_context_targets": [
                "sampling_calibration",
                "data_readiness",
                "source_quality",
                "identity_resolution",
                "factor_coverage",
                "null_model_baseline",
                "state_transition_diagnostics",
                "tail_entropy_hardening",
                "failure_retrieval",
                "operator_review",
                "excluded_scope_archive",
            ],
        },
        "authority_boundaries": {
            "review_packet_is_context_only": True,
            "not_alpha_authority": True,
            "not_queue_mutation": True,
            "not_candidate_promotion": True,
            "not_campaign_mutation": True,
            "not_strategy_registration": True,
            "not_preset_mutation": True,
            "not_trade_signal_generation": True,
            "not_provider_activation": True,
            "not_data_fetching": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "not_risk_authority": True,
            "does_not_mutate_frozen_contracts": True,
            "does_not_mutate_research_latest": True,
            "does_not_mutate_strategy_matrix": True,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_external_data": False,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "mutates_queues": False,
            "mutates_candidates": False,
            "mutates_campaigns": False,
            "mutates_strategies": False,
            "mutates_presets": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(packet: Mapping[str, Any]) -> str:
    summary = packet.get("summary") if isinstance(packet.get("summary"), Mapping) else {}
    trust_blockers = summary.get("trust_blockers") if isinstance(summary.get("trust_blockers"), list) else []
    return "\n".join(
        [
            "# QRE Trusted Loop Review Packet",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Trust Verdict",
            "",
            f"- trust_level: {summary.get('trust_level')}",
            f"- trust_verdict: {summary.get('trust_verdict')}",
            f"- exact_next_action: {summary.get('exact_next_action')}",
            f"- trusted_loop_review_ready: {summary.get('trusted_loop_review_ready')}",
            f"- readiness_state: {summary.get('readiness_state')}",
            f"- reason_record_count: {summary.get('reason_record_count')}",
            f"- failure_actionable_count: {summary.get('failure_actionable_count')}",
            f"- evidence_complete_basket_count: {summary.get('evidence_complete_basket_count')}",
            f"- routing_evidence_ready: {summary.get('routing_evidence_ready')}",
            f"- sampling_evidence_ready: {summary.get('sampling_evidence_ready')}",
            f"- research_memory_ready: {summary.get('research_memory_ready')}",
            f"- guarded_alias_bounded_generation_cascade_result: {summary.get('guarded_alias_bounded_generation_cascade_result')}",
            f"- guarded_alias_bounded_generation_top_blocker: {summary.get('guarded_alias_bounded_generation_top_blocker')}",
            f"- trust_blockers: {', '.join(str(item) for item in trust_blockers) or 'none'}",
            "",
            "## Current Status",
            "",
            f"- capability_count: {summary.get('capability_count')}",
            f"- implemented_capability_count: {summary.get('implemented_capability_count')}",
            f"- report_surface_count: {summary.get('report_surface_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
            "## Authority Boundary",
            "",
            "- This packet is operator-review context only.",
            "- It does not authorize paper, shadow, live trading, broker execution, risk changes, queue mutation, campaign mutation, strategy registration, or preset mutation.",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_trusted_loop_review_packet: refusing write outside allowlist: {path!r}")


def write_outputs(packet: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME

    for target in (latest, summary_path):
        _validate_write_target(target)

    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)

    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(packet), encoding="utf-8")
    os.replace(tmp_md, summary_path)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_trusted_loop_review_packet",
        description="Build read-only QRE trusted-loop review packet.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_trusted_loop_review_packet()
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
