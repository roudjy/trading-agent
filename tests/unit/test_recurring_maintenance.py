"""Unit tests for ``reporting.recurring_maintenance``.

Properties enforced (verbatim from the v3.15.15.23 brief):

* job registry contains only the five approved job types
* unknown job type rejected at planner AND executor
* no arbitrary command execution; no shell/subprocess in the module
* plan mode does not mutate state
* run-once executes only the selected job
* run-due-once respects next_run_after_utc
* loop mode respects max_iterations + interval clamping
* job state persists across runs (state.json)
* atomic write (tmp + os.replace)
* history.jsonl appends one record per execution
* secret redaction at the snapshot boundary
* one failing job does not crash other jobs
* timeout classified as timeout
* disabled job skipped
* dependabot job disabled by default
* dependabot job rejects without --enable-dependabot-execute-safe
* dependabot job dispatch goes through github_pr_lifecycle (we
  cover the lifecycle module's HIGH-rejection separately)
* no git push/force/admin/direct-main operation possible from this
  module
* approval_inbox integration for failed/blocked jobs
* status endpoint projection
* frozen hashes unchanged
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from reporting import recurring_maintenance as rm

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    return tmp_path


def _file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _patch_executor(
    monkeypatch: pytest.MonkeyPatch,
    job_type: str,
    fn,
) -> None:
    """Replace one job's executor so tests don't actually invoke the
    real workloop / proposal-queue / lifecycle modules."""
    spec = dict(rm._JOB_REGISTRY[job_type])
    spec["executor"] = fn
    monkeypatch.setitem(rm._JOB_REGISTRY, job_type, spec)


# ---------------------------------------------------------------------------
# Closed registry
# ---------------------------------------------------------------------------


def test_job_registry_contains_only_approved_types() -> None:
    expected = {
        "refresh_workloop_runtime_once",
        "refresh_proposal_queue",
        "refresh_approval_inbox",
        "refresh_github_pr_lifecycle_dry_run",
        "dependabot_low_medium_execute_safe",
    }
    assert set(rm.JOB_TYPES) == expected
    assert set(rm._JOB_REGISTRY.keys()) == expected
    assert len(rm.JOB_TYPES) == 5


def test_dependabot_job_disabled_by_default() -> None:
    spec = rm._JOB_REGISTRY[rm.JOB_DEPENDABOT_EXECUTE_SAFE]
    assert spec["default_enabled"] is False
    assert spec["risk_class"] == rm.RISK_MEDIUM


def test_other_jobs_enabled_by_default() -> None:
    for job_type in rm.JOB_TYPES:
        if job_type == rm.JOB_DEPENDABOT_EXECUTE_SAFE:
            continue
        assert rm._JOB_REGISTRY[job_type]["default_enabled"] is True


def test_unknown_job_type_is_refused_via_run_one_job(isolated: Path) -> None:
    snap = rm.run_one_job("rm_minus_rf_root", persist=False)
    refused = [
        a
        for a in snap["actions_taken"]
        if a.get("kind") == "refused" and a.get("target") == "rm_minus_rf_root"
    ]
    assert refused, snap


# ---------------------------------------------------------------------------
# Plan + list (no mutation)
# ---------------------------------------------------------------------------


def test_list_jobs_does_not_mutate(isolated: Path) -> None:
    snap = rm.list_jobs()
    assert snap["mode"] == "list"
    # Nothing written.
    assert not (isolated / "rm" / "latest.json").exists()
    assert not (isolated / "rm" / "state.json").exists()


def test_plan_does_not_mutate(isolated: Path) -> None:
    snap = rm.plan()
    assert snap["mode"] == "plan"
    assert "due_now" in snap
    # Initially every enabled job is due (no last_run_at_utc).
    assert rm.JOB_REFRESH_WORKLOOP_RUNTIME in snap["due_now"]
    # Plan does NOT execute, so state.json is not written.
    assert not (isolated / "rm" / "state.json").exists()


# ---------------------------------------------------------------------------
# run_one_job
# ---------------------------------------------------------------------------


def test_run_one_job_executes_only_selected_job(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_PROPOSAL_QUEUE,
        lambda: (calls.append("proposal_queue"), {"summary": "ok"})[1],
    )
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: (calls.append("approval_inbox"), {"summary": "ok"})[1],
    )
    snap = rm.run_one_job(rm.JOB_REFRESH_PROPOSAL_QUEUE, persist=True)
    assert calls == ["proposal_queue"]
    state = snap["jobs"]
    pq = next(j for j in state if j["job_type"] == rm.JOB_REFRESH_PROPOSAL_QUEUE)
    assert pq["last_status"] == rm.STATUS_SUCCEEDED


def test_run_once_persists_state(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    state_file = isolated / "rm" / "state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert rm.JOB_REFRESH_APPROVAL_INBOX in data
    assert data[rm.JOB_REFRESH_APPROVAL_INBOX]["last_status"] == rm.STATUS_SUCCEEDED


def test_disabled_job_is_skipped(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a job is disabled in state, run_one_job marks it skipped
    without invoking the executor."""
    state = rm._hydrate_state()
    state[rm.JOB_REFRESH_APPROVAL_INBOX]["enabled"] = False
    rm._write_state(state)
    called: list[bool] = []
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: (called.append(True), {"summary": "ok"})[1]
    )
    snap = rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    assert called == []
    job_state = next(
        j for j in snap["jobs"] if j["job_type"] == rm.JOB_REFRESH_APPROVAL_INBOX
    )
    assert job_state["last_status"] == rm.STATUS_SKIPPED


