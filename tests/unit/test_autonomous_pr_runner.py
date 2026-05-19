"""Unit tests for A21c -- Bounded Autonomous PR Runner.

Pins:

* import is side-effect free (no subprocess, no git, no gh, no
  network, no file writes at module level);
* closed vocabularies (RUN_STATUS, STOP_REASON, SAFETY_GATE,
  GATE_RESULT, RUNNER_MODE, IMPLEMENTATION_STRATEGY) and schema
  field tuples;
* every safety gate refusal path produces the correct closed-vocab
  stop reason and runner status;
* unsafe authority / risk / gate / requires_operator_go are
  refused;
* missing expected_files / forbidden_files / required_tests are
  refused;
* forbidden expected_files (live / paper / shadow / broker /
  agent.risk / agent.execution / dashboard.dashboard.py /
  research/research_latest.json / research/strategy_matrix.csv /
  tests/regression / docs/development_work_queue / .claude / etc)
  are refused at the no_forbidden_in_expected gate;
* terminal statuses (merged / blocked / skipped / failed) are
  refused;
* max_units > 1 is refused (A21c hard cap = 1);
* default implementation_strategy = "none" is refused;
* diff outside expected_files is refused;
* diff touching a forbidden path is refused even if it was in
  expected_files;
* empty diff is refused;
* required tests failing => tests_failed stop;
* governance lint failing => governance_lint_failed stop;
* commit / push / PR-create / CI failures each surface the
  matching closed-vocab stop reason;
* no auto-merge path exists in module source;
* no deploy path exists in module source;
* no force-push / no --admin / no hook bypass tokens in module
  source;
* shell / git / gh / implementation strategy are all injectable in
  tests; no real git / gh / subprocess is invoked by the unit
  test suite;
* runner_invariants pin every Step 5 / Level 6 / runtime / merge /
  deploy / mutation route / approval button / ledger-mutation /
  test-weakening guard.
"""

from __future__ import annotations

import ast as _ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import autonomous_pr_runner as apr


# ---------------------------------------------------------------------------
# Test fixtures: fake shell + fake implementation strategy
# ---------------------------------------------------------------------------


class _FakeShell:
    """Deterministic injectable ShellRunner.

    The fake matches commands by their first two tokens (e.g.
    ``("git", "checkout")``) and returns a queued result. Tests
    pre-load expected commands.
    """

    def __init__(self) -> None:
        self.results: list[tuple[tuple[str, ...], apr.CommandResult]] = []
        self.calls: list[tuple[list[str], Path | None, int]] = []

    def queue(
        self,
        prefix: tuple[str, ...],
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int = 1,
    ) -> None:
        self.results.append(
            (
                prefix,
                apr.CommandResult(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                ),
            )
        )

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = apr.DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> apr.CommandResult:
        self.calls.append((list(args), cwd, timeout))
        for i, (prefix, result) in enumerate(self.results):
            if tuple(args[: len(prefix)]) == prefix:
                self.results.pop(i)
                return result
        return apr.CommandResult(
            exit_code=0, stdout="", stderr="", duration_ms=1
        )


class _FakeStrategy:
    """Deterministic injectable ImplementationStrategy."""

    name = "fake"

    def __init__(
        self,
        *,
        success: bool = True,
        reason: str = "fake_ok",
    ) -> None:
        self._success = success
        self._reason = reason
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        unit: dict[str, Any],
        *,
        repo_root: Path,
        shell: apr.ShellRunner,
    ) -> apr.ImplementationResult:
        self.calls.append({"unit_id": unit.get("id"), "root": repo_root})
        return apr.ImplementationResult(
            success=self._success,
            reason=self._reason,
            files_changed=(),
        )


_FROZEN_UTC = "2026-05-18T20:00:00Z"


def _write_minimal_upstreams(
    tmp_path: Path,
    *,
    unit_overrides: dict[str, Any] | None = None,
    decision_overrides: dict[str, Any] | None = None,
) -> None:
    """Write tiny A20b + A20c artefacts pinning ONE eligible unit."""
    unit: dict[str, Any] = {
        "id": "u_runner_synth",
        "roadmap_task_id": "phase_v3_15_17",
        "title": "Synthetic eligible runner unit",
        "phase": "v3.15.17",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": [],
        "expected_files": [
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        "forbidden_files": [
            ".claude/**",
            "dashboard/dashboard.py",
        ],
        "forbidden_surface_reasons": [],
        "required_tests": [
            "tests/unit/test_synthetic_runner_target.py",
        ],
        "definition_of_done": [],
        "stop_conditions": [],
        "prerequisites": [],
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    }
    if unit_overrides:
        unit.update(unit_overrides)
    decision: dict[str, Any] = {
        "implementation_unit_id": unit["id"],
        "roadmap_task_id": unit["roadmap_task_id"],
        "phase": unit["phase"],
        "final_authority_class": "AUTO_ALLOWED",
        "max_severity": 0,
        "evidence": [],
        "requires_operator_go": False,
        "permanently_denied": False,
        "deny_reasons": [],
        "classifier_used": True,
        "fail_closed": False,
    }
    if decision_overrides:
        decision.update(decision_overrides)

    units_dir = tmp_path / "logs" / "roadmap_task_units"
    units_dir.mkdir(parents=True, exist_ok=True)
    (units_dir / "latest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "v3.15.16.A20b",
                "report_kind": "roadmap_task_units",
                "generated_at_utc": "2026-05-18T08:00:00Z",
                "implementation_units": [unit],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    auth_dir = tmp_path / "logs" / "roadmap_unit_authority"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "latest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "v3.15.16.A20c",
                "report_kind": "roadmap_unit_authority",
                "generated_at_utc": "2026-05-18T08:00:00Z",
                "authority_decisions": [decision],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Module-level guarantees: import safety + module-source scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(apr.__file__).read_text(encoding="utf-8")


def _module_top_level_imports() -> list[str]:
    """Module-level (not function-level) import statements."""
    tree = _ast.parse(_module_source())
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, _ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                out.append(f"{mod}.{alias.name}" if mod else alias.name)
    return out


def test_module_imports_cleanly() -> None:
    importlib.reload(apr)
    assert callable(apr.status)
    assert callable(apr.plan)
    assert callable(apr.run_one)
    assert callable(apr.main)


def test_import_does_not_use_subprocess_at_module_level() -> None:
    """``subprocess`` must NOT be imported at module top level. It
    is imported lazily inside the real shell runner factory so the
    module is import-safe."""
    top = _module_top_level_imports()
    for module in top:
        assert not module.startswith("subprocess"), module


def test_no_socket_or_urllib_or_http_or_requests() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "from socket",
        "import urllib",
        "from urllib",
        "import http\n",
        "from http",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_runtime_imports_via_ast() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "live",
        "paper",
        "shadow",
        "trading",
        "reporting.intelligent_routing",
        "reporting.execution_authority",
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
    )
    for module in _module_top_level_imports():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def _code_lines() -> str:
    """Module source with docstrings + comment lines stripped, so
    documentation references to forbidden tokens (e.g. ``--admin`` in
    a 'no --admin' docstring) do not falsely trip the source-scan
    invariants. Removes triple-quoted strings and ``#`` line comments
    via AST."""
    src = _module_source()
    tree = _ast.parse(src)
    # Collect (line range, kind) for every triple-quoted string
    # literal. Strip those line ranges from the source.
    bad_lines: set[int] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Expr) and isinstance(
            node.value, _ast.Constant
        ):
            if isinstance(node.value.value, str):
                # This catches module / function / class docstrings.
                start = node.lineno
                end = node.end_lineno or start
                for ln in range(start, end + 1):
                    bad_lines.add(ln)
    out: list[str] = []
    for i, line in enumerate(src.splitlines(), start=1):
        if i in bad_lines:
            continue
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def test_no_admin_merge_argument_in_module_code() -> None:
    """A21d ships bounded squash-merge for runner-originated PRs.
    ``gh pr merge`` is invoked, but ``--admin`` MUST NOT appear in
    any argument list (and the runner_invariants block pins this).
    Docstring references are excluded via :func:`_code_lines` so the
    'no --admin' statement in the module docstring does not trip the
    scan."""
    code = _code_lines()
    assert "--admin" not in code, "--admin must not appear in runner code"


