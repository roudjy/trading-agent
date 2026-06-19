from __future__ import annotations

from pathlib import Path

from research import qre_failure_to_action_mapper as failure_mapper
from research import qre_preregistered_multiwindow_evidence_run as run


def _approval() -> dict[str, object]:
    return {
        "approval_id": "approval-multiwindow-001",
        "approved_by": "operator:local",
        "approved_at_utc": "2026-06-19T10:05:00Z",
        "expiry_utc": "2026-06-21T10:05:00Z",
        "scope": {
            "symbols": ["AAA", "BBB"],
            "preset_id": "trend_pullback_continuation_daily_v1",
            "timeframe": "daily_v1",
            "source_data_ref": "data/cache/market/local.parquet",
            "window_definitions": [
                {
                    "window_id": "window_01",
                    "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-07"},
                    "oos_window": {"start": "2026-04-29", "end": "2026-05-07"},
                    "regime_label": "trend",
                },
                {
                    "window_id": "window_02",
                    "bounded_input_window": {"start": "2026-05-08", "end": "2026-06-08"},
                    "oos_window": {"start": "2026-05-29", "end": "2026-06-08"},
                    "regime_label": "high_volatility",
                },
            ],
        },
        "allowed_command_class": "bounded_controlled_validation",
        "allowed_output_paths": list(run.ALLOWED_OUTPUT_PATHS),
        "forbidden_capabilities": ["strategy_synthesis", "parameter_optimization", "external_fetch"],
        "dry_run_allowed": True,
        "real_run_allowed": True,
        "evidence_acceptance_allowed": True,
        "external_fetch_allowed": False,
    }


def test_all_preregistered_windows_execute_in_order_and_failures_remain_visible(monkeypatch) -> None:
    monkeypatch.setattr(
        run,
        "build_sampling_plan_for_multiwindow_approval",
        lambda **_: {
            "sampling_plan_id": "plan-001",
            "hash": "plan-hash",
            "status": "sampling_plan_ready_context_only",
            "window_definitions": [
                {
                    "window_id": "window_01",
                    "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-07"},
                    "oos_window": {"start": "2026-04-29", "end": "2026-05-07"},
                    "regime_label": "trend",
                },
                {
                    "window_id": "window_02",
                    "bounded_input_window": {"start": "2026-05-08", "end": "2026-06-08"},
                    "oos_window": {"start": "2026-05-29", "end": "2026-06-08"},
                    "regime_label": "high_volatility",
                },
            ],
        },
    )
    monkeypatch.setattr(
        run,
        "build_campaign_for_multiwindow_approval",
        lambda **_: {
            "campaign_id": "camp-001",
            "hash": "camp-hash",
            "sampling_plan_hash": "plan-hash",
            "window_run_specs": [
                {
                    "window_id": "window_01",
                    "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-07"},
                    "oos_window": {"start": "2026-04-29", "end": "2026-05-07"},
                    "regime_label": "trend",
                    "symbols": ["AAA"],
                },
                {
                    "window_id": "window_02",
                    "bounded_input_window": {"start": "2026-05-08", "end": "2026-06-08"},
                    "oos_window": {"start": "2026-05-29", "end": "2026-06-08"},
                    "regime_label": "high_volatility",
                    "symbols": ["AAA"],
                },
            ],
            "minimum_required_windows": 2,
            "minimum_total_oos_trades": 1,
            "status": "campaign_ready_preregistered_context",
        },
    )
    monkeypatch.setattr(run.campaign_builder, "compute_campaign_hash", lambda _: "camp-hash")
    calls: list[str] = []

    def fake_classify_window_symbol(**kwargs):
        calls.append(kwargs["window_spec"]["window_id"])
        if kwargs["window_spec"]["window_id"] == "window_01":
            return {
                "window_id": "window_01",
                "symbol": "AAA",
                "accepted_lineage_count": 1,
                "accepted_oos_count": 1,
                "positive_oos_trade_count": 2,
                "oos_trade_count": 2,
                "classification": "accepted_for_campaign_lineage",
                "rejection_reasons": [],
                "lineage_records": [{"candidate_id": "cand-001"}],
                "oos_records": [{"candidate_id": "cand-001"}],
            }
        return {
            "window_id": "window_02",
            "symbol": "AAA",
            "accepted_lineage_count": 1,
            "accepted_oos_count": 0,
            "positive_oos_trade_count": 0,
            "oos_trade_count": 0,
            "classification": "accepted_for_campaign_lineage_only",
            "rejection_reasons": ["non_positive_oos_trade_count"],
            "lineage_records": [{"candidate_id": "cand-001"}],
            "oos_records": [],
        }

    monkeypatch.setattr(run, "_classify_window_symbol", fake_classify_window_symbol)

    report = run.build_preregistered_multiwindow_evidence_run(approval_manifest=_approval())

    assert calls == ["window_01", "window_02"]
    assert report["accepted_window_count"] == 1
    assert report["failed_window_count"] == 1
    assert report["window_results"][1]["rejection_reasons"] == ["non_positive_oos_trade_count"]
    assert report["null_control_results"]["status"] in {"controls_incomplete", "controls_not_run"}
    assert report["null_control_results"]["blockers"]
    assert report["can_promote_candidate"] is False
    assert report["can_activate_deployment"] is False


