from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_evidence_quality_gate as gate


FROZEN = "2026-06-01T12:00:00Z"


def _hypothesis(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "supporting_evidence_refs": ["fixture#candidate-support"],
        "contradicting_evidence_refs": [],
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _result(**overrides) -> dict:
    base = {
        "result_id": "qre-result-fixture-001",
        "hypothesis_id": "qre-hyp-fixture-001",
        "status": "passed",
        "metric_results": {"trade_count": 120, "sharpe": 1.2},
        "falsification_hits": [],
        "supporting_evidence_refs": ["fixture#result-support"],
        "contradicting_evidence_refs": [],
        "source_artifact": "fixture/results.json",
        "source_report_kind": "fixture",
        "source_row_id": "row-001",
        "source_ref": "fixture/results.json#row-001",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _update(**overrides) -> dict:
    base = {
        "evidence_update_id": "qre-evidence-fixture-001",
        "hypothesis_id": "qre-hyp-fixture-001",
        "evidence_decision": "supported",
        "supporting_evidence_refs": ["fixture#update-support"],
        "contradicting_evidence_refs": [],
        "source_artifact": "fixture/results.json",
        "source_report_kind": "fixture",
        "source_row_id": "row-001",
        "source_ref": "fixture/results.json#row-001",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_payload(path: Path, report_kind: str, field: str | None, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "report_kind": report_kind,
        "generated_at_utc": FROZEN,
        "safe_to_execute": False,
    }
    if field is not None:
        payload[field] = rows
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _artifact_set(
    tmp_path: Path,
    *,
    hypotheses: list[dict] | None = None,
    results: list[dict] | None = None,
    updates: list[dict] | None = None,
    operator_report: dict | None = None,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "hypotheses": _write_payload(
            tmp_path / "hypotheses.json",
            "qre_hypothesis_candidates",
            "hypotheses",
            [_hypothesis()] if hypotheses is None else hypotheses,
        ),
        "results": _write_payload(
            tmp_path / "results.json",
            "qre_hypothesis_validation_results",
            "validation_results",
            [_result()] if results is None else results,
        ),
        "updates": _write_payload(
            tmp_path / "updates.json",
            "qre_hypothesis_evidence_update",
            "evidence_updates",
            [_update()] if updates is None else updates,
        ),
        "operator_report": tmp_path / "operator_report.json",
        "readiness": _write_payload(
            tmp_path / "readiness.json",
            "qre_trusted_loop_readiness",
            None,
            [],
        ),
    }
    operator_payload = {
        "schema_version": 1,
        "report_kind": "qre_closed_loop_operator_report",
        "operator_report": {"safe_to_execute": False},
        "safe_to_execute": False,
    }
    if operator_report is not None:
        operator_payload["operator_report"].update(operator_report)
    paths["operator_report"].write_text(json.dumps(operator_payload, indent=2), encoding="utf-8")
    return paths


def _collect(paths: dict[str, Path]) -> dict:
    return gate.collect_snapshot(
        hypotheses_path=paths["hypotheses"],
        validation_results_path=paths["results"],
        evidence_updates_path=paths["updates"],
        operator_report_path=paths["operator_report"],
        readiness_path=paths["readiness"],
        generated_at_utc=FROZEN,
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


def test_missing_inputs_fail_closed_with_zero_rows(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    paths = {
        "hypotheses": missing,
        "results": missing,
        "updates": missing,
        "operator_report": missing,
        "readiness": missing,
    }

    snap = _collect(paths)

    assert snap["evidence_quality_rows"] == []
    assert gate.NOTE_INPUT_ISSUES in snap["validation_warnings"]
    assert snap["final_recommendation"] == "operator_review_required_or_more_evidence_needed"
    _assert_safety_flags_false(snap)


def test_malformed_inputs_fail_closed(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["results"].write_text(json.dumps({"report_kind": "wrong"}), encoding="utf-8")

    snap = _collect(paths)

    assert snap["evidence_quality_rows"] == []
    assert gate.NOTE_INPUT_ISSUES in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_supported_result_with_lineage_metrics_and_trade_count_is_usable(tmp_path: Path) -> None:
    snap = _collect(_artifact_set(tmp_path))

    row = snap["evidence_quality_rows"][0]
    assert row["quality_class"] == "usable"
    assert row["quality_score"] == 75
    assert row["source_lineage_present"] is True
    assert row["metric_completeness"] == "complete"
    assert row["trade_count_present"] is True
    assert row["primary_metrics_present"] is True
    assert row["promotion_allowed"] is True
    assert row["safe_to_execute"] is False


def test_supported_result_with_repeatability_and_operator_indicator_is_strong(
    tmp_path: Path,
) -> None:
    paths = _artifact_set(
        tmp_path,
        results=[_result(repeatability_evidence_refs=["fixture#repeatability"])],
        operator_report={"operator_approved_for_trusted_loop": True},
    )

    snap = _collect(paths)

    row = snap["evidence_quality_rows"][0]
    assert row["quality_class"] == "strong"
    assert row["repeatability_status"] == "repeatability_evidence_present"
    assert row["operator_approved_indicator_present"] is True
    assert row["promotion_allowed"] is True


def test_supported_result_without_lineage_is_thin_at_best(tmp_path: Path) -> None:
    paths = _artifact_set(
        tmp_path,
        results=[
            _result(
                source_artifact="",
                source_report_kind="",
                source_row_id="",
                source_ref="",
            )
        ],
        updates=[
            _update(
                source_artifact="",
                source_report_kind="",
                source_row_id="",
                source_ref="",
            )
        ],
    )

    row = _collect(paths)["evidence_quality_rows"][0]

    assert row["quality_class"] == "thin"
    assert row["source_lineage_present"] is False
    assert row["promotion_allowed"] is False


def test_inconclusive_or_missing_result_is_not_promotable(tmp_path: Path) -> None:
    inconclusive = _collect(
        _artifact_set(tmp_path / "a", results=[_result(status="inconclusive")])
    )["evidence_quality_rows"][0]
    missing = _collect(
        _artifact_set(tmp_path / "b", results=[], updates=[_update()])
    )["evidence_quality_rows"][0]

    assert inconclusive["quality_class"] in {"insufficient", "thin"}
    assert inconclusive["promotion_allowed"] is False
    assert missing["quality_class"] == "insufficient"
    assert missing["validation_status"] == "missing"
    assert missing["promotion_allowed"] is False


def test_falsified_evidence_is_contradictory_and_never_promoted(tmp_path: Path) -> None:
    row = _collect(
        _artifact_set(
            tmp_path,
            results=[_result(status="failed", falsification_hits=["fixture#fail"])],
            updates=[_update(evidence_decision="falsified")],
        )
    )["evidence_quality_rows"][0]

    assert row["quality_class"] == "contradictory"
    assert row["promotion_allowed"] is False


def test_contradiction_detected_is_contradictory(tmp_path: Path) -> None:
    row = _collect(
        _artifact_set(
            tmp_path,
            results=[_result(contradicting_evidence_refs=["fixture#against"])],
            updates=[_update(evidence_decision="contradiction_detected")],
        )
    )["evidence_quality_rows"][0]

    assert row["quality_class"] == "contradictory"
    assert row["contradiction_visible"] is True
    assert row["promotion_allowed"] is False


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)

    snap_a = _collect(paths)
    snap_b = _collect(paths)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = _artifact_set(tmp_path)
    artifact_dir = tmp_path / "logs" / "qre_evidence_quality_gate"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(gate, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(gate, "ARTIFACT_LATEST", latest)

    rc = gate.main(
        [
            "--no-write",
            "--hypotheses-source",
            str(paths["hypotheses"]),
            "--results-source",
            str(paths["results"]),
            "--evidence-updates-source",
            str(paths["updates"]),
            "--operator-report-source",
            str(paths["operator_report"]),
            "--readiness-source",
            str(paths["readiness"]),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["evidence_quality_rows"][0]["quality_class"] == "usable"


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gate._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(gate.__file__).read_text(encoding="utf-8")
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
    src = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = (
        "seed.jsonl",
        "delegation_seed.jsonl",
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


def test_all_top_level_mutation_flags_are_false(tmp_path: Path) -> None:
    _assert_safety_flags_false(_collect(_artifact_set(tmp_path)))
