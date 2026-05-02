"""Unit tests for ``reporting.github_pr_lifecycle``.

Covers every scenario the v3.15.15.17 brief enumerates:

* gh provider unavailable / unauthenticated / repo not detected /
  malformed output / permission-denied PR list.
* Dependabot LOW with CLEAN + green checks → ``merge_allowed``.
* Dependabot MEDIUM with CLEAN + green checks → ``merge_allowed``.
* Dependabot HIGH with CLEAN + green checks → ``blocked_high_risk``.
* BEHIND main → ``wait_for_rebase`` and proposed action.
* DIRTY → ``blocked_conflict``.
* Checks pending → ``wait_for_checks``.
* Checks failing → ``blocked_failing_checks``.
* Diff touches a protected path → ``blocked_protected_path``.
* Diff touches a frozen contract → ``blocked_protected_path``.
* Diff touches ``.claude/**`` → ``blocked_protected_path``.
* Unknown mergeStateStatus → ``blocked_unknown``.
* Non-Dependabot author → ``needs_human``.
* Non-main base → ``needs_human``.
* Draft → ``needs_human``.
* Dry-run does not mutate (no gh comment / merge calls).
* Execute-safe never calls direct ``git push main``.
* Execute-safe never merges HIGH (defensive re-check).
* Execute-safe calls squash-merge only for LOW / MEDIUM that passed
  every gate.
* JSON snapshot carries every required top-level key.
* Frozen contracts byte-identical before/after the snapshot run.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from reporting import github_pr_lifecycle as glp

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_pr(
    *,
    number: int = 49,
    title: str = "chore(ci)(deps): Bump gitleaks/gitleaks-action from 2.3.7 to 2.3.9",
    author: str = "app/dependabot",
    branch: str = "dependabot/github_actions/gitleaks/gitleaks-action-2.3.9",
    base: str = "main",
    merge_state: str = "CLEAN",
    is_draft: bool = False,
    files: list[str] | None = None,
    additions: int = 1,
    deletions: int = 1,
) -> dict:
    if files is None:
        files = [".github/workflows/tests.yml"]
    return {
        "number": number,
        "title": title,
        "author": {"login": author, "is_bot": True},
        "headRefName": branch,
        "baseRefName": base,
        "mergeStateStatus": merge_state,
        "isDraft": is_draft,
        "additions": additions,
        "deletions": deletions,
        "files": [{"path": p} for p in files],
        "url": f"https://example.invalid/pr/{number}",
    }


def _checks(state: str) -> list[dict]:
    """Build a checks list of the requested aggregate state.
    ``state`` is one of ``passed`` / ``pending`` / ``failed`` / ``unknown``."""
    if state == "passed":
        return [
            {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "tests", "status": "COMPLETED", "conclusion": "SUCCESS"},
        ]
    if state == "pending":
        return [
            {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "tests", "status": "IN_PROGRESS", "conclusion": ""},
        ]
    if state == "failed":
        return [
            {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "tests", "status": "COMPLETED", "conclusion": "FAILURE"},
        ]
    return []


# ---------------------------------------------------------------------------
# Provider probe
# ---------------------------------------------------------------------------


def test_provider_status_when_gh_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: None)
    status = glp.gh_provider_status()
    assert status["status"] == "not_available"
    assert status["gh_path"] is None
    assert status["account"] is None


def test_provider_status_when_gh_version_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")
    monkeypatch.setattr(glp, "_run", lambda cmd, **kw: (1, "", "boom"))
    status = glp.gh_provider_status()
    assert status["status"] == "not_available"


def test_provider_status_unauthenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kw):
        calls.append(cmd)
        if cmd[1:] == ["--version"]:
            return (0, "gh version 2.92.0\n", "")
        if cmd[1:3] == ["auth", "status"]:
            return (1, "", "not logged in")
        return (0, "", "")

    monkeypatch.setattr(glp, "_run", fake_run)
    status = glp.gh_provider_status()
    assert status["status"] == "not_authenticated"
    assert status["version"].startswith("gh version")


def test_provider_status_repo_not_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")

    def fake_run(cmd: list[str], **kw):
        if cmd[1:] == ["--version"]:
            return (0, "gh version 2.92.0\n", "")
        if cmd[1:3] == ["auth", "status"]:
            return (0, "Logged in to github.com account roudjy\n", "")
        if cmd[1:3] == ["repo", "view"]:
            return (1, "", "no remote")
        return (0, "", "")

    monkeypatch.setattr(glp, "_run", fake_run)
    status = glp.gh_provider_status()
    assert status["status"] == "repo_not_detected"
    assert status["account"] == "roudjy"


def test_provider_status_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")

    def fake_run(cmd: list[str], **kw):
        if cmd[1:] == ["--version"]:
            return (0, "gh version 2.92.0\n", "")
        if cmd[1:3] == ["auth", "status"]:
            return (0, "Logged in to github.com account roudjy\n", "")
        if cmd[1:3] == ["repo", "view"]:
            return (0, "roudjy/trading-agent\n", "")
        return (0, "", "")

    monkeypatch.setattr(glp, "_run", fake_run)
    status = glp.gh_provider_status()
    assert status["status"] == "available"
    assert status["repo"] == "roudjy/trading-agent"


def test_list_open_prs_handles_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")
    monkeypatch.setattr(glp, "_run", lambda cmd, **kw: (0, "not json", ""))
    prs, err = glp.list_open_prs()
    assert prs == []
    assert err is not None
    assert "malformed" in err


def test_list_open_prs_handles_permission_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glp, "_gh_path", lambda: "/fake/gh")
    monkeypatch.setattr(glp, "_run", lambda cmd, **kw: (1, "", "permission denied"))
    prs, err = glp.list_open_prs()
    assert prs == []
    assert err is not None


# ---------------------------------------------------------------------------
# Risk classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,branch,files,expected",
    [
        # GH Actions patch — workflow-only — LOW.
        (
            "chore(ci)(deps): Bump gitleaks/gitleaks-action from 2.3.7 to 2.3.9",
            "dependabot/github_actions/gitleaks/gitleaks-action-2.3.9",
            [".github/workflows/tests.yml"],
            glp.RISK_LOW,
        ),
        # GH Actions 0.x minor on workflow file — MEDIUM.
        (
            "chore(ci)(deps): Bump aquasecurity/trivy-action from 0.24.0 to 0.36.0",
            "dependabot/github_actions/aquasecurity/trivy-action-0.36.0",
            [".github/workflows/docker-build.yml"],
            glp.RISK_MEDIUM,
        ),
        # Python pip floor bump on requirements.txt — MEDIUM.
        (
            "chore(deps)(deps): Update loguru requirement from >=0.7.0 to >=0.7.3",
            "dependabot/pip/loguru-gte-0.7.3",
            ["requirements.txt"],
            glp.RISK_MEDIUM,
        ),
    ],
)
def test_classify_low_or_medium(title, branch, files, expected) -> None:
    pr = _make_pr(title=title, branch=branch, files=files)
    cls, _, _ = glp.classify_pr(pr, files)
    assert cls == expected


@pytest.mark.parametrize(
    "title,branch,files,reason_token",
    [
        # numpy is on the HIGH list regardless of bump shape.
        (
            "chore(deps)(deps): Update numpy requirement from >=1.24.0 to >=1.26.4",
            "dependabot/pip/numpy-gte-1.26.4",
            ["requirements.txt"],
            "HIGH-risk list",
        ),
        # Major-version bump on a non-listed package.
        (
            "chore(ci)(deps): Bump docker/login-action from 3.3.0 to 4.1.0",
            "dependabot/github_actions/docker/login-action-4.1.0",
            [".github/workflows/docker-build.yml"],
            "major-version bump",
        ),
        # Diff touches a frozen contract.
        (
            "chore(deps)(deps): would touch contract",
            "dependabot/pip/whatever-1.0.0",
            ["research/research_latest.json"],
            "protected path",
        ),
        # Diff touches .claude/.
        (
            "chore: hooks bump",
            "dependabot/whatever",
            [".claude/hooks/audit_emit.py"],
            "protected path",
        ),
        # Diff touches Dockerfile (protected globs catch this first).
        (
            "chore: docker base bump",
            "dependabot/whatever",
            ["Dockerfile"],
            "protected path",
        ),
        # Diff touches docker-compose (non-prod) — caught by the
        # explicit Docker-runtime branch (path-side, not title-side).
        # Title is intentionally generic so the title-token branch
        # does not fire first.
        (
            "chore: bump base image",
            "dependabot/whatever",
            ["docker-compose.yml"],
            "Docker runtime artifact",
        ),
    ],
)
def test_classify_high(title, branch, files, reason_token) -> None:
    pr = _make_pr(title=title, branch=branch, files=files)
    cls, reason, _ = glp.classify_pr(pr, files)
    assert cls == glp.RISK_HIGH
    assert reason_token in reason


def test_protected_path_detection_covers_dot_env() -> None:
    # The .env / .env.* globs must register as protected.
    touched, hit = glp.diff_touches_protected([".env"])
    assert touched and hit == ".env"
    touched2, hit2 = glp.diff_touches_protected([".env.production"])
    assert touched2


def test_live_path_detection_blocks_trading_flow() -> None:
    touched, hit = glp.diff_touches_live_or_trading(["agent/execution/live/broker.py"])
    assert touched and "live" in hit


# ---------------------------------------------------------------------------
# Aggregate-checks reducer
# ---------------------------------------------------------------------------


def test_aggregate_checks_passed() -> None:
    assert glp.aggregate_checks(_checks("passed")) == "passed"


def test_aggregate_checks_pending() -> None:
    assert glp.aggregate_checks(_checks("pending")) == "pending"


def test_aggregate_checks_failed() -> None:
    assert glp.aggregate_checks(_checks("failed")) == "failed"


def test_aggregate_checks_unknown_when_empty() -> None:
    # The deliberate property: empty checks list → UNKNOWN, never
    # assume green.
    assert glp.aggregate_checks([]) == "unknown"


def test_aggregate_checks_treats_unknown_conclusion_as_unknown() -> None:
    out = glp.aggregate_checks(
        [{"name": "x", "status": "COMPLETED", "conclusion": "WEIRD"}]
    )
    assert out == "unknown"


# ---------------------------------------------------------------------------
# Decision planner
# ---------------------------------------------------------------------------


def _decide(
    *,
    pr=None,
    files=None,
    checks=None,
    risk_class=glp.RISK_LOW,
    risk_reason="LOW: ok",
    baseline_ok=True,
):
    pr = pr or _make_pr()
    files = files if files is not None else [".github/workflows/tests.yml"]
    checks = checks if checks is not None else _checks("passed")
    return glp.decide_for_pr(
        pr,
        files,
        checks,
        risk_class=risk_class,
        risk_reason=risk_reason,
        baseline_ok=baseline_ok,
    )


def test_low_clean_passed_yields_merge_allowed() -> None:
    d = _decide()
    assert d["decision"] == "merge_allowed"
    assert d["actions_proposed"] == ["squash_merge"]


def test_medium_clean_passed_yields_merge_allowed() -> None:
    d = _decide(risk_class=glp.RISK_MEDIUM, risk_reason="MEDIUM: ok")
    assert d["decision"] == "merge_allowed"


def test_high_clean_passed_yields_blocked_high_risk() -> None:
    d = _decide(risk_class=glp.RISK_HIGH, risk_reason="numpy major")
    assert d["decision"] == "blocked_high_risk"
    assert "HIGH" in d["reason"]
    assert d["actions_proposed"] == []


def test_behind_main_yields_wait_for_rebase() -> None:
    pr = _make_pr(merge_state="BEHIND")
    d = _decide(pr=pr)
    assert d["decision"] == "wait_for_rebase"
    assert d["actions_proposed"] == ["comment_dependabot_rebase"]


def test_dirty_conflict_yields_blocked_conflict() -> None:
    pr = _make_pr(merge_state="DIRTY")
    d = _decide(pr=pr)
    assert d["decision"] == "blocked_conflict"


def test_pending_checks_yield_wait_for_checks() -> None:
    d = _decide(checks=_checks("pending"))
    assert d["decision"] == "wait_for_checks"


def test_failing_checks_yield_blocked_failing_checks() -> None:
    d = _decide(checks=_checks("failed"))
    assert d["decision"] == "blocked_failing_checks"


def test_protected_path_yields_blocked_protected_path() -> None:
    pr = _make_pr(files=[".claude/hooks/audit_emit.py"])
    d = _decide(pr=pr, files=[".claude/hooks/audit_emit.py"])
    assert d["decision"] == "blocked_protected_path"


def test_frozen_contract_yields_blocked_protected_path() -> None:
    pr = _make_pr(files=["research/research_latest.json"])
    d = _decide(pr=pr, files=["research/research_latest.json"])
    assert d["decision"] == "blocked_protected_path"


def test_live_trading_path_yields_blocked_protected_path() -> None:
    pr = _make_pr(files=["execution/live/broker.py"])
    d = _decide(pr=pr, files=["execution/live/broker.py"])
    assert d["decision"] == "blocked_protected_path"


def test_unknown_merge_state_yields_blocked_unknown() -> None:
    pr = _make_pr(merge_state="UNKNOWN")
    d = _decide(pr=pr)
    assert d["decision"] == "blocked_unknown"


def test_non_dependabot_author_yields_needs_human() -> None:
    pr = _make_pr(author="some-human-developer")
    d = _decide(pr=pr)
    assert d["decision"] == "needs_human"


def test_non_main_base_yields_needs_human() -> None:
    pr = _make_pr(base="release-2026")
    d = _decide(pr=pr)
    assert d["decision"] == "needs_human"


def test_draft_yields_needs_human() -> None:
    pr = _make_pr(is_draft=True)
    d = _decide(pr=pr)
    assert d["decision"] == "needs_human"


def test_baseline_not_ok_yields_needs_human() -> None:
    d = _decide(baseline_ok=False)
    assert d["decision"] == "needs_human"
    assert "baseline" in d["reason"]


# ---------------------------------------------------------------------------
# Snapshot — JSON shape and invariants
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect digest dir to ``tmp_path`` and pin the provider to
    available so the snapshot can be exercised end-to-end without a
    real ``gh``."""
    monkeypatch.setattr(glp, "DIGEST_DIR_JSON", tmp_path / "log_dir")
    return tmp_path


