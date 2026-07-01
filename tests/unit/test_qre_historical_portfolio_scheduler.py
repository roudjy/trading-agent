from __future__ import annotations

import json
from pathlib import Path

from research import qre_historical_portfolio_scheduler as scheduler


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "generated_research" / "campaign_execution" / "evidence" / "empirical_evidence_pack.v1.json",
        {
            "source_hypothesis_id": "cross_sectional_momentum_v0",
            "campaign_identity": "qcx_40d35874111bcd98",
            "recommended_next_action": "launch_data_oos_capacity_expansion",
            "disposition": "NEEDS_MORE_EVIDENCE",
            "decision_semantics": {
                "active_blocker": "REQUEST_MORE_EVIDENCE",
                "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
                "terminal_disposition": "NEEDS_MORE_EVIDENCE",
                "next_action": "launch_data_oos_capacity_expansion",
                "reason_codes": ["insufficient_activity"],
            },
            "oos": {"presence": "AVAILABLE", "sufficiency": "INSUFFICIENT"},
            "transaction_costs": {"presence": "AVAILABLE", "sufficiency": "INSUFFICIENT"},
            "slippage": {"presence": "AVAILABLE", "sufficiency": "INSUFFICIENT"},
            "null_model": {"presence": "AVAILABLE", "sufficiency": "INSUFFICIENT"},
        },
    )
    _write_json(
        tmp_path / "generated_research" / "campaign_execution" / "reports" / "second_campaign_closeout.v1.json",
        {
            "executed_campaign_identity": "qcx_40d35874111bcd98",
            "decision": {"strategy_decision": "REJECTED_SCREENING"},
            "feedback_routing": {"next_action": "launch_data_oos_capacity_expansion"},
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json",
        {
            "record": {
                "hypothesis_id": "trend_pullback_behavior_v1",
                "behavior_id": "pullback_continuation",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "timeframe": "1d",
                "hypothesis_disposition": "not_supported",
                "failure_classes": ["non_positive_oos_trade_count"],
                "reason_record_refs": ["rr-1"],
                "accepted_lineage_refs": [],
                "accepted_oos_refs": [],
                "regime_refs": ["trend"],
                "window_refs": ["window-1"],
                "retry_policy": {"same_scope_suppressed": True},
                "disposition_scope": {
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "behavior_id": "pullback_continuation",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframe": "1d",
                    "universe_or_basket_scope": "AAPL/NVDA bounded basket",
                },
            }
        },
    )


def test_scheduler_changes_ranking_and_suppresses_duplicates(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)

    monkeypatch.setattr(
        scheduler,
        "_candidate_rows",
        lambda _repo_root: [
            {
                "candidate_variant_id": "cross_sectional_momentum_v0::catalog::0",
                "candidate_source": "catalog",
                "hypothesis_id": "cross_sectional_momentum_v0",
                "source_hypothesis_id": "cross_sectional_momentum_v0",
                "mechanism_family": "cross_sectional_momentum",
                "behavior_family": "cross_sectional_momentum",
                "status": "planned",
                "cost_class": "medium",
                "eligible_campaign_types": [],
                "feature_dependencies": ["lookback_returns", "rank_returns"],
                "expected_failure_modes": ["insufficient_trades"],
                "baseline_reference": "",
                "priority_seed": 10.0,
                "provenance": ["research/strategy_hypothesis_catalog_latest.v1.json"],
                "portfolio_stage": "OOS_CAPACITY_BLOCKED",
                "portfolio_blocker": "oos_sample_size",
            },
            {
                "candidate_variant_id": "cross_sectional_momentum_v0::generated::0",
                "candidate_source": "generated_thesis",
                "hypothesis_id": "qhc_51bc7a5c7b3f64ba",
                "source_hypothesis_id": "cross_sectional_momentum_v0",
                "mechanism_family": "relative_strength",
                "behavior_family": "relative_strength",
                "status": "ADMITTED_GENERATION_BLOCKED",
                "cost_class": "medium",
                "eligible_campaign_types": ["daily_primary"],
                "feature_dependencies": ["lookback_returns", "rank_returns"],
                "expected_failure_modes": ["insufficient_trades", "cost_fragile"],
                "baseline_reference": "",
                "priority_seed": 22.0,
                "provenance": ["generated_research/hypotheses/registry/generated_thesis_registry.v1.json"],
                "portfolio_stage": "OOS_CAPACITY_BLOCKED",
                "portfolio_blocker": "oos_sample_size",
            },
            {
                "candidate_variant_id": "trend_pullback_v1::catalog::0",
                "candidate_source": "catalog",
                "hypothesis_id": "trend_pullback_v1",
                "source_hypothesis_id": "trend_pullback_v1",
                "mechanism_family": "trend_pullback",
                "behavior_family": "trend_pullback",
                "status": "active_discovery",
                "cost_class": "medium",
                "eligible_campaign_types": ["daily_primary"],
                "feature_dependencies": ["ema_fast", "ema_slow"],
                "expected_failure_modes": ["insufficient_trades", "cost_fragile"],
                "baseline_reference": "ema_trend_baseline",
                "priority_seed": 30.0,
                "provenance": ["research/strategy_hypothesis_catalog_latest.v1.json"],
                "portfolio_stage": "",
                "portfolio_blocker": "",
            },
            {
                "candidate_variant_id": "dynamic_pairs_v0::catalog::0",
                "candidate_source": "catalog",
                "hypothesis_id": "dynamic_pairs_v0",
                "source_hypothesis_id": "dynamic_pairs_v0",
                "mechanism_family": "dynamic_pairs",
                "behavior_family": "dynamic_pairs",
                "status": "disabled",
                "cost_class": "high",
                "eligible_campaign_types": [],
                "feature_dependencies": ["rolling_beta"],
                "expected_failure_modes": ["parameter_fragile"],
                "baseline_reference": "",
                "priority_seed": 2.0,
                "provenance": ["research/strategy_hypothesis_catalog_latest.v1.json"],
                "portfolio_stage": "",
                "portfolio_blocker": "",
            },
        ],
    )
    monkeypatch.setattr(
        scheduler.research_memory,
        "build_research_memory",
        lambda **_: {
            "summary": {"entry_count": 4, "memory_content_hash": "sha256:deadbeef"},
            "entries": [{"artifact_id": "x", "keywords": ["cross_sectional_momentum_v0"], "ontology_tags": []}],
        },
    )
    monkeypatch.setattr(
        scheduler.research_memory,
        "retrieve",
        lambda _memory, query, limit=5: [{"artifact_id": query, "score": 1}] if "cross_sectional" in query or "trend" in query else [],
    )
    monkeypatch.setattr(
        scheduler.memory_retrieval,
        "build_research_memory_retrieval",
        lambda **_: {
            "summary": {
                "query_count": 3,
                "matched_query_count": 2,
                "research_memory_ready": True,
                "final_recommendation": "failure_retrieval_ready",
            },
            "queries": [
                {"query_id": "materially_similar_scope_rejected", "status": "matched"},
                {"query_id": "recurring_evidence_or_source_failures", "status": "matched"},
                {"query_id": "contradictory_outcomes", "status": "not_found"},
            ],
            "deterministic_hash": "sha256:1234",
        },
    )
    monkeypatch.setattr(
        scheduler.current_artifacts,
        "build_research_memory_current_artifacts",
        lambda **_: {
            "summary": {
                "final_recommendation": "research_memory_current_artifacts_ready",
                "indexed_entry_count": 4,
            }
        },
    )
    monkeypatch.setattr(
        scheduler.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {"summary": {"campaign_throughput_bottleneck_intelligence_ready": True, "bottleneck_count": 1}},
    )
    monkeypatch.setattr(
        scheduler.source_usefulness,
        "build_source_usefulness_ledger",
        lambda **_: {"summary": {"research_ready": True, "source_count": 1, "ready_source_count": 1}, "rows": [{"source": "yfinance", "usefulness_state": "useful"}]},
    )
    monkeypatch.setattr(
        scheduler.disposition_memory,
        "evaluate_revisit_eligibility",
        lambda _memory, proposed_scope: {
            "eligible": proposed_scope.get("hypothesis_id") != "trend_pullback_v1",
            "reason": "same_failed_scope_suppressed" if proposed_scope.get("hypothesis_id") == "trend_pullback_v1" else "materially_new_scope",
        },
    )
    monkeypatch.setattr(
        scheduler.dcal,
        "classify_terminal_disposition",
        lambda **_: {
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
            "reason_codes": ["insufficient_activity"],
        },
    )

    report = scheduler.build_historical_portfolio_scheduler(repo_root=tmp_path)

    assert report["summary"]["candidate_count"] == 4
    assert report["summary"]["ranking_changed"] is True
    assert report["summary"]["duplicate_suppressed_count"] >= 1
    assert report["summary"]["cycle_count"] == 3
    assert report["summary"]["exact_match_hit_rate"] == 1.0
    assert report["real_hypothesis_follow_up"]["new_terminal_disposition"] == "NEEDS_MORE_EVIDENCE"
    assert any(row["admission_status"] == "SUPPRESSED_DUPLICATE" for row in report["candidates"])
    assert any(row["admission_status"] == "ADMITTED" for row in report["cycles"][0]["admitted_candidates"])
    assert report["terminal_outcomes"]


def test_scheduler_write_outputs_and_status(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)
    monkeypatch.setattr(scheduler, "_candidate_rows", lambda _repo_root: [])
    monkeypatch.setattr(
        scheduler.research_memory,
        "build_research_memory",
        lambda **_: {"summary": {"entry_count": 0, "memory_content_hash": "sha256:0"}, "entries": []},
    )
    monkeypatch.setattr(
        scheduler.memory_retrieval,
        "build_research_memory_retrieval",
        lambda **_: {"summary": {"query_count": 0, "matched_query_count": 0, "research_memory_ready": False, "final_recommendation": "failure_retrieval_not_ready"}, "queries": [], "deterministic_hash": "sha256:0"},
    )
    monkeypatch.setattr(
        scheduler.current_artifacts,
        "build_research_memory_current_artifacts",
        lambda **_: {"summary": {"final_recommendation": "research_memory_current_artifacts_partial"}},
    )
    monkeypatch.setattr(
        scheduler.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {"summary": {"campaign_throughput_bottleneck_intelligence_ready": False, "bottleneck_count": 0}},
    )
    monkeypatch.setattr(
        scheduler.source_usefulness,
        "build_source_usefulness_ledger",
        lambda **_: {"summary": {"research_ready": False, "source_count": 0, "ready_source_count": 0}, "rows": []},
    )
    monkeypatch.setattr(
        scheduler.disposition_memory,
        "evaluate_revisit_eligibility",
        lambda _memory, proposed_scope: {"eligible": True, "reason": "materially_new_scope"},
    )
    monkeypatch.setattr(
        scheduler.dcal,
        "classify_terminal_disposition",
        lambda **_: {
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "resolved_blockers": [],
            "reason_codes": ["insufficient_activity"],
        },
    )

    report = scheduler.build_historical_portfolio_scheduler(repo_root=tmp_path)
    paths = scheduler.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_historical_portfolio_scheduler/latest.json"
    assert paths["operator_summary"] == "logs/qre_historical_portfolio_scheduler/operator_summary.md"
    assert scheduler.read_status(repo_root=tmp_path)["status"] == "ready"
