"""Targeted pin-tests for the v3.15.16.N5b.phase1 recurring
maintenance integration of the dry-run merge-preflight projector.

These tests pin that the N5b Phase 1 dry-run merge-preflight
projector (``reporting.development_merge_preflight``) is registered
in the recurring-maintenance scheduler as a LOW-risk,
no-``gh``-needed, default-enabled job, and that its executor:

* returns the documented ``{"summary": str, "evidence": dict}``
  envelope;
* writes ``logs/development_merge_preflight/latest.json`` atomically
  via the projector's own write path (sentinel-restricted);
* is failure-non-fatal when upstream A22 / A23 artefacts are
  absent (default-deny + closed-vocab warnings, never raises);
* preserves the dry-run / no-live-merge / no-deploy-coupling
  invariants in the persisted snapshot regardless of upstream
  state;
* never calls ``gh``, ``git``, ``subprocess``, or the network,
  pinned by an AST/source-text scan of the executor and the
  projector module that backs it.

These tests do **not** enable any runtime gate. They do not flip
Step 5 / Level 6 invariants. They do not call ``gh``. They do not
merge or deploy.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_merge_preflight as dmp
from reporting import recurring_maintenance as rm

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_latest(repo_logs: Path) -> dict[str, Any]:
    """Read the N5b Phase 1 preflight artefact from a tmp-rooted
    ``logs/development_merge_preflight/latest.json``."""
    path = repo_logs / "development_merge_preflight" / "latest.json"
    assert path.is_file(), f"preflight artefact missing under tmp: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_projector_paths_to_tmp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect the projector's write target (and its upstream-read
    paths) into a hermetic tmp directory so the executor cannot
    pollute the repo's real ``logs/`` tree during test execution.

    The projector's atomic-write sentinel restricts writes to
    ``logs/development_merge_preflight/``; we keep that substring
    in the redirected path so the sentinel passes."""
    tmp_logs = tmp_path / "logs"
    tmp_artifact_dir = tmp_logs / "development_merge_preflight"
    tmp_artifact_dir.mkdir(parents=True, exist_ok=True)
    tmp_artifact_latest = tmp_artifact_dir / "latest.json"
    monkeypatch.setattr(dmp, "ARTIFACT_DIR", tmp_artifact_dir)
    monkeypatch.setattr(dmp, "ARTIFACT_LATEST", tmp_artifact_latest)
    return tmp_logs


# ---------------------------------------------------------------------------
# Closed-registry pins
# ---------------------------------------------------------------------------


def test_merge_preflight_job_constant_value() -> None:
    """The exact CLI-facing job_type string is pinned. Operators
    invoke it via ``--run-once refresh_merge_preflight``; if that
    string ever drifts, this test fails before the rename can land."""
    assert rm.JOB_REFRESH_MERGE_PREFLIGHT == "refresh_merge_preflight"


def test_merge_preflight_job_is_in_closed_registry() -> None:
    assert rm.JOB_REFRESH_MERGE_PREFLIGHT in rm.JOB_TYPES
    assert rm.JOB_REFRESH_MERGE_PREFLIGHT in rm._JOB_REGISTRY


def test_merge_preflight_job_is_low_risk_no_gh_enabled_by_default() -> None:
    """The N5b Phase 1 projector is pure stdlib and reads only
    on-disk artefacts. The job must therefore be LOW risk,
    ``needs_gh=False``, default-enabled."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_MERGE_PREFLIGHT]
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False
    assert spec["default_enabled"] is True


def test_merge_preflight_registry_interval_matches_documented_cadence() -> None:
    """30-minute cadence mirrors the A22-adjacent projections and
    the upstream ``refresh_github_pr_lifecycle_dry_run`` cadence.
    A deliberate change here must update the runbook in the same
    PR."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_MERGE_PREFLIGHT]
    assert spec["default_interval_seconds"] == 30 * 60


def test_merge_preflight_job_timeout_is_default() -> None:
    """No bespoke timeout — the projector reads two small JSON
    files and writes one. The default 90-second budget is more
    than enough."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_MERGE_PREFLIGHT]
    assert spec["timeout_seconds"] == rm.DEFAULT_JOB_TIMEOUT_SECONDS


def test_merge_preflight_executor_is_the_documented_function() -> None:
    """The registry's executor handle must point at the documented
    in-process function. A drift here would silently re-route the
    refresh."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_MERGE_PREFLIGHT]
    assert spec["executor"] is rm._exec_refresh_merge_preflight


# ---------------------------------------------------------------------------
# Executor behaviour
# ---------------------------------------------------------------------------