def _stub_provider_available() -> dict:
    return {
        "status": "available",
        "gh_path": "/fake/gh",
        "version": "gh version 2.92.0",
        "account": "roudjy",
        "repo": "roudjy/trading-agent",
    }


def _baseline_ok() -> dict:
    return {
        "governance_lint": {"ok": True, "summary": "Governance lint OK"},
        "smoke_tests": {"ok": True, "summary": "14 passed"},
        "frozen_hashes": {p: "0" * 64 for p in glp.FROZEN_CONTRACTS},
        "all_ok": True,
    }


def test_snapshot_top_level_shape(isolated_lifecycle: Path) -> None:
    snap = glp.collect_snapshot(
        mode="dry-run",
        provider=_stub_provider_available(),
        prs_override=[],
        baseline_override=_baseline_ok(),
    )
    required = {
        "schema_version",
        "report_kind",
        "module_version",
        "generated_at_utc",
        "repo",
        "provider_status",
        "provider",
        "mode",
        "baseline_status",
        "baseline",
        "frozen_hashes",
        "prs",
        "actions_taken",
        "final_recommendation",
    }
    assert required.issubset(snap.keys())
    assert snap["schema_version"] == 1
    assert snap["report_kind"] == "github_pr_lifecycle_digest"
    assert snap["mode"] == "dry-run"
    assert snap["baseline_status"] == "ok"
    assert snap["final_recommendation"] == "no_open_prs"


