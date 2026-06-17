from __future__ import annotations

from research import qre_bounded_basket_request as basket_request
from research import qre_bounded_current_basket_generation_discovery as discovery


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-generic-001",
        "symbols": ["QQQ", "MSFT"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "approval-manifest-001",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": [
            "logs/qre_bounded_current_basket_generation_discovery/",
            "artifacts/qre_bounded_current_basket_generation_discovery/",
        ],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-17T16:05:00Z",
        "source": "request_fixture",
    }


def test_generic_discovery_reports_request_driven_command_surface() -> None:
    report = discovery.build_bounded_current_basket_generation_discovery(_request_payload())

    assert report["report_kind"] == "qre_bounded_current_basket_generation_discovery"
    assert report["request"]["symbols"] == ["MSFT", "QQQ"]
    assert report["summary"]["exact_scope_candidate_count"] == 3
    assert report["summary"]["safe_bounded_generation_command_found"] is False
    assert report["summary"]["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"


def test_generic_discovery_classifies_candidate_commands() -> None:
    report = discovery.build_bounded_current_basket_generation_discovery(_request_payload())
    rows = report["command_surface"]["rows"]
    row_by_command = {row["command"]: row for row in rows}

    assert row_by_command[
        "python -m research.qre_bounded_current_basket_generation_discovery --write"
    ]["classification"] == "report_only"
    assert row_by_command[
        "python -m research.controlled_discovery_grid --symbols MSFT,QQQ --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1"
    ]["classification"] == "bounded_generation_candidate"
    assert row_by_command[
        "python -m research.controlled_validation --symbols MSFT,QQQ --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1"
    ]["classification"] == "approval_required_generation"
    assert row_by_command[
        "python -m research.qre_bounded_current_basket_generation_runner --request-file logs/qre_bounded_basket_request/latest.json"
    ]["classification"] == "unknown_requires_operator_review"
    assert row_by_command[
        "python -m research.campaign_launcher --preset trend_pullback_continuation_daily_v1"
    ]["classification"] == "forbidden_mutation"


def test_generic_discovery_is_deterministic() -> None:
    first = discovery.build_bounded_current_basket_generation_discovery(_request_payload())
    second = discovery.build_bounded_current_basket_generation_discovery(_request_payload())

    assert first == second


def test_compatibility_wrapper_delegates_to_generic_surface() -> None:
    from research import qre_bounded_aapl_nvda_current_basket_generation_discovery as wrapper

    report = wrapper.build_bounded_aapl_nvda_current_basket_generation_discovery()

    assert report["report_kind"] == "qre_bounded_aapl_nvda_current_basket_generation_discovery"
    assert report["deprecated_wrapper_for"] == discovery.REPORT_KIND
    assert report["generic_discovery_report"]["report_kind"] == discovery.REPORT_KIND
    assert report["summary"]["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
    assert basket_request.REPORT_KIND == "qre_bounded_basket_request"
