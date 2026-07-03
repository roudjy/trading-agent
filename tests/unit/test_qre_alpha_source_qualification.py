from __future__ import annotations

from packages.qre_research.alpha_discovery.contracts import DatasetSnapshot
from packages.qre_research.alpha_discovery.snapshot_lineage import append_snapshot_row
from packages.qre_research.alpha_discovery.source_qualification import (
    SOURCE_BLOCKED,
    SOURCE_SCREENING_ELIGIBLE,
    qualify_datasets,
    reconcile_source_policy,
)


def test_manual_research_only_source_stays_blocked_even_with_ready_snapshot(tmp_path) -> None:
    catalog = {
        "datasets": [
            {
                "dataset_id": "qds_fixture",
                "dataset_fingerprint": "sha256:test",
                "source_id": "yfinance",
                "instrument_ids": ["AAPL"],
                "timeframe": "1d",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "quality_summary": {"effective_research_quality_status": "ready"},
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 10,
                    "unique_bar_count": 8,
                    "expected_bar_count": 8,
                    "coverage_ratio": 1.0,
                    "exact_duplicate_row_count": 2,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                    "impossible_bar_density": False,
                },
                "corporate_action_summary": {"status": "UNKNOWN"},
            }
        ]
    }
    policy = reconcile_source_policy(repo_root=tmp_path, dataset_catalog=catalog)
    qualifications = qualify_datasets(dataset_catalog=catalog, policy_reconciliation=policy)
    row = qualifications["rows"][0]

    assert policy["exact_cause"] in {"MANUAL_RESEARCH_ONLY_BY_DESIGN", "GLOBAL_VERSUS_CAMPAIGN_SCOPE"}
    assert row["allowed_evidence_tier"] == SOURCE_BLOCKED
    assert "global_policy_ceiling_manual_research_only" in row["reason_codes"]


def test_missing_screening_metrics_fail_closed(tmp_path) -> None:
    catalog = {
        "datasets": [
            {
                "dataset_id": "qds_fixture",
                "dataset_snapshot_id": "qds_fixture",
                "dataset_fingerprint": "sha256:test",
                "source_id": "yfinance",
                "instrument_ids": ["AAPL"],
                "timeframe": "1d",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "quality_summary": {"effective_research_quality_status": "ready"},
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 25,
                    "unique_bar_count": 25,
                    "expected_bar_count": None,
                    "coverage_ratio": None,
                    "exact_duplicate_row_count": 0,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                },
                "corporate_action_summary": {"status": "UNKNOWN"},
            }
        ]
    }
    policy = {"current_yfinance_status": "manual_research_only", "content_identity": "policy-fixture", "policy_version": "policy-fixture"}
    qualifications = qualify_datasets(dataset_catalog=catalog, policy_reconciliation=policy)
    row = qualifications["rows"][0]

    assert row["allowed_evidence_tier"] == SOURCE_BLOCKED
    assert row["qualification_status"] == "BLOCKED"
    assert row["coverage_ratio"] is None
    assert "qualification_metric_missing:expected_bar_count" in row["reason_codes"]
    assert "qualification_metric_missing:coverage_ratio" in row["reason_codes"]
    assert "insufficient_unique_history" in row["reason_codes"]


def test_complete_snapshot_can_be_screening_eligible(tmp_path) -> None:
    repo_root = tmp_path
    snapshot = DatasetSnapshot(
        dataset_snapshot_id="snap-screening",
        logical_dataset_family_id="yfinance|AAPL|1d",
        acquisition_batch_ids=("batch-1",),
        parent_snapshot_id=None,
        instrument_ids=("AAPL",),
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
        fingerprint="sha256:screening",
        source_id="yfinance",
        source_policy_version="policy-v1",
        qualification_status="COHERENT",
        immutable=True,
        created_at_utc="2026-07-03T00:00:00Z",
        partition_refs=("data/cache/market/yfinance__AAPL__1d__20260101__20260401__abcd.parquet",),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity="content-screening",
    )
    append_snapshot_row(repo_root, snapshot)
    catalog = {
        "datasets": [
            {
                "dataset_id": "yfinance|AAPL|1d",
                "dataset_snapshot_id": "snap-screening",
                "dataset_fingerprint": "sha256:screening",
                "source_id": "yfinance",
                "instrument_ids": ["AAPL"],
                "timeframe": "1d",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-04-01T00:00:00Z",
                "quality_summary": {
                    "effective_research_quality_status": "ready",
                    "minimum_required_history": "90d",
                    "minimum_required_rows": 90,
                },
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 120,
                    "unique_bar_count": 120,
                    "expected_bar_count": 120,
                    "coverage_ratio": 1.0,
                    "exact_duplicate_row_count": 0,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                    "activity_estimate": 4,
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
    policy = {"current_yfinance_status": "manual_research_only", "content_identity": "policy-fixture", "policy_version": "policy-fixture"}
    qualifications = qualify_datasets(repo_root=repo_root, dataset_catalog=catalog, policy_reconciliation=policy)
    row = qualifications["rows"][0]

    assert row["allowed_evidence_tier"] == SOURCE_SCREENING_ELIGIBLE
    assert row["qualification_status"] == "COHERENT"
    assert row["coverage_ratio"] == 1.0
    assert not row["reason_codes"]


def test_qualification_summary_counts_blocked_replay_and_logical_datasets(tmp_path) -> None:
    catalog = {
        "datasets": [
            {
                "dataset_id": "family-1",
                "dataset_snapshot_id": "snapshot-1",
                "dataset_fingerprint": "sha256:one",
                "source_id": "yfinance",
                "instrument_ids": ["AAPL"],
                "timeframe": "1d",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "quality_summary": {"effective_research_quality_status": "ready"},
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 10,
                    "unique_bar_count": 10,
                    "expected_bar_count": None,
                    "coverage_ratio": 1.0,
                    "exact_duplicate_row_count": 0,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                },
                "corporate_action_summary": {"status": "UNKNOWN"},
            },
            {
                "dataset_id": "family-2",
                "dataset_snapshot_id": "snapshot-2",
                "dataset_fingerprint": "sha256:two",
                "source_id": "yfinance",
                "instrument_ids": ["BTC-USD"],
                "timeframe": "1h",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "quality_summary": {"effective_research_quality_status": "ready"},
                "identity_summary": {"instrument_identity_status": "ready"},
                "integrity_summary": {
                    "raw_row_count": 20,
                    "unique_bar_count": 20,
                    "expected_bar_count": 20,
                    "coverage_ratio": 1.0,
                    "exact_duplicate_row_count": 0,
                    "conflicting_row_count": 0,
                    "invalid_row_count": 0,
                },
                "corporate_action_summary": {"status": "UNKNOWN"},
            },
        ]
    }
    policy = {"current_yfinance_status": "manual_research_only", "content_identity": "policy-fixture", "policy_version": "policy-fixture"}
    qualifications = qualify_datasets(dataset_catalog=catalog, policy_reconciliation=policy)

    summary = qualifications["summary"]
    assert summary["qualification_row_count"] == 2
    assert summary["physical_snapshot_count"] == 2
    assert summary["logical_dataset_count"] == 2
    assert summary["replayed_snapshot_count"] == 2
    assert summary["historical_or_superseded_count"] == 2
    assert summary["blocked_count"] == 2
    assert summary["screening_eligible_count"] == 0
    assert summary["missing_expected_bar_count"] == 1
    assert summary["missing_coverage_count"] == 1
