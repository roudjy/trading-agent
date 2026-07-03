from __future__ import annotations

from packages.qre_research.alpha_discovery.source_qualification import (
    SOURCE_BLOCKED,
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