def test_snapshot_when_provider_unavailable() -> None:
    snap = glp.collect_snapshot(
        mode="dry-run",
        provider={"status": "not_available", "gh_path": None},
        prs_override=[],
        baseline_override=_baseline_ok(),
    )
    assert snap["provider_status"] == "not_available"
    assert snap["final_recommendation"] == "provider_not_available"
    assert snap["prs"] == []


def test_snapshot_when_baseline_blocked() -> None:
    bad = {
        "governance_lint": {"ok": False, "summary": "fail"},
        "smoke_tests": {"ok": True, "summary": "ok"},
        "frozen_hashes": {p: "0" * 64 for p in glp.FROZEN_CONTRACTS},
        "all_ok": False,
    }
    snap = glp.collect_snapshot(
        mode="dry-run",
        provider=_stub_provider_available(),
        prs_override=[],
        baseline_override=bad,
    )
    assert snap["baseline_status"] == "blocked"
    assert snap["final_recommendation"] == "baseline_not_green"


def test_snapshot_pr_rows_carry_all_required_fields() -> None:
    pr = _make_pr()

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    snap = glp.collect_snapshot(
        mode="dry-run",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )
    assert len(snap["prs"]) == 1
    row = snap["prs"][0]
    required = {
        "number",
        "title",
        "author",
        "base",
        "branch",
        "url",
        "package",
        "risk_class",
        "risk_reason",
        "merge_state",
        "checks_state",
        "protected_paths_touched",
        "files_count",
        "additions",
        "deletions",
        "decision",
        "reason",
        "actions_taken",
    }
    assert required.issubset(row.keys())


