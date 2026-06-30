"""A20b — Implementation Unit Decomposer (read-only, deterministic).

Converts each :pyfunc:`reporting.roadmap_task_catalog.collect_snapshot`
``RoadmapTask`` into one or more deterministic, PR-sized
``ImplementationUnit`` records and emits a projection at
``logs/roadmap_task_units/latest.json``.

This module is **decomposition data**, not heuristics. The
unit→file mapping is hand-authored as a Python literal pinned by
tests. There is **no** LLM, no fuzzy parsing, no file-content
parsing of canonical roadmap documents at runtime. The decomposer
trusts the A20a catalog as the only upstream and re-classifies
nothing.

This module does **not** call ``execution_authority.classify(...)``.
Per-unit ``authority_hint`` is a deterministic, conservative
projection. Final authority classification is A20c's responsibility
and will replace the hint with the actual classifier output. A20b's
hint never grants implementation authority by itself.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.roadmap_task_catalog`` (read-only) only.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.execution_authority``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``.
* No LLM, no external API, no fuzzy parsing, no file-content
  parsing of any canonical document at runtime.
* Closed vocabularies for ``UNIT_KIND``, ``RISK_CLASS``,
  ``AUTHORITY_HINT``, ``OPERATOR_GATE``, ``UNIT_STATUS``,
  ``TARGET_LAYER``, ``FORBIDDEN_SURFACE_REASON``. Widening any
  requires a code change pinned by an updated unit test.
* Atomic write only under ``logs/roadmap_task_units/``.
* Deterministic output: same upstream + injected
  ``generated_at_utc`` → byte-identical artefact.
* Every emitted unit's ``forbidden_files`` includes the full
  baseline: ``.claude/**``, ``dashboard/dashboard.py``,
  ``research/research_latest.json``,
  ``research/strategy_matrix.csv``,
  ``automation/live_gate.py``, ``broker/**``, ``agent/risk/**``,
  ``agent/execution/**``, ``live/**``, ``paper/**``, ``shadow/**``,
  ``trading/**``, plus the canonical-roadmap and branch-protection
  paths.
* Every unit's ``forbidden_surface_reasons`` includes
  ``frozen_contract``, ``live_path``, ``claude_governance_hook``,
  ``dashboard_wiring``, and ``branch_protection_config`` at
  minimum.
* No unit declares a paper / shadow / live / broker / risk /
  execution surface as an ``expected_files`` target. Each such
  surface is in ``forbidden_files`` of every unit.
* Decomposer creates **zero** units under ``phase == "addendum_2"``
  or ``phase == "addendum_3"`` while the matching source documents
  are absent. Catalog absence flags propagate.
* No unit grants runtime, trading, paper, shadow, broker, risk,
  or live authority.
* ``step5_implementation_allowed`` remains ``False``;
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

CLI::

    python -m reporting.roadmap_task_units
    python -m reporting.roadmap_task_units --no-write
    python -m reporting.roadmap_task_units --status
    python -m reporting.roadmap_task_units --indent 2
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

from reporting import roadmap_task_catalog as rtc

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20b"
REPORT_KIND: Final[str] = "roadmap_task_units"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed implementation-unit kind. Mirrors the surface a unit
#: primarily writes to; aligned with the existing repo layout.
UNIT_KIND: Final[tuple[str, ...]] = (
    "reporting_module",
    "research_module",
    "governance_doc",
    "test_only",
    "schema_only",
    "diagnostic_primitive",
    "external_intelligence_source",
)

#: Closed risk-class vocabulary. Mirrors the four-value enum used by
#: ``reporting.execution_authority`` without importing that module.
#: A20c will replace this hint with the actual classifier output.
RISK_CLASS: Final[tuple[str, ...]] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "UNKNOWN",
)

#: Closed authority-hint vocabulary. A20b values are *candidates*
#: only. A20c will resolve them against the canonical classifier and
#: replace each unit's hint with a real ``ExecutionDecision``.
#: ``UNKNOWN`` inputs MUST fail closed to ``NEEDS_HUMAN_CANDIDATE``.
AUTHORITY_HINT: Final[tuple[str, ...]] = (
    "AUTO_ALLOWED_CANDIDATE",
    "NEEDS_HUMAN_CANDIDATE",
    "PERMANENTLY_DENIED_SURFACE",
)

#: Closed operator-gate vocabulary. ``governance_bootstrap_pr_required``
#: is the strongest gate: only an operator-authored PR may modify the
#: unit's surface.
OPERATOR_GATE: Final[tuple[str, ...]] = (
    "none",
    "operator_go_required",
    "governance_bootstrap_pr_required",
)

#: Closed unit-status vocabulary. Today every unit lands in
#: ``not_started`` — the decomposer records intent, not progress.
UNIT_STATUS: Final[tuple[str, ...]] = (
    "not_started",
    "ready",
    "in_flight",
    "merged",
    "blocked",
    "human_needed",
    "permanently_denied",
)

#: Closed target-layer vocabulary. Verbatim from
#: ``reporting.roadmap_task_catalog.TARGET_LAYER`` so the catalog and
#: the decomposer stay aligned without runtime coupling.
TARGET_LAYER: Final[tuple[str, ...]] = rtc.TARGET_LAYER

#: Closed forbidden-surface-reason vocabulary. Each unit declares
#: the reasons that justify its baseline / extra forbidden_files
#: entries.
FORBIDDEN_SURFACE_REASON: Final[tuple[str, ...]] = (
    "live_path",
    "frozen_contract",
    "claude_governance_hook",
    "dashboard_wiring",
    "branch_protection_config",
    "ci_workflow",
    "canonical_policy_doc",
    "canonical_roadmap",
    "deploy_script",
    "step5_blocked",
    "level6_disabled",
    "n5b_phase4_denied",
    "addendum_2_not_present",
    "addendum_3_not_present",
    "aac_aggregator_pinned",
    "existing_a17_admission_policy",
    "frozen_seed_files",
    "regression_tests_operator_only",
    "frozen_schema_artifacts",
)


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: ``ImplementationUnit`` field list. Exact and ordered.
IMPLEMENTATION_UNIT_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "roadmap_task_id",
    "title",
    "phase",
    "unit_kind",
    "target_layer",
    "source_requirement_ids",
    "expected_files",
    "forbidden_files",
    "forbidden_surface_reasons",
    "required_tests",
    "definition_of_done",
    "stop_conditions",
    "prerequisites",
    "risk_class",
    "authority_hint",
    "operator_gate",
    "status",
)

#: ``UnitDecompositionProjection`` field list. Exact and ordered.
UNIT_DECOMPOSITION_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_catalog_schema_version",
    "implementation_units",
    "decomposition_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_TITLE_LEN: Final[int] = 200
MAX_ID_LEN: Final[int] = 128
MAX_PATH_LEN: Final[int] = 300
MAX_REASON_LEN: Final[int] = 80
MAX_LIST_ITEM_LEN: Final[int] = 240
MAX_EXPECTED_FILES: Final[int] = 16
MAX_FORBIDDEN_FILES: Final[int] = 32
MAX_REQUIRED_TESTS: Final[int] = 16
MAX_DOD_ITEMS: Final[int] = 16
MAX_STOP_CONDITIONS: Final[int] = 16
MAX_PREREQUISITES: Final[int] = 16
MAX_SOURCE_REQUIREMENT_IDS: Final[int] = 32
MAX_FORBIDDEN_SURFACE_REASONS: Final[int] = 16


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_task_units"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/roadmap_task_units/latest.json"

#: Atomic-write allowlist (POSIX path substring form). Any write
#: target whose path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_task_units/"


# ---------------------------------------------------------------------------
# Baseline forbidden files / reasons applied to every unit
# ---------------------------------------------------------------------------

#: Forbidden-file baseline injected into every emitted unit. The
#: ``__contains__`` test fixture asserts that the full baseline is
#: present in every unit's ``forbidden_files``.
BASELINE_FORBIDDEN_FILES: Final[tuple[str, ...]] = (
    ".claude/**",
    "dashboard/dashboard.py",
    "research/research_latest.json",
    "research/strategy_matrix.csv",
    "automation/live_gate.py",
    "broker/**",
    "agent/risk/**",
    "agent/execution/**",
    "live/**",
    "paper/**",
    "shadow/**",
    "trading/**",
    ".github/branch_protection_main.yml",
    "docs/governance/execution_authority.md",
    "docs/governance/no_touch_paths.md",
    "docs/roadmap/Roadmap v6.md",
    "docs/roadmap/Roadmap v6 Addendum.md",
    "docs/roadmap/autonomous_development.txt",
    "docs/development_work_queue/seed.jsonl",
    "docs/development_work_queue/delegation_seed.jsonl",
    "reporting/development_queue_admission_policy.py",
    "reporting/development_agent_activity_timeline.py",
    "reporting/execution_authority.py",
    "tests/regression/**",
    "artifacts/build_provenance.schema.json",
)

#: Reason-baseline injected into every emitted unit's
#: ``forbidden_surface_reasons``.
BASELINE_FORBIDDEN_SURFACE_REASONS: Final[tuple[str, ...]] = (
    "frozen_contract",
    "live_path",
    "claude_governance_hook",
    "dashboard_wiring",
    "branch_protection_config",
    "canonical_policy_doc",
    "canonical_roadmap",
    "existing_a17_admission_policy",
    "aac_aggregator_pinned",
    "frozen_seed_files",
    "regression_tests_operator_only",
    "frozen_schema_artifacts",
    "level6_disabled",
    "n5b_phase4_denied",
)

#: Standard test selectors that every unit must execute as part of
#: its validation. Individual units add their own targeted tests on
#: top of this baseline.
BASELINE_REQUIRED_TESTS: Final[tuple[str, ...]] = (
    "python -m pytest tests/smoke -v",
    "python scripts/governance_lint.py",
    "python -m pytest tests/regression/test_public_output_contract.py "
    "tests/regression/test_v12_contracts_preserved.py "
    "tests/regression/test_authority_invariants.py -v",
)

#: Standard DoD bullets every unit must satisfy on top of its
#: targeted DoD list.
BASELINE_DEFINITION_OF_DONE: Final[tuple[str, ...]] = (
    "module imports cleanly with no forbidden imports",
    "atomic write restricted to the unit's own logs/<module>/ directory",
    "deterministic byte-identical output with injected generated_at_utc",
    "frozen contracts unchanged (research_latest.json, strategy_matrix.csv)",
    (
        "no live / paper / shadow / broker / risk / execution path "
        "changes in the diff"
    ),
    "no dashboard/dashboard.py change",
    "no .claude/** change",
    "no edit to canonical roadmap or canonical policy docs",
    (
        "PR opened via gh pr create (no --admin, no force push, no "
        "hook bypass)"
    ),
)

#: Standard stop conditions every unit honours on top of its targeted
#: stop conditions.
BASELINE_STOP_CONDITIONS: Final[tuple[str, ...]] = (
    "forbidden import or forbidden token found in module source -> STOP, "
    "fix, do not weaken the scan",
    "any forbidden path appears in git diff -> STOP, abort the PR",
    (
        "frozen-contract / public-output regression test fails -> STOP, "
        "do not bypass"
    ),
    "pre-commit or pre-push hook fails -> STOP, fix root cause; no --no-verify",
    "any attempt to grant runtime / trading authority -> STOP, abort",
)


# ---------------------------------------------------------------------------
# Discipline invariants emitted on every projection
# ---------------------------------------------------------------------------

_DECOMPOSITION_INVARIANTS: Final[dict[str, bool]] = {
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
    # A23 made Addendum 2 + 3 repo-resident in docs/roadmap/.
    # Decomposition seed now carries Addendum 2 + 3 ImplementationUnit
    # records; both absence flags flip to False.
    "addendum_2_not_present": False,
    "addendum_3_not_present": False,
    "grants_runtime_authority": False,
    "grants_trading_authority": False,
    "grants_paper_authority": False,
    "grants_shadow_authority": False,
    "grants_broker_authority": False,
    "grants_risk_authority": False,
    "grants_live_authority": False,
    "calls_execution_authority_classifier": False,  # A20c flipped this on in its own projection
    "final_authority_classified": False,  # A20c flipped this on in its own projection
    "next_buildable_selector_present": True,  # A20e selects a deterministic next-buildable unit from A20b rows
    "aac_visibility_present": True,  # A20d surfaces A20b rows via the AAC aggregator
}


# ---------------------------------------------------------------------------
# Hand-encoded ImplementationUnit seed data
# ---------------------------------------------------------------------------
#
# Each entry below is a partial unit. The decomposer merges baseline
# ``forbidden_files`` + baseline ``forbidden_surface_reasons`` +
# baseline ``required_tests`` + baseline ``definition_of_done`` +
# baseline ``stop_conditions`` into every record so the emitted
# projection always satisfies the per-unit invariants pinned by the
# test suite.

# Re-usable helpers --------------------------------------------------------


def _targeted_unit_tests(test_path: str) -> tuple[str, ...]:
    return (
        f"python -m pytest {test_path} -v",
    )


def _governance_doc_dod(doc_path: str) -> tuple[str, ...]:
    return (
        f"{doc_path} written and pinned by an existence-or-content unit test",
        "doc marks the unit as read-only by construction",
        (
            "doc explicitly disclaims runtime / trading / paper / "
            "shadow / broker / risk / live authority"
        ),
    )


def _reporting_module_dod(
    module_dotted: str, artefact_logs_dir: str
) -> tuple[str, ...]:
    return (
        f"{module_dotted} module imports cleanly under stdlib + roadmap_task_catalog only",
        (
            "module exposes deterministic collect_snapshot(...) "
            "with closed vocabularies and bounded scalars"
        ),
        (
            f"atomic write helper refuses every path outside "
            f"{artefact_logs_dir}"
        ),
    )


def _research_module_dod(target_path: str) -> tuple[str, ...]:
    return (
        f"{target_path} created with stdlib-only scaffold",
        (
            "no executable strategy generation; no LLM; no fuzzy "
            "parsing; no broker / order / risk / execution import"
        ),
        (
            "sidecar artefacts only; research_latest.json and "
            "strategy_matrix.csv remain byte-frozen"
        ),
    )


# Unit seed records -------------------------------------------------------

_UNIT_SEED: Final[tuple[dict[str, Any], ...]] = (
    # -------------------- ADE-QRE-017 Trusted Research Intelligence -----
    {
        "id": "u_ade_qre_017a_maturity_matrix_reporter_001",
        "roadmap_task_id": "ade_qre_017a_baseline_reconciliation",
        "title": "Trusted research maturity matrix reporter",
        "phase": "ade_qre_017a",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_ade_qre_017a_maturity_matrix",
            "req_ade_qre_017a_blocker_census",
        ),
        "expected_files": (
            "reporting/qre_trusted_research_maturity_matrix.py",
            "tests/unit/test_qre_trusted_research_maturity_matrix.py",
            "docs/governance/qre_trusted_research_maturity_matrix.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_trusted_research_maturity_matrix.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_trusted_research_maturity_matrix",
            "logs/qre_trusted_research_maturity_matrix/",
        )
        + (
            (
                "matrix emits closed-vocab maturity classes and explicit "
                "blockers for each capability row"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any attempt to infer trusted or evidence-authoritative "
                "status from file presence alone -> STOP"
            ),
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "merged",
    },
    {
        "id": "u_ade_qre_017b_evidence_density_inventory_001",
        "roadmap_task_id": "ade_qre_017b_evidence_density_population",
        "title": "Evidence-density inventory and blocker reporter",
        "phase": "ade_qre_017b",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_ade_qre_017b_evidence_inventory",
        ),
        "expected_files": (
            "reporting/qre_evidence_density_inventory.py",
            "tests/unit/test_qre_evidence_density_inventory.py",
            "docs/governance/qre_evidence_density_inventory.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_evidence_density_inventory.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_evidence_density_inventory",
            "logs/qre_evidence_density_inventory/",
        )
        + (
            (
                "inventory records producers, consumers, population state, "
                "and fail-closed blockers per evidence class"
            ),
        ),
        "extra_stop_conditions": (
            "any evidence class without a bounded status vocabulary -> STOP",
        ),
        "prerequisites": (
            "u_ade_qre_017a_maturity_matrix_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "merged",
    },
    {
        "id": "u_ade_qre_017c_reason_record_maturity_reporter_001",
        "roadmap_task_id": "ade_qre_017c_reason_record_maturity",
        "title": "Reason-record maturity and evidence-linkage reporter",
        "phase": "ade_qre_017c",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_ade_qre_017c_reason_record_linkage",
        ),
        "expected_files": (
            "reporting/qre_reason_record_maturity.py",
            "tests/unit/test_qre_reason_record_maturity.py",
            "docs/governance/qre_reason_record_maturity.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_reason_record_maturity.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_reason_record_maturity",
            "logs/qre_reason_record_maturity/",
        )
        + (
            (
                "reporter fails closed when reason records claim evidence "
                "that is absent or unlinked"
            ),
        ),
        "extra_stop_conditions": (
            "any synthesized reason text without evidence reference -> STOP",
        ),
        "prerequisites": (
            "u_ade_qre_017b_evidence_density_inventory_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "merged",
    },
    {
        "id": "u_ade_qre_017d_readiness_population_reporter_001",
        "roadmap_task_id": "ade_qre_017d_routing_sampling_readiness",
        "title": "Routing and sampling readiness population reporter",
        "phase": "ade_qre_017d",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_ade_qre_017d_readiness_population",
        ),
        "expected_files": (
            "reporting/qre_routing_sampling_readiness.py",
            "tests/unit/test_qre_routing_sampling_readiness.py",
            "docs/governance/qre_routing_sampling_readiness.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_routing_sampling_readiness.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_routing_sampling_readiness",
            "logs/qre_routing_sampling_readiness/",
        )
        + (
            (
                "readiness status distinguishes scaffold from evidence-backed "
                "readiness for routing and sampling surfaces"
            ),
        ),
        "extra_stop_conditions": (
            "any readiness row promoted from scaffold without evidence -> STOP",
        ),
        "prerequisites": (
            "u_ade_qre_017c_reason_record_maturity_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "merged",
    },
    {
        "id": "u_ade_qre_017e_kpi_snapshot_reporter_001",
        "roadmap_task_id": "ade_qre_017e_kpi_snapshot_completeness",
        "title": "KPI completeness and historical snapshot reporter",
        "phase": "ade_qre_017e",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_ade_qre_017e_kpi_snapshots",
        ),
        "expected_files": (
            "reporting/qre_kpi_snapshot_completeness.py",
            "tests/unit/test_qre_kpi_snapshot_completeness.py",
            "docs/governance/qre_kpi_snapshot_completeness.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_kpi_snapshot_completeness.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_kpi_snapshot_completeness",
            "logs/qre_kpi_snapshot_completeness/",
        )
        + (
            (
                "snapshot output records numeric KPI values or explicit "
                "unavailable states with repeatable historical identity"
            ),
        ),
        "extra_stop_conditions": (
            "any KPI row omitted instead of marked unavailable -> STOP",
        ),
        "prerequisites": (
            "u_ade_qre_017d_readiness_population_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "merged",
    },
    {
        "id": "u_ade_qre_018a_queue_baseline_reconciliation_001",
        "roadmap_task_id": "ade_qre_018a_historical_queue_baseline_reconciliation",
        "title": "Historical queue warning classifier and remediation baseline admission",
        "phase": "ade_qre_018a",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/ade_queue_status_self_audit.py",
            "tests/unit/test_ade_queue_status_self_audit.py",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_ade_queue_status_self_audit.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.ade_queue_status_self_audit",
            "logs/ade_queue_status_self_audit/",
        )
        + (
            (
                "historical queue warnings are classified without being hidden, and one deterministic remediation-program selection remains visible",
            ),
        ),
        "extra_stop_conditions": (
            "any change that silently clears historical missing evidence -> STOP",
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018b_blocked_thesis_lineage_census_001",
        "roadmap_task_id": "ade_qre_018b_blocked_thesis_lineage_census",
        "title": "Blocked-thesis lineage census reporter",
        "phase": "ade_qre_018b",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_blocked_thesis_lineage_census.py",
            "tests/unit/test_qre_blocked_thesis_lineage_census.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_blocked_thesis_lineage_census.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_blocked_thesis_lineage_census",
            "logs/qre_blocked_thesis_lineage_census/",
        ),
        "extra_stop_conditions": (
            "any inferred campaign, dataset, or source identity without authoritative evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018a_queue_baseline_reconciliation_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018c_identity_ambiguity_resolution_001",
        "roadmap_task_id": "ade_qre_018c_identity_ambiguity_resolution",
        "title": "Identity ambiguity resolution reporter",
        "phase": "ade_qre_018c",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_identity_ambiguity_resolution.py",
            "tests/unit/test_qre_identity_ambiguity_resolution.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_identity_ambiguity_resolution.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_identity_ambiguity_resolution",
            "logs/qre_identity_ambiguity_resolution/",
        ),
        "extra_stop_conditions": (
            "any fuzzy or alias-only identity acceptance without authoritative support -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018b_blocked_thesis_lineage_census_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018d_campaign_lineage_materialization_001",
        "roadmap_task_id": "ade_qre_018d_campaign_lineage_materialization",
        "title": "Campaign lineage materialization reporter",
        "phase": "ade_qre_018d",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_campaign_lineage_materialization.py",
            "tests/unit/test_qre_campaign_lineage_materialization.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_campaign_lineage_materialization.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_campaign_lineage_materialization",
            "logs/qre_campaign_lineage_materialization/",
        ),
        "extra_stop_conditions": (
            "any executable campaign cell emitted without complete identity and data lineage -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018c_identity_ambiguity_resolution_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018e_null_control_readiness_001",
        "roadmap_task_id": "ade_qre_018e_null_control_specification_completeness",
        "title": "Null-control readiness and completeness reporter",
        "phase": "ade_qre_018e",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_null_control_readiness.py",
            "tests/unit/test_qre_null_control_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_null_control_readiness.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_null_control_readiness",
            "logs/qre_null_control_readiness/",
        ),
        "extra_stop_conditions": (
            "any fixture contract reported as empirical null-control evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018d_campaign_lineage_materialization_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018f_evidence_reason_record_completion_001",
        "roadmap_task_id": "ade_qre_018f_evidence_reason_record_completion",
        "title": "Evidence and reason-record completion reporter",
        "phase": "ade_qre_018f",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_evidence_reason_record_completion.py",
            "tests/unit/test_qre_evidence_reason_record_completion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_evidence_reason_record_completion.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_evidence_reason_record_completion",
            "logs/qre_evidence_reason_record_completion/",
        ),
        "extra_stop_conditions": (
            "any missing empirical evidence represented as authoritative completion -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018e_null_control_readiness_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018g_validation_repro_operator_completion_001",
        "roadmap_task_id": "ade_qre_018g_validation_repro_operator_completion",
        "title": "Validation, reproducibility, and operator completeness reporter",
        "phase": "ade_qre_018g",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_validation_repro_operator_completion.py",
            "tests/unit/test_qre_validation_repro_operator_completion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_validation_repro_operator_completion.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_validation_repro_operator_completion",
            "logs/qre_validation_repro_operator_completion/",
        ),
        "extra_stop_conditions": (
            "any thesis promoted to reproducible or validation-complete without supporting evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018f_evidence_reason_record_completion_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018h_campaign_portfolio_reconstruction_001",
        "roadmap_task_id": "ade_qre_018h_campaign_ready_portfolio_reconstruction",
        "title": "Campaign-ready portfolio reconstruction reporter",
        "phase": "ade_qre_018h",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_campaign_portfolio_reconstruction.py",
            "tests/unit/test_qre_campaign_portfolio_reconstruction.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_campaign_portfolio_reconstruction.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_campaign_portfolio_reconstruction",
            "logs/qre_campaign_portfolio_reconstruction/",
        ),
        "extra_stop_conditions": (
            "any campaign-ready cell emitted when OOS, null-control, identity, or lineage gates remain unresolved -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018g_validation_repro_operator_completion_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018i_rejected_thesis_replacement_plan_001",
        "roadmap_task_id": "ade_qre_018i_replacement_hypothesis_planning",
        "title": "Rejected thesis archive and replacement planning reporter",
        "phase": "ade_qre_018i",
        "unit_kind": "reporting_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_rejected_thesis_replacement_plan.py",
            "tests/unit/test_qre_rejected_thesis_replacement_plan.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_rejected_thesis_replacement_plan.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_rejected_thesis_replacement_plan",
            "logs/qre_rejected_thesis_replacement_plan/",
        ),
        "extra_stop_conditions": (
            "any parameter-only or threshold-only trend-pullback clone treated as a novel replacement -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018h_campaign_portfolio_reconstruction_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018j_second_broad_campaign_prep_001",
        "roadmap_task_id": "ade_qre_018j_second_broad_preregistered_campaign",
        "title": "Second broad preregistered campaign preparation reporter",
        "phase": "ade_qre_018j",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_second_broad_campaign_prep.py",
            "tests/unit/test_qre_second_broad_campaign_prep.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_broad_campaign_prep.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_second_broad_campaign_prep",
            "logs/qre_second_broad_campaign_prep/",
        ),
        "extra_stop_conditions": (
            "any campaign execution launched from the preparation surface -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018i_rejected_thesis_replacement_plan_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_018k_second_synthesis_readiness_review_001",
        "roadmap_task_id": "ade_qre_018k_second_synthesis_readiness_review",
        "title": "Second synthesis-readiness review reporter",
        "phase": "ade_qre_018k",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_second_synthesis_readiness_review.py",
            "tests/unit/test_qre_second_synthesis_readiness_review.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_synthesis_readiness_review.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_second_synthesis_readiness_review",
            "logs/qre_second_synthesis_readiness_review/",
        ),
        "extra_stop_conditions": (
            "any synthesis eligibility emitted before mandatory gates are satisfied -> STOP",
        ),
        "prerequisites": ("u_ade_qre_018j_second_broad_campaign_prep_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019a_generation_governance_migration_001",
        "roadmap_task_id": "ade_qre_019a_generation_authority_governance",
        "title": "ADE-QRE-019 governance migration for isolated generated research",
        "phase": "ade_qre_019a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_automated_strategy_generation_program.md",
            "docs/governance/ade_qre_019_governance_conflict_matrix.md",
            "tests/unit/test_execution_authority.py",
            "tests/unit/test_hooks_no_touch.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_execution_authority.py"
        ),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/roadmap/qre_automated_strategy_generation_program.md"
        )
        + (
            "governance preserves .claude/** immutability and research/** protection",
            "governance admits isolated generated-research surfaces outside research/**",
        ),
        "extra_stop_conditions": (
            "any change that narrows .claude/** protection or general research/** write denial -> STOP",
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019b_typed_spec_contract_001",
        "roadmap_task_id": "ade_qre_019b_typed_strategy_specification_contract",
        "title": "Typed strategy specification and generated path policy",
        "phase": "ade_qre_019b",
        "unit_kind": "schema_only",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/generated_strategy_paths.py",
            "packages/qre_research/automated_strategy_generation.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "typed specification exposes closed fields, versions, and deterministic identity",
            "generated path policy refuses writes into research/** and protected runtime surfaces",
            "schema permits bounded research-only generation only",
        ),
        "extra_stop_conditions": (
            "any arbitrary code, import, or filesystem escape admitted by the specification -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019a_generation_governance_migration_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019c_thesis_compiler_001",
        "roadmap_task_id": "ade_qre_019c_thesis_to_specification_compiler",
        "title": "Behavior thesis to typed specification compiler",
        "phase": "ade_qre_019c",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_strategy_generation.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "compiler emits only closed-vocabulary outcomes",
            "compiler blocks rejected clones, unresolved identities, and unsupported primitives",
            "compiler provenance traces back to authoritative thesis and identity artifacts",
        ),
        "extra_stop_conditions": (
            "any inferred or invented thesis mechanics used to fill missing fields -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019b_typed_spec_contract_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019d_executable_generator_001",
        "roadmap_task_id": "ade_qre_019d_deterministic_executable_strategy_generator",
        "title": "Deterministic generated strategy renderer",
        "phase": "ade_qre_019d",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "agent/backtesting/generated_strategies/generated_qgs_5af8f605ba82ae53.py",
            "packages/qre_research/automated_strategy_generation.py",
            "agent/backtesting/features.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/generated_strategies/test_generated_qgs_5af8f605ba82ae53.py"
        ),
        "extra_definition_of_done": (
            "identical canonical inputs produce byte-identical generated strategy source",
            "generated code uses only allowlisted imports and approved thin-strategy primitives",
            "generated source lives outside protected research/** surfaces",
        ),
        "extra_stop_conditions": (
            "any generated code with import-time side effects, eval, exec, or broker/risk/execution imports -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019c_thesis_compiler_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019e_generated_test_suite_001",
        "roadmap_task_id": "ade_qre_019e_automated_test_generator",
        "title": "Deterministic generated strategy test suite",
        "phase": "ade_qre_019e",
        "unit_kind": "test_only",
        "target_layer": "test",
        "source_requirement_ids": (),
        "expected_files": (
            "tests/generated_strategies/test_generated_qgs_5af8f605ba82ae53.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/generated_strategies/test_generated_qgs_5af8f605ba82ae53.py"
        ),
        "extra_definition_of_done": (
            "generated tests cover deterministic import, interface, warmup, empty input, and boundary conditions",
            "generated tests assert no network, no subprocess, and no file mutation capability",
            "generated tests derive from typed specification rather than free-form source generation",
        ),
        "extra_stop_conditions": (
            "any generated test that weakens or skips a safety boundary -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019d_executable_generator_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019f_static_safety_gate_001",
        "roadmap_task_id": "ade_qre_019f_static_safety_architecture_gate",
        "title": "Static safety, integrity, and architecture validation gate",
        "phase": "ade_qre_019f",
        "unit_kind": "research_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_strategy_generation.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "static gate validates AST safety, allowed imports, manifest integrity, and code/spec traceability",
            "gate quarantines generated strategies that fail policy or architecture checks",
            "no architecture exception is introduced for generated code",
        ),
        "extra_stop_conditions": (
            "any forbidden import edge allowlisted solely to pass generated strategy checks -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019e_generated_test_suite_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019g_sandbox_validation_001",
        "roadmap_task_id": "ade_qre_019g_isolated_sandbox_validation",
        "title": "Isolated sandbox validation for generated strategies",
        "phase": "ade_qre_019g",
        "unit_kind": "research_module",
        "target_layer": "test",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/validation/qgs_5af8f605ba82ae53.json",
            "packages/qre_research/automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "sandbox validation records deterministic technical outcomes only",
            "fixture smoke validation is not promoted to empirical market evidence",
            "validation enforces identity uniqueness and repeated deterministic execution",
        ),
        "extra_stop_conditions": (
            "any fixture result treated as OOS, null-control, or alpha evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019f_static_safety_gate_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019h_generated_registry_admission_001",
        "roadmap_task_id": "ade_qre_019h_automatic_research_only_registration",
        "title": "Automatic generated-registry admission and resolved catalog composition",
        "phase": "ade_qre_019h",
        "unit_kind": "research_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/registry/generated_strategy_registry.v1.json",
            "packages/qre_research/automated_strategy_generation.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "generated registry admits only validated research-only strategies with complete provenance",
            "canonical resolver composes protected manual authority with validated generated entries",
            "resolver excludes collisions, stale manifests, and rejected lineage",
        ),
        "extra_stop_conditions": (
            "any partial registry admission visible through the resolver after a failure -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019g_sandbox_validation_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019i_bounded_preset_generation_001",
        "roadmap_task_id": "ade_qre_019i_automatic_bounded_preset_generation",
        "title": "Automatic bounded research preset generation",
        "phase": "ade_qre_019i",
        "unit_kind": "research_module",
        "target_layer": "preset",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/presets/generated_research_presets.v1.json",
            "packages/qre_research/automated_strategy_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "preset generation is deterministic, bounded, and constrained to approved parameter domains",
            "preset generation performs no search, optimization, or OOS-derived tuning",
            "registered strategies may remain campaign-blocked when no valid preset can be produced",
        ),
        "extra_stop_conditions": (
            "any preset value outside the typed parameter domain -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019h_generated_registry_admission_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019j_null_control_generation_001",
        "roadmap_task_id": "ade_qre_019j_automatic_null_control_specification",
        "title": "Automatic null-control specification generation",
        "phase": "ade_qre_019j",
        "unit_kind": "research_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/lineage/generated_null_controls.v1.json",
            "packages/qre_research/automated_strategy_generation.py",
            "reporting/qre_null_control_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "null-control specifications are mechanism-appropriate and deterministic",
            "deterministic seeds derive from canonical identities only",
            "null-control specifications remain distinct from executed empirical evidence",
        ),
        "extra_stop_conditions": (
            "any null-control specification reported as executed evidence without campaign execution -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019i_bounded_preset_generation_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019k_lineage_portfolio_integration_001",
        "roadmap_task_id": "ade_qre_019k_campaign_lineage_portfolio_integration",
        "title": "Generated lineage and portfolio integration via resolved catalog",
        "phase": "ade_qre_019k",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/lineage/generated_campaign_lineage.v1.json",
            "reporting/qre_blocked_thesis_lineage_census.py",
            "reporting/qre_campaign_lineage_materialization.py",
            "reporting/qre_campaign_portfolio_reconstruction.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_campaign_portfolio_reconstruction",
            "logs/qre_campaign_portfolio_reconstruction/",
        )
        + (
            "reporting surfaces read generated artifacts without importing qre_research implementation modules",
            "generated registry is not consumed as a second authority; the resolved catalog remains sole authority",
        ),
        "extra_stop_conditions": (
            "any reporting module imports generator implementation code across a forbidden boundary -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019j_null_control_generation_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019l_blocked_thesis_pipeline_application_001",
        "roadmap_task_id": "ade_qre_019l_apply_pipeline_to_blocked_theses",
        "title": "Apply ADE-QRE-019 pipeline to blocked theses",
        "phase": "ade_qre_019l",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/specs/qsp_16800da8a94ff0cc.json",
            "generated_research/manifests/qgs_5af8f605ba82ae53.json",
            "generated_research/reports/automated_generation_closeout.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "pipeline records one closed final outcome per blocked thesis",
            "trend_pullback_v1 and rejected clones remain excluded from automated generation",
            "no campaign execution occurs during blocked-thesis pipeline application",
        ),
        "extra_stop_conditions": (
            "any automated application path executes a campaign instead of stopping at readiness artifacts -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019k_lineage_portfolio_integration_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_019m_generation_closeout_001",
        "roadmap_task_id": "ade_qre_019m_automated_generation_closeout",
        "title": "Integrated ADE-QRE-019 closeout reporter",
        "phase": "ade_qre_019m",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "reporting/qre_automated_generation_closeout.py",
            "tests/unit/test_qre_automated_strategy_generation.py",
            "docs/governance/qre_automated_generation_closeout.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.qre_automated_generation_closeout",
            "logs/qre_automated_generation_closeout/",
        )
        + (
            "closeout states whether .claude/** and research/** protections were preserved",
            "closeout records exact automatic-registration and campaign-readiness blockers",
        ),
        "extra_stop_conditions": (
            "any closeout that claims campaign execution, paper, shadow, or live authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_019l_blocked_thesis_pipeline_application_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020a_hypothesis_governance_001",
        "roadmap_task_id": "ade_qre_020a_governance_and_hypothesis_authority",
        "title": "ADE-QRE-020 governance and hypothesis authority admission",
        "phase": "ade_qre_020a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_automated_hypothesis_generation_program.md",
            "docs/governance/ade_qre_020_governance_conflict_matrix.md",
            "packages/qre_research/README.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/roadmap/qre_automated_hypothesis_generation_program.md"
        )
        + (
            "ADE-QRE-020 preserves .claude/** immutability and research/** protection",
            "ADE-QRE-020 delegates executable strategy generation to ADE-QRE-019",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-020 change that permits strategy generation inside A20 or narrows protected research boundaries -> STOP",
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020b_snapshot_inputs_001",
        "roadmap_task_id": "ade_qre_020b_evidence_snapshot_and_opportunity_inputs",
        "title": "Deterministic evidence snapshot for automated hypothesis generation",
        "phase": "ade_qre_020b",
        "unit_kind": "schema_only",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/generated_hypothesis_paths.py",
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/reports/evidence_snapshot.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "evidence snapshot captures authoritative thesis, strategy, contradiction, feedback, and portfolio identities",
            "snapshot identity is deterministic and excludes wall-clock inputs",
        ),
        "extra_stop_conditions": (
            "any snapshot identity derived from clock time, branch names, or PR numbers -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020a_hypothesis_governance_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020c_to_020f_pipeline_001",
        "roadmap_task_id": "ade_qre_020c_research_opportunity_detector",
        "title": "Opportunity, observation, mechanism, and thesis compilation pipeline",
        "phase": "ade_qre_020c",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/opportunities/generated_opportunities.v1.json",
            "generated_research/hypotheses/observations/generated_observations.v1.json",
            "generated_research/hypotheses/mechanisms/generated_mechanisms.v1.json",
            "generated_research/hypotheses/candidates/generated_candidates.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "opportunities, observations, mechanisms, and thesis candidates remain deterministic and provenance-complete",
            "candidate theses describe market behavior rather than executable code",
        ),
        "extra_stop_conditions": (
            "any candidate thesis that embeds executable strategy code or unconstrained prose authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020b_snapshot_inputs_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020g_to_020k_gates_001",
        "roadmap_task_id": "ade_qre_020g_scientific_quality_and_falsifiability_gate",
        "title": "Scientific, novelty, contradiction, testability, and compatibility gates",
        "phase": "ade_qre_020g",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/rejections/generated_thesis_rejections.v1.json",
            "generated_research/hypotheses/priorities/primitive_extension_requests.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "scientific gate rejects unfalsifiable or leakage-prone theses with closed reason vocabularies",
            "compatibility gate distinguishes compilable, extension-blocked, unsupported, unavailable-data, unresolved-identity, and inadmissible states",
        ),
        "extra_stop_conditions": (
            "any thesis distortion solely to fit current ADE-QRE-019 primitives -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020c_to_020f_pipeline_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020l_to_020o_resolver_feedback_001",
        "roadmap_task_id": "ade_qre_020l_automatic_thesis_admission_and_resolver",
        "title": "Generated thesis admission, resolved catalog, prioritization, integration, and feedback",
        "phase": "ade_qre_020l",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
            "generated_research/hypotheses/registry/resolved_thesis_catalog.v1.json",
            "generated_research/hypotheses/priorities/generated_thesis_priorities.v1.json",
            "generated_research/hypotheses/feedback/generated_hypothesis_feedback.v1.json",
            "packages/qre_research/automated_hypothesis_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "generated thesis registry is a controlled input rather than a competing final authority",
            "resolved thesis catalog is the sole resolved research-only thesis authority",
            "ADE-QRE-019 integration preserves its own gates and does not bypass strategy generation safety",
        ),
        "extra_stop_conditions": (
            "any generated thesis visible through a second unresolved authority surface -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020g_to_020k_gates_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020p_to_020q_apply_closeout_001",
        "roadmap_task_id": "ade_qre_020p_apply_to_current_research_state",
        "title": "Apply ADE-QRE-020 to current state and produce integrated closeout",
        "phase": "ade_qre_020p",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/hypotheses/reports/automated_hypothesis_generation_closeout.v1.json",
            "generated_research/hypotheses/reports/automated_hypothesis_generation_closeout.v1.md",
            "tests/unit/test_qre_automated_hypothesis_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "closeout records opportunities, admissions, blocked states, primitive-extension requests, and exact next action",
            "no campaign execution or strategy generation occurs inside ADE-QRE-020",
        ),
        "extra_stop_conditions": (
            "any closeout that claims campaign or synthesis readiness without canonical gate satisfaction -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020l_to_020o_resolver_feedback_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- v3.15.16 Intelligent Routing Layer ------------
    {
        "id": "u_ade_qre_020d_market_observation_builder_001",
        "roadmap_task_id": "ade_qre_020d_market_observation_builder",
        "title": "Deterministic market observation builder",
        "phase": "ade_qre_020d",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/observations/generated_observations.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "observations remain descriptive, uncertainty-aware, and separate from hypotheses",
        ),
        "extra_stop_conditions": (
            "any observation promoted to causal truth without mechanism and falsification context -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020c_to_020f_pipeline_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020e_mechanism_engine_001",
        "roadmap_task_id": "ade_qre_020e_closed_mechanism_proposal_engine",
        "title": "Closed-vocabulary mechanism proposal engine",
        "phase": "ade_qre_020e",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/mechanisms/generated_mechanisms.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "mechanism proposals use a closed causal vocabulary and explicit alternatives",
        ),
        "extra_stop_conditions": (
            "any unconstrained prose mechanism accepted as authoritative -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020d_market_observation_builder_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020f_behavior_thesis_compiler_001",
        "roadmap_task_id": "ade_qre_020f_behavior_thesis_compiler",
        "title": "Typed behavior thesis candidate compiler",
        "phase": "ade_qre_020f",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/candidates/generated_candidates.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "candidate theses carry falsification, validation, OOS, and null-control plans",
        ),
        "extra_stop_conditions": (
            "any executable strategy code emitted by the thesis compiler -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020e_mechanism_engine_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020h_novelty_gate_001",
        "roadmap_task_id": "ade_qre_020h_novelty_and_rejected_lineage_gate",
        "title": "Novelty and rejected-lineage protection",
        "phase": "ade_qre_020h",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/rejections/generated_thesis_rejections.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "duplicates, parameter clones, threshold clones, and rejected-lineage matches fail closed",
        ),
        "extra_stop_conditions": (
            "any trend_pullback_v1 resurrection through cosmetic or threshold-only variation -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020g_to_020k_gates_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020i_contradiction_engine_001",
        "roadmap_task_id": "ade_qre_020i_contradiction_and_alternative_explanation_engine",
        "title": "Contradiction and alternative-explanation ranking",
        "phase": "ade_qre_020i",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/candidates/generated_candidates.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "candidate surfaces expose supporting, contradicting, and alternative explanations",
        ),
        "extra_stop_conditions": (
            "any contradiction retrieval promoted to evidence authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020h_novelty_gate_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020j_testability_estimator_001",
        "roadmap_task_id": "ade_qre_020j_testability_and_signal_density_estimator",
        "title": "Testability and signal-density estimator",
        "phase": "ade_qre_020j",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/candidates/generated_candidates.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "testability states remain estimates and do not become empirical evidence",
        ),
        "extra_stop_conditions": (
            "any estimated signal density reported as empirical campaign evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020i_contradiction_engine_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020k_primitive_compatibility_001",
        "roadmap_task_id": "ade_qre_020k_primitive_compatibility_classifier",
        "title": "Primitive compatibility classification and extension requests",
        "phase": "ade_qre_020k",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/priorities/primitive_extension_requests.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "compatibility classifier distinguishes current-primitive, bounded-extension, unsupported-class, unavailable-data, unresolved-identity, and inadmissible states",
        ),
        "extra_stop_conditions": (
            "any thesis rewritten solely to fit current primitive support -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020j_testability_estimator_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020m_prioritization_001",
        "roadmap_task_id": "ade_qre_020m_hypothesis_prioritization",
        "title": "Transparent prioritization of admitted theses",
        "phase": "ade_qre_020m",
        "unit_kind": "reporting_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/hypotheses/priorities/generated_thesis_priorities.v1.json",
            "packages/qre_research/automated_hypothesis_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "prioritization surfaces explicit score breakdowns and preserves fail-closed zero-admission outcomes",
        ),
        "extra_stop_conditions": (
            "any priority score driven by expected profit alone or previously consumed OOS -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020l_to_020o_resolver_feedback_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020n_a19_integration_001",
        "roadmap_task_id": "ade_qre_020n_ade_qre_019_integration",
        "title": "ADE-QRE-019 submission adapter for admitted hypotheses",
        "phase": "ade_qre_020n",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_hypothesis_generation.py",
            "generated_research/hypotheses/feedback/generated_hypothesis_feedback.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "only compilable admitted theses can reach ADE-QRE-019 and exact downstream outcomes are preserved",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-019 submission that bypasses its compiler or sandbox gates -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020m_prioritization_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020o_feedback_loop_001",
        "roadmap_task_id": "ade_qre_020o_autonomous_feedback_loop",
        "title": "Bounded downstream feedback ingestion for A20",
        "phase": "ade_qre_020o",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/hypotheses/feedback/generated_hypothesis_feedback.v1.json",
            "packages/qre_research/automated_hypothesis_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "feedback loop records downstream generation outcomes without lowering safety or scientific gates",
        ),
        "extra_stop_conditions": (
            "any feedback path that rewrites hypotheses after OOS or lowers admission criteria automatically -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020n_a19_integration_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_020q_integrated_closeout_001",
        "roadmap_task_id": "ade_qre_020q_integrated_closeout",
        "title": "Integrated automated hypothesis-generation closeout",
        "phase": "ade_qre_020q",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/hypotheses/reports/automated_hypothesis_generation_closeout.v1.json",
            "generated_research/hypotheses/reports/automated_hypothesis_generation_closeout.v1.md",
            "packages/qre_research/automated_hypothesis_generation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_hypothesis_generation.py"
        ),
        "extra_definition_of_done": (
            "closeout records opportunities, admissions, extension requests, resolver state, and exact next action",
        ),
        "extra_stop_conditions": (
            "any closeout that invents admissions or downstream generation outcomes -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020p_to_020q_apply_closeout_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021a_governance_authority_001",
        "roadmap_task_id": "ade_qre_021a_primitive_expansion_governance_and_authority",
        "title": "ADE-QRE-021 governance, authority, and generated-primitive path admission",
        "phase": "ade_qre_021a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_automated_bounded_primitive_expansion_program.md",
            "docs/governance/ade_qre_021_governance_conflict_matrix.md",
            "docs/governance/no_touch_paths.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hooks_no_touch.py"
        ),
        "extra_definition_of_done": (
            "ADE-QRE-021 admits isolated generated-primitive surfaces outside research/**",
            "no .claude/** hook change is required or permitted",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-021 change that narrows protected research boundaries -> STOP",
        ),
        "prerequisites": ("u_ade_qre_020q_integrated_closeout_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021b_to_021h_primitive_pipeline_001",
        "roadmap_task_id": "ade_qre_021b_primitive_extension_request_contract",
        "title": "Primitive request validation, specification, generation, validation, and registry admission",
        "phase": "ade_qre_021b",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_primitive_expansion.py",
            "packages/qre_research/generated_primitive_paths.py",
            "generated_research/primitives/registry/generated_primitive_registry.v1.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "bounded primitive requests fail closed unless complete and authoritative",
            "generated primitive admission is atomic and research-only",
        ),
        "extra_stop_conditions": (
            "any arbitrary primitive family expansion without authoritative request -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021a_governance_authority_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021c_primitive_specification_schema_001",
        "roadmap_task_id": "ade_qre_021c_closed_primitive_specification_schema",
        "title": "Closed primitive specification schema for bounded generated primitives",
        "phase": "ade_qre_021c",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_primitive_expansion.py",
            "packages/qre_research/generated_primitive_paths.py",
            "generated_research/primitives/specs/qps_008aa161c214b2b5.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "primitive specifications pin deterministic temporal, grouping, ordering, and missing-data semantics",
        ),
        "extra_stop_conditions": (
            "any primitive specification that permits arbitrary execution semantics -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021b_to_021h_primitive_pipeline_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021d_primitive_implementation_generator_001",
        "roadmap_task_id": "ade_qre_021d_primitive_implementation_generator",
        "title": "Deterministic primitive implementation generator for bounded requests",
        "phase": "ade_qre_021d",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_primitive_expansion.py",
            "agent/backtesting/generated_primitives/generated_qgp_bbfb1728e13038c1.py",
            "generated_research/primitives/manifests/qgp_bbfb1728e13038c1.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "identical primitive inputs regenerate byte-identical source and manifests",
        ),
        "extra_stop_conditions": (
            "any generated primitive implementation with forbidden imports or side effects -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021c_primitive_specification_schema_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021e_primitive_test_generator_001",
        "roadmap_task_id": "ade_qre_021e_primitive_test_generator",
        "title": "Deterministic primitive test generation from the closed primitive schema",
        "phase": "ade_qre_021e",
        "unit_kind": "test_only",
        "target_layer": "test",
        "source_requirement_ids": (),
        "expected_files": (
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py"
        ),
        "extra_definition_of_done": (
            "generated primitive tests cover determinism, shape, safety, and traceability",
        ),
        "extra_stop_conditions": (
            "any generated primitive test that weakens static safety requirements -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021d_primitive_implementation_generator_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021f_static_safety_architecture_validation_001",
        "roadmap_task_id": "ade_qre_021f_static_safety_and_architecture_validation",
        "title": "Static safety, integrity, and architecture validation for generated primitives",
        "phase": "ade_qre_021f",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_primitive_expansion.py",
            "generated_research/primitives/validation/qgp_bbfb1728e13038c1.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "generated primitives fail closed on AST, import, integrity, and package-boundary violations",
        ),
        "extra_stop_conditions": (
            "any architecture exception added to permit generated primitive code -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021e_primitive_test_generator_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021g_primitive_sandbox_validation_001",
        "roadmap_task_id": "ade_qre_021g_primitive_sandbox_validation",
        "title": "Isolated sandbox validation for generated bounded primitives",
        "phase": "ade_qre_021g",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_primitive_expansion.py",
            "generated_research/primitives/validation/qgp_bbfb1728e13038c1.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "sandbox validation proves deterministic repeated execution with no side effects",
        ),
        "extra_stop_conditions": (
            "any generated primitive sandbox run that mutates inputs or writes outside approved surfaces -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021f_static_safety_architecture_validation_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021h_automatic_primitive_registry_admission_001",
        "roadmap_task_id": "ade_qre_021h_automatic_primitive_registry_admission",
        "title": "Automatic generated primitive registry admission and resolved catalog composition",
        "phase": "ade_qre_021h",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "agent/backtesting/features.py",
            "generated_research/primitives/registry/generated_primitive_registry.v1.json",
            "tests/unit/test_qre_automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "only validated generated primitives become visible in the resolved primitive catalog",
        ),
        "extra_stop_conditions": (
            "any partial primitive registry admission or duplicate primitive visibility -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021g_primitive_sandbox_validation_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021i_to_021j_cross_sectional_contract_001",
        "roadmap_task_id": "ade_qre_021i_cross_sectional_data_contract",
        "title": "Cross-sectional panel contract and generated cross_sectional_rank primitive",
        "phase": "ade_qre_021i",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "agent/backtesting/generated_primitives/__init__.py",
            "agent/backtesting/generated_primitives/generated_qgp_bbfb1728e13038c1.py",
            "generated_research/primitives/specs/qps_008aa161c214b2b5.json",
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py"
        ),
        "extra_definition_of_done": (
            "cross_sectional_rank preserves timestamp-only contemporaneous ranking and stable tie handling",
        ),
        "extra_stop_conditions": (
            "any cross-sectional primitive that silently drops assets or uses future data -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021b_to_021h_primitive_pipeline_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021j_cross_sectional_rank_implementation_001",
        "roadmap_task_id": "ade_qre_021j_cross_sectional_rank_implementation",
        "title": "Generated cross_sectional_rank primitive implementation and deterministic contract coverage",
        "phase": "ade_qre_021j",
        "unit_kind": "research_module",
        "target_layer": "strategy_mapping",
        "source_requirement_ids": (),
        "expected_files": (
            "agent/backtesting/generated_primitives/generated_qgp_bbfb1728e13038c1.py",
            "generated_research/primitives/specs/qps_008aa161c214b2b5.json",
            "generated_research/primitives/validation/qgp_bbfb1728e13038c1.json",
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/generated_primitives/test_generated_qgp_bbfb1728e13038c1.py"
        ),
        "extra_definition_of_done": (
            "cross_sectional_rank preserves deterministic breadth, tie, and missing-value semantics",
        ),
        "extra_stop_conditions": (
            "any cross_sectional_rank output that depends on input order or future information -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021i_to_021j_cross_sectional_contract_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021k_to_021m_strategy_replay_001",
        "roadmap_task_id": "ade_qre_021k_automatic_thesis_recompile",
        "title": "Automatic thesis recompile, strategy replay, and readiness reevaluation",
        "phase": "ade_qre_021k",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_strategy_generation.py",
            "agent/backtesting/generated_strategies/generated_qgs_e565b01bd0a162d0.py",
            "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_research/reports/automated_generation_closeout.v1.json",
            "tests/generated_strategies/test_generated_qgs_e565b01bd0a162d0.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "generated cross-sectional strategy remains research-only and campaign readiness stays fail-closed",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-019 replay that bypasses static or sandbox validation -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021i_to_021j_cross_sectional_contract_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021l_automatic_strategy_generation_retest_001",
        "roadmap_task_id": "ade_qre_021l_automatic_strategy_generation_and_retest",
        "title": "Automatic ADE-QRE-019 replay for the newly compilable cross-sectional thesis",
        "phase": "ade_qre_021l",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_strategy_generation.py",
            "agent/backtesting/generated_strategies/generated_qgs_e565b01bd0a162d0.py",
            "generated_research/manifests/qgs_e565b01bd0a162d0.json",
            "tests/generated_strategies/test_generated_qgs_e565b01bd0a162d0.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "ADE-QRE-019 replay preserves all existing strategy safety and registration gates",
        ),
        "extra_stop_conditions": (
            "any automatic strategy replay that bypasses duplicate, identity, or sandbox checks -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021k_to_021m_strategy_replay_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021m_campaign_readiness_reevaluation_001",
        "roadmap_task_id": "ade_qre_021m_campaign_readiness_reevaluation",
        "title": "Campaign readiness reevaluation after primitive expansion and strategy replay",
        "phase": "ade_qre_021m",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/lineage/generated_campaign_lineage.v1.json",
            "generated_research/lineage/generated_null_controls.v1.json",
            "generated_research/presets/generated_research_presets.v1.json",
            "generated_research/reports/automated_generation_closeout.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_strategy_generation.py"
        ),
        "extra_definition_of_done": (
            "campaign readiness remains fail-closed unless preset, data, identity, and null-control gates all pass",
        ),
        "extra_stop_conditions": (
            "any readiness reevaluation that treats technical validation as market evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021l_automatic_strategy_generation_retest_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021n_to_021o_closeout_001",
        "roadmap_task_id": "ade_qre_021n_autonomous_capability_expansion_loop",
        "title": "Autonomous bounded primitive-expansion loop closeout",
        "phase": "ade_qre_021n",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/primitives/reports/automated_primitive_expansion_closeout.v1.json",
            "packages/qre_research/automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "closeout records exact primitive, strategy, and readiness outcomes plus next action",
        ),
        "extra_stop_conditions": (
            "any closeout that reports primitive or strategy validation as empirical evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021k_to_021m_strategy_replay_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_021o_integrated_closeout_001",
        "roadmap_task_id": "ade_qre_021o_integrated_closeout",
        "title": "Integrated ADE-QRE-021 closeout with primitive, strategy, and readiness outcomes",
        "phase": "ade_qre_021o",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/primitives/reports/automated_primitive_expansion_closeout.v1.json",
            "packages/qre_research/automated_primitive_expansion.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_primitive_expansion.py"
        ),
        "extra_definition_of_done": (
            "integrated closeout records exact extension, recompile, replay, and readiness outcomes plus next action",
        ),
        "extra_stop_conditions": (
            "any closeout that overstates readiness or fabricates empirical evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021n_to_021o_closeout_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022a_governance_readiness_authority_001",
        "roadmap_task_id": "ade_qre_022a_governance_and_readiness_authority",
        "title": "Governed admission of deterministic campaign-readiness remediation",
        "phase": "ade_qre_022a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_automated_campaign_identity_readiness_resolution_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "tests/unit/test_roadmap_task_catalog.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_roadmap_task_catalog.py"
        ),
        "extra_definition_of_done": (
            "ADE-QRE-022 is canonically admitted without weakening protected `.claude/**` or `research/**` boundaries",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-022 admission that grants campaign execution or trading authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_021o_integrated_closeout_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022b_readiness_gap_diagnosis_001",
        "roadmap_task_id": "ade_qre_022b_readiness_gap_diagnosis",
        "title": "Deterministic readiness-gap diagnosis for research-registered strategies",
        "phase": "ade_qre_022b",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/gaps/strategy_readiness_gaps.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "aggregate blockers are decomposed into exact field-level readiness gaps with provenance and next actions",
        ),
        "extra_stop_conditions": (
            "any readiness diagnosis that hides exact unresolved fields behind an opaque blocker -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022a_governance_readiness_authority_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022c_identity_resolution_contract_001",
        "roadmap_task_id": "ade_qre_022c_canonical_identity_resolution_contract",
        "title": "Closed identity-resolution contract for campaign readiness",
        "phase": "ade_qre_022c",
        "unit_kind": "schema_only",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/identity_decisions/strategy_identity_decisions.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "only unique authoritative or canonical-alias identities proceed; ambiguity fails closed",
        ),
        "extra_stop_conditions": (
            "any fuzzy or semantic candidate accepted as final identity authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022b_readiness_gap_diagnosis_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022d_instrument_universe_resolution_001",
        "roadmap_task_id": "ade_qre_022d_instrument_and_universe_resolution",
        "title": "Canonical instrument and universe resolution without survivor shortcuts",
        "phase": "ade_qre_022d",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/identity_candidates/strategy_identity_candidates.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "instrument and universe binding stays deterministic and discloses every inclusion or exclusion reason",
        ),
        "extra_stop_conditions": (
            "any universe resolution that silently projects current membership backward through history -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022c_identity_resolution_contract_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022e_data_binding_resolution_001",
        "roadmap_task_id": "ade_qre_022e_source_dataset_snapshot_resolution",
        "title": "Authoritative source, dataset, and snapshot binding for campaign readiness",
        "phase": "ade_qre_022e",
        "unit_kind": "research_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/data_bindings/strategy_data_bindings.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "data bindings distinguish source authority, dataset identity, snapshot identity, schema compatibility, and freshness",
        ),
        "extra_stop_conditions": (
            "any snapshot identity invented without immutable input evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022d_instrument_universe_resolution_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022f_timeframe_regime_binding_001",
        "roadmap_task_id": "ade_qre_022f_timeframe_and_regime_binding",
        "title": "Deterministic timeframe, warmup, rebalance, and regime binding",
        "phase": "ade_qre_022f",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/gaps/strategy_readiness_gaps.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "timeframe and regime bindings remain explicit and reject unsupported cadence or session combinations",
        ),
        "extra_stop_conditions": (
            "any timeframe inferred solely from a strategy or thesis name -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022e_data_binding_resolution_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022g_window_capacity_001",
        "roadmap_task_id": "ade_qre_022g_train_validation_oos_capacity",
        "title": "Deterministic train, validation, OOS, and null-control capacity assessment",
        "phase": "ade_qre_022g",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/window_capacity/strategy_window_capacity.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "consumed or non-independent OOS windows are excluded and capacity remains fail-closed when authoritative coverage is absent",
        ),
        "extra_stop_conditions": (
            "any reused or shifted consumed OOS window reported as independent -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022f_timeframe_regime_binding_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022h_preset_completion_001",
        "roadmap_task_id": "ade_qre_022h_preset_completion",
        "title": "Bounded generated preset completion after identity and window binding",
        "phase": "ade_qre_022h",
        "unit_kind": "research_module",
        "target_layer": "preset",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/presets/strategy_preset_readiness.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "preset completion stays bounded, deterministic, and free of OOS-derived parameter changes",
        ),
        "extra_stop_conditions": (
            "any preset completion that performs parameter search or OOS-aware tuning -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022g_window_capacity_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022i_null_control_execution_readiness_001",
        "roadmap_task_id": "ade_qre_022i_null_control_execution_readiness",
        "title": "Execution-readiness classification for required null controls",
        "phase": "ade_qre_022i",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/null_controls/strategy_null_control_readiness.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "null-control readiness distinguishes specification-only availability from actual execution readiness",
        ),
        "extra_stop_conditions": (
            "any null-control specification reported as empirical completion without execution -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022h_preset_completion_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022j_campaign_metadata_materialization_001",
        "roadmap_task_id": "ade_qre_022j_campaign_metadata_materialization",
        "title": "Fail-closed campaign metadata materialization from resolved readiness inputs",
        "phase": "ade_qre_022j",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/campaigns/generated_campaign_metadata.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "campaign metadata exists only when every mandatory field is authoritative and complete",
        ),
        "extra_stop_conditions": (
            "any campaign metadata row created with unresolved mandatory identities -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022i_null_control_execution_readiness_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022k_campaign_lineage_completion_001",
        "roadmap_task_id": "ade_qre_022k_campaign_lineage_completion",
        "title": "Complete readiness lineage from opportunity through campaign candidate",
        "phase": "ade_qre_022k",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/campaigns/generated_campaign_lineage_resolution.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "lineage detects missing edges, stale links, mismatched hashes, and conflicting identities deterministically",
        ),
        "extra_stop_conditions": (
            "any lineage completion that hides orphaned readiness artifacts -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022j_campaign_metadata_materialization_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022l_portfolio_prereg_reevaluation_001",
        "roadmap_task_id": "ade_qre_022l_portfolio_and_preregistration_reevaluation",
        "title": "Portfolio status rebuild and preregistration reevaluation without campaign execution",
        "phase": "ade_qre_022l",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/campaigns/generated_portfolio_readiness.v1.json",
            "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "only genuinely ready cells enter a second-campaign manifest and zero-ready outcomes remain explicit",
        ),
        "extra_stop_conditions": (
            "any preregistration manifest created from blocked or insufficient-evidence cells -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022k_campaign_lineage_completion_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022m_autonomous_readiness_loop_001",
        "roadmap_task_id": "ade_qre_022m_autonomous_readiness_remediation_loop",
        "title": "General deterministic readiness-remediation loop with governed feedback routes",
        "phase": "ade_qre_022m",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_campaign_readiness.py",
            "generated_research/readiness/reports/automated_campaign_readiness_closeout.v1.json",
            "tests/unit/test_qre_automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "remaining readiness blockers feed back deterministically to thesis, primitive, identity, or data remediation without lowering gates",
        ),
        "extra_stop_conditions": (
            "any automatic readiness loop that lowers acceptance criteria after failure -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022l_portfolio_prereg_reevaluation_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022n_apply_to_current_generated_strategies_001",
        "roadmap_task_id": "ade_qre_022n_apply_to_qgs_e565b01bd0a162d0",
        "title": "Apply readiness remediation to the resolver-visible generated strategies",
        "phase": "ade_qre_022n",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/readiness/gaps/strategy_readiness_gaps.v1.json",
            "generated_research/readiness/campaigns/generated_portfolio_readiness.v1.json",
            "generated_research/readiness/reports/automated_campaign_readiness_closeout.v1.json",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "qgs_e565b01bd0a162d0 and qgs_5af8f605ba82ae53 receive exact readiness diagnoses and fail-closed reevaluation outcomes",
        ),
        "extra_stop_conditions": (
            "any current-strategy readiness replay that forces equal outcomes across different blocker sets -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022m_autonomous_readiness_loop_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_022o_integrated_closeout_001",
        "roadmap_task_id": "ade_qre_022o_integrated_closeout",
        "title": "Integrated ADE-QRE-022 closeout with exact readiness blockers and next action",
        "phase": "ade_qre_022o",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "generated_research/readiness/reports/automated_campaign_readiness_closeout.v1.json",
            "packages/qre_research/automated_campaign_readiness.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_campaign_readiness.py"
        ),
        "extra_definition_of_done": (
            "closeout records exact identity, data, window, null-control, lineage, and portfolio outcomes plus the next permitted action",
        ),
        "extra_stop_conditions": (
            "any closeout that overstates campaign readiness or invents a preregistration path -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022n_apply_to_current_generated_strategies_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023a_autonomous_closure_governance_001",
        "roadmap_task_id": "ade_qre_023a_autonomous_closure_governance",
        "title": "Governed admission of the ADE-QRE-023 autonomous readiness-closure loop",
        "phase": "ade_qre_023a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_autonomous_readiness_closure_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "tests/unit/test_roadmap_task_catalog.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_roadmap_task_catalog.py"
        ),
        "extra_definition_of_done": (
            "ADE-QRE-023 is canonically admitted without weakening `.claude/**`, protected `research/**`, or trading-authority boundaries",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-023 admission that grants campaign execution or trading authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_022o_integrated_closeout_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023b_blocker_taxonomy_dependency_graph_001",
        "roadmap_task_id": "ade_qre_023b_blocker_taxonomy_and_dependency_graph",
        "title": "Typed blocker taxonomy and dependency ordering for autonomous closure",
        "phase": "ade_qre_023b",
        "unit_kind": "schema_only",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_readiness_blockers.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "blocker classes and dependency ordering keep the loop focused on upstream causes before downstream symptoms",
        ),
        "extra_stop_conditions": (
            "any blocker ordering that prioritizes downstream symptoms over unresolved upstream authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023a_autonomous_closure_governance_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023c_remediation_planner_001",
        "roadmap_task_id": "ade_qre_023c_remediation_planner",
        "title": "Deterministic remediation planner for governed readiness blockers",
        "phase": "ade_qre_023c",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_readiness_iteration_ledger.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "every blocker maps to exactly one deterministic remediation class or fail-closed terminal path",
        ),
        "extra_stop_conditions": (
            "any remediation plan selected without matching authority or evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023b_blocker_taxonomy_dependency_graph_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023d_universe_authority_001",
        "roadmap_task_id": "ade_qre_023d_canonical_universe_authority",
        "title": "Canonical resolved universe authority and alias closure",
        "phase": "ade_qre_023d",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "canonical universes, alias mappings, and point-in-time membership snapshots remain deterministic and fail closed on ambiguity",
        ),
        "extra_stop_conditions": (
            "any universe authority that backfills current membership through history or accepts symbol-only identity -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023c_remediation_planner_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023e_historical_membership_001",
        "roadmap_task_id": "ade_qre_023e_historical_universe_membership",
        "title": "Historical point-in-time universe membership evidence and breadth validation",
        "phase": "ade_qre_023e",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "universe membership records disclose inclusion, exclusion, and minimum-breadth evidence for each strategy cell",
        ),
        "extra_stop_conditions": (
            "any member silently dropped from a cross-sectional universe without a reason record -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023d_universe_authority_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023f_timeframe_resolution_001",
        "roadmap_task_id": "ade_qre_023f_timeframe_resolution",
        "title": "Deterministic timeframe resolution and multi-cell split handling",
        "phase": "ade_qre_023f",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_timeframe_resolution.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "ambiguous strategies are deterministically split into distinct campaign cells rather than silently selecting one timeframe",
        ),
        "extra_stop_conditions": (
            "any timeframe selected solely from a strategy or thesis name -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023e_historical_membership_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023g_preset_completion_001",
        "roadmap_task_id": "ade_qre_023g_preset_completion",
        "title": "Bounded preset completion after authoritative readiness binding",
        "phase": "ade_qre_023g",
        "unit_kind": "research_module",
        "target_layer": "preset",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/presets/autonomous_completed_presets.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "preset completion remains deterministic, bounded, and free of OOS-aware parameter search",
        ),
        "extra_stop_conditions": (
            "any preset completion that changes parameters outside approved domains or uses OOS-derived values -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023f_timeframe_resolution_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023h_source_dataset_snapshot_binding_001",
        "roadmap_task_id": "ade_qre_023h_source_dataset_and_snapshot_binding",
        "title": "Authoritative source, dataset, and snapshot closure for readiness replay",
        "phase": "ade_qre_023h",
        "unit_kind": "research_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/data_bindings/autonomous_strategy_data_bindings.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "source, dataset, schema, coverage, and immutable snapshot bindings remain authoritative and deterministic",
        ),
        "extra_stop_conditions": (
            "any snapshot identity invented without immutable local input evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023g_preset_completion_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023i_window_oos_capacity_001",
        "roadmap_task_id": "ade_qre_023i_window_and_independent_oos_capacity",
        "title": "Deterministic train, validation, and independent OOS capacity closure",
        "phase": "ade_qre_023i",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/window_capacity/autonomous_window_capacity.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "window capacity discloses exact coverage and fails closed when authoritative independent OOS assignment cannot be proven",
        ),
        "extra_stop_conditions": (
            "any reused or shifted consumed OOS window reported as independent -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023h_source_dataset_snapshot_binding_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023j_null_control_closure_001",
        "roadmap_task_id": "ade_qre_023j_null_control_implementation_closure",
        "title": "Execution-readiness closure for required null controls",
        "phase": "ade_qre_023j",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/null_controls/autonomous_null_control_readiness.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "null-control readiness distinguishes execution-ready controls from specification-only surfaces without fabricating empirical nulls",
        ),
        "extra_stop_conditions": (
            "any null-control report that implies empirical completion before execution -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023i_window_oos_capacity_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023k_cost_slippage_regime_binding_001",
        "roadmap_task_id": "ade_qre_023k_cost_slippage_and_regime_binding",
        "title": "Deterministic cost, slippage, and regime binding for campaign readiness",
        "phase": "ade_qre_023k",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/campaigns/autonomous_campaign_metadata.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "costs, slippage, sessions, timezones, and regime identities are explicit before a campaign cell can be ready",
        ),
        "extra_stop_conditions": (
            "any zero-cost or zero-slippage assumption introduced without explicit policy evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023j_null_control_closure_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023l_campaign_metadata_lineage_closure_001",
        "roadmap_task_id": "ade_qre_023l_campaign_metadata_and_lineage_closure",
        "title": "Campaign metadata and lineage closure from readiness inputs",
        "phase": "ade_qre_023l",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/campaigns/autonomous_campaign_metadata.v1.json",
            "generated_research/readiness/campaigns/autonomous_campaign_lineage.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "campaign metadata and lineage exist only when every mandatory upstream field is authoritative and complete",
        ),
        "extra_stop_conditions": (
            "any lineage row that hides stale, orphaned, or mismatched edges -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023k_cost_slippage_regime_binding_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023m_capability_generator_integration_001",
        "roadmap_task_id": "ade_qre_023m_autonomous_capability_generator_integration",
        "title": "Integration of autonomous closure with governed remediation generators",
        "phase": "ade_qre_023m",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_readiness_iteration_ledger.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "remaining blockers route to existing governed generators or fail closed without widening authority",
        ),
        "extra_stop_conditions": (
            "any autonomous remediation that bypasses ADE-QRE-019/020/021/022 guardrails -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023l_campaign_metadata_lineage_closure_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023n_iterative_readiness_replay_001",
        "roadmap_task_id": "ade_qre_023n_iterative_readiness_replay",
        "title": "Bounded iterative readiness replay with causal-progress evidence",
        "phase": "ade_qre_023n",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_readiness_iteration_ledger.v1.json",
            "generated_research/readiness/reports/autonomous_readiness_closeout.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "the replay loop records iterations, detects cycles, enforces bounds, and demonstrates causal progress or irreducible fail-closed outcomes",
        ),
        "extra_stop_conditions": (
            "any replay loop that regenerates equivalent artifacts without blocker progress and still claims remediation -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023m_capability_generator_integration_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023o_second_campaign_prereg_001",
        "roadmap_task_id": "ade_qre_023o_second_campaign_preregistration",
        "title": "Second-campaign preregistration only from genuinely ready cells",
        "phase": "ade_qre_023o",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/campaigns/autonomous_second_campaign_manifest.v1.json",
            "generated_research/readiness/campaigns/autonomous_portfolio_readiness.v1.json",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "a manifest is written only when at least one portfolio cell is genuinely READY_FOR_PREREGISTRATION",
        ),
        "extra_stop_conditions": (
            "any second-campaign manifest created from blocked or insufficient-evidence cells -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023n_iterative_readiness_replay_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_023p_integrated_closure_report_001",
        "roadmap_task_id": "ade_qre_023p_integrated_closure_report",
        "title": "Integrated ADE-QRE-023 closeout with terminal outcomes and exact next action",
        "phase": "ade_qre_023p",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/autonomous_readiness_closure.py",
            "generated_research/readiness/reports/autonomous_readiness_closeout.v1.json",
            "generated_research/readiness/reports/autonomous_readiness_closeout.v1.md",
            "tests/unit/test_qre_autonomous_readiness_closure.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_autonomous_readiness_closure.py"
        ),
        "extra_definition_of_done": (
            "closeout records strategies processed, iterations, blockers resolved, irreducible blockers, manifest status, and the exact next permitted action",
        ),
        "extra_stop_conditions": (
            "any closeout that overstates readiness or fabricates a campaign path -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023o_second_campaign_prereg_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024a_governance_data_window_authority_001",
        "roadmap_task_id": "ade_qre_024a_governance_and_data_window_authority",
        "title": "Governed admission of the deterministic ADE-QRE-024 data/window remediation loop",
        "phase": "ade_qre_024a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_automated_data_capacity_window_assignment_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "tests/unit/test_roadmap_task_catalog.py",
            "tests/unit/test_roadmap_task_units.py",
            "tests/unit/test_roadmap_next_unit.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": (
            "python -m pytest tests/unit/test_roadmap_task_catalog.py -v",
            "python -m pytest tests/unit/test_roadmap_task_units.py -v",
            "python -m pytest tests/unit/test_roadmap_next_unit.py -v",
        ),
        "extra_definition_of_done": (
            "ADE-QRE-024 is admitted canonically with research-only authority and no protected-surface weakening",
        ),
        "extra_stop_conditions": (
            "any governance text that weakens .claude/** or protected research/** -> STOP",
        ),
        "prerequisites": ("u_ade_qre_023p_integrated_closure_report_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024b_data_capacity_diagnosis_001",
        "roadmap_task_id": "ade_qre_024b_data_capacity_diagnosis",
        "title": "Deterministic campaign-cell data-capacity diagnosis",
        "phase": "ade_qre_024b",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/data_capacity/strategy_data_capacity_diagnosis.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "diagnosis records exact cache, coverage, snapshot, and point-in-time blockers per campaign cell",
        ),
        "extra_stop_conditions": (
            "any diagnosis that invents coverage or external availability -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024a_governance_data_window_authority_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024c_canonical_data_cache_authority_001",
        "roadmap_task_id": "ade_qre_024c_canonical_data_binding_and_cache_authority",
        "title": "Canonical data/cache authority resolver for campaign readiness",
        "phase": "ade_qre_024c",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/data_capacity/canonical_data_cache_authority.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "resolver exposes one canonical source/dataset/cache-row/snapshot view per cell",
        ),
        "extra_stop_conditions": (
            "any competing final data authority or alias-only authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024b_data_capacity_diagnosis_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024d_missing_cache_row_materialization_001",
        "roadmap_task_id": "ade_qre_024d_missing_cache_row_materialization",
        "title": "Governed local cache-row materialization and fail-closed data-source detection",
        "phase": "ade_qre_024d",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/data_capacity/materialized_cache_rows.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "missing rows are materialized only from governed local inputs or remain fail-closed with exact reasons",
        ),
        "extra_stop_conditions": (
            "any arbitrary external fetch or fabricated cache row -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024c_canonical_data_cache_authority_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024e_data_quality_coverage_validation_001",
        "roadmap_task_id": "ade_qre_024e_data_quality_and_coverage_validation",
        "title": "Deterministic data-quality and usable-coverage validation",
        "phase": "ade_qre_024e",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "quality report records usable range, blockers, and stable quality identity",
        ),
        "extra_stop_conditions": (
            "any interpolation promoted as authoritative market evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024d_missing_cache_row_materialization_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024f_immutable_snapshot_materialization_001",
        "roadmap_task_id": "ade_qre_024f_immutable_snapshot_materialization",
        "title": "Immutable content-addressed strategy snapshots for campaign cells",
        "phase": "ade_qre_024f",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "snapshots freeze source, dataset, coverage, schema, hashes, and point-in-time universe context deterministically",
        ),
        "extra_stop_conditions": (
            "any snapshot identity derived from wall-clock or branch state -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024e_data_quality_coverage_validation_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024g_authoritative_window_policy_001",
        "roadmap_task_id": "ade_qre_024g_authoritative_window_policy",
        "title": "Versioned deterministic train/validation/OOS assignment policy",
        "phase": "ade_qre_024g",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_capacity/authoritative_window_policy.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "policy assigns windows deterministically without inspecting returns or campaign outcomes",
        ),
        "extra_stop_conditions": (
            "any performance-aware or post-hoc window selection -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024f_immutable_snapshot_materialization_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024h_window_ledger_registry_001",
        "roadmap_task_id": "ade_qre_024h_window_ledger_and_consumption_registry",
        "title": "Canonical window ledger and reservation registry",
        "phase": "ade_qre_024h",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "ledger prevents consumed OOS reuse, overlap relabeling, and silent window shifts",
        ),
        "extra_stop_conditions": (
            "any consumed OOS reuse or silent overlapping-independent claim -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024g_authoritative_window_policy_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024i_window_assignment_001",
        "roadmap_task_id": "ade_qre_024i_train_validation_oos_assignment",
        "title": "Deterministic train/validation/OOS assignment and reservation",
        "phase": "ade_qre_024i",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "valid cells receive deterministic train, validation, OOS, warmup, and embargo assignments with provenance",
        ),
        "extra_stop_conditions": (
            "any window chosen from performance or silent multiple-choice collapse -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024h_window_ledger_registry_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024j_oos_independence_proof_001",
        "roadmap_task_id": "ade_qre_024j_oos_independence_and_leakage_proof",
        "title": "Machine-readable OOS independence and leakage proof",
        "phase": "ade_qre_024j",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "OOS windows proceed only when unseen, non-reused, non-overlapping where required, and embargo-compliant",
        ),
        "extra_stop_conditions": (
            "any fabricated independence proof or hidden overlap -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024i_window_assignment_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024k_pit_universe_breadth_validation_001",
        "roadmap_task_id": "ade_qre_024k_point_in_time_universe_and_breadth_validation",
        "title": "Point-in-time universe and breadth validation for campaign cells",
        "phase": "ade_qre_024k",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_capacity/point_in_time_universe_validation.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "point-in-time universe membership, listing state, and breadth are validated without survivor backfill",
        ),
        "extra_stop_conditions": (
            "any current-universe backfill or silent member substitution -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024j_oos_independence_proof_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024l_signal_density_capacity_001",
        "roadmap_task_id": "ade_qre_024l_signal_density_capacity_validation",
        "title": "Signal-density and sample-capacity validation without returns",
        "phase": "ade_qre_024l",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "expected signals and trades are estimated from non-performance evidence and remain fail-closed when insufficient",
        ),
        "extra_stop_conditions": (
            "any automatic signal-threshold relaxation -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024k_pit_universe_breadth_validation_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024m_iterative_data_window_closure_001",
        "roadmap_task_id": "ade_qre_024m_iterative_data_window_closure_loop",
        "title": "Bounded autonomous data/window remediation loop with progress ledger",
        "phase": "ade_qre_024m",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/reports/automated_data_window_iteration_ledger.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "loop records before blockers, selected remediation, created artifacts, after blockers, and progress classification per iteration",
        ),
        "extra_stop_conditions": (
            "any endless equivalent regeneration or silent no-progress loop -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024l_signal_density_capacity_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024n_downstream_readiness_replay_001",
        "roadmap_task_id": "ade_qre_024n_downstream_readiness_replay",
        "title": "Automatic downstream readiness replay after data/window remediation",
        "phase": "ade_qre_024n",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "portfolio and readiness replay update automatically after each successful upstream data/window change",
        ),
        "extra_stop_conditions": (
            "any operator-prompt requirement between remediation iterations -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024m_iterative_data_window_closure_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024o_second_campaign_prereg_001",
        "roadmap_task_id": "ade_qre_024o_second_campaign_preregistration",
        "title": "Second-campaign preregistration from genuinely ready campaign cells",
        "phase": "ade_qre_024o",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "manifest is created only when at least one cell is genuinely READY_FOR_PREREGISTRATION",
        ),
        "extra_stop_conditions": (
            "any manifest created from blocked or insufficient-evidence cells -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024n_downstream_readiness_replay_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_024p_integrated_closeout_001",
        "roadmap_task_id": "ade_qre_024p_integrated_closeout",
        "title": "Integrated ADE-QRE-024 closeout with resolved blockers, manifest status, and next action",
        "phase": "ade_qre_024p",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/automated_data_window_capacity.py",
            "generated_research/readiness/reports/automated_data_window_capacity_closeout.v1.json",
            "generated_research/readiness/reports/automated_data_window_capacity_closeout.v1.md",
            "tests/unit/test_qre_automated_data_window_capacity.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_automated_data_window_capacity.py"
        ),
        "extra_definition_of_done": (
            "closeout records campaign cells processed, data blockers, snapshots, window assignments, independence proof, readiness replay, and the exact next permitted action",
        ),
        "extra_stop_conditions": (
            "any closeout that overstates readiness or invents independence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024o_second_campaign_prereg_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025a_campaign_execution_governance_001",
        "roadmap_task_id": "ade_qre_025a_campaign_execution_governance",
        "title": "Governed admission of frozen second-campaign execution and post-campaign research loop",
        "phase": "ade_qre_025a",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "docs/roadmap/qre_execute_second_preregistered_campaign_program.md",
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md",
            "tests/unit/test_roadmap_task_catalog.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_roadmap_task_catalog.py"
        ),
        "extra_definition_of_done": (
            "ADE-QRE-025 is canonically admitted as the execution successor to the scientifically unblocked second-campaign path without granting any non-research authority",
        ),
        "extra_stop_conditions": (
            "any ADE-QRE-025 admission that grants paper, shadow, live, broker, risk, or deployment authority -> STOP",
        ),
        "prerequisites": ("u_ade_qre_024p_integrated_closeout_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025b_manifest_integrity_verification_001",
        "roadmap_task_id": "ade_qre_025b_manifest_integrity_verification",
        "title": "Deterministic verifier for the frozen second-campaign manifest and all dependent identities",
        "phase": "ade_qre_025b",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/integrity/manifest_integrity_verification.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "campaign execution fails closed unless manifest identity, strategy hash, preset, dataset, snapshot, windows, and null controls all match the frozen preregistration state",
        ),
        "extra_stop_conditions": (
            "any manifest mismatch silently repaired or regenerated in-place -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025a_campaign_execution_governance_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025c_deterministic_campaign_runner_001",
        "roadmap_task_id": "ade_qre_025c_deterministic_campaign_runner",
        "title": "Deterministic runner that executes only the single ready preregistered campaign cell",
        "phase": "ade_qre_025c",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/runs/second_campaign_execution.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "only qrcell_fdd68e20fd2724dd executes; blocked manifest cells remain excluded and no frozen input mutates during execution",
        ),
        "extra_stop_conditions": (
            "any blocked cell admitted into execution or any mutable manifest field changed after execution begins -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025b_manifest_integrity_verification_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025d_train_screening_execution_001",
        "roadmap_task_id": "ade_qre_025d_train_and_screening_execution",
        "title": "Frozen train-window execution and screening accounting",
        "phase": "ade_qre_025d",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/stages/train_and_screening.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "train and screening metrics, signals, trades, and threshold distances are persisted without any adaptive parameter changes",
        ),
        "extra_stop_conditions": (
            "any train result used to change parameters, windows, or criteria -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025c_deterministic_campaign_runner_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025e_validation_execution_001",
        "roadmap_task_id": "ade_qre_025e_validation_execution",
        "title": "Frozen validation-window execution with degradation and stability reporting",
        "phase": "ade_qre_025e",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/stages/validation.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "validation runs only when screening permits it and records exact pass/fail reasons plus train-to-validation degradation",
        ),
        "extra_stop_conditions": (
            "any validation replay with altered preset, costs, windows, or thresholds -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025d_train_screening_execution_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025f_oos_execution_001",
        "roadmap_task_id": "ade_qre_025f_oos_execution",
        "title": "Exact reserved OOS execution with canonical consumption evidence",
        "phase": "ade_qre_025f",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/stages/oos.v1.json",
            "generated_research/campaign_execution/window_ledger/oos_consumption.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "the exact preregistered OOS window executes once, is marked consumed in the canonical ledger, and cannot be reused as independent evidence",
        ),
        "extra_stop_conditions": (
            "any shifted, overlapping, or replayed OOS window treated as new independent evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025e_validation_execution_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025g_null_control_execution_001",
        "roadmap_task_id": "ade_qre_025g_null_control_execution",
        "title": "Execution of manifest-frozen null controls with deterministic seeds",
        "phase": "ade_qre_025g",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/stages/null_controls.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "each required null control executes against the frozen snapshot, window, and preset and is persisted as authoritative executed evidence",
        ),
        "extra_stop_conditions": (
            "any null-control specification treated as executed evidence without an actual run artifact -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025f_oos_execution_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025h_evidence_reason_record_completion_001",
        "roadmap_task_id": "ade_qre_025h_evidence_and_reason_record_completion",
        "title": "Complete campaign evidence, reason-record, and reproducibility accounting",
        "phase": "ade_qre_025h",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/evidence/campaign_evidence_accounting.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "every stage decision is linked to authoritative metrics, policies, reasons, provenance, and replay identity",
        ),
        "extra_stop_conditions": (
            "any decision state without linked metric, policy, or source artifact -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025g_null_control_execution_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025i_funnel_diagnosis_001",
        "roadmap_task_id": "ade_qre_025i_funnel_diagnosis",
        "title": "Deterministic campaign-funnel diagnosis with threshold distances and bottlenecks",
        "phase": "ade_qre_025i",
        "unit_kind": "reporting_module",
        "target_layer": "funnel",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/funnel_diagnosis.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "the executed funnel records counts, conversions, threshold distances, primary bottleneck, secondary bottlenecks, and one bounded recommendation per criterion",
        ),
        "extra_stop_conditions": (
            "any funnel diagnosis that changes the criteria it is supposed to diagnose -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025h_evidence_reason_record_completion_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025j_hypothesis_strategy_decision_001",
        "roadmap_task_id": "ade_qre_025j_hypothesis_and_strategy_decision",
        "title": "Canonical research-only hypothesis and strategy decisions from campaign evidence",
        "phase": "ade_qre_025j",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/hypothesis_strategy_decision.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "one canonical hypothesis decision and one canonical strategy decision are emitted without any paper, shadow, live, or deployment promotion",
        ),
        "extra_stop_conditions": (
            "any decision artifact that implies candidate-quality, deployment, or trading promotion -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025i_funnel_diagnosis_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025k_recalibration_decision_001",
        "roadmap_task_id": "ade_qre_025k_recalibration_decision",
        "title": "Bounded one-class-only recalibration decision gate",
        "phase": "ade_qre_025k",
        "unit_kind": "reporting_module",
        "target_layer": "policy",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/recalibration_decision.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "recalibration is justified only when one bounded criterion class is demonstrably mislocated and all other frozen campaign inputs remain unchanged",
        ),
        "extra_stop_conditions": (
            "any multi-criterion or post-OOS-tuned recalibration decision -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025j_hypothesis_strategy_decision_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025l_same_input_replay_001",
        "roadmap_task_id": "ade_qre_025l_same_input_replay",
        "title": "Same-input replay that preserves consumed-OOS semantics",
        "phase": "ade_qre_025l",
        "unit_kind": "research_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/same_input_replay.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "replay runs only when canonically justified and records that replayed OOS is not new independent evidence",
        ),
        "extra_stop_conditions": (
            "any replay result labeled as new unseen OOS evidence -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025k_recalibration_decision_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025m_independent_oos_assessment_001",
        "roadmap_task_id": "ade_qre_025m_independent_oos_assessment",
        "title": "Independent-OOS availability assessment using the canonical window ledger",
        "phase": "ade_qre_025m",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/independent_oos_assessment.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "the system proves or blocks future independent OOS availability without subdividing, shifting, or reusing the consumed OOS window",
        ),
        "extra_stop_conditions": (
            "any consumed or overlapping OOS window relabeled as independent -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025l_same_input_replay_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025n_autonomous_feedback_routing_001",
        "roadmap_task_id": "ade_qre_025n_autonomous_feedback_routing",
        "title": "Deterministic next-program routing from the campaign closeout evidence",
        "phase": "ade_qre_025n",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/autonomous_feedback_routing.v1.json",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "exactly one next machine-routable research action is selected from the closed campaign closeout vocabulary",
        ),
        "extra_stop_conditions": (
            "any feedback route that mutates strategy parameters or launches an ungoverned execution path -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025m_independent_oos_assessment_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_ade_qre_025o_integrated_campaign_closeout_001",
        "roadmap_task_id": "ade_qre_025o_integrated_campaign_closeout",
        "title": "Integrated A25 closeout with manifest verification, campaign evidence, decisions, and terminal outcome",
        "phase": "ade_qre_025o",
        "unit_kind": "reporting_module",
        "target_layer": "governance",
        "source_requirement_ids": (),
        "expected_files": (
            "packages/qre_research/second_preregistered_campaign.py",
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.md",
            "tests/unit/test_qre_second_preregistered_campaign.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_qre_second_preregistered_campaign.py"
        ),
        "extra_definition_of_done": (
            "closeout records manifest verification, executed cell, excluded blocked cells, train/validation/OOS/null outcomes, OOS consumption, decisions, next action, and terminal campaign status",
        ),
        "extra_stop_conditions": (
            "any closeout that executes a new campaign or mutates the frozen manifest during reporting -> STOP",
        ),
        "prerequisites": ("u_ade_qre_025n_autonomous_feedback_routing_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_16_diagnostic_routing_signals_schema_001",
        "roadmap_task_id": "phase_v3_15_16",
        "title": (
            "Read-only diagnostic-aware routing-signals schema and "
            "projector"
        ),
        "phase": "v3.15.16",
        "unit_kind": "reporting_module",
        "target_layer": "campaign",
        "source_requirement_ids": (
            "req_v3_15_16_behavior_aware_routing",
            "req_v3_15_16_diagnostic_aware_routing",
        ),
        "expected_files": (
            "reporting/intelligent_routing_diagnostic_signals.py",
            "tests/unit/test_intelligent_routing_diagnostic_signals.py",
            "docs/governance/intelligent_routing_diagnostic_signals.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_intelligent_routing_diagnostic_signals.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.intelligent_routing_diagnostic_signals",
            "logs/intelligent_routing_diagnostic_signals/",
        )
        + (
            (
                "schema exposes closed vocabularies for "
                "entropy / tail / criticality / network / quorum "
                "signal kinds"
            ),
            "no executable routing change; this PR is schema-only",
        ),
        "extra_stop_conditions": (
            (
                "any change to the existing routing executor surface "
                "-> STOP, abort"
            ),
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        # Implemented and merged via PR #250 on 2026-05-18.
        # Merge SHA: fcb1abbea4bd2ca190fe6e807b3dacd184faa702.
        # Status flipped from "not_started" -> "merged" in a
        # follow-up queue-status update PR so the A20e selector
        # can advance to the next eligible v3.15.16 unit. A20
        # projections are deterministic / read-only and do not
        # auto-discover merged PRs.
        "status": "merged",
    },
    {
        "id": "u_v3_15_16_routing_explanation_reporter_001",
        "roadmap_task_id": "phase_v3_15_16",
        "title": (
            "Read-only routing-decision explanation reporter "
            "(deterministic projector)"
        ),
        "phase": "v3.15.16",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_v3_15_16_behavior_aware_routing",
            "req_v3_15_16_diagnostic_aware_routing",
        ),
        "expected_files": (
            "reporting/routing_explanation.py",
            "tests/unit/test_routing_explanation.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_routing_explanation.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.routing_explanation",
            "logs/routing_explanation/",
        )
        + (
            (
                "report exposes why each candidate was routed / "
                "deprioritised, with bounded-scalar evidence only"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_v3_15_16_diagnostic_routing_signals_schema_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        # Implemented and merged via PR #252 on 2026-05-18.
        # Merge SHA: 6f588a89b43a2cfec40f92252bde530220877b37.
        # Status flipped from "not_started" -> "merged" in a
        # follow-up queue-status update PR so the A20e selector
        # can advance to the next eligible v3.15.16 unit. A20
        # projections are deterministic / read-only and do not
        # auto-discover merged PRs.
        "status": "merged",
    },
    {
        "id": "u_v3_15_16_routing_governance_doc_001",
        "roadmap_task_id": "phase_v3_15_16",
        "title": (
            "Governance doc for diagnostic-aware routing signals "
            "(read-only)"
        ),
        "phase": "v3.15.16",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_v3_15_16_diagnostic_aware_routing",
        ),
        "expected_files": (
            "docs/governance/intelligent_routing_diagnostic_signals.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/intelligent_routing_diagnostic_signals.md"
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_v3_15_16_diagnostic_routing_signals_schema_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- v3.15.17 Sampling Intelligence ----------------
    {
        "id": "u_v3_15_17_sampling_plan_reporter_001",
        "roadmap_task_id": "phase_v3_15_17",
        "title": (
            "Deterministic sampling-plan projector (read-only "
            "reporting module)"
        ),
        "phase": "v3.15.17",
        "unit_kind": "reporting_module",
        "target_layer": "preset",
        "source_requirement_ids": (
            "req_v3_15_17_deterministic_sampling",
            "req_v3_15_17_diagnostic_aware_sampling",
        ),
        "expected_files": (
            "reporting/sampling_plan.py",
            "tests/unit/test_sampling_plan.py",
            "docs/governance/sampling_plan.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_sampling_plan.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.sampling_plan",
            "logs/sampling_plan/",
        )
        + (
            (
                "plan exposes diagnostic-conditioned sampling "
                "metadata (tail / entropy / phase-transition / "
                "barrier / resonance / network / post-shock / "
                "null-model) without executing samples"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any stochastic search introduced -> STOP, sampling "
                "must remain deterministic"
            ),
        ),
        "prerequisites": (
            "u_v3_15_16_diagnostic_routing_signals_schema_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_17_sampling_coverage_metrics_001",
        "roadmap_task_id": "phase_v3_15_17",
        "title": (
            "Sampling coverage metrics reporter (read-only "
            "deterministic projector)"
        ),
        "phase": "v3.15.17",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_v3_15_17_deterministic_sampling",
        ),
        "expected_files": (
            "reporting/sampling_coverage_metrics.py",
            "tests/unit/test_sampling_coverage_metrics.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_sampling_coverage_metrics.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.sampling_coverage_metrics",
            "logs/sampling_coverage_metrics/",
        )
        + (
            (
                "coverage / low-information / null-control regions "
                "are reported as bounded scalars"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": ("u_v3_15_17_sampling_plan_reporter_001",),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- v3.15.18 Research Observability Expansion -----
    {
        "id": "u_v3_15_18_diagnostic_explanation_reporter_001",
        "roadmap_task_id": "phase_v3_15_18",
        "title": (
            "Research diagnostic-contribution explanation reporter "
            "(read-only)"
        ),
        "phase": "v3.15.18",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_v3_15_18_research_observability",
            "req_v3_15_18_diagnostic_surfaces",
        ),
        "expected_files": (
            "reporting/research_diagnostic_explanation.py",
            "tests/unit/test_research_diagnostic_explanation.py",
            "docs/governance/research_diagnostic_explanation.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_diagnostic_explanation.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.research_diagnostic_explanation",
            "logs/research_diagnostic_explanation/",
        )
        + (
            (
                "reporter explains which diagnostics supported / "
                "contradicted each candidate"
            ),
            "no mutation endpoints; no approval buttons; no frontend change",
        ),
        "extra_stop_conditions": (
            (
                "any approval verb (approve / reject / merge / "
                "deploy) introduced -> STOP, abort"
            ),
        ),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_18_lineage_provenance_reporter_001",
        "roadmap_task_id": "phase_v3_15_18",
        "title": (
            "Hypothesis-seed lineage / external-data provenance "
            "reporter (read-only)"
        ),
        "phase": "v3.15.18",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_v3_15_18_research_observability",
            "req_v3_15_18_diagnostic_surfaces",
            "req_addendum_1_public_source_manifest_fields",
        ),
        "expected_files": (
            "reporting/research_lineage_provenance.py",
            "tests/unit/test_research_lineage_provenance.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_lineage_provenance.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.research_lineage_provenance",
            "logs/research_lineage_provenance/",
        )
        + (
            (
                "exposes the public-source manifest fields and the "
                "quality-gate verdicts as a bounded-scalar projection"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_v3_15_18_diagnostic_explanation_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_18_quorum_state_reporter_001",
        "roadmap_task_id": "phase_v3_15_18",
        "title": (
            "Independent-evidence quorum-state reporter (read-only "
            "deterministic projector)"
        ),
        "phase": "v3.15.18",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_addendum_1_independent_evidence_quorum",
        ),
        "expected_files": (
            "reporting/quorum_state.py",
            "tests/unit/test_quorum_state.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_quorum_state.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.quorum_state",
            "logs/quorum_state/",
        )
        + (
            (
                "exposes quorum status, confirmation diversity, "
                "single-source dependency flag"
            ),
            (
                "quorum is a promotion guardrail only; never a "
                "live-trade trigger"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_v3_15_18_diagnostic_explanation_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- v3.15.19 Hypothesis Discovery Engine ----------
    {
        "id": "u_v3_15_19_behavior_catalog_scaffold_001",
        "roadmap_task_id": "phase_v3_15_19",
        "title": (
            "research/hypothesis_discovery/behavior_catalog.py "
            "scaffold (deterministic, non-executable)"
        ),
        "phase": "v3.15.19",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (
            "req_v3_15_19_hypothesis_discovery_modules",
        ),
        "expected_files": (
            "research/hypothesis_discovery/__init__.py",
            "research/hypothesis_discovery/behavior_catalog.py",
            "tests/unit/test_hypothesis_discovery_behavior_catalog.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hypothesis_discovery_behavior_catalog.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/hypothesis_discovery/behavior_catalog.py"
        )
        + (
            (
                "behavior catalog records named market behaviours, "
                "not indicator combinations"
            ),
        ),
        "extra_stop_conditions": (
            (
                "auto-writing executable strategy code "
                "-> STOP, abort"
            ),
        ),
        "prerequisites": (
            "u_v3_15_18_diagnostic_explanation_reporter_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_19_behavior_hypotheses_scaffold_001",
        "roadmap_task_id": "phase_v3_15_19",
        "title": (
            "research/hypothesis_discovery/behavior_hypotheses.py "
            "scaffold (deterministic hypothesis records)"
        ),
        "phase": "v3.15.19",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (
            "req_v3_15_19_hypothesis_discovery_modules",
        ),
        "expected_files": (
            "research/hypothesis_discovery/behavior_hypotheses.py",
            "tests/unit/test_hypothesis_discovery_behavior_hypotheses.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hypothesis_discovery_behavior_hypotheses.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/hypothesis_discovery/behavior_hypotheses.py"
        )
        + (
            (
                "hypotheses are behaviour-first records with "
                "bounded scalars and source provenance"
            ),
        ),
        "extra_stop_conditions": (
            (
                "stochastic mutation introduced -> STOP, abort"
            ),
        ),
        "prerequisites": ("u_v3_15_19_behavior_catalog_scaffold_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_19_opportunity_scoring_scaffold_001",
        "roadmap_task_id": "phase_v3_15_19",
        "title": (
            "research/hypothesis_discovery/opportunity_scoring.py "
            "scaffold (deterministic, explainable)"
        ),
        "phase": "v3.15.19",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (
            "req_v3_15_19_hypothesis_discovery_modules",
            "req_v3_15_19_opportunity_probability_score",
        ),
        "expected_files": (
            "research/hypothesis_discovery/opportunity_scoring.py",
            "tests/unit/test_hypothesis_discovery_opportunity_scoring.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hypothesis_discovery_opportunity_scoring.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/hypothesis_discovery/opportunity_scoring.py"
        )
        + (
            (
                "opportunity_probability_score = expected research "
                "value; not alpha certainty, not ML confidence, not "
                "prediction certainty"
            ),
            "scoring is deterministic and explainable",
        ),
        "extra_stop_conditions": (
            (
                "any hidden ML / RL / opaque selector introduced "
                "-> STOP, abort"
            ),
        ),
        "prerequisites": ("u_v3_15_19_behavior_hypotheses_scaffold_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_19_diagnostic_hypothesis_adapter_scaffold_001",
        "roadmap_task_id": "phase_v3_15_19",
        "title": (
            "research/hypothesis_discovery/diagnostic_hypothesis_adapter.py "
            "scaffold (deterministic bridge)"
        ),
        "phase": "v3.15.19",
        "unit_kind": "research_module",
        "target_layer": "hypothesis_discovery",
        "source_requirement_ids": (
            "req_v3_15_19_addendum_modules",
        ),
        "expected_files": (
            "research/hypothesis_discovery/diagnostic_hypothesis_adapter.py",
            "tests/unit/test_hypothesis_discovery_diagnostic_adapter.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hypothesis_discovery_diagnostic_adapter.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/hypothesis_discovery/diagnostic_hypothesis_adapter.py"
        )
        + (
            (
                "adapter maps Addendum 1 diagnostic outputs to "
                "behaviour-first hypothesis seeds (no strategy "
                "invention)"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": ("u_v3_15_19_opportunity_scoring_scaffold_001",),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_19_hypothesis_discovery_reporter_001",
        "roadmap_task_id": "phase_v3_15_19",
        "title": (
            "Read-only hypothesis-discovery summary reporter "
            "(reporting module)"
        ),
        "phase": "v3.15.19",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_v3_15_19_hypothesis_discovery_modules",
            "req_v3_15_19_opportunity_probability_score",
        ),
        "expected_files": (
            "reporting/hypothesis_discovery_summary.py",
            "tests/unit/test_hypothesis_discovery_summary.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hypothesis_discovery_summary.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.hypothesis_discovery_summary",
            "logs/hypothesis_discovery_summary/",
        )
        + (
            (
                "summary projects bounded-scalar opportunity scores "
                "and seed provenance"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_v3_15_19_diagnostic_hypothesis_adapter_scaffold_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- v3.15.20 Failure -> Action Mapping ------------
    {
        "id": "u_v3_15_20_failure_taxonomy_reporter_001",
        "roadmap_task_id": "phase_v3_15_20",
        "title": (
            "Deterministic failure-taxonomy reporter (read-only "
            "projection module)"
        ),
        "phase": "v3.15.20",
        "unit_kind": "reporting_module",
        "target_layer": "policy",
        "source_requirement_ids": (
            "req_v3_15_20_failure_action_mappings",
            "req_v3_15_20_addendum_mappings",
        ),
        "expected_files": (
            "reporting/failure_taxonomy.py",
            "tests/unit/test_failure_taxonomy.py",
            "docs/governance/failure_taxonomy.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_failure_taxonomy.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.failure_taxonomy",
            "logs/failure_taxonomy/",
        )
        + (
            (
                "taxonomy is closed-vocab; widening requires a code "
                "change + matching test"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_v3_15_20_failure_action_mapping_reporter_001",
        "roadmap_task_id": "phase_v3_15_20",
        "title": (
            "Failure -> action mapping reporter (deterministic, "
            "research-routing only)"
        ),
        "phase": "v3.15.20",
        "unit_kind": "reporting_module",
        "target_layer": "policy",
        "source_requirement_ids": (
            "req_v3_15_20_failure_action_mappings",
            "req_v3_15_20_addendum_mappings",
        ),
        "expected_files": (
            "reporting/failure_action_mapping.py",
            "tests/unit/test_failure_action_mapping.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_failure_action_mapping.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.failure_action_mapping",
            "logs/failure_action_mapping/",
        )
        + (
            (
                "mappings affect routing / suppression / cooldown / "
                "confirmation only; never trade execution"
            ),
            (
                "mapping deterministic; failure-class -> action is a "
                "pure function"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any mapping that touches live risk / capital "
                "allocation / order placement -> STOP, abort"
            ),
        ),
        "prerequisites": (
            "u_v3_15_20_failure_taxonomy_reporter_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # -------------------- Addendum 1 cross-cutting groundwork -----------
    {
        "id": "u_addendum_1_diagnostics_library_scaffold_001",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "title": (
            "Behavior Diagnostics Library scaffold under "
            "research/diagnostics/ (null-models first)"
        ),
        "phase": "addendum_1",
        "unit_kind": "diagnostic_primitive",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_1_diagnostics_do_not_trade",
            "req_addendum_1_null_model_brownian",
            "req_addendum_1_sidecar_artifacts_only",
        ),
        "expected_files": (
            "research/diagnostics/__init__.py",
            "research/diagnostics/null_models.py",
            "tests/unit/test_research_diagnostics_null_models.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_diagnostics_null_models.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/diagnostics/null_models.py"
        )
        + (
            (
                "diagnostic primitives are pure functions; no "
                "executable strategy generation; no broker / order "
                "/ risk / execution surface touched"
            ),
            "diagnostics do not trade",
        ),
        "extra_stop_conditions": (
            (
                "any diagnostic that mutates live risk or places a "
                "trade -> STOP, abort"
            ),
        ),
        "prerequisites": (),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_addendum_1_external_intelligence_source_registry_001",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "title": (
            "External Intelligence source registry + source-manifest "
            "schema (no fetchers)"
        ),
        "phase": "addendum_1",
        "unit_kind": "external_intelligence_source",
        "target_layer": "external_intelligence",
        "source_requirement_ids": (
            "req_addendum_1_external_intelligence_intake",
            "req_addendum_1_public_source_manifest_fields",
        ),
        "expected_files": (
            "research/external_intelligence/__init__.py",
            "research/external_intelligence/source_registry.py",
            "research/external_intelligence/source_manifest_schema.py",
            "tests/unit/test_external_intelligence_source_registry.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_external_intelligence_source_registry.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/external_intelligence/source_registry.py"
        )
        + (
            (
                "manifest fields verbatim from Addendum 1 Section "
                "8.4; no paid feeds, no vendor alpha"
            ),
            (
                "no network calls; this unit only models sources, "
                "it does not fetch"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any paid-feed / vendor-alpha import introduced "
                "-> STOP, abort"
            ),
        ),
        "prerequisites": (),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_addendum_1_public_data_quality_gates_001",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "title": (
            "Public-data quality-gate primitives (freshness / "
            "missing / monotonicity / duplicate / outlier / coverage)"
        ),
        "phase": "addendum_1",
        "unit_kind": "external_intelligence_source",
        "target_layer": "external_intelligence",
        "source_requirement_ids": (
            "req_addendum_1_public_data_quality_gates",
            "req_addendum_1_external_data_not_alpha",
        ),
        "expected_files": (
            "research/external_intelligence/quality_gates.py",
            "tests/unit/test_external_intelligence_quality_gates.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_external_intelligence_quality_gates.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/external_intelligence/quality_gates.py"
        )
        + (
            (
                "quality gates are pure functions; no hypothesis "
                "seed promoted from public data without passing all "
                "gates"
            ),
            "external data is an unvalidated prior, not alpha",
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_1_external_intelligence_source_registry_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_addendum_1_diagnostic_sidecar_writer_001",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "title": (
            "Diagnostic sidecar artefact writer "
            "(research/diagnostics/seed_artifact_writer.py)"
        ),
        "phase": "addendum_1",
        "unit_kind": "diagnostic_primitive",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_1_sidecar_artifacts_only",
        ),
        "expected_files": (
            "research/diagnostics/seed_artifact_writer.py",
            "tests/unit/test_research_diagnostics_seed_artifact_writer.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("frozen_seed_files",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_diagnostics_seed_artifact_writer.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/diagnostics/seed_artifact_writer.py"
        )
        + (
            (
                "writes only under artifacts/diagnostics/*.v1.json "
                "(atomic, allowlist-restricted)"
            ),
            (
                "never writes to research/research_latest.json or "
                "research/strategy_matrix.csv"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any write path outside artifacts/diagnostics/ "
                "-> STOP, abort"
            ),
        ),
        "prerequisites": (
            "u_addendum_1_diagnostics_library_scaffold_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "operator_go_required",
        "status": "not_started",
    },
    {
        "id": "u_addendum_1_diagnostics_governance_doc_001",
        "roadmap_task_id": "addendum_1_diagnostics_intake",
        "title": (
            "Governance doc for the Behavior Diagnostics Library "
            "(read-only)"
        ),
        "phase": "addendum_1",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_1_diagnostics_do_not_trade",
            "req_addendum_1_external_data_not_alpha",
            "req_addendum_1_sidecar_artifacts_only",
        ),
        "expected_files": (
            "docs/governance/research_diagnostics_library.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/research_diagnostics_library.md"
        )
        + (
            (
                "doc pins the Diagnostics-do-not-trade and "
                "External-data-is-not-alpha principles verbatim"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # =====================================================================
    # A23 — Addendum 2 implementation units (State, Sequential,
    # Knowledge & Retrieval). Each unit is a small, conveyor-friendly
    # scaffold derived from the operator-provided canonical doc. No
    # executable strategy generation. No broker / risk / execution.
    # No live / paper / shadow. Frozen contracts untouched.
    # =====================================================================
    {
        "id": "u_addendum_2_state_diagnostics_governance_doc_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "State & Sequential Diagnostics Layer governance doc "
            "(read-only)"
        ),
        "phase": "addendum_2",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_2_state_transition_diagnostics",
            "req_addendum_2_hidden_markov_models",
            "req_addendum_2_semi_markov_regime_duration",
        ),
        "expected_files": (
            "docs/governance/state_sequential_diagnostics_layer.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/state_sequential_diagnostics_layer.md"
        )
        + (
            (
                "doc explains state-transition / HMM / semi-Markov / "
                "higher-order / particle / martingale / random-walk "
                "/ FSM / queueing diagnostics are read-only sidecar "
                "context and never trade"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_1_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_knowledge_retrieval_governance_doc_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Research Knowledge & Retrieval Layer governance doc "
            "(read-only)"
        ),
        "phase": "addendum_2",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_2_knowledge_graph_memory",
            "req_addendum_2_ontology_taxonomy",
            "req_addendum_2_entity_resolution",
            "req_addendum_2_hybrid_retrieval",
            "req_addendum_2_reciprocal_rank_fusion",
        ),
        "expected_files": (
            "docs/governance/research_knowledge_retrieval_layer.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/research_knowledge_retrieval_layer.md"
        )
        + (
            (
                "doc explains knowledge graph / ontology / entity "
                "resolution / hybrid retrieval / rank fusion are "
                "deterministic read-only research-routing context"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_1_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_state_transition_schema_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "State-transition diagnostic schema + read-only projector"
        ),
        "phase": "addendum_2",
        "unit_kind": "reporting_module",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_2_state_transition_diagnostics",
        ),
        "expected_files": (
            "reporting/state_transition_diagnostic.py",
            "tests/unit/test_state_transition_diagnostic.py",
            "docs/governance/state_transition_diagnostic.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_state_transition_diagnostic.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.state_transition_diagnostic",
            "logs/state_transition_diagnostic/",
        )
        + (
            (
                "schema exposes closed-vocab regimes/states and "
                "deterministic transition statistics; no executable "
                "strategy generation"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any attempt to mutate live risk or place a trade "
                "from this diagnostic -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_2_state_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_null_process_baseline_schema_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Null-process (martingale + random-walk) baseline "
            "diagnostic schema + projector"
        ),
        "phase": "addendum_2",
        "unit_kind": "reporting_module",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_2_martingale_baseline",
            "req_addendum_2_random_walk_surrogate",
        ),
        "expected_files": (
            "reporting/null_process_baseline_diagnostic.py",
            "tests/unit/test_null_process_baseline_diagnostic.py",
            "docs/governance/null_process_baseline_diagnostic.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_null_process_baseline_diagnostic.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.null_process_baseline_diagnostic",
            "logs/null_process_baseline_diagnostic/",
        )
        + (
            (
                "deterministic random seeds; surrogate samples are "
                "sidecar artefacts only"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any stochastic baseline must use a deterministic "
                "seed; failure -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_2_state_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_queueing_throughput_reporter_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Queueing / research-throughput diagnostic reporter "
            "(read-only)"
        ),
        "phase": "addendum_2",
        "unit_kind": "reporting_module",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_2_queueing_throughput",
        ),
        "expected_files": (
            "reporting/research_throughput_diagnostic.py",
            "tests/unit/test_research_throughput_diagnostic.py",
            "docs/governance/research_throughput_diagnostic.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_throughput_diagnostic.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.research_throughput_diagnostic",
            "logs/research_throughput_diagnostic/",
        )
        + (
            (
                "models queueing metrics deterministically over "
                "research-pipeline scheduling artefacts; never "
                "modifies pipeline state"
            ),
        ),
        "extra_stop_conditions": (
            "any throughput diagnostic that schedules work -> STOP",
        ),
        "prerequisites": (
            "u_addendum_2_state_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_knowledge_graph_scaffold_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Research knowledge-graph scaffold (research-memory "
            "graph nodes + lineage edges)"
        ),
        "phase": "addendum_2",
        "unit_kind": "research_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_addendum_2_knowledge_graph_memory",
        ),
        "expected_files": (
            "research/knowledge_graph/__init__.py",
            "research/knowledge_graph/memory_graph_scaffold.py",
            "tests/unit/test_research_knowledge_graph_scaffold.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_knowledge_graph_scaffold.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/knowledge_graph/memory_graph_scaffold.py"
        )
        + (
            (
                "scaffold encodes deterministic node/edge schemas; "
                "no probabilistic edges; no LLM relation extraction"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any edge sourced from an LLM / fuzzy parser / "
                "external vendor -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_2_knowledge_retrieval_governance_doc_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_ontology_entity_resolution_scaffold_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Canonical taxonomy + entity-resolution scaffold "
            "(closed-vocab term registry)"
        ),
        "phase": "addendum_2",
        "unit_kind": "research_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_addendum_2_ontology_taxonomy",
            "req_addendum_2_entity_resolution",
        ),
        "expected_files": (
            "research/knowledge_graph/ontology_scaffold.py",
            "research/knowledge_graph/entity_resolution_scaffold.py",
            "tests/unit/test_research_ontology_scaffold.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_research_ontology_scaffold.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/knowledge_graph/ontology_scaffold.py"
        )
        + (
            (
                "ontology is closed-vocab; entity-resolution uses "
                "deterministic exact-match + canonical-id mapping; "
                "no LLM"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any probabilistic tie-breaking or LLM-based "
                "coreference -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_2_knowledge_graph_scaffold_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_2_hybrid_retrieval_reporter_001",
        "roadmap_task_id": (
            "addendum_2_state_sequential_knowledge_retrieval"
        ),
        "title": (
            "Hybrid retrieval + rank-fusion reporter "
            "(deterministic, read-only)"
        ),
        "phase": "addendum_2",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_addendum_2_hybrid_retrieval",
            "req_addendum_2_reciprocal_rank_fusion",
        ),
        "expected_files": (
            "reporting/hybrid_retrieval_reporter.py",
            "tests/unit/test_hybrid_retrieval_reporter.py",
            "docs/governance/hybrid_retrieval_reporter.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_hybrid_retrieval_reporter.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.hybrid_retrieval_reporter",
            "logs/hybrid_retrieval_reporter/",
        )
        + (
            (
                "ranking is deterministic closed-formula; no LLM "
                "reranker; no fuzzy parsing"
            ),
        ),
        "extra_stop_conditions": (
            "any LLM-based reranker introduced -> STOP",
        ),
        "prerequisites": (
            "u_addendum_2_ontology_entity_resolution_scaffold_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    # =====================================================================
    # A23 — Addendum 3 implementation units (Source Identity, Data
    # Quality, Throughput). Each unit is a small, conveyor-friendly
    # scaffold derived from the operator-provided canonical doc.
    # Registry / manifest / quality-gate / cache scaffolds only —
    # no live network ingest, no vendor credentials, no broker
    # connections, no order placement.
    # =====================================================================
    {
        "id": "u_addendum_3_source_candidate_registry_governance_doc_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Source Candidate Registry governance doc (read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_3_source_candidate_registry",
        ),
        "expected_files": (
            "docs/governance/source_candidate_registry.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/source_candidate_registry.md"
        )
        + (
            (
                "doc pins identity / license / access mode / "
                "repo-resident-only / status fields; registry is "
                "sidecar-artefact only; never grants connection "
                "authority"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_1_diagnostics_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_source_identity_governance_doc_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Source Identity & Symbology Layer governance doc "
            "(read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_3_openfigi_identity",
        ),
        "expected_files": (
            "docs/governance/source_identity_symbology_layer.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/source_identity_symbology_layer.md"
        )
        + (
            (
                "doc describes deterministic symbology mapping; no "
                "live OpenFIGI calls; no vendor credentials in repo"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_3_source_candidate_registry_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_quality_gate_governance_doc_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Source Manifest & Quality Gate Layer governance doc "
            "(read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_3_quality_gate_reporter",
        ),
        "expected_files": (
            "docs/governance/source_manifest_quality_gate_layer.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/source_manifest_quality_gate_layer.md"
        )
        + (
            (
                "doc pins closed-vocab verdicts "
                "(passes_quality_gate / fails_quality_gate / "
                "insufficient_evidence); verdicts never gate "
                "trading; external data is not alpha"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_3_source_candidate_registry_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_cache_throughput_governance_doc_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Local Data Cache & Throughput Layer governance doc "
            "(read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "governance_doc",
        "target_layer": "governance",
        "source_requirement_ids": (
            "req_addendum_3_parquet_cache",
            "req_addendum_3_duckdb_query_catalog",
        ),
        "expected_files": (
            "docs/governance/local_data_cache_throughput_layer.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": (),
        "extra_required_tests": (),
        "extra_definition_of_done": _governance_doc_dod(
            "docs/governance/local_data_cache_throughput_layer.md"
        )
        + (
            (
                "doc pins Parquet + DuckDB manifest scaffolds as "
                "read-only offline-research artefacts; never live; "
                "never broker / risk / execution"
            ),
        ),
        "extra_stop_conditions": (),
        "prerequisites": (
            "u_addendum_3_source_candidate_registry_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_source_usefulness_ledger_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Source Usefulness Ledger scaffold "
            "(deterministic, read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "reporting_module",
        "target_layer": "evidence",
        "source_requirement_ids": (
            "req_addendum_3_source_usefulness_ledger",
        ),
        "expected_files": (
            "reporting/source_usefulness_ledger.py",
            "tests/unit/test_source_usefulness_ledger.py",
            "docs/governance/source_usefulness_ledger.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_source_usefulness_ledger.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.source_usefulness_ledger",
            "logs/source_usefulness_ledger/",
        )
        + (
            (
                "per-source usefulness verdicts recorded as sidecar "
                "artefacts; never grants trading authority"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any attempt to feed the ledger into a live trading "
                "decision -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_3_quality_gate_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_quality_gate_reporter_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Public-data quality-gate reporter "
            "(deterministic verdicts, read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "reporting_module",
        "target_layer": "diagnostics",
        "source_requirement_ids": (
            "req_addendum_3_quality_gate_reporter",
        ),
        "expected_files": (
            "reporting/public_data_quality_gate.py",
            "tests/unit/test_public_data_quality_gate.py",
            "docs/governance/public_data_quality_gate.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_public_data_quality_gate.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.public_data_quality_gate",
            "logs/public_data_quality_gate/",
        )
        + (
            (
                "verdicts are closed-vocab "
                "(passes_quality_gate / fails_quality_gate / "
                "insufficient_evidence); external data is not alpha"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any verdict that promotes external data into a "
                "trade signal -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_3_quality_gate_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_openfigi_identity_registry_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "OpenFIGI identity candidate-registry scaffold "
            "(no live calls)"
        ),
        "phase": "addendum_3",
        "unit_kind": "external_intelligence_source",
        "target_layer": "external_intelligence",
        "source_requirement_ids": (
            "req_addendum_3_openfigi_identity",
        ),
        "expected_files": (
            "research/external_intelligence/openfigi_identity_scaffold.py",
            "tests/unit/test_openfigi_identity_scaffold.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_openfigi_identity_scaffold.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/external_intelligence/openfigi_identity_scaffold.py"
        )
        + (
            (
                "registry entry only; no live OpenFIGI HTTP calls; "
                "no credentials in repo; no vendor SDK import"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any network call (urllib / requests / httpx / "
                "socket) -> STOP"
            ),
        ),
        "prerequisites": (
            "u_addendum_3_source_identity_governance_doc_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_binance_public_bulk_cache_manifest_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Binance public bulk-data cache manifest scaffold "
            "(no broker / order surface)"
        ),
        "phase": "addendum_3",
        "unit_kind": "external_intelligence_source",
        "target_layer": "external_intelligence",
        "source_requirement_ids": (
            "req_addendum_3_binance_public_bulk_cache",
        ),
        "expected_files": (
            "research/external_intelligence/binance_public_bulk_cache_manifest.py",
            "tests/unit/test_binance_public_bulk_cache_manifest.py",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_binance_public_bulk_cache_manifest.py"
        ),
        "extra_definition_of_done": _research_module_dod(
            "research/external_intelligence/binance_public_bulk_cache_manifest.py"
        )
        + (
            (
                "manifest scaffold only; no live Binance API call; "
                "no broker import; no order surface; no credentials"
            ),
        ),
        "extra_stop_conditions": (
            (
                "any broker / order / risk / execution import "
                "-> STOP"
            ),
            "any API key / credential / endpoint hard-coded -> STOP",
        ),
        "prerequisites": (
            "u_addendum_3_cache_throughput_governance_doc_001",
        ),
        "risk_class": "MEDIUM",
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
    {
        "id": "u_addendum_3_parquet_duckdb_cache_manifest_001",
        "roadmap_task_id": (
            "addendum_3_source_identity_data_quality_throughput"
        ),
        "title": (
            "Parquet + DuckDB cache manifest scaffold "
            "(offline-research read-only)"
        ),
        "phase": "addendum_3",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": (
            "req_addendum_3_parquet_cache",
            "req_addendum_3_duckdb_query_catalog",
        ),
        "expected_files": (
            "reporting/parquet_duckdb_cache_manifest.py",
            "tests/unit/test_parquet_duckdb_cache_manifest.py",
            "docs/governance/parquet_duckdb_cache_manifest.md",
        ),
        "extra_forbidden_files": (),
        "extra_forbidden_surface_reasons": ("step5_blocked",),
        "extra_required_tests": _targeted_unit_tests(
            "tests/unit/test_parquet_duckdb_cache_manifest.py"
        ),
        "extra_definition_of_done": _reporting_module_dod(
            "reporting.parquet_duckdb_cache_manifest",
            "logs/parquet_duckdb_cache_manifest/",
        )
        + (
            (
                "manifest scaffold only; no live cache write; no "
                "broker / order / risk / execution surface; offline "
                "research artefact only"
            ),
        ),
        "extra_stop_conditions": (
            "any live cache mutation from production -> STOP",
        ),
        "prerequisites": (
            "u_addendum_3_cache_throughput_governance_doc_001",
        ),
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    },
)


# ---------------------------------------------------------------------------
# Decomposition helpers
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


def _bounded_str_tuple(values: Any, max_items: int, max_len: int) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        b = _bounded_str(v, max_len)
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(b)
        if len(out) >= max_items:
            break
    return tuple(out)


def _merge_forbidden_files(extra: tuple[str, ...]) -> list[str]:
    merged = list(BASELINE_FORBIDDEN_FILES) + list(extra)
    seen: set[str] = set()
    out: list[str] = []
    for entry in merged:
        if entry in seen:
            continue
        seen.add(entry)
        out.append(entry)
    out.sort()
    return out[:MAX_FORBIDDEN_FILES]


def _merge_forbidden_surface_reasons(
    extra: tuple[str, ...],
) -> list[str]:
    merged = list(BASELINE_FORBIDDEN_SURFACE_REASONS) + list(extra)
    seen: set[str] = set()
    out: list[str] = []
    for r in merged:
        if r in seen:
            continue
        if r not in FORBIDDEN_SURFACE_REASON:
            continue
        seen.add(r)
        out.append(r)
    out.sort()
    return out[:MAX_FORBIDDEN_SURFACE_REASONS]


def _merge_required_tests(extra: tuple[str, ...]) -> list[str]:
    merged = list(extra) + list(BASELINE_REQUIRED_TESTS)
    seen: set[str] = set()
    out: list[str] = []
    for t in merged:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:MAX_REQUIRED_TESTS]


def _merge_definition_of_done(extra: tuple[str, ...]) -> list[str]:
    merged = list(extra) + list(BASELINE_DEFINITION_OF_DONE)
    seen: set[str] = set()
    out: list[str] = []
    for d in merged:
        b = _bounded_str(d, MAX_LIST_ITEM_LEN)
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(b)
    return out[:MAX_DOD_ITEMS]


def _merge_stop_conditions(extra: tuple[str, ...]) -> list[str]:
    merged = list(extra) + list(BASELINE_STOP_CONDITIONS)
    seen: set[str] = set()
    out: list[str] = []
    for s in merged:
        b = _bounded_str(s, MAX_LIST_ITEM_LEN)
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(b)
    return out[:MAX_STOP_CONDITIONS]


def _resolve_authority_hint(value: Any) -> str:
    """Fail-closed authority-hint resolver. Anything outside the
    closed vocabulary falls back to NEEDS_HUMAN_CANDIDATE."""
    if value in AUTHORITY_HINT:
        return value
    return "NEEDS_HUMAN_CANDIDATE"


def _normalize_unit(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _bounded_str(raw["id"], MAX_ID_LEN),
        "roadmap_task_id": _bounded_str(raw["roadmap_task_id"], MAX_ID_LEN),
        "title": _bounded_str(raw["title"], MAX_TITLE_LEN),
        "phase": raw["phase"],
        "unit_kind": raw["unit_kind"],
        "target_layer": raw["target_layer"],
        "source_requirement_ids": list(
            _bounded_str_tuple(
                raw.get("source_requirement_ids", ()),
                MAX_SOURCE_REQUIREMENT_IDS,
                MAX_ID_LEN,
            )
        ),
        "expected_files": list(
            _bounded_str_tuple(
                raw.get("expected_files", ()),
                MAX_EXPECTED_FILES,
                MAX_PATH_LEN,
            )
        ),
        "forbidden_files": _merge_forbidden_files(
            raw.get("extra_forbidden_files", ())
        ),
        "forbidden_surface_reasons": _merge_forbidden_surface_reasons(
            raw.get("extra_forbidden_surface_reasons", ())
        ),
        "required_tests": _merge_required_tests(
            raw.get("extra_required_tests", ())
        ),
        "definition_of_done": _merge_definition_of_done(
            raw.get("extra_definition_of_done", ())
        ),
        "stop_conditions": _merge_stop_conditions(
            raw.get("extra_stop_conditions", ())
        ),
        "prerequisites": list(
            _bounded_str_tuple(
                raw.get("prerequisites", ()),
                MAX_PREREQUISITES,
                MAX_ID_LEN,
            )
        ),
        "risk_class": raw["risk_class"]
        if raw.get("risk_class") in RISK_CLASS
        else "UNKNOWN",
        "authority_hint": _resolve_authority_hint(raw.get("authority_hint")),
        "operator_gate": raw["operator_gate"]
        if raw.get("operator_gate") in OPERATOR_GATE
        else "operator_go_required",
        "status": raw["status"]
        if raw.get("status") in UNIT_STATUS
        else "not_started",
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic implementation-unit decomposition.

    Args:
        generated_at_utc: override the report timestamp. Tests inject
            this for byte-stable output.
    """
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    # Read the upstream catalog to derive the known-task-id set. We
    # only use it as a closed reference; we do not invent units for
    # tasks that the catalog has not committed.
    #
    # A23 made Addendum 2 + 3 repo-resident and added their tasks to
    # the catalog, so addendum_2 / addendum_3 unit seeds are now
    # accepted. The defensive ``addendum_absence`` filter that
    # previously dropped them has been removed; the
    # ``known_task_ids`` / ``known_phases`` gates below still keep
    # unit seeds from leaking through for unrecognised tasks/phases.
    catalog = rtc.collect_snapshot(generated_at_utc=ts)
    known_task_ids: set[str] = {t["id"] for t in catalog["roadmap_tasks"]}
    known_phases: set[str] = {t["phase"] for t in catalog["roadmap_tasks"]}

    units: list[dict[str, Any]] = []
    skipped_warnings: list[str] = []
    for seed in _UNIT_SEED:
        if seed["roadmap_task_id"] not in known_task_ids:
            skipped_warnings.append(
                f"unit_skipped_unknown_task:{seed['id']}:"
                f"{seed['roadmap_task_id']}"
            )
            continue
        if seed["phase"] not in known_phases:
            skipped_warnings.append(
                f"unit_skipped_unknown_phase:{seed['id']}:{seed['phase']}"
            )
            continue
        units.append(_normalize_unit(seed))

    units.sort(key=lambda u: (u["phase"], u["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "source_catalog_module_version": catalog["module_version"],
        "source_catalog_schema_version": catalog["schema_version"],
        "vocabularies": {
            "unit_kind": list(UNIT_KIND),
            "risk_class": list(RISK_CLASS),
            "authority_hint": list(AUTHORITY_HINT),
            "operator_gate": list(OPERATOR_GATE),
            "unit_status": list(UNIT_STATUS),
            "target_layer": list(TARGET_LAYER),
            "forbidden_surface_reason": list(FORBIDDEN_SURFACE_REASON),
        },
        "skipped_warnings": skipped_warnings,
        "implementation_units": units,
        "decomposition_invariants": dict(_DECOMPOSITION_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside ``logs/roadmap_task_units/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_task_units._atomic_write_json refuses "
            f"non-units-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_task_units.",
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
    units = snapshot["implementation_units"]
    inv = snapshot["decomposition_invariants"]
    by_phase: dict[str, int] = {}
    by_hint: dict[str, int] = {h: 0 for h in AUTHORITY_HINT}
    by_risk: dict[str, int] = {r: 0 for r in RISK_CLASS}
    for u in units:
        by_phase[u["phase"]] = by_phase.get(u["phase"], 0) + 1
        by_hint[u["authority_hint"]] += 1
        by_risk[u["risk_class"]] += 1
    lines = [
        f"roadmap_task_units {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"implementation_units={len(units)}",
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
            "calls_execution_authority_classifier="
            f"{inv['calls_execution_authority_classifier']} "
            "final_authority_classified="
            f"{inv['final_authority_classified']}"
        ),
        f"by_phase={dict(sorted(by_phase.items()))}",
        f"by_authority_hint={by_hint}",
        f"by_risk_class={by_risk}",
    ]
    for u in units:
        lines.append(
            f"  unit {u['id']} phase={u['phase']} "
            f"risk={u['risk_class']} hint={u['authority_hint']} "
            f"gate={u['operator_gate']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_task_units",
        description=(
            "A20b Implementation Unit Decomposer. Read-only "
            "deterministic projection of A20a Roadmap v6 task catalog "
            "into PR-sized implementation units. No final authority "
            "classification (A20c). No AAC / dashboard visibility "
            "(A20d). No next-buildable-unit selector (A20e). Step 5 "
            "implementation remains BLOCKED."
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
            "Do not persist logs/roadmap_task_units/latest.json "
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
