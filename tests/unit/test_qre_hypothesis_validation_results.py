from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_validation_results as results


FROZEN = "2026-06-01T12:00:00Z"


def _result(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "validation_plan_id": "qre-plan-fixture-001",
        "run_manifest_id": "qre-run-fixture-001",
        "status": "passed",
        "metric_results": {"deflated_sharpe": 1.2, "trade_count": 120},
        "falsification_hits": [],
        "supporting_evidence_refs": ["fixture#support"],
        "contradicting_evidence_refs": [],
    }
    base.update(overrides)
    return base


def _write_results(path: Path, rows: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "synthetic_validation_result_fixture",
        "generated_at_utc": FROZEN,
        "validation_results": rows,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_authorities(tmp_path: Path) -> dict[str, Path]:
    hypothesis_id = "qre-hyp-fixture-001"
    plan_id = "qre-plan-fixture-001"
    run_id = "qre-run-fixture-001"
    hypotheses = tmp_path / "hypotheses.json"
    plans = tmp_path / "plans.json"
    manifests = tmp_path / "run_manifests.json"
    hypotheses.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_candidates",
                "hypotheses": [{"hypothesis_id": hypothesis_id}],
            }
        ),
        encoding="utf-8",
    )
    plans.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [
                    {"hypothesis_id": hypothesis_id, "validation_plan_id": plan_id}
                ],
            }
        ),
        encoding="utf-8",
    )
    manifests.write_text(
        json.dumps(
            {
                "report_kind": "qre_research_run_manifest",
                "run_manifests": [
                    {
                        "run_manifest_id": run_id,
                        "target_validation_plan_id": plan_id,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return {"hypotheses": hypotheses, "plans": plans, "manifests": manifests}


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
    snap = results.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )

    assert snap["input_artifact_available"] is False
    assert snap["validation_results"] == []
    assert results.NOTE_INPUT_ABSENT in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    source = _write_results(tmp_path / "bad.json", [_result()], report_kind="wrong")

    snap = results.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["validation_results"] == []
    assert results.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    source = _write_results(tmp_path / "results.json", [_result()])

    snap_a = results.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)
    snap_b = results.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["validation_results"][0]
    assert row["result_id"].startswith("qre-result-")
    assert row["hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["validation_plan_id"] == "qre-plan-fixture-001"
    assert row["run_manifest_id"] == "qre-run-fixture-001"
    assert row["status"] == "passed"
    assert row["metric_results"]["trade_count"] == 120
    assert row["supporting_evidence_refs"] == ["fixture#support"]
    assert row["safe_to_execute"] is False


def test_real_source_screening_evidence_maps_linked_rows(tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path)
    source = tmp_path / "screening_evidence_latest.v1.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "candidates": [
                    {
                        "candidate_id": "candidate-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "stage_result": "screening_reject",
                        "metrics": {"profit_factor": 0.8, "totaal_trades": 42},
                        "failure_reasons": ["profit_factor_below_floor"],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    snap = results.collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    row = snap["validation_results"][0]
    assert row["hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["validation_plan_id"] == "qre-plan-fixture-001"
    assert row["run_manifest_id"] == "qre-run-fixture-001"
    assert row["status"] == "failed"
    assert row["metric_results"]["profit_factor"] == 0.8
    assert row["falsification_hits"] == ["profit_factor_below_floor"]
    assert row["source_artifact"].endswith("screening_evidence_latest.v1.json")
    assert row["source_report_kind"] == "screening_evidence"
    assert row["source_row_id"] == "candidate-001"
    assert row["source_ref"].endswith("#candidate-001")
    assert row["safe_to_execute"] is False


def test_real_source_unlinked_rows_are_skipped_with_warning(tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path)
    source = tmp_path / "screening_evidence_latest.v1.json"
    source.write_text(
        json.dumps({"candidates": [{"candidate_id": "candidate-001"}]}),
        encoding="utf-8",
    )

    snap = results.collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    assert snap["validation_results"] == []
    assert f"{results.NOTE_REAL_SOURCE_ROWS_SKIPPED}:1" in snap["validation_warnings"]


def test_real_source_lineage_and_ids_are_deterministic(tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path)
    source = tmp_path / "screening_evidence_latest.v1.json"
    source.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "candidate-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "stage_result": "screening_pass",
                        "metrics": {"profit_factor": 1.4},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snap_a = results.collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )
    snap_b = results.collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    assert (
        snap_a["validation_results"][0]["result_id"] == snap_b["validation_results"][0]["result_id"]
    )
    assert (
        snap_a["validation_results"][0]["source_ref"]
        == snap_b["validation_results"][0]["source_ref"]
    )


def test_real_source_malformed_artifact_fails_closed(tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path)
    source = tmp_path / "screening_evidence_latest.v1.json"
    source.write_text("{", encoding="utf-8")

    snap = results.collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    assert snap["validation_results"] == []
    assert any(
        results.NOTE_REAL_SOURCE_ARTIFACT_UNPARSEABLE in item
        for item in snap["validation_warnings"]
    )


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        results._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = _write_results(tmp_path / "results.json", [_result()])
    artifact_dir = tmp_path / "logs" / "qre_hypothesis_validation_results"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(results, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(results, "ARTIFACT_LATEST", latest)

    rc = results.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["validation_results"][0]["status"] == "passed"


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(results.__file__).read_text(encoding="utf-8")
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
    src = Path(results.__file__).read_text(encoding="utf-8")
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
