"""Targeted pin-tests for the v3.15.16.A18c recurring maintenance
integration of the default-disabled admission projector.

These tests pin that the A18c admission projector
(``reporting.development_generated_lane_a18c``) is registered in
the recurring-maintenance scheduler as a LOW-risk,
no-``gh``-needed, default-enabled job, and that its executor:

* returns the documented ``{"summary": str, "evidence": dict}``
  envelope;
* writes ``logs/development_generated_lane_a18c/latest.json``
  atomically via the projector's own sentinel-restricted write
  path;
* respects the projector's existing env-gate
  (``ADE_GENERATED_LANE_A18C_ENABLED``) — the scheduler entry runs
  the projector every interval, but whether any work happens
  remains the projector's decision;
* preserves the dry-run / no-live-merge / no-deploy-coupling /
  Step 5 / Level 6 invariants in the persisted snapshot
  regardless of upstream state;
* never calls ``gh``, ``git``, ``subprocess``, or the network;
* never mutates the environment, never enables A18b's writer
  gate, never enables N5b's live-execute gate, never forces the
  A18c env-gate on.

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

from reporting import development_generated_lane_a18c as dmgl_a18c
from reporting import recurring_maintenance as rm

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_latest(repo_logs: Path) -> dict[str, Any]:
    """Read the A18c artefact from a tmp-rooted
    ``logs/development_generated_lane_a18c/latest.json``."""
    path = repo_logs / "development_generated_lane_a18c" / "latest.json"
    assert path.is_file(), f"A18c artefact missing under tmp: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_projector_paths_to_tmp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect the projector's write target into a hermetic tmp
    directory so the executor cannot pollute the repo's real
    ``logs/`` tree during test execution.

    The projector's atomic-write sentinel restricts writes to
    ``logs/development_generated_lane_a18c/``; we keep that
    substring in the redirected path so the sentinel passes."""
    tmp_logs = tmp_path / "logs"
    tmp_artifact_dir = tmp_logs / "development_generated_lane_a18c"
    tmp_artifact_dir.mkdir(parents=True, exist_ok=True)
    tmp_artifact_latest = tmp_artifact_dir / "latest.json"
    monkeypatch.setattr(dmgl_a18c, "ARTIFACT_LATEST", tmp_artifact_latest)
    return tmp_logs


def _force_env_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the A18c env-gate evaluates to False inside the test
    process regardless of the operator's local shell. The projector
    requires the exact literal string ``"true"`` to enable; any
    other value (including the literal ``"0"`` used here) leaves
    it disabled. No real ``"true"`` value is ever set by these
    tests."""
    monkeypatch.setenv(dmgl_a18c.ENV_GATE, "0")


# ---------------------------------------------------------------------------
# Closed-registry pins
# ---------------------------------------------------------------------------


def test_generated_lane_a18c_job_constant_value() -> None:
    """The exact CLI-facing job_type string is pinned. Operators
    invoke it via ``--run-once refresh_generated_lane_a18c``; if
    that string ever drifts, this test fails before the rename
    can land."""
    assert (
        rm.JOB_REFRESH_GENERATED_LANE_A18C == "refresh_generated_lane_a18c"
    )


def test_generated_lane_a18c_job_is_in_closed_registry() -> None:
    assert rm.JOB_REFRESH_GENERATED_LANE_A18C in rm.JOB_TYPES
    assert rm.JOB_REFRESH_GENERATED_LANE_A18C in rm._JOB_REGISTRY


def test_generated_lane_a18c_job_is_low_risk_no_gh_enabled_by_default() -> None:
    """The A18c admission projector is pure stdlib and reads only
    on-disk artefacts (and only when its own env-gate is enabled).
    The job must therefore be LOW risk, ``needs_gh=False``,
    default-enabled."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_GENERATED_LANE_A18C]
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False
    assert spec["default_enabled"] is True


def test_generated_lane_a18c_registry_interval_is_thirty_minutes() -> None:
    """30-minute cadence mirrors the A22-adjacent / A18-adjacent
    projections and the upstream ``refresh_merge_preflight``
    cadence. A deliberate change here must update the runbook in
    the same PR."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_GENERATED_LANE_A18C]
    assert spec["default_interval_seconds"] == 30 * 60


def test_generated_lane_a18c_job_timeout_is_default() -> None:
    """No bespoke timeout — the projector reads one small JSON
    file (only when env-gate is on) and writes one. The default
    90-second budget is more than enough."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_GENERATED_LANE_A18C]
    assert spec["timeout_seconds"] == rm.DEFAULT_JOB_TIMEOUT_SECONDS


