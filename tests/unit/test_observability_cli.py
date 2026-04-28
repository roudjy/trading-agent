"""Unit tests for research.diagnostics.cli."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics import (
    aggregator as agg_mod,
    artifact_health as ah_mod,
    cli as cli_mod,
    failure_modes as fm_mod,
    paths as paths_mod,
    system_integrity as si_mod,
    throughput as tp_mod,
)


@pytest.fixture
def isolated_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    research_root = tmp_path / "research"
    obs = research_root / "observability"
    research_root.mkdir(parents=True)
    obs.mkdir()

    monkeypatch.setattr(paths_mod, "RESEARCH_DIR", research_root)
    monkeypatch.setattr(paths_mod, "OBSERVABILITY_DIR", obs)
    for attr in ("ARTIFACT_HEALTH_PATH", "FAILURE_MODES_PATH", "THROUGHPUT_METRICS_PATH",
                 "SYSTEM_INTEGRITY_PATH", "OBSERVABILITY_SUMMARY_PATH"):
        monkeypatch.setattr(
            paths_mod, attr, obs / getattr(paths_mod, attr).name
        )
    monkeypatch.setattr(
        paths_mod, "CAMPAIGN_REGISTRY_PATH", research_root / "campaign_registry_latest.v1.json"
    )
    monkeypatch.setattr(
        paths_mod,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research_root / "campaign_evidence_ledger.jsonl",
    )

    # Re-bind in modules that already imported the constants.
    monkeypatch.setattr(ah_mod, "ARTIFACT_HEALTH_PATH", obs / "artifact_health_latest.v1.json")
    monkeypatch.setattr(
        ah_mod,
        "INPUT_ARTIFACTS",
        (
            (
                "research_latest.json",
                "frozen_public_contract",
                research_root / "research_latest.json",
            ),
        ),
    )
    monkeypatch.setattr(
        fm_mod, "CAMPAIGN_REGISTRY_PATH", research_root / "campaign_registry_latest.v1.json"
    )
    monkeypatch.setattr(
        fm_mod,
        "CAMPAIGN_EVIDENCE_LEDGER_PATH",
        research_root / "campaign_evidence_ledger.jsonl",
    )
    monkeypatch.setattr(
        fm_mod, "FAILURE_MODES_PATH", obs / "failure_modes_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_REGISTRY_PATH", research_root / "campaign_registry_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_QUEUE_PATH", research_root / "campaign_queue_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "CAMPAIGN_DIGEST_PATH", research_root / "campaign_digest_latest.v1.json"
    )
    monkeypatch.setattr(
        tp_mod, "THROUGHPUT_METRICS_PATH", obs / "throughput_metrics_latest.v1.json"
    )
    monkeypatch.setattr(si_mod, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        si_mod, "SYSTEM_INTEGRITY_PATH", obs / "system_integrity_latest.v1.json"
    )
    monkeypatch.setattr(
        agg_mod, "OBSERVABILITY_SUMMARY_PATH", obs / "observability_summary_latest.v1.json"
    )
    monkeypatch.setattr(
        cli_mod, "OBSERVABILITY_SUMMARY_PATH", obs / "observability_summary_latest.v1.json"
    )
    monkeypatch.setattr(cli_mod, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        agg_mod,
        "ACTIVE_COMPONENTS",
        (
            ("artifact_health", "artifact-health", obs / "artifact_health_latest.v1.json"),
            ("failure_modes", "failure-modes", obs / "failure_modes_latest.v1.json"),
            ("throughput_metrics", "throughput", obs / "throughput_metrics_latest.v1.json"),
            ("system_integrity", "system-integrity", obs / "system_integrity_latest.v1.json"),
        ),
    )
    return research_root


def test_cmd_build_succeeds_on_empty_inputs(isolated_tree: Path):
    rc = cli_mod.cmd_build(now_utc=datetime(2026, 4, 28, tzinfo=UTC))
    assert rc == cli_mod.EXIT_OK
    obs = isolated_tree / "observability"
    expected = {
        "artifact_health_latest.v1.json",
        "failure_modes_latest.v1.json",
        "throughput_metrics_latest.v1.json",
        "system_integrity_latest.v1.json",
        "observability_summary_latest.v1.json",
    }
    actual = {p.name for p in obs.iterdir()}
    assert expected.issubset(actual)


def test_cmd_status_no_summary_returns_ok(isolated_tree: Path, capsys: pytest.CaptureFixture):
    monkey_path = isolated_tree / "observability" / "observability_summary_latest.v1.json"
    if monkey_path.exists():
        monkey_path.unlink()

    rc = cli_mod.cmd_status()
    err = capsys.readouterr().err
    assert rc == cli_mod.EXIT_OK
    assert "no observability summary present" in err


def test_cmd_status_prints_overall(isolated_tree: Path, capsys: pytest.CaptureFixture):
    summary_path = isolated_tree / "observability" / "observability_summary_latest.v1.json"
    summary_path.write_text(
        json.dumps(
            {
                "overall_status": "healthy",
                "component_status_counts": {"available": 4},
                "recommended_next_human_action": "none",
            }
        ),
        encoding="utf-8",
    )
    rc = cli_mod.cmd_status()
    out = capsys.readouterr().out
    assert rc == cli_mod.EXIT_OK
    assert "overall_status: healthy" in out


def test_main_dispatches_subcommands(isolated_tree: Path):
    rc = cli_mod.main(["build"])
    assert rc == cli_mod.EXIT_OK


def test_main_unknown_subcommand_exits_with_parser_error(isolated_tree: Path):
    rc = cli_mod.main(["nonsense"])
    assert rc == cli_mod.EXIT_PARSER_ERROR