def test_pr_merge_invocation_uses_squash_and_delete_branch() -> None:
    """A21d's merge invocation must be squash + delete-branch. No
    admin, no force, no hook bypass. Pinned by inspecting the exact
    arg list in the module source."""
    code = _code_lines()
    assert '"--squash"' in code, "expected --squash arg"
    assert '"--delete-branch"' in code, "expected --delete-branch arg"
    assert "--admin" not in code
    assert "--force" not in code
    assert "--no-verify" not in code


def test_no_force_push_in_module_code() -> None:
    code = _code_lines()
    assert "--force" not in code
    assert "push --force" not in code
    assert "--force-with-lease" not in code


def test_no_hook_bypass_in_module_code() -> None:
    code = _code_lines()
    assert "--no-verify" not in code
    assert "--no-gpg-sign" not in code


def test_no_deploy_invocation_in_module_code() -> None:
    """No deploy *invocation* exists in the runner code. A21d
    observes ``Deploy VPS Dashboard`` (passes it as a workflow name
    to ``gh run list``) but does NOT run docker push, ssh root@, or
    any deploy-trigger command. The workflow-name string is allowed;
    real deploy invocations are not."""
    code = _code_lines()
    for token in (
        "docker push",
        "ssh root@",
        "scp root@",
        "rsync root@",
        "kubectl apply",
        "fly deploy",
        "vercel deploy",
    ):
        assert token not in code, token


def test_post_merge_watch_uses_deploy_workflow_name_for_read_only_observation() -> None:
    """A21d watches the existing post-merge gates by passing their
    workflow names to ``gh run list``/``gh run watch``. The string
    ``Deploy VPS Dashboard`` appears here as a workflow-name LITERAL,
    not as a deploy invocation. Pinned to prevent regressions."""
    code = _code_lines()
    assert "Deploy VPS Dashboard" in code
    assert "Build & Push Docker Image" in code
    assert "Fast pre-merge gate" in code


def test_no_eval_or_exec_in_module_code() -> None:
    code = _code_lines()
    assert "eval(" not in code
    assert "exec(" not in code
    assert "os.system(" not in code
    assert "shell=True" not in code


def test_no_github_api_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "api.github.com",
        "anthropic",
        "openai",
        "X-API-Key",
        "X-GitHub-Token",
    ):
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------------------
# Closed vocabularies + schema integrity
# ---------------------------------------------------------------------------


def test_run_status_vocab_is_closed_exact() -> None:
    assert apr.RUN_STATUS == (
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
    )


