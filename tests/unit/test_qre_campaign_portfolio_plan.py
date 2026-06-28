from __future__ import annotations

import ast
from pathlib import Path

from reporting import qre_campaign_portfolio_plan as report


PRESET_SOURCE = """
_CRYPTO_UNIVERSE = ("BTC-EUR", "ETH-EUR", "SOL-EUR")
_EQUITY_UNIVERSE = ("AAPL", "MSFT")
PRESETS = (
    ResearchPreset(
        name="trend_pullback_crypto_1h",
        universe=_CRYPTO_UNIVERSE,
        timeframe="1h",
        bundle=("trend_pullback_v1",),
        hypothesis_id="trend_pullback_v1",
        cost_mode="realistic",
        status="stable",
        enabled=True,
    ),
    ResearchPreset(
        name="trend_pullback_equities_4h",
        universe=_EQUITY_UNIVERSE,
        timeframe="4h",
        bundle=("trend_pullback_v1",),
        hypothesis_id="trend_pullback_v1",
        cost_mode="realistic",
        status="stable",
        enabled=True,
    ),
    ResearchPreset(
        name="vol_compression_breakout_crypto_1h",
        universe=_CRYPTO_UNIVERSE,
        timeframe="1h",
        bundle=("volatility_compression_breakout",),
        hypothesis_id="volatility_compression_breakout_v0",
        cost_mode="realistic",
        status="stable",
        enabled=True,
    ),
)
"""


def _base_registry() -> dict[str, object]:
    return {
        "rows": [
            {
                "thesis_id": "qbt_pullback",
                "source_hypothesis_id": "trend_pullback_v1",
                "title": "Pullback Continuation: trend_pullback_v1",
                "behavior_family": "pullback_continuation",
                "mechanism": "Temporary retracement within a trend resolves and resumes the prior directional move.",
                "expected_behavior": "retracement_into_trend_zone",
                "regime_context": "bounded_existing_research_scope:pullback_continuation",
                "supporting_evidence": ["registry:trend_pullback_v1"],
                "contradicting_evidence": ["memory:trend_pullback_v1"],
                "minimum_sample": "campaign_specific_minimum_sample_required_before_support",
                "signal_density_expectation": "moderate",
                "null_controls": ["shuffle_returns", "qre_null_control_falsification_suite"],
                "provenance_refs": ["registry:trend_pullback_v1"],
                "status": "research_ready",
                "universe": "existing_preset_bound_universes_only",
            },
            {
                "thesis_id": "qbt_vol",
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "title": "Volatility Compression Breakout: volatility_compression_breakout_v0",
                "behavior_family": "volatility_compression_breakout",
                "mechanism": "Compressed volatility resolves into expansion with a directional breakout.",
                "expected_behavior": "narrow_range_compression",
                "regime_context": "bounded_existing_research_scope:volatility_compression_breakout",
                "supporting_evidence": ["registry:volatility_compression_breakout_v0"],
                "contradicting_evidence": ["none_recorded:contradicting_evidence"],
                "minimum_sample": "campaign_specific_minimum_sample_required_before_support",
                "signal_density_expectation": "moderate",
                "null_controls": ["shuffle_returns", "qre_null_control_falsification_suite"],
                "provenance_refs": ["registry:volatility_compression_breakout_v0"],
                "status": "research_ready",
                "universe": "existing_preset_bound_universes_only",
            },
            {
                "thesis_id": "qbt_draft",
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "title": "Trend Continuation: atr_adaptive_trend_v0",
                "behavior_family": "trend_continuation",
                "mechanism": "Trend-anchor met ATR-genormaliseerde move filter.",
                "expected_behavior": "higher_highs_or_lower_lows",
                "regime_context": "blocked:regime_context_pending:active",
                "supporting_evidence": ["registry:atr_adaptive_trend_v0"],
                "contradicting_evidence": ["none_recorded:contradicting_evidence"],
                "minimum_sample": "blocked:minimum_sample_not_defined_until_research_ready",
                "signal_density_expectation": "moderate",
                "null_controls": ["blocked:null_controls:behavior_not_research_ready"],
                "provenance_refs": ["registry:atr_adaptive_trend_v0"],
                "status": "draft",
                "universe": "blocked:campaign_scope_pending_registry_maturation",
            },
            {
                "thesis_id": "qbt_disabled",
                "source_hypothesis_id": "dynamic_pairs_v0",
                "title": "Mean Reversion: dynamic_pairs_v0",
                "behavior_family": "mean_reversion",
                "mechanism": "Transient deviations revert toward a local mean after bounded extreme moves.",
                "expected_behavior": "overshoot_then_revert",
                "regime_context": "blocked:regime_context_pending:provisional",
                "supporting_evidence": ["registry:dynamic_pairs_v0"],
                "contradicting_evidence": ["none_recorded:contradicting_evidence"],
                "minimum_sample": "blocked:minimum_sample_not_defined_until_research_ready",
                "signal_density_expectation": "blocked",
                "null_controls": ["blocked:null_controls:behavior_not_research_ready"],
                "provenance_refs": ["registry:dynamic_pairs_v0"],
                "status": "blocked",
                "universe": "blocked:campaign_scope_pending_registry_maturation",
            },
        ]
    }


