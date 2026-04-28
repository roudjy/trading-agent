"""Functional-suite fixtures: opt-in flag, frozen-contract sentinel, sandbox.

Hard guarantees enforced here:

1. **Opt-in**: every test under ``tests/functional/`` is skipped unless
   ``--run-functional`` is passed to pytest. Default ``pytest -q`` runs
   are unaffected.
2. **Frozen-contract md5 sentinel**: package-scope autouse fixture
   md5s the production frozen contracts at session start and end and
   hard-fails on any change.
3. **Sandbox + path monkeypatch**: per-test fixture that builds a
   synthetic ``research/`` tree under ``workspace_tmp_path`` and
   re-binds every PATH constant the diagnostics CLI touches. Mirrors
   the canonical pattern from
   ``tests/unit/test_observability_no_other_artifacts_mutated.py``.

Imports stay within the harness allowlist (stdlib, pytest,
``research._sidecar_io``, ``research.diagnostics.*``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Opt-in flag
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-functional",
        action="store_true",
        default=False,
        help="Run the tests/functional/ suite. Skipped by default.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-functional"):
        return
    skip = pytest.mark.skip(
        reason="functional suite — opt in with --run-functional"
    )
    here = Path(__file__).resolve().parent
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except (OSError, ValueError):
            continue
        try:
            item_path.relative_to(here)
        except ValueError:
            continue
        item.add_marker(skip)


# ---------------------------------------------------------------------------
# Frozen-contract md5 sentinel — package scope, autouse
# ---------------------------------------------------------------------------


_FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def _md5_of(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return None


@pytest.fixture(scope="package", autouse=True)
def frozen_contract_sentinel():
    """Hard-fail if any frozen contract is mutated during the suite.

    Operates on the *production* file paths under the repository root.
    Functional tests run in a sandbox (per-test fixture below) so they
    must never touch these. Defense in depth: even if a future code
    change accidentally bypasses the sandbox (e.g. a default-arg
    pinned to the production path), this sentinel catches it.
    """
    repo_root = Path(__file__).resolve().parents[2]
    targets = [repo_root / rel for rel in _FROZEN_CONTRACTS]
    before = {p.name: _md5_of(p) for p in targets}
    yield
    after = {p.name: _md5_of(p) for p in targets}
    diff = {
        name: (before[name], after[name])
        for name in before
        if before[name] != after[name]
    }
    assert not diff, (
        f"frozen contract mutated during functional run: {diff}"
    )


# ---------------------------------------------------------------------------
# Sandbox dataclass + per-test fixture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionalSandbox:
    """Resolved paths inside the per-test sandbox."""

    research_dir: Path
    observability_dir: Path
    registry_path: Path
    queue_path: Path
    digest_path: Path
    ledger_path: Path
    artifact_health_path: Path
    failure_modes_path: Path
    throughput_metrics_path: Path
    system_integrity_path: Path
    observability_summary_path: Path


@pytest.fixture
def sandbox(workspace_tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FunctionalSandbox:
    """Build a synthetic ``research/`` tree under workspace_tmp_path and
    monkeypatch every PATH constant the diagnostics layer reads."""
    research = workspace_tmp_path / "research"
    obs = research / "observability"
    research.mkdir()
    obs.mkdir()

    # Lazy imports — we keep the harness within the import allowlist by
    # only importing diagnostics.* + _sidecar_io.
    from research.diagnostics import (
        aggregator as agg_mod,
        artifact_health as ah_mod,
        cli as cli_mod,
        failure_modes as fm_mod,
        paths as paths_mod,
        system_integrity as si_mod,
        throughput as tp_mod,
    )

    # --- paths module: single source of truth ---
    monkeypatch.setattr(paths_mod, "RESEARCH_DIR", research)
    monkeypatch.setattr(paths_mod, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        paths_mod, "ARTIFACT_HEALTH_PATH", obs / "artifact_health_latest.v1.json"
    )
    monkeypatch.setattr(
        paths_mod, "FAILURE_MODES_PATH", obs / "failure_modes_latest.v1.json"
    )
    monkeypatch.setattr(
        paths_mod,
        "THROUGHPUT_METRICS_PATH",
        obs / "throughput_metrics_latest.v1.json",
    )
    monkeypatch.setattr(
        paths_mod,
        "SYSTEM_INTEGRITY_PATH",
        obs / "system_integrity_latest.v1.json",
    )
    monkeypatch.setattr(
        paths_mod,
        "OBSERVABILITY_SUMMARY_PATH",
        obs / "observability_summary_latest.v1.json",
    )
    monkeypatch.setattr(
        paths_mod,
        "CAMPAIGN_REGISTRY_PATH",
        research / "campaign_registry_latest.v1.json",
    )
    monkeypatch.setattr(
        paths_mod,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research / "campaign_evidence_ledger.jsonl",
    )

    # --- per-module re-bindings (each module imported the constant by
    # name at import time, so monkeypatching paths_mod alone is not
    # enough; this mirrors test_observability_no_other_artifacts_mutated). ---

    # artifact_health
    monkeypatch.setattr(
        ah_mod, "ARTIFACT_HEALTH_PATH", obs / "artifact_health_latest.v1.json"
    )
    monkeypatch.setattr(
        ah_mod,
        "INPUT_ARTIFACTS",
        (
            (
                "research_latest.json",
                "frozen_public_contract",
                research / "research_latest.json",
            ),
            (
                "strategy_matrix.csv",
                "frozen_public_contract",
                research / "strategy_matrix.csv",
            ),
            (
                "campaign_registry_latest.v1.json",
                "campaign_artifact",
                research / "campaign_registry_latest.v1.json",
            ),
            (
                "campaign_evidence_ledger.jsonl",
                "evidence_artifact",
                research / "campaign_evidence_ledger.jsonl",
            ),
        ),
    )
    # failure_modes
    monkeypatch.setattr(
        fm_mod, "CAMPAIGN_REGISTRY_PATH", research / "campaign_registry_latest.v1.json"
    )
    monkeypatch.setattr(
        fm_mod,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research / "campaign_evidence_ledger.jsonl",
    )
    monkeypatch.setattr(
        fm_mod, "FAILURE_MODES_PATH", obs / "failure_modes_latest.v1.json"
    )
    # throughput
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_REGISTRY_PATH", research / "campaign_registry_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_QUEUE_PATH", research / "campaign_queue_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_DIGEST_PATH", research / "campaign_digest_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod,
        "THROUGHPUT_METRICS_PATH",
        obs / "throughput_metrics_latest.v1.json",
    )
    # system_integrity
    monkeypatch.setattr(si_mod, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        si_mod, "SYSTEM_INTEGRITY_PATH", obs / "system_integrity_latest.v1.json"
    )
    # aggregator
    monkeypatch.setattr(
        agg_mod,
        "OBSERVABILITY_SUMMARY_PATH",
        obs / "observability_summary_latest.v1.json",
    )
    monkeypatch.setattr(
        agg_mod,
        "ACTIVE_COMPONENTS",
        (
            (
                "artifact_health",
                "artifact-health",
                obs / "artifact_health_latest.v1.json",
            ),
            (
                "failure_modes",
                "failure-modes",
                obs / "failure_modes_latest.v1.json",
            ),
            (
                "throughput_metrics",
                "throughput",
                obs / "throughput_metrics_latest.v1.json",
            ),
            (
                "system_integrity",
                "system-integrity",
                obs / "system_integrity_latest.v1.json",
            ),
        ),
    )
    # cli
    monkeypatch.setattr(cli_mod, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        cli_mod, "OBSERVABILITY_SUMMARY_PATH", obs / "observability_summary_latest.v1.json"
    )

    return FunctionalSandbox(
        research_dir=research,
        observability_dir=obs,
        registry_path=research / "campaign_registry_latest.v1.json",
        queue_path=research / "campaign_queue_latest.v1.json",
        digest_path=research / "campaign_digest_latest.v1.json",
        ledger_path=research / "campaign_evidence_ledger.jsonl",
        artifact_health_path=obs / "artifact_health_latest.v1.json",
        failure_modes_path=obs / "failure_modes_latest.v1.json",
        throughput_metrics_path=obs / "throughput_metrics_latest.v1.json",
        system_integrity_path=obs / "system_integrity_latest.v1.json",
        observability_summary_path=obs / "observability_summary_latest.v1.json",
    )


# ---------------------------------------------------------------------------
# Diagnostics build orchestration helper
# ---------------------------------------------------------------------------


def run_diagnostics_build(
    sandbox: FunctionalSandbox, *, now_utc: datetime
) -> None:
    """Drive a complete diagnostics build over ``sandbox`` using the
    pure-function APIs with explicit paths.

    Functionally equivalent to ``research.diagnostics.cli.cmd_build``
    for the output artifacts, but parameterised on the sandbox paths
    rather than depending on default-argument resolution. cmd_build
    itself is already exercised by
    ``tests/unit/test_observability_cli.py``.
    """
    from research.diagnostics import (
        aggregator as agg_mod,
        artifact_health as ah_mod,
        failure_modes as fm_mod,
        io as io_mod,
        paths as paths_mod,
        system_integrity as si_mod,
        throughput as tp_mod,
    )

    # 1) artifact_health
    ah_payload = ah_mod.inspect_artifact_health(
        now_utc=now_utc, artifacts=ah_mod.INPUT_ARTIFACTS
    )
    ah_mod.write_artifact_health(ah_payload, path=sandbox.artifact_health_path)

    # 2) failure_modes — read inputs explicitly + call the pure compute fn
    reg = io_mod.read_json_safe(sandbox.registry_path)
    led = io_mod.read_jsonl_tail_safe(
        sandbox.ledger_path,
        max_lines=paths_mod.MAX_LEDGER_LINES,
        max_tail_bytes=paths_mod.MAX_LEDGER_TAIL_BYTES,
    )
    fm_payload = fm_mod.compute_failure_mode_distribution(
        registry_payload=reg.payload if reg.state == "valid" else None,
        ledger_events=led.events,
        registry_state=reg.state,
        ledger_state=led.state,
        ledger_meta={
            "lines_consumed": led.lines_consumed,
            "truncated": led.truncated,
            "partial_trailing_line_dropped": led.partial_trailing_line_dropped,
            "parse_errors": led.parse_errors,
        },
        now_utc=now_utc,
    )
    fm_mod.write_failure_modes(fm_payload, path=sandbox.failure_modes_path)

    # 3) throughput
    queue = io_mod.read_json_safe(sandbox.queue_path)
    digest = io_mod.read_json_safe(sandbox.digest_path)
    tp_payload = tp_mod.compute_throughput_metrics(
        registry_payload=reg.payload if reg.state == "valid" else None,
        queue_payload=queue.payload if queue.state == "valid" else None,
        digest_payload=digest.payload if digest.state == "valid" else None,
        registry_state=reg.state,
        queue_state=queue.state,
        digest_state=digest.state,
        now_utc=now_utc,
    )
    tp_mod.write_throughput(tp_payload, path=sandbox.throughput_metrics_path)

    # 4) system_integrity
    si_payload = si_mod.build_system_integrity_snapshot(now_utc=now_utc)
    si_mod.write_system_integrity(si_payload, path=sandbox.system_integrity_path)

    # 5) aggregator summary — uses module-level ACTIVE_COMPONENTS
    # (already monkeypatched by the sandbox fixture)
    summary = agg_mod.build_observability_summary(now_utc=now_utc)
    agg_mod.write_observability_summary(
        summary, path=sandbox.observability_summary_path
    )