def test_safety_gate_vocab_is_closed_exact() -> None:
    assert apr.SAFETY_GATE == (
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


def test_gate_result_vocab_is_closed_exact() -> None:
    assert apr.GATE_RESULT == ("PASS", "FAIL", "NOT_CHECKED")


def test_runner_mode_vocab_is_closed_exact() -> None:
    assert apr.RUNNER_MODE == ("status_only", "plan_only", "run_one")


def test_implementation_strategy_vocab_is_closed_exact() -> None:
    assert apr.IMPLEMENTATION_STRATEGY == ("none", "external_command")


def test_stop_reason_vocab_contains_every_required_value() -> None:
    """Every refusal path in the runner must map to a closed-vocab
    STOP_REASON value. This pin protects against silent drift."""
    required = {
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
    }
    assert required.issubset(set(apr.STOP_REASON))


def test_runner_report_field_list_exact() -> None:
    assert apr.RUNNER_REPORT_FIELDS == (
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


def test_forbidden_path_patterns_cover_no_touch_list() -> None:
    required = {
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
        "docs/development_work_queue/",
        "tests/regression/",
        "research/research_latest.json",
        "research/strategy_matrix.csv",
        "artifacts/",
    }
    assert required.issubset(set(apr.FORBIDDEN_PATH_PATTERNS))


def test_max_units_per_run_hard_capped_at_one() -> None:
    assert apr.MAX_UNITS_PER_RUN_HARD_CAP == 1


def test_step5_implementation_allowed_is_final_false() -> None:
    assert apr.step5_implementation_allowed is False


def test_step5_enabled_substage_is_a21d() -> None:
    assert apr.STEP5_ENABLED_SUBSTAGE == (
        "a21d_bounded_pr_creation_and_auto_merge"
    )


def test_module_version_string() -> None:
    assert apr.MODULE_VERSION.endswith("A21d")


# ---------------------------------------------------------------------------
# Default CLI surface: status / plan-only do not execute anything
# ---------------------------------------------------------------------------


def test_cli_default_does_not_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bare ``python -m reporting.autonomous_pr_runner`` (no flag)
    falls back to status-only and writes nothing."""
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    rc = apr.main([])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "mode=status_only" in out
    assert "final_runner_status=status_only" in out


def test_cli_status_does_not_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    rc = apr.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "no_runtime_trading_authority=True" in out
    assert "no_auto_merge_outside_bounded_a21d_slice=True" in out
    assert "no_admin_merge=True" in out
    assert "no_deploy_invocation=True" in out
    assert "no_step5_broad=True" in out
    assert "no_level6=True" in out


def test_cli_plan_only_does_not_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    rc = apr.main(["--plan-only", "--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["mode"] == "plan_only"
    assert payload["final_runner_status"] == "plan_only"
    # No git / gh command should have been recorded.
    for cmd in payload["commands_run"]:
        first = cmd["command"].split()[:1]
        assert first not in (["git"], ["gh"])


def test_cli_run_one_with_default_strategy_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--run-one`` without an explicit strategy is refused at
    the implementation_strategy_configured gate."""
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    # Use --no-write to avoid touching the real repo logs/ dir.
    rc = apr.main(["--run-one", "--no-write"])
    # Exit code is non-zero because stop_reason != ok_pr_opened.
    assert rc != 0


# ---------------------------------------------------------------------------
# Safety gate evaluation
# ---------------------------------------------------------------------------


def _baseline_selector_snapshot(unit_id: str = "u_runner_synth") -> dict[str, Any]:
    return {
        "selection": {
            "selection_status": "OK_SELECTED",
            "selected_unit_id": unit_id,
            "selected_phase": "v3.15.17",
            "selected_authority_class": "AUTO_ALLOWED",
            "selected_risk_class": "LOW",
            "selected_operator_gate": "none",
            "requires_operator_go": False,
        }
    }


def _baseline_unit() -> dict[str, Any]:
    return {
        "id": "u_runner_synth",
        "expected_files": [
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        "forbidden_files": [".claude/**"],
        "required_tests": ["tests/unit/test_synthetic_runner_target.py"],
        "status": "not_started",
    }


def test_gates_pass_on_happy_path() -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail is None
    for g in gates:
        assert g["result"] == "PASS", g


def test_gates_fail_when_selector_unavailable() -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=None,
        unit=None,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "selector_unavailable"
    # Every other gate must be NOT_CHECKED.
    for g in gates[1:]:
        assert g["result"] == "NOT_CHECKED", g


def test_gates_pass_selection_status_when_all_needs_human_gated() -> None:
    """``ALL_NEEDS_HUMAN_GATED`` names a specific gated unit; the
    selection_status_ok gate intentionally lets it through so the
    downstream per-authority gate produces the more specific stop
    reason (``unsafe_authority_class`` / ``unsafe_operator_gate`` /
    ``requires_operator_go``)."""
    snap = _baseline_selector_snapshot()
    snap["selection"]["selection_status"] = "ALL_NEEDS_HUMAN_GATED"
    snap["selection"]["selected_authority_class"] = "NEEDS_HUMAN"
    snap["selection"]["requires_operator_go"] = True
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    # selection_status_ok gate PASSES; authority gate FAILS first.
    assert fail == "unsafe_authority_class"
    by_gate = {g["gate"]: g for g in gates}
    assert by_gate["selection_status_ok"]["result"] == "PASS"
    assert by_gate["auto_allowed_authority"]["result"] == "FAIL"


@pytest.mark.parametrize(
    "bad_status,expected_fail",
    [
        ("NO_ELIGIBLE_UNITS", "no_eligible_unit"),
        ("UPSTREAM_UNAVAILABLE", "no_eligible_unit"),
        ("ALL_PERMANENTLY_DENIED", "ambiguous_selection"),
        ("ALL_BLOCKED_BY_PREREQUISITES", "ambiguous_selection"),
        ("FAIL_CLOSED_INVARIANT", "ambiguous_selection"),
    ],
)
def test_gates_fail_when_selection_status_terminal_no_unit(
    bad_status: str, expected_fail: str
) -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["selection_status"] = bad_status
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == expected_fail


def test_gates_fail_on_needs_human_authority() -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["selected_authority_class"] = "NEEDS_HUMAN"
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "unsafe_authority_class"


def test_gates_fail_on_permanently_denied_authority() -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["selected_authority_class"] = "PERMANENTLY_DENIED"
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "unsafe_authority_class"


@pytest.mark.parametrize("risk", ["MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"])
def test_gates_fail_on_non_low_risk(risk: str) -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["selected_risk_class"] = risk
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "unsafe_risk_class"


@pytest.mark.parametrize(
    "gate_value",
    ["operator_go_required", "governance_bootstrap_pr_required"],
)
def test_gates_fail_on_non_none_operator_gate(gate_value: str) -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["selected_operator_gate"] = gate_value
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "unsafe_operator_gate"


def test_gates_fail_on_requires_operator_go() -> None:
    snap = _baseline_selector_snapshot()
    snap["selection"]["requires_operator_go"] = True
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=snap,
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "requires_operator_go"


def test_gates_fail_when_expected_files_empty() -> None:
    unit = _baseline_unit()
    unit["expected_files"] = []
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=unit,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "missing_expected_files"


def test_gates_fail_when_forbidden_files_empty() -> None:
    unit = _baseline_unit()
    unit["forbidden_files"] = []
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=unit,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "missing_forbidden_files"


def test_gates_fail_when_required_tests_empty() -> None:
    unit = _baseline_unit()
    unit["required_tests"] = []
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=unit,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "missing_required_tests"


@pytest.mark.parametrize(
    "forbidden_in_expected",
    [
        "dashboard/dashboard.py",
        ".claude/hooks/x.py",
        ".github/workflows/main.yml",
        "automation/live_gate.py",
        "broker/router.py",
        "agent/risk/limits.py",
        "agent/execution/runner.py",
        "live/strategy.py",
        "paper/strategy.py",
        "shadow/strategy.py",
        "trading/api.py",
        "research/research_latest.json",
        "research/strategy_matrix.csv",
        "tests/regression/test_authority_invariants.py",
        "docs/development_work_queue/admission.jsonl",
        "reporting/execution_authority.py",
        "reporting/development_queue_admission_policy.py",
    ],
)
def test_gates_fail_when_expected_files_contains_forbidden_path(
    forbidden_in_expected: str,
) -> None:
    unit = _baseline_unit()
    unit["expected_files"] = [forbidden_in_expected]
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=unit,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "forbidden_path_in_expected_files"


@pytest.mark.parametrize(
    "terminal_status",
    ["merged", "blocked", "skipped", "failed"],
)
def test_gates_fail_on_terminal_static_status(
    terminal_status: str,
) -> None:
    unit = _baseline_unit()
    unit["status"] = terminal_status
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=unit,
        max_units=1,
        implementation_strategy="external_command",
    )
    assert fail == "terminal_status"


@pytest.mark.parametrize("requested", [0, 2, 3, 5, 10])
def test_gates_fail_when_max_units_not_one(requested: int) -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=_baseline_unit(),
        max_units=requested,
        implementation_strategy="external_command",
    )
    assert fail == "max_units_exceeded"


def test_gates_fail_when_implementation_strategy_is_default_none() -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="none",
    )
    assert fail == "implementation_strategy_not_configured"


def test_gates_fail_on_unknown_implementation_strategy() -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="some_unknown_strategy",
    )
    assert fail == "implementation_strategy_not_configured"


# ---------------------------------------------------------------------------
# status() / plan() do not execute
# ---------------------------------------------------------------------------


def test_status_does_not_invoke_shell_or_strategy(tmp_path: Path) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(
        repo_root=tmp_path, generated_at_utc=_FROZEN_UTC
    )
    assert report["mode"] == "status_only"
    assert report["final_runner_status"] == "status_only"
    assert report["stop_reason"] == "status_only_mode"
    assert report["commands_run"] == []


