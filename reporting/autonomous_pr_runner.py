"""Autonomous PR Runner -- A21c bounded PR creation + A21d bounded
auto-merge + A21e continuous conveyor.

Operates in three explicit modes:

* ``--run-one`` (A21c): takes ONE A20e-selected unit, opens ONE
  PR, watches CI to first verdict, stops.
* ``--run-one --auto-merge-runner-pr`` (A21d): same as A21c plus
  bounded squash-merge for runner-originated PRs after CI-green
  + post-merge gate watch + evidence-backed ledger update.
* ``--run-continuous --auto-merge-runner-pr`` (A21e): wraps the
  A21d cycle in a loop. After each successful merge + post-merge
  gates green + status-artefact refresh, re-runs A20e against
  the updated overlay. If the next selection is OK_SELECTED and
  passes every safety gate, processes the next unit. Stops only
  when:

  1. the selector returns no eligible unit
     (``ok_conveyor_completed_no_eligible_unit``);
  2. an explicit operator-stop signal fires
     (``--stop-after-current`` flag or the
     ``logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal``
     sentinel file);
  3. any safety or technical stop condition fires inside an
     iteration (same closed-vocab STOP_REASON values that A21c /
     A21d use).

  There is **no artificial max_units_per_run cap**, **no hard
  wall-clock budget**, and **no per-unit timeout as a queue
  policy**. The conveyor stops only on no-eligible-work, a real
  safety/technical condition, or operator interrupt.

The runner is the **first concrete Step 5 slice**. It is bounded:

* exactly one unit per invocation (``max_units_per_run = 1``);
* exactly one merge per invocation
  (``max_merges_per_run = 1``, A21d hard cap);
* AUTO_ALLOWED + LOW risk + ``operator_gate = none`` only;
* auto-merge is OPT-IN and only valid for the PR the runner just
  opened in the same invocation
  (``--auto-merge-runner-pr`` + same-invocation PR-number
  cross-check);
* no production-merge authority outside the bounded auto-merge
  slice; no ``--admin``;
* no deploy, no deploy watcher; the runner observes post-merge
  gates only when ``--auto-merge-runner-pr`` is set and reports
  their outcome read-only;
* the auto-merge phase appends an evidence-backed ``merged``
  record to ``logs/roadmap_unit_status/runner_merges.json`` (the
  A21a auxiliary artefact). The static A20b ``_UNIT_SEED`` and
  the A21a ``_STATUS_LEDGER_SEED`` are NEVER mutated by the
  runner;
* no second-unit continuation; the runner stops after one PR (or
  one merge if auto-merge is enabled);
* no force-push, no hook bypass;
* no LLM, no external API calls except via the explicit
  ``external_command`` implementation strategy that the operator
  opts into via CLI flag.

Hard guarantees (pinned by tests):

* **Safe to import.** Stdlib + (read-only) consumer of A20b /
  A20e / A21a. No subprocess invocation on import, no git, no gh,
  no file writes, no network. The ``subprocess`` module is
  imported lazily inside the real shell runner factory so the
  module-level ``import reporting.autonomous_pr_runner`` is
  side-effect free.
* **Default CLI behaviour is safe.** ``--status`` and
  ``--plan-only`` never invoke git / gh / subprocess and never
  write anything outside ``logs/autonomous_pr_runner/``.
* **Tests inject fakes for shell / git / gh and the
  implementation strategy.** No real branch, commit, push, PR,
  merge, or deploy is ever performed by unit tests.
* **Fail-closed on every safety-gate failure.** Closed
  ``STOP_REASON`` vocab; closed ``SAFETY_GATE`` vocab; closed
  ``GATE_RESULT`` vocab; closed ``RUN_STATUS`` vocab; closed
  ``RUNNER_MODE`` vocab; closed ``IMPLEMENTATION_STRATEGY``
  vocab. Widening any requires a code + test change.
* **Bounded slice.** ``max_units_per_run > 1`` is rejected;
  ``--implementation-strategy none`` (the default) refuses to
  execute and reports
  ``implementation_strategy_not_configured``; auto-merge / deploy
  paths do not exist in the module source (asserted by tests
  scanning the module text for forbidden tokens).

CLI::

    # Inspection-only (default; no execution, no writes outside
    # logs/autonomous_pr_runner/):
    python -m reporting.autonomous_pr_runner --status
    python -m reporting.autonomous_pr_runner --plan-only
    python -m reporting.autonomous_pr_runner --no-write

    # Real execution (requires explicit operator strategy choice):
    python -m reporting.autonomous_pr_runner \\
        --run-one --max-units 1 \\
        --implementation-strategy external_command \\
        --implementation-command "<operator-provided real command>"

The runner DOES NOT:

* squash-merge;
* use ``--admin``;
* force-push;
* bypass hooks;
* delete the branch after merge;
* deploy anything;
* update the dynamic unit-status ledger to merged;
* continue to a second unit;
* touch any forbidden path;
* mutate any approval inbox, mutation route, or approval button;
* grant runtime / trading / paper / shadow / live authority;
* call any LLM, external API, or hidden judgment on its own;
* activate Step 5 broadly (this slice is the bounded carve-out)
  or Level 6 (permanently disabled per ADR-015) or relax any
  branch-protection invariant.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Final, Protocol

from reporting import roadmap_next_unit as rnu
from reporting import roadmap_task_units as rtu
from reporting import roadmap_unit_status as rus

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A21e+A22+A24"
REPORT_KIND: Final[str] = "autonomous_pr_runner"
CONVEYOR_REPORT_KIND: Final[str] = "autonomous_pr_runner_conveyor"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants; never flipped at runtime)
# ---------------------------------------------------------------------------

#: The A21c slice carves out a bounded PR-creation slice of Step 5.
#: The broad Step 5 lock remains BLOCKED everywhere else.
STEP5_ENABLED_SUBSTAGE: Final[str] = (
    "a21e_continuous_conveyor_with_bounded_auto_merge"
)
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Top-level runner status. Exactly one value per run.
RUN_STATUS: Final[tuple[str, ...]] = (
    "not_run",
    "status_only",
    "plan_only",
    "refused_unsafe",
    "executed_pr_opened",
    "executed_pr_merged",
    "executed_blocked_at_implementation",
    "executed_blocked_at_diff",
    "executed_blocked_at_tests",
    "executed_blocked_at_governance_lint",
    "executed_blocked_at_commit",
    "executed_blocked_at_push",
    "executed_blocked_at_pr_create",
    "executed_blocked_at_ci",
    "executed_blocked_at_auto_merge",
    "executed_blocked_at_post_merge_gates",
    "executed_blocked_at_ledger_update",
    # A21e conveyor outcomes
    "executed_conveyor_completed_no_eligible",
    "executed_conveyor_stopped_operator",
    "executed_conveyor_stopped_safety",
    "executed_conveyor_stopped_technical",
    "executed_conveyor_refused_unsafe",
)

#: Closed per-run stop-reason vocabulary. Exactly one value per run.
STOP_REASON: Final[tuple[str, ...]] = (
    "status_only_mode",
    "plan_only_mode",
    "selector_unavailable",
    "no_eligible_unit",
    "ambiguous_selection",
    "unsafe_authority_class",
    "unsafe_risk_class",
    "unsafe_operator_gate",
    "requires_operator_go",
    "missing_expected_files",
    "missing_forbidden_files",
    "missing_required_tests",
    "forbidden_path_in_expected_files",
    "terminal_status",
    "max_units_exceeded",
    "implementation_strategy_not_configured",
    "implementation_strategy_failed",
    "diff_outside_expected_files",
    "diff_touches_forbidden_path",
    "diff_empty",
    "tests_failed",
    "governance_lint_failed",
    "commit_failed",
    "hook_failed",
    "branch_creation_failed",
    "branch_already_exists",
    "push_failed",
    "pr_creation_failed",
    "ci_failed",
    "ci_timeout",
    "ci_not_clean",
    "unknown_evidence",
    "ok_pr_opened",
    # A21d auto-merge stop reasons
    "auto_merge_disabled",
    "not_runner_originated",
    "pr_branch_mismatch",
    "pr_title_missing_unit_id",
    "pr_body_missing_runner_signature",
    "pr_diff_outside_expected_files",
    "pr_diff_touches_forbidden_path",
    "mergeability_not_clean",
    "branch_protection_requires_admin",
    "max_merges_exceeded",
    "merge_failed",
    "merge_sha_unknown",
    "post_merge_fast_gate_failed",
    "post_merge_docker_build_failed",
    "post_merge_deploy_failed",
    "post_merge_watch_timeout",
    "status_ledger_write_failed",
    "ok_pr_opened_no_auto_merge",
    "ok_pr_merged",
    # A21e conveyor stop reasons
    "conveyor_requires_auto_merge",
    "conveyor_selector_unavailable",
    "conveyor_selector_repeated_merged_unit",
    "conveyor_selector_repeated_unit_without_status_change",
    "conveyor_operator_stop_after_current",
    "conveyor_operator_stop_signal_file",
    "conveyor_status_artifact_refresh_failed",
    "ok_conveyor_completed_no_eligible_unit",
)

#: Closed safety-gate vocabulary. Each gate evaluates PASS / FAIL.
SAFETY_GATE: Final[tuple[str, ...]] = (
    "selector_available",
    "selection_status_ok",
    "unit_present",
    "auto_allowed_authority",
    "low_risk",
    "no_operator_gate",
    "no_operator_go_required",
    "expected_files_nonempty",
    "forbidden_files_nonempty",
    "required_tests_nonempty",
    "no_forbidden_in_expected",
    "not_terminal_status",
    "max_units_per_run_one",
    "implementation_strategy_configured",
    # A21d auto-merge gates
    "auto_merge_enabled",
    "pr_runner_originated",
    "pr_branch_matches_runner_convention",
    "pr_title_contains_unit_id",
    "pr_body_contains_runner_signature",
    "pr_diff_within_expected_files",
    "pr_diff_no_forbidden_path",
    "ci_status_clean",
    "mergeability_clean",
    "no_admin_merge_required",
    "max_merges_per_run_one",
)

#: Closed gate-result vocabulary.
GATE_RESULT: Final[tuple[str, ...]] = ("PASS", "FAIL", "NOT_CHECKED")

#: Closed runner-mode vocabulary.
RUNNER_MODE: Final[tuple[str, ...]] = (
    "status_only",
    "plan_only",
    "run_one",
    "run_continuous",
)

#: Closed implementation-strategy vocabulary. ``none`` is the default
#: and refuses to execute. ``external_command`` shells out to an
#: operator-supplied command via ``--implementation-command``.
IMPLEMENTATION_STRATEGY: Final[tuple[str, ...]] = (
    "none",
    "external_command",
)


# ---------------------------------------------------------------------------
# Forbidden-path patterns (no-touch list). Any expected_files entry
# matching these refuses the run at the no_forbidden_in_expected gate.
# Any diff path matching these refuses the run at the diff-scope check.
# Patterns match by ``startswith`` after normalising to POSIX.
# ---------------------------------------------------------------------------

FORBIDDEN_PATH_PATTERNS: Final[tuple[str, ...]] = (
    ".claude/",
    ".github/",
    "dashboard/dashboard.py",
    "automation/live_gate.py",
    "broker/",
    "agent/risk/",
    "agent/execution/",
    "live/",
    "paper/",
    "shadow/",
    "trading/",
    "docs/roadmap/Roadmap v6.md",
    "docs/roadmap/Roadmap v6 Addendum.md",
    "docs/roadmap/autonomous_development.txt",
    "docs/governance/execution_authority.md",
    "docs/governance/no_touch_paths.md",
    "reporting/execution_authority.py",
    "reporting/development_queue_admission_policy.py",
    "docs/development_work_queue/",
    "tests/regression/",
    "research/research_latest.json",
    "research/strategy_matrix.csv",
    "artifacts/",
)


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

SAFETY_GATE_RESULT_FIELDS: Final[tuple[str, ...]] = (
    "gate",
    "result",
    "detail",
)

COMMAND_RUN_FIELDS: Final[tuple[str, ...]] = (
    "command",
    "exit_code",
    "duration_ms",
    "stdout_excerpt",
    "stderr_excerpt",
)

RUNNER_REPORT_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "module_version",
    "report_kind",
    "generated_at_utc",
    "mode",
    "max_units_per_run",
    "max_merges_per_run",
    "auto_merge_enabled",
    "implementation_strategy",
    "selected_unit_id",
    "selected_phase",
    "selected_authority_class",
    "selected_risk_class",
    "selected_operator_gate",
    "branch_name",
    "safety_gate_results",
    "commands_run",
    "files_changed",
    "tests_run",
    "pr_number",
    "ci_status",
    "pr_merge_sha",
    "post_merge_gates",
    "ledger_update_path",
    "stop_reason",
    "final_runner_status",
    "next_required_operator_action",
    "step5_enabled_substage",
    "step5_implementation_allowed",
    "runner_invariants",
)

#: Pinned runner-branch prefix. The auto-merge phase verifies the PR
#: branch name starts with this prefix as the runner-origin check.
RUNNER_BRANCH_PREFIX: Final[str] = "step5-a21c/"

#: Pinned runner-signature string. Every PR body emitted by the
#: runner contains this verbatim. The auto-merge phase verifies the
#: PR body contains this string before merging (defence in depth in
#: addition to the same-invocation PR-number check).
RUNNER_PR_SIGNATURE: Final[str] = (
    "Auto-prepared by `reporting.autonomous_pr_runner`"
)

#: Optional operator soft-stop sentinel file. If present at the
#: start of a conveyor iteration, the conveyor treats the remainder
#: of the run as ``stop_after_current = True``. The file is local-
#: only (``logs/`` is gitignored) and the operator creates it
#: manually to stop a running conveyor cleanly without sending
#: SIGINT.
CONVEYOR_STOP_SIGNAL_REL_PATH: Final[str] = (
    "logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal"
)

# ---------------------------------------------------------------------------
# A24 — External-command template constants (closed-vocab)
# ---------------------------------------------------------------------------

#: Bounded length cap on scalar token values after stringification.
MAX_EXTERNAL_COMMAND_SCALAR_TOKEN_LEN: Final[int] = 240

#: Bounded length cap on JSON-serialised list-token values.
MAX_EXTERNAL_COMMAND_JSON_TOKEN_LEN: Final[int] = 8000

#: Closed set of scalar tokens. Each maps to one unit-dict field
#: that must be a non-empty ``str``. Substituted verbatim into the
#: operator-supplied template before ``shlex.split``.
EXTERNAL_COMMAND_SCALAR_TOKENS: Final[tuple[str, ...]] = (
    "unit_id",
    "phase",
    "title",
    "risk_class",
    "operator_gate",
)

#: Closed set of JSON-list tokens. Each maps to one unit-dict field
#: that must be a ``list`` (or ``tuple``) of strings. The value is
#: compact-JSON-serialised deterministically before substitution.
EXTERNAL_COMMAND_JSON_TOKENS: Final[tuple[str, ...]] = (
    "expected_files_json",
    "forbidden_files_json",
    "required_tests_json",
    "definition_of_done_json",
    "stop_conditions_json",
)

#: Union of allowed tokens. Any ``{token}`` in the template that is
#: not in this set fails closed before invocation.
EXTERNAL_COMMAND_ALLOWED_TOKENS: Final[tuple[str, ...]] = (
    EXTERNAL_COMMAND_SCALAR_TOKENS + EXTERNAL_COMMAND_JSON_TOKENS
)

#: Map every template token to the unit-dict field it sources from.
#: Tokens are surface names; fields are the A20b unit-record keys.
_EXTERNAL_COMMAND_TOKEN_TO_UNIT_FIELD: Final[dict[str, str]] = {
    "unit_id": "id",
    "phase": "phase",
    "title": "title",
    "risk_class": "risk_class",
    "operator_gate": "operator_gate",
    "expected_files_json": "expected_files",
    "forbidden_files_json": "forbidden_files",
    "required_tests_json": "required_tests",
    "definition_of_done_json": "definition_of_done",
    "stop_conditions_json": "stop_conditions",
}

#: Pattern for the only allowed template syntax: ``{lowercase_token}``.
#: No attribute access (``{foo.bar}``), no indexing (``{foo[0]}``),
#: no format specs (``{foo:fmt}``), no positional refs (``{0}``).
_EXTERNAL_COMMAND_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{([a-z_]+)\}"
)

#: A21e per-iteration summary schema. Exact and ordered.
CONVEYOR_ITERATION_SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "iteration",
    "started_at_utc",
    "selected_unit_id",
    "selected_phase",
    "branch_name",
    "pr_number",
    "pr_merge_sha",
    "ci_status",
    "stop_reason",
    "final_runner_status",
    "post_merge_gates",
)

#: A21e per-iteration selector snapshot fields. Exact and ordered.
CONVEYOR_SELECTOR_RESULT_FIELDS: Final[tuple[str, ...]] = (
    "iteration",
    "selection_status",
    "selected_unit_id",
    "selected_authority_class",
    "selected_risk_class",
    "selected_operator_gate",
    "requires_operator_go",
    "candidate_count",
    "eligible_candidate_count",
)

#: A21e conveyor report schema. Exact and ordered.
CONVEYOR_REPORT_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "module_version",
    "report_kind",
    "generated_at_utc",
    "mode",
    "started_at_utc",
    "ended_at_utc",
    "auto_merge_enabled",
    "stop_after_current_requested",
    "implementation_strategy",
    "units_attempted",
    "units_pr_opened",
    "units_merged",
    "units_blocked",
    "unit_ids_processed",
    "pr_numbers_opened",
    "merge_shas",
    "post_merge_gates_by_iteration",
    "selector_results_by_iteration",
    "iteration_summaries",
    "final_iteration_full_report",
    "final_stop_reason",
    "final_selector_status",
    "final_runner_status",
    "next_required_operator_action",
    "step5_enabled_substage",
    "step5_implementation_allowed",
    "runner_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_UNITS_PER_RUN_HARD_CAP: Final[int] = 1
MAX_MERGES_PER_RUN_HARD_CAP: Final[int] = 1
MAX_BRANCH_NAME_LEN: Final[int] = 200
MAX_COMMAND_EXCERPT_LEN: Final[int] = 4000
MAX_DETAIL_LEN: Final[int] = 240
MAX_COMMANDS_RECORDED: Final[int] = 64
MAX_FILES_CHANGED_RECORDED: Final[int] = 64
MAX_TESTS_RECORDED: Final[int] = 64
MAX_BRANCH_NAME_PREFIX_LEN: Final[int] = 64
DEFAULT_COMMAND_TIMEOUT_SECONDS: Final[int] = 600
DEFAULT_CI_WATCH_TIMEOUT_SECONDS: Final[int] = 1800
DEFAULT_POST_MERGE_WATCH_TIMEOUT_SECONDS: Final[int] = 1800
MAX_SHA_LEN_FOR_RUN: Final[int] = 64


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "autonomous_pr_runner"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"

_WRITE_PREFIX: Final[str] = "logs/autonomous_pr_runner/"


# ---------------------------------------------------------------------------
# Runner invariants emitted on every report
# ---------------------------------------------------------------------------

_BASE_RUNNER_INVARIANTS: Final[dict[str, bool]] = {
    "deterministic_evaluation": True,
    "import_is_side_effect_free": True,
    "subprocess_module_used_only_inside_run_one": True,
    "no_runtime_trading_authority": True,
    "no_step5_broad": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "no_auto_merge_outside_bounded_a21d_slice": True,
    "no_arbitrary_pr_auto_merge": True,
    "no_non_runner_originated_pr_merge": True,
    "no_admin_merge": True,
    "no_force_push": True,
    "no_hook_bypass": True,
    "no_deploy_invocation": True,
    "no_deploy_workflow_trigger": True,
    "no_static_seed_mutation": True,
    "no_a21a_seed_mutation": True,
    "no_a20b_seed_mutation": True,
    "no_work_queue_jsonl_mutation": True,
    "no_second_unit_continuation": True,
    "no_branch_creation_outside_run_one": True,
    "no_pr_creation_outside_run_one": True,
    "no_pr_merge_outside_auto_merge_phase": True,
    "no_mutation_routes": True,
    "no_approval_buttons": True,
    "no_approval_inbox_mutation": True,
    "no_test_weakening": True,
    "writes_only_to_allowlisted_logs": True,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "writes_to_work_queue_jsonl": False,
    "writes_to_static_a21a_seed": False,
    "writes_to_static_a20b_seed": False,
    "calls_llm_or_external_api": False,
    "uses_network": False,
    "uses_subprocess_outside_run_one": False,
    "calls_execution_authority_classifier": False,
    "bounded_step5_pr_creation_only": True,
    "bounded_step5_auto_merge_only_for_runner_pr": True,
    "fail_closed_on_unsafe_unit": True,
    "fail_closed_on_diff_outside_expected_files": True,
    "fail_closed_on_forbidden_diff_path": True,
    "fail_closed_on_test_failure": True,
    "fail_closed_on_governance_lint_failure": True,
    "fail_closed_on_ci_failure": True,
    "fail_closed_on_unknown_evidence": True,
    "fail_closed_on_non_runner_originated_pr": True,
    "fail_closed_on_dirty_mergeability": True,
    "fail_closed_on_post_merge_gate_failure": True,
    "fail_closed_on_ledger_write_failure": True,
    "step5_implementation_allowed": False,
    "max_units_per_run_hard_capped_at_one": True,
    "max_merges_per_run_hard_capped_at_one": True,
    "auto_merge_requires_explicit_opt_in": True,
    "auto_merge_requires_ci_green": True,
    "auto_merge_requires_runner_origin": True,
    "auto_merge_squash_only_no_admin": True,
    "ledger_update_via_runner_merges_artifact_only": True,
    # A21e continuous-conveyor pins
    "conveyor_has_no_artificial_max_units_cap": True,
    "conveyor_has_no_wall_clock_budget_stop": True,
    "conveyor_has_no_per_unit_timeout_as_queue_policy": True,
    "conveyor_stops_only_on_no_eligible_or_safety_or_operator_stop": True,
    "conveyor_re_runs_selector_between_iterations": True,
    "conveyor_refreshes_status_artifact_between_iterations": True,
    "conveyor_status_update_only_via_runner_merges_artifact": True,
    "conveyor_operator_soft_stop_supported": True,
    "conveyor_never_merges_arbitrary_prs": True,
    "conveyor_never_continues_past_same_unit_without_status_change": True,
    "conveyor_never_re_selects_already_merged_unit": True,
    # A22 strategic-mandate runner pins
    "accepts_strategically_preapproved_authority": True,
    "accepts_medium_risk_only_when_strategically_preapproved": True,
    "never_accepts_needs_human_authority_for_execution": True,
    "never_accepts_permanently_denied_authority_for_execution": True,
    "never_accepts_high_or_critical_risk": True,
    "elevated_exceptions_remain_operator_driven": True,
    # A24 external-command templating pins
    "external_command_strategy_supports_unit_templating": True,
    "external_command_template_uses_closed_vocab_tokens_only": True,
    "external_command_template_rejects_unknown_tokens": True,
    "external_command_template_rejects_attribute_or_index_access": True,
    "external_command_template_uses_no_eval_or_exec": True,
    "external_command_template_uses_no_shell_true": True,
    "external_command_template_bounds_scalar_and_json_token_length": True,
}


# ---------------------------------------------------------------------------
# Dataclasses (deterministic typed records)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CommandResult:
    """Result of a single shell command. Returned by ShellRunner."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@dataclasses.dataclass(frozen=True)
