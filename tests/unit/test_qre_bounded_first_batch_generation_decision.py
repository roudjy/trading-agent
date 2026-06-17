from __future__ import annotations

from pathlib import Path

from research import qre_bounded_first_batch_generation_decision as decision


def test_bounded_generation_decision_requires_operator_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        decision.alias_policy,
        "build_guarded_preset_timeframe_alias_policy",
        lambda **_: {"summary": {"final_recommendation": "guarded_alias_policy_context_only"}},
    )
    monkeypatch.setattr(
        decision.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "rows": [
                {"symbol": "AAPL", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
                {"symbol": "NVDA", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
            ]
        },
    )

    report = decision.build_bounded_first_batch_generation_decision(repo_root=tmp_path)

    packet = report["decision_packet"]
    assert report["summary"]["final_recommendation"] == "operator_approve_bounded_aapl_nvda_current_basket_grid_generation"
    assert packet["symbols"] == ["AAPL", "NVDA"]
    assert packet["target_preset"] == "trend_pullback_continuation_daily_v1"
    assert packet["target_timeframe"] == "daily_v1"
    assert packet["operator_approval_required"] is True
    assert packet["auto_run_allowed"] is False
    assert "campaign_launcher" in packet["unsafe_command_candidates"]
    envelope = {row["command"]: row for row in report["command_envelope"]["rows"]}
    assert envelope["python -m research.qre_guarded_alias_bounded_generation_cascade --write"]["classification"] == "safe_report_only"
    assert envelope["python -m research.controlled_discovery_grid --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1"]["classification"] == "approval_required_generation"
    assert envelope["paper/shadow/live"]["classification"] == "forbidden_trading"
    assert envelope["strategy synthesis"]["classification"] == "forbidden_mutation"
    assert envelope["external data fetch"]["classification"] == "forbidden_external_fetch"


def test_bounded_generation_decision_write_outputs_stays_allowlisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        decision.alias_policy,
        "build_guarded_preset_timeframe_alias_policy",
        lambda **_: {"summary": {}},
    )
    monkeypatch.setattr(
        decision.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {"rows": []},
    )

    report = decision.build_bounded_first_batch_generation_decision(repo_root=tmp_path)
    paths = decision.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_bounded_first_batch_generation_decision/latest.json"
    assert paths["operator_summary"] == "logs/qre_bounded_first_batch_generation_decision/operator_summary.md"
