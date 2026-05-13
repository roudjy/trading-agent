"""Targeted pin-tests for the v3.15.16.A14 recurring maintenance
integration of the Step 5.0 dry-run / planner-only loop.

These tests pin that the Step 5.0 dry-run loop
(``reporting.development_step5_loop``) is registered in the
recurring-maintenance scheduler as a LOW-risk, no-``gh``-needed,
default-enabled job, and that its executor:

* returns the documented ``{"summary": str, "evidence": dict}``
  envelope;
* writes three artefacts under ``logs/step5_plan/`` and
  ``logs/step5_loop/`` atomically via the projector's own
  sentinel-restricted write helpers (per-cycle plan + bounded
  90-entry history + loop snapshot);
* is failure-non-fatal when the three upstream ADE artefacts
  (A11 delegation, A10 bugfix loop, A8 work queue) are absent
  (the projector emits a ``no_op_no_eligible_item`` cycle and
  never raises);
* preserves Step 5 / Level 6 invariants in the persisted
  snapshot regardless of upstream state — most importantly,
  ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"`` (both pinned at
  module-level as ``Final`` constants, re-asserted at runtime
  by the dedicated invariant test);
* never calls ``gh``, ``git``, ``subprocess``, or the network;
* never mutates the environment, never enables A18b's writer
  gate, never enables N5b's live-execute gate;
* never synthesises a Step 5 substage flip in its own function
  source.

These tests do **not** enable any runtime gate. They do not flip
Step 5 / Level 6 invariants. They do not call ``gh``. They do not
merge or deploy. They do not write to ``seed.jsonl`` /
``delegation_seed.jsonl`` / ``generated_seed.jsonl``.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_step5_loop as s5l
from reporting import development_work_queue as dwq
from reporting import recurring_maintenance as rm

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_step5_loop_latest(repo_logs: Path) -> dict[str, Any]:
    """Read the Step 5 loop snapshot from a tmp-rooted
    ``logs/step5_loop/latest.json``."""
    path = repo_logs / "step5_loop" / "latest.json"
    assert path.is_file(), f"step5_loop artefact missing under tmp: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_step5_paths_to_tmp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect the Step 5.0 module's three write targets into a
    hermetic tmp directory so the executor cannot pollute the
    repo's real ``logs/`` tree during test execution.

    The projector's atomic-write sentinel restricts writes to
    paths containing ``logs/step5_plan/`` or ``logs/step5_loop/``;
    we keep both substrings in the redirected paths so the
    sentinel passes."""
    tmp_logs = tmp_path / "logs"
    tmp_step5_loop_dir = tmp_logs / "step5_loop"
    tmp_step5_plan_dir = tmp_logs / "step5_plan"
    tmp_step5_loop_dir.mkdir(parents=True, exist_ok=True)
    tmp_step5_plan_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        s5l, "ARTIFACT_LATEST", tmp_step5_loop_dir / "latest.json"
    )
    monkeypatch.setattr(s5l, "PLAN_DIR", tmp_step5_plan_dir)
    monkeypatch.setattr(
        s5l, "HISTORY_PATH", tmp_step5_plan_dir / "history.jsonl"
    )
    return tmp_logs


def _redirect_upstreams_to_absent_tmp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Redirect the three upstream ADE ``ARTIFACT_LATEST``
    constants (delegation, bugfix loop, work queue) to nonexistent
    tmp paths so the projector's ``no_op_no_eligible_item``
    branch fires deterministically."""
    upstream_tmp = tmp_path / "upstream"
    upstream_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ddl, "ARTIFACT_LATEST", upstream_tmp / "deleg.json")
    monkeypatch.setattr(dbl, "ARTIFACT_LATEST", upstream_tmp / "bug.json")
    monkeypatch.setattr(dwq, "ARTIFACT_LATEST", upstream_tmp / "queue.json")


# ---------------------------------------------------------------------------
# Closed-registry pins
# ---------------------------------------------------------------------------


def test_step5_loop_job_constant_value() -> None:
    """The exact CLI-facing job_type string is pinned. Operators
    invoke it via ``--run-once refresh_step5_loop``; if that
    string ever drifts, this test fails before the rename can
    land."""
    assert rm.JOB_REFRESH_STEP5_LOOP == "refresh_step5_loop"


def test_step5_loop_job_is_in_closed_registry() -> None:
    assert rm.JOB_REFRESH_STEP5_LOOP in rm.JOB_TYPES
    assert rm.JOB_REFRESH_STEP5_LOOP in rm._JOB_REGISTRY


def test_step5_loop_job_is_low_risk_no_gh_enabled_by_default() -> None:
    """The Step 5.0 dry-run loop is pure stdlib + ADE peers; it
    reads only on-disk artefacts. The job must therefore be LOW
    risk, ``needs_gh=False``, default-enabled."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_STEP5_LOOP]
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False
    assert spec["default_enabled"] is True


