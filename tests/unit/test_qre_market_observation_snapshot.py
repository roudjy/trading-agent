from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_market_observation_snapshot as market


FROZEN = "2026-06-01T12:00:00Z"


def _write_source(path: Path, observations: list[dict]) -> Path:
    path.write_text(
        json.dumps({"observations": observations}, indent=2),
        encoding="utf-8",
    )
    return path


def _observation(**overrides) -> dict:
    base = {
        "observation_type": "low_trade_count",
        "asset_scope": ["BTC-USD"],
        "timeframe_scope": ["4h"],
        "regime_tags": ["trend"],
        "metric_refs": ["total_trades:19"],
        "summary": "Trend pullback has limited sample support on BTC-USD 4h.",
        "confidence": 0.8,
        "supporting_evidence_refs": ["fixture#btc-4h"],
        "contradicting_evidence_refs": [],
    }
    base.update(overrides)
    return base


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    snap = market.collect_snapshot(
        source_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["observations"] == []
    assert snap["safe_to_execute"] is False
    assert snap["launches_codex"] is False
    assert snap["eligible_for_direct_execution"] is False
    assert market.NOTE_INPUT_ABSENT in snap["validation_warnings"]


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text("{", encoding="utf-8")

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    assert snap["input_artifact_available"] is True
    assert snap["observations"] == []
    assert market.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]
    assert snap["safe_to_execute"] is False


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source.json", [_observation()])

    snap_a = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)
    snap_b = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    observation = snap_a["observations"][0]
    assert observation["observation_id"].startswith("qre-obs-")
    assert observation["observation_type"] == "low_trade_count"
    assert observation["safe_to_execute"] is False


def test_research_latest_input_projects_observations(tmp_path: Path) -> None:
    source = tmp_path / "research_latest.json"
    source.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "success": True,
                        "strategy_name": "trend_pullback_tp_sl",
                        "family": "trend",
                        "asset": "BTC-USD",
                        "interval": "4h",
                        "win_rate": 0.3,
                        "sharpe": -0.5,
                        "deflated_sharpe": -0.4,
                        "trades_per_maand": 0.5,
                        "totaal_trades": 19,
                        "consistentie": 0.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    types = {row["observation_type"] for row in snap["observations"]}
    assert {
        "exit_failure_pattern",
        "low_trade_count",
        "high_window_end_impact",
    } <= types


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        market._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_source(tmp_path / "source.json", [_observation()])
    artifact_dir = tmp_path / "logs" / "qre_market_observations"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(market, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(market, "ARTIFACT_LATEST", latest)

    rc = market.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == market.REPORT_KIND


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(market.__file__).read_text(encoding="utf-8")
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
    src = Path(market.__file__).read_text(encoding="utf-8")
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
