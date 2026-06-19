from __future__ import annotations

import json
from pathlib import Path

from research import qre_local_bounded_oos_source_inventory as inventory


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _materialized_payload(*, trade_count: int) -> dict[str, object]:
    return {
        "report_kind": "qre_controlled_validation_adapter_result_materialization",
        "request_ref": "req-001",
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "lineage_candidates": [
            {
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                "generation_id": "gen-001",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "request_id": "req-001",
                "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
                "timeframe": "daily_v1",
            }
        ],
        "oos_candidates": [
            {
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                "cost_slippage_assumption_refs": [
                    "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json#cost:AAA"
                ],
                "oos_metric_fields": {"oos_trade_count": trade_count},
                "oos_window": {"start": "2026-01-01", "end": "2026-01-31"},
                "preset_id": "trend_pullback_continuation_daily_v1",
                "request_id": "req-001",
                "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
                "timeframe": "daily_v1",
            }
        ],
    }


def _structured_source_payload(*, trade_count: int) -> dict[str, object]:
    return {
        "report_kind": "qre_bounded_local_cache_controlled_validation_source",
        "source_authority": "structured_source",
        "source_type": "structured_controlled_validation",
        "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
        "lineage_records": [
            {
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                "generation_run_id": "gen-001",
                "reason_record_refs": ["reason-lineage"],
                "validation_status": "accepted",
            }
        ],
        "oos_records": [
            {
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                "cost_slippage_assumption_refs": ["cost-001"],
                "oos_metric_fields": {"oos_trade_count": trade_count},
                "oos_window": {"start": "2026-01-01", "end": "2026-01-31"},
                "reason_record_refs": ["reason-oos"],
                "validation_status": "accepted",
            }
        ],
    }


def _queue_payload(*, symbol: str = "AAA") -> dict[str, object]:
    return {
        "report_kind": "qre_basket_next_action_queue",
        "rows": [
            {
                "candidate_id": f"seed::trend_pullback_continuation_daily_v1::{symbol}",
                "symbol": symbol,
                "preset_id": "trend_pullback_continuation_daily_v1",
            }
        ],
    }


def test_positive_local_structured_source_classified_correctly(tmp_path: Path) -> None:
    _write_json(tmp_path / inventory.ADAPTER_RESULT_PATH, _materialized_payload(trade_count=3))
    _write_json(
        tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-001.v1.json",
        _structured_source_payload(trade_count=3),
    )

    report = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    row = report["inventory_rows"][0]
    assert row["classification"] == "eligible_existing_structured_oos_source"
    assert row["approval_eligibility"] is True
    assert report["inventory_result"] == "ELIGIBLE_EXISTING_SOURCE_FOUND"


def test_zero_trade_source_is_blocked(tmp_path: Path) -> None:
    _write_json(tmp_path / inventory.ADAPTER_RESULT_PATH, _materialized_payload(trade_count=0))
    _write_json(
        tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-001.v1.json",
        _structured_source_payload(trade_count=0),
    )

    report = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    row = report["inventory_rows"][0]
    assert row["classification"] == "blocked_non_positive_oos_trade_count"
    assert row["rejection_reasons"] == ["non_positive_oos_trade_count"]


def test_generated_report_is_blocked(tmp_path: Path) -> None:
    _write_json(
        tmp_path / inventory.CONTROLLED_EXECUTION_REPORT_PATH,
        {"report_kind": "qre_controlled_validation_execution", "stdout_tail": ["report only"]},
    )

    report = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    row = report["inventory_rows"][0]
    assert row["classification"] == "blocked_generated_report_only"


def test_fixture_context_stdout_and_legacy_sources_are_blocked() -> None:
    assert inventory._existing_source_row(
        repo_root=Path("."),
        path=Path("tests/fixtures/source.json"),
        payload={"report_kind": "qre_fixture", "source_ref": "tests/fixtures/source.json"},
        materialized_details={},
    )["classification"] == "blocked_fixture_only"
    assert inventory._existing_source_row(
        repo_root=Path("."),
        path=Path("logs/context/source.json"),
        payload={"source_authority": "context_only", "source_type": "context_only"},
        materialized_details={},
    )["classification"] == "blocked_context_only"
    assert inventory._existing_source_row(
        repo_root=Path("."),
        path=Path("logs/stdout/source.json"),
        payload={"source_type": "stdout_only"},
        materialized_details={},
    )["classification"] == "blocked_stdout_only"
    assert inventory._existing_source_row(
        repo_root=Path("."),
        path=Path("logs/legacy_alias/source.json"),
        payload={"source_type": "legacy_alias_only"},
        materialized_details={},
    )["classification"] == "blocked_legacy_alias"


