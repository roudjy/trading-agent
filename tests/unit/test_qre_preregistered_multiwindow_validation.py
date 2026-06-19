from __future__ import annotations

import json
from pathlib import Path

from research import qre_preregistered_multiwindow_validation as campaign
from research import qre_sampling_plan as sampling


def _sampling_plan() -> dict[str, object]:
    return sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_lineage", "structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        window_definitions=[
            {
                "window_id": "window_01",
                "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-07"},
                "oos_window": {"start": "2026-04-29", "end": "2026-05-07"},
                "role": "oos",
                "regime_label": "trend",
                "locked": True,
            },
            {
                "window_id": "window_02",
                "bounded_input_window": {"start": "2026-05-08", "end": "2026-06-08"},
                "oos_window": {"start": "2026-05-29", "end": "2026-06-08"},
                "role": "oos",
                "regime_label": "high_volatility",
                "locked": True,
            },
        ],
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )


def _approval(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_id": "approval-multiwindow-001",
        "approved_by": "operator:local",
        "approved_at_utc": "2026-06-19T10:05:00Z",
        "expiry_utc": "2026-06-21T10:05:00Z",
        "scope": {
            "symbols": ["AAA", "BBB"],
            "preset_id": "trend_pullback_continuation_daily_v1",
            "timeframe": "daily_v1",
        },
        "allowed_command_class": "bounded_controlled_validation",
        "allowed_output_paths": [
            "logs/qre_bounded_current_basket_generation_runner/",
            "logs/qre_controlled_validation_adapter_results/",
            "logs/qre_bounded_generation_artifact_acceptance_verifier/",
            "logs/qre_evidence_complete_basket_closure/",
        ],
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
    payload.update(overrides)
    return payload


def test_campaign_is_deterministic_and_windows_stay_locked() -> None:
    first = campaign.build_preregistered_multiwindow_validation(
        sampling_plan_payload=_sampling_plan(),
        approval_manifest=_approval(),
        local_source_ref="data/cache/market/local.parquet",
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[{"control_id": "null_daily_holdout", "required": True}],
    )
    second = campaign.build_preregistered_multiwindow_validation(
        sampling_plan_payload=_sampling_plan(),
        approval_manifest=_approval(),
        local_source_ref="data/cache/market/local.parquet",
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[{"control_id": "null_daily_holdout", "required": True}],
    )

    assert first == second
    assert first["status"] == "campaign_ready_preregistered_context"
    assert all(spec["locked"] is True for spec in first["window_run_specs"])
    assert "do_not_stop_early_for_positive_results" in first["stopping_rules"]
    assert campaign.compute_campaign_hash(first) == first["hash"]


def test_invalid_approval_is_blocked() -> None:
    report = campaign.build_preregistered_multiwindow_validation(
        sampling_plan_payload=_sampling_plan(),
        approval_manifest=_approval(real_run_allowed=False),
        local_source_ref="data/cache/market/local.parquet",
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[{"control_id": "null_daily_holdout", "required": True}],
    )

    assert report["status"] == "blocked_invalid_approval"
    assert "real_run_not_allowed" in report["blocked_reasons"]


def test_external_fetch_is_denied() -> None:
    report = campaign.build_preregistered_multiwindow_validation(
        sampling_plan_payload=_sampling_plan(),
        approval_manifest=_approval(external_fetch_allowed=True),
        local_source_ref="data/cache/market/local.parquet",
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[{"control_id": "null_daily_holdout", "required": True}],
    )

    assert report["status"] == "blocked_external_fetch_not_allowed"


def test_outcome_based_additions_and_strategy_tuning_are_not_present() -> None:
    report = campaign.build_preregistered_multiwindow_validation(
        sampling_plan_payload=_sampling_plan(),
        approval_manifest=_approval(),
        local_source_ref="data/cache/market/local.parquet",
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[{"control_id": "null_daily_holdout", "required": True}],
    )

    serialized = json.dumps(report, sort_keys=True)
    assert "sharpe" not in serialized.lower()
    assert "profit" not in serialized.lower()
    assert "parameter_tuning" not in "".join(report["acceptance_rules"]).lower()


def test_core_campaign_has_no_symbol_hardcoding() -> None:
    source = Path("research/qre_preregistered_multiwindow_validation.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
