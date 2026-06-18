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


def _structured_source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
        "lineage_records": [
            {
                "candidate_id": "cand-001",
                "campaign_id": "camp-001",
                "generation_run_id": "gen-001",
                "reason_record_refs": ["rr-lineage-001"],
            }
        ],
        "oos_records": [
            {
                "candidate_id": "cand-001",
                "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                "oos_metric_fields": {"oos_trade_count": 24, "oos_return_pct": 3.1},
                "cost_slippage_assumption_refs": ["cost-model-001"],
                "reason_record_refs": ["rr-oos-001"],
            }
        ],
    }
    payload.update(overrides)
    return payload


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
    assert first["runner_status"] == "no_safe_controlled_validation_source"
    assert first["adapter_result"]["adapter_status"] == "no_safe_controlled_validation_source"
    assert first["accepted_lineage_count"] == 0
    assert first["accepted_oos_count"] == 0
    assert first["can_clear_blockers"] is False
    assert first["hash"] == runner.compute_runner_hash(first)


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
    assert report["preflight"]["controlled_validation_adapter_called"] is False
    assert report["runner_status"] == "blocked_missing_approval_ref"


def test_runner_write_outputs_are_allowlisted(tmp_path: Path) -> None:
    report = runner.build_bounded_current_basket_generation_runner(_request_payload())
    paths = runner.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_bounded_current_basket_generation_runner/latest.json"
    assert paths["operator_summary"] == "logs/qre_bounded_current_basket_generation_runner/operator_summary.md"
    payload = json.loads(
        (tmp_path / "logs" / "qre_bounded_current_basket_generation_runner" / "latest.json").read_text(encoding="utf-8")
    )
    assert payload["summary"]["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"


def test_runner_does_not_call_adapter_when_approval_ref_missing() -> None:
    payload = _request_payload()
    payload["approval_ref"] = ""
    report = runner.build_bounded_current_basket_generation_runner(
        payload,
        controlled_validation_source=_structured_source(),
    )

    assert report["preflight"]["controlled_validation_adapter_called"] is False
    assert report["runner_status"] == "blocked_missing_approval_ref"
    assert report["accepted_lineage_count"] == 0
    assert report["accepted_oos_count"] == 0


def test_runner_does_not_call_adapter_when_forbidden_capabilities_present() -> None:
    payload = _request_payload()
    payload["forbidden_capabilities"] = ["strategy_synthesis"]
    report = runner.build_bounded_current_basket_generation_runner(
        payload,
        controlled_validation_source=_structured_source(),
    )

    assert report["preflight"]["controlled_validation_adapter_called"] is False
    assert report["runner_status"] == "blocked_forbidden_capability"
    assert report["can_clear_blockers"] is False


def test_runner_returns_no_safe_controlled_validation_source_without_source() -> None:
    report = runner.build_bounded_current_basket_generation_runner(_request_payload())

    assert report["runner_status"] == "no_safe_controlled_validation_source"
    assert report["adapter_result"]["adapter_status"] == "no_safe_controlled_validation_source"
    assert report["accepted_lineage_count"] == 0
    assert report["accepted_oos_count"] == 0
    assert report["can_clear_blockers"] is False


def test_runner_preserves_adapter_rejected_result_without_clearing_blockers() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source={"source_type": "context_only", "source_ref": "report"},
    )

    assert report["runner_status"] == "adapter_rejected_source"
    assert report["adapter_result"]["adapter_status"] == "rejected_context_only_source"
    assert report["can_clear_blockers"] is False
    assert "context_only_source_rejected" in report["rejected_reasons"]


def test_runner_preserves_adapter_provisional_result_without_clearing_blockers() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source=_structured_source(
            lineage_records=[
                {"candidate_id": "", "campaign_id": "", "generation_run_id": ""}
            ],
        ),
    )

    assert report["runner_status"] == "adapter_provisional_only"
    assert report["adapter_result"]["adapter_status"] == "blocked_missing_candidate_id"
    assert report["accepted_lineage_count"] == 0
    assert report["can_clear_blockers"] is False


def test_runner_surfaces_adapter_accepted_counts_when_structured_source_is_accepted() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source=_structured_source(),
    )

    assert report["runner_status"] == "adapter_accepted_structured_evidence"
    assert report["adapter_result"]["adapter_status"] == "accepted_structured_evidence"
    assert report["accepted_lineage_count"] == 1
    assert report["accepted_oos_count"] == 1
    assert report["lineage_candidate_refs"] == [
        "artifacts/qre_controlled_validation/source-001.json#lineage:cand-001"
    ]
    assert report["oos_candidate_refs"] == [
        "artifacts/qre_controlled_validation/source-001.json#oos:cand-001"
    ]
    assert report["can_clear_blockers"] is False
    assert "verifier_acceptance_required_to_clear_blockers" in report["rejected_reasons"]


def test_runner_can_clear_blockers_requires_lineage_and_oos_counts() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source=_structured_source(oos_records=[]),
    )

    assert report["accepted_lineage_count"] == 1
    assert report["accepted_oos_count"] == 0
    assert report["can_clear_blockers"] is False


def test_runner_rejects_stdout_and_legacy_sources_as_non_authoritative() -> None:
    stdout_report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source={"source_type": "stdout_only", "source_ref": "stdout"},
    )
    legacy_report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source={"source_type": "legacy_alias_only", "source_ref": "alias"},
    )

    assert stdout_report["runner_status"] == "adapter_rejected_source"
    assert stdout_report["can_clear_blockers"] is False
    assert legacy_report["runner_status"] == "adapter_rejected_source"
    assert legacy_report["can_clear_blockers"] is False


def test_runner_authority_and_core_path_safety() -> None:
    report = runner.build_bounded_current_basket_generation_runner(
        _request_payload(),
        controlled_validation_source=_structured_source(),
    )
    source = Path("research/qre_bounded_current_basket_generation_runner.py").read_text(
        encoding="utf-8"
    )

    assert report["non_authoritative"] is True
    assert report["evidence_authority"] == "runner_context_until_verifier_acceptance"
    assert report["can_authorize_execution"] is False
    assert report["can_synthesize_strategy"] is False
    assert report["can_promote_candidate"] is False
    assert report["can_activate_deployment"] is False
    assert report["generation_manifest"]["auto_run_allowed"] is False
    assert report["safety_invariants"]["no_trading_authority"] is True
    assert report["safety_invariants"]["no_external_fetch"] is True
    assert report["safety_invariants"]["adapter_output_not_proof_by_itself"] is True
    assert "AAPL" not in source
    assert "NVDA" not in source
