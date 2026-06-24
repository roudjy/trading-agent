from __future__ import annotations

from pathlib import Path

from research import campaign_preregistered_multiwindow_evidence_run as campaign_run
from research import campaign_preregistered_sampling_plan as campaign_sampling
from research import qre_sampling_plan as sampling


def _proposal() -> dict[str, object]:
    return campaign_sampling.build_campaign_preregistered_sampling_plan(
        decision={
            "decision_status": "decision_ready",
            "recommended_action": "create_preregistered_sampling_plan",
            "action_authority": "report_only",
            "failure_class": "insufficient_window_length",
            "reason_codes": ["insufficient_window_length"],
            "prerequisites": ["larger_preregistered_local_range"],
            "selected_source": (
                "research/campaign_level_evidence_latest.v1.json"
            ),
            "evidence_refs": [
                "research/campaign_level_evidence_latest.v1.json"
            ],
            "campaign_scope": {
                "campaign_id": "campaign-source-001",
                "hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_equities_4h",
                "timeframe": "4h",
                "template_id": (
                    "daily_primary__trend_pullback_equities_4h"
                ),
                "strategy_family": "trend_pullback",
                "asset_class": "equity",
                "universe": ["AAA", "BBB"],
                "registry_record_present": True,
            },
            "safety_invariants": {
                "can_execute": False,
                "can_spawn_campaigns": False,
                "can_mutate_queue": False,
                "can_change_policy": False,
                "can_change_presets": False,
                "can_change_strategy": False,
                "can_access_paper_shadow_live": False,
            },
        },
        preregistration_timestamp="2026-06-24T17:58:20Z",
    )


def _approval(proposal: dict[str, object]) -> dict[str, object]:
    scope = proposal["campaign_scope"]
    assert isinstance(scope, dict)
    return {
        "approval_id": "approval-campaign-plan-001",
        "approved_by": "operator:local",
        "approved_at_utc": "2026-06-24T18:00:00Z",
        "expiry_utc": "2026-06-25T18:00:00Z",
        "scope": {
            "campaign_id": scope["campaign_id"],
            "proposal_id": proposal["proposal_id"],
            "proposal_hash": proposal["hash"],
            "symbols": list(scope["universe"]),
            "preset_id": scope["preset_name"],
            "timeframe": scope["timeframe"],
            "source_data_ref": "data/cache/market",
        },
        "allowed_command_class": "bounded_controlled_validation",
        "allowed_output_paths": list(
            campaign_run.multiwindow.ALLOWED_OUTPUT_PATHS
        ),
        "forbidden_capabilities": [
            "strategy_synthesis",
            "parameter_optimization",
            "external_fetch",
        ],
        "dry_run_allowed": True,
        "real_run_allowed": True,
        "evidence_acceptance_allowed": True,
        "external_fetch_allowed": False,
    }


def _common_dates() -> list[str]:
    return [f"2026-01-{day:02d}" for day in range(1, 29)] + [
        f"2026-02-{day:02d}" for day in range(1, 29)
    ]


def test_materializes_locked_windows_from_local_cache(monkeypatch) -> None:
    proposal = _proposal()
    approval = _approval(proposal)
    monkeypatch.setattr(
        campaign_run.multiwindow,
        "_load_common_trading_dates",
        lambda *_args, **_kwargs: _common_dates(),
    )

    plan = campaign_run.materialize_campaign_sampling_plan(
        proposal=proposal,
        approval_manifest=approval,
    )

    assert plan["status"] == "sampling_plan_ready_context_only"
    assert plan["timeframe"] == "4h"
    assert len(plan["window_definitions"]) == 2
    assert all(
        window["locked"] is True
        for window in plan["window_definitions"]
    )
    assert all(
        window["regime_label"] == "unclassified"
        for window in plan["window_definitions"]
    )
    assert sampling.validate_sampling_plan(plan)["valid"] is True


def test_requires_exact_operator_approval_binding() -> None:
    proposal = _proposal()
    approval = _approval(proposal)
    approval_scope = approval["scope"]
    assert isinstance(approval_scope, dict)
    approval_scope["proposal_hash"] = "wrong-hash"

    try:
        campaign_run.validate_proposal_approval_binding(
            proposal=proposal,
            approval_manifest=approval,
        )
    except ValueError as exc:
        assert str(exc) == (
            "campaign_proposal_approval_scope_mismatch:proposal_hash"
        )
    else:  # pragma: no cover
        raise AssertionError("proposal hash mismatch must fail closed")


def test_build_passes_only_materialized_plan_and_scope(monkeypatch) -> None:
    proposal = _proposal()
    approval = _approval(proposal)
    monkeypatch.setattr(
        campaign_run.multiwindow,
        "_load_common_trading_dates",
        lambda *_args, **_kwargs: _common_dates(),
    )
    captured: dict[str, object] = {}

    def fake_build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"campaign_outcome": "all_windows_non_positive_trade_count"}

    monkeypatch.setattr(
        campaign_run.multiwindow,
        "build_preregistered_multiwindow_evidence_run",
        fake_build,
    )

    report = campaign_run.build_campaign_preregistered_multiwindow_evidence_run(
        proposal=proposal,
        approval_manifest=approval,
    )

    plan = captured["sampling_plan_payload"]
    scope = captured["campaign_scope"]
    assert isinstance(plan, dict)
    assert isinstance(scope, dict)
    assert plan["status"] == "sampling_plan_ready_context_only"
    assert scope["campaign_id"] == "campaign-source-001"
    assert captured["proposal_id"] == proposal["proposal_id"]
    assert captured["proposal_hash"] == proposal["hash"]
    assert report["campaign_outcome"] == (
        "all_windows_non_positive_trade_count"
    )


def test_campaign_runner_contains_no_campaign_or_symbol_hardcoding() -> None:
    source = Path(
        "research/campaign_preregistered_multiwindow_evidence_run.py"
    ).read_text(encoding="utf-8")

    assert "col-20260605" not in source
    assert "AAPL" not in source
    assert "NVDA" not in source