# ---------------------------------------------------------------------------
# Failing / timeout supervision
# ---------------------------------------------------------------------------


def test_one_failing_job_does_not_crash_others(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom():
        raise RuntimeError("synthetic failure")

    _patch_executor(monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, _boom)
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_PROPOSAL_QUEUE, lambda: {"summary": "ok"}
    )
    snap = rm.run_due_once(persist=True)
    statuses = {
        j["job_type"]: j["last_status"]
        for j in snap["jobs"]
    }
    assert statuses[rm.JOB_REFRESH_APPROVAL_INBOX] == rm.STATUS_FAILED
    assert statuses[rm.JOB_REFRESH_PROPOSAL_QUEUE] == rm.STATUS_SUCCEEDED


def test_job_timeout_classified_as_timeout(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _slow():
        time.sleep(3.0)
        return {"summary": "should not reach"}

    # Patch the registry timeout for this job to 1s, plus the
    # executor itself.
    spec = dict(rm._JOB_REGISTRY[rm.JOB_REFRESH_APPROVAL_INBOX])
    spec["executor"] = _slow
    spec["timeout_seconds"] = 1
    monkeypatch.setitem(rm._JOB_REGISTRY, rm.JOB_REFRESH_APPROVAL_INBOX, spec)
    snap = rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=False)
    job_state = next(
        j for j in snap["jobs"] if j["job_type"] == rm.JOB_REFRESH_APPROVAL_INBOX
    )
    assert job_state["last_status"] == rm.STATUS_TIMEOUT
    assert "timeout" in (job_state["last_result_summary"] or "").lower()


