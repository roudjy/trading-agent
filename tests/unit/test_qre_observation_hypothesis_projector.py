from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_observation_hypothesis_projector as proj


FROZEN = "2026-06-01T12:00:00Z"


def _observation(**overrides) -> dict:
    base = {
        "observation_id": "qre-obs-fixture-002",
        "source_artifact": "fixture.json",
        "observation_type": "paper_divergence",
        "asset_scope": ["ETH-USD"],
        "timeframe_scope": ["4h"],
        "regime_tags": ["trend"],
        "metric_refs": ["paper_delta:material"],
        "summary": "Research and paper semantics appear divergent.",
        "confidence": 0.9,
        "supporting_evidence_refs": ["fixture#2"],
        "contradicting_evidence_refs": [],
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_observations(path: Path, observations: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_market_observation_snapshot",
        "generated_at_utc": FROZEN,
        "observations": observations,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    snap = proj.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["projection_rows"] == []
    assert snap["safe_to_execute"] is False
    assert snap["eligible_for_direct_execution"] is False
    assert proj.NOTE_INPUT_ABSENT in snap["validation_warnings"]


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "obs.json", [], report_kind="wrong")

    snap = proj.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["input_artifact_available"] is True
    assert snap["projection_rows"] == []
    assert proj.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "obs.json", [_observation()])

    snap_a = proj.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = proj.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["projection_rows"][0]
    assert row["projection_rule"] == "engine_parity_hypothesis"
    assert row["proposed_hypothesis_id"].startswith("qre-hyp-")
    assert row["status"] == "proposed"
    assert row["safe_to_execute"] is False


def test_rule_mapping_covers_required_observation_types(tmp_path: Path) -> None:
    observations = [
        _observation(observation_id=f"obs-{kind}", observation_type=kind)
        for kind in [
            "exit_failure_pattern",
            "low_trade_count",
            "high_window_end_impact",
            "source_quality_issue",
            "paper_divergence",
        ]
    ]
    source = _write_observations(tmp_path / "obs.json", observations)

    snap = proj.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    rules = {row["projection_rule"] for row in snap["projection_rows"]}
    assert {
        "exit_invalidation_hypothesis",
        "sample_liquidity_hypothesis",
        "fold_window_boundary_hypothesis",
        "data_quality_hypothesis",
        "engine_parity_hypothesis",
    } == rules


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        proj._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_observations(tmp_path / "obs.json", [_observation()])
    artifact_dir = tmp_path / "logs" / "qre_observation_hypothesis_projection"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(proj, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(proj, "ARTIFACT_LATEST", latest)

    rc = proj.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["projection_rows"][0]["safe_to_execute"] is False


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(proj.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token


def test_source_does_not_write_active_or_mutating_paths() -> None:
    src = Path(proj.__file__).read_text(encoding="utf-8")
    forbidden = (
        "seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "agent/backtesting/strategies.py",
        "registry.py",
        "paper/",
        "shadow/",
        "live/",
    )
    for token in forbidden:
        assert token not in src, token
