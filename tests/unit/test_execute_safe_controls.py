"""Unit tests for ``reporting.execute_safe_controls``.

Properties enforced (verbatim from the v3.15.15.21 brief):

* Action catalog contains only the four whitelisted action types.
* Unknown action type is refused.
* HIGH action is never eligible.
* Arbitrary command input is refused (no free-form path exists).
* Dirty tracked working tree blocks execution.
* Known runtime artifacts do not falsely block planning.
* gh unavailable blocks gh-dependent actions.
* gh unauthenticated blocks gh-dependent actions.
* PR lifecycle dry-run action invokes only the fixed argv recipe.
* Proposal queue dry-run action invokes only the fixed argv recipe.
* Approval inbox dry-run action invokes only the fixed argv recipe.
* Dependabot execute-safe invokes only the existing
  github_pr_lifecycle execute-safe path.
* No direct git push / force-push / --admin can be invoked.
* Frozen hashes are checked before AND after executable actions.
* Catalog snapshot schema is stable.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from reporting import execute_safe_controls as esc

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gh(status: str) -> dict:
    return {
        "status": status,
        "gh_path": "/fake/gh" if status != "not_available" else None,
        "version": "gh version test" if status != "not_available" else None,
        "account": "tester" if status == "available" else None,
        "repo": "test/repo" if status == "available" else None,
    }


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Catalog membership / closed list
# ---------------------------------------------------------------------------


def test_action_types_are_exactly_four() -> None:
    assert len(esc.ACTION_TYPES) == 4
    assert set(esc.ACTION_TYPES) == {
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        esc.ACTION_REFRESH_APPROVAL_INBOX,
        esc.ACTION_RUN_DEPENDABOT_EXECUTE_SAFE,
    }


def test_unknown_action_type_is_refused_at_planner() -> None:
    plan = esc.plan_action(
        "rm_minus_rf_root_filesystem",
        git_clean=True,
        git_dirty_lines=[],
        gh_status=_gh("available"),
    )
    assert plan["eligibility"] == esc.ELIG_INELIGIBLE
    assert "unknown_action_type" in (plan["blocked_reason"] or "")


def test_unknown_action_type_is_refused_at_executor() -> None:
    out = esc.execute_action("rm_minus_rf_root_filesystem")
    assert out["result_status"] == esc.RESULT_BLOCKED
    assert "unknown_action_type" in (out["result_summary"] or out["blocked_reason"] or "")


def test_no_high_risk_action_in_catalog_is_eligible() -> None:
    """Defense in depth: even if a future change accidentally marks
    an action HIGH, the planner refuses to make it eligible."""
    # Force a HIGH risk by monkey-patching the risk map; restore.
    original = dict(esc._ACTION_RISK)
    try:
        esc._ACTION_RISK[esc.ACTION_REFRESH_PR_LIFECYCLE] = esc.RISK_HIGH
        plan = esc.plan_action(
            esc.ACTION_REFRESH_PR_LIFECYCLE,
            git_clean=True,
            git_dirty_lines=[],
            gh_status=_gh("available"),
        )
        assert plan["eligibility"] == esc.ELIG_BLOCKED
        assert "HIGH" in (plan["blocked_reason"] or "")
    finally:
        esc._ACTION_RISK.clear()
        esc._ACTION_RISK.update(original)


# ---------------------------------------------------------------------------
# Working-tree gate
# ---------------------------------------------------------------------------


def test_dirty_working_tree_blocks_planning() -> None:
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        git_clean=False,
        git_dirty_lines=[" M something.py"],
        gh_status=_gh("available"),
    )
    assert plan["eligibility"] == esc.ELIG_BLOCKED
    assert "working tree" in (plan["blocked_reason"] or "")


def test_known_runtime_untracked_does_not_falsely_block() -> None:
    """The working-tree probe ignores ``research/discovery_sprints/``
    and ``frontend/src/`` (gitignored stale tsc-emit artifacts) so the
    operator does not have to clean them up to plan."""
    # The probe reads `git status --porcelain`. We simulate a status
    # that contains only known runtime untracked paths.
    import subprocess

    class _FakeResult:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.returncode = returncode

    original_run = subprocess.run

    def fake_run(*args, **kwargs):  # noqa: ARG001
        return _FakeResult(
            "?? research/discovery_sprints/\n?? frontend/src/App.js\n"
        )

    subprocess.run = fake_run  # type: ignore[assignment]
    try:
        clean, lines, err = esc._git_status_safe()
    finally:
        subprocess.run = original_run

    assert err is None
    assert clean is True
    assert len(lines) == 2


def test_unknown_untracked_path_blocks() -> None:
    import subprocess

    class _FakeResult:
        def __init__(self, stdout: str):
            self.stdout = stdout
            self.returncode = 0

    original = subprocess.run

    def fake_run(*args, **kwargs):  # noqa: ARG001
        return _FakeResult("?? somewhere/unexpected.bin\n")

    subprocess.run = fake_run  # type: ignore[assignment]
    try:
        clean, lines, err = esc._git_status_safe()
    finally:
        subprocess.run = original

    assert err is None
    assert clean is False
    assert lines == ["?? somewhere/unexpected.bin"]


# ---------------------------------------------------------------------------
# gh provider gate (eligibility planner)
# ---------------------------------------------------------------------------


def test_gh_unavailable_blocks_gh_dependent_action() -> None:
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        git_clean=True,
        git_dirty_lines=[],
        gh_status=_gh("not_available"),
    )
    assert plan["eligibility"] == esc.ELIG_BLOCKED
    assert "gh CLI is not available" in (plan["blocked_reason"] or "")


def test_gh_unauthenticated_blocks_gh_dependent_action() -> None:
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        git_clean=True,
        git_dirty_lines=[],
        gh_status=_gh("not_authenticated"),
    )
    assert plan["eligibility"] == esc.ELIG_BLOCKED
    assert "not authenticated" in (plan["blocked_reason"] or "")


def test_gh_unknown_yields_unknown_eligibility() -> None:
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        git_clean=True,
        git_dirty_lines=[],
        gh_status={"status": "unknown"},
    )
    assert plan["eligibility"] == esc.ELIG_UNKNOWN


def test_gh_independent_action_is_eligible_without_gh() -> None:
    """proposal_queue and approval_inbox do NOT need gh, so they
    plan as eligible even when gh is missing."""
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        git_clean=True,
        git_dirty_lines=[],
        gh_status=_gh("not_available"),
    )
    assert plan["eligibility"] == esc.ELIG_ELIGIBLE


def test_gh_available_action_is_eligible() -> None:
    plan = esc.plan_action(
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        git_clean=True,
        git_dirty_lines=[],
        gh_status=_gh("available"),
    )
    assert plan["eligibility"] == esc.ELIG_ELIGIBLE


# ---------------------------------------------------------------------------
# Argv recipes (no operator-supplied tokens)
# ---------------------------------------------------------------------------


def test_argv_recipes_are_constant_and_dont_use_shell() -> None:
    for at, argv in esc._ACTION_ARGV.items():
        assert isinstance(argv, tuple) and len(argv) >= 4, at
        # Must start with the python interpreter + ``-m``.
        assert argv[0] == sys.executable
        assert argv[1] == "-m"
        # The module path must be one of the three reporting modules.
        assert argv[2].startswith("reporting."), at
        # No subprocess shell, no command tokens with spaces, no
        # free-form operator input.
        for token in argv[2:]:
            assert " " not in token, f"token contains space: {token!r}"
            assert ";" not in token, f"token contains semicolon: {token!r}"
            assert "&" not in token, f"token contains ampersand: {token!r}"
            assert "$" not in token, f"token contains dollar: {token!r}"


def test_no_argv_recipe_invokes_git_or_gh_or_destructive_flag() -> None:
    for at, argv in esc._ACTION_ARGV.items():
        joined = " ".join(argv)
        assert "git push" not in joined, at
        assert "--force" not in joined, at
        assert "--force-with-lease" not in joined, at
        assert "--admin" not in joined, at
        # The catalog should never invoke gh / git directly. gh
        # invocations happen INSIDE github_pr_lifecycle, gated by
        # that module's own policy.
        assert "/gh" not in joined, at
        assert "/git" not in joined, at
        # Ensure no shell metacharacters at all.
        for ch in "|;&><`":
            assert ch not in joined, f"shell metachar {ch!r} in argv for {at}"


# ---------------------------------------------------------------------------
# Executor — fixed-command-only via injected runner
# ---------------------------------------------------------------------------


def test_executor_invokes_only_the_fixed_argv() -> None:
    captured: list[tuple[str, ...]] = []

    def fake_runner(argv, *, timeout):  # noqa: ARG001
        captured.append(tuple(argv))
        return (0, "{}", "")

    out = esc.execute_action(
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_SUCCEEDED
    assert captured == [esc._ACTION_ARGV[esc.ACTION_REFRESH_PROPOSAL_QUEUE]]


def test_executor_dependabot_requires_confirm_token() -> None:
    """The Dependabot execute-safe action must not run without the
    literal ``--confirm dependabot-execute-safe`` token."""
    captured: list[tuple[str, ...]] = []

    def fake_runner(argv, *, timeout):  # noqa: ARG001
        captured.append(tuple(argv))
        return (0, "{}", "")

    # Without confirm — must refuse.
    out = esc.execute_action(
        esc.ACTION_RUN_DEPENDABOT_EXECUTE_SAFE,
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_BLOCKED
    assert "confirm" in (out["result_summary"] or "").lower()
    assert captured == []

    # With wrong token — must refuse.
    out = esc.execute_action(
        esc.ACTION_RUN_DEPENDABOT_EXECUTE_SAFE,
        confirm_token="wrong-token",
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_BLOCKED
    assert captured == []

    # With correct token — should run.
    out = esc.execute_action(
        esc.ACTION_RUN_DEPENDABOT_EXECUTE_SAFE,
        confirm_token="dependabot-execute-safe",
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_SUCCEEDED
    assert captured == [esc._ACTION_ARGV[esc.ACTION_RUN_DEPENDABOT_EXECUTE_SAFE]]


def test_executor_blocks_when_planner_says_blocked() -> None:
    captured: list[tuple[str, ...]] = []

    def fake_runner(argv, *, timeout):  # noqa: ARG001
        captured.append(tuple(argv))
        return (0, "{}", "")

    out = esc.execute_action(
        esc.ACTION_REFRESH_PR_LIFECYCLE,
        git_status=(False, [" M something.py"], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_BLOCKED
    assert captured == [], "blocked plan must not invoke runner"


def test_executor_marks_subprocess_failure() -> None:
    def fake_runner(argv, *, timeout):  # noqa: ARG001
        return (1, "", "boom")

    out = esc.execute_action(
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_FAILED
    assert "exit code 1" in (out["result_summary"] or "")


def test_executor_detects_frozen_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a frozen-contract sha changes during action execution, the
    executor returns FAILED with a CRITICAL message — never silently
    accepts."""
    calls = {"n": 0}

    def fake_hashes() -> dict[str, str]:
        calls["n"] += 1
        # Return different content on second call to simulate drift.
        if calls["n"] == 1:
            return {f: "before" for f in esc.FROZEN_CONTRACTS}
        return {f: "AFTER_DRIFT" for f in esc.FROZEN_CONTRACTS}

    monkeypatch.setattr(esc, "_frozen_hashes", fake_hashes)

    def fake_runner(argv, *, timeout):  # noqa: ARG001
        return (0, "{}", "")

    out = esc.execute_action(
        esc.ACTION_REFRESH_PROPOSAL_QUEUE,
        git_status=(True, [], None),
        gh_status=_gh("available"),
        runner=fake_runner,
    )
    assert out["result_status"] == esc.RESULT_FAILED
    assert "FROZEN-CONTRACT DRIFT" in (out["result_summary"] or "")


