from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research.alpha_discovery.contracts import (
    SOURCE_TIER_SCREENING_ELIGIBLE,
    DataRequirement,
    DatasetSnapshot,
)
from packages.qre_research.alpha_discovery.snapshot_lineage import append_snapshot_row
from packages.qre_research.alpha_discovery.source_qualification import (
    qualify_datasets,
    reconcile_source_policy,
)
from packages.qre_research.alpha_discovery.source_resolution import resolve_source


def _requirement() -> DataRequirement:
    return DataRequirement(
        requirement_id="req-1",
        experiment_id="exp-1",
        universe_plan_id="uni-1",
        universe_selector="single_asset",
        resolved_instrument_ids=("ETH-EUR",),
        instrument_requirements=("ETH-EUR",),
        timeframe="1d",
        base_timeframe="1d",
        required_timeframes=("1d",),
        required_fields=("open", "high", "low", "close", "volume"),
        required_history_start="2026-01-01T00:00:00Z",
        required_history_end="2026-07-01T00:00:00Z",
        required_history_span="90d",
        minimum_rows=90,
        minimum_rows_per_asset=90,
        minimum_assets=1,
        target_assets=1,
        minimum_common_history="90d",
        requested_execution_tier="EMPIRICAL_SCREENING",
        minimum_history_span="90d",
        minimum_expected_signals=3,
        minimum_expected_trades=3,
        minimum_validation_rows=20,
        minimum_locked_oos_rows=20,
        minimum_locked_oos_activity=2,
        validation_requirement="validation",
        locked_oos_requirement="locked_oos",
        embargo_requirement="embargo",
        warmup_requirement="warmup",
        required_source_quality="quality_gated",
        required_identity_status="resolved",
        required_cost_model="canonical_costs",
        required_slippage_model="canonical_slippage",
        point_in_time_requirement="not_required",
        corporate_action_requirement="not_required",
        session_calendar_requirement="not_required",
        PIT_requirement="PIT_NOT_REQUIRED",
        cost_data_requirement="canonical_costs",
        slippage_data_requirement="canonical_slippage",
        regime_context_requirement="regime",
        quality_policy="ready_only",
        identity_policy="resolved_only",
        preferred_sources=("market_repository",),
        content_identity="req-content",
    )


def test_snapshot_append_enables_screening_resolution(tmp_path: Path) -> None:
    repo_root = tmp_path
    snapshot = DatasetSnapshot(
        dataset_snapshot_id="snap-1",
        logical_dataset_family_id="yfinance|ETH-EUR|1d",
        acquisition_batch_ids=("batch-1",),
        parent_snapshot_id=None,
        instrument_ids=("ETH-EUR",),
        timeframe="1d",
        start="2026-01-01T00:00:00Z",
        end="2026-07-01T00:00:00Z",
        unique_bar_count=180,
        raw_row_count=180,
        exact_duplicate_row_count=0,
        overlapping_row_count=0,
        conflicting_row_count=0,
        invalid_row_count=0,
        expected_bar_count=None,
        coverage_ratio=1.0,
        fingerprint="fp-1",
        source_id="yfinance",
        source_policy_version="policy-v1",
        qualification_status="COHERENT",
        immutable=True,
        created_at_utc="2026-07-03T00:00:00Z",
        partition_refs=("data/cache/market/yfinance__ETH-EUR__1d__20260101__20260701__abcd.parquet",),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity="content-1",
    )
    append_snapshot_row(repo_root, snapshot)
    resolution = resolve_source(repo_root=repo_root, requirement=_requirement(), target_source_tier=SOURCE_TIER_SCREENING_ELIGIBLE)
    assert resolution.selected_snapshot == "snap-1"
    assert resolution.current_source_tier == SOURCE_TIER_SCREENING_ELIGIBLE
    assert resolution.operator_action_required is False


