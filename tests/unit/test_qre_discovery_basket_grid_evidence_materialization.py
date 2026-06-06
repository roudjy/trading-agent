from __future__ import annotations

import json
from pathlib import Path

from research import qre_discovery_basket_grid_evidence_materialization as materialization


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _seed_supporting_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "coverage": [
                {"instrument": "AAPL", "timeframe": "1d", "ready": True},
                {"instrument": "ADYEN.AS", "timeframe": "1d", "ready": True},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [
                {"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"},
                {"instrument": "ADYEN.AS", "timeframe": "1d", "quality_status": "ready"},
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
                        "oos_trade_count": 20,
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


def test_fail_closed_when_no_grid_run_artifacts_exist(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["grid_runs_scanned_count"] == 0
    row = next(item for item in report["rows"] if item["asset"] == "AAPL")
    assert row["join_key_status"] == "no_grid_run_found"
    assert row["exact_blocker_category"] == "no_grid_run_found"


def test_matches_grid_row_by_exact_key_and_preserves_no_promotion(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    _write_jsonl(
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-001"
        / "combination_results.v1.jsonl",
        [
            {
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "hypothesis_id": "trend_pullback_behavior_v1",
                "timeframe": "1d",
                "status": "completed",
                "outcome_class": "sufficient_oos_evidence",
                "blocker_class": "criteria_consistentie_failed",
                "criteria_status": "consistentie,win_rate",
                "trades_total": 20,
                "oos_trades": 14,
                "hd_trades": 6,
                "provider_symbol_aliases": [],
                "source_identity_status": "provider_symbol_verified",
                "provider_symbol_status": "verified",
            }
        ],
    )

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    row = next(item for item in report["rows"] if item["asset"] == "AAPL")
    assert row["join_key_status"] == "grid_row_match_found"
    assert row["matched_grid_rows_count"] == 1
    assert row["sufficient_oos_evidence_status"] == "present"
    assert row["exact_blocker_category"] == "criteria_failed"
    assert row["closest_to_routing_sampling_ready"] is True


def test_matches_grid_row_by_provider_alias_and_explains_adapter_gap(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    _write_jsonl(
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-002"
        / "combination_results.v1.jsonl",
        [
                {
                    "sequence_number": 2,
                    "instrument_symbol": "ADYEN.AS",
                    "primary_data_provider_symbol": "ADYEN.AS",
                    "provider_symbol_aliases": ["ADYEN.AS"],
                    "behavior_preset_id": "relative_strength_vs_sector_daily_v1",
                    "hypothesis_id": "relative_strength_sector_behavior_v1",
                    "timeframe": "1d",
                    "status": "completed",
                    "outcome_class": "screening_pass_no_oos",
                "blocker_class": "no_oos_evidence",
                "criteria_status": "",
                "trades_total": 12,
                "oos_trades": 0,
                "hd_trades": 12,
                "source_identity_status": "candidate_alias_only",
                "provider_symbol_status": "candidate_alias_requires_verification",
            }
        ],
    )

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=15,
    )

    row = next(item for item in report["rows"] if item["asset"] == "ADYEN")
    assert row["join_key_status"] == "grid_row_match_found"
    assert row["readiness_adapter_gap"] is True
    assert row["source_identity_blocker"] == "source_identity_blocked"
    assert row["exact_next_action"] == "bridge_grid_evidence_into_readiness_surfaces"


def test_join_mismatch_is_explained(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    _write_jsonl(
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-003"
        / "combination_results.v1.jsonl",
        [
            {
                "sequence_number": 3,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "hypothesis_id": "trend_continuation_behavior_v1",
                "timeframe": "1d",
                "status": "completed",
                "outcome_class": "screening_pass_no_oos",
                "blocker_class": "no_oos_evidence",
                "provider_symbol_aliases": [],
                "source_identity_status": "provider_symbol_verified",
                "provider_symbol_status": "verified",
            }
        ],
    )

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    row = next(item for item in report["rows"] if item["asset"] == "AAPL")
    assert row["join_key_status"] == "join_key_mismatch"
    assert row["exact_blocker_category"] == "join_key_mismatch"


def test_metric_inconsistent_rows_are_not_treated_as_clean_evidence(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    _write_jsonl(
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-004"
        / "combination_results.v1.jsonl",
        [
            {
                "sequence_number": 4,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "hypothesis_id": "trend_pullback_behavior_v1",
                "timeframe": "1d",
                "status": "completed",
                "outcome_class": "sufficient_oos_evidence",
                "blocker_class": "",
                "criteria_status": "",
                "trades_total": 15,
                "oos_trades": 20,
                "hd_trades": 0,
                "provider_symbol_aliases": [],
                "source_identity_status": "provider_symbol_verified",
                "provider_symbol_status": "verified",
            }
        ],
    )

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    row = next(item for item in report["rows"] if item["asset"] == "AAPL")
    assert row["metric_consistency_status"] == "metric_inconsistent"
    assert row["exact_blocker_category"] == "metric_inconsistent"


def test_operator_summary_includes_top_blockers_and_closest_baskets(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    _write_jsonl(
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-005"
        / "combination_results.v1.jsonl",
        [
            {
                "sequence_number": 5,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "hypothesis_id": "trend_pullback_behavior_v1",
                "timeframe": "1d",
                "status": "completed",
                "outcome_class": "sufficient_oos_evidence",
                "blocker_class": "criteria_consistentie_failed",
                "criteria_status": "consistentie",
                "trades_total": 22,
                "oos_trades": 12,
                "hd_trades": 10,
                "provider_symbol_aliases": [],
                "source_identity_status": "provider_symbol_verified",
                "provider_symbol_status": "verified",
            }
        ],
    )

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )
    markdown = materialization.render_operator_summary(report)

    assert "# QRE Discovery Basket Grid Evidence Materialization" in markdown
    assert "## 3. Top blockers" in markdown
    assert "## 5. Closest baskets to readiness" in markdown
    assert "criteria_failed" in markdown
    assert "AAPL" in markdown


def test_malformed_jsonl_fails_closed(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    path = (
        tmp_path
        / "research"
        / "controlled_discovery_grid_runs"
        / "run-006"
        / "combination_results.v1.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json}\n", encoding="utf-8")

    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["grid_runs_scanned_count"] == 1
    row = next(item for item in report["rows"] if item["asset"] == "AAPL")
    assert row["join_key_status"] == "grid_artifact_missing"


def test_write_outputs_writes_only_inside_allowlisted_log_dir(tmp_path: Path) -> None:
    _seed_supporting_artifacts(tmp_path)
    report = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )

    paths = materialization.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_discovery_basket_grid_evidence_materialization/latest.json"
    assert paths["operator_summary"] == "logs/qre_discovery_basket_grid_evidence_materialization/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