# ---------------------------------------------------------------------------
# Mutation guarantees
# ---------------------------------------------------------------------------


def test_dry_run_does_not_invoke_comment_or_merge() -> None:
    """The pure planner builds the snapshot without performing any
    mutating action even when a row is ``merge_allowed``."""
    pr = _make_pr(merge_state="CLEAN")

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    snap = glp.collect_snapshot(
        mode="dry-run",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )
    # In dry-run the runner is never invoked → no actions recorded.
    assert snap["actions_taken"] == []
    assert all(r["actions_taken"] == [] for r in snap["prs"])


def test_execute_safe_squash_merges_only_low_or_medium_with_all_gates_green() -> None:
    pr = _make_pr(merge_state="CLEAN")  # LOW workflow-only diff

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    snap = glp.collect_snapshot(
        mode="execute-safe",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )
    merge_calls: list[int] = []
    comment_calls: list[int] = []

    def do_comment(n):
        comment_calls.append(n)
        return (True, None)

    def do_merge(n):
        merge_calls.append(n)
        return (True, None)

    out = glp.execute_safe_actions(snap, do_comment=do_comment, do_merge=do_merge)
    assert merge_calls == [pr["number"]]
    assert comment_calls == []
    assert any(
        a["kind"] == "merge_squash" and a["outcome"] == "ok"
        for a in out["actions_taken"]
    )


