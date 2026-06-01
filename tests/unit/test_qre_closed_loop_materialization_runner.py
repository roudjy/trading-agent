from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from reporting import qre_closed_loop_materialization_runner as runner


FROZEN = "2026-06-01T12:00:00Z"


def _fake_module(name: str, report_kind: str, out_dir: Path, calls: list[str]):
    latest = out_dir / report_kind / "latest.json"

    def collect_snapshot(*, generated_at_utc: str | None = None) -> dict:
        calls.append(f"collect:{report_kind}:{generated_at_utc}")
        return {
            "schema_version": 1,
            "report_kind": report_kind,
            "generated_at_utc": generated_at_utc,
            "counts": {"total": 1},
            "final_recommendation": f"{report_kind}_ready",
            "validation_warnings": [],
            "safe_to_execute": False,
        }

    def write_outputs(snapshot: dict) -> Path:
        calls.append(f"write:{report_kind}")
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(snapshot), encoding="utf-8")
        return latest

    return SimpleNamespace(
        __name__=name,
        collect_snapshot=collect_snapshot,
        write_outputs=write_outputs,
    )


def _fake_modules(tmp_path: Path, calls: list[str]):
    names = [
        "qre_market_observation_snapshot",
        "qre_hypothesis_candidates",
        "qre_observation_hypothesis_projector",
        "qre_hypothesis_validation_plan",
        "qre_validation_research_action_candidates",
        "qre_research_run_manifest",
        "qre_hypothesis_validation_results",
        "qre_hypothesis_evidence_update",
        "qre_closed_loop_operator_report",
        "qre_trusted_loop_readiness",
    ]
    return tuple(
        _fake_module(f"reporting.{name}", name, tmp_path / "logs", calls) for name in names
    )


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


def test_no_write_mode_collects_in_exact_step_order_without_module_writes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    fake_modules = _fake_modules(tmp_path, calls)
    monkeypatch.setattr(runner, "STEP_MODULES", fake_modules)

    snap = runner.collect_snapshot(no_write=True, generated_at_utc=FROZEN)

    assert [step["report_kind"] for step in snap["steps"]] == [
        "qre_market_observation_snapshot",
        "qre_hypothesis_candidates",
        "qre_observation_hypothesis_projector",
        "qre_hypothesis_validation_plan",
        "qre_validation_research_action_candidates",
        "qre_research_run_manifest",
        "qre_hypothesis_validation_results",
        "qre_hypothesis_evidence_update",
        "qre_closed_loop_operator_report",
        "qre_trusted_loop_readiness",
    ]
    assert all(call.startswith("collect:") for call in calls)
    assert all(step["artifact_path"] is None for step in snap["steps"])
    _assert_safety_flags_false(snap)


def test_write_mode_uses_module_write_outputs_and_runner_artifact_only_for_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    fake_modules = _fake_modules(tmp_path, calls)
    materialization_dir = tmp_path / "logs" / "qre_closed_loop_materialization"
    monkeypatch.setattr(runner, "STEP_MODULES", fake_modules)
    monkeypatch.setattr(runner, "ARTIFACT_DIR", materialization_dir)
    monkeypatch.setattr(runner, "ARTIFACT_LATEST", materialization_dir / "latest.json")

    snap = runner.collect_snapshot(no_write=False, generated_at_utc=FROZEN)
    out = runner.write_outputs(snap)

    assert out == materialization_dir / "latest.json"
    assert out.exists()
    assert calls.count("write:qre_market_observation_snapshot") == 1
    written = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json"))
    assert "logs/qre_closed_loop_materialization/latest.json" in written
    assert all(path.startswith("logs/qre_") for path in written)
    _assert_safety_flags_false(snap)


def test_cli_no_write_does_not_write_runner_artifact(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    calls: list[str] = []
    fake_modules = _fake_modules(tmp_path, calls)
    materialization_dir = tmp_path / "logs" / "qre_closed_loop_materialization"
    monkeypatch.setattr(runner, "STEP_MODULES", fake_modules)
    monkeypatch.setattr(runner, "ARTIFACT_DIR", materialization_dir)
    monkeypatch.setattr(runner, "ARTIFACT_LATEST", materialization_dir / "latest.json")

    rc = runner.main(["--no-write", "--frozen-utc", FROZEN, "--indent", "0"])

    assert rc == 0
    assert (materialization_dir / "latest.json").exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["safe_to_execute"] is False
    assert all(call.startswith("collect:") for call in calls)


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        runner._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(runner.__file__).read_text(encoding="utf-8")
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
    src = Path(runner.__file__).read_text(encoding="utf-8")
    forbidden = (
        "seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "campaigns/",
        "agent/backtesting/strategies.py",
        "registry.py",
        "paper/",
        "shadow/",
        "live/",
    )
    for token in forbidden:
        assert token not in src, token
