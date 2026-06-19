from __future__ import annotations

from pathlib import Path

from research import qre_multiwindow_evidence_closure as closure


def _campaign(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "campaign_id": "camp-001",
        "sampling_plan_id": "plan-001",
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
            null_control_results={"status": "passed"},
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
            null_control_results={"status": "failed"},
        )
    )

    assert report["closure_status"] == "null_control_failed"
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