def test_step5_loop_registry_interval_is_thirty_minutes() -> None:
    """30-minute cadence mirrors the rest of the A22-adjacent /
    A18-adjacent reporters and the upstream ``refresh_merge_preflight``
    cadence. A deliberate change here must update the runbook in
    the same PR."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_STEP5_LOOP]
    assert spec["default_interval_seconds"] == 30 * 60


def test_step5_loop_job_timeout_is_default() -> None:
    """No bespoke timeout — the loop reads three small JSON
    files and writes three. The default 90-second budget is more
    than enough."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_STEP5_LOOP]
    assert spec["timeout_seconds"] == rm.DEFAULT_JOB_TIMEOUT_SECONDS


def test_step5_loop_executor_is_the_documented_function() -> None:
    """The registry's executor handle must point at the documented
    in-process function. A drift here would silently re-route the
    refresh."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_STEP5_LOOP]
    assert spec["executor"] is rm._exec_refresh_step5_loop


def test_registry_entry_for_step5_loop_carries_no_runtime_authority() -> None:
    """Registry entry must not silently elevate the job to MEDIUM
    risk, mark ``needs_gh`` true, or expose any execute-safe-style
    flag — those are reserved for the Dependabot path."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_STEP5_LOOP]
    # The registry shape is closed to a fixed key-set; if a future
    # change introduces a new key (e.g. an opt-in flag), this test
    # forces a deliberate update.
    assert set(spec.keys()) == {
        "default_interval_seconds",
        "default_enabled",
        "executor",
        "description",
        "risk_class",
        "needs_gh",
        "timeout_seconds",
    }
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False


# ---------------------------------------------------------------------------
# Executor behaviour
# ---------------------------------------------------------------------------