# ---------------------------------------------------------------------------
# Catalog snapshot shape
# ---------------------------------------------------------------------------


def test_catalog_snapshot_has_required_top_level_fields() -> None:
    snap = esc.collect_catalog(
        git_status=(True, [], None),
        gh_status=_gh("available"),
    )
    required = {
        "schema_version",
        "report_kind",
        "module_version",
        "generated_at_utc",
        "git_clean",
        "git_dirty_count",
        "gh_provider",
        "frozen_hashes",
        "actions",
        "counts",
    }
    assert required.issubset(snap.keys())
    assert snap["schema_version"] == esc.SCHEMA_VERSION
    assert snap["report_kind"] == "execute_safe_controls_catalog"
    assert len(snap["actions"]) == len(esc.ACTION_TYPES)


def test_every_action_in_catalog_carries_required_fields() -> None:
    snap = esc.collect_catalog(
        git_status=(True, [], None),
        gh_status=_gh("available"),
    )
    required = {
        "action_id",
        "action_type",
        "title",
        "summary",
        "risk_class",
        "eligibility",
        "blocked_reason",
        "required_confirmations",
        "forbidden_side_effects",
        "allowed_side_effects",
        "source_refs",
        "created_at",
        "stale_after",
        "audit_event_id",
        "result_status",
        "result_summary",
        "output_artifact_path",
    }
    for a in snap["actions"]:
        assert required.issubset(a.keys())
        # Universal forbidden list is on every action.
        assert "git push origin main" in a["forbidden_side_effects"]
        assert "arbitrary shell command" in a["forbidden_side_effects"]


