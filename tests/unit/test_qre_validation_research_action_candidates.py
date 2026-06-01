from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_candidates as hyp
from reporting import qre_hypothesis_validation_plan as plan
from reporting import qre_market_observation_snapshot as market
from reporting import qre_observation_hypothesis_projector as proj
from reporting import qre_validation_research_action_candidates as action


FROZEN = "2026-06-01T12:00:00Z"


def _plan(**overrides) -> dict:
    base = {
        "validation_plan_id": "qre-plan-fixture-001",
        "hypothesis_id": "qre-hyp-fixture-001",
        "required_experiments": ["sample_size_sufficiency_check_plan"],
        "asset_scope": ["BTC-USD"],
        "timeframe_scope": ["1h"],
        "minimum_trade_count": 100,
        "primary_metrics": ["deflated_sharpe", "trade_count"],
        "falsification_criteria": "Insufficient sample after expansion.",
        "status": "planned",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_plans(path: Path, plans: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_hypothesis_validation_plan",
        "generated_at_utc": FROZEN,
        "validation_plans": plans,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _assert_safety_flags_false(snapshot: dict) -> None:
    for key in (
        "safe_to_execute",
        "writes_development_work_queue",
        "writes_seed_jsonl",
        "writes_generated_seed_jsonl",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    snap = action.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["action_candidates"] == []
    assert snap["safe_to_execute"] is False
    assert snap["writes_research_action_queue"] is False
    assert action.NOTE_INPUT_ABSENT in snap["validation_warnings"]


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_plans(tmp_path / "plans.json", [], report_kind="wrong")

    snap = action.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["input_artifact_available"] is True
    assert snap["action_candidates"] == []
    assert action.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_plans(tmp_path / "plans.json", [_plan()])

    snap_a = action.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = action.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["action_candidates"][0]
    assert row["action_id"].startswith("qre-action-")
    assert row["target_hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["target_validation_plan_id"] == "qre-plan-fixture-001"
    assert row["status"] == "pending"
    assert row["outcome_status"] == "not_recorded"
    assert row["operator_approval_required"] is True
    assert row["safe_to_execute"] is False
    assert row["eligible_for_direct_execution"] is False
    assert set(action.FORBIDDEN_ACTIONS) <= set(row["forbidden_actions"])


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        action._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_plans(tmp_path / "plans.json", [_plan()])
    artifact_dir = tmp_path / "logs" / "qre_validation_research_action_candidates"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(action, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(action, "ARTIFACT_LATEST", latest)

    rc = action.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["action_candidates"][0]["operator_approval_required"] is True


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(action.__file__).read_text(encoding="utf-8")
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
    src = Path(action.__file__).read_text(encoding="utf-8")
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


def test_integration_synthetic_observation_to_action_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    market_dir = logs_dir / "qre_market_observations"
    hyp_dir = logs_dir / "qre_hypothesis_candidates"
    proj_dir = logs_dir / "qre_observation_hypothesis_projection"
    plan_dir = logs_dir / "qre_hypothesis_validation_plans"
    action_dir = logs_dir / "qre_validation_research_action_candidates"
    monkeypatch.setattr(market, "ARTIFACT_DIR", market_dir)
    monkeypatch.setattr(market, "ARTIFACT_LATEST", market_dir / "latest.json")
    monkeypatch.setattr(hyp, "ARTIFACT_DIR", hyp_dir)
    monkeypatch.setattr(hyp, "ARTIFACT_LATEST", hyp_dir / "latest.json")
    monkeypatch.setattr(proj, "ARTIFACT_DIR", proj_dir)
    monkeypatch.setattr(proj, "ARTIFACT_LATEST", proj_dir / "latest.json")
    monkeypatch.setattr(plan, "ARTIFACT_DIR", plan_dir)
    monkeypatch.setattr(plan, "ARTIFACT_LATEST", plan_dir / "latest.json")
    monkeypatch.setattr(action, "ARTIFACT_DIR", action_dir)
    monkeypatch.setattr(action, "ARTIFACT_LATEST", action_dir / "latest.json")

    source = tmp_path / "synthetic_market_source.json"
    source.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "observation_type": "low_trade_count",
                        "asset_scope": ["BTC-USD"],
                        "timeframe_scope": ["4h"],
                        "regime_tags": ["trend"],
                        "metric_refs": ["total_trades:19"],
                        "summary": "The fold has too few trades for durable validation.",
                        "confidence": 0.8,
                        "supporting_evidence_refs": ["fixture#low-count"],
                        "contradicting_evidence_refs": [],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    market_snap = market.collect_snapshot(source_path=source, generated_at_utc=FROZEN)
    market.write_outputs(market_snap)
    hyp_snap = hyp.collect_snapshot(
        input_artifact_path=market.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    hyp.write_outputs(hyp_snap)
    proj_snap = proj.collect_snapshot(
        input_artifact_path=market.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    proj.write_outputs(proj_snap)
    plan_snap = plan.collect_snapshot(
        input_artifact_path=hyp.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    plan.write_outputs(plan_snap)
    action_snap = action.collect_snapshot(
        input_artifact_path=plan.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    action.write_outputs(action_snap)

    for snap in [market_snap, hyp_snap, proj_snap, plan_snap, action_snap]:
        _assert_safety_flags_false(snap)

    observation = market_snap["observations"][0]
    hypothesis = hyp_snap["hypotheses"][0]
    projection = proj_snap["projection_rows"][0]
    validation_plan = plan_snap["validation_plans"][0]
    candidate = action_snap["action_candidates"][0]

    assert hypothesis["source_observation_id"] == observation["observation_id"]
    assert projection["observation_id"] == observation["observation_id"]
    assert projection["proposed_hypothesis_id"] == hypothesis["hypothesis_id"]
    assert validation_plan["hypothesis_id"] == hypothesis["hypothesis_id"]
    assert candidate["target_hypothesis_id"] == hypothesis["hypothesis_id"]
    assert candidate["target_validation_plan_id"] == validation_plan["validation_plan_id"]
    assert candidate["operator_approval_required"] is True
    assert candidate["eligible_for_direct_execution"] is False

    allowed_dirs = {
        "qre_market_observations",
        "qre_hypothesis_candidates",
        "qre_observation_hypothesis_projection",
        "qre_hypothesis_validation_plans",
        "qre_validation_research_action_candidates",
    }
    written = [path for path in logs_dir.rglob("*") if path.is_file()]
    assert {path.parent.name for path in written} <= allowed_dirs
    assert {path.name for path in written} == {"latest.json"}
