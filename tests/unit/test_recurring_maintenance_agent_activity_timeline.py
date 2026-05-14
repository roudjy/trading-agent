"""Targeted pin-tests for the v3.15.16.A15.B2.0b recurring
maintenance integration of the Agent Activity Center aggregator.

These tests pin that the AAC aggregator
(``reporting.development_agent_activity_timeline``) is registered
in the recurring-maintenance scheduler as a LOW-risk,
no-``gh``-needed, default-enabled job, and that its executor:

* returns the documented ``{"summary": str, "evidence": dict}``
  envelope;
* writes
  ``logs/development_agent_activity_timeline/latest.json``
  atomically via the projector's own sentinel-restricted write
  helper (``aat.v0.1`` / ``schema_version=1``);
* is failure-non-fatal when every upstream artefact is absent
  (the projector default-denies with closed-vocab warnings and
  never raises);
* preserves the closed Step 5 / Level 6 invariants in the
  persisted envelope;
* never calls ``gh``, ``git``, ``subprocess``, or the network;
* never mutates the environment, never enables A18b's writer
  gate, never enables N5b's live-execute gate;
* never flips Step 5 / Level 6 markers in its own function source.

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

from reporting import development_agent_activity_timeline as aat
from reporting import recurring_maintenance as rm

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_latest(repo_logs: Path) -> dict[str, Any]:
    """Read the AAC artefact from a tmp-rooted
    ``logs/development_agent_activity_timeline/latest.json``."""
    path = (
        repo_logs / "development_agent_activity_timeline" / "latest.json"
    )
    assert path.is_file(), f"AAC artefact missing under tmp: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_aggregator_paths_to_tmp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect the aggregator's write target into a hermetic tmp
    directory so the executor cannot pollute the repo's real
    ``logs/`` tree during test execution.

    The aggregator's atomic-write sentinel restricts writes to
    paths containing ``logs/development_agent_activity_timeline/``;
    we keep that substring in the redirected path so the sentinel
    passes. We also redirect ``REPO_ROOT`` so the aggregator reads
    its 11 upstreams from a hermetic tree."""
    tmp_logs = tmp_path / "logs"
    tmp_aat_dir = tmp_logs / "development_agent_activity_timeline"
    tmp_aat_dir.mkdir(parents=True, exist_ok=True)
    tmp_aat_latest = tmp_aat_dir / "latest.json"
    monkeypatch.setattr(aat, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(aat, "ARTIFACT_DIR", tmp_aat_dir)
    monkeypatch.setattr(aat, "ARTIFACT_LATEST", tmp_aat_latest)
    return tmp_logs


# ---------------------------------------------------------------------------
# Closed-registry pins
# ---------------------------------------------------------------------------


def test_agent_activity_timeline_job_constant_value() -> None:
    """The exact CLI-facing job_type string is pinned. Operators
    invoke it via ``--run-once refresh_agent_activity_timeline``;
    if that string ever drifts, this test fails before the rename
    can land."""
    assert (
        rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE
        == "refresh_agent_activity_timeline"
    )


def test_agent_activity_timeline_job_is_in_closed_registry() -> None:
    assert rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE in rm.JOB_TYPES
    assert rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE in rm._JOB_REGISTRY


def test_agent_activity_timeline_job_is_low_risk_no_gh_enabled_by_default() -> None:
    """The AAC aggregator is pure stdlib + read-only artefact reads.
    The job must therefore be LOW risk, ``needs_gh=False``,
    default-enabled."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE]
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False
    assert spec["default_enabled"] is True


def test_agent_activity_timeline_registry_interval_is_thirty_minutes() -> None:
    """30-minute cadence mirrors the rest of the A22-adjacent /
    A18-adjacent reporters."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE]
    assert spec["default_interval_seconds"] == 30 * 60


def test_agent_activity_timeline_job_timeout_is_default() -> None:
    """No bespoke timeout — the aggregator reads 11 small JSON
    artefacts and writes one. The default 90-second budget is more
    than enough."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE]
    assert spec["timeout_seconds"] == rm.DEFAULT_JOB_TIMEOUT_SECONDS


def test_agent_activity_timeline_executor_is_the_documented_function() -> None:
    """The registry's executor handle must point at the documented
    in-process function. A drift here would silently re-route the
    refresh."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE]
    assert spec["executor"] is rm._exec_refresh_agent_activity_timeline


def test_registry_entry_for_agent_activity_timeline_carries_no_runtime_authority() -> None:
    """Registry entry must not silently elevate the job to MEDIUM
    risk, mark ``needs_gh`` true, or expose any execute-safe-style
    flag — those are reserved for the Dependabot path."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE]
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
    """With every upstream artefact absent (tmp tree has no
    ``logs/development_*`` files), the aggregator emits a valid
    envelope with empty arrays and ``any_stale=True``. The
    executor returns ``{"summary", "evidence"}`` and never raises."""
    _patch_aggregator_paths_to_tmp(monkeypatch, tmp_path)
    out = rm._exec_refresh_agent_activity_timeline()
    assert isinstance(out, dict)
    assert isinstance(out.get("summary"), str)
    assert isinstance(out.get("evidence"), dict)
    ev = out["evidence"]
    assert ev["total_open"] == 0
    assert ev["needs_human"] == 0
    assert ev["any_stale"] is True
    assert ev["any_malformed"] is False


def test_executor_persists_snapshot_under_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor calls the aggregator's ``write_outputs`` which
    is sentinel-restricted to
    ``logs/development_agent_activity_timeline/``. Verify the
    persisted snapshot carries the schema anchors verbatim."""
    tmp_logs = _patch_aggregator_paths_to_tmp(monkeypatch, tmp_path)
    rm._exec_refresh_agent_activity_timeline()
    snap = _read_latest(tmp_logs)
    assert snap["schema_version"] == 1
    assert snap["module_version"] == "aat.v0.1"
    assert snap["report_kind"] == "agent_activity_timeline"


def test_executor_persisted_snapshot_pins_invariant_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The persisted envelope must carry the 9-row closed
    ``invariant_status[]`` block with ``level_6`` ``danger_off``
    and ``step5_implementation_allowed`` ``off``."""
    tmp_logs = _patch_aggregator_paths_to_tmp(monkeypatch, tmp_path)
    rm._exec_refresh_agent_activity_timeline()
    snap = _read_latest(tmp_logs)
    invariants = snap.get("invariant_status") or []
    by_key = {row["key"]: row for row in invariants}
    assert by_key["level_6"]["value"] == "permanently_disabled"
    assert by_key["level_6"]["tone"] == "danger_off"
    assert by_key["step5_implementation_allowed"]["value"] is False
    assert by_key["step5_implementation_allowed"]["tone"] == "off"
    assert by_key["step5_substage"]["value"] == "none"
    assert by_key["live_merge_implemented"]["value"] is False
    assert by_key["deploy_coupled"]["value"] is False
    assert by_key["n5b_live_execute"]["value"] is False
    assert by_key["agent_service"]["value"] == "healthy"
    assert by_key["agent_service"]["tone"] == "on"


def test_executor_failure_non_fatal_under_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the recurring-maintenance supervisor:
    with every upstream absent, the executor returns cleanly and
    the supervisor classifies the run as ``STATUS_SUCCEEDED``."""
    _patch_aggregator_paths_to_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    snap = rm.run_one_job(
        rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE, persist=True
    )
    job_row = next(
        j
        for j in snap["jobs"]
        if j["job_type"] == rm.JOB_REFRESH_AGENT_ACTIVITY_TIMELINE
    )
    assert job_row["last_status"] == rm.STATUS_SUCCEEDED
    assert job_row["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# AST / source-text scans
# ---------------------------------------------------------------------------


def test_executor_source_contains_no_forbidden_tokens() -> None:
    """The supervisor isolates the executor in a daemon thread but
    still runs it in the same Python process. The executor's own
    source must therefore not import or invoke subprocess / socket
    / gh / git. Scoped to ``_exec_refresh_agent_activity_timeline``
    only — the aggregator module is independently pinned below."""
    src = inspect.getsource(rm._exec_refresh_agent_activity_timeline)
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
            f"_exec_refresh_agent_activity_timeline source contains "
            f"forbidden token {needle!r}"
        )


def test_aggregator_module_does_not_import_subprocess_or_network() -> None:
    """Defense-in-depth re-pin from the maintenance side: the
    AAC aggregator module that backs the executor must not import
    subprocess, socket, urllib, requests, httpx, aiohttp."""
    src = Path(aat.__file__).read_text(encoding="utf-8")
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
                    f"aggregator imports forbidden module: "
                    f"{alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in forbidden_top, (
                f"aggregator imports forbidden module: "
                f"from {node.module!r}"
            )