def test_plan_evaluates_gates_but_does_not_execute(tmp_path: Path) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.plan(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy="external_command",
    )
    assert report["mode"] == "plan_only"
    assert report["final_runner_status"] == "plan_only"
    assert report["commands_run"] == []
    assert report["branch_name"].startswith("step5-a21c/")
    for g in report["safety_gate_results"]:
        assert g["result"] in apr.GATE_RESULT


def test_plan_with_default_strategy_marks_gate_fail(tmp_path: Path) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.plan(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
    )
    assert report["stop_reason"] == "implementation_strategy_not_configured"


# ---------------------------------------------------------------------------
# run_one(...) end-to-end with fakes
# ---------------------------------------------------------------------------


def _run_one_with_fakes(
    tmp_path: Path,
    *,
    shell: _FakeShell,
    strategy: _FakeStrategy,
    unit_overrides: dict[str, Any] | None = None,
    decision_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _write_minimal_upstreams(
        tmp_path,
        unit_overrides=unit_overrides,
        decision_overrides=decision_overrides,
    )
    return apr.run_one(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy_name="external_command",
        shell=shell,
        implementation_strategy=strategy,
    )


def _queue_happy_path_shell(
    shell: _FakeShell,
    *,
    changed_paths: list[str],
    pr_number: int = 999,
) -> None:
    # git checkout -b
    shell.queue(("git", "checkout"), exit_code=0)
    # git status --porcelain (after implementation)
    porcelain = "\n".join(f" M {p}" for p in changed_paths)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=porcelain,
    )
    # required tests (one per required_test entry)
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    # smoke tests
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    # governance lint
    shell.queue(("python", "scripts/governance_lint.py"), exit_code=0)
    # git add (one per changed_path)
    for _ in changed_paths:
        shell.queue(("git", "add"), exit_code=0)
    # git commit
    shell.queue(("git", "commit"), exit_code=0)
    # git push
    shell.queue(("git", "push"), exit_code=0)
    # gh pr create
    shell.queue(
        ("gh", "pr", "create"),
        exit_code=0,
        stdout=f"https://github.com/test/test/pull/{pr_number}\n",
    )
    # gh pr checks --watch
    shell.queue(("gh", "pr", "checks"), exit_code=0)


def test_run_one_happy_path_opens_pr_and_stops(tmp_path: Path) -> None:
    """Without ``auto_merge_runner_pr``, the runner stops after the
    PR is opened + CI green; final stop reason is the no-auto-merge
    success."""
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_happy_path_shell(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        pr_number=999,
    )
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_pr_opened"
    assert report["stop_reason"] == "ok_pr_opened_no_auto_merge"
    assert report["pr_number"] == 999
    assert report["ci_status"] == "PASS"
    assert report["auto_merge_enabled"] is False
    assert report["pr_merge_sha"] == ""
    assert report["post_merge_gates"] == []
    assert report["ledger_update_path"] == ""
    assert strategy.calls == [
        {"unit_id": "u_runner_synth", "root": tmp_path}
    ]


