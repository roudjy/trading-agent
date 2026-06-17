from __future__ import annotations

import json
from pathlib import Path

from research import qre_bounded_current_basket_generation_runner as runner


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-runner-001",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "approval-001",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": [
            "logs/qre_bounded_current_basket_generation_runner/",
            "logs/qre_bounded_current_basket_generation_discovery/",
        ],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-17T16:10:00Z",
        "source": "operator_approval_manifest",
    }


def test_runner_is_deterministic_and_fail_closed() -> None:
    first = runner.build_bounded_current_basket_generation_runner(_request_payload())
    second = runner.build_bounded_current_basket_generation_runner(_request_payload())

    assert first == second
    assert first["report_kind"] == runner.REPORT_KIND
    assert first["summary"]["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
    assert first["generation_manifest"]["execution_status"] == "not_executed"
    assert first["generation_manifest"]["auto_run_allowed"] is False
    assert first["preflight"]["approval_packet_ready"] is True
    assert first["preflight"]["safe_existing_generation_command_available"] is False


def test_runner_emits_reason_records_and_downstream_manifest() -> None:
    report = runner.build_bounded_current_basket_generation_runner(_request_payload())

    assert report["reason_records"]
    assert report["reason_records"][0]["record_kind"] == "reason_record"
    assert report["reason_records"][0]["validation_status"] == "provisional"
    assert "safe_bounded_generation_command_not_found" in report["preflight"]["blocking_preflight_reasons"]
    assert "python -m research.qre_artifact_authority --write" in report["downstream_rerun_manifest"]["commands"]
    assert "python -m research.qre_reason_record_contract --write" in report["downstream_rerun_manifest"]["commands"]
    assert "python -m research.qre_structured_lineage_artifacts --write" in report["downstream_rerun_manifest"]["commands"]
    assert "python -m research.qre_structured_oos_artifacts --write" in report["downstream_rerun_manifest"]["commands"]


def test_runner_rejects_invalid_request_payload_fail_closed() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        {
            "request_id": "req-invalid",
            "symbols": [],
            "preset_id": "",
            "timeframe": "",
            "approval_ref": "",
            "required_artifact_types": [],
            "allowed_output_paths": ["paper/output/"],
            "forbidden_capabilities": ["campaign_launcher"],
            "created_at_utc": "2026-06-17T16:10:00Z",
            "source": "fixture",
        }
    )

    assert report["request_validation_status"] == "rejected"
    assert report["summary"]["final_recommendation"] == "request_invalid_fails_closed"
    assert report["preflight"]["approval_packet_ready"] is False


def test_runner_write_outputs_are_allowlisted(tmp_path: Path) -> None:
    report = runner.build_bounded_current_basket_generation_runner(_request_payload())
    paths = runner.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_bounded_current_basket_generation_runner/latest.json"
    assert paths["operator_summary"] == "logs/qre_bounded_current_basket_generation_runner/operator_summary.md"
    payload = json.loads(
        (tmp_path / "logs" / "qre_bounded_current_basket_generation_runner" / "latest.json").read_text(encoding="utf-8")
    )
    assert payload["summary"]["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