# ---------------------------------------------------------------------------
# Negative pins
# ---------------------------------------------------------------------------


def test_executor_source_does_not_mutate_environment() -> None:
    """The executor must not mutate or export environment
    variables."""
    src = inspect.getsource(rm._exec_refresh_agent_activity_timeline)
    forbidden_substrings = (
        "os.environ[",
        "os.environ.setdefault",
        "os.putenv",
        "putenv(",
        "os.getenv",
        "export ADE_",
    )
    for needle in forbidden_substrings:
        assert needle not in src, (
            f"_exec_refresh_agent_activity_timeline source contains "
            f"forbidden env-mutation token {needle!r}"
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
                            "_exec_refresh_agent_activity_timeline body "
                            "assigns to os.environ[...]"
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
                            "_exec_refresh_agent_activity_timeline body "
                            "calls os.environ.setdefault(...)"
                        )
                    if (
                        isinstance(parent, ast.Name)
                        and parent.id == "os"
                        and func.attr == "putenv"
                    ):
                        raise AssertionError(
                            "_exec_refresh_agent_activity_timeline body "
                            "calls os.putenv(...)"
                        )


def test_executor_source_does_not_enable_a18b_or_n5b_live_execute() -> None:
    """The executor must not export, set, or read the A18b writer
    enablement env or the N5b live-execute enablement env."""
    src = inspect.getsource(rm._exec_refresh_agent_activity_timeline)
    forbidden = (
        "ADE_GENERATED_LANE_WRITER_ENABLED",
        "ADE_N5B_LIVE_EXECUTE_ENABLED",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_agent_activity_timeline source contains "
            f"forbidden runtime-gate flag {needle!r}"
        )


def test_executor_source_does_not_flip_step5_or_level6() -> None:
    """The executor must not assign to / mutate any Step 5 or
    Level 6 marker."""
    src = inspect.getsource(rm._exec_refresh_agent_activity_timeline)
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
            f"_exec_refresh_agent_activity_timeline source contains "
            f"forbidden Step 5 / Level 6 flip: {needle!r}"
        )
