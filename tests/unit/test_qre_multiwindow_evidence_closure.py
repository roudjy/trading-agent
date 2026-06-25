from __future__ import annotations

from pathlib import Path

from research import qre_multiwindow_evidence_closure as closure


def _campaign(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "campaign_id": "qmwv-001",
        "source_campaign_id": "source-campaign-001",
        "campaign_scope": {
            "campaign_id": "source-campaign-001",
            "hypothesis_id": "hypothesis-001",
            "preset_name": "preset-4h",
            "timeframe": "4h",
            "template_id": "template-001",
            "strategy_family": "trend_pullback",
            "asset_class": "equity",
            "universe": ["AAA", "BBB"],
            "lineage_root_campaign_id": "source-campaign-001",
            "parent_campaign_id": "",
            "registry_record_present": True,
        },
        "proposal_id": "proposal-001",
        "proposal_hash": "proposal-hash-001",
        "sampling_plan_id": "plan-001",
        "sampling_plan_hash": "sampling-hash-001",
        "accepted_lineage_count": 2,
        "accepted_oos_count": 0,
        "positive_oos_trade_count_total": 0,
        "campaign_outcome": "all_windows_non_positive_trade_count",
        "window_results": [
            {
                "window_id": "window_01",
                "accepted_oos_count": 0,
                "rejection_reasons": ["non_positive_oos_trade_count"],
            },
            {
                "window_id": "window_02",
                "accepted_oos_count": 0,
                "rejection_reasons": ["non_positive_oos_trade_count"],
            },
        ],
        "null_control_results": {"status": "not_run_due_to_no_accepted_oos"},
    }
    payload.update(overrides)
    return payload


def test_complete_evidence_requires_all_criteria() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(
            accepted_oos_count=2,
            positive_oos_trade_count_total=4,
            campaign_outcome="accepted_multiwindow_oos_evidence",
            null_control_results={"status": "controls_passed_context_only"},
        )
    )

    assert report["closure_status"] == "evidence_complete"
    assert report["evidence_complete_count"] == 1


def test_partial_accepted_windows_do_not_become_complete() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(
            accepted_oos_count=1,
            positive_oos_trade_count_total=1,
            campaign_outcome="partial_oos_evidence",
        )
    )

    assert report["closure_status"] == "evidence_partial"
    assert report["evidence_complete_count"] == 0


def test_all_zero_windows_reject_hypothesis_fail_closed() -> None:
    report = closure.build_multiwindow_evidence_closure(_campaign())

    assert report["closure_status"] == "all_windows_no_oos_trades"
    assert report["hypothesis_disposition"] == "fail_closed_rejected"
    assert report["recommended_next_action"] == "reject_hypothesis"


def test_missing_windows_block_closure() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(window_results=[], campaign_outcome="blocked_approval")
    )

    assert report["closure_status"] == "blocked_incomplete_campaign"


def test_null_control_failure_blocks_completion() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(
            accepted_oos_count=2,
            positive_oos_trade_count_total=4,
            campaign_outcome="accepted_multiwindow_oos_evidence",
            null_control_results={"status": "controls_failed"},
        )
    )

    assert report["closure_status"] == "null_control_failed"
    assert report["evidence_complete_count"] == 0


def test_missing_null_controls_block_completion_even_with_accepted_oos() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(
            accepted_oos_count=2,
            positive_oos_trade_count_total=4,
            campaign_outcome="accepted_multiwindow_oos_evidence",
            null_control_results={"status": "controls_incomplete"},
        )
    )

    assert report["closure_status"] == "blocked_missing_null_controls"
    assert report["evidence_complete_count"] == 0


def test_reason_records_and_authority_are_explicit() -> None:
    report = closure.build_multiwindow_evidence_closure(_campaign())

    assert report["reason_records"]
    assert report["authority"]["can_promote_candidate"] is False
    assert report["authority"]["can_activate_deployment"] is False


def test_core_closure_has_no_symbol_hardcoding() -> None:
    source = Path("research/qre_multiwindow_evidence_closure.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source


def test_all_zero_windows_override_incomplete_controls() -> None:
    report = closure.build_multiwindow_evidence_closure(
        _campaign(
            null_control_results={"status": "controls_incomplete"},
        )
    )

    assert report["closure_status"] == "all_windows_no_oos_trades"
    assert report["hypothesis_disposition"] == "fail_closed_rejected"
    assert report["recommended_next_action"] == "reject_hypothesis"
    assert "null_controls_incomplete" not in report["blockers_remaining"]
    assert "no_oos_evidence" in report["blockers_remaining"]


def test_closure_preserves_source_scope_and_hash_lineage() -> None:
    report = closure.build_multiwindow_evidence_closure(_campaign())

    assert report["campaign_ref"] == "qmwv-001"
    assert report["source_campaign_id"] == "source-campaign-001"
    assert report["campaign_scope"]["timeframe"] == "4h"
    assert report["campaign_scope"]["universe"] == ["AAA", "BBB"]
    assert report["proposal_id"] == "proposal-001"
    assert report["proposal_hash"] == "proposal-hash-001"
    assert report["sampling_plan_ref"] == "plan-001"
    assert report["sampling_plan_hash"] == "sampling-hash-001"
    assert report["hash"] == closure.compute_multiwindow_closure_hash(report)

    tampered = dict(report)
    tampered["proposal_hash"] = "tampered"
    assert closure.compute_multiwindow_closure_hash(tampered) != report["hash"]
