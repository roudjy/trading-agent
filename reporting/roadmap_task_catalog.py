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