class ImplementationResult:
    """Result of an implementation strategy invocation."""

    success: bool
    reason: str
    files_changed: tuple[str, ...]


# ---------------------------------------------------------------------------
# Injectable interfaces (Protocols)
# ---------------------------------------------------------------------------


class ShellRunner(Protocol):
    """Pluggable shell-command runner.

    Concrete implementations: ``_RealShellRunner`` (uses
    ``subprocess`` lazily; constructed only inside ``run_one``) and
    test-injected fakes.
    """

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> CommandResult: ...


class ImplementationStrategy(Protocol):
    """Pluggable implementation strategy.

    ``invoke(unit, repo_root)`` is expected to mutate the filesystem
    under ``repo_root`` in a way that satisfies the unit's
    ``expected_files`` contract. The default in-module strategies are
    ``_NoneStrategy`` (refuses) and ``_ExternalCommandStrategy``
    (shells out to a configured command).
    """

    def invoke(
        self,
        unit: dict[str, Any],
        *,
        repo_root: Path,
        shell: ShellRunner,
    ) -> ImplementationResult: ...


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


def _is_forbidden_path(path: str) -> bool:
    posix = path.replace("\\", "/")
    for pattern in FORBIDDEN_PATH_PATTERNS:
        if pattern.endswith("/"):
            if posix.startswith(pattern):
                return True
        else:
            if posix == pattern:
                return True
    return False


def _gate(name: str, result: str, detail: str = "") -> dict[str, Any]:
    if name not in SAFETY_GATE:
        raise ValueError(f"unknown safety gate: {name}")
    if result not in GATE_RESULT:
        raise ValueError(f"unknown gate result: {result}")
    return {
        "gate": name,
        "result": result,
        "detail": _bounded_str(detail, MAX_DETAIL_LEN),
    }


# ---------------------------------------------------------------------------
# Safety gate evaluation
# ---------------------------------------------------------------------------


