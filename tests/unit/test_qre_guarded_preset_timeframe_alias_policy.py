from __future__ import annotations

from pathlib import Path

from research import qre_guarded_preset_timeframe_alias_policy as policy


def test_guarded_alias_policy_keeps_legacy_first_batch_evidence_context_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        policy.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "legacy_compatibility": {
                "rows": [
                    {
                        "symbol": "AAPL",
                        "legacy_preset_id": "trend_pullback_v1",
                        "target_preset_id": "trend_pullback_continuation_daily_v1",
                        "legacy_timeframe": "4h",
                        "target_timeframe": "daily_v1",
                        "preset_alias_outcome": "alias_allowed_for_context_only",
                        "timeframe_alias_outcome": "alias_blocked_timeframe_mismatch",
                        "campaign_lineage_eligible": False,
                    },
                    {
                        "symbol": "NVDA",
                        "legacy_preset_id": "trend_pullback_v1",
                        "target_preset_id": "trend_pullback_continuation_daily_v1",
                        "legacy_timeframe": "4h",
                        "target_timeframe": "daily_v1",
                        "preset_alias_outcome": "alias_allowed_for_context_only",
                        "timeframe_alias_outcome": "alias_blocked_timeframe_mismatch",
                        "campaign_lineage_eligible": False,
                    },
                ]
            }
        },
    )

    report = policy.build_guarded_preset_timeframe_alias_policy(repo_root=tmp_path)

    assert report["summary"]["final_recommendation"] == "guarded_alias_policy_context_only"
    assert report["summary"]["evidence_completion_allowed_count"] == 0
    rows = {row["symbol"]: row for row in report["rows"]}
    assert sorted(rows) == ["AAPL", "NVDA"]
    assert rows["AAPL"]["legacy_preset_id"] == "trend_pullback_v1"
    assert rows["AAPL"]["current_preset_id"] == "trend_pullback_continuation_daily_v1"
    assert rows["AAPL"]["legacy_timeframe"] == "4h"
    assert rows["AAPL"]["current_timeframe"] == "daily_v1"
    assert rows["AAPL"]["policy_decision"] == "context_only_allowed"
    assert rows["AAPL"]["safe_for_operator_context"] is True
    assert rows["AAPL"]["safe_for_campaign_lineage"] is False
    assert rows["AAPL"]["safe_for_evidence_completion"] is False
    assert "evidence_completeness_proof" in rows["AAPL"]["blocked_usage"]
    assert rows["NVDA"]["policy_decision"] == "context_only_allowed"


def test_guarded_alias_policy_write_outputs_stays_allowlisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        policy.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {"legacy_compatibility": {"rows": []}},
    )

    report = policy.build_guarded_preset_timeframe_alias_policy(repo_root=tmp_path)
    paths = policy.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_guarded_preset_timeframe_alias_policy/latest.json"
    assert paths["operator_summary"] == "logs/qre_guarded_preset_timeframe_alias_policy/operator_summary.md"
