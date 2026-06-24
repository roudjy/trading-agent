from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research import campaign_evidence_decision as decision

CAMPAIGN_ID = (
    "col-20260605T122346491432Z-"
    "trend_pullback_equities_4h-b68c030d9c"
)


def _campaign_evidence(
    *,
    attributed: bool = True,
    owner_verified: bool = True,
    primary_limitation: str = "insufficient_trades",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "evidence_status": "attributed_with_artifact_gaps",
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "preset_name": "trend_pullback_equities_4h",
            "strategy_family": "trend_pullback",
            "asset_class": "equity",
        },
        "failure_attribution": {
            "attributed": attributed,
            "state": "gate_rejection_attributed",
        },
        "screening_evidence": {
            "owner_verified": owner_verified,
            "dominant_failure_reasons": [primary_limitation],
        },
        "interpretation": {
            "primary_limitation": primary_limitation,
        },
    }


def _registry() -> dict[str, Any]:
    return {
        "campaigns": {
            CAMPAIGN_ID: {
                "campaign_id": CAMPAIGN_ID,
                "hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_equities_4h",
                "template_id": (
                    "daily_primary__trend_pullback_equities_4h"
                ),
                "strategy_family": "trend_pullback",
                "asset_class": "equity",
                "universe": ["AAPL", "NVDA", "MSFT"],
                "lineage_root_campaign_id": CAMPAIGN_ID,
                "parent_campaign_id": None,
            }
        }
    }


def _exact_campaign_closure() -> dict[str, Any]:
    return {
        "campaign_ref": CAMPAIGN_ID,
        "campaign_outcome": "all_windows_non_positive_trade_count",
        "closure_status": "all_windows_no_oos_trades",
        "sampling_plan_ref": "qsp_matching",
        "reason_records": [
            {
                "reason_codes": [
                    "all_windows_non_positive_trade_count"
                ]
            }
        ],
    }


def _compound_scope_closure() -> dict[str, Any]:
    return {
        "hypothesis_id": "trend_pullback_v1",
        "preset_name": "trend_pullback_equities_4h",
        "template_id": (
            "daily_primary__trend_pullback_equities_4h"
        ),
        "universe": ["NVDA", "MSFT", "AAPL"],
        "campaign_outcome": "all_windows_non_positive_trade_count",
        "closure_status": "all_windows_no_oos_trades",
    }


def test_no_matching_plan_creates_sampling_plan() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run={
            "campaign_id": "unrelated_campaign",
            "preset_id": "unrelated_daily_v1",
        },
        multiwindow_closure={
            "campaign_ref": "unrelated_campaign",
            "sampling_plan_ref": "qsp_unrelated",
        },
        run_status="present",
        closure_status="present",
    )

    assert report["decision_status"] == "decision_ready"
    assert (
        report["scope_match_status"]
        == "no_matching_preregistered_evidence"
    )
    assert report["failure_class"] == "insufficient_window_length"
    assert (
        report["recommended_action"]
        == "create_preregistered_sampling_plan"
    )
    assert report["action_authority"] == "report_only"
    assert report["campaign_scope"]["timeframe"] == "4h"
    assert report["safety_invariants"]["can_execute"] is False
    assert len(report["ignored_artifacts"]) == 2
    assert {
        row["reason"] for row in report["ignored_artifacts"]
    } == {"scope_mismatch"}


def test_exact_campaign_closure_rejects_hypothesis() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure=_exact_campaign_closure(),
        run_status="missing",
        closure_status="present",
    )

    assert (
        report["scope_match_status"]
        == "matching_multiwindow_closure"
    )
    assert (
        report["failure_class"]
        == "all_preregistered_windows_failed"
    )
    assert report["recommended_action"] == "reject_hypothesis"
    assert report["action_authority"] == "report_only"


def test_exact_compound_scope_closure_matches() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure=_compound_scope_closure(),
        run_status="missing",
        closure_status="present",
    )

    assert (
        report["scope_match_status"]
        == "matching_multiwindow_closure"
    )
    assert report["recommended_action"] == "reject_hypothesis"


def test_hypothesis_only_match_is_rejected() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure={
            "hypothesis_id": "trend_pullback_v1",
            "campaign_outcome": (
                "all_windows_non_positive_trade_count"
            ),
        },
        run_status="missing",
        closure_status="present",
    )

    assert (
        report["scope_match_status"]
        == "no_matching_preregistered_evidence"
    )
    assert report["ignored_artifacts"][0]["reason"] == "scope_mismatch"


