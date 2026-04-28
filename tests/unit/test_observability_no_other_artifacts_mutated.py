"""End-to-end safety: a CLI build mutates ONLY research/observability/.

Snapshots the (relative_path, mtime, size) of every file under a tmp
research tree before and after a CLI build, then asserts that:

* no file under research/ outside research/observability/ was added,
  removed, or modified;
* the only writes are under research/observability/.

This is the strongest read-only guarantee: regardless of what the
modules do internally, the filesystem tells the truth.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics import cli as observability_cli
from research.diagnostics import paths as observability_paths


def _snapshot(root: Path) -> dict[str, tuple[float, int]]:
    out: dict[str, tuple[float, int]] = {}
    for current, _, files in os.walk(root):
        for name in files:
            p = Path(current) / name
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(root).as_posix()
            out[rel] = (st.st_mtime, st.st_size)
    return out


@pytest.fixture
def isolated_research_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a synthetic research/ tree under tmp_path, redirect every
    observability path constant to point inside it, run the CLI, and
    return the snapshot ``before`` state plus the tree root."""

    research_root = tmp_path / "research"
    obs_root = research_root / "observability"
    research_root.mkdir(parents=True)
    obs_root.mkdir()

    # Plant a couple of pre-existing artifacts to verify they are NOT
    # touched by the build.
    (research_root / "research_latest.json").write_text(
        '{"hello": "world"}', encoding="utf-8"
    )
    (research_root / "strategy_matrix.csv").write_text(
        "preset,family\nfoo,bar\n", encoding="utf-8"
    )
    (research_root / "campaign_registry_latest.v1.json").write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "campaign_id": "c1",
                        "preset": "foo",
                        "outcome": "completed",
                        "finished_at_utc": "2026-04-27T10:00:00Z",
                        "started_at_utc": "2026-04-27T09:50:00Z",
                        "runtime_min": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (research_root / "campaign_queue_latest.v1.json").write_text(
        '{"queue": []}', encoding="utf-8"
    )
    (research_root / "campaign_evidence_ledger.jsonl").write_text(
        '{"outcome": "failed", "preset": "foo", "failure_reason": "screening_no_survivors"}\n',
        encoding="utf-8",
    )

    # Redirect EVERY path constant the modules use to the tmp tree.
    monkeypatch.setattr(observability_paths, "RESEARCH_DIR", research_root)
    monkeypatch.setattr(observability_paths, "OBSERVABILITY_DIR", obs_root)
    monkeypatch.setattr(
        observability_paths,
        "ARTIFACT_HEALTH_PATH",
        obs_root / "artifact_health_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "FAILURE_MODES_PATH",
        obs_root / "failure_modes_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "THROUGHPUT_METRICS_PATH",
        obs_root / "throughput_metrics_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "SYSTEM_INTEGRITY_PATH",
        obs_root / "system_integrity_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "OBSERVABILITY_SUMMARY_PATH",
        obs_root / "observability_summary_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "CAMPAIGN_REGISTRY_PATH",
        research_root / "campaign_registry_latest.v1.json",
    )
    monkeypatch.setattr(
        observability_paths,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research_root / "campaign_evidence_ledger.jsonl",
    )

    # Re-bind the path constants the modules already imported by name.
    from research.diagnostics import (
        aggregator as aggregator_mod,
        artifact_health as ah_mod,
        failure_modes as fm_mod,
        system_integrity as si_mod,
        throughput as tp_mod,
    )

    monkeypatch.setattr(
        ah_mod, "ARTIFACT_HEALTH_PATH", obs_root / "artifact_health_latest.v1.json"
    )
    monkeypatch.setattr(
        ah_mod,
        "INPUT_ARTIFACTS",
        (
            (
                "research_latest.json",
                "frozen_public_contract",
                research_root / "research_latest.json",
            ),
            (
                "strategy_matrix.csv",
                "frozen_public_contract",
                research_root / "strategy_matrix.csv",
            ),
            (
                "campaign_registry_latest.v1.json",
                "campaign_artifact",
                research_root / "campaign_registry_latest.v1.json",
            ),
            (
                "campaign_evidence_ledger.jsonl",
                "evidence_artifact",
                research_root / "campaign_evidence_ledger.jsonl",
            ),
        ),
    )
    monkeypatch.setattr(
        fm_mod,
        "CAMPAIGN_REGISTRY_PATH",
        research_root / "campaign_registry_latest.v1.json",
    )
    monkeypatch.setattr(
        fm_mod,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research_root / "campaign_evidence_ledger.jsonl",
    )
    monkeypatch.setattr(
        fm_mod, "FAILURE_MODES_PATH", obs_root / "failure_modes_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod,
        "CAMPAIGN_REGISTRY_PATH",
        research_root / "campaign_registry_latest.v1.json",
    )
    monkeypatch.setattr(
        tp_mod,
        "CAMPAIGN_QUEUE_PATH",
        research_root / "campaign_queue_latest.v1.json",
    )
    monkeypatch.setattr(
        tp_mod,
        "CAMPAIGN_DIGEST_PATH",
        research_root / "campaign_digest_latest.v1.json",
    )
    monkeypatch.setattr(
        tp_mod, "THROUGHPUT_METRICS_PATH", obs_root / "throughput_metrics_latest.v1.json"
    )
    monkeypatch.setattr(
        si_mod, "OBSERVABILITY_DIR", obs_root
    )
    monkeypatch.setattr(
        si_mod,
        "SYSTEM_INTEGRITY_PATH",
        obs_root / "system_integrity_latest.v1.json",
    )
    monkeypatch.setattr(
        aggregator_mod,
        "OBSERVABILITY_SUMMARY_PATH",
        obs_root / "observability_summary_latest.v1.json",
    )
    monkeypatch.setattr(
        aggregator_mod,
        "ACTIVE_COMPONENTS",
        (
            (
                "artifact_health",
                "artifact-health",
                obs_root / "artifact_health_latest.v1.json",
            ),
            (
                "failure_modes",
                "failure-modes",
                obs_root / "failure_modes_latest.v1.json",
            ),
            (
                "throughput_metrics",
                "throughput",
                obs_root / "throughput_metrics_latest.v1.json",
            ),
            (
                "system_integrity",
                "system-integrity",
                obs_root / "system_integrity_latest.v1.json",
            ),
        ),
    )

    return research_root


