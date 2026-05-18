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
    "addendum_2_not_present": True,
    "addendum_3_not_present": True,
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
    # -------------------- v3.15.16 Intelligent Routing Layer ------------
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
    # tasks that the catalog has not committed. This is what keeps
    # Addendum 2 / Addendum 3 absence from leaking into the unit
    # projection.
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
        if seed["phase"] in ("addendum_2", "addendum_3"):
            # Defensive: the catalog must not encode these phases as
            # tasks, but reassert it here too so a future drift cannot
            # smuggle invented units through.
            skipped_warnings.append(
                f"unit_skipped_addendum_absence:{seed['id']}:{seed['phase']}"
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