def test_append_snapshot_persists_latest_artifact(tmp_path: Path) -> None:
    repo_root = tmp_path
    snapshot = DatasetSnapshot(
        dataset_snapshot_id="snap-2",
        logical_dataset_family_id="yfinance|BTC-USD|1h",
        acquisition_batch_ids=("batch-2",),
        parent_snapshot_id=None,
        instrument_ids=("BTC-USD",),
        timeframe="1h",
        start="2026-01-01T00:00:00Z",
        end="2026-07-01T00:00:00Z",
        unique_bar_count=1000,
        raw_row_count=1000,
        exact_duplicate_row_count=0,
        overlapping_row_count=0,
        conflicting_row_count=0,
        invalid_row_count=0,
        expected_bar_count=None,
        coverage_ratio=1.0,
        fingerprint="fp-2",
        source_id="yfinance",
        source_policy_version="policy-v1",
        qualification_status="COHERENT",
        immutable=True,
        created_at_utc="2026-07-03T00:00:00Z",
        partition_refs=("data/cache/market/yfinance__BTC-USD__1h__20260101__20260701__efgh.parquet",),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity="content-2",
    )
    append_snapshot_row(repo_root, snapshot)
    payload = json.loads((repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").read_text(encoding="utf-8"))
    assert payload["rows"][0]["dataset_snapshot_id"] == "snap-2"


def test_source_resolution_ignores_stale_unqualified_lineage_updates(tmp_path: Path) -> None:
    repo_root = tmp_path
    snapshot_v1 = DatasetSnapshot(
        dataset_snapshot_id="snap-v1",
        logical_dataset_family_id="yfinance|ETH-EUR|1d",
        acquisition_batch_ids=("batch-1",),
        parent_snapshot_id=None,
        instrument_ids=("ETH-EUR",),
        timeframe="1d",
        start="2026-01-01T00:00:00Z",
        end="2026-04-01T00:00:00Z",
        unique_bar_count=120,
        raw_row_count=120,
        exact_duplicate_row_count=0,
        overlapping_row_count=0,
        conflicting_row_count=0,
        invalid_row_count=0,
        expected_bar_count=120,
        coverage_ratio=1.0,
        fingerprint="fp-v1",
        source_id="yfinance",
        source_policy_version="policy-v1",
        qualification_status="COHERENT",
        immutable=True,
        created_at_utc="2026-07-03T00:00:00Z",
        partition_refs=("data/cache/market/yfinance__ETH-EUR__1d__20260101__20260401__v1.parquet",),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity="content-v1",
    )
    append_snapshot_row(repo_root, snapshot_v1)
    catalog = {
        "datasets": [
            {
                "dataset_id": "yfinance|ETH-EUR|1d",
                "dataset_snapshot_id": "snap-v1",
                "dataset_fingerprint": "fp-v1",
                "source_id": "yfinance",
                "instrument_ids": ["ETH-EUR"],
                "timeframe": "1d",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-04-01T00:00:00Z",
                "quality_summary": {"effective_research_quality_status": "ready"},
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 120,
                    "unique_bar_count": 120,
                    "expected_bar_count": 120,
                    "coverage_ratio": 1.0,
                    "exact_duplicate_row_count": 0,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                },
                "adjustment_policy": "explicit",
                "timezone_policy": "UTC_NORMALIZED",
                "session_policy": "canonical_session_calendar",
                "history_span": "90d",
                "validation_capacity": 1,
                "activity_estimate": 4,
                "source_policy_version": "policy-v1",
                "qualification_policy_version": "policy-v1",
            }
        ]
    }
    policy = reconcile_source_policy(repo_root=repo_root, dataset_catalog=catalog)
    qualification_payload = qualify_datasets(repo_root=repo_root, dataset_catalog=catalog, policy_reconciliation=policy)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps(qualification_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    resolution_v1 = resolve_source(repo_root=repo_root, requirement=_requirement(), target_source_tier=SOURCE_TIER_SCREENING_ELIGIBLE)
    assert resolution_v1.selected_snapshot == "snap-v1"

    snapshot_v2 = DatasetSnapshot(
        dataset_snapshot_id="snap-v2",
        logical_dataset_family_id="yfinance|ETH-EUR|1d",
        acquisition_batch_ids=("batch-2",),
        parent_snapshot_id="snap-v1",
        instrument_ids=("ETH-EUR",),
        timeframe="1d",
        start="2026-04-02T00:00:00Z",
        end="2026-07-01T00:00:00Z",
        unique_bar_count=120,
        raw_row_count=120,
        exact_duplicate_row_count=0,
        overlapping_row_count=0,
        conflicting_row_count=0,
        invalid_row_count=0,
        expected_bar_count=120,
        coverage_ratio=1.0,
        fingerprint="fp-v2",
        source_id="yfinance",
        source_policy_version="policy-v1",
        qualification_status="COHERENT",
        immutable=True,
        created_at_utc="2026-07-03T00:00:00Z",
        partition_refs=("data/cache/market/yfinance__ETH-EUR__1d__20260402__20260701__v2.parquet",),
        compatibility_status="COMPATIBLE_APPEND",
        lineage_depth=1,
        content_identity="content-v2",
    )
    append_snapshot_row(repo_root, snapshot_v2)

    resolution_v2 = resolve_source(repo_root=repo_root, requirement=_requirement(), target_source_tier=SOURCE_TIER_SCREENING_ELIGIBLE)

    assert resolution_v2.selected_snapshot == "snap-v1"
    assert resolution_v2.selected_snapshot != "snap-v2"
    assert "SOURCE_RESOLUTION_STALE" not in resolution_v2.unresolved_blockers
