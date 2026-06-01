from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_hypothesis_evidence_update as evidence


FROZEN = "2026-06-01T12:00:00Z"


def _hypothesis(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "status": "proposed",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _result(**overrides) -> dict:
    base = {
        "result_id": "qre-result-fixture-001",
        "hypothesis_id": "qre-hyp-fixture-001",
        "validation_plan_id": "qre-plan-fixture-001",
        "run_manifest_id": "qre-run-fixture-001",
        "status": "passed",
        "metric_results": {"trade_count": 120},
        "falsification_hits": [],
        "supporting_evidence_refs": ["fixture#support"],
        "contradicting_evidence_refs": [],
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_hypotheses(path: Path, rows: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_hypothesis_candidates",
        "generated_at_utc": FROZEN,
        "hypotheses": rows,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_results(path: Path, rows: list[dict], **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_hypothesis_validation_results",
        "generated_at_utc": FROZEN,
        "validation_results": rows,
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
    snap = evidence.collect_snapshot(
        hypothesis_input_artifact_path=tmp_path / "missing-hyp.json",
        result_input_artifact_path=tmp_path / "missing-results.json",
        generated_at_utc=FROZEN,
    )

    assert snap["evidence_updates"] == []
    assert evidence.NOTE_INPUT_ABSENT in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    hyp_source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    result_source = _write_results(
        tmp_path / "results.json",
        [_result()],
        report_kind="wrong",
    )

    snap = evidence.collect_snapshot(
        hypothesis_input_artifact_path=hyp_source,
        result_input_artifact_path=result_source,
        generated_at_utc=FROZEN,
    )

    assert snap["evidence_updates"] == []
    assert evidence.NOTE_INPUT_UNPARSEABLE in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    hyp_source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    result_source = _write_results(tmp_path / "results.json", [_result()])

    snap_a = evidence.collect_snapshot(
        hypothesis_input_artifact_path=hyp_source,
        result_input_artifact_path=result_source,
        generated_at_utc=FROZEN,
    )
    snap_b = evidence.collect_snapshot(
        hypothesis_input_artifact_path=hyp_source,
        result_input_artifact_path=result_source,
        generated_at_utc=FROZEN,
    )

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    row = snap_a["evidence_updates"][0]
    assert row["evidence_update_id"].startswith("qre-evidence-")
    assert row["hypothesis_id"] == "qre-hyp-fixture-001"
    assert row["previous_status"] == "proposed"
    assert row["evidence_decision"] == "supported"
    assert row["recommended_next_status"] == "supported"
    assert row["supporting_evidence_refs"] == ["fixture#support"]
    assert row["safe_to_execute"] is False


def test_decision_mapping_failed_and_contradiction_and_no_result(tmp_path: Path) -> None:
    hyp_source = _write_hypotheses(
        tmp_path / "hypotheses.json",
        [
            _hypothesis(hypothesis_id="qre-hyp-failed"),
            _hypothesis(hypothesis_id="qre-hyp-contradiction"),
            _hypothesis(hypothesis_id="qre-hyp-missing"),
        ],
    )
    result_source = _write_results(
        tmp_path / "results.json",
        [
            _result(
                result_id="qre-result-failed",
                hypothesis_id="qre-hyp-failed",
                status="failed",
            ),
            _result(
                result_id="qre-result-contradiction",
                hypothesis_id="qre-hyp-contradiction",
                status="passed",
                supporting_evidence_refs=["fixture#support"],
                contradicting_evidence_refs=["fixture#contradiction"],
            ),
        ],
    )

    snap = evidence.collect_snapshot(
        hypothesis_input_artifact_path=hyp_source,
        result_input_artifact_path=result_source,
        generated_at_utc=FROZEN,
    )

    decisions = {
        row["hypothesis_id"]: row["evidence_decision"]
        for row in snap["evidence_updates"]
    }
    assert decisions == {
        "qre-hyp-failed": "falsified",
        "qre-hyp-contradiction": "contradiction_detected",
        "qre-hyp-missing": "needs_more_data",
    }


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evidence._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    hyp_source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    result_source = _write_results(tmp_path / "results.json", [_result()])
    artifact_dir = tmp_path / "logs" / "qre_hypothesis_evidence_updates"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(evidence, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(evidence, "ARTIFACT_LATEST", latest)

    rc = evidence.main(
        [
            "--no-write",
            "--hypotheses-source",
            str(hyp_source),
            "--results-source",
            str(result_source),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["evidence_updates"][0]["evidence_decision"] == "supported"


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(evidence.__file__).read_text(encoding="utf-8")
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
    src = Path(evidence.__file__).read_text(encoding="utf-8")
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
