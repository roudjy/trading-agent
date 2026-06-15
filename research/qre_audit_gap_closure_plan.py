"""Deterministic QRE audit gap closure plan.

This module materializes the PR0 roadmap artifact for closing the current
QRE audit gaps. It is intentionally static, read-only, and planning-only:
it does not fetch data, launch campaigns, synthesize strategies, or mutate
research outputs.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_audit_gap_closure_plan"
SCHEMA_VERSION: Final[str] = "1.0"
GENERATED_AT_UTC: Final[str] = "2026-06-15T00:00:00Z"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_audit_gap_closure_plan")
DOC_PATH: Final[Path] = Path("docs/roadmap/qre_audit_gap_closure_plan.md")
LATEST_NAME: Final[str] = "latest.json"
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_audit_gap_closure_plan/",
    "docs/roadmap/qre_audit_gap_closure_plan.md",
)


AUDIT_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "id": 1,
        "audit_item": "PIT/report-lag/restatement",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": [
            "research/data_readiness/*policy.py",
            "tests for restatement policy",
        ],
        "target_capability": "multi-source historical accounting engine",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [2, 8, 18],
    },
    {
        "id": 2,
        "audit_item": "Factor field coverage",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["factor_field_coverage.py", "factor coverage tests"],
        "target_capability": "approved-provider factor coverage matrix",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [4, 5, 8, 18],
    },
    {
        "id": 3,
        "audit_item": "SEC Companyfacts manifest",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["source manifest registry/tests"],
        "target_capability": "active read-only SEC source candidate with gates",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [1, 5, 7],
    },
    {
        "id": 4,
        "audit_item": "OpenFIGI identity manifest",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["OpenFIGI tests", "identity modules"],
        "target_capability": "production-grade symbology resolver input",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [1, 3, 5, 10],
    },
    {
        "id": 5,
        "audit_item": "Grid lineage bridge",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_grid_candidate_campaign_lineage_bridge.py"],
        "target_capability": "source to hypothesis to campaign to evidence graph",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 9, 17, 18],
    },
    {
        "id": 6,
        "audit_item": "Source/cache sidecars",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_source_cache_readiness_materialization.py"],
        "target_capability": "deterministic sidecar materialization",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [1, 6, 8, 18],
    },
    {
        "id": 7,
        "audit_item": "Local grid refresh",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_local_grid_artifact_refresh.py"],
        "target_capability": "controlled refresh discipline",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [6, 8],
    },
    {
        "id": 8,
        "audit_item": "Targeted readiness rerun",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_targeted_readiness_rerun.py"],
        "target_capability": "real-data readiness rerun gate",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 15, 16, 18],
    },
    {
        "id": 9,
        "audit_item": "Candidate blockers",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_candidate_explanation_rows.py"],
        "target_capability": "high-density actionable blockers",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 17, 18],
    },
    {
        "id": 10,
        "audit_item": "Basket closure",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_evidence_complete_basket_closure.py"],
        "target_capability": "evidence-complete closure gate",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 17, 18],
    },
    {
        "id": 11,
        "audit_item": "Research memory",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": [
            "research/qre_research_memory_current_artifacts.py",
            "packages/qre_research/*",
        ],
        "target_capability": "graph-backed research memory",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [9, 11, 18],
    },
    {
        "id": 12,
        "audit_item": "Ontology",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_research_ontology.py"],
        "target_capability": "mature canonical ontology",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [9, 10, 11],
    },
    {
        "id": 13,
        "audit_item": "Entity resolution",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_entity_resolution.py"],
        "target_capability": "canonical identity resolution",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [3, 9, 10, 18],
    },
    {
        "id": 14,
        "audit_item": "Related failure retrieval",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["memory/retrieval tests"],
        "target_capability": "deterministic RRF/hybrid retrieval",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [9, 11, 17, 18],
    },
    {
        "id": 15,
        "audit_item": "Null model baseline",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_null_model_baseline.py"],
        "target_capability": "broader no-edge baseline suite",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [12, 13, 14, 18],
    },
    {
        "id": 16,
        "audit_item": "State transitions",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_state_transition_diagnostics.py"],
        "target_capability": "state/sequence/regime-duration diagnostics",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [12, 13],
    },
    {
        "id": 17,
        "audit_item": "Tail/entropy",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_tail_entropy_hardening.py"],
        "target_capability": "evidence-dense tail/entropy diagnostics",
        "target_maturity": "WORKING_CAPABILITY",
        "closure_prs": [12, 14],
    },
    {
        "id": 18,
        "audit_item": "Routing calibration",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_routing_calibration.py"],
        "target_capability": "real-evidence routing calibration",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 12, 13, 14, 15, 18],
    },
    {
        "id": 19,
        "audit_item": "Sampling calibration",
        "current_maturity": "SCAFFOLD",
        "repo_evidence": ["research/qre_sampling_calibration.py"],
        "target_capability": "real-evidence sampling calibration",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [8, 12, 13, 14, 16, 18],
    },
    {
        "id": 20,
        "audit_item": "Trusted-loop packet",
        "current_maturity": "WORKING_CAPABILITY",
        "repo_evidence": ["research/qre_trusted_loop_review_packet.py"],
        "target_capability": "evidence-backed operator-trust verdict",
        "target_maturity": "OPERATOR_TRUSTED",
        "closure_prs": [17, 18],
    },
)


GAP_CLOSURE_PRS: tuple[dict[str, Any], ...] = (
    {
        "pr": 0,
        "title": "Audit gap closure plan and maturity matrix",
        "objective": "Add generated roadmap artifact aligned with repo inspection.",
        "depends_on": [],
        "main_artifacts_tests": [
            "docs/roadmap/qre_audit_gap_closure_plan.md",
            "research/qre_audit_gap_closure_plan.py",
            "logs/qre_audit_gap_closure_plan/latest.json",
            "tests/unit/test_qre_audit_gap_closure_plan.py",
        ],
        "risk": "Low",
        "approval": "normal PR",
    },
    {
        "pr": 1,
        "title": "Source lifecycle and quality gate contract",
        "objective": "Implement strict source lifecycle and transition gates.",
        "depends_on": [0],
        "main_artifacts_tests": [
            "source lifecycle sidecar",
            "tests blocking candidate to active_read_only jumps",
        ],
        "required_gates": [
            "manifest_completeness",
            "allowed_use_declared",
            "forbidden_use_declared",
            "quality_gates_passed",
            "identity_mapping_present",
            "historical_lineage_present",
        ],
        "risk": "Medium",
        "approval": "operator review for lifecycle semantics",
    },
    {
        "pr": 2,
        "title": "Historical accounting foundation",
        "objective": "PIT/report-lag/restatement snapshot contracts.",
        "depends_on": [1],
        "main_artifacts_tests": ["accounting sidecar", "stale/revised detection tests"],
        "risk": "Medium",
        "approval": "operator review",
    },
    {
        "pr": 3,
        "title": "Symbology resolver foundation",
        "objective": "Canonical IDs, aliases, and ambiguity blocking.",
        "depends_on": [1],
        "main_artifacts_tests": ["identity sidecar", "ambiguity blocks escalation tests"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 4,
        "title": "Factor coverage matrix",
        "objective": "Provider to field to factor coverage and freshness.",
        "depends_on": [1, 2, 3],
        "main_artifacts_tests": [
            "factor coverage report",
            "tests no provider as alpha authority",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 5,
        "title": "SEC/OpenFIGI manifest hardening",
        "objective": "Promote manifests to quality-gated readiness inputs, not alpha.",
        "depends_on": [1, 2, 3, 4],
        "main_artifacts_tests": [
            "manifest completeness reports",
            "license/allowed-use tests",
        ],
        "risk": "Medium",
        "approval": "operator source review",
    },
    {
        "pr": 6,
        "title": "Cache and throughput manifests",
        "objective": "Parquet snapshot contract, DuckDB catalog manifest, Polars-use policy.",
        "depends_on": [1, 2, 3, 4, 5],
        "main_artifacts_tests": [
            "cache quality/coverage reports",
            "tests throughput cannot skip gates",
        ],
        "required_gates": ["source_quality_ready", "cache_manifest_ready"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 7,
        "title": "Source usefulness ledger",
        "objective": "Track source usefulness, failures, and cost savings.",
        "depends_on": [5, 6],
        "main_artifacts_tests": [
            "usefulness ledger",
            "false-positive and quality-failure tests",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 8,
        "title": "Lineage graph v1",
        "objective": "Source to normalized data to factor to hypothesis to campaign to evidence lineage.",
        "depends_on": [2, 3, 4, 5, 6, 7],
        "main_artifacts_tests": ["deterministic graph JSON", "orphan/contradiction tests"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 9,
        "title": "Knowledge graph and contradiction visibility",
        "objective": "Add research memory graph and contradiction edges.",
        "depends_on": [8],
        "main_artifacts_tests": ["KG sidecar", "tests graph is context not truth"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 10,
        "title": "Entity resolution hardening",
        "objective": "Canonical cross-artifact entity resolver.",
        "depends_on": [3, 9],
        "main_artifacts_tests": ["canonical ID report", "ambiguity blocks escalation tests"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 11,
        "title": "Retrieval maturity",
        "objective": "Keyword plus metadata plus graph-neighbor retrieval with RRF scaffold.",
        "depends_on": [9, 10],
        "main_artifacts_tests": ["retrieval quality report", "tests retrieval is context only"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 12,
        "title": "Null/no-edge baseline suite",
        "objective": "Random walk, shuffled/surrogate, martingale-like baseline reports.",
        "depends_on": [8, 11],
        "main_artifacts_tests": [
            "baseline sidecars",
            "tests no baseline promotes candidates alone",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 13,
        "title": "State/sequence/regime duration",
        "objective": "State transition and dwell-time diagnostics.",
        "depends_on": [12],
        "main_artifacts_tests": ["state/regime reports", "sparse data fail-closed tests"],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 14,
        "title": "Tail/entropy evidence density",
        "objective": "Expand diagnostics with real evidence density and null challenges.",
        "depends_on": [12, 13],
        "main_artifacts_tests": [
            "tail/entropy report",
            "tests diagnostics do not trade",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 15,
        "title": "Routing calibration on real evidence",
        "objective": "Use source/data/readiness/diagnostic evidence for routing recommendations.",
        "depends_on": [8, 9, 10, 11, 12, 13, 14],
        "main_artifacts_tests": [
            "routing calibration report",
            "tests no queue/campaign mutation",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 16,
        "title": "Sampling calibration on real evidence",
        "objective": "Coverage/source/null/regime-aware sampling recommendations.",
        "depends_on": [8, 9, 10, 11, 12, 13, 14, 15],
        "main_artifacts_tests": [
            "sampling report",
            "tests no stochastic/bruteforce shortcut",
        ],
        "risk": "Medium",
        "approval": "normal PR",
    },
    {
        "pr": 17,
        "title": "Evidence-complete basket closure",
        "objective": "High-density blockers, reason records, and closure criteria.",
        "depends_on": [8, 9, 10, 11, 12, 13, 14, 15, 16],
        "main_artifacts_tests": [
            "basket closure packet",
            "tests negative results preserved",
        ],
        "risk": "Medium",
        "approval": "operator review",
    },
    {
        "pr": 18,
        "title": "Operator-trust review packet v3",
        "objective": "Evidence-backed Level 1/2/3 verdict and exact next action.",
        "depends_on": [17],
        "main_artifacts_tests": [
            "final trust packet",
            "tests missing evidence fails closed",
        ],
        "risk": "Low",
        "approval": "operator trust decision",
    },
)


DEPENDENCIES: tuple[dict[str, str], ...] = (
    {
        "dependency": "source_lifecycle_before_active_sources",
        "rule": "Source lifecycle and quality gates must pass before active read-only source usage.",
    },
    {
        "dependency": "symbology_before_factor_agreement",
        "rule": "Symbology resolver must exist before broad factor coverage and cross-source agreement.",
    },
    {
        "dependency": "historical_accounting_before_pit_factors",
        "rule": "Historical accounting must exist before PIT-aware factor evaluation.",
    },
    {
        "dependency": "cache_manifest_before_throughput_metrics",
        "rule": "Cache manifest must exist before throughput metrics.",
    },
    {
        "dependency": "usefulness_after_quality_and_cache",
        "rule": "Source usefulness ledger follows source quality and cache manifests.",
    },
    {
        "dependency": "lineage_before_trust_packet",
        "rule": "Lineage graph must precede contradiction visibility and operator-trust packet.",
    },
    {
        "dependency": "entity_resolution_before_retrieval_confidence",
        "rule": "Entity resolution must precede mature retrieval and lineage confidence.",
    },
    {
        "dependency": "null_baselines_before_diagnostic_influence",
        "rule": "Null baselines must precede state/tail/entropy influence on routing or sampling.",
    },
    {
        "dependency": "real_evidence_before_operator_trusted_calibration",
        "rule": "Real evidence runs must precede operator-trusted routing or sampling calibration.",
    },
    {
        "dependency": "reason_density_before_final_verdict",
        "rule": "Reason-record density and basket closure must precede final operator-trust verdict.",
    },
)


BLOCKED_SHORTCUTS: tuple[str, ...] = (
    "source_to_alpha",
    "cache_to_trade",
    "diagnostic_to_trade",
    "retrieval_to_authority",
    "knowledge_graph_to_truth",
    "identity_ambiguity_to_escalation",
    "throughput_bypasses_source_quality",
    "null_baseline_promotes_candidate_alone",
    "routing_mutates_queue_or_campaign",
    "sampling_uses_stochastic_bruteforce",
)

FORBIDDEN_PATHS: tuple[str, ...] = (
    "strategy_synthesis",
    "shadow_activation",
    "paper_activation",
    "live_activation",
    "broker_integration",
    "risk_authority",
    "execution_behavior",
    "dashboard_mutation_routes",
    "hidden_ml_rl_selectors",
    "stochastic_mutation",
    "generated_strategy_code",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_audit_gap_closure_plan(
    *,
    generated_at_utc: str = GENERATED_AT_UTC,
) -> dict[str, Any]:
    current_counts = Counter(str(row["current_maturity"]) for row in AUDIT_ITEMS)
    target_counts = Counter(str(row["target_maturity"]) for row in AUDIT_ITEMS)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "audit_items": [dict(row) for row in AUDIT_ITEMS],
        "current_maturity": dict(sorted(current_counts.items())),
        "target_maturity": dict(sorted(target_counts.items())),
        "gap_closure_prs": [dict(row) for row in GAP_CLOSURE_PRS],
        "dependencies": [dict(row) for row in DEPENDENCIES],
        "blocked_shortcuts": list(BLOCKED_SHORTCUTS),
        "forbidden_paths": list(FORBIDDEN_PATHS),
        "safe_to_strategy_synthesis": False,
        "safe_to_shadow": False,
        "safe_to_paper": False,
        "safe_to_live": False,
        "summary": {
            "audit_item_count": len(AUDIT_ITEMS),
            "gap_closure_pr_count": len(GAP_CLOSURE_PRS),
            "operator_summary": (
                "PR0 records the audit gap closure roadmap only. It keeps QRE in "
                "research-only planning mode and does not unlock strategy synthesis, "
                "paper, shadow, live, broker, risk, or execution behavior."
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "fetches_external_data": False,
            "runs_research": False,
            "launches_campaigns": False,
            "mutates_candidates": False,
            "mutates_campaigns": False,
            "mutates_strategies": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "operator_review_only": True,
        },
    }


def render_markdown(plan: Mapping[str, Any]) -> str:
    audit_items = plan.get("audit_items")
    audit_items = audit_items if isinstance(audit_items, list) else []
    prs = plan.get("gap_closure_prs")
    prs = prs if isinstance(prs, list) else []
    dependencies = plan.get("dependencies")
    dependencies = dependencies if isinstance(dependencies, list) else []

    audit_table = _table(
        [
            "#",
            "Audit item",
            "Current maturity",
            "Target maturity",
            "Closure PRs",
            "Target capability",
        ],
        [
            [
                str(row.get("id") or ""),
                str(row.get("audit_item") or ""),
                str(row.get("current_maturity") or ""),
                str(row.get("target_maturity") or ""),
                ", ".join(f"PR{value}" for value in row.get("closure_prs", [])),
                str(row.get("target_capability") or ""),
            ]
            for row in audit_items
            if isinstance(row, Mapping)
        ],
    )
    pr_table = _table(
        ["PR", "Title", "Objective", "Depends on", "Approval"],
        [
            [
                f"PR{row.get('pr')}",
                str(row.get("title") or ""),
                str(row.get("objective") or ""),
                ", ".join(f"PR{value}" for value in row.get("depends_on", [])) or "none",
                str(row.get("approval") or ""),
            ]
            for row in prs
            if isinstance(row, Mapping)
        ],
    )
    dependency_lines = [
        f"- {row.get('dependency')}: {row.get('rule')}"
        for row in dependencies
        if isinstance(row, Mapping)
    ]
    blocked_lines = [f"- {value}" for value in plan.get("blocked_shortcuts", [])]
    forbidden_lines = [f"- {value}" for value in plan.get("forbidden_paths", [])]

    return "\n".join(
        [
            "# QRE Audit Gap Closure Plan",
            "",
            f"Generated at UTC: `{plan.get('generated_at_utc')}`",
            "",
            "## Summary",
            "",
            str((plan.get("summary") or {}).get("operator_summary") or ""),
            "",
            "This artifact is PR0 of the roadmap. It is a deterministic, read-only "
            "planning surface and is not evidence that QRE is operator-trusted.",
            "",
            "## Current-To-Target Matrix",
            "",
            audit_table,
            "",
            "## PR Sequence",
            "",
            pr_table,
            "",
            "## Dependency Graph",
            "",
            *dependency_lines,
            "",
            "## Blocked Shortcuts",
            "",
            *blocked_lines,
            "",
            "## Forbidden Paths",
            "",
            *forbidden_lines,
            "",
            "## Safety Flags",
            "",
            f"- safe_to_strategy_synthesis: {plan.get('safe_to_strategy_synthesis')}",
            f"- safe_to_shadow: {plan.get('safe_to_shadow')}",
            f"- safe_to_paper: {plan.get('safe_to_paper')}",
            f"- safe_to_live: {plan.get('safe_to_live')}",
            "",
            "## Recommended Next PR",
            "",
            "After PR0, build PR1: `feat: add QRE source lifecycle and quality gate contract`.",
            "",
            "Reason: source lifecycle and quality gates are the dependency root for "
            "approved providers, symbology, factor coverage, PIT accounting, cache "
            "trust, routing/sampling evidence, and final operator trust.",
        ]
    )


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(f"qre_audit_gap_closure_plan: refusing write outside allowlist: {path!r}")


def write_outputs(
    plan: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    latest = repo_root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    doc = repo_root / DOC_PATH
    for target in (latest, doc):
        _validate_write_target(target)
        target.parent.mkdir(parents=True, exist_ok=True)

    latest_payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_doc = doc.with_suffix(doc.suffix + ".tmp")
    tmp_doc.write_text(render_markdown(plan) + "\n", encoding="utf-8")
    os.replace(tmp_doc, doc)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_plan": doc.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_audit_gap_closure_plan",
        description="Materialize the deterministic QRE audit gap closure plan.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    plan = build_audit_gap_closure_plan()
    if args.write:
        plan["_artifact_paths"] = write_outputs(plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