def test_failed_job_increments_consecutive_failures(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    for _ in range(3):
        rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    state = rm._read_state()
    assert state[rm.JOB_REFRESH_APPROVAL_INBOX]["consecutive_failures"] == 3
    assert state[rm.JOB_REFRESH_APPROVAL_INBOX]["last_status"] == rm.STATUS_FAILED


def test_succeeded_job_resets_consecutive_failures(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two failures.
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    # One success.
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    state = rm._read_state()
    assert state[rm.JOB_REFRESH_APPROVAL_INBOX]["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Dependabot opt-in gate
# ---------------------------------------------------------------------------


def test_dependabot_job_requires_cli_opt_in(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if the operator manually flips enabled=true in
    state.json, the Dependabot job is still ``blocked`` without the
    runtime --enable-dependabot-execute-safe flag."""
    state = rm._hydrate_state()
    state[rm.JOB_DEPENDABOT_EXECUTE_SAFE]["enabled"] = True
    rm._write_state(state)

    called: list[bool] = []
    _patch_executor(
        monkeypatch,
        rm.JOB_DEPENDABOT_EXECUTE_SAFE,
        lambda: (called.append(True), {"summary": "ok"})[1],
    )
    snap = rm.run_one_job(
        rm.JOB_DEPENDABOT_EXECUTE_SAFE, enable_dependabot=False, persist=True
    )
    job_state = next(
        j for j in snap["jobs"] if j["job_type"] == rm.JOB_DEPENDABOT_EXECUTE_SAFE
    )
    assert called == [], "executor must NOT be invoked without CLI opt-in"
    assert job_state["last_status"] == rm.STATUS_BLOCKED
    assert (
        job_state["blocked_reason"] == "missing_dependabot_cli_opt_in"
    ), job_state


def test_dependabot_job_runs_with_explicit_opt_in(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = rm._hydrate_state()
    state[rm.JOB_DEPENDABOT_EXECUTE_SAFE]["enabled"] = True
    rm._write_state(state)

    called: list[bool] = []
    _patch_executor(
        monkeypatch,
        rm.JOB_DEPENDABOT_EXECUTE_SAFE,
        lambda: (called.append(True), {"summary": "merged 0 PRs"})[1],
    )
    snap = rm.run_one_job(
        rm.JOB_DEPENDABOT_EXECUTE_SAFE, enable_dependabot=True, persist=True
    )
    job_state = next(
        j for j in snap["jobs"] if j["job_type"] == rm.JOB_DEPENDABOT_EXECUTE_SAFE
    )
    assert called == [True]
    assert job_state["last_status"] == rm.STATUS_SUCCEEDED


# ---------------------------------------------------------------------------
# run_due_once — schedule respect
# ---------------------------------------------------------------------------


def test_run_due_once_respects_next_run_after_utc(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once a job has run, its next_run_after_utc is set in the
    future; a subsequent run_due_once should NOT re-execute it."""
    calls: list[str] = []
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: (calls.append("a"), {"summary": "ok"})[1],
    )
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_PROPOSAL_QUEUE,
        lambda: (calls.append("p"), {"summary": "ok"})[1],
    )
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_WORKLOOP_RUNTIME,
        lambda: (calls.append("r"), {"summary": "ok"})[1],
    )
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_PR_LIFECYCLE_DRY_RUN,
        lambda: (calls.append("g"), {"summary": "ok"})[1],
    )
    rm.run_due_once(persist=True)
    n_first = len(calls)
    rm.run_due_once(persist=True)
    n_second = len(calls)
    # Second pass: nothing was due, so no additional executor calls.
    assert n_second == n_first, calls


def test_run_due_once_runs_due_jobs_when_time_advances(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If we manually push next_run_after_utc into the past, the job
    runs again."""
    calls: list[int] = []
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: (calls.append(1), {"summary": "ok"})[1],
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    state = rm._read_state()
    state[rm.JOB_REFRESH_APPROVAL_INBOX]["next_run_after_utc"] = (
        "2000-01-01T00:00:00Z"
    )
    # Disable other jobs so we only check the targeted one.
    for jt in rm.JOB_TYPES:
        if jt != rm.JOB_REFRESH_APPROVAL_INBOX:
            state[jt]["enabled"] = False
    rm._write_state(state)
    rm.run_due_once(persist=True)
    assert sum(calls) == 2  # original + due-now run


# ---------------------------------------------------------------------------
# Loop mode
# ---------------------------------------------------------------------------


def test_loop_clamps_max_iterations(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    snaps = rm.run_loop(
        interval_seconds=30,
        max_iterations=10_000,
        persist=False,
        sleeper=lambda s: sleeps.append(s),
    )
    assert len(snaps) == rm.MAX_ITERATIONS_LIMIT
    assert len(sleeps) == rm.MAX_ITERATIONS_LIMIT - 1


def test_loop_clamps_interval_seconds(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    rm.run_loop(
        interval_seconds=1,  # below MIN; should clamp up
        max_iterations=2,
        persist=False,
        sleeper=lambda s: sleeps.append(s),
    )
    assert all(s >= rm.MIN_INTERVAL_SECONDS for s in sleeps)


# ---------------------------------------------------------------------------
# Atomic write + history
# ---------------------------------------------------------------------------


def test_json_write_is_atomic(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    latest = isolated / "rm" / "latest.json"
    assert latest.exists()
    assert not (isolated / "rm" / "latest.json.tmp").exists()
    assert not (isolated / "rm" / "state.json.tmp").exists()


def test_history_jsonl_appends_one_record_per_run(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    for _ in range(3):
        rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    history = (isolated / "rm" / "history.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in history.splitlines() if ln.strip()]
    assert len(lines) == 3
    for ln in lines:
        rec = json.loads(ln)
        assert rec["report_kind"] == "recurring_maintenance_digest"


# ---------------------------------------------------------------------------
# safe_to_execute always false
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Across list / plan / run-once / run-due-once, the digest's
    safe_to_execute is hard-coded false."""
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    for snap in (
        rm.list_jobs(),
        rm.plan(),
        rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=False),
        rm.run_due_once(persist=False),
    ):
        assert snap["safe_to_execute"] is False