def test_generated_lane_a18c_executor_is_the_documented_function() -> None:
    """The registry's executor handle must point at the documented
    in-process function. A drift here would silently re-route the
    refresh."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_GENERATED_LANE_A18C]
    assert spec["executor"] is rm._exec_refresh_generated_lane_a18c


def test_registry_entry_for_a18c_carries_no_runtime_authority() -> None:
    """Registry entry must not silently elevate the job to MEDIUM
    risk, mark ``needs_gh`` true, or expose any execute-safe-style
    flag — those are reserved for the Dependabot path."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_GENERATED_LANE_A18C]
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


def test_executor_returns_documented_envelope_env_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the A18c env-gate UNSET (or set to anything other than
    the exact literal ``"true"``), the projector emits the
    enabled=False no-op envelope without reading
    ``generated_seed.jsonl``. The executor must return a valid
    ``{"summary", "evidence"}`` envelope and never raise."""
    _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    _force_env_gate_off(monkeypatch)
    out = rm._exec_refresh_generated_lane_a18c()
    assert isinstance(out, dict)
    assert isinstance(out.get("summary"), str)
    assert isinstance(out.get("evidence"), dict)
    ev = out["evidence"]
    assert ev["enabled"] is False
    assert ev["total"] == 0
    assert ev["admissible"] == 0
    assert ev["note"] == "env_gate_off"
    # Evidence carries the closed dry-run invariants verbatim.
    assert ev["dry_run_only"] is True
    assert ev["live_merge_implemented"] is False
    assert ev["deploy_coupled"] is False
    assert ev["level6_enabled"] is False
    assert ev["step5_implementation_allowed"] is False
    assert ev["step5_enabled_substage"] == "none"


def test_executor_persists_snapshot_under_tmp_env_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor calls the projector's ``write_outputs`` which
    is sentinel-restricted to ``logs/development_generated_lane_a18c/``.
    Verify the file was written under the tmp-redirected path and
    that the persisted snapshot carries the Step 5 / Level 6
    invariants verbatim even on the env-off no-op path."""
    tmp_logs = _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    _force_env_gate_off(monkeypatch)
    rm._exec_refresh_generated_lane_a18c()
    snap = _read_latest(tmp_logs)
    assert snap["report_kind"] == dmgl_a18c.REPORT_KIND
    assert snap["enabled"] is False
    assert snap["note"] == "env_gate_off"
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    assert snap["level6_enabled"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_executor_does_not_read_seed_when_env_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense-in-depth: with the env-gate UNSET, the executor's
    snapshot must show that the projector took the no-op path
    (``note=="env_gate_off"``, ``rows == []``). Catches an
    accidental gate bypass that would otherwise show a different
    note string."""
    _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    _force_env_gate_off(monkeypatch)
    # Even if a generated_seed.jsonl existed at the canonical path,
    # the projector must not read it on the env-off path. We do
    # not create that file here; the test asserts on the snapshot
    # shape rather than on filesystem absence.
    rm._exec_refresh_generated_lane_a18c()
    tmp_logs = tmp_path / "logs"
    snap = _read_latest(tmp_logs)
    assert snap["note"] == "env_gate_off"
    assert snap["rows"] == []
    assert "env_gate_off_no_op" in snap["validation_warnings"]


def test_executor_failure_non_fatal_under_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the recurring-maintenance supervisor:
    with the env-gate unset, the executor must return cleanly and
    the supervisor must classify the run as ``STATUS_SUCCEEDED``
    (not ``STATUS_FAILED`` / ``STATUS_TIMEOUT`` /
    ``STATUS_NOT_AVAILABLE``)."""
    _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    _force_env_gate_off(monkeypatch)
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    snap = rm.run_one_job(rm.JOB_REFRESH_GENERATED_LANE_A18C, persist=True)
    job_row = next(
        j
        for j in snap["jobs"]
        if j["job_type"] == rm.JOB_REFRESH_GENERATED_LANE_A18C
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
    pinned by ``test_projector_module_does_not_import_subprocess_or_network``
    below."""
    src = inspect.getsource(rm._exec_refresh_generated_lane_a18c)
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
            f"_exec_refresh_generated_lane_a18c source contains "
            f"forbidden token {needle!r}"
        )


def test_projector_module_does_not_import_subprocess_or_network() -> None:
    """The A18c projector module that backs the executor must not
    import subprocess, socket, urllib, requests, httpx, aiohttp.
    AST-level scan — catches indirect re-exports."""
    src = Path(dmgl_a18c.__file__).read_text(encoding="utf-8")
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
                    f"projector imports forbidden module: "
                    f"{alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in forbidden_top, (
                f"projector imports forbidden module: "
                f"from {node.module!r}"
            )
    # Belt-and-braces literal-source scan for the canonical
    # ``import <module>`` shapes.
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
            f"projector source contains literal import of "
            f"{forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — the refresh path must not introduce env mutation,
# A18b writer enablement, or N5b live-execute authority.
# ---------------------------------------------------------------------------


def test_executor_source_does_not_mutate_environment() -> None:
    """The executor must not mutate or export environment
    variables. Per the operator brief, merely naming
    ``ADE_GENERATED_LANE_A18C_ENABLED`` in a docstring is
    permitted (the description legitimately documents the gate),
    but no code path may assign to ``os.environ``, call
    ``os.environ.setdefault``, call ``os.putenv``, or use a
    shell-style export to force the gate on."""
    src = inspect.getsource(rm._exec_refresh_generated_lane_a18c)
    forbidden_substrings = (
        "os.environ[",
        "os.environ.setdefault",
        "os.putenv",
        "putenv(",
        "export ADE_",
        "ADE_GENERATED_LANE_A18C_ENABLED=true",
        'ADE_GENERATED_LANE_A18C_ENABLED="true"',
        "ADE_GENERATED_LANE_A18C_ENABLED='true'",
    )
    for needle in forbidden_substrings:
        assert needle not in src, (
            f"_exec_refresh_generated_lane_a18c source contains "
            f"forbidden env-mutation token {needle!r}"
        )
    # AST-level pin: assert the executor body assigns nothing to
    # any ``os.environ[...]`` Subscript and never calls a function
    # whose attribute access ends in ``putenv`` or
    # ``environ.setdefault``.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # Reject ``os.environ[<key>] = <value>``.
                if isinstance(target, ast.Subscript):
                    value = target.value
                    if (
                        isinstance(value, ast.Attribute)
                        and value.attr == "environ"
                    ):
                        raise AssertionError(
                            "_exec_refresh_generated_lane_a18c body "
                            "assigns to os.environ[...]"
                        )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                # Reject ``os.environ.setdefault(...)``,
                # ``os.putenv(...)``, ``environ.setdefault(...)``.
                if func.attr in {"setdefault", "putenv"}:
                    parent = func.value
                    if isinstance(parent, ast.Attribute) and parent.attr == "environ":
                        raise AssertionError(
                            "_exec_refresh_generated_lane_a18c body calls "
                            "os.environ.setdefault(...)"
                        )
                    if isinstance(parent, ast.Name) and parent.id == "os" and func.attr == "putenv":
                        raise AssertionError(
                            "_exec_refresh_generated_lane_a18c body calls "
                            "os.putenv(...)"
                        )


def test_executor_source_does_not_enable_a18b_or_n5b_live_execute() -> None:
    """The executor must not export, set, or read the two gating
    env flags for A18b writer activation and N5b live execute.
    These flags govern *other* default-disabled surfaces and must
    not be touched by the A18c maintenance entry."""
    src = inspect.getsource(rm._exec_refresh_generated_lane_a18c)
    forbidden = (
        "ADE_GENERATED_LANE_WRITER_ENABLED",
        "ADE_N5B_LIVE_EXECUTE_ENABLED",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_generated_lane_a18c source contains "
            f"forbidden runtime-gate flag {needle!r}"
        )


def test_executor_source_does_not_flip_step5_or_level6() -> None:
    """The executor must not assign to / mutate any Step 5 or
    Level 6 marker. (The projector module's own tests separately
    pin that the artefact's invariants stay false / none.)"""
    src = inspect.getsource(rm._exec_refresh_generated_lane_a18c)
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
            f"_exec_refresh_generated_lane_a18c source contains "
            f"forbidden Step 5 / Level 6 flip: {needle!r}"
        )