def test_all_zero_windows_produce_fail_closed_outcome(monkeypatch) -> None:
    monkeypatch.setattr(
        run,
        "build_sampling_plan_for_multiwindow_approval",
        lambda **_: {"sampling_plan_id": "plan-001", "hash": "plan-hash", "status": "sampling_plan_ready_context_only"},
    )
    monkeypatch.setattr(
        run,
        "build_campaign_for_multiwindow_approval",
        lambda **_: {
            "campaign_id": "camp-001",
            "hash": "camp-hash",
            "sampling_plan_hash": "plan-hash",
            "window_run_specs": [
                {"window_id": "window_01", "regime_label": "trend", "symbols": ["AAA"]},
                {"window_id": "window_02", "regime_label": "range", "symbols": ["AAA"]},
            ],
            "minimum_required_windows": 2,
            "minimum_total_oos_trades": 1,
            "status": "campaign_ready_preregistered_context",
        },
    )
    monkeypatch.setattr(run.campaign_builder, "compute_campaign_hash", lambda _: "camp-hash")
    monkeypatch.setattr(
        run,
        "_classify_window_symbol",
        lambda **kwargs: {
            "window_id": kwargs["window_spec"]["window_id"],
            "symbol": "AAA",
            "accepted_lineage_count": 1,
            "accepted_oos_count": 0,
            "positive_oos_trade_count": 0,
            "oos_trade_count": 0,
            "classification": "accepted_for_campaign_lineage_only",
            "rejection_reasons": ["non_positive_oos_trade_count"],
            "lineage_records": [],
            "oos_records": [],
        },
    )

    report = run.build_preregistered_multiwindow_evidence_run(approval_manifest=_approval())

    assert report["campaign_outcome"] == "all_windows_non_positive_trade_count"
    assert report["accepted_oos_count"] == 0
    assert report["positive_oos_trade_count_total"] == 0


def test_campaign_run_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(
        run,
        "build_sampling_plan_for_multiwindow_approval",
        lambda **_: {"sampling_plan_id": "plan-001", "hash": "plan-hash", "status": "sampling_plan_ready_context_only"},
    )
    monkeypatch.setattr(
        run,
        "build_campaign_for_multiwindow_approval",
        lambda **_: {
            "campaign_id": "camp-001",
            "hash": "camp-hash",
            "sampling_plan_hash": "plan-hash",
            "window_run_specs": [{"window_id": "window_01", "regime_label": "trend", "symbols": ["AAA"]}],
            "minimum_required_windows": 1,
            "minimum_total_oos_trades": 1,
            "status": "campaign_ready_preregistered_context",
        },
    )
    monkeypatch.setattr(run.campaign_builder, "compute_campaign_hash", lambda _: "camp-hash")
    monkeypatch.setattr(
        run,
        "_classify_window_symbol",
        lambda **kwargs: {
            "window_id": "window_01",
            "symbol": "AAA",
            "accepted_lineage_count": 1,
            "accepted_oos_count": 1,
            "positive_oos_trade_count": 2,
            "oos_trade_count": 2,
            "classification": "accepted_for_campaign_lineage",
            "rejection_reasons": [],
            "lineage_records": [],
            "oos_records": [],
        },
    )

    first = run.build_preregistered_multiwindow_evidence_run(approval_manifest=_approval())
    second = run.build_preregistered_multiwindow_evidence_run(approval_manifest=_approval())

    assert first == second
    assert first["hash"] == run.compute_campaign_run_hash(first)


def test_core_run_has_no_symbol_hardcoding() -> None:
    source = Path("research/qre_preregistered_multiwindow_evidence_run.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