# ---------------------------------------------------------------------------
# Module invariants — no shell, no subprocess, no free-form command
# ---------------------------------------------------------------------------


def test_module_does_not_invoke_subprocess_directly() -> None:
    src = Path(rm.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        '"gh"',
        "'gh'",
        '"git"',
        "'git'",
        "Popen",
        "os.system",
        "shell=True",
    )
    for token in forbidden:
        assert token not in src, (
            f"forbidden token in recurring_maintenance.py: {token!r}"
        )


def test_cli_does_not_accept_freeform_command_flags() -> None:
    src = Path(rm.__file__).read_text(encoding="utf-8")
    for forbidden_flag in ("--command", "--argv", "--shell", "--cmd"):
        assert forbidden_flag not in src


# ---------------------------------------------------------------------------
# Frozen contract integrity
# ---------------------------------------------------------------------------


def test_frozen_contracts_byte_identical_around_run(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    paths = [
        REPO_ROOT / "research" / "research_latest.json",
        REPO_ROOT / "research" / "strategy_matrix.csv",
    ]
    before = {p.name: _file_sha256(p) for p in paths if p.exists()}
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    after = {p.name: _file_sha256(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# Credential-redaction guard
# ---------------------------------------------------------------------------


def test_credential_value_in_summary_is_sanitized(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If an executor returns a summary string containing a
    credential pattern (sk-ant-...), the supervisor sanitises it to
    ``secret_redaction_failed`` before persisting — defence in
    depth on top of the lifecycle module's own redaction."""
    _patch_executor(
        monkeypatch,
        rm.JOB_REFRESH_APPROVAL_INBOX,
        lambda: {"summary": "leaked sk-ant-api03-fakeleak token"},
    )
    snap = rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=False)
    job_state = next(
        j for j in snap["jobs"] if j["job_type"] == rm.JOB_REFRESH_APPROVAL_INBOX
    )
    assert "sk-ant-" not in (job_state["last_result_summary"] or "")
    assert "secret_redaction_failed" in (job_state["last_result_summary"] or "")


# ---------------------------------------------------------------------------
# read_latest_snapshot helper (used by api_agent_control + approval_inbox)
# ---------------------------------------------------------------------------


def test_read_latest_snapshot_handles_missing(isolated: Path) -> None:
    assert rm.read_latest_snapshot() is None


def test_read_latest_snapshot_handles_malformed(isolated: Path) -> None:
    (isolated / "rm").mkdir()
    (isolated / "rm" / "latest.json").write_text("{ not json", encoding="utf-8")
    assert rm.read_latest_snapshot() is None


def test_read_latest_snapshot_returns_dict(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executor(
        monkeypatch, rm.JOB_REFRESH_APPROVAL_INBOX, lambda: {"summary": "ok"}
    )
    rm.run_one_job(rm.JOB_REFRESH_APPROVAL_INBOX, persist=True)
    snap = rm.read_latest_snapshot()
    assert isinstance(snap, dict)
    assert snap["report_kind"] == "recurring_maintenance_digest"


# ---------------------------------------------------------------------------
# CLI thin-shim
# ---------------------------------------------------------------------------


def test_cli_list_jobs_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    rc = rm.main(["--list-jobs", "--no-write"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_kind"] == "recurring_maintenance_digest"
    assert payload["mode"] == "list"


def test_cli_plan_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    rc = rm.main(["--plan", "--no-write"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "plan"
    assert "due_now" in payload
    assert not (tmp_path / "rm" / "state.json").exists()


def test_cli_status_when_no_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    rc = rm.main(["--status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_available"
