from __future__ import annotations

import json
from pathlib import Path

from research import qre_routing_readiness_from_basket as routing


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_routing_readiness_marks_complete_basket_as_ready(tmp_path: Path) -> None:
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
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
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

    report = routing.build_routing_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["routing_readiness_state"] == "ready"
    assert aapl["routing_ready"] is True
    assert aapl["primary_reason_code"] == "evidence_ready_for_readonly_routing"
    assert aapl["routing_readiness_score_pct"] == 100


def test_build_routing_readiness_blocks_source_identity_issues(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = routing.build_routing_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=5,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    asmi = rows["ASMI"]
    assert asmi["routing_readiness_state"] == "blocked"
    assert asmi["primary_reason_code"] == "source_identity_blocked"
    assert asmi["routing_ready"] is False


def test_build_routing_readiness_keeps_zero_ready_evidence_backed(tmp_path: Path) -> None:
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
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = routing.build_routing_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["summary"]["routing_ready_count"] == 0
    assert report["summary"]["evidence_backed_zero_ready"] is True
    assert report["summary"]["final_recommendation"] == "nothing_ready_evidence_backed"


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = routing.build_routing_readiness_from_basket(repo_root=tmp_path, max_candidates=1)
    markdown = routing.render_operator_summary(report)
    paths = routing.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Routing Readiness From Basket Evidence" in markdown
    assert "## 2. Routing readiness counts" in markdown
    assert paths["latest"] == "logs/qre_routing_readiness_from_basket/latest.json"
    assert paths["operator_summary"] == "logs/qre_routing_readiness_from_basket/operator_summary.md"


def test_grid_bridge_visible_oos_without_lineage_keeps_routing_deferred(tmp_path: Path) -> None:
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
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "rows": [
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
                }
            ]
        },
    )

    report = routing.build_routing_readiness_from_basket(repo_root=tmp_path, max_candidates=2)

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["routing_readiness_state"] == "deferred"
    assert aapl["primary_reason_code"] == "lineage_missing"