# ---------------------------------------------------------------------------
# Frozen-contract integrity around the catalog emit
# ---------------------------------------------------------------------------


def test_catalog_emit_does_not_mutate_frozen_contracts() -> None:
    paths = [REPO_ROOT / rel for rel in esc.FROZEN_CONTRACTS]
    before = {p.name: _file_sha256(p) for p in paths if p.exists()}
    esc.collect_catalog(git_status=(True, [], None), gh_status=_gh("available"))
    after = {p.name: _file_sha256(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(esc, "DIGEST_DIR_JSON", tmp_path / "esc")
    monkeypatch.setattr(
        esc,
        "_git_status_safe",
        lambda: (True, [], None),
    )
    monkeypatch.setattr(esc, "_gh_provider_status", lambda: _gh("available"))
    rc = esc.main(["--mode", "dry-run", "--no-write"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_kind"] == "execute_safe_controls_catalog"


# ---------------------------------------------------------------------------
# Static module invariants
# ---------------------------------------------------------------------------


def test_module_does_not_construct_argv_from_user_input() -> None:
    """Walk the module source and reject anything that would build an
    argv from the operator. This is a paranoia check — the runtime
    behavior is already exercised by the executor tests above."""
    src = Path(esc.__file__).read_text(encoding="utf-8")
    # The default runner uses subprocess.run(list(argv), ...) — that's the
    # only subprocess invocation in the module. No shell=True anywhere.
    assert "shell=True" not in src
    # No raw os.system / popen.
    assert "os.system" not in src
    assert "Popen(" not in src
    # No eval / exec.
    assert "eval(" not in src
    assert "exec(" not in src or src.count("exec(") <= 0


def test_no_action_argv_invokes_destructive_git_or_gh() -> None:
    """Belt-and-braces — same property as the per-action test above
    but on the global map."""
    for at, argv in esc._ACTION_ARGV.items():
        joined = " ".join(argv)
        for forbidden in (
            "git push",
            "--force",
            "--admin",
            "rm -rf",
            "shutdown",
        ):
            assert forbidden not in joined, f"{forbidden!r} found in {at}"
