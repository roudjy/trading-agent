from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_validation_results as results
from reporting.qre_hypothesis_validation_results import collect_snapshot

FROZEN = "2026-06-01T12:00:00Z"
HYPOTHESIS_ID = "qre-hyp-fixture-001"
VALIDATION_PLAN_ID = "qre-plan-fixture-001"
RUN_MANIFEST_ID = "qre-run-fixture-001"


def _result(**overrides) -> dict:
    base = {
        "hypothesis_id": HYPOTHESIS_ID,
        "validation_plan_id": VALIDATION_PLAN_ID,
        "run_manifest_id": RUN_MANIFEST_ID,
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
    hypotheses = tmp_path / "hypotheses.json"
    plans = tmp_path / "plans.json"
    manifests = tmp_path / "run_manifests.json"
    hypotheses.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_candidates",
                "hypotheses": [{"hypothesis_id": HYPOTHESIS_ID}],
            }
        ),
        encoding="utf-8",
    )
    plans.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "validation_plan_id": VALIDATION_PLAN_ID,
                    }
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
                        "run_manifest_id": RUN_MANIFEST_ID,
                        "target_validation_plan_id": VALIDATION_PLAN_ID,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return {"hypotheses": hypotheses, "plans": plans, "manifests": manifests}


def _strict_linked_candidate(row_id: str, **overrides) -> dict:
    base = {
        "candidate_id": row_id,
        "hypothesis_id": HYPOTHESIS_ID,
        "validation_plan_id": VALIDATION_PLAN_ID,
        "run_manifest_id": RUN_MANIFEST_ID,
        "source_artifact": "screening_evidence_latest.v1.json",
        "source_report_kind": "screening_evidence",
        "source_row_id": row_id,
        "metrics": {"expectancy": 0.42},
    }
    base.update(overrides)
    return base


def _write_screening_evidence(path: Path, candidates: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_kind": "screening_evidence",
                "candidates": candidates,
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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


def test_real_source_status_semantics_for_strict_linked_screening_rows(
    tmp_path: Path,
) -> None:
    authorities = _write_authorities(tmp_path)
    source = _write_screening_evidence(
        tmp_path / "screening_evidence_latest.v1.json",
        [
            _strict_linked_candidate("status-passed", status="passed"),
            _strict_linked_candidate("status-failed", status="failed"),
            _strict_linked_candidate(
                "missing-falls-through",
                status="missing",
                stage_result="screening_pass",
            ),
            _strict_linked_candidate(
                "candidate-falls-through",
                status="candidate",
                stage_result="screening_pass",
            ),
            _strict_linked_candidate(
                "promotion-candidate",
                decision="promotion_candidate",
            ),
            _strict_linked_candidate("quality-ready", quality_status="ready"),
            _strict_linked_candidate(
                "screening-reject",
                stage_result="screening_reject",
            ),
            _strict_linked_candidate("quality-blocked", quality_status="blocked"),
            _strict_linked_candidate("near-pass", stage_result="near_pass"),
            _strict_linked_candidate("candidate-no-fallback", status="candidate"),
        ],
    )

    snap = collect_snapshot(
        source_artifact_paths=[source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    assert snap["counts"] == {
        "total": 10,
        "by_status": {
            "passed": 5,
            "failed": 3,
            "inconclusive": 2,
            "missing": 0,
        },
    }
    assert snap["validation_warnings"] == []
    assert snap["note"] == results.NOTE_RESULTS_PRESENT
    assert snap["final_recommendation"] == "validation_results_ready_for_evidence_update"
    assert snap["safe_to_execute"] is False

    by_row_id = {row["source_row_id"]: row for row in snap["validation_results"]}
    assert {row_id: row["status"] for row_id, row in by_row_id.items()} == {
        "status-passed": "passed",
        "status-failed": "failed",
        "missing-falls-through": "passed",
        "candidate-falls-through": "passed",
        "promotion-candidate": "passed",
        "quality-ready": "passed",
        "screening-reject": "failed",
        "quality-blocked": "failed",
        "near-pass": "inconclusive",
        "candidate-no-fallback": "inconclusive",
    }

    for row in snap["validation_results"]:
        assert row["hypothesis_id"] == HYPOTHESIS_ID
        assert row["validation_plan_id"] == VALIDATION_PLAN_ID
        assert row["run_manifest_id"] == RUN_MANIFEST_ID
        assert row["source_report_kind"] == "screening_evidence"
        assert row["source_row_id"]
        assert row["safe_to_execute"] is False
        assert row["metric_results"]["expectancy"] == 0.42

    assert by_row_id["missing-falls-through"]["metric_results"]["stage_result"] == (
        "screening_pass"
    )
    assert by_row_id["quality-ready"]["metric_results"]["quality_status"] == "ready"


def test_strict_linked_run_candidates_and_screening_evidence_materialize_results(
    tmp_path: Path,
) -> None:
    authorities = _write_authorities(tmp_path)
    screening_source = _write_screening_evidence(
        tmp_path / "screening_evidence_latest.v1.json",
        [
            _strict_linked_candidate(
                "screening-row-001",
                stage_result="screening_pass",
            )
        ],
    )
    run_candidates_source = tmp_path / "run_candidates_latest.v1.json"
    run_candidates_source.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_kind": "run_candidates",
                "candidates": [
                    {
                        **_strict_linked_candidate(
                            "run-candidate-row-001",
                            status="passed",
                        ),
                        "source_artifact": "run_candidates_latest.v1.json",
                        "source_report_kind": "run_candidates",
                    }
                ],
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    snap = collect_snapshot(
        source_artifact_paths=[run_candidates_source, screening_source],
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )

    assert snap["counts"]["total"] == 2
    assert snap["note"] == results.NOTE_RESULTS_PRESENT
    assert snap["final_recommendation"] == "validation_results_ready_for_evidence_update"
    assert {row["source_report_kind"] for row in snap["validation_results"]} == {
        "run_candidates",
        "screening_evidence",
    }
    assert snap["safe_to_execute"] is False
    for row in snap["validation_results"]:
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
