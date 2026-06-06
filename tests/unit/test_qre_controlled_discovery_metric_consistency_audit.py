from __future__ import annotations

import json
from pathlib import Path

from research import qre_controlled_discovery_metric_consistency_audit as audit
from research import qre_discovery_basket_grid_evidence_materialization as materialization


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _seed_grid_rows(tmp_path: Path, rows: list[dict]) -> None:
    _write_jsonl(
        tmp_path / "research" / "controlled_discovery_grid_runs" / "run-001" / "combination_results.v1.jsonl",
        rows,
    )


def _seed_materialization_support(tmp_path: Path) -> None:
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
        {"candidates": []},
    )
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})


def test_oos_trades_greater_than_total_is_inconsistent(tmp_path: Path) -> None:
    _seed_grid_rows(
        tmp_path,
        [
            {
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 15,
                "oos_trades": 20,
                "hd_trades": 0,
            }
        ],
    )

    report = audit.build_metric_consistency_audit(repo_root=tmp_path)

    row = report["rows"][0]
    assert row["classification"] == "inconsistent_oos_gt_total"
    assert row["no_alpha_interpretation"] is True


def test_missing_and_non_numeric_metrics_are_classified(tmp_path: Path) -> None:
    _seed_grid_rows(
        tmp_path,
        [
            {
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": "",
                "oos_trades": 10,
            },
            {
                "sequence_number": 2,
                "instrument_symbol": "MSFT",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": "abc",
                "oos_trades": 5,
            },
        ],
    )

    report = audit.build_metric_consistency_audit(repo_root=tmp_path)

    classifications = {row["instrument_symbol"]: row["classification"] for row in report["rows"]}
    assert classifications["AAPL"] == "missing_total_trades"
    assert classifications["MSFT"] == "non_numeric_metric"


def test_clean_consistent_and_aggregation_scope_mismatch_are_distinct(tmp_path: Path) -> None:
    _seed_grid_rows(
        tmp_path,
        [
            {
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 20,
                "oos_trades": 10,
                "hd_trades": 10,
            },
            {
                "sequence_number": 2,
                "instrument_symbol": "MSFT",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 10,
                "oos_trades": 12,
                "hd_trades": 0,
                "aggregation_scope_hint": "aggregation_scope_mismatch",
            },
        ],
    )

    report = audit.build_metric_consistency_audit(repo_root=tmp_path)

    classifications = {row["instrument_symbol"]: row["classification"] for row in report["rows"]}
    assert classifications["AAPL"] == "clean_consistent"
    assert classifications["MSFT"] == "aggregation_scope_mismatch"


def test_deterministic_output_ordering_and_write_outputs(tmp_path: Path) -> None:
    _seed_grid_rows(
        tmp_path,
        [
            {"sequence_number": 2, "instrument_symbol": "MSFT", "behavior_preset_id": "trend_continuation_daily_v1"},
            {"sequence_number": 1, "instrument_symbol": "AAPL", "behavior_preset_id": "trend_continuation_daily_v1", "trades_total": 10, "oos_trades": 12},
        ],
    )

    report = audit.build_metric_consistency_audit(repo_root=tmp_path)
    assert [row["instrument_symbol"] for row in report["rows"]] == ["AAPL", "MSFT"]

    paths = audit.write_outputs(report, repo_root=tmp_path)
    assert paths["latest"] == "logs/qre_controlled_discovery_metric_consistency_audit/latest.json"
    assert (tmp_path / paths["latest"]).is_file()


def test_materialization_consumes_metric_audit_and_marks_row_not_clean(tmp_path: Path) -> None:
    _seed_materialization_support(tmp_path)
    _seed_grid_rows(
        tmp_path,
        [
            {
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "hypothesis_id": "trend_pullback_behavior_v1",
                "timeframe": "1d",
                "status": "completed",
                "outcome_class": "sufficient_oos_evidence",
                "trades_total": 15,
                "oos_trades": 20,
                "hd_trades": 0,
            }
        ],
    )
    report = audit.build_metric_consistency_audit(repo_root=tmp_path)
    audit.write_outputs(report, repo_root=tmp_path)

    materialized = materialization.build_discovery_basket_grid_evidence_materialization(
        repo_root=tmp_path,
        max_candidates=2,
    )
    row = next(item for item in materialized["rows"] if item["asset"] == "AAPL")
    assert row["metric_consistency_status"] == "inconsistent_oos_gt_total"
    assert row["exact_blocker_category"] == "metric_inconsistent"
