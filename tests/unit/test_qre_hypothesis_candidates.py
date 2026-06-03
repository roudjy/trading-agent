from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_candidates as hyp

FROZEN = "2026-06-01T12:00:00Z"


def _observation(**overrides) -> dict:
    base = {
        "observation_id": "qre-obs-fixture-001",
        "source_artifact": "fixture.json",
        "observation_type": "exit_failure_pattern",
        "asset_scope": ["BTC-USD"],
        "timeframe_scope": ["1h"],
        "regime_tags": ["trend"],
        "metric_refs": ["sharpe:-1.0"],
        "summary": "Exit rules appear to degrade the trend edge.",
        "confidence": 0.7,
        "supporting_evidence_refs": ["fixture#1"],
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
    snap = hyp.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["hypotheses"] == []
    assert snap["safe_to_execute"] is False
    assert snap["launches_codex"] is False
    assert hyp.NOTE_INPUT_ABSENT in snap["validation_warnings"]


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "obs.json", [], report_kind="wrong")

    snap = hyp.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["input_artifact_available"] is True
    assert snap["hypotheses"] == []
    assert hyp.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]
    assert snap["safe_to_execute"] is False


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "obs.json", [_observation()])

    snap_a = hyp.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = hyp.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["hypotheses"][0]
    assert row["hypothesis_id"].startswith("qre-hyp-")
    assert row["source_observation_id"] == "qre-obs-fixture-001"
    assert row["status"] == "proposed"
    assert row["validation_plan_required"] is True
    assert row["safe_to_execute"] is False


def test_explicit_executable_bridge_fields_are_preserved_when_present(
    tmp_path: Path,
) -> None:
    source = _write_observations(
        tmp_path / "obs.json",
        [
            _observation(
                executable_hypothesis_id="trend_pullback_v1",
                source_hypothesis_id="source-trend-pullback",
                strategy_family="trend",
                strategy_template_id="trend_pullback",
                preset_name="trend_pullback_crypto_1h",
            )
        ],
    )

    snap = hyp.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    row = snap["hypotheses"][0]
    assert row["executable_hypothesis_id"] == "trend_pullback_v1"
    assert row["source_hypothesis_id"] == "source-trend-pullback"
    assert row["strategy_family"] == "trend"
    assert row["strategy_template_id"] == "trend_pullback"
    assert row["preset_name"] == "trend_pullback_crypto_1h"


def test_executable_bridge_fields_are_not_invented_when_absent(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "obs.json", [_observation()])

    snap = hyp.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    row = snap["hypotheses"][0]
    for field in hyp.OPTIONAL_BRIDGE_FIELDS:
        assert field not in row


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        hyp._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_observations(tmp_path / "obs.json", [_observation()])
    artifact_dir = tmp_path / "logs" / "qre_hypothesis_candidates"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(hyp, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(hyp, "ARTIFACT_LATEST", latest)

    rc = hyp.main(["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"])

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["hypotheses"][0]["status"] == "proposed"


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(hyp.__file__).read_text(encoding="utf-8")
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
    src = Path(hyp.__file__).read_text(encoding="utf-8")
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
