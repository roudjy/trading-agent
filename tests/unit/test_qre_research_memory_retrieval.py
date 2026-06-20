from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_research_memory_retrieval as retrieval


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "research" / "research_latest.json",
        {
            "generated_at_utc": "2026-06-19T08:00:00Z",
            "results": [
                {
                    "strategy_name": "trend_pullback",
                    "hypothesis": "Trend pullback broadening",
                    "asset": "AAPL",
                    "interval": "1d",
                    "success": False,
                    "error": "non_positive_oos_trade_count",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {"campaigns": {"cmp-1": {"preset_name": "trend_pullback_continuation_daily_v1", "hypothesis_id": "trend_pullback_behavior_v1"}}},
    )
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json",
        {
            "record": {
                "hypothesis_id": "trend_pullback_behavior_v1",
                "behavior_id": "trend_pullback",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "timeframe": "1d",
                "hypothesis_disposition": "not_supported",
                "failure_classes": ["non_positive_oos_trade_count", "no_oos_evidence"],
                "reason_record_refs": ["rr-1"],
                "accepted_lineage_refs": ["lineage-1", "lineage-2"],
                "accepted_oos_refs": [],
                "regime_refs": ["trend", "high_volatility"],
                "window_refs": ["window-1", "window-2"],
                "retry_policy": {"same_scope_suppressed": True},
                "disposition_scope": {
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "behavior_id": "trend_pullback",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframe": "1d",
                    "universe_or_basket_scope": "AAPL/NVDA bounded basket",
                },
            }
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "recommended_research_action": "propose_materially_new_behavior_family",
            "eligible_directions": [
                {
                    "direction_id": "behavior_rotation::volatility_compression_breakout",
                    "direction_type": "different_behavior_family",
                    "route_status": "eligible_context_only",
                    "eligibility_reasons": ["materially_new_behavior_direction"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_evidence_breadth_framework" / "latest.json",
        {
            "coverage_matrix": [
                {
                    "dimension": "preset",
                    "scope_key": "trend_pullback_continuation_daily_v1",
                    "inventory_count": 1,
                    "basket_count": 1,
                    "accepted_oos_count": 0,
                    "rejected_hypothesis_count": 1,
                    "blocker_reasons": ["oos_evidence_missing"],
                },
                {
                    "dimension": "behavior",
                    "scope_key": "trend_pullback",
                    "inventory_count": 1,
                    "basket_count": 1,
                    "accepted_oos_count": 0,
                    "rejected_hypothesis_count": 1,
                    "blocker_reasons": ["no_oos_evidence"],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_source_identity_authority_normalization" / "latest.json",
        {
            "rows": [
                {
                    "scope_key": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "authority_status": "blocked_provider_symbol_ambiguity",
                    "authority_reasons": ["provider_symbol_verification_required"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json",
        {
            "window_results": [
                {"regime_label": "trend", "symbol_results": [{"oos_records": []}]},
                {"regime_label": "high_volatility", "symbol_results": [{"oos_records": []}]},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_multiwindow_evidence_closure" / "latest.json",
        {"generated_at_utc": "2026-06-19T08:05:00Z"},
    )


def test_build_research_memory_retrieval_answers_required_queries(tmp_path: Path) -> None:
    _seed_artifacts(tmp_path)

    left = retrieval.build_research_memory_retrieval(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T09:00:00Z",
    )
    right = retrieval.build_research_memory_retrieval(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T09:00:00Z",
    )

    assert left == right
    assert left["summary"]["research_memory_ready"] is True
    queries = {row["query_id"]: row for row in left["queries"]}
    assert queries["exact_scope_already_tested"]["answer"] is True
    assert queries["materially_similar_scope_rejected"]["answer"] is True
    assert queries["regimes_consistently_no_trades"]["rows"][0]["regime_label"] == "trend"
    assert queries["presets_with_inadequate_sample_density"]["rows"][0]["preset_id"] == "trend_pullback_continuation_daily_v1"
    assert queries["recurring_evidence_or_source_failures"]["rows"][0]["count"] >= 1
    assert queries["novel_remaining_research_directions"]["rows"][0]["direction_type"] == "different_behavior_family"
    assert (
        queries["source_authority_remaining_scope_gaps"]["rows"][0]["authority_status"]
        == "blocked_provider_symbol_ambiguity"
    )
    assert queries["stale_or_superseded_knowledge"]["status"] in {"matched", "not_found"}
    assert left["authority_boundary"]["retrieval_is_context_not_truth"] is True
    assert left["summary"]["source_authority_blocked_scope_count"] == 1
    assert left["deterministic_hash"].startswith("sha256:")


def test_write_outputs_writes_expected_files(tmp_path: Path) -> None:
    _seed_artifacts(tmp_path)
    report = retrieval.build_research_memory_retrieval(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T09:00:00Z",
    )
    paths = retrieval.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_research_memory_retrieval/latest.json",
        "operator_summary": "logs/qre_research_memory_retrieval/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()


def test_source_is_read_only() -> None:
    source = Path(retrieval.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source