def test_strategy_family_only_match_is_rejected() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure={
            "strategy_family": "trend_pullback",
            "campaign_outcome": (
                "all_windows_non_positive_trade_count"
            ),
        },
        run_status="missing",
        closure_status="present",
    )

    assert (
        report["scope_match_status"]
        == "no_matching_preregistered_evidence"
    )
    assert report["recommended_action"] == (
        "create_preregistered_sampling_plan"
    )


def test_partial_universe_match_is_rejected() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure={
            "hypothesis_id": "trend_pullback_v1",
            "preset_name": "trend_pullback_equities_4h",
            "universe": ["AAPL", "NVDA"],
            "campaign_outcome": (
                "all_windows_non_positive_trade_count"
            ),
        },
        run_status="missing",
        closure_status="present",
    )

    assert (
        report["scope_match_status"]
        == "no_matching_preregistered_evidence"
    )
    assert report["ignored_artifacts"][0]["reason"] == "scope_mismatch"


def test_malformed_closure_is_ignored_fail_closed() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure=None,
        run_status="missing",
        closure_status="malformed",
    )

    assert (
        report["recommended_action"]
        == "create_preregistered_sampling_plan"
    )
    assert report["ignored_artifacts"] == [
        {
            "artifact_path": (
                "logs/qre_multiwindow_evidence_closure/latest.json"
            ),
            "status": "malformed",
            "reason": "artifact_malformed",
        }
    ]


def test_unattributed_campaign_routes_to_operator_review() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(attributed=False),
        campaign_registry=_registry(),
        multiwindow_run=None,
        multiwindow_closure=None,
    )

    assert report["decision_status"] == "incomplete_unattributed"
    assert report["scope_match_status"] == "campaign_scope_unverified"
    assert report["recommended_action"] == "route_to_operator_review"
    assert report["safety_invariants"]["can_execute"] is False


def test_matching_run_with_remaining_window_uses_mapper() -> None:
    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=_registry(),
        multiwindow_run={
            "campaign_id": CAMPAIGN_ID,
            "window_results": [
                {
                    "recommended_next_action": {
                        "recommended_action": (
                            "run_next_preregistered_window"
                        )
                    }
                }
            ],
        },
        multiwindow_closure=None,
        run_status="present",
        closure_status="missing",
    )

    assert report["scope_match_status"] == "matching_multiwindow_run"
    assert report["failure_class"] == "non_positive_oos_trade_count"
    assert (
        report["recommended_action"]
        == "run_next_preregistered_window"
    )
    assert report["action_authority"] == "approval_required"


def test_cli_writes_json_and_markdown(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)

    evidence_path = (
        tmp_path / "research/campaign_level_evidence_latest.v1.json"
    )
    registry_path = (
        tmp_path / "research/campaign_registry_latest.v1.json"
    )
    evidence_path.parent.mkdir(parents=True)

    evidence_path.write_text(
        json.dumps(_campaign_evidence()),
        encoding="utf-8",
    )
    registry_path.write_text(
        json.dumps(_registry()),
        encoding="utf-8",
    )

    result = decision.main(["--from-current-artifacts"])

    assert result == 0

    json_output = (
        tmp_path / "research/campaign_evidence_decision_latest.v1.json"
    )
    markdown_output = (
        tmp_path / "research/campaign_evidence_decision_latest.md"
    )

    assert json_output.is_file()
    assert markdown_output.is_file()

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert (
        payload["recommended_action"]
        == "create_preregistered_sampling_plan"
    )
    assert "Campaign Evidence Decision" in markdown_output.read_text(
        encoding="utf-8"
    )


def test_module_contains_no_trading_runtime_imports() -> None:
    source = Path(decision.__file__).read_text(encoding="utf-8-sig")

    forbidden = (
        "broker",
        "paper_trading",
        "shadow_trading",
        "live_trading",
        "order_generation",
        "capital_allocation",
    )

    for token in forbidden:
        assert f"import {token}" not in source
        assert f"from {token}" not in source


def test_registry_timeframe_overrides_preset_fallback() -> None:
    registry = _registry()
    registry["campaigns"][CAMPAIGN_ID]["timeframe"] = "1h"

    report = decision.build_campaign_evidence_decision(
        campaign_evidence=_campaign_evidence(),
        campaign_registry=registry,
        multiwindow_run=None,
        multiwindow_closure=None,
    )

    assert report["campaign_scope"]["timeframe"] == "1h"
