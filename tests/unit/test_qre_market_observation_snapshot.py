from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_candidates as hyp
from reporting import qre_market_observation_snapshot as market
from research.screening_evidence import build_qre_validation_linkage_authority

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
    assert "executable_hypothesis_id" not in observation


def test_fixture_observation_preserves_explicit_executable_identity_fields(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path / "source.json",
        [
            _observation(
                executable_hypothesis_id="trend_pullback_v1",
                source_hypothesis_id="source-trend-pullback",
                strategy_family="trend_pullback",
                strategy_template_id="trend_pullback_template",
                preset_name="trend_pullback_crypto_1h",
                candidate_id="candidate-001",
                strategy_id="strategy-001",
            )
        ],
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    assert observation["executable_hypothesis_id"] == "trend_pullback_v1"
    assert observation["source_hypothesis_id"] == "source-trend-pullback"
    assert observation["strategy_family"] == "trend_pullback"
    assert observation["strategy_template_id"] == "trend_pullback_template"
    assert observation["preset_name"] == "trend_pullback_crypto_1h"
    assert observation["candidate_id"] == "candidate-001"
    assert observation["strategy_id"] == "strategy-001"


def test_fixture_observation_does_not_infer_identity_from_alias_like_fields(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path / "source.json",
        [
            _observation(
                family="trend",
                strategy_name="trend_pullback_v1",
                hypothesis_id="runtime-hypothesis-id",
            )
        ],
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    assert "strategy_family" not in observation
    assert "strategy_template_id" not in observation
    assert "executable_hypothesis_id" not in observation
    assert "hypothesis_id" not in observation


def test_fixture_observation_drops_malformed_identity_fields(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path / "source.json",
        [
            _observation(
                executable_hypothesis_id={"not": "scalar"},
                source_hypothesis_id=["not-scalar"],
                strategy_family=True,
                strategy_template_id=None,
            )
        ],
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    for field in market.OPTIONAL_EXECUTABLE_IDENTITY_FIELDS:
        assert field not in observation


def test_fixture_observation_bounds_identity_field_values(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path / "source.json",
        [
            _observation(
                executable_hypothesis_id="x" * 500,
                preset_name="p" * 500,
            )
        ],
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    assert len(observation["executable_hypothesis_id"]) <= 160
    assert len(observation["preset_name"]) <= 160


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


def test_research_latest_input_preserves_only_explicit_identity_fields(
    tmp_path: Path,
) -> None:
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
                        "executable_hypothesis_id": "trend_pullback_v1",
                        "source_hypothesis_id": "source-trend-pullback",
                        "strategy_family": "trend_pullback",
                        "strategy_template_id": "trend_pullback_template",
                        "preset_name": "trend_pullback_crypto_1h",
                        "candidate_id": "candidate-001",
                        "strategy_id": "strategy-001",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    assert snap["observations"]
    for observation in snap["observations"]:
        assert observation["executable_hypothesis_id"] == "trend_pullback_v1"
        assert observation["source_hypothesis_id"] == "source-trend-pullback"
        assert observation["strategy_family"] == "trend_pullback"
        assert observation["strategy_template_id"] == "trend_pullback_template"
        assert observation["preset_name"] == "trend_pullback_crypto_1h"
        assert observation["candidate_id"] == "candidate-001"
        assert observation["strategy_id"] == "strategy-001"


def test_research_latest_input_does_not_infer_strategy_family_or_template(
    tmp_path: Path,
) -> None:
    source = tmp_path / "research_latest.json"
    source.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "success": True,
                        "strategy_name": "trend_pullback_v1",
                        "family": "trend",
                        "asset": "BTC-USD",
                        "interval": "4h",
                        "trades_per_maand": 0.5,
                        "totaal_trades": 19,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    assert snap["observations"]
    for observation in snap["observations"]:
        assert "strategy_family" not in observation
        assert "strategy_template_id" not in observation
        assert "executable_hypothesis_id" not in observation


def test_candidate_source_input_preserves_explicit_executable_identity_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run_candidates_latest.v1.json"
    source.write_text(
        json.dumps(
            {
                "version": "v1",
                "candidates": [
                    {
                        "candidate_id": "candidate-001",
                        "current_status": "planned",
                        "strategy_name": "trend_pullback_v1",
                        "strategy_family": "trend_pullback",
                        "strategy_template_id": "trend_pullback_v1",
                        "preset_name": "trend_pullback_crypto_1h",
                        "asset": "BTC-EUR",
                        "interval": "1h",
                        "executable_hypothesis_id": "trend_pullback_v1",
                        "source_hypothesis_id": "source-trend-pullback",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    assert observation["source_artifact"].endswith("run_candidates_latest.v1.json")
    assert observation["supporting_evidence_refs"] == [
        f"{observation['source_artifact']}#candidate-001"
    ]
    assert observation["asset_scope"] == ["BTC-EUR"]
    assert observation["timeframe_scope"] == ["1h"]
    assert observation["executable_hypothesis_id"] == "trend_pullback_v1"
    assert observation["source_hypothesis_id"] == "source-trend-pullback"
    assert observation["strategy_family"] == "trend_pullback"
    assert observation["strategy_template_id"] == "trend_pullback_v1"
    assert observation["preset_name"] == "trend_pullback_crypto_1h"
    assert observation["candidate_id"] == "candidate-001"


def test_candidate_source_input_does_not_infer_identity_from_alias_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run_candidates_latest.v1.json"
    source.write_text(
        json.dumps(
            {
                "version": "v1",
                "candidates": [
                    {
                        "candidate_id": "candidate-001",
                        "strategy_name": "trend_pullback_v1",
                        "family": "trend",
                        "hypothesis_id": "trend_pullback_v1",
                        "asset": "BTC-EUR",
                        "interval": "1h",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)

    observation = snap["observations"][0]
    assert "executable_hypothesis_id" not in observation
    assert "strategy_template_id" not in observation
    assert "strategy_family" not in observation


def test_explicit_identity_fixture_chain_reaches_hypothesis_bridge_authority(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path / "source.json",
        [
            _observation(
                executable_hypothesis_id="trend_pullback_v1",
                source_hypothesis_id="source-trend-pullback",
                strategy_family="trend_pullback",
                strategy_template_id="trend_pullback_template",
                preset_name="trend_pullback_crypto_1h",
            )
        ],
    )

    market_snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)
    market_artifact = tmp_path / "market_observations.json"
    market_artifact.write_text(json.dumps(market_snap), encoding="utf-8")
    hyp_snap = hyp.collect_snapshot(
        input_artifact_path=market_artifact,
        generated_at_utc=FROZEN,
    )
    hypothesis = hyp_snap["hypotheses"][0]
    plan_id = "qre-plan-fixture"
    run_id = "qre-run-fixture"

    authority = build_qre_validation_linkage_authority(
        hypothesis_candidates_payload=hyp_snap,
        validation_plans_payload={
            "report_kind": "qre_hypothesis_validation_plan",
            "validation_plans": [
                {
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "validation_plan_id": plan_id,
                }
            ],
        },
        run_manifest_payload={
            "report_kind": "qre_research_run_manifest",
            "run_manifests": [
                {
                    "run_manifest_id": run_id,
                    "target_validation_plan_id": plan_id,
                }
            ],
        },
    )

    assert market_snap["observations"][0]["executable_hypothesis_id"] == ("trend_pullback_v1")
    assert hypothesis["executable_hypothesis_id"] == "trend_pullback_v1"
    bridge = authority["by_executable_hypothesis_id"]["trend_pullback_v1"]
    assert bridge["bridge_status"] == "bridge_exact"
    assert bridge["qre_hypothesis_id"] == hypothesis["hypothesis_id"]
    assert bridge["validation_plan_id"] == plan_id
    assert bridge["run_manifest_id"] == run_id


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