def test_cli_build_only_writes_under_observability(isolated_research_tree: Path):
    research_root = isolated_research_tree
    obs_root = research_root / "observability"

    before = _snapshot(research_root)

    rc = observability_cli.cmd_build(now_utc=datetime(2026, 4, 28, tzinfo=UTC))
    assert rc == observability_cli.EXIT_OK, "cmd_build should not raise on this tree"

    after = _snapshot(research_root)

    # Every change must live under research/observability/.
    changed = []
    for rel, (mtime, size) in after.items():
        prev = before.get(rel)
        if prev is None or prev != (mtime, size):
            changed.append(rel)
    illegal = [c for c in changed if not c.startswith("observability/")]
    assert not illegal, (
        f"observability build mutated non-observability files: {illegal}"
    )

    # And the observability artifacts must actually have been written.
    expected_outputs = {
        "observability/artifact_health_latest.v1.json",
        "observability/failure_modes_latest.v1.json",
        "observability/throughput_metrics_latest.v1.json",
        "observability/system_integrity_latest.v1.json",
        "observability/observability_summary_latest.v1.json",
    }
    written = {c for c in changed if c.startswith("observability/")}
    assert expected_outputs.issubset(written), (
        f"missing expected observability outputs: {expected_outputs - written}"
    )

    # No file outside research/observability/ was added or removed.
    only_outside = {k for k in before if not k.startswith("observability/")}
    only_outside_after = {k for k in after if not k.startswith("observability/")}
    assert only_outside == only_outside_after, (
        f"non-observability file set changed: "
        f"removed={only_outside - only_outside_after}, "
        f"added={only_outside_after - only_outside}"
    )