def test_execute_safe_never_merges_high() -> None:
    # numpy is HIGH regardless of bump shape.
    pr = _make_pr(
        title="chore(deps)(deps): Update numpy requirement from >=1.24.0 to >=1.26.4",
        branch="dependabot/pip/numpy-gte-1.26.4",
        files=["requirements.txt"],
        merge_state="CLEAN",
    )

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    snap = glp.collect_snapshot(
        mode="execute-safe",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )
    # The planner already set decision=blocked_high_risk.
    assert snap["prs"][0]["decision"] == "blocked_high_risk"

    merge_calls: list[int] = []

    def do_merge(n):
        merge_calls.append(n)
        return (True, None)

    out = glp.execute_safe_actions(snap, do_comment=lambda n: (True, None), do_merge=do_merge)
    assert merge_calls == [], "execute-safe must never merge a HIGH PR"
    # And we never recorded a successful merge action.
    assert not any(
        a["kind"] == "merge_squash" and a["outcome"] == "ok"
        for a in out["actions_taken"]
    )


def test_execute_safe_comments_rebase_for_behind_only_under_clean_baseline() -> None:
    pr = _make_pr(merge_state="BEHIND")

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    snap = glp.collect_snapshot(
        mode="execute-safe",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )

    comment_calls: list[int] = []
    merge_calls: list[int] = []

    def do_comment(n):
        comment_calls.append(n)
        return (True, None)

    def do_merge(n):
        merge_calls.append(n)
        return (True, None)

    out = glp.execute_safe_actions(snap, do_comment=do_comment, do_merge=do_merge)
    assert comment_calls == [pr["number"]]
    assert merge_calls == []
    assert any(
        a["kind"] == "comment_dependabot_rebase" for a in out["actions_taken"]
    )


def test_execute_safe_aborts_when_baseline_not_ok() -> None:
    pr = _make_pr(merge_state="CLEAN")

    def fake_inspect(n):
        return (pr, None)

    def fake_checks(n):
        return (_checks("passed"), None)

    bad_baseline = {
        "governance_lint": {"ok": False, "summary": "fail"},
        "smoke_tests": {"ok": True, "summary": "ok"},
        "frozen_hashes": {p: "0" * 64 for p in glp.FROZEN_CONTRACTS},
        "all_ok": False,
    }
    snap = glp.collect_snapshot(
        mode="execute-safe",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=bad_baseline,
        fetch_inspect=fake_inspect,
        fetch_checks=fake_checks,
    )

    merge_calls: list[int] = []
    comment_calls: list[int] = []

    out = glp.execute_safe_actions(
        snap,
        do_comment=lambda n: (comment_calls.append(n), (True, None))[1],
        do_merge=lambda n: (merge_calls.append(n), (True, None))[1],
    )
    assert merge_calls == []
    assert comment_calls == []
    assert any(a["kind"] == "abort" for a in out["actions_taken"])


