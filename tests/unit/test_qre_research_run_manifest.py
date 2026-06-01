from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_research_run_manifest as manifest


FROZEN = "2026-06-01T12:00:00Z"


def _action(**overrides) -> dict:
    base = {
        "action_id": "qre-action-fixture-001",
        "target_hypothesis_id": "qre-hyp-fixture-001",
        "target_validation_plan_id": "qre-plan-fixture-001",
        "status": "pending",
        "forbidden_actions": ["strategy_or_preset_mutation"],
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }
    base.update(overrides)
    return base


def _write_actions(path: Path, actions: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_validation_research_action_candidates",
        "generated_at_utc": FROZEN,
        "action_candidates": actions,
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
        "writes_research_action_queue",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    snap = manifest.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["run_manifests"] == []
    assert manifest.NOTE_INPUT_ABSENT in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_actions(tmp_path / "actions.json", [], report_kind="wrong")

    snap = manifest.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["run_manifests"] == []
    assert manifest.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_actions(tmp_path / "actions.json", [_action()])

    snap_a = manifest.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = manifest.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["run_manifests"][0]
    assert row["run_manifest_id"].startswith("qre-run-")
    assert row["source_action_id"] == "qre-action-fixture-001"
    assert row["target_hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["target_validation_plan_id"] == "qre-plan-fixture-001"
    assert row["status"] == "operator_review_required"
    assert row["operator_approval_required"] is True
    assert row["safe_to_execute"] is False
    assert row["eligible_for_direct_execution"] is False
    assert "Informational only" in row["suggested_command"]


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        manifest._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_actions(tmp_path / "actions.json", [_action()])
    artifact_dir = tmp_path / "logs" / "qre_research_run_manifest"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(manifest, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(manifest, "ARTIFACT_LATEST", latest)

    rc = manifest.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["run_manifests"][0]["operator_approval_required"] is True


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(manifest.__file__).read_text(encoding="utf-8")
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
    src = Path(manifest.__file__).read_text(encoding="utf-8")
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
