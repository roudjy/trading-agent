"""End-to-end single-tick integration test for the campaign launcher.

Runs the launcher inside a temp workspace with ``--no-subprocess`` so no
real research pipeline is invoked; verifies the full artifact chain
(registry + queue + ledger + decision + digest + budget) comes out
healthy and consistent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_launcher(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root), env.get("PYTHONPATH", "")]
    )
    return subprocess.run(
        [sys.executable, "-m", "research.campaign_launcher", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research" / ".locks").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_first_tick_spawns_daily_primary(workspace: Path) -> None:
    result = _run_launcher(workspace, ["--no-subprocess"])
    assert result.returncode == 0, result.stderr

    registry_path = workspace / "research" / "campaign_registry_latest.v1.json"
    queue_path = workspace / "research" / "campaign_queue_latest.v1.json"
    ledger_path = workspace / "research" / "campaign_evidence_ledger_latest.v1.jsonl"
    digest_path = workspace / "research" / "campaign_digest_latest.v1.json"
    decision_path = workspace / "research" / "campaign_policy_decision_latest.v1.json"
    templates_path = workspace / "research" / "campaign_templates_latest.v1.json"

    for path in (registry_path, queue_path, ledger_path, digest_path, decision_path, templates_path):
        assert path.exists(), f"missing artifact {path.name}"

    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["decision"]["action"] == "spawn"
    assert decision["decision"]["campaign_type"] == "daily_primary"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    campaigns = registry["campaigns"]
    assert len(campaigns) == 1
    record = next(iter(campaigns.values()))
    assert record["state"] == "leased"
    assert record["campaign_type"] == "daily_primary"
    assert record["priority_tier"] == 2

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(queue["queue"]) == 1
    assert queue["queue"][0]["state"] == "leased"

    ledger_lines = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = {ev["event_type"] for ev in ledger_lines}
    assert {"campaign_spawned", "campaign_leased"} <= event_types


def test_second_tick_respects_single_worker(workspace: Path) -> None:
    first = _run_launcher(workspace, ["--no-subprocess"])
    assert first.returncode == 0, first.stderr
    second = _run_launcher(workspace, ["--no-subprocess"])
    assert second.returncode == 0, second.stderr

    decision_path = workspace / "research" / "campaign_policy_decision_latest.v1.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["decision"]["action"] == "idle_noop"
    assert decision["decision"]["reason"] == "worker_busy"


def test_dry_run_mutates_nothing(workspace: Path) -> None:
    result = _run_launcher(workspace, ["--dry-run"])
    assert result.returncode == 0, result.stderr
    assert not (workspace / "research" / "campaign_registry_latest.v1.json").exists()
    assert not (workspace / "research" / "campaign_evidence_ledger_latest.v1.jsonl").exists()


def test_ledger_append_is_idempotent_across_ticks(workspace: Path) -> None:
    first = _run_launcher(workspace, ["--no-subprocess"])
    assert first.returncode == 0, first.stderr
    ledger_path = workspace / "research" / "campaign_evidence_ledger_latest.v1.jsonl"
    first_bytes = ledger_path.read_bytes()

    # Second tick is worker_busy → no new events, ledger unchanged.
    second = _run_launcher(workspace, ["--no-subprocess"])
    assert second.returncode == 0, second.stderr
    assert ledger_path.read_bytes() == first_bytes