def test_execute_safe_never_calls_git_push_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute-safe must never invoke ``git push origin main`` (or
    any ``git push main``-shaped command).  We monkeypatch ``_run`` to
    record every subprocess and assert no ``git push main``-shaped
    invocation happens during a full execute-safe cycle.
    """
    seen_cmds: list[list[str]] = []

    def recorder(cmd, **kw):
        seen_cmds.append(list(cmd))
        # Pretend gh always succeeds.
        if cmd and cmd[0].endswith("gh"):
            return (0, "{}", "")
        return (0, "", "")

    monkeypatch.setattr(glp, "_run", recorder)
    pr = _make_pr(merge_state="CLEAN")
    snap = glp.collect_snapshot(
        mode="execute-safe",
        provider=_stub_provider_available(),
        prs_override=[pr],
        baseline_override=_baseline_ok(),
        fetch_inspect=lambda n: (pr, None),
        fetch_checks=lambda n: (_checks("passed"), None),
    )
    # Run the actions through the *real* ``merge_squash`` path so we
    # exercise the gh wrapper, but ``_run`` is intercepted.
    glp.execute_safe_actions(snap)
    for cmd in seen_cmds:
        joined = " ".join(cmd)
        assert "git push" not in joined, f"unexpected git push: {joined}"
        assert "force" not in joined, f"unexpected force-push: {joined}"
        assert "--admin" not in joined, f"unexpected --admin merge: {joined}"


# ---------------------------------------------------------------------------
# Frozen contract integrity
# ---------------------------------------------------------------------------


def test_frozen_contracts_byte_identical_around_snapshot(
    isolated_lifecycle: Path,
) -> None:
    """The snapshot run must not mutate frozen contract files."""
    paths = [
        REPO_ROOT / "research" / "research_latest.json",
        REPO_ROOT / "research" / "strategy_matrix.csv",
    ]
    before = {p.name: _file_sha256(p) for p in paths if p.exists()}

    glp.collect_snapshot(
        mode="dry-run",
        provider=_stub_provider_available(),
        prs_override=[],
        baseline_override=_baseline_ok(),
    )

    after = {p.name: _file_sha256(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# CLI thin-shim
# ---------------------------------------------------------------------------


def test_cli_dry_run_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        glp, "collect_snapshot",
        lambda **kw: {
            "schema_version": 1,
            "report_kind": "github_pr_lifecycle_digest",
            "module_version": glp.MODULE_VERSION,
            "generated_at_utc": "2026-05-02T12:00:00Z",
            "repo": "test/repo",
            "provider_status": "available",
            "provider": {"status": "available"},
            "mode": kw.get("mode", "dry-run"),
            "baseline_status": "ok",
            "baseline": _baseline_ok(),
            "frozen_hashes": {p: "0" * 64 for p in glp.FROZEN_CONTRACTS},
            "prs": [],
            "actions_taken": [],
            "final_recommendation": "no_open_prs",
        },
    )
    rc = glp.main(["--mode", "dry-run", "--no-write"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["report_kind"] == "github_pr_lifecycle_digest"
    assert payload["mode"] == "dry-run"


def test_cli_execute_safe_routes_through_runner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocations: list[str] = []

    def fake_collect(**kw):
        invocations.append(f"collect:{kw.get('mode')}")
        return {
            "schema_version": 1,
            "report_kind": "github_pr_lifecycle_digest",
            "module_version": glp.MODULE_VERSION,
            "generated_at_utc": "2026-05-02T12:00:00Z",
            "repo": "test/repo",
            "provider_status": "available",
            "provider": {"status": "available"},
            "mode": kw.get("mode", "execute-safe"),
            "baseline_status": "ok",
            "baseline": _baseline_ok(),
            "frozen_hashes": {p: "0" * 64 for p in glp.FROZEN_CONTRACTS},
            "prs": [],
            "actions_taken": [],
            "final_recommendation": "no_open_prs",
        }

    def fake_runner(snapshot, **kw):
        invocations.append("runner")
        snapshot["actions_taken"].append({"kind": "noop", "outcome": "ok"})
        return snapshot

    monkeypatch.setattr(glp, "collect_snapshot", fake_collect)
    monkeypatch.setattr(glp, "execute_safe_actions", fake_runner)
    rc = glp.main(["--mode", "execute-safe", "--no-write"])
    assert rc == 0
    assert "collect:execute-safe" in invocations
    assert "runner" in invocations
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "execute-safe"
    assert any(a["kind"] == "noop" for a in payload["actions_taken"])