def test_missing_metadata_reasons_are_explicit(tmp_path: Path) -> None:
    _write_json(tmp_path / inventory.ADAPTER_RESULT_PATH, _materialized_payload(trade_count=3))
    _write_json(
        tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-001.v1.json",
        {
            "report_kind": "qre_bounded_local_cache_controlled_validation_source",
            "source_authority": "structured_source",
            "source_type": "structured_controlled_validation",
            "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
            "lineage_records": [{"candidate_id": "", "validation_status": ""}],
            "oos_records": [{"candidate_id": "", "oos_window": {}, "oos_metric_fields": {}, "validation_status": ""}],
        },
    )

    report = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    row = report["inventory_rows"][0]
    assert row["classification"] == "blocked_missing_lineage_metadata"
    assert "missing_candidate_id" in row["rejection_reasons"]


def test_ranking_does_not_use_profitability_fields(tmp_path: Path) -> None:
    positive = _structured_source_payload(trade_count=2)
    positive["oos_records"][0]["oos_metric_fields"]["oos_return_pct"] = -10.0  # type: ignore[index]
    negative = _structured_source_payload(trade_count=1)
    negative["source_ref"] = "logs/qre_controlled_validation_adapter_results/source_artifacts/source-002.v1.json"
    negative["lineage_records"][0]["candidate_id"] = "seed::trend_pullback_continuation_daily_v1::BBB"  # type: ignore[index]
    negative["lineage_records"][0]["generation_run_id"] = "gen-002"  # type: ignore[index]
    negative["oos_records"][0]["candidate_id"] = "seed::trend_pullback_continuation_daily_v1::BBB"  # type: ignore[index]
    negative["oos_records"][0]["cost_slippage_assumption_refs"] = ["cost-002"]  # type: ignore[index]
    negative["oos_records"][0]["oos_metric_fields"] = {"oos_trade_count": 1, "oos_return_pct": 99.0}  # type: ignore[index]
    _write_json(
        tmp_path / inventory.ADAPTER_RESULT_PATH,
        {
            "report_kind": "qre_controlled_validation_adapter_result_materialization",
            "preset_id": "trend_pullback_continuation_daily_v1",
            "request_ref": "req-001",
            "timeframe": "daily_v1",
            "lineage_candidates": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                    "generation_id": "gen-001",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "request_id": "req-001",
                    "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
                    "timeframe": "daily_v1",
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::BBB",
                    "generation_id": "gen-002",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "request_id": "req-001",
                    "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-002.v1.json",
                    "timeframe": "daily_v1",
                },
            ],
            "oos_candidates": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAA",
                    "cost_slippage_assumption_refs": ["cost-001"],
                    "oos_metric_fields": {"oos_trade_count": 2},
                    "oos_window": {"start": "2026-01-01", "end": "2026-01-31"},
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "request_id": "req-001",
                    "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-001.v1.json",
                    "timeframe": "daily_v1",
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::BBB",
                    "cost_slippage_assumption_refs": ["cost-002"],
                    "oos_metric_fields": {"oos_trade_count": 1},
                    "oos_window": {"start": "2026-01-01", "end": "2026-01-31"},
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "request_id": "req-001",
                    "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/source-002.v1.json",
                    "timeframe": "daily_v1",
                },
            ],
        },
    )
    _write_json(tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-001.v1.json", positive)
    _write_json(tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-002.v1.json", negative)

    report = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    assert report["profitability_fields_used"] == []
    assert report["selection_ranking_fields"] == list(inventory.NON_PERFORMANCE_FIELDS)


def test_deterministic_result(tmp_path: Path) -> None:
    _write_json(tmp_path / inventory.ADAPTER_RESULT_PATH, _materialized_payload(trade_count=0))
    _write_json(
        tmp_path / inventory.SOURCE_ARTIFACT_DIR / "source-001.v1.json",
        _structured_source_payload(trade_count=0),
    )
    _write_json(tmp_path / inventory.NEXT_ACTION_QUEUE_PATH, _queue_payload())

    first = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)
    second = inventory.build_local_bounded_oos_source_inventory(repo_root=tmp_path)

    assert first == second
    assert first["hash"] == inventory.compute_inventory_hash(first)


def test_no_symbol_specific_core_behavior() -> None:
    source = Path("research/qre_local_bounded_oos_source_inventory.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