def test_executor_returns_documented_envelope_when_upstreams_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With all three upstream ADE artefacts absent, the
    projector emits a ``no_op_no_eligible_item`` cycle. The
    executor must return a valid ``{"summary", "evidence"}``
    envelope and never raise. The Step 5 invariants must be
    present in evidence."""
    _patch_step5_paths_to_tmp(monkeypatch, tmp_path)
    _redirect_upstreams_to_absent_tmp(monkeypatch, tmp_path)
    out = rm._exec_refresh_step5_loop()
    assert isinstance(out, dict)
    assert isinstance(out.get("summary"), str)
    assert isinstance(out.get("evidence"), dict)
    ev = out["evidence"]
    assert ev["step5_enabled_substage"] == "none"
    assert ev["step5_implementation_allowed"] is False
    assert ev["outcome"] == "no_op_no_eligible_item"
    assert ev["presence"] == {
        "delegation": False,
        "bugfix_loop": False,
        "queue": False,
    }
    assert ev["max_history_entries"] == 90


def test_executor_persists_three_snapshots_under_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor calls the projector's ``write_outputs`` which
    is sentinel-restricted to ``logs/step5_plan/`` and
    ``logs/step5_loop/``. Verify all three artefacts (per-cycle
    plan, bounded history, loop snapshot) are written under the
    tmp-redirected paths and that the loop snapshot carries the
    Step 5 invariants verbatim."""
    tmp_logs = _patch_step5_paths_to_tmp(monkeypatch, tmp_path)
    _redirect_upstreams_to_absent_tmp(monkeypatch, tmp_path)
    rm._exec_refresh_step5_loop()
    # 1. Loop snapshot
    snap = _read_step5_loop_latest(tmp_logs)
    assert snap["report_kind"] == s5l.LOOP_REPORT_KIND
    assert snap["step5_enabled_substage"] == "none"
    assert snap["step5_implementation_allowed"] is False
    assert snap["max_history_entries"] == 90
    # 2. Per-cycle plan file under logs/step5_plan/<cycle_id>.json
    plan_dir = tmp_logs / "step5_plan"
    plan_files = [
        p
        for p in plan_dir.iterdir()
        if p.is_file() and p.suffix == ".json" and p.name != "history.jsonl"
    ]
    assert len(plan_files) == 1, (
        f"expected exactly one per-cycle plan file, got: {plan_files}"
    )
    plan = json.loads(plan_files[0].read_text(encoding="utf-8"))
    assert plan["report_kind"] == s5l.REPORT_KIND
    # 3. Bounded history file
    history_path = plan_dir / "history.jsonl"
    assert history_path.is_file()
    history_lines = [
        line
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(history_lines) == 1, (
        f"expected exactly one history entry after one tick, got "
        f"{len(history_lines)}"
    )
    history_entry = json.loads(history_lines[0])
    assert history_entry["module_version"] == s5l.MODULE_VERSION


def test_executor_failure_non_fatal_under_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the recurring-maintenance supervisor:
    with all upstream ADE artefacts absent, the executor must
    return cleanly and the supervisor must classify the run as
    ``STATUS_SUCCEEDED`` (not ``STATUS_FAILED`` /
    ``STATUS_TIMEOUT`` / ``STATUS_NOT_AVAILABLE``)."""
    _patch_step5_paths_to_tmp(monkeypatch, tmp_path)
    _redirect_upstreams_to_absent_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    snap = rm.run_one_job(rm.JOB_REFRESH_STEP5_LOOP, persist=True)
    job_row = next(
        j
        for j in snap["jobs"]
        if j["job_type"] == rm.JOB_REFRESH_STEP5_LOOP
    )
    assert job_row["last_status"] == rm.STATUS_SUCCEEDED
    # The supervisor must not have flagged a consecutive failure.
    assert job_row["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# AST / source-text scan: the executor and the projector module
# never reach for gh / git / subprocess / network.
# ---------------------------------------------------------------------------


def test_executor_source_contains_no_subprocess_or_network() -> None:
    """The supervisor isolates the executor in a daemon thread but
    still runs it in the same Python process. The executor's own
    source must therefore not import or invoke subprocess / socket
    / gh / git. The projector module it reaches is independently
    pinned by ``test_step5_loop_module_does_not_import_subprocess_or_network``
    below and by the Step 5 module's own dedicated test suite."""
    src = inspect.getsource(rm._exec_refresh_step5_loop)
    lowered = src.lower()
    forbidden = (
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "popen",
        "shell=true",
        " gh ",
        " git ",
        "os.system",
    )
    for needle in forbidden:
        assert needle not in lowered, (
            f"_exec_refresh_step5_loop source contains forbidden "
            f"token {needle!r}"
        )


def test_step5_loop_module_does_not_import_subprocess_or_network() -> None:
    """Defense-in-depth re-pin from the maintenance side: the
    Step 5.0 module that backs the executor must not import
    subprocess, socket, urllib, requests, httpx, aiohttp.
    AST-level scan — catches indirect re-exports."""
    src = Path(s5l.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_top = {
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in forbidden_top, (
                    f"step5 module imports forbidden module: "
                    f"{alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in forbidden_top, (
                f"step5 module imports forbidden module: "
                f"from {node.module!r}"
            )
    # Belt-and-braces literal-source scan.
    forbidden_literal = {
        "subprocess",
        "socket",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "requests",
        "httpx",
        "aiohttp",
        "http.client",
    }
    for forbidden in forbidden_literal:
        assert f"import {forbidden}" not in src, (
            f"step5 module source contains literal import of "
            f"{forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — the refresh path must not introduce env mutation,
# A18b writer enablement, N5b live-execute authority, or any Step 5
# substage flip from inside the executor function.
# ---------------------------------------------------------------------------


def test_executor_source_does_not_mutate_environment() -> None:
    """The executor must not mutate or export environment
    variables. The Step 5.0 module has no env gate of its own,
    but the executor must still be defensive: no code path may
    assign to ``os.environ``, call ``os.environ.setdefault``,
    call ``os.putenv``, or use a shell-style export."""
    src = inspect.getsource(rm._exec_refresh_step5_loop)
    forbidden_substrings = (
        "os.environ[",
        "os.environ.setdefault",
        "os.putenv",
        "putenv(",
        "export ADE_",
    )
    for needle in forbidden_substrings:
        assert needle not in src, (
            f"_exec_refresh_step5_loop source contains forbidden "
            f"env-mutation token {needle!r}"
        )
    # AST-level pin: assert the executor body assigns nothing to
    # any ``os.environ[...]`` Subscript and never calls
    # ``os.environ.setdefault(...)`` / ``os.putenv(...)``.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    value = target.value
                    if (
                        isinstance(value, ast.Attribute)
                        and value.attr == "environ"
                    ):
                        raise AssertionError(
                            "_exec_refresh_step5_loop body assigns "
                            "to os.environ[...]"
                        )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in {"setdefault", "putenv"}:
                    parent = func.value
                    if (
                        isinstance(parent, ast.Attribute)
                        and parent.attr == "environ"
                    ):
                        raise AssertionError(
                            "_exec_refresh_step5_loop body calls "
                            "os.environ.setdefault(...)"
                        )
                    if (
                        isinstance(parent, ast.Name)
                        and parent.id == "os"
                        and func.attr == "putenv"
                    ):
                        raise AssertionError(
                            "_exec_refresh_step5_loop body calls "
                            "os.putenv(...)"
                        )


def test_executor_source_does_not_enable_a18b_or_n5b_live_execute() -> None:
    """The executor must not export, set, or read the two gating
    env flags for A18b writer activation and N5b live execute.
    These flags govern *other* default-disabled surfaces and must
    not be touched by the Step 5.0 maintenance entry."""
    src = inspect.getsource(rm._exec_refresh_step5_loop)
    forbidden = (
        "ADE_GENERATED_LANE_WRITER_ENABLED",
        "ADE_N5B_LIVE_EXECUTE_ENABLED",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_step5_loop source contains forbidden "
            f"runtime-gate flag {needle!r}"
        )


def test_executor_source_does_not_flip_step5_or_level6() -> None:
    """The executor must not assign to / mutate any Step 5 or
    Level 6 marker. (The Step 5 module's own tests separately
    pin that the artefact's invariants stay false / none.)"""
    src = inspect.getsource(rm._exec_refresh_step5_loop)
    forbidden = (
        "step5_implementation_allowed = True",
        "step5_implementation_allowed=True",
        'STEP5_ENABLED_SUBSTAGE = "5',
        "STEP5_ENABLED_SUBSTAGE='5",
        "level6_enabled = True",
        "level6_enabled=True",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_step5_loop source contains forbidden "
            f"Step 5 / Level 6 flip: {needle!r}"
        )


def test_executor_source_does_not_synthesize_step5_substage_flip() -> None:
    """Belt-and-braces source-text scan: the executor function
    must not synthesise any substage value other than ``"none"``.
    The literals ``"5.0"`` / ``"5.1"`` / ``"5.2"`` must not appear
    in the executor's own bytes, because they would only ever be
    used to flip ``STEP5_ENABLED_SUBSTAGE`` away from the
    default-deny value."""
    src = inspect.getsource(rm._exec_refresh_step5_loop)
    forbidden_literal_pairs = (
        '"5.0"',
        "'5.0'",
        '"5.1"',
        "'5.1'",
        '"5.2"',
        "'5.2'",
    )
    for needle in forbidden_literal_pairs:
        assert needle not in src, (
            f"_exec_refresh_step5_loop source contains forbidden "
            f"substage literal {needle!r}"
        )


# ---------------------------------------------------------------------------
# B1.4-specific runtime invariant pin
# ---------------------------------------------------------------------------


def test_step5_invariants_remain_pinned_after_executor_import() -> None:
    """After importing the Step 5.0 module the way the executor
    does (via ``from reporting.development_step5_loop import
    collect_snapshot, write_outputs``), the two load-bearing
    constants must still evaluate to their default-deny values.

    Belt-and-braces runtime confirmation that the maintenance
    entry does not (and cannot, given the constants are
    module-level ``Final``) flip either constant. Combined with
    the source-text scans above, this gives defense in depth:

    * static: executor source contains no flip token;
    * runtime: after import, both constants still read False /
      "none".
    """
    # Re-import via the same path the executor uses.
    from reporting.development_step5_loop import (  # noqa: F401
        collect_snapshot,
        write_outputs,
    )
    from reporting import development_step5_loop as _s5l

    assert _s5l.step5_implementation_allowed is False, (
        "step5_implementation_allowed must remain False — the "
        "recurring-maintenance entry must NOT flip this constant"
    )
    assert _s5l.STEP5_ENABLED_SUBSTAGE == "none", (
        'STEP5_ENABLED_SUBSTAGE must remain "none" — the '
        "recurring-maintenance entry must NOT flip this constant"
    )