def evaluate_safety_gates(
    *,
    selector_snapshot: dict[str, Any] | None,
    unit: dict[str, Any] | None,
    max_units: int,
    implementation_strategy: str,
    max_merges: int = MAX_MERGES_PER_RUN_HARD_CAP,
) -> tuple[list[dict[str, Any]], str | None]:
    """Run every safety gate. Return ``(results, first_failure_reason)``.

    ``first_failure_reason`` is a closed-vocab STOP_REASON value or
    ``None`` if every gate passed. Gates that depend on a previous
    gate's pass are recorded as ``NOT_CHECKED`` if that previous gate
    failed (defence in depth, no silent cascade).

    Note: the A21d auto-merge gates (``pr_runner_originated``,
    ``pr_diff_within_expected_files``, ``ci_status_clean``,
    ``mergeability_clean``, etc.) are NOT evaluated here; they only
    apply mid-execution after the runner has opened the PR. This
    function evaluates the pre-execution gates only. The
    ``max_merges_per_run_one`` gate IS evaluated here because it is
    a static pre-flight invariant.
    """
    results: list[dict[str, Any]] = []
    fail: str | None = None

    # selector_available
    if selector_snapshot is None:
        results.append(
            _gate(
                "selector_available",
                "FAIL",
                "no selector snapshot provided",
            )
        )
        fail = "selector_unavailable"
        for g in SAFETY_GATE:
            if g != "selector_available":
                results.append(_gate(g, "NOT_CHECKED", "blocked upstream"))
        return results, fail
    results.append(_gate("selector_available", "PASS", ""))

    # selection_status_ok
    #
    # ``OK_SELECTED`` is the happy path. ``ALL_NEEDS_HUMAN_GATED``
    # also names a specific selected unit (just one that needs
    # operator-go); we let the per-authority gate catch that so the
    # operator sees the more specific stop reason
    # (``unsafe_authority_class`` / ``unsafe_operator_gate`` /
    # ``requires_operator_go``). Any other status means the selector
    # did not pick a single unit and we stop here.
    sel = selector_snapshot.get("selection") or {}
    sel_status = _bounded_str(sel.get("selection_status"), 64)
    if sel_status not in {"OK_SELECTED", "ALL_NEEDS_HUMAN_GATED"}:
        results.append(
            _gate(
                "selection_status_ok",
                "FAIL",
                f"selection_status={sel_status}",
            )
        )
        if sel_status == "":
            fail = "selector_unavailable"
        elif sel_status in {"NO_ELIGIBLE_UNITS", "UPSTREAM_UNAVAILABLE"}:
            fail = "no_eligible_unit"
        else:
            fail = "ambiguous_selection"
        for g in SAFETY_GATE:
            if g not in {"selector_available", "selection_status_ok"}:
                results.append(_gate(g, "NOT_CHECKED", "blocked upstream"))
        return results, fail
    results.append(_gate("selection_status_ok", "PASS", ""))

    # unit_present
    if unit is None:
        results.append(
            _gate(
                "unit_present",
                "FAIL",
                "selected unit not found in A20b decomposition",
            )
        )
        fail = "no_eligible_unit"
        for g in SAFETY_GATE:
            if g not in {
                "selector_available",
                "selection_status_ok",
                "unit_present",
            }:
                results.append(_gate(g, "NOT_CHECKED", "blocked upstream"))
        return results, fail
    results.append(_gate("unit_present", "PASS", ""))

    # auto_allowed_authority
    # A22: accepts AUTO_ALLOWED OR STRATEGICALLY_PREAPPROVED. The
    # latter is the mandate-promoted class that A20c's post-process
    # produces for NEEDS_HUMAN units meeting every condition of the
    # operator's strategic execution mandate.
    final_class = _bounded_str(sel.get("selected_authority_class"), 32)
    if final_class not in {"AUTO_ALLOWED", "STRATEGICALLY_PREAPPROVED"}:
        results.append(
            _gate(
                "auto_allowed_authority",
                "FAIL",
                f"authority_class={final_class}",
            )
        )
        if fail is None:
            fail = "unsafe_authority_class"
    else:
        results.append(_gate("auto_allowed_authority", "PASS", ""))

    # low_risk
    # A22: accepts LOW always. Accepts MEDIUM only when the unit is
    # STRATEGICALLY_PREAPPROVED — the strategic mandate explicitly
    # opts MEDIUM-risk research/scaffold units into auto-execution.
    # HIGH / CRITICAL / UNKNOWN risk are never accepted here.
    risk_class = _bounded_str(sel.get("selected_risk_class"), 16)
    if risk_class == "LOW":
        results.append(_gate("low_risk", "PASS", ""))
    elif (
        risk_class == "MEDIUM"
        and final_class == "STRATEGICALLY_PREAPPROVED"
    ):
        results.append(
            _gate(
                "low_risk",
                "PASS",
                "medium_risk_strategically_preapproved",
            )
        )
    else:
        results.append(
            _gate("low_risk", "FAIL", f"risk_class={risk_class}")
        )
        if fail is None:
            fail = "unsafe_risk_class"

    # no_operator_gate
    gate_val = _bounded_str(sel.get("selected_operator_gate"), 64)
    if gate_val != "none":
        results.append(
            _gate(
                "no_operator_gate",
                "FAIL",
                f"operator_gate={gate_val}",
            )
        )
        if fail is None:
            fail = "unsafe_operator_gate"
    else:
        results.append(_gate("no_operator_gate", "PASS", ""))

    # no_operator_go_required
    requires_go = bool(sel.get("requires_operator_go"))
    if requires_go:
        results.append(
            _gate(
                "no_operator_go_required",
                "FAIL",
                "requires_operator_go=True",
            )
        )
        if fail is None:
            fail = "requires_operator_go"
    else:
        results.append(_gate("no_operator_go_required", "PASS", ""))

    # expected_files_nonempty
    expected = unit.get("expected_files") or []
    if not isinstance(expected, list) or not expected:
        results.append(
            _gate(
                "expected_files_nonempty",
                "FAIL",
                "expected_files is empty or not a list",
            )
        )
        if fail is None:
            fail = "missing_expected_files"
    else:
        results.append(_gate("expected_files_nonempty", "PASS", ""))

    # forbidden_files_nonempty
    forbidden = unit.get("forbidden_files") or []
    if not isinstance(forbidden, list) or not forbidden:
        results.append(
            _gate(
                "forbidden_files_nonempty",
                "FAIL",
                "forbidden_files is empty or not a list",
            )
        )
        if fail is None:
            fail = "missing_forbidden_files"
    else:
        results.append(_gate("forbidden_files_nonempty", "PASS", ""))

    # required_tests_nonempty
    required_tests = unit.get("required_tests") or []
    if not isinstance(required_tests, list) or not required_tests:
        results.append(
            _gate(
                "required_tests_nonempty",
                "FAIL",
                "required_tests is empty or not a list",
            )
        )
        if fail is None:
            fail = "missing_required_tests"
    else:
        results.append(_gate("required_tests_nonempty", "PASS", ""))

    # no_forbidden_in_expected
    forbidden_hits = [
        p for p in expected
        if isinstance(p, str) and _is_forbidden_path(p)
    ]
    if forbidden_hits:
        detail = ",".join(forbidden_hits[:3])
        results.append(
            _gate("no_forbidden_in_expected", "FAIL", detail)
        )
        if fail is None:
            fail = "forbidden_path_in_expected_files"
    else:
        results.append(_gate("no_forbidden_in_expected", "PASS", ""))

    # not_terminal_status
    static_status = _bounded_str(unit.get("status"), 32)
    if static_status in {"merged", "blocked", "skipped", "failed"}:
        results.append(
            _gate(
                "not_terminal_status",
                "FAIL",
                f"status={static_status}",
            )
        )
        if fail is None:
            fail = "terminal_status"
    else:
        results.append(_gate("not_terminal_status", "PASS", ""))

    # max_units_per_run_one
    if max_units != MAX_UNITS_PER_RUN_HARD_CAP:
        results.append(
            _gate(
                "max_units_per_run_one",
                "FAIL",
                f"requested={max_units}",
            )
        )
        if fail is None:
            fail = "max_units_exceeded"
    else:
        results.append(_gate("max_units_per_run_one", "PASS", ""))

    # implementation_strategy_configured
    if implementation_strategy == "none":
        results.append(
            _gate(
                "implementation_strategy_configured",
                "FAIL",
                "default 'none' refuses to run",
            )
        )
        if fail is None:
            fail = "implementation_strategy_not_configured"
    elif implementation_strategy not in IMPLEMENTATION_STRATEGY:
        results.append(
            _gate(
                "implementation_strategy_configured",
                "FAIL",
                f"unknown strategy={implementation_strategy}",
            )
        )
        if fail is None:
            fail = "implementation_strategy_not_configured"
    else:
        results.append(_gate("implementation_strategy_configured", "PASS", ""))

    # max_merges_per_run_one (A21d pre-flight invariant)
    if max_merges != MAX_MERGES_PER_RUN_HARD_CAP:
        results.append(
            _gate(
                "max_merges_per_run_one",
                "FAIL",
                f"requested={max_merges}",
            )
        )
        if fail is None:
            fail = "max_merges_exceeded"
    else:
        results.append(_gate("max_merges_per_run_one", "PASS", ""))

    return results, fail


# ---------------------------------------------------------------------------
# Real shell runner factory (subprocess imported lazily)
# ---------------------------------------------------------------------------