def _base_operator() -> dict[str, object]:
    return {
        "rows": [
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "final_decision": "REJECTED",
                "next_action": "reject_hypothesis",
                "primary_reasons": [
                    "The preregistered campaign completed with no positive OOS trades."
                ],
                "funnel_result": {
                    "campaign_id": "campaign-pullback",
                    "accepted_oos_count": 0,
                    "accepted_window_count": 0,
                    "failed_window_count": 2,
                    "positive_oos_trade_count_total": 0,
                    "campaign_outcome": "all_windows_non_positive_trade_count",
                    "status": "all_windows_no_oos_trades",
                },
                "oos": {
                    "accepted_oos_count": 0,
                    "accepted_window_count": 0,
                    "positive_oos_trade_count_total": 0,
                    "status": "campaign_closure:all_windows_no_oos_trades",
                },
                "null_controls": {
                    "status": "controls_incomplete",
                    "missing_control_ids": ["null_preregistered_holdout"],
                },
                "lineage_completeness": {"lineage_complete": True, "missing_lineage_fields": []},
                "provenance_refs": ["operator:trend_pullback_v1"],
            },
            {
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "final_decision": "BLOCKED",
                "next_action": "establish_campaign_lineage_for_thesis",
                "lineage_completeness": {
                    "lineage_complete": False,
                    "missing_lineage_fields": [
                        "campaign_identity",
                        "data_snapshot_identity",
                        "source_identity",
                    ],
                },
                "provenance_refs": ["operator:volatility_compression_breakout_v0"],
            },
            {
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "final_decision": "BLOCKED",
                "next_action": "establish_campaign_lineage_for_thesis",
                "lineage_completeness": {
                    "lineage_complete": False,
                    "missing_lineage_fields": ["campaign_identity"],
                },
                "provenance_refs": ["operator:atr_adaptive_trend_v0"],
            },
            {
                "source_hypothesis_id": "dynamic_pairs_v0",
                "final_decision": "BLOCKED",
                "next_action": "establish_campaign_lineage_for_thesis",
                "lineage_completeness": {
                    "lineage_complete": False,
                    "missing_lineage_fields": ["campaign_identity"],
                },
                "provenance_refs": ["operator:dynamic_pairs_v0"],
            },
        ]
    }


def _base_hypothesis_catalog() -> dict[str, object]:
    return {
        "hypotheses": [
            {
                "hypothesis_id": "trend_pullback_v1",
                "status": "active_discovery",
                "cost_class": "medium",
                "eligible_campaign_types": ["daily_primary", "weekly_retest"],
            },
            {
                "hypothesis_id": "volatility_compression_breakout_v0",
                "status": "active_discovery",
                "cost_class": "medium",
                "eligible_campaign_types": ["daily_primary", "weekly_retest"],
            },
            {
                "hypothesis_id": "atr_adaptive_trend_v0",
                "status": "planned",
                "cost_class": "medium",
                "eligible_campaign_types": [],
            },
            {
                "hypothesis_id": "dynamic_pairs_v0",
                "status": "disabled",
                "cost_class": "high",
                "eligible_campaign_types": [],
            },
        ]
    }


def _base_campaign_metadata() -> dict[str, object]:
    return {
        "hypotheses": {
            "trend_pullback_v1": {"eligible_campaign_types": ["daily_primary", "weekly_retest"]},
            "volatility_compression_breakout_v0": {"eligible_campaign_types": ["daily_primary", "weekly_retest"]},
            "atr_adaptive_trend_v0": {"eligible_campaign_types": []},
            "dynamic_pairs_v0": {"eligible_campaign_types": []},
        }
    }


def _base_templates() -> dict[str, object]:
    return {
        "config": {
            "daily_compute_budget_seconds": 57600,
            "lease_ttl_seconds": 7200,
        },
        "templates": [
            {
                "template_id": "daily_primary__trend_pullback_crypto_1h",
                "preset_name": "trend_pullback_crypto_1h",
                "estimated_runtime_seconds_default": 1800,
            },
            {
                "template_id": "daily_primary__trend_pullback_equities_4h",
                "preset_name": "trend_pullback_equities_4h",
                "estimated_runtime_seconds_default": 1800,
            },
            {
                "template_id": "daily_primary__vol_compression_breakout_crypto_1h",
                "preset_name": "vol_compression_breakout_crypto_1h",
                "estimated_runtime_seconds_default": 1800,
            },
        ],
    }


