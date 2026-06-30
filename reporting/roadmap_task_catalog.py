"""A20a — Static Roadmap v6 Task Catalog Seed (read-only, deterministic).

Pure, stdlib-only, repo-resident task-catalog **seed**. Hand-encodes the
Roadmap v6 phase tasks (v3.15.16 through v3.15.20) plus a cross-cutting
Addendum 1 task, and the per-requirement Addendum 1 diagnostic coverage,
into a deterministic projection emitted at
``logs/roadmap_task_catalog/latest.json``.

This module is a **catalog**, not a queue. It does not:

* mutate the canonical roadmap documents;
* mutate frozen contracts;
* promote anything into ``docs/development_work_queue/seed.jsonl`` or
  ``docs/development_work_queue/delegation_seed.jsonl``;
* select a next-buildable unit (A20e scope);
* decompose phases into PR-sized implementation units (A20b scope);
* call ``execution_authority.classify(...)`` for risk/authority mapping
  (A20c scope);
* surface anything to the AAC / task board / dashboard (A20d scope);
* enable or hint at Step 5 substages or autonomy-ladder Level 6;
* grant trading, paper, shadow, broker, risk, or live execution
  authority to any agent.

Roadmap v6 remains canonical for product. Roadmap v6 Addendum is the
diagnostic / external-intelligence extension. Roadmap v6 Addendum 2
and Addendum 3 are **not in the repo** at the time of this seed and
are represented only as absence flags on the projection. They must
not be invented here.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` (read-only constants
  only — no ``classify(...)`` calls in this PR).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``.
* No LLM, no external API, no fuzzy parsing.
* Closed vocabularies for ``PHASE``, ``SOURCE_DOCUMENT``, ``STATUS``,
  ``ADDENDUM_LINK``, ``TARGET_LAYER``. Widening any of them requires
  a code change pinned by an updated unit test.
* Atomic write only under ``logs/roadmap_task_catalog/``.
* Deterministic output: same input + injected ``generated_at_utc`` →
  byte-identical artefact across runs.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

CLI::

    python -m reporting.roadmap_task_catalog
    python -m reporting.roadmap_task_catalog --no-write
    python -m reporting.roadmap_task_catalog --status
    python -m reporting.roadmap_task_catalog --indent 2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20a+A23"
REPORT_KIND: Final[str] = "roadmap_task_catalog"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

#: Closed Step 5 sub-stage cap. Mirrors the value asserted across the
#: ADE-core reporting modules. Default-deny: ``"none"`` means this
#: catalog does not escalate any phase.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Hard-pinned literal: Step 5 implementation remains BLOCKED.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed roadmap-phase vocabulary. Addendum 2 / Addendum 3 are listed
#: so consumers can carry their phase identity, but neither has a file
#: committed to the repo at the time of this seed; their requirements
#: remain empty and absence flags are emitted on every projection.
PHASE: Final[tuple[str, ...]] = (
    "ade_qre_017a",
    "ade_qre_017b",
    "ade_qre_017c",
    "ade_qre_017d",
    "ade_qre_017e",
    "ade_qre_018a",
    "ade_qre_018b",
    "ade_qre_018c",
    "ade_qre_018d",
    "ade_qre_018e",
    "ade_qre_018f",
    "ade_qre_018g",
    "ade_qre_018h",
    "ade_qre_018i",
    "ade_qre_018j",
    "ade_qre_018k",
    "ade_qre_019a",
    "ade_qre_019b",
    "ade_qre_019c",
    "ade_qre_019d",
    "ade_qre_019e",
    "ade_qre_019f",
    "ade_qre_019g",
    "ade_qre_019h",
    "ade_qre_019i",
    "ade_qre_019j",
    "ade_qre_019k",
    "ade_qre_019l",
    "ade_qre_019m",
    "ade_qre_020a",
    "ade_qre_020b",
    "ade_qre_020c",
    "ade_qre_020d",
    "ade_qre_020e",
    "ade_qre_020f",
    "ade_qre_020g",
    "ade_qre_020h",
    "ade_qre_020i",
    "ade_qre_020j",
    "ade_qre_020k",
    "ade_qre_020l",
    "ade_qre_020m",
    "ade_qre_020n",
    "ade_qre_020o",
    "ade_qre_020p",
    "ade_qre_020q",
    "ade_qre_021a",
    "ade_qre_021b",
    "ade_qre_021c",
    "ade_qre_021d",
    "ade_qre_021e",
    "ade_qre_021f",
    "ade_qre_021g",
    "ade_qre_021h",
    "ade_qre_021i",
    "ade_qre_021j",
    "ade_qre_021k",
    "ade_qre_021l",
    "ade_qre_021m",
    "ade_qre_021n",
    "ade_qre_021o",
    "ade_qre_022a",
    "ade_qre_022b",
    "ade_qre_022c",
    "ade_qre_022d",
    "ade_qre_022e",
    "ade_qre_022f",
    "ade_qre_022g",
    "ade_qre_022h",
    "ade_qre_022i",
    "ade_qre_022j",
    "ade_qre_022k",
    "ade_qre_022l",
    "ade_qre_022m",
    "ade_qre_022n",
    "ade_qre_022o",
    "ade_qre_023a",
    "ade_qre_023b",
    "ade_qre_023c",
    "ade_qre_023d",
    "ade_qre_023e",
    "ade_qre_023f",
    "ade_qre_023g",
    "ade_qre_023h",
    "ade_qre_023i",
    "ade_qre_023j",
    "ade_qre_023k",
    "ade_qre_023l",
    "ade_qre_023m",
    "ade_qre_023n",
    "ade_qre_023o",
    "ade_qre_023p",
    "ade_qre_024a",
    "ade_qre_024b",
    "ade_qre_024c",
    "ade_qre_024d",
    "ade_qre_024e",
    "ade_qre_024f",
    "ade_qre_024g",
    "ade_qre_024h",
    "ade_qre_024i",
    "ade_qre_024j",
    "ade_qre_024k",
    "ade_qre_024l",
    "ade_qre_024m",
    "ade_qre_024n",
    "ade_qre_024o",
    "ade_qre_024p",
    "ade_qre_025a",
    "ade_qre_025b",
    "ade_qre_025c",
    "ade_qre_025d",
    "ade_qre_025e",
    "ade_qre_025f",
    "ade_qre_025g",
    "ade_qre_025h",
    "ade_qre_025i",
    "ade_qre_025j",
    "ade_qre_025k",
    "ade_qre_025l",
    "ade_qre_025m",
    "ade_qre_025n",
    "ade_qre_025o",
    "ade_qre_026a",
    "ade_qre_026b",
    "ade_qre_026c",
    "ade_qre_026d",
    "ade_qre_026e",
    "ade_qre_026f",
    "ade_qre_026g",
    "ade_qre_026h",
    "ade_qre_026i",
    "ade_qre_026j",
    "ade_qre_026k",
    "ade_qre_026l",
    "ade_qre_026m",
    "ade_qre_026n",
    "ade_qre_026o",
    "ade_qre_026p",
    "ade_qre_026q",
    "ade_qre_026r",
    "v3.15.16",
    "v3.15.17",
    "v3.15.18",
    "v3.15.19",
    "v3.15.20",
    "addendum_1",
    "addendum_2",
    "addendum_3",
)

#: Closed source-document vocabulary. Roadmap v6 + Addendum 1/2/3
#: are now all repo-resident. A23 added the operator-provided
#: Addendum 2 and Addendum 3 verbatim into ``docs/roadmap/``; their
#: file paths are pinned here.
SOURCE_DOCUMENT: Final[tuple[str, ...]] = (
    "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
    "docs/roadmap/qre_maturity_roadmap_to_100.md",
    "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
    "docs/roadmap/qre_automated_strategy_generation_program.md",
    "docs/roadmap/qre_automated_hypothesis_generation_program.md",
    "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
    "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
    "docs/roadmap/qre_autonomous_readiness_closure_program.md",
    "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
    "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
    "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
    "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
    "docs/governance/qre_synthesis_readiness_review.md",
    "docs/roadmap/Roadmap v6.md",
    "docs/roadmap/Roadmap v6 Addendum.md",
    (
        "docs/roadmap/Roadmap v6 Addendum 2 - "
        "State Sequential Knowledge Retrieval.md"
    ),
    (
        "docs/roadmap/Roadmap v6 Addendum 3 - "
        "Source Identity Data Quality and Throughput Intelligence.md"
    ),
    "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
    "docs/roadmap/qre_roadmap_v6_phase_prompts.md",
)

#: Closed task / requirement status vocabulary. Today every entry
#: lands in ``not_started`` — the catalog records intent, not
#: in-flight or completed work. Future projections (A20b / A20c) may
#: lift records to other values; this seed never does.
STATUS: Final[tuple[str, ...]] = (
    "not_started",
    "ready",
    "in_flight",
    "merged",
    "blocked",
    "human_needed",
    "permanently_denied",
)

#: Closed addendum-link vocabulary. ``"none"`` is the explicit value
#: for "no addendum link" so the field is never silently missing.
ADDENDUM_LINK: Final[tuple[str, ...]] = (
    "addendum_1",
    "addendum_2",
    "addendum_3",
    "none",
)

#: Closed target-layer vocabulary. Mirrors the Addendum 1 architecture
#: stack plus the ADE-side surfaces this catalog can describe without
#: pretending to govern runtime/trading behaviour.
TARGET_LAYER: Final[tuple[str, ...]] = (
    "external_intelligence",
    "diagnostics",
    "market_behavior",
    "hypothesis_discovery",
    "strategy_mapping",
    "preset",
    "campaign",
    "funnel",
    "evidence",
    "policy",
    "shadow",
    "paper",
    "live",
    "reporting",
    "governance",
    "docs",
    "test",
)


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: ``RoadmapTask`` field list. Exact and ordered.
ROADMAP_TASK_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "title",
    "phase",
    "source_documents",
    "purpose",
    "status",
    "prerequisites",
)

#: ``RoadmapRequirement`` field list. Exact and ordered.
ROADMAP_REQUIREMENT_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "roadmap_task_id",
    "source_document",
    "source_anchor",
    "phase",
    "addendum_link",
    "statement",
    "target_layer",
    "status",
)

#: ``TaskCatalogProjection`` field list. Exact and ordered.
TASK_CATALOG_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "roadmap_tasks",
    "roadmap_requirements",
    "discipline_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_TITLE_LEN: Final[int] = 200
MAX_PURPOSE_LEN: Final[int] = 1000
MAX_STATEMENT_LEN: Final[int] = 500
MAX_ID_LEN: Final[int] = 96
MAX_ANCHOR_LEN: Final[int] = 200


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_task_catalog"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/roadmap_task_catalog/latest.json"

#: Atomic-write allowlist (POSIX path substring form). Any write
#: target whose path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_task_catalog/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted on every projection
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool]] = {
    "actually_modifies_target": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "mergeable_by_agent": False,
    "deployable_by_agent": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "diagnostics_do_not_trade": True,
    "external_data_is_not_alpha": True,
    # A23 made Addendum 2 + 3 repo-resident; absence flags flip
    # from True to False. The catalog now encodes tasks /
    # requirements derived verbatim from the operator-provided
    # canonical files in ``docs/roadmap/``.
    "addendum_2_not_present": False,
    "addendum_3_not_present": False,
    "grants_runtime_authority": False,
    "grants_trading_authority": False,
    "grants_paper_authority": False,
    "grants_shadow_authority": False,
    "grants_broker_authority": False,
    "grants_risk_authority": False,
    "grants_live_authority": False,
}


# ---------------------------------------------------------------------------
# Hand-encoded RoadmapTask seed data
# ---------------------------------------------------------------------------

#: One entry per Roadmap v6 phase v3.15.16..20, plus a cross-cutting
#: ``addendum_1`` task. Order matches ``PHASE`` declaration order;
#: ``sort`` at projection time keeps the artefact stable regardless.
_ROADMAP_TASKS_SEED: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "ade_qre_017a_baseline_reconciliation",
        "title": "ADE-QRE-017A Baseline Reconciliation and Maturity Matrix",
        "phase": "ade_qre_017a",
        "source_documents": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "docs/roadmap/qre_maturity_roadmap_to_100.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Establish a repository-backed baseline reconciliation for the "
            "trusted research intelligence program. Classify relevant QRE "
            "capabilities by maturity, count current evidence-bearing "
            "surfaces, and make blockers explicit without inferring trust "
            "from scaffold presence alone."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    {
        "id": "ade_qre_017b_evidence_density_population",
        "title": "ADE-QRE-017B Evidence-Density Population Plan",
        "phase": "ade_qre_017b",
        "source_documents": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Inventory required evidence classes, their producers and "
            "consumers, and the population gaps that currently block "
            "repeatable research decisions. Fail-closed blockers must be "
            "named explicitly."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_017a_baseline_reconciliation",),
    },
    {
        "id": "ade_qre_017c_reason_record_maturity",
        "title": "ADE-QRE-017C Reason-Record Maturity",
        "phase": "ade_qre_017c",
        "source_documents": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Make reason records durable, normalized, and evidence-linked "
            "when real evidence exists. Missing evidence must fail closed; "
            "the program may not synthesize reasons or evidence."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_017b_evidence_density_population",),
    },
    {
        "id": "ade_qre_017d_routing_sampling_readiness",
        "title": "ADE-QRE-017D Routing and Sampling Readiness Population",
        "phase": "ade_qre_017d",
        "source_documents": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Promote routing-ready and sampling-ready signals from scaffold "
            "status to repository-backed readiness based on actual evidence. "
            "Readiness may not be inferred from module existence alone."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_017c_reason_record_maturity",),
    },
    {
        "id": "ade_qre_017e_kpi_snapshot_completeness",
        "title": "ADE-QRE-017E KPI Completeness and Historical Snapshots",
        "phase": "ade_qre_017e",
        "source_documents": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Materialize KPI completeness with numeric values or explicit "
            "unavailability, and produce repeatable historical snapshots "
            "that preserve evidence state over time."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_017d_routing_sampling_readiness",),
    },
    {
        "id": "ade_qre_018a_historical_queue_baseline_reconciliation",
        "title": "ADE-QRE-018A Historical Queue and Baseline Reconciliation",
        "phase": "ade_qre_018a",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "docs/governance/qre_synthesis_readiness_review.md",
        ),
        "purpose": (
            "Classify historical queue ambiguity without hiding it, "
            "preserve audit history, and establish a deterministic "
            "post-ADE-QRE-017 remediation baseline."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    {
        "id": "ade_qre_018b_blocked_thesis_lineage_census",
        "title": "ADE-QRE-018B Blocked-Thesis Lineage Census",
        "phase": "ade_qre_018b",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Materialize a deterministic lineage census for the six "
            "blocked theses and preserve fail-closed missing-link states."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018a_historical_queue_baseline_reconciliation",
        ),
    },
    {
        "id": "ade_qre_018c_identity_ambiguity_resolution",
        "title": "ADE-QRE-018C Identity Ambiguity Resolution",
        "phase": "ade_qre_018c",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Resolve thesis, strategy, preset, source, instrument, "
            "dataset, snapshot, campaign, and evidence identities "
            "where authoritative repository evidence exists."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_018b_blocked_thesis_lineage_census",),
    },
    {
        "id": "ade_qre_018d_campaign_lineage_materialization",
        "title": "ADE-QRE-018D Campaign Lineage Materialization",
        "phase": "ade_qre_018d",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Materialize bounded thesis-to-campaign lineage only where "
            "strategy, preset, data, and identity evidence actually support it."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_018c_identity_ambiguity_resolution",),
    },
    {
        "id": "ade_qre_018e_null_control_specification_completeness",
        "title": "ADE-QRE-018E Null-Control Specification and Completeness",
        "phase": "ade_qre_018e",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Specify mechanistically appropriate null controls and record "
            "completeness or blockers without fabricating empirical outcomes."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018d_campaign_lineage_materialization",
        ),
    },
    {
        "id": "ade_qre_018f_evidence_reason_record_completion",
        "title": "ADE-QRE-018F Evidence and Reason-Record Completion",
        "phase": "ade_qre_018f",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Complete reason-record and evidence-completeness reporting "
            "where authoritative evidence exists and fail closed elsewhere."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018e_null_control_specification_completeness",
        ),
    },
    {
        "id": "ade_qre_018g_validation_repro_operator_completion",
        "title": "ADE-QRE-018G Validation, Reproducibility and Operator-Report Completion",
        "phase": "ade_qre_018g",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Consolidate validation, reproducibility, freshness, and "
            "operator-report readiness from the remediated evidence chain."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_018f_evidence_reason_record_completion",),
    },
    {
        "id": "ade_qre_018h_campaign_ready_portfolio_reconstruction",
        "title": "ADE-QRE-018H Campaign-Ready Portfolio Reconstruction",
        "phase": "ade_qre_018h",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Rebuild a fail-closed portfolio from the remediated artifacts "
            "and preserve blocked, rejected, duplicate, and dead-zone states."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018g_validation_repro_operator_completion",
        ),
    },
    {
        "id": "ade_qre_018i_replacement_hypothesis_planning",
        "title": "ADE-QRE-018I Replacement Hypothesis Planning",
        "phase": "ade_qre_018i",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Archive trend_pullback_v1 as rejected and propose one "
            "genuinely distinct replacement thesis via deterministic "
            "discovery machinery."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018h_campaign_ready_portfolio_reconstruction",
        ),
    },
    {
        "id": "ade_qre_018j_second_broad_preregistered_campaign",
        "title": "ADE-QRE-018J Second Broad Preregistered Campaign",
        "phase": "ade_qre_018j",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Prepare and execute a second preregistered campaign only "
            "after genuinely ready cells and a canonically accepted "
            "preregistered artifact exist."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018i_replacement_hypothesis_planning",
        ),
    },
    {
        "id": "ade_qre_018k_second_synthesis_readiness_review",
        "title": "ADE-QRE-018K Second Synthesis-Readiness Review",
        "phase": "ade_qre_018k",
        "source_documents": (
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "docs/governance/qre_synthesis_readiness_review.md",
        ),
        "purpose": (
            "Re-run synthesis-readiness only after the second campaign "
            "produces new authoritative evidence."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_018j_second_broad_preregistered_campaign",
        ),
    },
    {
        "id": "ade_qre_019a_generation_authority_governance",
        "title": "ADE-QRE-019A Governance and Research-Only Generation Authority",
        "phase": "ade_qre_019a",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Authorize the bounded ADE-QRE-019 research-only generation "
            "pipeline while preserving the .claude hook, protected "
            "research surfaces, and all deployment-denial safety boundaries."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    {
        "id": "ade_qre_019b_typed_strategy_specification_contract",
        "title": "ADE-QRE-019B Typed Strategy Specification Contract",
        "phase": "ade_qre_019b",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Define the closed, versioned, typed strategy specification "
            "that the generator compiles from approved behavior theses."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_019a_generation_authority_governance",),
    },
    {
        "id": "ade_qre_019c_thesis_to_specification_compiler",
        "title": "ADE-QRE-019C Thesis-to-Specification Compiler",
        "phase": "ade_qre_019c",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Compile eligible theses into typed strategy specifications "
            "using closed vocabularies and fail-closed policy gates."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019b_typed_strategy_specification_contract",
        ),
    },
    {
        "id": "ade_qre_019d_deterministic_executable_strategy_generator",
        "title": "ADE-QRE-019D Deterministic Executable Strategy Generator",
        "phase": "ade_qre_019d",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Render byte-identical research-only executable strategies "
            "from typed specifications into isolated generated surfaces."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019c_thesis_to_specification_compiler",
        ),
    },
    {
        "id": "ade_qre_019e_automated_test_generator",
        "title": "ADE-QRE-019E Automated Test Generator",
        "phase": "ade_qre_019e",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Generate deterministic contract and safety tests for every "
            "generated executable strategy."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019d_deterministic_executable_strategy_generator",
        ),
    },
    {
        "id": "ade_qre_019f_static_safety_architecture_gate",
        "title": "ADE-QRE-019F Static Safety and Architecture Gate",
        "phase": "ade_qre_019f",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Reject generated code that violates AST safety, import, "
            "integrity, or architecture constraints before execution."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019e_automated_test_generator",
        ),
    },
    {
        "id": "ade_qre_019g_isolated_sandbox_validation",
        "title": "ADE-QRE-019G Isolated Sandbox Validation",
        "phase": "ade_qre_019g",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Run generated strategies and their tests in isolated, "
            "deterministic technical validation without creating market evidence."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019f_static_safety_architecture_gate",
        ),
    },
    {
        "id": "ade_qre_019h_automatic_research_only_registration",
        "title": "ADE-QRE-019H Automatic Research-Only Registration",
        "phase": "ade_qre_019h",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Automatically admit validated generated strategies into a "
            "controlled generated registry with research-only authority."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019g_isolated_sandbox_validation",
        ),
    },
    {
        "id": "ade_qre_019i_automatic_bounded_preset_generation",
        "title": "ADE-QRE-019I Automatic Bounded Preset Generation",
        "phase": "ade_qre_019i",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Generate bounded deterministic research presets from admitted "
            "generated strategies without optimization or OOS-derived tuning."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019h_automatic_research_only_registration",
        ),
    },
    {
        "id": "ade_qre_019j_automatic_null_control_specification",
        "title": "ADE-QRE-019J Automatic Null-Control Specification",
        "phase": "ade_qre_019j",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Generate deterministic, mechanism-appropriate null-control "
            "specifications without claiming empirical completeness."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019i_automatic_bounded_preset_generation",
        ),
    },
    {
        "id": "ade_qre_019k_campaign_lineage_portfolio_integration",
        "title": "ADE-QRE-019K Campaign Lineage and Portfolio Integration",
        "phase": "ade_qre_019k",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Expose generated strategies through one resolved research-only "
            "catalog and integrate them into lineage and portfolio surfaces."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019j_automatic_null_control_specification",
        ),
    },
    {
        "id": "ade_qre_019l_apply_pipeline_to_blocked_theses",
        "title": "ADE-QRE-019L Apply Pipeline to Blocked Theses",
        "phase": "ade_qre_019l",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Run the bounded ADE-QRE-019 pipeline against the currently "
            "blocked theses and preserve correct fail-closed outcomes."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019k_campaign_lineage_portfolio_integration",
        ),
    },
    {
        "id": "ade_qre_019m_automated_generation_closeout",
        "title": "ADE-QRE-019M Automated Generation Closeout",
        "phase": "ade_qre_019m",
        "source_documents": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Produce the integrated ADE-QRE-019 closeout describing "
            "governance migration, generation outcomes, blockers, and next action."
        ),
        "status": "not_started",
        "prerequisites": (
            "ade_qre_019l_apply_pipeline_to_blocked_theses",
        ),
    },
    {
        "id": "ade_qre_020a_governance_and_hypothesis_authority",
        "title": "ADE-QRE-020A Governance and Hypothesis Authority",
        "phase": "ade_qre_020a",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Authorize bounded deterministic automated hypothesis generation, "
            "admission, prioritization, and ADE-QRE-019 submission without "
            "granting strategy-generation or trading authority."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    {
        "id": "ade_qre_020b_evidence_snapshot_and_opportunity_inputs",
        "title": "ADE-QRE-020B Evidence Snapshot and Opportunity Inputs",
        "phase": "ade_qre_020b",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": (
            "Freeze deterministic authoritative inputs for each automated "
            "hypothesis-generation run."
        ),
        "status": "not_started",
        "prerequisites": ("ade_qre_020a_governance_and_hypothesis_authority",),
    },
    {
        "id": "ade_qre_020c_research_opportunity_detector",
        "title": "ADE-QRE-020C Research Opportunity Detector",
        "phase": "ade_qre_020c",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Detect closed-vocabulary research opportunities from authoritative evidence.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020b_evidence_snapshot_and_opportunity_inputs",),
    },
    {
        "id": "ade_qre_020d_market_observation_builder",
        "title": "ADE-QRE-020D Market Observation Builder",
        "phase": "ade_qre_020d",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Build descriptive observations separate from hypotheses and strategy logic.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020c_research_opportunity_detector",),
    },
    {
        "id": "ade_qre_020e_closed_mechanism_proposal_engine",
        "title": "ADE-QRE-020E Closed Mechanism Proposal Engine",
        "phase": "ade_qre_020e",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Emit mechanism proposals from a closed causal vocabulary only.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020d_market_observation_builder",),
    },
    {
        "id": "ade_qre_020f_behavior_thesis_compiler",
        "title": "ADE-QRE-020F Behavior Thesis Compiler",
        "phase": "ade_qre_020f",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Compile typed falsifiable Behavior Thesis candidates from opportunities and mechanisms.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020e_closed_mechanism_proposal_engine",),
    },
    {
        "id": "ade_qre_020g_scientific_quality_and_falsifiability_gate",
        "title": "ADE-QRE-020G Scientific Quality and Falsifiability Gate",
        "phase": "ade_qre_020g",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Reject or block unfalsifiable, vague, or leakage-prone thesis candidates.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020f_behavior_thesis_compiler",),
    },
    {
        "id": "ade_qre_020h_novelty_and_rejected_lineage_gate",
        "title": "ADE-QRE-020H Novelty and Rejected-Lineage Gate",
        "phase": "ade_qre_020h",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Reject duplicates, cosmetic variants, and rejected-lineage matches.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020g_scientific_quality_and_falsifiability_gate",),
    },
    {
        "id": "ade_qre_020i_contradiction_and_alternative_explanation_engine",
        "title": "ADE-QRE-020I Contradiction and Alternative-Explanation Engine",
        "phase": "ade_qre_020i",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Retrieve supporting, contradicting, and alternative explanations for every candidate.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020h_novelty_and_rejected_lineage_gate",),
    },
    {
        "id": "ade_qre_020j_testability_and_signal_density_estimator",
        "title": "ADE-QRE-020J Testability and Signal-Density Estimator",
        "phase": "ade_qre_020j",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Estimate testability, window needs, OOS capacity, and compute cost as estimates only.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020i_contradiction_and_alternative_explanation_engine",),
    },
    {
        "id": "ade_qre_020k_primitive_compatibility_classifier",
        "title": "ADE-QRE-020K Primitive Compatibility Classifier",
        "phase": "ade_qre_020k",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Classify which admitted-quality theses can or cannot flow into ADE-QRE-019.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020j_testability_and_signal_density_estimator",),
    },
    {
        "id": "ade_qre_020l_automatic_thesis_admission_and_resolver",
        "title": "ADE-QRE-020L Automatic Thesis Admission and Resolver",
        "phase": "ade_qre_020l",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Atomically admit generated theses and compose one resolved research-only thesis catalog.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020k_primitive_compatibility_classifier",),
    },
    {
        "id": "ade_qre_020m_hypothesis_prioritization",
        "title": "ADE-QRE-020M Hypothesis Prioritization",
        "phase": "ade_qre_020m",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Prioritize admitted hypotheses transparently on information gain, readiness, and diversity.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020l_automatic_thesis_admission_and_resolver",),
    },
    {
        "id": "ade_qre_020n_ade_qre_019_integration",
        "title": "ADE-QRE-020N ADE-QRE-019 Integration",
        "phase": "ade_qre_020n",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Submit only admitted, compilable generated theses into ADE-QRE-019 without bypassing its gates.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020m_hypothesis_prioritization",),
    },
    {
        "id": "ade_qre_020o_autonomous_feedback_loop",
        "title": "ADE-QRE-020O Autonomous Feedback Loop",
        "phase": "ade_qre_020o",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Ingest downstream generation and later campaign outcomes as bounded feedback only.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020n_ade_qre_019_integration",),
    },
    {
        "id": "ade_qre_020p_apply_to_current_research_state",
        "title": "ADE-QRE-020P Apply to Current Research State",
        "phase": "ade_qre_020p",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Run the full deterministic A20 loop against the current authoritative repository state.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020o_autonomous_feedback_loop",),
    },
    {
        "id": "ade_qre_020q_integrated_closeout",
        "title": "ADE-QRE-020Q Integrated Closeout",
        "phase": "ade_qre_020q",
        "source_documents": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Produce the integrated A20 closeout, primitive-extension requests, and exact next action.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020p_apply_to_current_research_state",),
    },
    {
        "id": "ade_qre_021a_primitive_expansion_governance_and_authority",
        "title": "ADE-QRE-021A Primitive Expansion Governance and Authority",
        "phase": "ade_qre_021a",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Authorize bounded deterministic primitive expansion and downstream research-only replay without granting trading authority.",
        "status": "not_started",
        "prerequisites": ("ade_qre_020q_integrated_closeout",),
    },
    {
        "id": "ade_qre_021b_primitive_extension_request_contract",
        "title": "ADE-QRE-021B Primitive Extension Request Contract",
        "phase": "ade_qre_021b",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Validate deterministic primitive-extension requests from authoritative thesis blockers.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021a_primitive_expansion_governance_and_authority",),
    },
    {
        "id": "ade_qre_021c_closed_primitive_specification_schema",
        "title": "ADE-QRE-021C Closed Primitive Specification Schema",
        "phase": "ade_qre_021c",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Compile closed primitive specifications with deterministic temporal, grouping, ordering, and missing-data semantics.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021b_primitive_extension_request_contract",),
    },
    {
        "id": "ade_qre_021d_primitive_implementation_generator",
        "title": "ADE-QRE-021D Primitive Implementation Generator",
        "phase": "ade_qre_021d",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generate deterministic primitive implementations from closed primitive specifications.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021c_closed_primitive_specification_schema",),
    },
    {
        "id": "ade_qre_021e_primitive_test_generator",
        "title": "ADE-QRE-021E Primitive Test Generator",
        "phase": "ade_qre_021e",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generate deterministic primitive tests from the closed primitive schema.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021d_primitive_implementation_generator",),
    },
    {
        "id": "ade_qre_021f_static_safety_and_architecture_validation",
        "title": "ADE-QRE-021F Static Safety and Architecture Validation",
        "phase": "ade_qre_021f",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Reject forbidden imports, side effects, and boundary violations before primitive execution.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021e_primitive_test_generator",),
    },
    {
        "id": "ade_qre_021g_primitive_sandbox_validation",
        "title": "ADE-QRE-021G Primitive Sandbox Validation",
        "phase": "ade_qre_021g",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Validate generated primitives in an isolated deterministic sandbox.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021f_static_safety_and_architecture_validation",),
    },
    {
        "id": "ade_qre_021h_automatic_primitive_registry_admission",
        "title": "ADE-QRE-021H Automatic Primitive Registry Admission",
        "phase": "ade_qre_021h",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Atomically admit validated generated primitives into the isolated generated registry and resolved primitive catalog.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021g_primitive_sandbox_validation",),
    },
    {
        "id": "ade_qre_021i_cross_sectional_data_contract",
        "title": "ADE-QRE-021I Cross-Sectional Data Contract",
        "phase": "ade_qre_021i",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Define the deterministic cross-sectional input contract required by cross_sectional_rank.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021h_automatic_primitive_registry_admission",),
    },
    {
        "id": "ade_qre_021j_cross_sectional_rank_implementation",
        "title": "ADE-QRE-021J cross_sectional_rank Implementation",
        "phase": "ade_qre_021j",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generate and validate the first bounded primitive requested by ADE-QRE-020.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021i_cross_sectional_data_contract",),
    },
    {
        "id": "ade_qre_021k_automatic_thesis_recompile",
        "title": "ADE-QRE-021K Automatic Thesis Recompile",
        "phase": "ade_qre_021k",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Automatically recompile blocked theses after a bounded primitive becomes resolver-visible.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021j_cross_sectional_rank_implementation",),
    },
    {
        "id": "ade_qre_021l_automatic_strategy_generation_and_retest",
        "title": "ADE-QRE-021L Automatic Strategy Generation and Retest",
        "phase": "ade_qre_021l",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Invoke ADE-QRE-019 automatically after successful primitive admission and preserve its gates.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021k_automatic_thesis_recompile",),
    },
    {
        "id": "ade_qre_021m_campaign_readiness_reevaluation",
        "title": "ADE-QRE-021M Campaign Readiness Reevaluation",
        "phase": "ade_qre_021m",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Rebuild preset, null-control, lineage, portfolio, and preregistration readiness without campaign execution.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021l_automatic_strategy_generation_and_retest",),
    },
    {
        "id": "ade_qre_021n_autonomous_capability_expansion_loop",
        "title": "ADE-QRE-021N Autonomous Capability Expansion Loop",
        "phase": "ade_qre_021n",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generalize the bounded primitive-expansion loop for future authoritative requests.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021m_campaign_readiness_reevaluation",),
    },
    {
        "id": "ade_qre_021o_integrated_closeout",
        "title": "ADE-QRE-021O Integrated Closeout",
        "phase": "ade_qre_021o",
        "source_documents": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Produce the integrated A21 closeout with primitive, strategy, and readiness outcomes plus the exact next action.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021n_autonomous_capability_expansion_loop",),
    },
    {
        "id": "ade_qre_022a_governance_and_readiness_authority",
        "title": "ADE-QRE-022A Governance and Readiness Authority",
        "phase": "ade_qre_022a",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit deterministic campaign-readiness remediation while preserving protected `.claude/**` and `research/**` boundaries.",
        "status": "not_started",
        "prerequisites": ("ade_qre_021o_integrated_closeout",),
    },
    {
        "id": "ade_qre_022b_readiness_gap_diagnosis",
        "title": "ADE-QRE-022B Readiness Gap Diagnosis",
        "phase": "ade_qre_022b",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Decompose aggregate campaign-readiness blockers into exact field-level gaps, candidates, and next actions.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022a_governance_and_readiness_authority",),
    },
    {
        "id": "ade_qre_022c_canonical_identity_resolution_contract",
        "title": "ADE-QRE-022C Canonical Identity Resolution Contract",
        "phase": "ade_qre_022c",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve only unique or canonically aliased identities and fail closed on ambiguity or conflict.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022b_readiness_gap_diagnosis",),
    },
    {
        "id": "ade_qre_022d_instrument_and_universe_resolution",
        "title": "ADE-QRE-022D Instrument and Universe Resolution",
        "phase": "ade_qre_022d",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Bind canonical instruments and universes without symbol-only or survivor-biased shortcuts.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022c_canonical_identity_resolution_contract",),
    },
    {
        "id": "ade_qre_022e_source_dataset_snapshot_resolution",
        "title": "ADE-QRE-022E Source, Dataset and Snapshot Resolution",
        "phase": "ade_qre_022e",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Bind source, dataset, snapshot, schema, and freshness only when authoritative evidence supports them.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022d_instrument_and_universe_resolution",),
    },
    {
        "id": "ade_qre_022f_timeframe_and_regime_binding",
        "title": "ADE-QRE-022F Timeframe and Regime Binding",
        "phase": "ade_qre_022f",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve timeframe, rebalance, warmup, and regime bindings without inferring them from names alone.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022e_source_dataset_snapshot_resolution",),
    },
    {
        "id": "ade_qre_022g_train_validation_oos_capacity",
        "title": "ADE-QRE-022G Train, Validation and OOS Capacity",
        "phase": "ade_qre_022g",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Assess train, validation, OOS, and null-control capacity while excluding consumed or non-independent windows.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022f_timeframe_and_regime_binding",),
    },
    {
        "id": "ade_qre_022h_preset_completion",
        "title": "ADE-QRE-022H Preset Completion",
        "phase": "ade_qre_022h",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Create or complete bounded presets only when identity, timeframe, and data bindings are authoritative.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022g_train_validation_oos_capacity",),
    },
    {
        "id": "ade_qre_022i_null_control_execution_readiness",
        "title": "ADE-QRE-022I Null-Control Execution Readiness",
        "phase": "ade_qre_022i",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Distinguish executable null-control readiness from specification-only availability.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022h_preset_completion",),
    },
    {
        "id": "ade_qre_022j_campaign_metadata_materialization",
        "title": "ADE-QRE-022J Campaign Metadata Materialization",
        "phase": "ade_qre_022j",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize deterministic campaign metadata only when every mandatory readiness field is resolved.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022i_null_control_execution_readiness",),
    },
    {
        "id": "ade_qre_022k_campaign_lineage_completion",
        "title": "ADE-QRE-022K Campaign Lineage Completion",
        "phase": "ade_qre_022k",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize the full readiness lineage from hypothesis opportunity through campaign candidate.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022j_campaign_metadata_materialization",),
    },
    {
        "id": "ade_qre_022l_portfolio_and_preregistration_reevaluation",
        "title": "ADE-QRE-022L Portfolio and Preregistration Reevaluation",
        "phase": "ade_qre_022l",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Rebuild the canonical portfolio and admit a preregistered second campaign only when a cell is genuinely ready.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022k_campaign_lineage_completion",),
    },
    {
        "id": "ade_qre_022m_autonomous_readiness_remediation_loop",
        "title": "ADE-QRE-022M Autonomous Readiness Remediation Loop",
        "phase": "ade_qre_022m",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generalize deterministic readiness remediation and feed exact remaining blockers back to prior governed loops.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022l_portfolio_and_preregistration_reevaluation",),
    },
    {
        "id": "ade_qre_022n_apply_to_qgs_e565b01bd0a162d0",
        "title": "ADE-QRE-022N Apply to qgs_e565b01bd0a162d0",
        "phase": "ade_qre_022n",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Apply readiness remediation to the resolver-visible generated strategies and preserve exact fail-closed outcomes.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022m_autonomous_readiness_remediation_loop",),
    },
    {
        "id": "ade_qre_022o_integrated_closeout",
        "title": "ADE-QRE-022O Integrated Closeout",
        "phase": "ade_qre_022o",
        "source_documents": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Produce the integrated readiness-remediation outcome and the exact next action without overstating campaign readiness.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022n_apply_to_qgs_e565b01bd0a162d0",),
    },
    {
        "id": "ade_qre_023a_autonomous_closure_governance",
        "title": "ADE-QRE-023A Autonomous Closure Governance",
        "phase": "ade_qre_023a",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit the bounded autonomous readiness-closure loop without weakening `.claude/**`, protected `research/**`, or trading-authority boundaries.",
        "status": "not_started",
        "prerequisites": ("ade_qre_022o_integrated_closeout",),
    },
    {
        "id": "ade_qre_023b_blocker_taxonomy_and_dependency_graph",
        "title": "ADE-QRE-023B Blocker Taxonomy and Dependency Graph",
        "phase": "ade_qre_023b",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Define the closed blocker contract and dependency ordering so upstream causes are resolved before downstream symptoms.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023a_autonomous_closure_governance",),
    },
    {
        "id": "ade_qre_023c_remediation_planner",
        "title": "ADE-QRE-023C Remediation Planner",
        "phase": "ade_qre_023c",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Map each blocker class to exactly one deterministic remediation action, routed program, or fail-closed terminal path.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023b_blocker_taxonomy_and_dependency_graph",),
    },
    {
        "id": "ade_qre_023d_canonical_universe_authority",
        "title": "ADE-QRE-023D Canonical Universe Authority",
        "phase": "ade_qre_023d",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve canonical universes, alias mappings, and authoritative point-in-time membership without survivor-biased shortcuts.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023c_remediation_planner",),
    },
    {
        "id": "ade_qre_023e_historical_universe_membership",
        "title": "ADE-QRE-023E Historical Universe Membership",
        "phase": "ade_qre_023e",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Preserve deterministic point-in-time universe membership, inclusion and exclusion reasons, and minimum-breadth evidence.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023d_canonical_universe_authority",),
    },
    {
        "id": "ade_qre_023f_timeframe_resolution",
        "title": "ADE-QRE-023F Timeframe Resolution",
        "phase": "ade_qre_023f",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve deterministic timeframes or split ambiguous strategies into distinct campaign cells without silently selecting one.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023e_historical_universe_membership",),
    },
    {
        "id": "ade_qre_023g_preset_completion",
        "title": "ADE-QRE-023G Preset Completion",
        "phase": "ade_qre_023g",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Complete bounded presets after authoritative identity, timeframe, source, dataset, and snapshot binding.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023f_timeframe_resolution",),
    },
    {
        "id": "ade_qre_023h_source_dataset_and_snapshot_binding",
        "title": "ADE-QRE-023H Source, Dataset and Snapshot Binding",
        "phase": "ade_qre_023h",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Bind authoritative source, dataset, schema, coverage, and immutable snapshot identities outside protected empirical surfaces.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023g_preset_completion",),
    },
    {
        "id": "ade_qre_023i_window_and_independent_oos_capacity",
        "title": "ADE-QRE-023I Window and Independent OOS Capacity",
        "phase": "ade_qre_023i",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize exact train, validation, and unseen OOS capacity while failing closed when independence cannot be proven.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023h_source_dataset_and_snapshot_binding",),
    },
    {
        "id": "ade_qre_023j_null_control_implementation_closure",
        "title": "ADE-QRE-023J Null-Control Implementation Closure",
        "phase": "ade_qre_023j",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Close null-control implementation and execution-readiness gaps without claiming empirical null outcomes.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023i_window_and_independent_oos_capacity",),
    },
    {
        "id": "ade_qre_023k_cost_slippage_and_regime_binding",
        "title": "ADE-QRE-023K Cost, Slippage and Regime Binding",
        "phase": "ade_qre_023k",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve cost, slippage, session, timezone, and regime identities required for deterministic campaign readiness.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023j_null_control_implementation_closure",),
    },
    {
        "id": "ade_qre_023l_campaign_metadata_and_lineage_closure",
        "title": "ADE-QRE-023L Campaign Metadata and Lineage Closure",
        "phase": "ade_qre_023l",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize complete campaign metadata and lineage only when every mandatory upstream field is authoritative and complete.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023k_cost_slippage_and_regime_binding",),
    },
    {
        "id": "ade_qre_023m_autonomous_capability_generator_integration",
        "title": "ADE-QRE-023M Autonomous Capability Generator Integration",
        "phase": "ade_qre_023m",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Integrate bounded remediation routing with the existing ADE-QRE-019/020/021/022 governed generators and fail-closed feedback paths.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023l_campaign_metadata_and_lineage_closure",),
    },
    {
        "id": "ade_qre_023n_iterative_readiness_replay",
        "title": "ADE-QRE-023N Iterative Readiness Replay",
        "phase": "ade_qre_023n",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute the bounded multi-iteration readiness replay loop with cycle detection, iteration bounds, and persistent causal-progress evidence.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023m_autonomous_capability_generator_integration",),
    },
    {
        "id": "ade_qre_023o_second_campaign_preregistration",
        "title": "ADE-QRE-023O Second-Campaign Preregistration",
        "phase": "ade_qre_023o",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit a second-campaign preregistration manifest only when at least one cell is genuinely READY_FOR_PREREGISTRATION.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023n_iterative_readiness_replay",),
    },
    {
        "id": "ade_qre_023p_integrated_closure_report",
        "title": "ADE-QRE-023P Integrated Closure Report",
        "phase": "ade_qre_023p",
        "source_documents": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Persist the integrated autonomous readiness-closure report, irreducible blockers, manifest status, and the exact next permitted action.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023o_second_campaign_preregistration",),
    },
    {
        "id": "ade_qre_024a_governance_and_data_window_authority",
        "title": "ADE-QRE-024A Governance and Data/Window Authority",
        "phase": "ade_qre_024a",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit the bounded deterministic data-capacity and authoritative-window-assignment loop without weakening protected empirical or execution boundaries.",
        "status": "not_started",
        "prerequisites": ("ade_qre_023p_integrated_closure_report",),
    },
    {
        "id": "ade_qre_024b_data_capacity_diagnosis",
        "title": "ADE-QRE-024B Data Capacity Diagnosis",
        "phase": "ade_qre_024b",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Diagnose exact cache, coverage, source, snapshot, point-in-time membership, and data-capacity blockers for every campaign cell.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024a_governance_and_data_window_authority",),
    },
    {
        "id": "ade_qre_024c_canonical_data_binding_and_cache_authority",
        "title": "ADE-QRE-024C Canonical Data Binding and Cache Authority",
        "phase": "ade_qre_024c",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Resolve one canonical data/cache authority across source, dataset, cache-row, snapshot, instrument, and timeframe bindings.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024b_data_capacity_diagnosis",),
    },
    {
        "id": "ade_qre_024d_missing_cache_row_materialization",
        "title": "ADE-QRE-024D Missing Cache Row Materialization",
        "phase": "ade_qre_024d",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize missing authoritative cache rows only from governed local inputs or fail closed when no safe source exists.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024c_canonical_data_binding_and_cache_authority",),
    },
    {
        "id": "ade_qre_024e_data_quality_and_coverage_validation",
        "title": "ADE-QRE-024E Data Quality and Coverage Validation",
        "phase": "ade_qre_024e",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Validate schema, range, duplicates, gaps, timezone, quality, and usable coverage before any snapshot or window assignment.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024d_missing_cache_row_materialization",),
    },
    {
        "id": "ade_qre_024f_immutable_snapshot_materialization",
        "title": "ADE-QRE-024F Immutable Snapshot Materialization",
        "phase": "ade_qre_024f",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Freeze source, dataset, cache rows, universe version, timeframe, schema, coverage, and content hashes into immutable strategy snapshots.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024e_data_quality_and_coverage_validation",),
    },
    {
        "id": "ade_qre_024g_authoritative_window_policy",
        "title": "ADE-QRE-024G Authoritative Window Policy",
        "phase": "ade_qre_024g",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Define a deterministic policy for assigning train, validation, and unseen OOS windows before any strategy-result inspection.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024f_immutable_snapshot_materialization",),
    },
    {
        "id": "ade_qre_024h_window_ledger_and_consumption_registry",
        "title": "ADE-QRE-024H Window Ledger and Consumption Registry",
        "phase": "ade_qre_024h",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Track available, reserved, consumed, invalidated, and superseded train/validation/OOS windows in one canonical ledger.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024g_authoritative_window_policy",),
    },
    {
        "id": "ade_qre_024i_train_validation_oos_assignment",
        "title": "ADE-QRE-024I Train/Validation/OOS Assignment",
        "phase": "ade_qre_024i",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Assign deterministic train, validation, OOS, warmup, embargo, and null-control windows for valid campaign cells.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024h_window_ledger_and_consumption_registry",),
    },
    {
        "id": "ade_qre_024j_oos_independence_and_leakage_proof",
        "title": "ADE-QRE-024J OOS Independence and Leakage Proof",
        "phase": "ade_qre_024j",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Prove that each reserved OOS window is unseen, non-overlapping where required, embargo-compliant, and free of future leakage.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024i_train_validation_oos_assignment",),
    },
    {
        "id": "ade_qre_024k_point_in_time_universe_and_breadth_validation",
        "title": "ADE-QRE-024K Point-in-Time Universe and Breadth Validation",
        "phase": "ade_qre_024k",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Validate point-in-time universe membership, breadth, listing state, and no-survivorship assumptions for campaign cells.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024j_oos_independence_and_leakage_proof",),
    },
    {
        "id": "ade_qre_024l_signal_density_capacity_validation",
        "title": "ADE-QRE-024L Signal-Density Capacity Validation",
        "phase": "ade_qre_024l",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Estimate whether assigned windows can plausibly satisfy required sample and signal counts without using strategy returns.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024k_point_in_time_universe_and_breadth_validation",),
    },
    {
        "id": "ade_qre_024m_iterative_data_window_closure_loop",
        "title": "ADE-QRE-024M Iterative Data/Window Closure Loop",
        "phase": "ade_qre_024m",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Run the bounded autonomous data/window remediation loop until at least one cell is ready or an irreducible terminal blocker is proven.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024l_signal_density_capacity_validation",),
    },
    {
        "id": "ade_qre_024n_downstream_readiness_replay",
        "title": "ADE-QRE-024N Downstream Readiness Replay",
        "phase": "ade_qre_024n",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Replay ADE-QRE-022 and ADE-QRE-023 downstream readiness after every successful data or window remediation.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024m_iterative_data_window_closure_loop",),
    },
    {
        "id": "ade_qre_024o_second_campaign_preregistration",
        "title": "ADE-QRE-024O Second-Campaign Preregistration",
        "phase": "ade_qre_024o",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Materialize a deterministic second-campaign manifest only when at least one campaign cell is genuinely READY_FOR_PREREGISTRATION.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024n_downstream_readiness_replay",),
    },
    {
        "id": "ade_qre_024p_integrated_closeout",
        "title": "ADE-QRE-024P Integrated Closeout",
        "phase": "ade_qre_024p",
        "source_documents": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Persist the integrated data/window-capacity closeout, exact blockers resolved or remaining, manifest status, and the next permitted machine action.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024o_second_campaign_preregistration",),
    },
    {
        "id": "ade_qre_025a_campaign_execution_governance",
        "title": "ADE-QRE-025A Campaign Execution Governance",
        "phase": "ade_qre_025a",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit the bounded deterministic execution of the frozen second-campaign manifest plus the post-campaign research-decision loop without weakening protected empirical or execution boundaries.",
        "status": "not_started",
        "prerequisites": ("ade_qre_024p_integrated_closeout",),
    },
    {
        "id": "ade_qre_025b_manifest_integrity_verification",
        "title": "ADE-QRE-025B Manifest Integrity Verification",
        "phase": "ade_qre_025b",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Verify every frozen manifest identity, hash, window, policy, and null-control input before any campaign execution begins.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025a_campaign_execution_governance",),
    },
    {
        "id": "ade_qre_025c_deterministic_campaign_runner",
        "title": "ADE-QRE-025C Deterministic Campaign Runner",
        "phase": "ade_qre_025c",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute only the ready manifest cell through deterministic train, validation, OOS, null-control, and accounting stages.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025b_manifest_integrity_verification",),
    },
    {
        "id": "ade_qre_025d_train_and_screening_execution",
        "title": "ADE-QRE-025D Train and Screening Execution",
        "phase": "ade_qre_025d",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute the frozen train window, screening criteria, and stage accounting without changing manifest inputs.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025c_deterministic_campaign_runner",),
    },
    {
        "id": "ade_qre_025e_validation_execution",
        "title": "ADE-QRE-025E Validation Execution",
        "phase": "ade_qre_025e",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute the frozen validation window and record degradation, stability, and exact validation pass/fail reasons.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025d_train_and_screening_execution",),
    },
    {
        "id": "ade_qre_025f_oos_execution",
        "title": "ADE-QRE-025F OOS Execution",
        "phase": "ade_qre_025f",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute the exact reserved unseen OOS window, then record canonical consumption evidence and reuse prevention.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025e_validation_execution",),
    },
    {
        "id": "ade_qre_025g_null_control_execution",
        "title": "ADE-QRE-025G Null-Control Execution",
        "phase": "ade_qre_025g",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute every manifest-frozen null control with deterministic seeds and authoritative comparisons against the actual strategy path.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025f_oos_execution",),
    },
    {
        "id": "ade_qre_025h_evidence_and_reason_record_completion",
        "title": "ADE-QRE-025H Evidence and Reason-Record Completion",
        "phase": "ade_qre_025h",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Complete authoritative stage-level evidence, reason-record, reproducibility, and provenance accounting for the executed campaign.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025g_null_control_execution",),
    },
    {
        "id": "ade_qre_025i_funnel_diagnosis",
        "title": "ADE-QRE-025I Funnel Diagnosis",
        "phase": "ade_qre_025i",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Diagnose stage conversion, threshold distances, bottlenecks, and exact failure taxonomy for the executed campaign funnel.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025h_evidence_and_reason_record_completion",),
    },
    {
        "id": "ade_qre_025j_hypothesis_and_strategy_decision",
        "title": "ADE-QRE-025J Hypothesis and Strategy Decision",
        "phase": "ade_qre_025j",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Emit one canonical hypothesis decision and one canonical strategy decision from the campaign evidence without any promotion authority beyond research.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025i_funnel_diagnosis",),
    },
    {
        "id": "ade_qre_025k_recalibration_decision",
        "title": "ADE-QRE-025K Recalibration Decision",
        "phase": "ade_qre_025k",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Determine whether exactly one bounded criterion class is justified for recalibration under current replay policy.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025j_hypothesis_and_strategy_decision",),
    },
    {
        "id": "ade_qre_025l_same_input_replay",
        "title": "ADE-QRE-025L Same-Input Replay",
        "phase": "ade_qre_025l",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Run same-input replay only when canonically justified and preserve replay as non-independent evidence under consumed-OOS policy.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025k_recalibration_decision",),
    },
    {
        "id": "ade_qre_025m_independent_oos_assessment",
        "title": "ADE-QRE-025M Independent OOS Assessment",
        "phase": "ade_qre_025m",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Assess whether another genuinely unseen independent OOS path exists using the canonical ledger and current independence rules.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025l_same_input_replay",),
    },
    {
        "id": "ade_qre_025n_autonomous_feedback_routing",
        "title": "ADE-QRE-025N Autonomous Feedback Routing",
        "phase": "ade_qre_025n",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Select exactly one deterministic next program-level action from the executed campaign evidence and route it through governed subsystems when locally executable.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025m_independent_oos_assessment",),
    },
    {
        "id": "ade_qre_025o_integrated_campaign_closeout",
        "title": "ADE-QRE-025O Integrated Campaign Closeout",
        "phase": "ade_qre_025o",
        "source_documents": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Persist manifest verification, executed-cell evidence, funnel, decisions, replay, OOS consumption, readiness update, and the exact terminal next action for the second preregistered campaign.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025n_autonomous_feedback_routing",),
    },
    {
        "id": "ade_qre_026a_autonomous_orchestration_governance",
        "title": "ADE-QRE-026A Autonomous Orchestration Governance",
        "phase": "ade_qre_026a",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Admit the bounded autonomous orchestration layer, define explicit local versus external execution boundaries, and preserve all immutable research and no-trading surfaces.",
        "status": "not_started",
        "prerequisites": ("ade_qre_025o_integrated_campaign_closeout",),
    },
    {
        "id": "ade_qre_026b_unified_research_portfolio_model",
        "title": "ADE-QRE-026B Unified Research Portfolio Model",
        "phase": "ade_qre_026b",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Compose one canonical resolved portfolio view spanning hypotheses, strategies, campaigns, blockers, budgets, and next actions.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026a_autonomous_orchestration_governance",),
    },
    {
        "id": "ade_qre_026c_typed_next_action_contract",
        "title": "ADE-QRE-026C Typed Next-Action Contract",
        "phase": "ade_qre_026c",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Define the closed next-action vocabulary and deterministic action artifacts that drive autonomous work admission.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026b_unified_research_portfolio_model",),
    },
    {
        "id": "ade_qre_026d_autonomous_work_admission",
        "title": "ADE-QRE-026D Autonomous Work Admission",
        "phase": "ade_qre_026d",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Convert typed next actions into governed bounded work items with explicit authority proof, writable surfaces, budgets, and terminal outcomes.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026c_typed_next_action_contract",),
    },
    {
        "id": "ade_qre_026e_dependency_and_causal_blocker_graph",
        "title": "ADE-QRE-026E Dependency and Causal Blocker Graph",
        "phase": "ade_qre_026e",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Model causal blocker dependencies so the scheduler prefers shared upstream unlocks over repeated downstream symptom work.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026d_autonomous_work_admission",),
    },
    {
        "id": "ade_qre_026f_work_planner_and_router",
        "title": "ADE-QRE-026F Work Planner and Router",
        "phase": "ade_qre_026f",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Map each admitted work class to an existing ADE-QRE capability or a bounded development work package.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026e_dependency_and_causal_blocker_graph",),
    },
    {
        "id": "ade_qre_026g_capability_execution_adapters",
        "title": "ADE-QRE-026G Capability Execution Adapters",
        "phase": "ade_qre_026g",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Provide typed allowlisted repository-native adapters for invoking governed capabilities and validation commands without arbitrary shell execution.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026f_work_planner_and_router",),
    },
    {
        "id": "ade_qre_026h_development_work_package_generator",
        "title": "ADE-QRE-026H Development Work Package Generator",
        "phase": "ade_qre_026h",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Generate deterministic machine-executable development work packages when repository-native capability routing is unavailable.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026g_capability_execution_adapters",),
    },
    {
        "id": "ade_qre_026i_validation_and_evidence_gate",
        "title": "ADE-QRE-026I Validation and Evidence Gate",
        "phase": "ade_qre_026i",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Validate work-item success through artifact, test, governance, architecture, and causal-progress evidence rather than exit codes alone.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026h_development_work_package_generator",),
    },
    {
        "id": "ade_qre_026j_research_replay_controller",
        "title": "ADE-QRE-026J Research Replay Controller",
        "phase": "ade_qre_026j",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Replay only the minimum affected downstream research chain after validated work while preserving historical evidence and consumed OOS records.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026i_validation_and_evidence_gate",),
    },
    {
        "id": "ade_qre_026k_research_throughput_scheduler",
        "title": "ADE-QRE-026K Research Throughput Scheduler",
        "phase": "ade_qre_026k",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Prioritize safe high-information research throughput using deterministic information-gain, blocker-depth, evidence-cost, and diversity-aware scheduling.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026j_research_replay_controller",),
    },
    {
        "id": "ade_qre_026l_campaign_portfolio_scheduler",
        "title": "ADE-QRE-026L Campaign Portfolio Scheduler",
        "phase": "ade_qre_026l",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Schedule independent campaign cells in safe bounded batches while preserving OOS exclusivity, preregistration order, and compute limits.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026k_research_throughput_scheduler",),
    },
    {
        "id": "ade_qre_026m_oos_and_evidence_budget_manager",
        "title": "ADE-QRE-026M OOS and Evidence Budget Manager",
        "phase": "ade_qre_026m",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Treat independent OOS as a scarce evidence budget and apply explicit conservation and admission policy before campaign execution.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026l_campaign_portfolio_scheduler",),
    },
    {
        "id": "ade_qre_026n_autonomous_data_oos_capacity_expansion",
        "title": "ADE-QRE-026N Autonomous Data/OOS Capacity Expansion",
        "phase": "ade_qre_026n",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Execute the exact A25 next action to expand data and OOS capacity where authoritative local inputs permit, without mutating historical evidence or strategy logic.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026m_oos_and_evidence_budget_manager",),
    },
    {
        "id": "ade_qre_026o_continuous_research_loop",
        "title": "ADE-QRE-026O Continuous Research Loop",
        "phase": "ade_qre_026o",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Run the bounded continuous local loop that admits, executes, validates, replays, preregisters, executes, and reprioritizes governed research work.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026n_autonomous_data_oos_capacity_expansion",),
    },
    {
        "id": "ade_qre_026p_operator_controls_and_kill_switches",
        "title": "ADE-QRE-026P Operator Controls and Kill Switches",
        "phase": "ade_qre_026p",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Expose explicit operating modes, budgets, pause/resume, graceful stop, and safety kill switches for the autonomous orchestration engine.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026o_continuous_research_loop",),
    },
    {
        "id": "ade_qre_026r_simple_research_operations_configuration_monitoring_and_daily_intelligence",
        "title": "ADE-QRE-026R Simple Research Operations Configuration, Monitoring, and Daily Intelligence",
        "phase": "ade_qre_026r",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Provide one typed operations configuration surface, simple operator commands, daily reporting, monitoring status, alerting, backlog replenishment, and independence-aware daily orchestration controls.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026p_operator_controls_and_kill_switches",),
    },
    {
        "id": "ade_qre_026q_integrated_closeout",
        "title": "ADE-QRE-026Q Integrated Closeout",
        "phase": "ade_qre_026q",
        "source_documents": (
            "docs/roadmap/qre_autonomous_ade_work_admission_orchestration_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
        ),
        "purpose": "Persist the orchestration closeout with autonomous stages, external execution boundary, portfolio advancement, throughput metrics, and exact resume command.",
        "status": "not_started",
        "prerequisites": ("ade_qre_026r_simple_research_operations_configuration_monitoring_and_daily_intelligence",),
    },
    {
        "id": "phase_v3_15_16",
        "title": "Intelligent Routing Layer",
        "phase": "v3.15.16",
        "source_documents": (
            "docs/roadmap/Roadmap v6.md",
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Make campaign routing behavior-aware instead of "
            "preset-count-aware. Prioritize most informative exploration "
            "via deterministic, inspectable, artifact-driven routing "
            "decisions. Diagnostics inform routing only; they do not "
            "trade."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    {
        "id": "phase_v3_15_17",
        "title": "Sampling Intelligence",
        "phase": "v3.15.17",
        "source_documents": (
            "docs/roadmap/Roadmap v6.md",
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Replace brute-force parameter-grid exploration with "
            "deterministic intelligent sampling: stratified, "
            "low-information suppression, signal-density-aware. "
            "Diagnostics inform sampling only."
        ),
        "status": "not_started",
        "prerequisites": ("phase_v3_15_16",),
    },
    {
        "id": "phase_v3_15_18",
        "title": "Research Observability Expansion",
        "phase": "v3.15.18",
        "source_documents": (
            "docs/roadmap/Roadmap v6.md",
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Expose read-only observability surfaces explaining why a "
            "campaign / hypothesis was explored, which diagnostics "
            "supported or contradicted it, and why it failed or "
            "survived. No mutation endpoints; no approval buttons."
        ),
        "status": "not_started",
        "prerequisites": ("phase_v3_15_17",),
    },
    {
        "id": "phase_v3_15_19",
        "title": "Hypothesis Discovery Engine",
        "phase": "v3.15.19",
        "source_documents": (
            "docs/roadmap/Roadmap v6.md",
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Introduce the autonomous research-front-door layer. "
            "Behavior-first hypothesis proposals with explainable "
            "opportunity scoring as expected research value, not "
            "prediction certainty. No executable strategy auto-writing; "
            "no hidden AI logic; no direct promotion to trading."
        ),
        "status": "not_started",
        "prerequisites": ("phase_v3_15_18",),
    },
    {
        "id": "phase_v3_15_20",
        "title": "Failure to Action Mapping",
        "phase": "v3.15.20",
        "source_documents": (
            "docs/roadmap/Roadmap v6.md",
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Convert research failures into deterministic adaptive "
            "actions. Failure taxonomy + closed action mapping that "
            "affects routing / suppression / cooldown / confirmation. "
            "No live risk mutation; no capital allocation; no trade "
            "placement."
        ),
        "status": "not_started",
        "prerequisites": ("phase_v3_15_19",),
    },
    {
        "id": "addendum_1_diagnostics_intake",
        "title": (
            "Mechanistic Behavior Diagnostics and External Intelligence "
            "Intake"
        ),
        "phase": "addendum_1",
        "source_documents": (
            "docs/roadmap/Roadmap v6 Addendum.md",
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        ),
        "purpose": (
            "Cross-cutting Roadmap v6 Addendum 1 task. Establish the "
            "Behavior Diagnostics Library / Research Diagnostics "
            "Primitives + External Intelligence Intake. Diagnostics "
            "do not trade. External / public data is an unvalidated "
            "prior, not alpha. New diagnostic information lives in "
            "sidecar artifacts; research_latest.json and "
            "strategy_matrix.csv remain frozen."
        ),
        "status": "not_started",
        "prerequisites": (),
    },
    # A23 — Addendum 2: State, Sequential, Knowledge & Retrieval
    # Intelligence. Cross-cutting task derived verbatim from the
    # operator-provided canonical doc. Diagnostics still do not
    # trade; knowledge graphs / retrieval / state diagnostics live
    # in sidecar artefacts; frozen contracts remain frozen.
    {
        "id": "addendum_2_state_sequential_knowledge_retrieval",
        "title": (
            "State, Sequential, Knowledge and Retrieval Intelligence"
        ),
        "phase": "addendum_2",
        "source_documents": (
            (
                "docs/roadmap/Roadmap v6 Addendum 2 - "
                "State Sequential Knowledge Retrieval.md"
            ),
        ),
        "purpose": (
            "Cross-cutting Roadmap v6 Addendum 2 task. Establish the "
            "Research Knowledge & Retrieval Layer and the State & "
            "Sequential Diagnostics Layer as deterministic, read-only "
            "research-routing surfaces. Knowledge graphs, ontologies, "
            "entity resolution, hybrid retrieval, state transition / "
            "HMM / semi-Markov / particle-filter / martingale / "
            "random-walk / queueing diagnostics never trade, never "
            "place orders, never allocate capital, never mutate live "
            "risk. All new information lives in sidecar artifacts; "
            "research_latest.json and strategy_matrix.csv remain "
            "frozen."
        ),
        "status": "not_started",
        "prerequisites": ("addendum_1_diagnostics_intake",),
    },
    # A23 — Addendum 3: Source Identity, Data Quality & Throughput
    # Intelligence. Cross-cutting task derived verbatim from the
    # operator-provided canonical doc. External / public data is
    # not alpha; only the QRE may decide which sources are useful.
    # Identity, manifest, quality-gate, cache, and throughput
    # surfaces remain read-only / artefact-only.
    {
        "id": "addendum_3_source_identity_data_quality_throughput",
        "title": (
            "Source Identity, Data Quality and Throughput "
            "Intelligence"
        ),
        "phase": "addendum_3",
        "source_documents": (
            (
                "docs/roadmap/Roadmap v6 Addendum 3 - "
                "Source Identity Data Quality and Throughput "
                "Intelligence.md"
            ),
        ),
        "purpose": (
            "Cross-cutting Roadmap v6 Addendum 3 task. Establish the "
            "Source Candidate Registry, Source Identity & Symbology "
            "Layer, Source Manifest & Quality Gate Layer, Local Data "
            "Cache & Throughput Layer, and Source Usefulness Ledger "
            "as deterministic, read-only research-routing surfaces. "
            "OpenFIGI identity, FRED/ALFRED macro, CFTC COT, EIA, "
            "Binance public bulk data, CoinGecko, event calendars, "
            "ETF/index constituents, options surfaces, Parquet / "
            "DuckDB / Polars / Dask / Dagster orchestration scaffolds "
            "never trade, never place orders, never allocate capital, "
            "never mutate live risk. All new information lives in "
            "sidecar artifacts; research_latest.json and "
            "strategy_matrix.csv remain frozen."
        ),
        "status": "not_started",
        "prerequisites": ("addendum_1_diagnostics_intake",),
    },
)


# ---------------------------------------------------------------------------
# Hand-encoded Addendum 1 + Roadmap v6 phase requirement seed data
# ---------------------------------------------------------------------------
#
# Each entry maps to one ``RoadmapRequirement``. The catalog only
# encodes requirements that have a normative anchor in Roadmap v6 or
# the committed Addendum 1 file. Addendum 2 / 3 requirements are NOT
# encoded here — their source documents are not in the repo.

_ROADMAP_REQUIREMENTS_SEED: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "req_ade_qre_017a_maturity_matrix",
        "roadmap_task_id": "ade_qre_017a_baseline_reconciliation",
        "source_document": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md"
        ),
        "source_anchor": "ADE-QRE-017A - Baseline Reconciliation and Maturity Matrix",
        "phase": "ade_qre_017a",
        "addendum_link": "none",
        "statement": (
            "Produce a repository-backed maturity matrix that classifies "
            "relevant QRE capabilities as scaffold, populated working "
            "capability, integrated capability, repeatable evidence "
            "capability, decision-useful capability, operator-trusted "
            "capability, or evidence-authoritative capability."
        ),
        "target_layer": "governance",
        "status": "not_started",
    },
    {
        "id": "req_ade_qre_017a_blocker_census",
        "roadmap_task_id": "ade_qre_017a_baseline_reconciliation",
        "source_document": (
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md"
        ),
        "source_anchor": "ADE-QRE-017A - Baseline Reconciliation and Maturity Matrix",
        "phase": "ade_qre_017a",
        "addendum_link": "none",
        "statement": (
            "Baseline reconciliation must count relevant artifacts and make "
            "current blockers explicit without inferring evidence authority "
            "from file existence."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    {
        "id": "req_ade_qre_017b_evidence_inventory",
        "roadmap_task_id": "ade_qre_017b_evidence_density_population",
        "source_document": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md"
        ),
        "source_anchor": "ADE-QRE-017B - Evidence-Density Population Plan",
        "phase": "ade_qre_017b",
        "addendum_link": "none",
        "statement": (
            "Inventory required evidence classes, their producers, their "
            "consumers, current population state, and the fail-closed "
            "blockers that prevent evidence density from becoming decision "
            "useful."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_ade_qre_017c_reason_record_linkage",
        "roadmap_task_id": "ade_qre_017c_reason_record_maturity",
        "source_document": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md"
        ),
        "source_anchor": "ADE-QRE-017C - Reason-Record Maturity",
        "phase": "ade_qre_017c",
        "addendum_link": "none",
        "statement": (
            "Reason records must be non-empty when real evidence exists, "
            "durable across runs, normalized to a closed representation, "
            "and explicitly linked to evidence references."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_ade_qre_017d_readiness_population",
        "roadmap_task_id": "ade_qre_017d_routing_sampling_readiness",
        "source_document": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md"
        ),
        "source_anchor": "ADE-QRE-017D - Routing and Sampling Readiness Population",
        "phase": "ade_qre_017d",
        "addendum_link": "none",
        "statement": (
            "Routing-ready and sampling-ready status must be derived from "
            "real repository evidence. Scaffold-only presence may not be "
            "promoted to readiness."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    {
        "id": "req_ade_qre_017e_kpi_snapshots",
        "roadmap_task_id": "ade_qre_017e_kpi_snapshot_completeness",
        "source_document": (
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md"
        ),
        "source_anchor": "ADE-QRE-017E - KPI Completeness and Historical Snapshots",
        "phase": "ade_qre_017e",
        "addendum_link": "none",
        "statement": (
            "Every KPI must be present as a numeric value or an explicit "
            "unavailable state, and the system must emit repeatable "
            "historical snapshots that preserve evidence time context."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    # ---- Addendum 1 - Core principles ----------------------------------
    {
        "id": "req_addendum_1_diagnostics_do_not_trade",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 2 Core Rule",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Diagnostics do not trade. A diagnostic may influence "
            "hypothesis priority, sampling, routing, evidence scoring, "
            "cooldown, confirmation, suppression or observability; it "
            "may not place trades, mutate live risk, allocate capital, "
            "bypass policy governance, or change frozen output "
            "contracts."
        ),
        "target_layer": "policy",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_external_data_not_alpha",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 8.1 Principle",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "External / public data is not alpha. It is an unvalidated "
            "prior. Only QRE-validated, OOS-stable, cost-aware, "
            "execution-realistic, policy-approved behavior can become "
            "edge."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_sidecar_artifacts_only",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 5 Proposed Repo Structure",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Diagnostic and external-intelligence information must "
            "live in sidecar artifacts. Do not mutate "
            "research_latest.json or strategy_matrix.csv."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    # ---- Addendum 1 — Diagnostic families (Section 6 + 7) --------------
    {
        "id": "req_addendum_1_tail_power_law",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.A Power Laws",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Tail / power-law diagnostics: return tail exponent, "
            "drawdown tail exponent, tail asymmetry, expected "
            "shortfall proxy, outlier dependency flag. Tail evidence "
            "may support a hypothesis; it may not directly promote a "
            "candidate."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_entropy_information_density",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.B Entropy",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Entropy / information-density diagnostics: Shannon and "
            "approximate entropy of returns / signals, entropy regime "
            "classification, market orderliness, information density. "
            "Used as a routing / policy state, not as a directional "
            "signal."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_criticality_phase_transitions",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.C Phase Transitions / Criticality",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Criticality / phase-transition diagnostics: autocorrelation "
            "drift, variance increase, critical slowing down, regime "
            "switch warnings. May trigger caution or segmentation; "
            "must not predict crashes as deterministic events."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_barrier_breakout_pressure",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.D Barrier / Tunneling",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Barrier / breakout-pressure diagnostics: probabilistic "
            "barrier crossing, range escape, post-breakout decay, "
            "failed-breakout rate. Seed breakout hypotheses; do not "
            "create deterministic support / resistance rules."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_resonance_cycle",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.E Resonance / Harmonic Oscillators",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Resonance / cycle diagnostics: dominant cycle period, "
            "cycle stability, resonance confluence, window alignment. "
            "Cycle fit must be checked against null models; no "
            "cycle-equals-alpha assumption."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_null_model_brownian",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 6.2.F Brownian / Random Walk / Null Models",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Null-model / Brownian / random-walk diagnostics: "
            "shuffled-return tests, surrogate data tests, "
            "noise-baseline excess return, false-discovery warnings. "
            "Every exotic diagnostic must eventually face a "
            "null-model challenge."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_network_diagnostics",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.2 Network Theory",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Network diagnostics: correlation networks, minimum "
            "spanning trees, asset clustering, contagion, cross-asset "
            "lead / lag, network fragility, diversification breakdown. "
            "Used for behavior hypotheses and portfolio research, not "
            "live allocation."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_adversarial_market_behavior",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.4 Game Theory",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Adversarial market-behavior diagnostics: crowding, "
            "adverse selection, fake-breakout rate, post-signal decay, "
            "liquidity-trap and predatory-regime warnings. Used to "
            "model adversarial market structure, not to randomize the "
            "QRE."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_control_stability",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.3 Control Theory",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Control-stability diagnostics: policy stability, evidence "
            "drift, signal-density drift, control oscillation, "
            "degradation rate, throttle recommendation. Not allowed "
            "now: PID position sizing, automatic exposure increase, "
            "equity-curve chasing, live risk mutation."
        ),
        "target_layer": "policy",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_seismic_aftershock",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.6 Seismology / Aftershock Modeling",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Seismic shock / aftershock diagnostics: mainshock "
            "detection, shock magnitude, aftershock decay rate, "
            "volatility half-life, shock-cluster intensity, "
            "post-shock directional bias, cooldown recommendation. "
            "Models shock processes; does not deterministically "
            "predict crashes."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_liquidity_turbulence",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.8 Fluid Dynamics / Turbulence",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Liquidity-turbulence diagnostics: liquidity turbulence "
            "score, slippage convexity proxy, flow-break risk, "
            "order-size stress score. Informs research and shadow / "
            "paper / live realism in their future approved phases; "
            "does not directly trade."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_independent_evidence_quorum",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.9 Biomimicry / Quorum Sensing",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Independent evidence quorum: independent confirmations, "
            "required confirmations, quorum status, confirmation "
            "diversity score, single-source dependency flag. Quorum "
            "sensing is a promotion / evidence guardrail, not a live "
            "trade trigger."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_market_language",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 7.10 Linguistics / Information Foraging",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Market-language diagnostics: token entropy, Zipf slope, "
            "sequence rarity, grammar shift, vocabulary collapse. "
            "Must be null-model tested. Not candle folklore; no "
            "rare-pattern-equals-alpha assumption."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    # ---- Addendum 1 — External intelligence intake ---------------------
    {
        "id": "req_addendum_1_external_intelligence_intake",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 8 External Intelligence Intake",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "External intelligence intake from public / free data "
            "sources only: Yahoo / yfinance, Stooq, Binance public "
            "klines, Bitvavo public candles, CoinGecko free, FRED, "
            "SEC EDGAR. No paid feeds, no vendor alpha, no commercial "
            "signal libraries, no private alternative-data vendors."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_public_source_manifest_fields",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 8.4 Source Manifest Fields",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Each public-source manifest must declare: source_id, "
            "source_type, access_method, expected_latency, "
            "expected_freshness, asset_coverage, timeframe_coverage, "
            "allowed_use, known_limitations, license_terms_reference, "
            "reproducibility_method, quality_gates."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_1_public_data_quality_gates",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 8.5 Public Data Quality Gates",
        "phase": "addendum_1",
        "addendum_link": "addendum_1",
        "statement": (
            "Required public-data quality gates: freshness, missing "
            "data, timestamp monotonicity, duplicate bar, outlier, "
            "coverage, source-agreement where possible, and "
            "license / terms metadata. No hypothesis seed may be "
            "promoted from public data without passing these checks."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    # ---- Roadmap v6 — phase v3.15.16 -----------------------------------
    {
        "id": "req_v3_15_16_behavior_aware_routing",
        "roadmap_task_id": "phase_v3_15_16",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.16 Intelligent Routing Layer",
        "phase": "v3.15.16",
        "addendum_link": "none",
        "statement": (
            "Replace preset-count-aware campaign routing with "
            "behavior-aware routing that prioritizes the most "
            "informative exploration, with orthogonality-aware queue "
            "discipline and dead-zone-aware suppression."
        ),
        "target_layer": "campaign",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_16_diagnostic_aware_routing",
        "roadmap_task_id": "phase_v3_15_16",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 9 v3.15.16 Intelligent Routing Layer",
        "phase": "v3.15.16",
        "addendum_link": "addendum_1",
        "statement": (
            "Add diagnostic-aware routing signals: entropy-aware, "
            "tail-aware, criticality-aware, network-aware, "
            "quorum-aware, external-intelligence-aware, and "
            "dead-zone suppression by diagnostic failure. Routing "
            "remains deterministic, inspectable, and artifact-backed."
        ),
        "target_layer": "campaign",
        "status": "not_started",
    },
    # ---- Roadmap v6 — phase v3.15.17 -----------------------------------
    {
        "id": "req_v3_15_17_deterministic_sampling",
        "roadmap_task_id": "phase_v3_15_17",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.17 Sampling Intelligence",
        "phase": "v3.15.17",
        "addendum_link": "none",
        "statement": (
            "Introduce stratified, adaptive deterministic coverage; "
            "low-information-region suppression; exploratory breadth "
            "balancing; signal-density-aware sampling. Replace "
            "brute-force parameter grids with high-information "
            "exploration."
        ),
        "target_layer": "preset",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_17_diagnostic_aware_sampling",
        "roadmap_task_id": "phase_v3_15_17",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 9 v3.15.17 Sampling Intelligence",
        "phase": "v3.15.17",
        "addendum_link": "addendum_1",
        "statement": (
            "Add tail-aware, entropy-stratified, "
            "phase-transition-zone, barrier-condition, "
            "resonance-window, network-regime, post-shock, and "
            "null-model control sampling. Sampling must remain "
            "deterministic and reproducible."
        ),
        "target_layer": "preset",
        "status": "not_started",
    },
    # ---- Roadmap v6 — phase v3.15.18 -----------------------------------
    {
        "id": "req_v3_15_18_research_observability",
        "roadmap_task_id": "phase_v3_15_18",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.18 Research Observability Expansion",
        "phase": "v3.15.18",
        "addendum_link": "none",
        "statement": (
            "Expose behavior-level diagnostics, exploration lineage, "
            "campaign decomposition, hypothesis traceability, "
            "information-gain surfaces, explanation artifacts, and "
            "failure-clustering visibility. Read-only; no mutation "
            "endpoints."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_18_diagnostic_surfaces",
        "roadmap_task_id": "phase_v3_15_18",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 9 v3.15.18 Research Observability Expansion",
        "phase": "v3.15.18",
        "addendum_link": "addendum_1",
        "statement": (
            "Expose read-only surfaces for diagnostic contribution "
            "explanation, external data lineage, public data quality "
            "status, hypothesis-seed provenance, null-model "
            "comparison, quorum status, network state, and the "
            "entropy / tail / criticality regime."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    # ---- Roadmap v6 — phase v3.15.19 -----------------------------------
    {
        "id": "req_v3_15_19_hypothesis_discovery_modules",
        "roadmap_task_id": "phase_v3_15_19",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.19 Hypothesis Discovery Engine",
        "phase": "v3.15.19",
        "addendum_link": "none",
        "statement": (
            "Introduce research/hypothesis_discovery/ with "
            "behavior_catalog, behavior_hypotheses, "
            "opportunity_scoring, preset_feasibility, and "
            "campaign_seed_proposer. Reason in market behaviors, not "
            "indicator combinations. Deterministic, inspectable, "
            "non-black-box."
        ),
        "target_layer": "hypothesis_discovery",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_19_opportunity_probability_score",
        "roadmap_task_id": "phase_v3_15_19",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.19 Probability Scoring",
        "phase": "v3.15.19",
        "addendum_link": "none",
        "statement": (
            "opportunity_probability_score is expected research "
            "value: feasibility, expected signal density, "
            "orthogonality, prior evidence alignment, regime "
            "compatibility, information gain, compute efficiency, "
            "historical survival similarity. It is NOT prediction "
            "certainty, alpha certainty, or ML confidence."
        ),
        "target_layer": "hypothesis_discovery",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_19_addendum_modules",
        "roadmap_task_id": "phase_v3_15_19",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 9 v3.15.19 Hypothesis Discovery Engine",
        "phase": "v3.15.19",
        "addendum_link": "addendum_1",
        "statement": (
            "Extend hypothesis-discovery modules with "
            "external_intelligence_catalog, public_data_seed_registry, "
            "physics_behavior_catalog, mechanistic_behavior_catalog, "
            "and diagnostic_hypothesis_adapter. No auto-writing of "
            "executable strategies; no hidden AI logic."
        ),
        "target_layer": "hypothesis_discovery",
        "status": "not_started",
    },
    # ---- Roadmap v6 — phase v3.15.20 -----------------------------------
    {
        "id": "req_v3_15_20_failure_action_mappings",
        "roadmap_task_id": "phase_v3_15_20",
        "source_document": "docs/roadmap/Roadmap v6.md",
        "source_anchor": "v3.15.20 Failure to Action Mapping",
        "phase": "v3.15.20",
        "addendum_link": "none",
        "statement": (
            "Convert failures into deterministic actions. Base "
            "mappings: insufficient_trades -> higher timeframe; "
            "high_drawdown -> volatility normalization; "
            "weak_stability -> regime segmentation."
        ),
        "target_layer": "policy",
        "status": "not_started",
    },
    {
        "id": "req_v3_15_20_addendum_mappings",
        "roadmap_task_id": "phase_v3_15_20",
        "source_document": "docs/roadmap/Roadmap v6 Addendum.md",
        "source_anchor": "Section 9 v3.15.20 Failure to Action Mapping",
        "phase": "v3.15.20",
        "addendum_link": "addendum_1",
        "statement": (
            "Add deterministic Addendum 1 mappings: high_entropy, "
            "weak_tail_fit, left_tail_fragility, "
            "phase_transition_unstable, barrier_false_positive_high, "
            "resonance_not_persistent, network_concentration_high, "
            "post_shock_aftershock_unstable, "
            "liquidity_turbulence_high, quorum_insufficient, "
            "null_model_not_beaten. Mappings affect research routing / "
            "suppression / cooldown only; never trade execution."
        ),
        "target_layer": "policy",
        "status": "not_started",
    },
    # =====================================================================
    # A23 — Addendum 2 requirements (State, Sequential, Knowledge,
    # Retrieval). Each entry maps to one capability section from the
    # operator-provided canonical doc. Statements are paraphrased from
    # the doc into bounded-prose; the canonical doc remains the source
    # of truth.
    # =====================================================================
    {
        "id": "req_addendum_2_state_transition_diagnostics",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.2 Markov Chains / State Transition Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Compute deterministic state-transition statistics over "
            "closed-vocab regimes/states and emit them as sidecar "
            "diagnostics. Never trades, never mutates frozen "
            "contracts, never modifies live risk. Inputs are "
            "QRE-validated regimes/states; outputs are read-only "
            "research-routing context."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_hidden_markov_models",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.3 Hidden Markov Models / Latent Regime "
            "Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Fit deterministic Hidden Markov Models on QRE-validated "
            "inputs and emit posterior regime probabilities as "
            "sidecar diagnostics. Outputs are read-only research-"
            "routing context only; never executable trade signals."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_semi_markov_regime_duration",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.4 Semi-Markov / Regime Duration Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Model regime-duration distributions deterministically "
            "and emit sidecar diagnostics about how long regimes "
            "persist. Read-only context only; no trade signals."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_higher_order_state_sequence",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.5 Higher-Order State Sequence Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Compute higher-order state-sequence statistics "
            "(n-grams, mutual information across lags) and emit "
            "them as sidecar diagnostics. Read-only context only."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_particle_filters",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.6 Particle Filters / Sequential Monte Carlo"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Sequential-Monte-Carlo / particle-filter diagnostics on "
            "QRE-validated inputs only. Deterministic seeds. Outputs "
            "are read-only research-routing context."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_martingale_baseline",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.7 Martingale / No-Edge Baseline Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Martingale / no-edge baseline diagnostics that report "
            "whether observed structure beats a fair-game baseline. "
            "Read-only sidecar context; no trade signals."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_random_walk_surrogate",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.8 Random Walk / Surrogate Process Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Random-walk and surrogate-process baseline diagnostics. "
            "Deterministic seed sets. Read-only sidecar context."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_finite_state_machines",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.9 Finite State Machines / Deterministic "
            "Lifecycle Governance"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Encode research-pipeline lifecycle as deterministic "
            "finite state machines with closed-vocab transitions. "
            "Governance scaffold only; no runtime mutation."
        ),
        "target_layer": "governance",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_queueing_throughput",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 6.10 Queueing / Research Throughput Diagnostics"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Research-throughput diagnostics modelled as deterministic "
            "queueing-system metrics. Inputs and outputs are "
            "research-pipeline scheduling artefacts; no live system "
            "modification."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_knowledge_graph_memory",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 7.2 Knowledge Graphs / Research Memory Graph"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Knowledge-graph scaffold for research memory: nodes are "
            "QRE-validated artefacts; edges are deterministic "
            "lineage / dependency / contradiction relations. "
            "Read-only retrieval context."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_ontology_taxonomy",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": "Section 7.3 Ontologies / Canonical Taxonomy",
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Canonical taxonomy / ontology scaffold: closed-vocab "
            "term registry that normalises diagnostics, regimes, "
            "behaviours, evidence kinds. Pinned by tests."
        ),
        "target_layer": "governance",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_entity_resolution",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 7.4 Entity Resolution / Cross-Document Coreference"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Deterministic entity-resolution scaffold: cross-document "
            "coreference among QRE artefacts. No probabilistic "
            "tie-breaking; closed-vocab decisions only."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_hybrid_retrieval",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": "Section 7.5 Hybrid Search / Research Retrieval",
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Hybrid lexical + structural retrieval scaffold over the "
            "research-memory graph. Deterministic ranking; no LLM "
            "ranking; no fuzzy parsing. Read-only context."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_2_reciprocal_rank_fusion",
        "roadmap_task_id": "addendum_2_state_sequential_knowledge_retrieval",
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        "source_anchor": (
            "Section 7.6 Reciprocal Rank Fusion / Deterministic Rank "
            "Fusion"
        ),
        "phase": "addendum_2",
        "addendum_link": "addendum_2",
        "statement": (
            "Deterministic rank-fusion scaffold across multiple "
            "ranking signals. Closed-formula combinator pinned by "
            "tests."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    # =====================================================================
    # A23 — Addendum 3 requirements (Source Identity, Data Quality,
    # Throughput). Each entry maps to one capability section.
    # =====================================================================
    {
        "id": "req_addendum_3_source_candidate_registry",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": "Section 4 Source Candidate Registry",
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Deterministic registry of candidate data sources. "
            "Each entry pins identity, license, access mode "
            "(public / vendor / paid), repo-resident-only flag, "
            "and a status. The registry is sidecar-artefact only; "
            "it never grants connection authority."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_openfigi_identity",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": "Section 6.2 OpenFIGI / Instrument Identity",
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "OpenFIGI instrument-identity scaffold. Read-only "
            "symbology resolver wrapped as a deterministic "
            "candidate-registry entry. No live connections; no "
            "vendor credentials; no order placement."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_fred_alfred_macro",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": (
            "Section 6.3 FRED / ALFRED Revision-Aware Macro"
        ),
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "FRED / ALFRED revision-aware macro source candidate "
            "scaffold. Registry entry + manifest scaffold only; "
            "no live ingest; no trading authority."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_cftc_cot_positioning",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": "Section 6.4 CFTC COT / Positioning Context",
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "CFTC Commitment of Traders positioning-context source "
            "candidate scaffold. Registry + manifest only; not "
            "alpha; never trade."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_binance_public_bulk_cache",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": (
            "Section 6.8 Binance Public Bulk Data / Crypto Cache"
        ),
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Binance public bulk-data cache manifest scaffold. "
            "Cache-side artefact only; no live broker connection; "
            "no order placement; no credentials."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_parquet_cache",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": "Section 7.2 Parquet Cache",
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Local Parquet cache manifest scaffold for offline "
            "research data. Read-only manifest; never live; never "
            "broker / risk / execution path."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_duckdb_query_catalog",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": (
            "Section 7.3 DuckDB Metadata and Query Catalog"
        ),
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "DuckDB metadata / query-catalog scaffold for offline "
            "research data. Read-only catalog manifest; never live."
        ),
        "target_layer": "reporting",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_quality_gate_reporter",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": (
            "Section 4 Source Manifest & Quality Gate Layer"
        ),
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Public-data quality-gate reporter scaffold. "
            "Deterministic verdicts (passes_quality_gate / "
            "fails_quality_gate / insufficient_evidence) emitted as "
            "sidecar artefacts; never gates trading; never alpha."
        ),
        "target_layer": "diagnostics",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_source_usefulness_ledger",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": "Section 4 Source Usefulness Ledger",
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Deterministic per-source usefulness ledger that records "
            "QRE-validated quality verdicts and routing relevance. "
            "Sidecar artefact only; never trading authority."
        ),
        "target_layer": "evidence",
        "status": "not_started",
    },
    {
        "id": "req_addendum_3_event_calendar_scaffold",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "source_document": (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "source_anchor": (
            "Section 6.10 Event Calendars / Earnings, Dividends, "
            "Splits, Macro Releases"
        ),
        "phase": "addendum_3",
        "addendum_link": "addendum_3",
        "statement": (
            "Event-calendar source-candidate registry scaffold. "
            "Read-only catalog of public release schedules; never "
            "live; never trading; never alpha."
        ),
        "target_layer": "external_intelligence",
        "status": "not_started",
    },
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a seed task tuple into a schema-conformant dict.

    All free-text fields are bounded; tuples are coerced to sorted
    lists with stable order; closed-vocab fields are echoed verbatim.
    Schema integrity is enforced by tests, not by silent coercion.
    """
    return {
        "id": _bounded_str(raw["id"], MAX_ID_LEN),
        "title": _bounded_str(raw["title"], MAX_TITLE_LEN),
        "phase": raw["phase"],
        "source_documents": sorted(raw["source_documents"]),
        "purpose": _bounded_str(raw["purpose"], MAX_PURPOSE_LEN),
        "status": raw["status"],
        "prerequisites": sorted(raw["prerequisites"]),
    }