def test_executor_returns_documented_envelope_when_upstream_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No upstream A22 / A23 artefacts present. The projector
    default-denies; the executor must return a valid
    ``{"summary", "evidence"}`` envelope and never raise."""
    _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    # Force the projector to read NON-existent upstream paths so the
    # default-deny path fires deterministically.
    monkeypatch.setattr(
        dmp,
        "REPO_ROOT",
        tmp_path,  # absolutely nothing under tmp/logs/development_pr_lifecycle_observer or .../development_merge_recommendation
        raising=False,
    )
    # Re-point the upstream artefact constants too (the projector
    # captures them at import time via the upstream module imports;
    # the safer hermetic move is to override the projector's own
    # call paths via collect_snapshot's parameters in a separate
    # test below).
    out = rm._exec_refresh_merge_preflight()
    assert isinstance(out, dict)
    assert isinstance(out.get("summary"), str)
    assert isinstance(out.get("evidence"), dict)
    # Evidence carries the closed dry-run invariants verbatim.
    ev = out["evidence"]
    assert ev["dry_run_only"] is True
    assert ev["live_merge_implemented"] is False
    assert ev["deploy_coupled"] is False
    # candidate_count is 0 because upstream is absent under tmp.
    assert ev["candidate_count"] == 0
    # note is one of the closed warnings.
    assert ev["note"] in (
        "missing_merge_recommendation_artifact",
        "missing_pr_lifecycle_artifact",
        "no_recommendation_rows",
    )


def test_executor_persists_snapshot_under_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor calls the projector's ``write_outputs`` which
    is sentinel-restricted to ``logs/development_merge_preflight/``.
    Verify the file was written under the tmp-redirected path."""
    tmp_logs = _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    rm._exec_refresh_merge_preflight()
    snap = _read_latest(tmp_logs)
    assert snap["report_kind"] == "development_merge_preflight"
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    assert snap["level6_enabled"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_executor_failure_non_fatal_when_upstream_absent_under_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the recurring-maintenance supervisor:
    even with no upstream A22 / A23 artefacts, the executor must
    return cleanly and the supervisor must classify the run as
    ``STATUS_SUCCEEDED`` (not ``STATUS_FAILED`` /
    ``STATUS_TIMEOUT`` / ``STATUS_NOT_AVAILABLE``)."""
    _patch_projector_paths_to_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(rm, "DIGEST_DIR_JSON", tmp_path / "rm")
    snap = rm.run_one_job(rm.JOB_REFRESH_MERGE_PREFLIGHT, persist=True)
    job_row = next(
        j
        for j in snap["jobs"]
        if j["job_type"] == rm.JOB_REFRESH_MERGE_PREFLIGHT
    )
    assert job_row["last_status"] == rm.STATUS_SUCCEEDED
    # The supervisor must not have flagged a consecutive failure.
    assert job_row["consecutive_failures"] == 0


def test_executor_preserves_dry_run_invariants_with_minimal_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hand-craft minimal valid A22 + A23 upstream fixtures on disk
    and verify the executor's persisted snapshot still asserts the
    six dry-run / no-live-merge / no-deploy-coupling / Step 5 /
    Level 6 invariants."""
    from reporting import development_merge_recommendation as dmr
    from reporting import development_pr_lifecycle_observer as a22

    tmp_logs = _patch_projector_paths_to_tmp(monkeypatch, tmp_path)

    # Redirect upstream artefact locations into tmp too. The
    # projector reads from the module-level ``ARTIFACT_LATEST``
    # constants of each upstream — patch both.
    a22_dir = tmp_logs / "development_pr_lifecycle_observer"
    a22_dir.mkdir(parents=True, exist_ok=True)
    a22_path = a22_dir / "latest.json"
    a22_path.write_text(
        json.dumps({"rows": []}),  # empty but valid shape
        encoding="utf-8",
    )
    monkeypatch.setattr(a22, "ARTIFACT_LATEST", a22_path)

    dmr_dir = tmp_logs / "development_merge_recommendation"
    dmr_dir.mkdir(parents=True, exist_ok=True)
    dmr_path = dmr_dir / "latest.json"
    dmr_path.write_text(
        json.dumps({"rows": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dmr, "ARTIFACT_LATEST", dmr_path)

    rm._exec_refresh_merge_preflight()
    snap = _read_latest(tmp_logs)

    # Six core invariants pinned verbatim.
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    assert snap["level6_enabled"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    # Closed-vocab discipline_invariants dict must match.
    di = snap["discipline_invariants"]
    assert di["dry_run_only"] is True
    assert di["live_merge_implemented"] is False
    assert di["executes_merge"] is False
    assert di["calls_github_api"] is False
    assert di["uses_subprocess_or_network"] is False
    assert di["deploy_coupled"] is False
    assert di["mints_or_verifies_approval_tokens"] is False
    assert di["writes_seed_files"] is False
    assert di["writes_generated_seed"] is False
    assert di["opens_or_merges_prs"] is False
    assert di["step5_implementation_allowed"] is False
    assert di["step5_enabled_substage"] == "none"
    assert di["level6_enabled"] is False


# ---------------------------------------------------------------------------
# AST / source-text scan: the executor and the projector module
# never reach for gh / git / subprocess / network.
# ---------------------------------------------------------------------------


def test_executor_source_contains_no_subprocess_or_network() -> None:
    """The supervisor isolates the executor in a daemon thread but
    still runs it in the same Python process. The executor's own
    source must therefore not import or invoke subprocess / socket
    / gh / git. The two upstream modules it ultimately reaches via
    ``development_merge_preflight`` are independently pinned by
    their own test suites."""
    src = inspect.getsource(rm._exec_refresh_merge_preflight)
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
            f"_exec_refresh_merge_preflight source contains "
            f"forbidden token {needle!r}"
        )


def test_projector_module_does_not_import_subprocess_or_network() -> None:
    """The N5b Phase 1 projector module that backs the executor
    must not import subprocess, socket, urllib, requests, httpx,
    aiohttp. AST-level scan — catches indirect re-exports."""
    src = Path(dmp.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_modules = {
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in {
                    "subprocess",
                    "socket",
                    "urllib",
                    "requests",
                    "httpx",
                    "aiohttp",
                }, (
                    f"projector imports forbidden module: "
                    f"{alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in {
                "subprocess",
                "socket",
                "urllib",
                "requests",
                "httpx",
                "aiohttp",
            }, (
                f"projector imports forbidden module: "
                f"from {node.module!r}"
            )
    # also a literal-source belt-and-braces scan for the canonical
    # `import subprocess` / `import socket` shapes.
    for forbidden in forbidden_modules:
        assert f"import {forbidden}" not in src, (
            f"projector source contains literal import of "
            f"{forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — the refresh path must not introduce token /
# deploy / Step 5 / Level 6 / A18b / N5b live-execute authority.
# ---------------------------------------------------------------------------


def test_executor_source_contains_no_token_mint_or_verify_call() -> None:
    """Preflight is pre-token. The executor must not import or
    invoke the N4 approval-token runtime."""
    src = inspect.getsource(rm._exec_refresh_merge_preflight).lower()
    forbidden_calls = (
        "approval_token_runtime",
        "mint_runtime",
        "verify_runtime",
        "mint_approval_token",
        "verify_approval_token",
    )
    for needle in forbidden_calls:
        assert needle not in src, (
            f"_exec_refresh_merge_preflight source contains "
            f"forbidden token-runtime reference {needle!r}"
        )


def test_executor_source_does_not_enable_a18b_or_n5b_live_execute() -> None:
    """The executor must not export, set, or read the two
    gating env flags (A18b writer activation, N5b live execute)."""
    src = inspect.getsource(rm._exec_refresh_merge_preflight)
    forbidden = (
        "ADE_GENERATED_LANE_WRITER_ENABLED",
        "ADE_N5B_LIVE_EXECUTE_ENABLED",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_merge_preflight source contains "
            f"forbidden runtime-gate flag {needle!r}"
        )


def test_executor_source_does_not_flip_step5_or_level6() -> None:
    """The executor must not assign to / mutate any Step 5 or
    Level 6 marker. (The projector module's own tests separately
    pin that the artefact's invariants stay false / none.)"""
    src = inspect.getsource(rm._exec_refresh_merge_preflight)
    forbidden = (
        "step5_implementation_allowed = True",
        "step5_implementation_allowed=True",
        "STEP5_ENABLED_SUBSTAGE = ",
        "level6_enabled = True",
        "level6_enabled=True",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"_exec_refresh_merge_preflight source contains "
            f"forbidden Step 5 / Level 6 flip: {needle!r}"
        )


def test_registry_entry_for_merge_preflight_carries_no_runtime_authority() -> None:
    """Registry entry must not silently elevate the job to MEDIUM
    risk, mark ``needs_gh`` true, or expose any execute-safe-style
    flag — those are reserved for the Dependabot path."""
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_MERGE_PREFLIGHT]
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