def _base_preset_policy() -> dict[str, object]:
    return {
        "presets": {
            "trend_pullback_crypto_1h": {"policy_state": "active"},
            "trend_pullback_equities_4h": {"policy_state": "active"},
            "vol_compression_breakout_crypto_1h": {"policy_state": "active"},
        }
    }


def _base_cache() -> dict[str, object]:
    return {
        "coverage": [
            {"instrument": "BTC-EUR", "timeframe": "1h", "ready": True, "row_count": 10, "min_timestamp_utc": "2024-01-01T00:00:00Z", "max_timestamp_utc": "2026-01-01T00:00:00Z"},
            {"instrument": "ETH-EUR", "timeframe": "1h", "ready": True, "row_count": 10, "min_timestamp_utc": "2024-01-01T00:00:00Z", "max_timestamp_utc": "2026-01-01T00:00:00Z"},
            {"instrument": "SOL-EUR", "timeframe": "1h", "ready": True, "row_count": 10, "min_timestamp_utc": "2024-01-01T00:00:00Z", "max_timestamp_utc": "2026-01-01T00:00:00Z"},
            {"instrument": "AAPL", "timeframe": "4h", "ready": True, "row_count": 5, "min_timestamp_utc": "2024-01-01T00:00:00Z", "max_timestamp_utc": "2026-01-01T00:00:00Z"},
            {"instrument": "MSFT", "timeframe": "4h", "ready": True, "row_count": 5, "min_timestamp_utc": "2024-01-01T00:00:00Z", "max_timestamp_utc": "2026-01-01T00:00:00Z"},
        ]
    }


def _base_identity() -> dict[str, object]:
    return {
        "rows": [
            {"symbol": "AAPL", "authority_status": "normalized_context_ready", "instrument_identity_status": "OK", "source_identity_status": "provider_symbol_verified"},
            {"symbol": "MSFT", "authority_status": "normalized_context_ready", "instrument_identity_status": "OK", "source_identity_status": "provider_symbol_verified"},
        ]
    }


def _base_source_usefulness() -> dict[str, object]:
    return {
        "summary": {
            "research_ready": True,
            "ready_source_count": 1,
            "source_count": 1,
            "cache_manifest_ready": True,
        },
        "rows": [{"source_id": "yfinance"}],
    }


def _base_prior_failure() -> dict[str, object]:
    return {
        "rows": [
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "dead_zone_count": 1,
                "provenance_refs": ["prior:trend_pullback_v1"],
                "retrieval_items": [
                    {"retrieval_kind": "dead_zone", "retrieval_ref": "dedup:exact"},
                ],
            },
            {
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "dead_zone_count": 0,
                "provenance_refs": ["prior:volatility_compression_breakout_v0"],
                "retrieval_items": [],
            },
        ]
    }


def _base_dedup() -> dict[str, object]:
    return {
        "duplicate_rows": [
            {"duplicate_class": "exact_failed_scope", "exact_next_action": "preserve_suppressed_scope_boundary"},
            {"duplicate_class": "materially_equivalent_retry", "exact_next_action": "preserve_suppressed_scope_boundary"},
        ]
    }


def _base_sampling_plan() -> dict[str, object]:
    return {
        "campaign_scope": {
            "hypothesis_id": "trend_pullback_v1",
            "preset_name": "trend_pullback_equities_4h",
        },
        "coverage_requirements": {
            "minimum_window_length": 20,
            "minimum_common_trading_dates": 40,
        },
        "sampling_plan": {
            "status": "blocked_insufficient_range",
            "minimum_window_length": 20,
            "window_definitions": [],
            "null_control_definitions": [
                {"control_id": "null_preregistered_holdout", "required_for_evidence_complete": True}
            ],
        },
    }


def _base_multiwindow_run() -> dict[str, object]:
    return {
        "campaign_scope": {
            "hypothesis_id": "trend_pullback_v1",
            "preset_name": "trend_pullback_equities_4h",
        },
        "accepted_oos_count": 0,
        "accepted_window_count": 0,
        "failed_window_count": 2,
        "positive_oos_trade_count_total": 0,
        "null_control_results": {
            "status": "controls_incomplete",
            "missing_control_ids": ["null_preregistered_holdout"],
            "recommended_next_action": "materialize_missing_preregistered_controls",
        },
    }


def _base_campaign_registry() -> dict[str, object]:
    return {
        "campaigns": {
            "campaign-pullback": {
                "campaign_id": "campaign-pullback",
                "hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_equities_4h",
            }
        }
    }


