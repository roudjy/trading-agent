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


def build_trusted_loop_review_packet(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    protected_artifacts = [
        _path_state(repo_root, "research/research_latest.json"),
        _path_state(repo_root, "research/strategy_matrix.csv"),
    ]

    implemented_count = sum(1 for row in CAPABILITY_ROWS if str(row.get("status", "")).startswith("implemented"))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "trusted_loop_review_ready": True,
            "capability_count": len(CAPABILITY_ROWS),
            "implemented_capability_count": implemented_count,
            "report_surface_count": len(REPORT_SURFACES),
            "final_recommendation": "trusted_loop_ready_for_operator_review_not_execution",
            "operator_summary": (
                "Roadmap A-E trusted-loop scaffolds and report surfaces are present as "
                "deterministic, read-only/context-only diagnostics. The system is ready "
                "for operator review of research-loop evidence, not for paper/shadow/live "
                "or broker/risk/execution activation."
            ),
        },
        "capabilities": list(CAPABILITY_ROWS),
        "report_surfaces": list(REPORT_SURFACES),
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
    return "\n".join(
        [
            "# QRE Trusted Loop Review Packet",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- trusted_loop_review_ready: {summary.get('trusted_loop_review_ready')}",
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