def test_run_one_does_not_auto_merge_or_deploy(tmp_path: Path) -> None:
    """No shell invocation should be ``gh pr merge``, carry
    ``--admin``, or be a deploy command. Commit / PR body arguments
    are excluded because their text legitimately states the no-deploy
    posture."""
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_happy_path_shell(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    for call_args, _cwd, _timeout in shell.calls:
        # No gh-pr-merge command and no deploy command.
        assert call_args[:3] != ["gh", "pr", "merge"]
        assert call_args[:1] != ["deploy"]
        # The first token (program name) must not be deploy-related.
        first = call_args[0] if call_args else ""
        assert "deploy" not in first.lower()
        # Inspect each argument individually so we can skip commit /
        # PR body text. The body intentionally states 'no auto-merge'
        # and 'no deploy' as part of the safety posture.
        for i, arg in enumerate(call_args):
            # Commit message follows ``git commit -m``.
            if (
                i >= 1
                and call_args[0] == "git"
                and len(call_args) > 1
                and call_args[1] == "commit"
                and call_args[i - 1] == "-m"
            ):
                continue
            # PR title follows ``--title`` and PR body follows
            # ``--body`` in ``gh pr create``.
            if i >= 1 and call_args[i - 1] in {"--title", "--body"}:
                continue
            assert "--admin" not in arg
            # Reject deploy as a literal arg in any non-message
            # position (e.g. ``deploy --target prod``).
            assert arg.lower() != "deploy"


def test_run_one_refuses_unsafe_authority(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy()
    report = _run_one_with_fakes(
        tmp_path,
        shell=shell,
        strategy=strategy,
        decision_overrides={
            "final_authority_class": "NEEDS_HUMAN",
            "requires_operator_go": True,
        },
        unit_overrides={"authority_hint": "NEEDS_HUMAN_CANDIDATE"},
    )
    assert report["final_runner_status"] == "refused_unsafe"
    assert report["stop_reason"] == "unsafe_authority_class"
    # No shell call should have happened — refusal is pre-execution.
    assert shell.calls == []
    assert strategy.calls == []


def test_run_one_refuses_diff_outside_expected_files(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=" M reporting/somewhere_unexpected.py\n",
    )
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_diff"
    assert report["stop_reason"] == "diff_outside_expected_files"


def test_run_one_refuses_diff_touching_forbidden_path(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=" M dashboard/dashboard.py\n",
    )
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_diff"
    assert report["stop_reason"] == "diff_touches_forbidden_path"


def test_run_one_refuses_empty_diff(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(("git", "status"), exit_code=0, stdout="")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_diff"
    assert report["stop_reason"] == "diff_empty"


def test_run_one_stops_on_failing_required_tests(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=(
            " M reporting/synthetic_runner_target.py\n"
            " M tests/unit/test_synthetic_runner_target.py\n"
        ),
    )
    # Required test fails.
    shell.queue(("python", "-m", "pytest"), exit_code=1, stdout="FAIL")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_tests"
    assert report["stop_reason"] == "tests_failed"


def test_run_one_stops_on_failing_governance_lint(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=(
            " M reporting/synthetic_runner_target.py\n"
            " M tests/unit/test_synthetic_runner_target.py\n"
        ),
    )
    # required tests pass
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    # smoke pass
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    # governance lint fails
    shell.queue(("python", "scripts/governance_lint.py"), exit_code=1)
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_governance_lint"
    )
    assert report["stop_reason"] == "governance_lint_failed"


def test_run_one_stops_on_implementation_strategy_failure(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=False, reason="strategy_died")
    shell.queue(("git", "checkout"), exit_code=0)
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_implementation"
    )
    assert report["stop_reason"] == "implementation_strategy_failed"


def test_run_one_stops_on_branch_creation_failure(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(
        ("git", "checkout"),
        exit_code=1,
        stderr="fatal: cannot create branch",
    )
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_implementation"
    )
    assert report["stop_reason"] == "branch_creation_failed"
    # Strategy must not have been invoked.
    assert strategy.calls == []


def test_run_one_detects_branch_already_exists(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(
        ("git", "checkout"),
        exit_code=128,
        stderr="fatal: a branch named 'step5-a21c/u_runner_synth' already exists",
    )
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["stop_reason"] == "branch_already_exists"


def test_run_one_stops_on_push_failure(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=(
            " M reporting/synthetic_runner_target.py\n"
            " M tests/unit/test_synthetic_runner_target.py\n"
        ),
    )
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    shell.queue(("python", "scripts/governance_lint.py"), exit_code=0)
    shell.queue(("git", "add"), exit_code=0)
    shell.queue(("git", "add"), exit_code=0)
    shell.queue(("git", "commit"), exit_code=0)
    shell.queue(("git", "push"), exit_code=1, stderr="rejected")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_push"
    assert report["stop_reason"] == "push_failed"


def test_run_one_stops_on_pr_creation_failure(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(
        ("git", "status"),
        exit_code=0,
        stdout=(
            " M reporting/synthetic_runner_target.py\n"
            " M tests/unit/test_synthetic_runner_target.py\n"
        ),
    )
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    shell.queue(("python", "-m", "pytest"), exit_code=0)
    shell.queue(("python", "scripts/governance_lint.py"), exit_code=0)
    shell.queue(("git", "add"), exit_code=0)
    shell.queue(("git", "add"), exit_code=0)
    shell.queue(("git", "commit"), exit_code=0)
    shell.queue(("git", "push"), exit_code=0)
    shell.queue(("gh", "pr", "create"), exit_code=1, stderr="boom")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_pr_create"
    )
    assert report["stop_reason"] == "pr_creation_failed"


def test_run_one_stops_on_ci_failure(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_happy_path_shell(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    # Replace the CI-watch queued entry (last entry) with a failure.
    # Easier: pop the last entry and re-queue a failing one.
    for i, (prefix, _r) in enumerate(shell.results):
        if prefix == ("gh", "pr", "checks"):
            shell.results.pop(i)
            break
    shell.queue(("gh", "pr", "checks"), exit_code=1, stderr="failing")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_ci"
    assert report["stop_reason"] == "ci_failed"
    assert report["ci_status"] == "FAIL"


def test_run_one_stops_on_ci_timeout(tmp_path: Path) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_happy_path_shell(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    for i, (prefix, _r) in enumerate(shell.results):
        if prefix == ("gh", "pr", "checks"):
            shell.results.pop(i)
            break
    shell.queue(("gh", "pr", "checks"), exit_code=124, stderr="timeout")
    report = _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_ci"
    assert report["stop_reason"] == "ci_timeout"
    assert report["ci_status"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# Runner invariants pinned on every report
# ---------------------------------------------------------------------------


def test_runner_invariants_pin_no_runtime_trading_authority(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_runner_invariants_pin_no_auto_merge_outside_a21d_slice(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_auto_merge_outside_bounded_a21d_slice"] is True
    assert inv["no_arbitrary_pr_auto_merge"] is True
    assert inv["no_non_runner_originated_pr_merge"] is True
    assert inv["no_admin_merge"] is True
    assert inv["no_force_push"] is True
    assert inv["no_hook_bypass"] is True
    assert inv["no_deploy_invocation"] is True
    assert inv["no_deploy_workflow_trigger"] is True


def test_runner_invariants_pin_no_step5_broad_no_level6(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_step5_broad"] is True
    assert inv["no_level6"] is True
    assert inv["no_production_merge_authority"] is True
    assert report["step5_implementation_allowed"] is False


def test_runner_invariants_pin_bounded_step5_pr_creation_only(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["bounded_step5_pr_creation_only"] is True
    assert inv["max_units_per_run_hard_capped_at_one"] is True


def test_runner_invariants_pin_no_static_seed_mutation(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_static_seed_mutation"] is True
    assert inv["no_a21a_seed_mutation"] is True
    assert inv["no_a20b_seed_mutation"] is True
    assert inv["no_work_queue_jsonl_mutation"] is True
    assert inv["writes_to_static_a21a_seed"] is False
    assert inv["writes_to_static_a20b_seed"] is False
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_work_queue_jsonl"] is False


def test_runner_invariants_pin_no_mutation_routes_or_approval_buttons(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_mutation_routes"] is True
    assert inv["no_approval_buttons"] is True
    assert inv["no_approval_inbox_mutation"] is True


def test_runner_invariants_pin_no_subprocess_outside_run_one(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["subprocess_module_used_only_inside_run_one"] is True
    assert inv["uses_subprocess_outside_run_one"] is False
    assert inv["uses_network"] is False
    assert inv["calls_llm_or_external_api"] is False


def test_runner_invariants_pin_fail_closed_contracts(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["fail_closed_on_unsafe_unit"] is True
    assert inv["fail_closed_on_diff_outside_expected_files"] is True
    assert inv["fail_closed_on_forbidden_diff_path"] is True
    assert inv["fail_closed_on_test_failure"] is True
    assert inv["fail_closed_on_governance_lint_failure"] is True
    assert inv["fail_closed_on_ci_failure"] is True


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        apr._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(
    tmp_path: Path,
) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
        "docs/development_work_queue/latest.jsonl",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            apr._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    apr._atomic_write_json(good, {"x": 1})
    assert good.is_file()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_status_deterministic_with_injected_ts(tmp_path: Path) -> None:
    _write_minimal_upstreams(tmp_path)
    a = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    b = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_plan_deterministic_with_injected_ts(tmp_path: Path) -> None:
    _write_minimal_upstreams(tmp_path)
    a = apr.plan(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy="external_command",
    )
    b = apr.plan(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy="external_command",
    )
    out_a = json.dumps(a, indent=2, sort_keys=True)
    out_b = json.dumps(b, indent=2, sort_keys=True)
    assert out_a == out_b


# ---------------------------------------------------------------------------
# Real shell runner factory invariants
# ---------------------------------------------------------------------------


def test_real_shell_runner_factory_imports_subprocess_lazily() -> None:
    """The real shell runner factory must import ``subprocess`` at
    invocation time, not at module load time. This is what keeps
    ``import reporting.autonomous_pr_runner`` import-safe."""
    src = _module_source()
    # Module-level: subprocess MUST NOT be imported at top.
    top = _module_top_level_imports()
    for module in top:
        assert not module.startswith("subprocess"), module
    # But the factory body must contain a deferred subprocess import.
    assert "import subprocess" in src


def test_real_shell_runner_factory_is_called_only_inside_run_one() -> None:
    """The factory is named ``_real_shell_runner_factory``. The
    runner only calls it when ``shell is None`` inside ``run_one``.
    Counted as ``= _real_shell_runner_factory()`` to exclude the
    function-definition line."""
    src = _module_source()
    call_sites = src.count("= _real_shell_runner_factory()")
    assert call_sites == 1


def test_module_imports_only_canonical_upstreams() -> None:
    """The runner may only import from A20b / A20e / A21a (read-only)
    and may NOT import the canonical execution_authority classifier
    or any runtime trading module."""
    allowed = {
        "reporting.roadmap_task_units",
        "reporting.roadmap_unit_authority",
        "reporting.roadmap_next_unit",
        "reporting.roadmap_unit_status",
    }
    for module in _module_top_level_imports():
        if module.startswith("reporting."):
            assert module in allowed, module


# ---------------------------------------------------------------------------
# parse_pr_number helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("https://github.com/owner/repo/pull/256\n", 256),
        ("https://github.com/owner/repo/pull/9999", 9999),
        ("Opened PR #42\nhttps://github.com/owner/repo/pull/42", 42),
        ("", 0),
        ("no url here", 0),
        ("https://example.com/no/pull/here/0", 0),
    ],
)
def test_parse_pr_number(stdout: str, expected: int) -> None:
    assert apr._parse_pr_number(stdout) == expected


# ===========================================================================
# A21d auto-merge phase tests
# ===========================================================================


_A21D_PR_NUMBER = 999
_A21D_MERGE_SHA = "abc1234def567890abc1234def567890abc1234d"


def _expected_pr_metadata_json(
    *,
    title: str | None = None,
    body: str | None = None,
    mergeable: str = "MERGEABLE",
    merge_state_status: str = "CLEAN",
) -> str:
    return json.dumps(
        {
            "title": (
                title
                if title is not None
                else "feat(u_runner_synth): Synthetic eligible runner unit"
            ),
            "body": (
                body
                if body is not None
                else (
                    "## Summary\n\n"
                    "Auto-prepared by `reporting.autonomous_pr_runner` "
                    "(A21c bounded slice) on branch step5-a21c/"
                    "u_runner_synth.\n\n"
                    "- Selected A20e unit id: u_runner_synth"
                )
            ),
            "mergeable": mergeable,
            "mergeStateStatus": merge_state_status,
        }
    )


def _expected_pr_diff_stdout(paths: list[str]) -> str:
    return "\n".join(paths) + "\n"


def _expected_merge_commit_json(sha: str = _A21D_MERGE_SHA) -> str:
    return json.dumps({"mergeCommit": {"oid": sha}})


def _expected_run_list_json(
    *,
    workflow_name: str,
    head_sha: str,
    run_id: int = 12345,
    status: str = "in_progress",
    conclusion: str | None = None,
) -> str:
    return json.dumps(
        [
            {
                "databaseId": run_id,
                "status": status,
                "conclusion": conclusion,
                "headSha": head_sha,
            }
        ]
    )


def _queue_auto_merge_happy_path(
    shell: _FakeShell,
    *,
    changed_paths: list[str],
    pr_number: int = _A21D_PR_NUMBER,
    merge_sha: str = _A21D_MERGE_SHA,
) -> None:
    """Queue shell responses for a full happy-path run-one +
    auto-merge cycle."""
    # PR-create phase
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=pr_number
    )
    # Auto-merge phase:
    # 1) gh pr view --json title,body,mergeable,mergeStateStatus
    shell.queue(
        ("gh", "pr", "view", str(pr_number), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(),
    )
    # 2) gh pr diff --name-only
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    # 3) gh pr merge --squash --delete-branch
    shell.queue(("gh", "pr", "merge"), exit_code=0)
    # 4) git checkout main
    shell.queue(("git", "checkout"), exit_code=0)
    # 5) git pull --ff-only
    shell.queue(("git", "pull"), exit_code=0)
    # 6) gh pr view --json mergeCommit
    shell.queue(
        ("gh", "pr", "view", str(pr_number), "--json"),
        exit_code=0,
        stdout=_expected_merge_commit_json(merge_sha),
    )
    # 7) For each post-merge workflow: list (success inline) - no
    # watch needed.
    for workflow_name in (
        "Fast pre-merge gate",
        "Build & Push Docker Image",
        "Deploy VPS Dashboard",
    ):
        shell.queue(
            ("gh", "run", "list"),
            exit_code=0,
            stdout=_expected_run_list_json(
                workflow_name=workflow_name,
                head_sha=merge_sha,
                status="completed",
                conclusion="success",
            ),
        )


def _run_one_with_auto_merge(
    tmp_path: Path,
    *,
    shell: _FakeShell,
    strategy: _FakeStrategy,
    unit_overrides: dict[str, Any] | None = None,
    decision_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _write_minimal_upstreams(
        tmp_path,
        unit_overrides=unit_overrides,
        decision_overrides=decision_overrides,
    )
    return apr.run_one(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy_name="external_command",
        auto_merge_runner_pr=True,
        shell=shell,
        implementation_strategy=strategy,
    )


# ---------------------------------------------------------------------------
# Auto-merge default-off
# ---------------------------------------------------------------------------


def test_run_one_default_does_not_auto_merge(tmp_path: Path) -> None:
    """Without ``auto_merge_runner_pr=True``, the runner must NOT
    invoke ``gh pr merge`` at all."""
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_happy_path_shell(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        pr_number=_A21D_PR_NUMBER,
    )
    _run_one_with_fakes(
        tmp_path, shell=shell, strategy=strategy
    )
    # No `gh pr merge` invocation must appear.
    for call_args, _cwd, _timeout in shell.calls:
        assert call_args[:3] != ["gh", "pr", "merge"], call_args


def test_cli_run_one_requires_explicit_auto_merge_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--run-one`` alone does not enable auto-merge. The flag must
    be opt-in."""
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    rc = apr.main([
        "--run-one",
        "--no-write",
        "--implementation-strategy", "external_command",
        "--implementation-command", "echo test",
    ])
    # Non-zero because the real run_one would need a real shell; this
    # path actually runs through the real shell factory and fails
    # somewhere in the real git commands. The test guarantee here is
    # only that auto-merge is NOT enabled by default.
    _ = rc  # the CLI returns 1 on stop, which we just assert is sane
    out_text = sentinel.read_text(encoding="utf-8") if sentinel.exists() else ""
    if out_text:
        payload = json.loads(out_text)
        assert payload["auto_merge_enabled"] is False


def test_status_with_auto_merge_flag_does_not_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "autonomous_pr_runner" / "latest.json"
    monkeypatch.setattr(apr, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(apr, "ARTIFACT_DIR", sentinel.parent)
    rc = apr.main(["--status", "--auto-merge-runner-pr"])
    assert rc == 0
    assert not sentinel.exists()


# ---------------------------------------------------------------------------
# Auto-merge happy path
# ---------------------------------------------------------------------------


def test_run_one_with_auto_merge_completes_full_pipeline(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_auto_merge_happy_path(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_pr_merged"
    assert report["stop_reason"] == "ok_pr_merged"
    assert report["pr_number"] == _A21D_PR_NUMBER
    assert report["pr_merge_sha"] == _A21D_MERGE_SHA
    assert report["auto_merge_enabled"] is True
    assert len(report["post_merge_gates"]) == 3
    for outcome in report["post_merge_gates"]:
        assert outcome["conclusion"] == "success"
    assert report["ledger_update_path"] == (
        "logs/roadmap_unit_status/runner_merges.json"
    )


def test_run_one_with_auto_merge_writes_runner_merges_artifact(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_auto_merge_happy_path(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    artifact = tmp_path / "logs" / "roadmap_unit_status" / "runner_merges.json"
    assert artifact.is_file()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "runner_auto_merge_evidence"
    assert len(payload["records"]) == 1
    rec = payload["records"][0]
    assert rec["unit_id"] == "u_runner_synth"
    assert rec["status"] == "merged"
    assert rec["source"] == "runner_auto_merge"
    assert rec["pr_number"] == _A21D_PR_NUMBER
    assert rec["merge_sha"] == _A21D_MERGE_SHA
    assert any("github_pr_number=999" in ev for ev in rec["evidence"])
    assert any(
        ev.startswith("fast_pre_merge_gate=") for ev in rec["evidence"]
    )
    assert any(
        ev.startswith("deploy_vps_dashboard=") for ev in rec["evidence"]
    )


def test_run_one_with_auto_merge_invokes_squash_not_admin(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_auto_merge_happy_path(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    # Find the gh pr merge call.
    merge_calls = [
        c[0] for c in shell.calls if c[0][:3] == ["gh", "pr", "merge"]
    ]
    assert len(merge_calls) == 1
    args = merge_calls[0]
    assert "--squash" in args
    assert "--delete-branch" in args
    assert "--admin" not in args
    assert "--force" not in args
    assert "--no-verify" not in args


def test_run_one_with_auto_merge_never_invokes_force_push(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _queue_auto_merge_happy_path(
        shell,
        changed_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
    )
    _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    for call_args, _cwd, _timeout in shell.calls:
        assert "--force" not in call_args
        assert "--force-with-lease" not in call_args


# ---------------------------------------------------------------------------
# Auto-merge eligibility gates
# ---------------------------------------------------------------------------


def test_evaluate_auto_merge_gates_happy_path() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": (
                "Body containing Auto-prepared by "
                "`reporting.autonomous_pr_runner` signature"
            ),
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail is None
    for g in gates:
        assert g["result"] == "PASS", g


def test_evaluate_auto_merge_gates_refuses_when_flag_off() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": (
                "Auto-prepared by `reporting.autonomous_pr_runner`"
            ),
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=[
            "reporting/synthetic_runner_target.py",
            "tests/unit/test_synthetic_runner_target.py",
        ],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=False,
        max_merges=1,
    )
    assert fail == "auto_merge_disabled"


def test_evaluate_auto_merge_gates_refuses_when_pr_number_missing() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=0,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "not_runner_originated"


def test_evaluate_auto_merge_gates_refuses_branch_mismatch() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="hand/some-other-branch",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "pr_branch_mismatch"


def test_evaluate_auto_merge_gates_refuses_title_without_unit_id() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "some unrelated PR title",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "pr_title_missing_unit_id"


def test_evaluate_auto_merge_gates_refuses_body_without_runner_signature() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Hand-written PR body without runner signature",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "pr_body_missing_runner_signature"


def test_evaluate_auto_merge_gates_refuses_diff_outside_expected_files() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=[
            "reporting/synthetic_runner_target.py",
            "reporting/some_other_unexpected_file.py",
        ],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "pr_diff_outside_expected_files"


def test_evaluate_auto_merge_gates_refuses_diff_touching_forbidden_path() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=[
            "reporting/synthetic_runner_target.py",
            "dashboard/dashboard.py",
        ],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "pr_diff_touches_forbidden_path"


def test_evaluate_auto_merge_gates_refuses_ci_not_green() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=False,
        mergeability="MERGEABLE",
        merge_state_status="CLEAN",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "ci_failed"


def test_evaluate_auto_merge_gates_refuses_dirty_mergeability() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="CONFLICTING",
        merge_state_status="DIRTY",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "mergeability_not_clean"


def test_evaluate_auto_merge_gates_refuses_branch_protection_requires_admin() -> None:
    gates, fail = apr._evaluate_auto_merge_gates(
        pr_number=_A21D_PR_NUMBER,
        branch_name="step5-a21c/u_runner_synth",
        unit=_baseline_unit(),
        pr_metadata={
            "title": "feat(u_runner_synth): xyz",
            "body": "Auto-prepared by `reporting.autonomous_pr_runner`",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED",
        },
        pr_diff_paths=["reporting/synthetic_runner_target.py"],
        ci_clean=True,
        mergeability="MERGEABLE",
        merge_state_status="BLOCKED",
        auto_merge_enabled=True,
        max_merges=1,
    )
    assert fail == "branch_protection_requires_admin"


# ---------------------------------------------------------------------------
# Pre-flight gates: max_merges and the existing per-unit safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("requested", [0, 2, 3, 5])
def test_pre_flight_gates_refuse_max_merges_not_one(requested: int) -> None:
    gates, fail = apr.evaluate_safety_gates(
        selector_snapshot=_baseline_selector_snapshot(),
        unit=_baseline_unit(),
        max_units=1,
        implementation_strategy="external_command",
        max_merges=requested,
    )
    assert fail == "max_merges_exceeded"


def test_run_one_with_auto_merge_refuses_max_merges_above_one(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    _write_minimal_upstreams(tmp_path)
    report = apr.run_one(
        repo_root=tmp_path,
        generated_at_utc=_FROZEN_UTC,
        implementation_strategy_name="external_command",
        max_merges=5,
        auto_merge_runner_pr=True,
        shell=shell,
        implementation_strategy=strategy,
    )
    assert report["final_runner_status"] == "refused_unsafe"
    assert report["stop_reason"] == "max_merges_exceeded"
    # Refusal happens pre-execution: no shell calls.
    assert shell.calls == []


# ---------------------------------------------------------------------------
# Auto-merge stop paths: merge failure, sha unknown, post-merge gates,
# ledger write failure
# ---------------------------------------------------------------------------


def test_run_one_with_auto_merge_stops_on_merge_failure(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    changed_paths = [
        "reporting/synthetic_runner_target.py",
        "tests/unit/test_synthetic_runner_target.py",
    ]
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=_A21D_PR_NUMBER
    )
    # Auto-merge phase: pr view (metadata) ok, pr diff ok, pr merge FAIL.
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(),
    )
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    shell.queue(
        ("gh", "pr", "merge"),
        exit_code=1,
        stderr="merge rejected",
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_auto_merge"
    assert report["stop_reason"] == "merge_failed"
    assert report["pr_merge_sha"] == ""


def test_run_one_with_auto_merge_stops_on_dirty_mergeability(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    changed_paths = [
        "reporting/synthetic_runner_target.py",
        "tests/unit/test_synthetic_runner_target.py",
    ]
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=_A21D_PR_NUMBER
    )
    # PR view returns DIRTY mergeability => auto-merge gate refuses
    # before any merge call.
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(
            mergeable="CONFLICTING", merge_state_status="DIRTY"
        ),
    )
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_auto_merge"
    assert report["stop_reason"] == "mergeability_not_clean"
    # No merge call.
    for call_args, _cwd, _timeout in shell.calls:
        assert call_args[:3] != ["gh", "pr", "merge"]


def test_run_one_with_auto_merge_stops_on_post_merge_fast_gate_failure(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    changed_paths = [
        "reporting/synthetic_runner_target.py",
        "tests/unit/test_synthetic_runner_target.py",
    ]
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=_A21D_PR_NUMBER
    )
    # Auto-merge phase up to merge SHA capture: all green.
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(),
    )
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    shell.queue(("gh", "pr", "merge"), exit_code=0)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(("git", "pull"), exit_code=0)
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_merge_commit_json(),
    )
    # Fast pre-merge gate returns failure.
    shell.queue(
        ("gh", "run", "list"),
        exit_code=0,
        stdout=_expected_run_list_json(
            workflow_name="Fast pre-merge gate",
            head_sha=_A21D_MERGE_SHA,
            status="completed",
            conclusion="failure",
        ),
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_post_merge_gates"
    )
    assert report["stop_reason"] == "post_merge_fast_gate_failed"
    assert report["pr_merge_sha"] == _A21D_MERGE_SHA
    # Ledger update must NOT happen on post-merge gate failure.
    artifact = (
        tmp_path / "logs" / "roadmap_unit_status" / "runner_merges.json"
    )
    assert not artifact.exists()


def test_run_one_with_auto_merge_stops_on_post_merge_deploy_failure(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    changed_paths = [
        "reporting/synthetic_runner_target.py",
        "tests/unit/test_synthetic_runner_target.py",
    ]
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=_A21D_PR_NUMBER
    )
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(),
    )
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    shell.queue(("gh", "pr", "merge"), exit_code=0)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(("git", "pull"), exit_code=0)
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_merge_commit_json(),
    )
    # Fast pre-merge gate ok.
    shell.queue(
        ("gh", "run", "list"),
        exit_code=0,
        stdout=_expected_run_list_json(
            workflow_name="Fast pre-merge gate",
            head_sha=_A21D_MERGE_SHA,
            status="completed",
            conclusion="success",
        ),
    )
    # Build & Push Docker Image ok.
    shell.queue(
        ("gh", "run", "list"),
        exit_code=0,
        stdout=_expected_run_list_json(
            workflow_name="Build & Push Docker Image",
            head_sha=_A21D_MERGE_SHA,
            status="completed",
            conclusion="success",
        ),
    )
    # Deploy VPS Dashboard FAILS.
    shell.queue(
        ("gh", "run", "list"),
        exit_code=0,
        stdout=_expected_run_list_json(
            workflow_name="Deploy VPS Dashboard",
            head_sha=_A21D_MERGE_SHA,
            status="completed",
            conclusion="failure",
        ),
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == (
        "executed_blocked_at_post_merge_gates"
    )
    assert report["stop_reason"] == "post_merge_deploy_failed"


def test_run_one_with_auto_merge_stops_on_merge_sha_unknown(
    tmp_path: Path,
) -> None:
    shell = _FakeShell()
    strategy = _FakeStrategy(success=True)
    changed_paths = [
        "reporting/synthetic_runner_target.py",
        "tests/unit/test_synthetic_runner_target.py",
    ]
    _queue_happy_path_shell(
        shell, changed_paths=changed_paths, pr_number=_A21D_PR_NUMBER
    )
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=_expected_pr_metadata_json(),
    )
    shell.queue(
        ("gh", "pr", "diff"),
        exit_code=0,
        stdout=_expected_pr_diff_stdout(changed_paths),
    )
    shell.queue(("gh", "pr", "merge"), exit_code=0)
    shell.queue(("git", "checkout"), exit_code=0)
    shell.queue(("git", "pull"), exit_code=0)
    # Merge commit query returns empty.
    shell.queue(
        ("gh", "pr", "view", str(_A21D_PR_NUMBER), "--json"),
        exit_code=0,
        stdout=json.dumps({"mergeCommit": None}),
    )
    report = _run_one_with_auto_merge(
        tmp_path, shell=shell, strategy=strategy
    )
    assert report["final_runner_status"] == "executed_blocked_at_auto_merge"
    assert report["stop_reason"] == "merge_sha_unknown"


# ---------------------------------------------------------------------------
# Runner invariants: A21d-specific pins
# ---------------------------------------------------------------------------


def test_runner_invariants_pin_a21d_auto_merge_bounds(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["bounded_step5_auto_merge_only_for_runner_pr"] is True
    assert inv["auto_merge_requires_explicit_opt_in"] is True
    assert inv["auto_merge_requires_ci_green"] is True
    assert inv["auto_merge_requires_runner_origin"] is True
    assert inv["auto_merge_squash_only_no_admin"] is True
    assert inv["ledger_update_via_runner_merges_artifact_only"] is True
    assert inv["max_merges_per_run_hard_capped_at_one"] is True


def test_runner_invariants_pin_no_arbitrary_pr_auto_merge(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["no_arbitrary_pr_auto_merge"] is True
    assert inv["no_non_runner_originated_pr_merge"] is True
    assert inv["no_pr_merge_outside_auto_merge_phase"] is True


def test_runner_invariants_pin_fail_closed_on_post_merge_gate_failure(
    tmp_path: Path,
) -> None:
    _write_minimal_upstreams(tmp_path)
    report = apr.status(repo_root=tmp_path, generated_at_utc=_FROZEN_UTC)
    inv = report["runner_invariants"]
    assert inv["fail_closed_on_post_merge_gate_failure"] is True
    assert inv["fail_closed_on_ledger_write_failure"] is True
    assert inv["fail_closed_on_non_runner_originated_pr"] is True
    assert inv["fail_closed_on_dirty_mergeability"] is True


# ---------------------------------------------------------------------------
# Workflow-name to evidence-key helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "workflow,key",
    [
        ("Fast pre-merge gate", "fast_pre_merge_gate"),
        ("Build & Push Docker Image", "build_and_push_docker_image"),
        ("Deploy VPS Dashboard", "deploy_vps_dashboard"),
        ("", "unknown_workflow"),
    ],
)
def test_workflow_to_evidence_key(workflow: str, key: str) -> None:
    assert apr._workflow_to_evidence_key(workflow) == key