def _normalize_requirement(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _bounded_str(raw["id"], MAX_ID_LEN),
        "roadmap_task_id": _bounded_str(raw["roadmap_task_id"], MAX_ID_LEN),
        "source_document": raw["source_document"],
        "source_anchor": _bounded_str(raw["source_anchor"], MAX_ANCHOR_LEN),
        "phase": raw["phase"],
        "addendum_link": raw["addendum_link"],
        "statement": _bounded_str(raw["statement"], MAX_STATEMENT_LEN),
        "target_layer": raw["target_layer"],
        "status": raw["status"],
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic Roadmap v6 task catalog projection.

    Args:
        generated_at_utc: override the wrapper's report timestamp.
            Tests inject this for byte-stable output.
    """
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    tasks = [_normalize_task(t) for t in _ROADMAP_TASKS_SEED]
    tasks.sort(key=lambda r: (r["phase"], r["id"]))

    requirements = [_normalize_requirement(r) for r in _ROADMAP_REQUIREMENTS_SEED]
    requirements.sort(key=lambda r: (r["phase"], r["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "vocabularies": {
            "phase": list(PHASE),
            "source_document": list(SOURCE_DOCUMENT),
            "status": list(STATUS),
            "addendum_link": list(ADDENDUM_LINK),
            "target_layer": list(TARGET_LAYER),
        },
        "roadmap_tasks": tasks,
        "roadmap_requirements": requirements,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside ``logs/roadmap_task_catalog/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_task_catalog._atomic_write_json refuses "
            f"non-catalog-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_task_catalog.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(snapshot: dict[str, Any]) -> str:
    """Render a compact, human-readable status string. Deterministic."""
    tasks = snapshot["roadmap_tasks"]
    reqs = snapshot["roadmap_requirements"]
    inv = snapshot["discipline_invariants"]
    lines = [
        f"roadmap_task_catalog {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"roadmap_tasks={len(tasks)} roadmap_requirements={len(reqs)}",
        (
            "step5_implementation_allowed="
            f"{snapshot['step5_implementation_allowed']} "
            f"step5_enabled_substage={snapshot['step5_enabled_substage']}"
        ),
        (
            "addendum_2_not_present="
            f"{inv['addendum_2_not_present']} "
            "addendum_3_not_present="
            f"{inv['addendum_3_not_present']}"
        ),
        (
            "diagnostics_do_not_trade="
            f"{inv['diagnostics_do_not_trade']} "
            "external_data_is_not_alpha="
            f"{inv['external_data_is_not_alpha']}"
        ),
    ]
    for t in tasks:
        lines.append(
            f"  task {t['id']} phase={t['phase']} status={t['status']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_task_catalog",
        description=(
            "A20a Static Roadmap v6 Task Catalog Seed. Read-only "
            "deterministic seed for v3.15.16..v3.15.20 plus Addendum 1. "
            "Addendum 2 / Addendum 3 are absent from the repo and "
            "represented only as absence flags. This catalog grants no "
            "implementation, runtime, trading, paper, shadow, broker, "
            "risk, or live authority. Step 5 implementation remains "
            "BLOCKED."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/roadmap_task_catalog/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to stdout "
            "and exit. Does not write any artefact."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snap = collect_snapshot()
    if args.status:
        sys.stdout.write(_render_status(snap))
        return 0
    indent = args.indent if args.indent and args.indent > 0 else None
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
