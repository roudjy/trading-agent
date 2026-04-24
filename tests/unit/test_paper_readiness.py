"""v3.15 unit tests: paper_readiness gate."""

from __future__ import annotations

import pytest

from research.candidate_timestamped_returns_feed import (
    TimestampedCandidateReturnsRecord,
)
from research.paper_readiness import (
    BLOCKING_REASONS,
    MIN_PAPER_OOS_DAYS,
    MIN_PAPER_SHARPE_FOR_READY,
    PAPER_READINESS_SCHEMA_VERSION,
    PAPER_READINESS_VERSION,
    PaperReadinessInput,
    READINESS_STATUSES,
    WARNING_REASONS,
    build_paper_readiness_payload,
    compute_readiness,
    compute_readiness_entry,
    summarize_readiness_counts,
)


def _tsr(n_obs: int, *, error: str | None = None, insufficient: bool = False) -> TimestampedCandidateReturnsRecord:
    timestamps = tuple(f"2024-05-{i+1:02d}T00:00:00+00:00" for i in range(n_obs))
    returns = tuple(0.001 for _ in range(n_obs))
    return TimestampedCandidateReturnsRecord(
        candidate_id="cand",
        timestamps=timestamps,
        daily_returns=returns,
        n_obs=n_obs,
        start_date=timestamps[0] if timestamps else None,
        end_date=timestamps[-1] if timestamps else None,
        insufficient_returns=insufficient,
        stream_error=error,
    )


def _divergence_entry(
    *,
    severity: str | None = "low",
    reason_excluded: str | None = None,
) -> dict:
    return {
        "candidate_id": "cand",
        "divergence_severity": severity,
        "reason_excluded": reason_excluded,
    }


def test_happy_path_ready_for_paper_promotion():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=120,
        projected_insufficient_event_count=5,
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=1.5,
    ))
    assert entry.readiness_status == "ready_for_paper_promotion"
    assert entry.blocking_reasons == ()
    assert entry.warnings == ()


def test_insufficient_venue_mapping_blocks():
    # Divergence entry excluded → reason_excluded set
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="unknown",
        sleeve_id=None,
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=10,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(
            severity=None, reason_excluded="insufficient_venue_mapping",
        ),
        paper_sharpe_proxy=0.5,
    ))
    assert "insufficient_venue_mapping" in entry.blocking_reasons
    assert entry.readiness_status == "blocked"


def test_insufficient_oos_days_blocks_when_below_threshold():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS - 1),
        ledger_event_count=50,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=1.0,
    ))
    assert "insufficient_oos_days" in entry.blocking_reasons
    assert entry.readiness_status == "blocked"


def test_missing_execution_events_blocks():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=0,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=1.0,
    ))
    assert "missing_execution_events" in entry.blocking_reasons
    assert entry.readiness_status == "blocked"


def test_excessive_divergence_blocks():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=50,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="high"),
        paper_sharpe_proxy=1.0,
    ))
    assert "excessive_divergence" in entry.blocking_reasons
    assert entry.readiness_status == "blocked"


def test_negative_paper_sharpe_is_warning_by_default_not_blocking():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=50,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=MIN_PAPER_SHARPE_FOR_READY - 0.1,
    ))
    # Warning present, no block → still ready
    assert "negative_paper_sharpe" in entry.warnings
    assert "negative_paper_sharpe" not in entry.blocking_reasons
    assert entry.readiness_status == "ready_for_paper_promotion"


def test_medium_divergence_is_warning_does_not_block():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=50,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="medium"),
        paper_sharpe_proxy=1.0,
    ))
    assert "medium_divergence" in entry.warnings
    assert entry.blocking_reasons == ()
    assert entry.readiness_status == "ready_for_paper_promotion"


def test_malformed_return_stream_blocks():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(0, error="malformed_oos_daily_return_stream", insufficient=True),
        ledger_event_count=50,
        projected_insufficient_event_count=0,
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=1.0,
    ))
    assert "malformed_return_stream" in entry.blocking_reasons


def test_projected_insufficient_events_ratio_warning():
    entry = compute_readiness_entry(PaperReadinessInput(
        candidate_id="c",
        asset_type="crypto",
        sleeve_id="S",
        timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
        ledger_event_count=100,
        projected_insufficient_event_count=30,  # 30% >= 20%
        divergence_entry=_divergence_entry(severity="low"),
        paper_sharpe_proxy=1.0,
    ))
    assert "projected_insufficient_events_ratio_high" in entry.warnings


def test_live_eligible_is_hard_false_in_payload():
    entries = compute_readiness([
        PaperReadinessInput(
            candidate_id="c",
            asset_type="crypto",
            sleeve_id="S",
            timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
            ledger_event_count=50,
            projected_insufficient_event_count=0,
            divergence_entry=_divergence_entry(severity="low"),
            paper_sharpe_proxy=1.0,
        )
    ])
    payload = build_paper_readiness_payload(
        entries=entries,
        generated_at_utc="2026-04-24T10:00:00+00:00",
        run_id="r",
        git_revision="g",
    )
    assert payload["live_eligible"] is False
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["schema_version"] == PAPER_READINESS_SCHEMA_VERSION
    assert payload["paper_readiness_version"] == PAPER_READINESS_VERSION
    # Taxonomies echoed
    assert payload["blocking_reasons_taxonomy"] == list(BLOCKING_REASONS)
    assert payload["warning_reasons_taxonomy"] == list(WARNING_REASONS)
    assert payload["readiness_statuses"] == list(READINESS_STATUSES)


def test_summarize_readiness_counts_aggregates_correctly():
    entries = compute_readiness([
        PaperReadinessInput(
            candidate_id="ready",
            asset_type="crypto",
            sleeve_id="S",
            timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
            ledger_event_count=50,
            projected_insufficient_event_count=0,
            divergence_entry=_divergence_entry(severity="low"),
            paper_sharpe_proxy=1.0,
        ),
        PaperReadinessInput(
            candidate_id="blocked",
            asset_type="unknown",
            sleeve_id=None,
            timestamped_returns=_tsr(10),
            ledger_event_count=5,
            projected_insufficient_event_count=0,
            divergence_entry=_divergence_entry(
                severity=None, reason_excluded="insufficient_venue_mapping"
            ),
            paper_sharpe_proxy=None,
        ),
        PaperReadinessInput(
            candidate_id="thin",
            asset_type="crypto",
            sleeve_id="S",
            timestamped_returns=_tsr(MIN_PAPER_OOS_DAYS + 10),
            ledger_event_count=0,
            projected_insufficient_event_count=0,
            divergence_entry=_divergence_entry(severity="low"),
            paper_sharpe_proxy=1.0,
        ),
    ])
    # ready, blocked, blocked (thin has missing_execution_events)
    counts = summarize_readiness_counts(entries)
    assert counts["ready_for_paper_promotion"] == 1
    assert counts["blocked"] == 2
    assert counts["insufficient_evidence"] == 0