def _real_shell_runner_factory() -> ShellRunner:
    """Construct a real ShellRunner.

    ``subprocess`` is imported inside this function so the top-level
    ``import reporting.autonomous_pr_runner`` is import-safe. This
    factory is only invoked inside ``run_one`` when the operator has
    passed ``--run-one`` AND ``--implementation-strategy`` other than
    ``none``.
    """
    import subprocess as _subprocess  # local import: lazy on purpose
    import time as _time

    class _RealShellRunner:
        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        ) -> CommandResult:
            start = _time.monotonic()
            try:
                proc = _subprocess.run(
                    args,
                    cwd=str(cwd) if cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except _subprocess.TimeoutExpired as exc:
                duration_ms = int((_time.monotonic() - start) * 1000)
                return CommandResult(
                    exit_code=124,
                    stdout="",
                    stderr=f"timeout after {timeout}s: {exc}",
                    duration_ms=duration_ms,
                )
            except OSError as exc:
                duration_ms = int((_time.monotonic() - start) * 1000)
                return CommandResult(
                    exit_code=127,
                    stdout="",
                    stderr=f"command not found: {exc}",
                    duration_ms=duration_ms,
                )
            duration_ms = int((_time.monotonic() - start) * 1000)
            return CommandResult(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_ms=duration_ms,
            )

    return _RealShellRunner()


# ---------------------------------------------------------------------------
# Built-in implementation strategies
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# A24 — Unit-templated external command expansion
# ---------------------------------------------------------------------------


def expand_external_command_template(
    template: str, unit: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Substitute closed-vocab unit-aware tokens into an operator-
    supplied ``--implementation-command`` template.

    Returns ``(expanded, None)`` on success or
    ``(None, error_reason)`` on failure. ``error_reason`` is a
    bounded diagnostic string suitable for the
    :attr:`ImplementationResult.reason` field; the runner maps every
    such failure to the closed-vocab stop reason
    ``implementation_strategy_failed``.

    Allowed template tokens are pinned by
    :data:`EXTERNAL_COMMAND_ALLOWED_TOKENS`. Scalar tokens
    (``unit_id``, ``phase``, ``title``, ``risk_class``,
    ``operator_gate``) substitute the unit-record string value
    verbatim. JSON tokens (``expected_files_json`` etc.) serialise
    the corresponding list field as compact deterministic JSON.

    Fail-closed rules:

    * unknown token name (not in
      :data:`EXTERNAL_COMMAND_ALLOWED_TOKENS`);
    * unit-dict is missing the field a token references;
    * scalar field is not a ``str``;
    * scalar value exceeds
      :data:`MAX_EXTERNAL_COMMAND_SCALAR_TOKEN_LEN`;
    * scalar value contains a newline (``\\n`` or ``\\r``);
    * JSON field is not a list/tuple;
    * JSON-serialised value exceeds
      :data:`MAX_EXTERNAL_COMMAND_JSON_TOKEN_LEN`;
    * expanded string still contains an unmatched ``{`` or ``}``
      (defence against typos like ``{unit_id``);
    * expanded string is empty / whitespace-only after substitution.

    This function does NOT call :func:`shlex.split` itself — the
    caller (:class:`_ExternalCommandStrategy`) does that downstream.
    The two-step layout keeps templating logic unit-testable in
    isolation.
    """
    if not isinstance(template, str):
        return None, "template_not_a_string"

    # Step 1: enumerate every {token} occurrence (preserving
    # duplicates) and reject any unknown token before we substitute.
    found_tokens = _EXTERNAL_COMMAND_TOKEN_PATTERN.findall(template)
    allowed = set(EXTERNAL_COMMAND_ALLOWED_TOKENS)
    for token in found_tokens:
        if token not in allowed:
            return None, _bounded_str(
                f"template_unknown_token:{token}", MAX_DETAIL_LEN
            )

    # Step 2: build the substitution map from the unit record.
    substitutions: dict[str, str] = {}
    scalar_tokens = set(EXTERNAL_COMMAND_SCALAR_TOKENS)
    json_tokens = set(EXTERNAL_COMMAND_JSON_TOKENS)
    for token in set(found_tokens):
        field = _EXTERNAL_COMMAND_TOKEN_TO_UNIT_FIELD[token]
        if field not in unit:
            return None, _bounded_str(
                f"template_missing_field:{token}:{field}",
                MAX_DETAIL_LEN,
            )
        raw_value = unit[field]
        if token in scalar_tokens:
            if not isinstance(raw_value, str):
                return None, _bounded_str(
                    f"template_scalar_not_string:{token}",
                    MAX_DETAIL_LEN,
                )
            if "\n" in raw_value or "\r" in raw_value:
                return None, _bounded_str(
                    f"template_scalar_has_newline:{token}",
                    MAX_DETAIL_LEN,
                )
            if len(raw_value) > MAX_EXTERNAL_COMMAND_SCALAR_TOKEN_LEN:
                return None, _bounded_str(
                    f"template_scalar_too_long:{token}",
                    MAX_DETAIL_LEN,
                )
            substitutions[token] = raw_value
        else:
            # JSON token — must serialise a list/tuple.
            if not isinstance(raw_value, (list, tuple)):
                return None, _bounded_str(
                    f"template_json_field_not_list:{token}",
                    MAX_DETAIL_LEN,
                )
            # Compact, deterministic. List ordering preserved as
            # given by the seed.
            try:
                serialised = json.dumps(
                    list(raw_value),
                    separators=(",", ":"),
                    sort_keys=False,
                    ensure_ascii=True,
                )
            except (TypeError, ValueError) as exc:
                return None, _bounded_str(
                    f"template_json_serialise_error:{token}:{exc}",
                    MAX_DETAIL_LEN,
                )
            if len(serialised) > MAX_EXTERNAL_COMMAND_JSON_TOKEN_LEN:
                return None, _bounded_str(
                    f"template_json_too_long:{token}",
                    MAX_DETAIL_LEN,
                )
            substitutions[token] = serialised

    # Step 3: perform the substitution.
    def _replace_one(match: re.Match[str]) -> str:
        return substitutions[match.group(1)]

    expanded = _EXTERNAL_COMMAND_TOKEN_PATTERN.sub(
        _replace_one, template
    )

    # Step 4: defence-in-depth — any leftover {/} indicates a
    # malformed template (e.g. ``{unit_id`` with no closing brace,
    # or ``{Unit_ID}`` that escaped the lower-case regex).
    if "{" in expanded or "}" in expanded:
        return None, "template_unmatched_brace"

    # Step 5: defence-in-depth — empty / whitespace-only expansion.
    if not expanded.strip():
        return None, "template_expanded_empty"

    return expanded, None


class _NoneStrategy:
    """Refuse-to-run strategy. The default."""

    name = "none"

    def invoke(
        self,
        unit: dict[str, Any],
        *,
        repo_root: Path,
        shell: ShellRunner,
    ) -> ImplementationResult:
        return ImplementationResult(
            success=False,
            reason="implementation_strategy_not_configured",
            files_changed=(),
        )


class _ExternalCommandStrategy:
    """Shell out to an operator-supplied command template.

    The template is expanded via
    :func:`expand_external_command_template` against the selected
    A20b unit BEFORE :func:`shlex.split`. The closed-vocab token
    set (see :data:`EXTERNAL_COMMAND_ALLOWED_TOKENS`) lets the
    operator parametrise one template across every iteration of
    the continuous conveyor without giving the strategy arbitrary
    field access. Unknown tokens, missing fields, oversize values,
    newline-bearing scalars, or non-list JSON fields all fail
    closed before any shell invocation.

    A template with no ``{token}`` placeholders is still accepted
    (backward-compat with A21c / A21d static-command tests). The
    runner does not interpret the command output; it only checks
    the exit code and the resulting git diff.
    """

    name = "external_command"

    def __init__(self, command: str, timeout: int) -> None:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("external_command requires a non-empty command")
        self._command = command
        self._timeout = max(1, int(timeout))

    def invoke(
        self,
        unit: dict[str, Any],
        *,
        repo_root: Path,
        shell: ShellRunner,
    ) -> ImplementationResult:
        # A24: expand operator-supplied template against the unit
        # record before shlex.split. Returns (None, reason) on every
        # fail-closed condition pinned by tests.
        expanded, expand_err = expand_external_command_template(
            self._command, unit
        )
        if expand_err is not None:
            return ImplementationResult(
                success=False,
                reason=expand_err,
                files_changed=(),
            )
        assert expanded is not None  # noqa: S101 (type-narrow only)
        try:
            args = shlex.split(expanded)
        except ValueError as exc:
            return ImplementationResult(
                success=False,
                reason=_bounded_str(
                    f"command_parse_error:{exc}", MAX_DETAIL_LEN
                ),
                files_changed=(),
            )
        if not args:
            return ImplementationResult(
                success=False,
                reason="command_parse_empty",
                files_changed=(),
            )
        result = shell.run(args, cwd=repo_root, timeout=self._timeout)
        if result.exit_code != 0:
            return ImplementationResult(
                success=False,
                reason=(
                    f"external_command_exit_code={result.exit_code}"
                ),
                files_changed=(),
            )
        return ImplementationResult(
            success=True,
            reason="external_command_ok",
            files_changed=(),
        )


def _build_strategy(
    name: str,
    *,
    external_command: str | None,
    external_timeout: int,
) -> ImplementationStrategy:
    if name == "none":
        return _NoneStrategy()
    if name == "external_command":
        return _ExternalCommandStrategy(
            command=external_command or "",
            timeout=external_timeout,
        )
    raise ValueError(f"unknown implementation strategy: {name}")


# ---------------------------------------------------------------------------
# Plan + report assembly
# ---------------------------------------------------------------------------


def _empty_report(
    *,
    mode: str,
    ts: str,
    max_units: int,
    implementation_strategy: str,
    max_merges: int = 0,
    auto_merge_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": mode,
        "max_units_per_run": max_units,
        "max_merges_per_run": max_merges,
        "auto_merge_enabled": auto_merge_enabled,
        "implementation_strategy": implementation_strategy,
        "selected_unit_id": "",
        "selected_phase": "",
        "selected_authority_class": "",
        "selected_risk_class": "",
        "selected_operator_gate": "",
        "branch_name": "",
        "safety_gate_results": [],
        "commands_run": [],
        "files_changed": [],
        "tests_run": [],
        "pr_number": 0,
        "ci_status": "",
        "pr_merge_sha": "",
        "post_merge_gates": [],
        "ledger_update_path": "",
        "stop_reason": "",
        "final_runner_status": "not_run",
        "next_required_operator_action": "",
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "runner_invariants": dict(_BASE_RUNNER_INVARIANTS),
    }


def _attach_selection(
    report: dict[str, Any],
    selector_snapshot: dict[str, Any] | None,
    unit: dict[str, Any] | None,
) -> None:
    if selector_snapshot is None:
        return
    sel = selector_snapshot.get("selection") or {}
    report["selected_unit_id"] = _bounded_str(
        sel.get("selected_unit_id"), 200
    )
    report["selected_phase"] = _bounded_str(sel.get("selected_phase"), 64)
    report["selected_authority_class"] = _bounded_str(
        sel.get("selected_authority_class"), 32
    )
    report["selected_risk_class"] = _bounded_str(
        sel.get("selected_risk_class"), 16
    )
    report["selected_operator_gate"] = _bounded_str(
        sel.get("selected_operator_gate"), 64
    )
    _ = unit  # unit may be used by callers later; signature stable


def _branch_name_for_unit(unit_id: str) -> str:
    sanitized = "".join(
        ch if (ch.isalnum() or ch in "-_/") else "-"
        for ch in unit_id
    )
    prefix = "step5-a21c"
    return _bounded_str(
        f"{prefix}/{sanitized}",
        MAX_BRANCH_NAME_LEN,
    )


# ---------------------------------------------------------------------------
# Selector + unit lookup
# ---------------------------------------------------------------------------


def _load_selector_snapshot(
    *, repo_root: Path
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort selector load. Returns ``(snapshot, error)``."""
    try:
        snap = rnu.collect_snapshot(repo_root=repo_root)
    except Exception as exc:  # defensive
        return None, _bounded_str(repr(exc), MAX_DETAIL_LEN)
    return snap, None


def _find_unit_in_a20b(
    *,
    unit_id: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Find the unit record in the A20b artefact by id."""
    units_path = repo_root / "logs" / "roadmap_task_units" / "latest.json"
    if not units_path.is_file():
        return None
    try:
        payload = json.loads(units_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    units = payload.get("implementation_units")
    if not isinstance(units, list):
        return None
    for u in units:
        if isinstance(u, dict) and u.get("id") == unit_id:
            return u
    return None


# ---------------------------------------------------------------------------
# Mode entry points
# ---------------------------------------------------------------------------


def status(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
    max_units: int = MAX_UNITS_PER_RUN_HARD_CAP,
    implementation_strategy: str = "none",
    max_merges: int = MAX_MERGES_PER_RUN_HARD_CAP,
    auto_merge_enabled: bool = False,
) -> dict[str, Any]:
    """Read-only status mode. Never executes anything."""
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    report = _empty_report(
        mode="status_only",
        ts=ts,
        max_units=max_units,
        max_merges=max_merges,
        auto_merge_enabled=auto_merge_enabled,
        implementation_strategy=implementation_strategy,
    )
    snap, _err = _load_selector_snapshot(repo_root=root)
    _attach_selection(report, snap, None)
    report["final_runner_status"] = "status_only"
    report["stop_reason"] = "status_only_mode"
    report["next_required_operator_action"] = (
        "review_selector_recommendation_then_invoke_plan_only"
    )
    return report


def plan(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
    max_units: int = MAX_UNITS_PER_RUN_HARD_CAP,
    implementation_strategy: str = "none",
    max_merges: int = MAX_MERGES_PER_RUN_HARD_CAP,
    auto_merge_enabled: bool = False,
) -> dict[str, Any]:
    """Plan-only mode. Evaluates safety gates but executes nothing.

    Useful for the operator to inspect which gates would PASS / FAIL
    before authorising ``--run-one``. The plan never invokes git,
    gh, subprocess, or any implementation strategy.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    report = _empty_report(
        mode="plan_only",
        ts=ts,
        max_units=max_units,
        max_merges=max_merges,
        auto_merge_enabled=auto_merge_enabled,
        implementation_strategy=implementation_strategy,
    )
    snap, _err = _load_selector_snapshot(repo_root=root)
    unit = None
    if snap is not None:
        sel = snap.get("selection") or {}
        uid = _bounded_str(sel.get("selected_unit_id"), 200)
        if uid:
            unit = _find_unit_in_a20b(unit_id=uid, repo_root=root)
    _attach_selection(report, snap, unit)
    gates, fail_reason = evaluate_safety_gates(
        selector_snapshot=snap,
        unit=unit,
        max_units=max_units,
        implementation_strategy=implementation_strategy,
        max_merges=max_merges,
    )
    report["safety_gate_results"] = gates
    report["final_runner_status"] = "plan_only"
    report["stop_reason"] = (
        fail_reason if fail_reason is not None else "plan_only_mode"
    )
    if unit is not None and report["selected_unit_id"]:
        report["branch_name"] = _branch_name_for_unit(
            report["selected_unit_id"]
        )
    if fail_reason is not None:
        report["next_required_operator_action"] = (
            "address_safety_gate_failure_before_run_one"
        )
    else:
        report["next_required_operator_action"] = (
            "invoke_run_one_with_explicit_implementation_strategy"
        )
    return report


def _record_command(
    commands: list[dict[str, Any]],
    command_args: list[str],
    result: CommandResult,
) -> None:
    if len(commands) >= MAX_COMMANDS_RECORDED:
        return
    commands.append(
        {
            "command": _bounded_str(" ".join(command_args), 480),
            "exit_code": int(result.exit_code),
            "duration_ms": int(result.duration_ms),
            "stdout_excerpt": _bounded_str(
                result.stdout, MAX_COMMAND_EXCERPT_LEN
            ),
            "stderr_excerpt": _bounded_str(
                result.stderr, MAX_COMMAND_EXCERPT_LEN
            ),
        }
    )


def _diff_paths_after_implementation(
    shell: ShellRunner,
    *,
    repo_root: Path,
    commands: list[dict[str, Any]],
) -> tuple[list[str], CommandResult]:
    """Run ``git status --porcelain`` and parse changed paths."""
    args = ["git", "status", "--porcelain"]
    result = shell.run(args, cwd=repo_root)
    _record_command(commands, args, result)
    paths: list[str] = []
    if result.exit_code != 0:
        return paths, result
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path and path not in paths:
            paths.append(path)
        if len(paths) >= MAX_FILES_CHANGED_RECORDED:
            break
    return paths, result


def run_one(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
    max_units: int = MAX_UNITS_PER_RUN_HARD_CAP,
    max_merges: int = MAX_MERGES_PER_RUN_HARD_CAP,
    implementation_strategy_name: str = "none",
    external_command: str | None = None,
    external_command_timeout: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    auto_merge_runner_pr: bool = False,
    shell: ShellRunner | None = None,
    implementation_strategy: ImplementationStrategy | None = None,
) -> dict[str, Any]:
    """Bounded autonomous PR runner for exactly one selected unit.

    Tests inject ``shell`` and ``implementation_strategy`` so no real
    shell command is invoked. The CLI path constructs real ones from
    the operator-supplied flags.

    When ``auto_merge_runner_pr=True``, after CI on the freshly-
    created PR returns green, the runner executes the A21d
    auto-merge phase: squash-merge (no ``--admin``, no force-push,
    no hook bypass), capture merge SHA, update local main, watch
    post-merge gates, and append an evidence-backed ``merged``
    record to ``logs/roadmap_unit_status/runner_merges.json``.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    report = _empty_report(
        mode="run_one",
        ts=ts,
        max_units=max_units,
        max_merges=max_merges,
        auto_merge_enabled=bool(auto_merge_runner_pr),
        implementation_strategy=implementation_strategy_name,
    )

    # ---- Safety gates first (no execution) ---------------------------------
    snap, _err = _load_selector_snapshot(repo_root=root)
    unit = None
    if snap is not None:
        sel = snap.get("selection") or {}
        uid = _bounded_str(sel.get("selected_unit_id"), 200)
        if uid:
            unit = _find_unit_in_a20b(unit_id=uid, repo_root=root)
    _attach_selection(report, snap, unit)
    gates, fail_reason = evaluate_safety_gates(
        selector_snapshot=snap,
        unit=unit,
        max_units=max_units,
        implementation_strategy=implementation_strategy_name,
        max_merges=max_merges,
    )
    report["safety_gate_results"] = gates
    if fail_reason is not None:
        report["final_runner_status"] = "refused_unsafe"
        report["stop_reason"] = fail_reason
        report["next_required_operator_action"] = (
            "address_safety_gate_failure_before_retry"
        )
        return report

    assert unit is not None  # gates guaranteed unit_present passed

    branch_name = _branch_name_for_unit(report["selected_unit_id"])
    report["branch_name"] = branch_name

    # ---- Construct injectable surfaces if not provided ---------------------
    if shell is None:
        shell = _real_shell_runner_factory()
    if implementation_strategy is None:
        implementation_strategy = _build_strategy(
            implementation_strategy_name,
            external_command=external_command,
            external_timeout=external_command_timeout,
        )

    commands: list[dict[str, Any]] = []
    report["commands_run"] = commands

    # ---- Branch creation ---------------------------------------------------
    args = ["git", "checkout", "-b", branch_name]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_implementation"
        # Distinguish "already exists" from generic failure.
        if (
            "already exists" in (res.stderr or "")
            or "already exists" in (res.stdout or "")
        ):
            report["stop_reason"] = "branch_already_exists"
        else:
            report["stop_reason"] = "branch_creation_failed"
        report["next_required_operator_action"] = (
            "clean_up_branch_state_and_retry"
        )
        return report

    # ---- Invoke implementation strategy ------------------------------------
    impl_result = implementation_strategy.invoke(
        unit, repo_root=root, shell=shell
    )
    if not impl_result.success:
        report["final_runner_status"] = "executed_blocked_at_implementation"
        if impl_result.reason == "implementation_strategy_not_configured":
            report["stop_reason"] = "implementation_strategy_not_configured"
        else:
            report["stop_reason"] = "implementation_strategy_failed"
        report["next_required_operator_action"] = (
            "review_implementation_strategy_logs_then_retry"
        )
        return report

    # ---- Diff scope check --------------------------------------------------
    changed_paths, diff_res = _diff_paths_after_implementation(
        shell, repo_root=root, commands=commands
    )
    report["files_changed"] = changed_paths
    if diff_res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_diff"
        report["stop_reason"] = "unknown_evidence"
        report["next_required_operator_action"] = "inspect_git_status"
        return report
    if not changed_paths:
        report["final_runner_status"] = "executed_blocked_at_diff"
        report["stop_reason"] = "diff_empty"
        report["next_required_operator_action"] = (
            "implementation_strategy_produced_no_changes_review_strategy"
        )
        return report

    expected_files = [
        _bounded_str(p, 300).replace("\\", "/")
        for p in (unit.get("expected_files") or [])
        if isinstance(p, str)
    ]
    expected_set = set(expected_files)
    for p in changed_paths:
        if _is_forbidden_path(p):
            report["final_runner_status"] = "executed_blocked_at_diff"
            report["stop_reason"] = "diff_touches_forbidden_path"
            report["next_required_operator_action"] = (
                "revert_branch_strategy_violated_forbidden_path"
            )
            return report
        if p not in expected_set:
            report["final_runner_status"] = "executed_blocked_at_diff"
            report["stop_reason"] = "diff_outside_expected_files"
            report["next_required_operator_action"] = (
                "revert_branch_strategy_exceeded_expected_files"
            )
            return report

    # ---- Required tests ----------------------------------------------------
    required_tests = [
        _bounded_str(t, 240)
        for t in (unit.get("required_tests") or [])
        if isinstance(t, str)
    ]
    tests_run: list[str] = []
    for test_target in required_tests[:MAX_TESTS_RECORDED]:
        tests_run.append(test_target)
        targets = [test_target]
        args = ["python", "-m", "pytest", "-q", *targets]
        res = shell.run(args, cwd=root)
        _record_command(commands, args, res)
        if res.exit_code != 0:
            report["final_runner_status"] = "executed_blocked_at_tests"
            report["stop_reason"] = "tests_failed"
            report["tests_run"] = tests_run
            report["next_required_operator_action"] = (
                "review_failing_tests_then_revert_or_fix_branch"
            )
            return report
    report["tests_run"] = tests_run

    # ---- Smoke tests + governance lint ------------------------------------
    args = ["python", "-m", "pytest", "-q", "tests/smoke"]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_tests"
        report["stop_reason"] = "tests_failed"
        report["next_required_operator_action"] = (
            "review_smoke_failures_then_revert_branch"
        )
        return report

    args = ["python", "scripts/governance_lint.py"]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_governance_lint"
        report["stop_reason"] = "governance_lint_failed"
        report["next_required_operator_action"] = (
            "review_governance_lint_failures_then_revert_branch"
        )
        return report

    # ---- Stage + commit ----------------------------------------------------
    for p in changed_paths:
        args = ["git", "add", "--", p]
        res = shell.run(args, cwd=root)
        _record_command(commands, args, res)
        if res.exit_code != 0:
            report["final_runner_status"] = "executed_blocked_at_commit"
            report["stop_reason"] = "commit_failed"
            report["next_required_operator_action"] = (
                "inspect_git_status_then_resolve"
            )
            return report

    commit_message = _commit_message_for_unit(unit)
    args = ["git", "commit", "-m", commit_message]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_commit"
        # Distinguish hook failure from generic commit failure.
        text = (res.stdout or "") + (res.stderr or "")
        if "hook" in text.lower() and "fail" in text.lower():
            report["stop_reason"] = "hook_failed"
        else:
            report["stop_reason"] = "commit_failed"
        report["next_required_operator_action"] = (
            "review_commit_or_hook_output_then_resolve"
        )
        return report

    # ---- Push --------------------------------------------------------------
    args = ["git", "push", "-u", "origin", branch_name]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_push"
        report["stop_reason"] = "push_failed"
        report["next_required_operator_action"] = (
            "review_push_output_then_resolve"
        )
        return report

    # ---- Open PR -----------------------------------------------------------
    pr_title = _pr_title_for_unit(unit)
    pr_body = _pr_body_for_unit(unit, branch_name)
    args = [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        branch_name,
        "--title",
        pr_title,
        "--body",
        pr_body,
    ]
    res = shell.run(args, cwd=root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_pr_create"
        report["stop_reason"] = "pr_creation_failed"
        report["next_required_operator_action"] = (
            "review_gh_pr_create_output_then_resolve"
        )
        return report
    pr_number = _parse_pr_number(res.stdout)
    report["pr_number"] = pr_number

    # ---- CI watch (first verdict only) -------------------------------------
    if pr_number > 0:
        args = [
            "gh",
            "pr",
            "checks",
            str(pr_number),
            "--watch",
            "--required",
        ]
        res = shell.run(args, cwd=root, timeout=DEFAULT_CI_WATCH_TIMEOUT_SECONDS)
        _record_command(commands, args, res)
        if res.exit_code == 124:
            report["final_runner_status"] = "executed_blocked_at_ci"
            report["stop_reason"] = "ci_timeout"
            report["ci_status"] = "TIMEOUT"
            report["next_required_operator_action"] = (
                "inspect_ci_run_manually"
            )
            return report
        if res.exit_code != 0:
            report["final_runner_status"] = "executed_blocked_at_ci"
            report["stop_reason"] = "ci_failed"
            report["ci_status"] = "FAIL"
            report["next_required_operator_action"] = (
                "review_failing_ci_jobs_then_resolve"
            )
            return report
        report["ci_status"] = "PASS"

    # ---- A21d auto-merge phase (opt-in) -----------------------------------
    if not auto_merge_runner_pr:
        report["final_runner_status"] = "executed_pr_opened"
        report["stop_reason"] = "ok_pr_opened_no_auto_merge"
        report["next_required_operator_action"] = (
            "review_pr_and_decide_merge_protocol"
        )
        return report

    _auto_merge_phase(
        report=report,
        shell=shell,
        unit=unit,
        repo_root=root,
        branch_name=branch_name,
        pr_number=pr_number,
        generated_at_utc=ts,
    )
    return report


# ---------------------------------------------------------------------------
# A21d auto-merge phase
# ---------------------------------------------------------------------------


def _evaluate_auto_merge_gates(
    *,
    pr_number: int,
    branch_name: str,
    unit: dict[str, Any],
    pr_metadata: dict[str, Any],
    pr_diff_paths: list[str],
    ci_clean: bool,
    mergeability: str,
    merge_state_status: str,
    auto_merge_enabled: bool,
    max_merges: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Run the A21d auto-merge eligibility gates.

    Returns ``(gate_results, first_failure_stop_reason)``. The gates
    are evaluated in defence-in-depth order (origin checks first,
    then content, then status).
    """
    results: list[dict[str, Any]] = []
    fail: str | None = None

    # auto_merge_enabled (operator must opt in)
    if not auto_merge_enabled:
        results.append(_gate("auto_merge_enabled", "FAIL", "flag absent"))
        for g in (
            "pr_runner_originated",
            "pr_branch_matches_runner_convention",
            "pr_title_contains_unit_id",
            "pr_body_contains_runner_signature",
            "pr_diff_within_expected_files",
            "pr_diff_no_forbidden_path",
            "ci_status_clean",
            "mergeability_clean",
            "no_admin_merge_required",
        ):
            results.append(_gate(g, "NOT_CHECKED", "blocked upstream"))
        return results, "auto_merge_disabled"
    results.append(_gate("auto_merge_enabled", "PASS", ""))

    # pr_runner_originated
    if pr_number <= 0:
        results.append(
            _gate(
                "pr_runner_originated",
                "FAIL",
                "pr_number not captured by run-one",
            )
        )
        if fail is None:
            fail = "not_runner_originated"
    else:
        results.append(_gate("pr_runner_originated", "PASS", ""))

    # pr_branch_matches_runner_convention
    if not branch_name.startswith(RUNNER_BRANCH_PREFIX):
        results.append(
            _gate(
                "pr_branch_matches_runner_convention",
                "FAIL",
                f"branch={branch_name}",
            )
        )
        if fail is None:
            fail = "pr_branch_mismatch"
    else:
        results.append(
            _gate("pr_branch_matches_runner_convention", "PASS", "")
        )

    unit_id = _bounded_str(unit.get("id"), 200)
    pr_title = _bounded_str(pr_metadata.get("title"), 480)
    pr_body = _bounded_str(pr_metadata.get("body"), MAX_COMMAND_EXCERPT_LEN)

    # pr_title_contains_unit_id
    if not unit_id or unit_id not in pr_title:
        results.append(
            _gate(
                "pr_title_contains_unit_id",
                "FAIL",
                "unit_id not present in PR title",
            )
        )
        if fail is None:
            fail = "pr_title_missing_unit_id"
    else:
        results.append(_gate("pr_title_contains_unit_id", "PASS", ""))

    # pr_body_contains_runner_signature
    if RUNNER_PR_SIGNATURE not in pr_body:
        results.append(
            _gate(
                "pr_body_contains_runner_signature",
                "FAIL",
                "runner signature not present in PR body",
            )
        )
        if fail is None:
            fail = "pr_body_missing_runner_signature"
    else:
        results.append(_gate("pr_body_contains_runner_signature", "PASS", ""))

    # pr_diff_no_forbidden_path (checked first so that a forbidden
    # path produces the more specific stop reason even when the path
    # is also outside expected_files)
    forbidden_hits = [p for p in pr_diff_paths if _is_forbidden_path(p)]
    if forbidden_hits:
        results.append(
            _gate(
                "pr_diff_no_forbidden_path",
                "FAIL",
                f"forbidden={forbidden_hits[:3]}",
            )
        )
        if fail is None:
            fail = "pr_diff_touches_forbidden_path"
    else:
        results.append(_gate("pr_diff_no_forbidden_path", "PASS", ""))

    # pr_diff_within_expected_files
    expected = {
        _bounded_str(p, 300).replace("\\", "/")
        for p in (unit.get("expected_files") or [])
        if isinstance(p, str)
    }
    extras = [
        p
        for p in pr_diff_paths
        if p not in expected and not _is_forbidden_path(p)
    ]
    if extras:
        results.append(
            _gate(
                "pr_diff_within_expected_files",
                "FAIL",
                f"unexpected={extras[:3]}",
            )
        )
        if fail is None:
            fail = "pr_diff_outside_expected_files"
    else:
        results.append(_gate("pr_diff_within_expected_files", "PASS", ""))

    # ci_status_clean
    if not ci_clean:
        results.append(_gate("ci_status_clean", "FAIL", "ci not green"))
        if fail is None:
            fail = "ci_failed"
    else:
        results.append(_gate("ci_status_clean", "PASS", ""))

    # no_admin_merge_required (checked first so a BLOCKED/BEHIND
    # state produces the more specific stop reason even when
    # mergeability is otherwise dirty)
    if merge_state_status in {"BLOCKED", "BEHIND"}:
        results.append(
            _gate(
                "no_admin_merge_required",
                "FAIL",
                f"merge_state={merge_state_status}",
            )
        )
        if fail is None:
            fail = "branch_protection_requires_admin"
    else:
        results.append(_gate("no_admin_merge_required", "PASS", ""))

    # mergeability_clean
    if mergeability != "MERGEABLE" or merge_state_status not in {
        "CLEAN",
        "BLOCKED",
        "BEHIND",
    }:
        results.append(
            _gate(
                "mergeability_clean",
                "FAIL",
                f"mergeable={mergeability},state={merge_state_status}",
            )
        )
        if fail is None:
            fail = "mergeability_not_clean"
    elif merge_state_status != "CLEAN":
        # BLOCKED/BEHIND already failed above; record this gate as
        # NOT_CHECKED here so the reader can see exactly which gate
        # produced the stop reason.
        results.append(
            _gate(
                "mergeability_clean",
                "NOT_CHECKED",
                "blocked by no_admin_merge_required",
            )
        )
    else:
        results.append(_gate("mergeability_clean", "PASS", ""))

    _ = max_merges  # the per-run cap is enforced pre-execution; here
    # the auto-merge phase runs exactly once per ``run_one`` call by
    # construction, so a runtime cap is not needed.

    return results, fail


def _query_pr_metadata(
    shell: ShellRunner,
    *,
    repo_root: Path,
    pr_number: int,
    commands: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    """Best-effort ``gh pr view`` returning the parsed JSON dict and
    an optional error string."""
    args = [
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--json",
        "title,body,mergeable,mergeStateStatus",
    ]
    res = shell.run(args, cwd=repo_root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        return {}, f"gh_pr_view_exit_code={res.exit_code}"
    try:
        payload = json.loads(res.stdout or "")
    except (TypeError, ValueError) as exc:
        return {}, f"gh_pr_view_parse_error={exc}"
    if not isinstance(payload, dict):
        return {}, "gh_pr_view_payload_not_dict"
    return payload, None


def _query_pr_diff_paths(
    shell: ShellRunner,
    *,
    repo_root: Path,
    pr_number: int,
    commands: list[dict[str, Any]],
) -> tuple[list[str], str | None]:
    """Best-effort ``gh pr diff --name-only`` returning the changed
    paths and an optional error string."""
    args = ["gh", "pr", "diff", str(pr_number), "--name-only"]
    res = shell.run(args, cwd=repo_root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        return [], f"gh_pr_diff_exit_code={res.exit_code}"
    paths: list[str] = []
    for line in (res.stdout or "").splitlines():
        cleaned = line.strip().replace("\\", "/")
        if cleaned and cleaned not in paths:
            paths.append(cleaned)
    return paths, None


def _query_merge_commit_sha(
    shell: ShellRunner,
    *,
    repo_root: Path,
    pr_number: int,
    commands: list[dict[str, Any]],
) -> str:
    args = ["gh", "pr", "view", str(pr_number), "--json", "mergeCommit"]
    res = shell.run(args, cwd=repo_root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        return ""
    try:
        payload = json.loads(res.stdout or "")
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    mc = payload.get("mergeCommit")
    if not isinstance(mc, dict):
        return ""
    oid = mc.get("oid")
    return _bounded_str(oid, MAX_SHA_LEN_FOR_RUN)


def _watch_post_merge_workflow(
    shell: ShellRunner,
    *,
    repo_root: Path,
    workflow_name: str,
    merge_sha: str,
    timeout_seconds: int,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    """Locate the post-merge workflow run for ``merge_sha`` and watch
    it to completion via ``gh run watch --exit-status``. Returns one
    dict shaped for the report's ``post_merge_gates`` list."""
    # First, locate the latest run for this workflow on main.
    args = [
        "gh",
        "run",
        "list",
        "--branch",
        "main",
        "--workflow",
        workflow_name,
        "--limit",
        "10",
        "--json",
        "databaseId,status,conclusion,headSha",
    ]
    res = shell.run(args, cwd=repo_root)
    _record_command(commands, args, res)
    run_id = ""
    conclusion = "unknown"
    if res.exit_code == 0:
        try:
            runs = json.loads(res.stdout or "")
        except (TypeError, ValueError):
            runs = []
        if isinstance(runs, list):
            for entry in runs:
                if not isinstance(entry, dict):
                    continue
                if entry.get("headSha") == merge_sha:
                    db_id = entry.get("databaseId")
                    if isinstance(db_id, int) and db_id > 0:
                        run_id = str(db_id)
                    inline_status = entry.get("status")
                    inline_conclusion = entry.get("conclusion")
                    if (
                        inline_status == "completed"
                        and isinstance(inline_conclusion, str)
                    ):
                        conclusion = inline_conclusion
                    break

    if run_id and conclusion not in {"success", "failure", "cancelled"}:
        # Watch the run to completion.
        watch_args = ["gh", "run", "watch", run_id, "--exit-status"]
        watch_res = shell.run(
            watch_args, cwd=repo_root, timeout=timeout_seconds
        )
        _record_command(commands, watch_args, watch_res)
        if watch_res.exit_code == 0:
            conclusion = "success"
        elif watch_res.exit_code == 124:
            conclusion = "timeout"
        else:
            conclusion = "failure"
    return {
        "workflow_name": workflow_name,
        "run_id": run_id,
        "conclusion": conclusion,
    }


_POST_MERGE_WORKFLOWS: Final[tuple[str, ...]] = (
    "Fast pre-merge gate",
    "Build & Push Docker Image",
    "Deploy VPS Dashboard",
)

_POST_MERGE_WORKFLOW_TO_STOP_REASON: Final[dict[str, str]] = {
    "Fast pre-merge gate": "post_merge_fast_gate_failed",
    "Build & Push Docker Image": "post_merge_docker_build_failed",
    "Deploy VPS Dashboard": "post_merge_deploy_failed",
}


def _auto_merge_phase(
    *,
    report: dict[str, Any],
    shell: ShellRunner,
    unit: dict[str, Any],
    repo_root: Path,
    branch_name: str,
    pr_number: int,
    generated_at_utc: str,
) -> None:
    """Execute the A21d auto-merge phase.

    Mutates ``report`` in place. The caller has already verified CI is
    green and the PR is open.
    """
    commands: list[dict[str, Any]] = report["commands_run"]

    # ---- Query PR metadata and PR diff (defence in depth) -----------------
    pr_md, md_err = _query_pr_metadata(
        shell, repo_root=repo_root, pr_number=pr_number, commands=commands
    )
    if md_err:
        report["final_runner_status"] = "executed_blocked_at_auto_merge"
        report["stop_reason"] = "unknown_evidence"
        report["next_required_operator_action"] = (
            "inspect_gh_pr_view_output"
        )
        return

    pr_diff_paths, diff_err = _query_pr_diff_paths(
        shell, repo_root=repo_root, pr_number=pr_number, commands=commands
    )
    if diff_err:
        report["final_runner_status"] = "executed_blocked_at_auto_merge"
        report["stop_reason"] = "unknown_evidence"
        report["next_required_operator_action"] = (
            "inspect_gh_pr_diff_output"
        )
        return

    # ---- Run auto-merge eligibility gates ---------------------------------
    auto_gates, auto_fail = _evaluate_auto_merge_gates(
        pr_number=pr_number,
        branch_name=branch_name,
        unit=unit,
        pr_metadata=pr_md,
        pr_diff_paths=pr_diff_paths,
        ci_clean=(report.get("ci_status") == "PASS"),
        mergeability=_bounded_str(pr_md.get("mergeable"), 32),
        merge_state_status=_bounded_str(pr_md.get("mergeStateStatus"), 32),
        auto_merge_enabled=bool(report.get("auto_merge_enabled")),
        max_merges=report.get("max_merges_per_run", 0),
    )
    # Append new auto-merge gates to the existing safety_gate_results
    # so the report carries one unified gate list.
    report["safety_gate_results"] = list(
        report.get("safety_gate_results", [])
    ) + auto_gates

    if auto_fail is not None:
        report["final_runner_status"] = "executed_blocked_at_auto_merge"
        report["stop_reason"] = auto_fail
        report["next_required_operator_action"] = (
            "review_auto_merge_gate_failure_then_resolve_manually"
        )
        return

    # ---- Squash-merge (no --admin, no force-push, no hook bypass) ---------
    args = [
        "gh",
        "pr",
        "merge",
        str(pr_number),
        "--squash",
        "--delete-branch",
    ]
    res = shell.run(args, cwd=repo_root)
    _record_command(commands, args, res)
    if res.exit_code != 0:
        report["final_runner_status"] = "executed_blocked_at_auto_merge"
        report["stop_reason"] = "merge_failed"
        report["next_required_operator_action"] = (
            "inspect_gh_pr_merge_output_then_resolve"
        )
        return

    # ---- Update local main ------------------------------------------------
    for git_args in (
        ["git", "checkout", "main"],
        ["git", "pull", "--ff-only"],
    ):
        res = shell.run(git_args, cwd=repo_root)
        _record_command(commands, git_args, res)
        if res.exit_code != 0:
            # We're past the merge; the report still records the merge
            # but the operator must reconcile their local state.
            report["final_runner_status"] = "executed_blocked_at_auto_merge"
            report["stop_reason"] = "unknown_evidence"
            report["next_required_operator_action"] = (
                "reconcile_local_main_then_recheck_post_merge_gates"
            )
            return

    # ---- Capture merge SHA -----------------------------------------------
    merge_sha = _query_merge_commit_sha(
        shell, repo_root=repo_root, pr_number=pr_number, commands=commands
    )
    if not merge_sha:
        report["final_runner_status"] = "executed_blocked_at_auto_merge"
        report["stop_reason"] = "merge_sha_unknown"
        report["next_required_operator_action"] = (
            "manually_capture_merge_sha_then_update_ledger"
        )
        return
    report["pr_merge_sha"] = merge_sha

    # ---- Watch post-merge gates ------------------------------------------
    gate_outcomes: list[dict[str, Any]] = []
    report["post_merge_gates"] = gate_outcomes
    for workflow_name in _POST_MERGE_WORKFLOWS:
        outcome = _watch_post_merge_workflow(
            shell,
            repo_root=repo_root,
            workflow_name=workflow_name,
            merge_sha=merge_sha,
            timeout_seconds=DEFAULT_POST_MERGE_WATCH_TIMEOUT_SECONDS,
            commands=commands,
        )
        gate_outcomes.append(outcome)
        if outcome["conclusion"] == "timeout":
            report["final_runner_status"] = (
                "executed_blocked_at_post_merge_gates"
            )
            report["stop_reason"] = "post_merge_watch_timeout"
            report["next_required_operator_action"] = (
                "inspect_post_merge_workflow_run_manually"
            )
            return
        if outcome["conclusion"] != "success":
            report["final_runner_status"] = (
                "executed_blocked_at_post_merge_gates"
            )
            report["stop_reason"] = (
                _POST_MERGE_WORKFLOW_TO_STOP_REASON.get(
                    workflow_name, "post_merge_fast_gate_failed"
                )
            )
            report["next_required_operator_action"] = (
                "inspect_failing_post_merge_workflow_run"
            )
            return

    # ---- Append evidence-backed merged status to runner_merges ledger ----
    unit_id = _bounded_str(unit.get("id"), 200)
    evidence_entries = [
        f"github_pr_number={pr_number}",
        f"github_merge_sha={merge_sha}",
    ]
    for outcome in gate_outcomes:
        evidence_entries.append(
            f"{_workflow_to_evidence_key(outcome['workflow_name'])}="
            f"{outcome['conclusion']}"
        )
    ledger_record = {
        "unit_id": unit_id,
        "status": "merged",
        "source": "runner_auto_merge",
        "updated_at_utc": generated_at_utc,
        "pr_number": int(pr_number),
        "merge_sha": merge_sha,
        "reason": (
            "auto-merged by A21d runner after CI green + post-merge "
            "gates green"
        ),
        "evidence": evidence_entries,
    }
    try:
        ledger_path = rus.append_runner_merge_record(
            ledger_record,
            repo_root=repo_root,
            generated_at_utc=generated_at_utc,
        )
    except ValueError as exc:
        report["final_runner_status"] = "executed_blocked_at_ledger_update"
        report["stop_reason"] = "status_ledger_write_failed"
        report["next_required_operator_action"] = (
            f"resolve_ledger_write_failure:{_bounded_str(str(exc), 160)}"
        )
        return
    except OSError as exc:
        report["final_runner_status"] = "executed_blocked_at_ledger_update"
        report["stop_reason"] = "status_ledger_write_failed"
        report["next_required_operator_action"] = (
            f"resolve_ledger_write_io_error:{_bounded_str(str(exc), 160)}"
        )
        return
    report["ledger_update_path"] = rus.RUNNER_MERGES_REL_PATH
    _ = ledger_path  # path is informational; relative path recorded above

    # ---- Done -------------------------------------------------------------
    report["final_runner_status"] = "executed_pr_merged"
    report["stop_reason"] = "ok_pr_merged"
    report["next_required_operator_action"] = (
        "review_runner_merges_artifact_or_continue_next_run"
    )


def _workflow_to_evidence_key(workflow_name: str) -> str:
    """Map a workflow display name to a stable underscored evidence
    key (e.g. 'Fast pre-merge gate' -> 'fast_pre_merge_gate')."""
    cleaned = workflow_name.lower().replace("&", "and").replace("-", " ")
    out_chars: list[str] = []
    last_was_alnum = False
    for ch in cleaned:
        if ch.isalnum():
            out_chars.append(ch)
            last_was_alnum = True
        else:
            if last_was_alnum:
                out_chars.append("_")
            last_was_alnum = False
    key = "".join(out_chars).strip("_")
    return key or "unknown_workflow"


# ---------------------------------------------------------------------------
# A21e continuous autonomous conveyor
# ---------------------------------------------------------------------------


def _refresh_status_artifact(
    *, root: Path, generated_at_utc: str
) -> str | None:
    """Refresh ``logs/roadmap_unit_status/latest.json`` so the next
    selector pass sees the latest A21d runner-merges overlay.

    Returns ``None`` on success or a closed-vocab error tag on
    failure. The conveyor stops with
    ``conveyor_status_artifact_refresh_failed`` if this fails — the
    selector's view of merged units would otherwise lag behind disk
    state and could repeat already-merged units.
    """
    try:
        snap = rus.collect_snapshot(
            repo_root=root, generated_at_utc=generated_at_utc
        )
    except Exception as exc:  # defensive
        return _bounded_str(repr(exc), MAX_DETAIL_LEN)
    target = root / "logs" / "roadmap_unit_status" / "latest.json"
    try:
        rus._atomic_write_json(target, snap)
    except (ValueError, OSError) as exc:
        return _bounded_str(repr(exc), MAX_DETAIL_LEN)
    return None


def _empty_conveyor_report(
    *,
    ts: str,
    started_at: str,
    auto_merge_enabled: bool,
    stop_after_current_requested: bool,
    implementation_strategy: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": CONVEYOR_REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "run_continuous",
        "started_at_utc": started_at,
        "ended_at_utc": "",
        "auto_merge_enabled": bool(auto_merge_enabled),
        "stop_after_current_requested": bool(stop_after_current_requested),
        "implementation_strategy": implementation_strategy,
        "units_attempted": 0,
        "units_pr_opened": 0,
        "units_merged": 0,
        "units_blocked": 0,
        "unit_ids_processed": [],
        "pr_numbers_opened": [],
        "merge_shas": [],
        "post_merge_gates_by_iteration": [],
        "selector_results_by_iteration": [],
        "iteration_summaries": [],
        "final_iteration_full_report": {},
        "final_stop_reason": "",
        "final_selector_status": "",
        "final_runner_status": "not_run",
        "next_required_operator_action": "",
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "runner_invariants": dict(_BASE_RUNNER_INVARIANTS),
    }


def _selector_iteration_record(
    *,
    iteration: int,
    sel: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "selection_status": _bounded_str(sel.get("selection_status"), 64),
        "selected_unit_id": _bounded_str(sel.get("selected_unit_id"), 200),
        "selected_authority_class": _bounded_str(
            sel.get("selected_authority_class"), 32
        ),
        "selected_risk_class": _bounded_str(
            sel.get("selected_risk_class"), 16
        ),
        "selected_operator_gate": _bounded_str(
            sel.get("selected_operator_gate"), 64
        ),
        "requires_operator_go": bool(sel.get("requires_operator_go")),
        "candidate_count": int(sel.get("candidate_count") or 0),
        "eligible_candidate_count": int(
            sel.get("eligible_candidate_count") or 0
        ),
    }


def _iteration_summary_from_iter_report(
    *, iteration: int, ts: str, iter_report: dict[str, Any]
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "started_at_utc": ts,
        "selected_unit_id": _bounded_str(
            iter_report.get("selected_unit_id"), 200
        ),
        "selected_phase": _bounded_str(
            iter_report.get("selected_phase"), 64
        ),
        "branch_name": _bounded_str(
            iter_report.get("branch_name"), MAX_BRANCH_NAME_LEN
        ),
        "pr_number": int(iter_report.get("pr_number", 0) or 0),
        "pr_merge_sha": _bounded_str(
            iter_report.get("pr_merge_sha"), MAX_SHA_LEN_FOR_RUN
        ),
        "ci_status": _bounded_str(iter_report.get("ci_status"), 32),
        "stop_reason": _bounded_str(iter_report.get("stop_reason"), 80),
        "final_runner_status": _bounded_str(
            iter_report.get("final_runner_status"), 64
        ),
        "post_merge_gates": list(iter_report.get("post_merge_gates") or []),
    }


def _next_action_for_stop(stop_reason: str) -> str:
    if stop_reason == "ok_conveyor_completed_no_eligible_unit":
        return "review_conveyor_report_then_decide_next_phase_decomposition"
    if stop_reason == "conveyor_operator_stop_after_current":
        return "review_completed_units_then_resume_with_run_continuous"
    if stop_reason == "conveyor_operator_stop_signal_file":
        return (
            "review_completed_units_then_remove_signal_file_then_resume"
        )
    if stop_reason == "conveyor_requires_auto_merge":
        return (
            "rerun_with_auto_merge_runner_pr_or_use_run_one_instead"
        )
    if stop_reason in {
        "conveyor_selector_repeated_merged_unit",
        "conveyor_selector_repeated_unit_without_status_change",
        "conveyor_status_artifact_refresh_failed",
        "conveyor_selector_unavailable",
    }:
        return (
            "inspect_selector_and_status_artifact_state_then_resolve"
        )
    return "review_final_iteration_report_then_resolve_before_resuming"


def run_continuous(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
    implementation_strategy_name: str = "none",
    external_command: str | None = None,
    external_command_timeout: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    auto_merge_runner_pr: bool = False,
    stop_after_current: bool = False,
    clock_fn: Callable[[], str] | None = None,
    shell: ShellRunner | None = None,
    implementation_strategy: ImplementationStrategy | None = None,
) -> dict[str, Any]:
    """A21e continuous autonomous conveyor.

    Repeatedly calls :func:`run_one` (with ``auto_merge_runner_pr``
    propagated) until one of these stops fires:

    * the selector returns ``selection_status != OK_SELECTED``
      (no eligible unit, upstream missing, ambiguous selection,
      etc.);
    * a per-iteration ``run_one`` reports anything other than
      ``ok_pr_merged`` (every A21c / A21d safety + technical stop
      is propagated);
    * the selector re-selects an already-merged unit
      (``conveyor_selector_repeated_merged_unit``);
    * the selector re-selects the same unit twice without the unit
      transitioning to merged in between
      (``conveyor_selector_repeated_unit_without_status_change``);
    * the operator's ``--stop-after-current`` flag was passed or
      the soft-stop sentinel file exists;
    * the between-iteration status-artefact refresh fails
      (``conveyor_status_artifact_refresh_failed``).

    No artificial unit-count or wall-clock cap.

    The conveyor *requires* ``auto_merge_runner_pr = True`` because
    without auto-merge the selected unit's status never flips to
    merged, the selector would re-select the same unit, and the
    same-unit-without-status-change guard would trip on iteration
    2. To keep semantics clean, the conveyor refuses to start
    without auto-merge enabled.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    tick = clock_fn if clock_fn is not None else _utcnow
    started_at = generated_at_utc if generated_at_utc is not None else tick()

    report = _empty_conveyor_report(
        ts=started_at,
        started_at=started_at,
        auto_merge_enabled=bool(auto_merge_runner_pr),
        stop_after_current_requested=bool(stop_after_current),
        implementation_strategy=implementation_strategy_name,
    )

    # ---- Pre-flight: auto-merge required for the conveyor -----------------
    if not auto_merge_runner_pr:
        report["final_stop_reason"] = "conveyor_requires_auto_merge"
        report["final_runner_status"] = "executed_conveyor_refused_unsafe"
        report["ended_at_utc"] = tick()
        report["next_required_operator_action"] = _next_action_for_stop(
            "conveyor_requires_auto_merge"
        )
        return report

    iteration = 0
    units_merged: set[str] = set()
    last_unit_id: str = ""
    last_iteration_was_merge: bool = False
    final_iteration_full_report: dict[str, Any] = {}
    stop_signal_path = root / CONVEYOR_STOP_SIGNAL_REL_PATH

    while True:
        iteration += 1

        # ---- Operator soft-stop sentinel check (per-iteration) -----------
        per_iter_stop_after_current = bool(stop_after_current)
        if not per_iter_stop_after_current and stop_signal_path.is_file():
            per_iter_stop_after_current = True

        # ---- Re-run selector ---------------------------------------------
        snap, _err = _load_selector_snapshot(repo_root=root)
        if snap is None:
            report["selector_results_by_iteration"].append(
                _selector_iteration_record(iteration=iteration, sel={})
            )
            report["final_stop_reason"] = "conveyor_selector_unavailable"
            report["final_runner_status"] = (
                "executed_conveyor_stopped_technical"
            )
            break

        sel = snap.get("selection") or {}
        sel_status = _bounded_str(sel.get("selection_status"), 64)
        sel_unit_id = _bounded_str(sel.get("selected_unit_id"), 200)
        report["selector_results_by_iteration"].append(
            _selector_iteration_record(iteration=iteration, sel=sel)
        )
        report["final_selector_status"] = sel_status

        # ---- Per-selector-status routing ---------------------------------
        # OK_SELECTED proceeds to run_one. ALL_NEEDS_HUMAN_GATED also
        # proceeds (defence in depth — run_one's per-authority gate will
        # fire the specific stop reason). The clean-completion statuses
        # (NO_ELIGIBLE_UNITS / ALL_PERMANENTLY_DENIED /
        # ALL_BLOCKED_BY_PREREQUISITES) end the conveyor cleanly. Other
        # statuses are technical stops.
        if sel_status not in {"OK_SELECTED", "ALL_NEEDS_HUMAN_GATED"}:
            if sel_status in {
                "NO_ELIGIBLE_UNITS",
                "ALL_PERMANENTLY_DENIED",
                "ALL_BLOCKED_BY_PREREQUISITES",
            }:
                report["final_stop_reason"] = (
                    "ok_conveyor_completed_no_eligible_unit"
                )
                report["final_runner_status"] = (
                    "executed_conveyor_completed_no_eligible"
                )
            elif sel_status == "UPSTREAM_UNAVAILABLE":
                report["final_stop_reason"] = (
                    "conveyor_selector_unavailable"
                )
                report["final_runner_status"] = (
                    "executed_conveyor_stopped_technical"
                )
            else:
                # FAIL_CLOSED_INVARIANT, empty, unknown, etc.
                report["final_stop_reason"] = "ambiguous_selection"
                report["final_runner_status"] = (
                    "executed_conveyor_stopped_technical"
                )
            break

        # ---- Stop: selector re-selected an already-merged unit -----------
        if sel_unit_id in units_merged:
            report["final_stop_reason"] = (
                "conveyor_selector_repeated_merged_unit"
            )
            report["final_runner_status"] = (
                "executed_conveyor_stopped_technical"
            )
            break

        # ---- Stop: same unit twice without status change ------------------
        if sel_unit_id == last_unit_id and not last_iteration_was_merge:
            report["final_stop_reason"] = (
                "conveyor_selector_repeated_unit_without_status_change"
            )
            report["final_runner_status"] = (
                "executed_conveyor_stopped_technical"
            )
            break

        # ---- Run one iteration via run_one (with auto-merge) -------------
        iter_ts = tick()
        iter_report = run_one(
            repo_root=root,
            generated_at_utc=iter_ts,
            max_units=MAX_UNITS_PER_RUN_HARD_CAP,
            max_merges=MAX_MERGES_PER_RUN_HARD_CAP,
            implementation_strategy_name=implementation_strategy_name,
            external_command=external_command,
            external_command_timeout=external_command_timeout,
            auto_merge_runner_pr=True,
            shell=shell,
            implementation_strategy=implementation_strategy,
        )
        final_iteration_full_report = iter_report
        report["units_attempted"] += 1
        report["iteration_summaries"].append(
            _iteration_summary_from_iter_report(
                iteration=iteration, ts=iter_ts, iter_report=iter_report
            )
        )
        if iter_report.get("selected_unit_id"):
            report["unit_ids_processed"].append(
                iter_report["selected_unit_id"]
            )
        if int(iter_report.get("pr_number", 0) or 0) > 0:
            report["pr_numbers_opened"].append(
                int(iter_report["pr_number"])
            )
        if iter_report.get("pr_merge_sha"):
            report["merge_shas"].append(iter_report["pr_merge_sha"])
        report["post_merge_gates_by_iteration"].append(
            list(iter_report.get("post_merge_gates") or [])
        )

        iter_stop = _bounded_str(iter_report.get("stop_reason"), 80)
        last_unit_id = sel_unit_id
        last_iteration_was_merge = iter_stop == "ok_pr_merged"

        if last_iteration_was_merge:
            units_merged.add(sel_unit_id)
            report["units_merged"] += 1
            report["units_pr_opened"] += 1

            # Operator soft-stop after this successful merge.
            if per_iter_stop_after_current:
                if stop_signal_path.is_file():
                    report["final_stop_reason"] = (
                        "conveyor_operator_stop_signal_file"
                    )
                else:
                    report["final_stop_reason"] = (
                        "conveyor_operator_stop_after_current"
                    )
                report["final_runner_status"] = (
                    "executed_conveyor_stopped_operator"
                )
                break

            # Refresh the status artefact so the next selector pass
            # sees the freshly merged unit. The runner_merges record
            # has already been appended by run_one's auto-merge phase.
            refresh_err = _refresh_status_artifact(
                root=root, generated_at_utc=iter_ts
            )
            if refresh_err is not None:
                report["final_stop_reason"] = (
                    "conveyor_status_artifact_refresh_failed"
                )
                report["final_runner_status"] = (
                    "executed_conveyor_stopped_technical"
                )
                break

            # Continue to the next iteration.
            continue

        # ---- Iteration stopped on a non-merge reason ----------------------
        if iter_stop in {"ok_pr_opened_no_auto_merge", "ok_pr_opened"}:
            # Conveyor required auto-merge but the iteration didn't
            # produce a merge. This shouldn't normally fire because we
            # forced auto_merge_runner_pr=True above; defence in depth.
            report["units_pr_opened"] += 1
            report["units_blocked"] += 1
            report["final_stop_reason"] = "conveyor_requires_auto_merge"
            report["final_runner_status"] = (
                "executed_conveyor_refused_unsafe"
            )
            break

        report["units_blocked"] += 1
        report["final_stop_reason"] = iter_stop or "unknown_evidence"
        final_status = _bounded_str(
            iter_report.get("final_runner_status"), 64
        )
        # Map the per-iteration stop to a conveyor-level final status.
        safety_stops = {
            "unsafe_authority_class",
            "unsafe_risk_class",
            "unsafe_operator_gate",
            "requires_operator_go",
            "missing_expected_files",
            "missing_forbidden_files",
            "missing_required_tests",
            "forbidden_path_in_expected_files",
            "terminal_status",
            "max_units_exceeded",
            "max_merges_exceeded",
            "implementation_strategy_not_configured",
            "implementation_strategy_failed",
            "diff_outside_expected_files",
            "diff_touches_forbidden_path",
            "diff_empty",
            "pr_diff_outside_expected_files",
            "pr_diff_touches_forbidden_path",
            "not_runner_originated",
            "pr_branch_mismatch",
            "pr_title_missing_unit_id",
            "pr_body_missing_runner_signature",
            "auto_merge_disabled",
            "branch_protection_requires_admin",
            # Code/CI/lint failures on the implementation itself are
            # safety stops: they indicate the produced change is not
            # safe to merge.
            "tests_failed",
            "governance_lint_failed",
            "mergeability_not_clean",
        }
        if iter_stop in safety_stops:
            report["final_runner_status"] = (
                "executed_conveyor_stopped_safety"
            )
        else:
            report["final_runner_status"] = (
                "executed_conveyor_stopped_technical"
            )
        _ = final_status  # informational
        break

    # ---- Finalise report -----------------------------------------------
    report["ended_at_utc"] = tick()
    if final_iteration_full_report:
        report["final_iteration_full_report"] = final_iteration_full_report
    report["next_required_operator_action"] = _next_action_for_stop(
        report["final_stop_reason"]
    )
    return report


# ---------------------------------------------------------------------------
# PR body / commit message helpers
# ---------------------------------------------------------------------------


def _commit_message_for_unit(unit: dict[str, Any]) -> str:
    uid = _bounded_str(unit.get("id"), 200)
    title = _bounded_str(unit.get("title"), 200)
    return (
        f"feat({uid}): {title}\n"
        "\n"
        "Auto-prepared by reporting.autonomous_pr_runner (A21c "
        "bounded slice).\n"
        "\n"
        "No auto-merge; no deploy; no runtime authority granted."
    )


def _pr_title_for_unit(unit: dict[str, Any]) -> str:
    uid = _bounded_str(unit.get("id"), 200)
    title = _bounded_str(unit.get("title"), 200)
    return f"feat({uid}): {title}"


def _pr_body_for_unit(unit: dict[str, Any], branch_name: str) -> str:
    uid = _bounded_str(unit.get("id"), 200)
    title = _bounded_str(unit.get("title"), 200)
    expected = unit.get("expected_files") or []
    expected_lines = "\n".join(
        f"- `{p}`" for p in expected if isinstance(p, str)
    ) or "- (none)"
    required = unit.get("required_tests") or []
    required_lines = "\n".join(
        f"- `{t}`" for t in required if isinstance(t, str)
    ) or "- (none)"
    return (
        f"## Summary\n\n"
        f"Auto-prepared by `reporting.autonomous_pr_runner` (A21c "
        f"bounded slice) on branch `{branch_name}`.\n\n"
        f"- **Selected A20e unit id:** `{uid}`\n"
        f"- **Title:** {title}\n"
        f"- **Authority class:** `AUTO_ALLOWED` (LOW risk, "
        f"`operator_gate = none`).\n"
        f"- **No auto-merge.** Operator decides squash-merge after CI.\n"
        f"- **No deploy.** Deploy gates run only after operator-driven "
        f"merge to `main`.\n"
        f"- **No runtime / trading / paper / shadow / live authority "
        f"granted.**\n\n"
        f"## Expected files\n\n{expected_lines}\n\n"
        f"## Required tests\n\n{required_lines}\n\n"
        f"## Authority posture\n\n"
        f"- Step 5 broad implementation remains BLOCKED.\n"
        f"- Autonomy-ladder Level 6 remains permanently disabled.\n"
        f"- N5b Phase 4 production merge remains permanently denied "
        f"for ADE.\n"
        f"- ADE remains development workflow automation only.\n"
    )


def _parse_pr_number(stdout: str) -> int:
    """Extract a PR number from a typical `gh pr create` stdout
    line such as ``https://github.com/owner/repo/pull/256``."""
    if not isinstance(stdout, str):
        return 0
    for token in stdout.split():
        if "/pull/" in token:
            tail = token.rsplit("/pull/", 1)[1]
            digits = "".join(ch for ch in tail if ch.isdigit())
            if digits:
                try:
                    return int(digits)
                except ValueError:
                    return 0
    return 0


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "autonomous_pr_runner._atomic_write_json refuses "
            f"non-runner-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".autonomous_pr_runner.",
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


def write_outputs(report: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, report)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(report: dict[str, Any]) -> str:
    inv = report["runner_invariants"]
    gates = report["safety_gate_results"]
    lines = [
        f"autonomous_pr_runner {report['module_version']} "
        f"schema={report['schema_version']}",
        f"generated_at_utc={report['generated_at_utc']}",
        f"mode={report['mode']}",
        f"selected_unit_id={report['selected_unit_id']}",
        f"selected_phase={report['selected_phase']}",
        f"authority={report['selected_authority_class']} "
        f"risk={report['selected_risk_class']} "
        f"gate={report['selected_operator_gate']}",
        f"implementation_strategy={report['implementation_strategy']}",
        f"max_units_per_run={report['max_units_per_run']}",
        f"final_runner_status={report['final_runner_status']}",
        f"stop_reason={report['stop_reason']}",
        f"next_required_operator_action="
        f"{report['next_required_operator_action']}",
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_broad={inv['no_step5_broad']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "no_auto_merge_outside_bounded_a21d_slice="
            f"{inv['no_auto_merge_outside_bounded_a21d_slice']} "
            f"no_admin_merge={inv['no_admin_merge']} "
            f"no_force_push={inv['no_force_push']} "
            f"no_hook_bypass={inv['no_hook_bypass']} "
            f"no_deploy_invocation={inv['no_deploy_invocation']}"
        ),
        (
            "no_a21a_seed_mutation="
            f"{inv['no_a21a_seed_mutation']} "
            "no_second_unit_continuation="
            f"{inv['no_second_unit_continuation']} "
            "bounded_step5_pr_creation_only="
            f"{inv['bounded_step5_pr_creation_only']} "
            "bounded_step5_auto_merge_only_for_runner_pr="
            f"{inv['bounded_step5_auto_merge_only_for_runner_pr']}"
        ),
    ]
    for g in gates:
        lines.append(
            f"  gate {g['gate']}={g['result']}"
            + (f" ({g['detail']})" if g["detail"] else "")
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.autonomous_pr_runner",
        description=(
            "A21c Bounded Autonomous PR Runner. Takes ONE A20e-"
            "selected unit and opens a real PR. Does NOT auto-merge, "
            "does NOT deploy, does NOT continue to another unit. "
            "Step 5 broad implementation remains BLOCKED."
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
            "Do not persist logs/autonomous_pr_runner/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to "
            "stdout and exit. Does not execute anything."
        ),
    )
    p.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Evaluate every safety gate against the current "
            "selector recommendation but do not execute anything."
        ),
    )
    p.add_argument(
        "--run-one",
        action="store_true",
        help=(
            "Execute exactly one bounded PR creation cycle. Must "
            "be combined with --implementation-strategy != none."
        ),
    )
    p.add_argument(
        "--run-continuous",
        action="store_true",
        help=(
            "A21e continuous conveyor mode. Repeats the A21d "
            "PR-create + CI watch + auto-merge cycle on every "
            "A20e-selected unit until no eligible unit remains, a "
            "safety / technical stop fires, or the operator sends "
            "an explicit stop (--stop-after-current or sentinel "
            "file). REQUIRES --auto-merge-runner-pr. No artificial "
            "unit-count or wall-clock budget."
        ),
    )
    p.add_argument(
        "--stop-after-current",
        action="store_true",
        help=(
            "Soft-stop for the continuous conveyor. Complete the "
            "currently-running iteration (if any) and stop before "
            "selecting another unit. The same effect can be "
            "achieved at runtime by creating the sentinel file at "
            "logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal."
        ),
    )
    p.add_argument(
        "--max-units",
        type=int,
        default=1,
        help=(
            "Maximum units per run. A21c hard-caps this at 1; any "
            "other value is rejected by the safety gates."
        ),
    )
    p.add_argument(
        "--implementation-strategy",
        choices=list(IMPLEMENTATION_STRATEGY),
        default="none",
        help=(
            "Implementation strategy. Default 'none' refuses to "
            "execute."
        ),
    )
    p.add_argument(
        "--implementation-command",
        default="",
        help=(
            "Operator-supplied implementation command for the "
            "external_command strategy."
        ),
    )
    p.add_argument(
        "--implementation-timeout",
        type=int,
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        help=(
            "Timeout (seconds) for the implementation command "
            "(external_command strategy only)."
        ),
    )
    p.add_argument(
        "--auto-merge-runner-pr",
        action="store_true",
        help=(
            "Opt in to the A21d auto-merge phase. After CI is green "
            "on the freshly-created PR, squash-merge without admin "
            "override, without force, without hook bypass, capture "
            "merge SHA, update local main, watch post-merge gates, "
            "and append an evidence-backed merged record to "
            "logs/roadmap_unit_status/runner_merges.json. Refused "
            "for any PR not opened in the same run-one invocation."
        ),
    )
    p.add_argument(
        "--max-merges",
        type=int,
        default=MAX_MERGES_PER_RUN_HARD_CAP,
        help=(
            "Maximum merges per run. A21d hard-caps this at 1; any "
            "other value is rejected by the safety gates."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.status:
        report = status(
            max_units=args.max_units,
            max_merges=args.max_merges,
            auto_merge_enabled=bool(args.auto_merge_runner_pr),
            implementation_strategy=args.implementation_strategy,
        )
        sys.stdout.write(_render_status(report))
        return 0

    if args.plan_only:
        report = plan(
            max_units=args.max_units,
            max_merges=args.max_merges,
            auto_merge_enabled=bool(args.auto_merge_runner_pr),
            implementation_strategy=args.implementation_strategy,
        )
        indent = args.indent if args.indent and args.indent > 0 else None
        if not args.no_write:
            write_outputs(report)
        json.dump(report, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if args.run_continuous:
        report = run_continuous(
            implementation_strategy_name=args.implementation_strategy,
            external_command=args.implementation_command,
            external_command_timeout=args.implementation_timeout,
            auto_merge_runner_pr=bool(args.auto_merge_runner_pr),
            stop_after_current=bool(args.stop_after_current),
        )
        indent = args.indent if args.indent and args.indent > 0 else None
        if not args.no_write:
            write_outputs(report)
        json.dump(report, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        ok_reasons = {
            "ok_conveyor_completed_no_eligible_unit",
            "conveyor_operator_stop_after_current",
            "conveyor_operator_stop_signal_file",
        }
        return 0 if report["final_stop_reason"] in ok_reasons else 1

    if args.run_one:
        report = run_one(
            max_units=args.max_units,
            max_merges=args.max_merges,
            implementation_strategy_name=args.implementation_strategy,
            external_command=args.implementation_command,
            external_command_timeout=args.implementation_timeout,
            auto_merge_runner_pr=bool(args.auto_merge_runner_pr),
        )
        indent = args.indent if args.indent and args.indent > 0 else None
        if not args.no_write:
            write_outputs(report)
        json.dump(report, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        ok_reasons = {"ok_pr_opened", "ok_pr_opened_no_auto_merge", "ok_pr_merged"}
        return 0 if report["stop_reason"] in ok_reasons else 1

    # No explicit mode flag. Default to status-only (safe).
    report = status(
        max_units=args.max_units,
        max_merges=args.max_merges,
        auto_merge_enabled=bool(args.auto_merge_runner_pr),
        implementation_strategy=args.implementation_strategy,
    )
    sys.stdout.write(_render_status(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