def _base_breadth() -> dict[str, object]:
    return {
        "breadth_priority_recommendations": [
            {
                "scope_key": "trend_continuation",
                "scope_label": "trend_continuation",
                "priority_score": 100,
                "reason": "Inventory exists, accepted OOS remains absent, and the current scope is still incomplete.",
                "recommended_next_action": "plan_read_only_breadth_expansion",
            },
            {
                "scope_key": "volatility_compression_breakout",
                "scope_label": "volatility_compression_breakout",
                "priority_score": 100,
                "reason": "Inventory exists, accepted OOS remains absent, and the current scope is still incomplete.",
                "recommended_next_action": "plan_read_only_breadth_expansion",
            },
        ]
    }


def _build() -> dict[str, object]:
    return report.build_campaign_portfolio_plan(
        registry_report=_base_registry(),
        operator_report=_base_operator(),
        why_report={"rows": []},
        suppression_report={"summary": {"final_recommendation": "suppression_efficacy_insufficient_baseline"}},
        dedup_report=_base_dedup(),
        router_report={"eligible_directions": []},
        prior_failure_report=_base_prior_failure(),
        source_usefulness_report=_base_source_usefulness(),
        source_identity_report=_base_identity(),
        cache_report=_base_cache(),
        breadth_report=_base_breadth(),
        hypothesis_catalog_report=_base_hypothesis_catalog(),
        campaign_metadata_report=_base_campaign_metadata(),
        templates_report=_base_templates(),
        preset_policy_report=_base_preset_policy(),
        campaign_registry_report=_base_campaign_registry(),
        sampling_plan_report=_base_sampling_plan(),
        multiwindow_run_report=_base_multiwindow_run(),
        budget_report={"daily_compute_budget_seconds": 57600, "lease_ttl_seconds": 7200},
        presets_source=PRESET_SOURCE,
    )


def test_build_is_deterministic_and_stable_ids() -> None:
    left = _build()
    right = _build()

    assert left == right
    assert left["portfolio_identity"].startswith("qcpp_")
    assert len({row["cell_id"] for row in left["rows"]}) == len(left["rows"])


def test_exact_failed_scope_is_excluded_and_zero_oos_is_preserved() -> None:
    out = _build()

    row = next(row for row in out["rows"] if row["preset_name"] == "trend_pullback_equities_4h")
    assert row["inclusion_status"] == "EXCLUDED_DEAD_ZONE"
    assert row["available_oos_window"]["accepted_oos_count"] == 0
    assert row["null_control_feasibility"]["status"] == "controls_incomplete"
    assert row["next_action"] == "preserve_suppressed_scope_boundary"


def test_missing_identity_blocks_crypto_and_missing_preset_fails_closed() -> None:
    out = _build()

    crypto = next(row for row in out["rows"] if row["preset_name"] == "vol_compression_breakout_crypto_1h")
    draft = next(row for row in out["rows"] if row["source_hypothesis_id"] == "atr_adaptive_trend_v0")
    disabled = next(row for row in out["rows"] if row["source_hypothesis_id"] == "dynamic_pairs_v0")

    assert crypto["identity_readiness"]["status"] == "missing"
    assert crypto["inclusion_status"] == "BLOCKED"
    assert "identity_readiness_incomplete" in crypto["blocker_reasons"]
    assert draft["preset_name"] == ""
    assert draft["inclusion_status"] == "INSUFFICIENT_EVIDENCE"
    assert "no_executable_preset_mapping" in draft["blocker_reasons"]
    assert disabled["expected_signal_density"]["status"] == "unsupported"
    assert disabled["inclusion_status"] == "BLOCKED"


def test_status_vocab_and_provenance_are_closed() -> None:
    out = _build()

    for row in out["rows"]:
        assert row["inclusion_status"] in report.VALID_INCLUSION_STATUSES
        assert row["provenance_refs"]
        assert row["next_action"]
    assert out["summary"]["ready_cell_count"] == 0


def test_parse_preset_catalog_and_write_round_trip(tmp_path: Path) -> None:
    catalog = report.parse_preset_catalog(PRESET_SOURCE)
    out = _build()

    assert [row["name"] for row in catalog] == [
        "trend_pullback_crypto_1h",
        "trend_pullback_equities_4h",
        "vol_compression_breakout_crypto_1h",
    ]
    paths = report.write_outputs(out, repo_root=tmp_path)
    assert paths == {
        "latest": "logs/qre_campaign_portfolio_plan/latest.json",
        "latest_md": "logs/qre_campaign_portfolio_plan/latest.md",
        "doc": "docs/governance/qre_campaign_portfolio_plan.md",
    }
    assert report.read_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_campaign_portfolio_plan/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_module_remains_read_only_and_non_executing() -> None:
    source = Path(report.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "research/research_latest.json" not in source
    assert "research/strategy_matrix.csv" not in source
    assert "\"can_launch_campaign\": False" in source
