from __future__ import annotations

import json
from pathlib import Path

from research import qre_real_basket_evidence_coverage as coverage


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_bridge_row(tmp_path: Path, row: dict) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [row]},
    )


def test_build_real_basket_evidence_coverage_maps_lineage_and_oos_evidence(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "coverage": [
                {"instrument": "AAPL", "timeframe": "1d", "ready": True},
                {"instrument": "ASML", "timeframe": "1d", "ready": True},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [
                {"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"},
                {"instrument": "ASML", "timeframe": "1d", "quality_status": "ready"},
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 14,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "state": "completed",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )

    report = coverage.build_real_basket_evidence_coverage(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["report_kind"] == "qre_real_basket_evidence_coverage"
    assert report["summary"]["basket_inventory_count"] == 2
    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["evidence_completeness_status"] == "complete"
    assert aapl["evidence_completeness_score_pct"] == 100
    assert aapl["validation_evidence_status_counts"] == {"sufficient_oos_evidence": 1}
    assert aapl["evidence_counts"]["campaign_lineage_rows"] == 1
    assert aapl["evidence_counts"]["candidate_lineage_rows"] == 1
    assert aapl["evidence_counts"]["oos_trade_count_max"] == 14
    assert aapl["missing_evidence_taxonomy"] == []
    assert aapl["follow_up"] == "eligible_for_readonly_routing"
    asml = rows["ASML"]
    assert "screening_evidence_missing" in asml["missing_evidence_taxonomy"]
    assert "oos_evidence_missing" in asml["missing_evidence_taxonomy"]
    assert asml["evidence_completeness_status"] == "thin"


def test_build_real_basket_evidence_coverage_marks_source_identity_blockers(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": []},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = coverage.build_real_basket_evidence_coverage(
        repo_root=tmp_path,
        max_candidates=5,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    asmi = rows["ASMI"]
    assert "source_identity_blocked" in asmi["missing_evidence_taxonomy"]
    assert asmi["follow_up"] == "require_identity_resolution"
    assert asmi["evidence_presence"]["source_identity_ready"] is False


def test_render_operator_summary_includes_coverage_table(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "no_oos_trades",
                        "oos_trade_count": 0,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {"campaigns": {}},
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": []},
    )

    report = coverage.build_real_basket_evidence_coverage(repo_root=tmp_path, max_candidates=2)
    markdown = coverage.render_operator_summary(report)

    assert "# QRE Real Basket Evidence Coverage" in markdown
    assert "## 2. Evidence completeness counts" in markdown
    assert "## 3. Basket evidence coverage" in markdown
    assert "| AAPL | trend_pullback_continuation_daily_v1 | diagnosable |" in markdown
    assert "no_oos_trades" in markdown


def test_grid_bridge_can_make_clean_sufficient_oos_readiness_visible(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )
    _write_bridge_row(
        tmp_path,
        {
            "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
            "asset": "AAPL",
            "provider_symbol": "AAPL",
            "preset": "trend_pullback_continuation_daily_v1",
            "matched_grid_rows_count": 1,
            "matched_grid_rows": [
                {
                    "run_id": "grid-run-1",
                    "sequence_number": 1,
                    "instrument_symbol": "AAPL",
                    "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                    "status": "completed",
                    "outcome_class": "sufficient_oos_evidence",
                    "criteria_status": "criteria_consistentie_failed",
                }
            ],
            "evidence_exists_in_grid": True,
            "source_identity_status": "provider_symbol_verified",
            "source_identity_blocker": "",
            "metric_consistency_status": "clean_consistent",
            "preset_executability_classification": "executable",
            "candidate_lineage_status": "visible",
            "oos_evidence_status": "sufficient_oos_evidence_present",
            "sufficient_oos_evidence_status": "present",
            "join_key_status": "grid_row_match_found",
            "exact_next_action": "review_criteria_failures",
        },
    )

    report = coverage.build_real_basket_evidence_coverage(repo_root=tmp_path, max_candidates=2)

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["validation_evidence_status_counts"] == {"sufficient_oos_evidence": 1}
    assert aapl["grid_readiness_bridge"]["readiness_bridge_status"] == (
        "bridged_sufficient_oos_but_not_promotion_ready"
    )
    assert report["summary"]["screening_evidence_rows_total"] >= 1
    assert report["summary"]["sufficient_oos_evidence_rows_total"] == 1


def test_grid_bridge_keeps_sufficient_oos_blocked_when_candidate_lineage_missing(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})
    _write_bridge_row(
        tmp_path,
        {
            "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
            "asset": "AAPL",
            "provider_symbol": "AAPL",
            "preset": "trend_pullback_continuation_daily_v1",
            "matched_grid_rows_count": 1,
            "matched_grid_rows": [
                {
                    "run_id": "grid-run-1",
                    "sequence_number": 1,
                    "instrument_symbol": "AAPL",
                    "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                    "status": "completed",
                    "outcome_class": "sufficient_oos_evidence",
                    "criteria_status": "criteria_consistentie_failed",
                }
            ],
            "evidence_exists_in_grid": True,
            "source_identity_status": "provider_symbol_verified",
            "source_identity_blocker": "",
            "metric_consistency_status": "clean_consistent",
            "preset_executability_classification": "executable",
            "candidate_lineage_status": "missing",
            "oos_evidence_status": "sufficient_oos_evidence_present",
            "sufficient_oos_evidence_status": "present",
            "join_key_status": "grid_row_match_found",
            "exact_next_action": "materialize_candidate_lineage",
        },
    )

    report = coverage.build_real_basket_evidence_coverage(repo_root=tmp_path, max_candidates=2)

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["grid_readiness_bridge"]["readiness_bridge_status"] == "blocked_candidate_lineage_missing"
    assert aapl["validation_evidence_status_counts"] == {"grid_oos_evidence_present": 1}
    assert report["summary"]["sufficient_oos_evidence_rows_total"] == 0


def test_write_outputs_writes_only_inside_allowlisted_log_dir(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": []},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = coverage.build_real_basket_evidence_coverage(repo_root=tmp_path, max_candidates=1)
    paths = coverage.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_real_basket_evidence_coverage/latest.json"
    assert paths["operator_summary"] == "logs/qre_real_basket_evidence_coverage/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
