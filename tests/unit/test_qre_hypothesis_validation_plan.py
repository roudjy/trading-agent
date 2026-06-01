from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_validation_plan as plan


FROZEN = "2026-06-01T12:00:00Z"


def _hypothesis(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "source_observation_id": "qre-obs-fixture-001",
        "title": "Sample and liquidity sufficiency",
        "claim": "The observation may be underpowered because trade count is too low.",
        "asset_scope": ["BTC-USD"],
        "timeframe_scope": ["4h"],
        "regime_tags": ["trend"],
        "expected_edge": "A better-sampled validation can separate weak evidence.",
        "falsification_criteria": "Expanded validation remains unstable.",
        "validation_plan_required": True,
        "supporting_evidence_refs": ["fixture#1"],
        "contradicting_evidence_refs": [],
        "status": "proposed",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_hypotheses(path: Path, hypotheses: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_hypothesis_candidates",
        "generated_at_utc": FROZEN,
        "hypotheses": hypotheses,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    snap = plan.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["validation_plans"] == []
    assert snap["safe_to_execute"] is False
    assert snap["launches_codex"] is False
    assert plan.NOTE_INPUT_ABSENT in snap["validation_warnings"]


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hyp.json", [], report_kind="wrong")

    snap = plan.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["input_artifact_available"] is True
    assert snap["validation_plans"] == []
    assert plan.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hyp.json", [_hypothesis()])

    snap_a = plan.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = plan.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["validation_plans"][0]
    assert row["validation_plan_id"].startswith("qre-plan-")
    assert row["hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["minimum_trade_count"] == 60
    assert row["status"] == "planned"
    assert row["safe_to_execute"] is False


def test_validation_plan_does_not_run_experiments(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hyp.json", [_hypothesis()])

    snap = plan.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    row = snap["validation_plans"][0]
    assert all(item.endswith("_plan") for item in row["required_experiments"])
    assert snap["eligible_for_direct_execution"] is False


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_hypotheses(tmp_path / "hyp.json", [_hypothesis()])
    artifact_dir = tmp_path / "logs" / "qre_hypothesis_validation_plans"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(plan, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(plan, "ARTIFACT_LATEST", latest)

    rc = plan.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["validation_plans"][0]["status"] == "planned"


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(plan.__file__).read_text(encoding="utf-8")
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
    src = Path(plan.__file__).read_text(encoding="utf-8")
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
