from __future__ import annotations

from datetime import UTC, datetime

from research.campaigns import (
    build_campaign_id,
    build_run_campaign_payload,
    build_run_campaign_progress_payload,
    resolve_campaign_status,
)


def _batch(status: str, **overrides) -> dict:
    payload = {
        "batch_id": "batch-1",
        "batch_index": 1,
        "strategy_family": "breakout",
        "interval": "1d",
        "status": status,
        "started_at": "2026-04-15T10:00:00+00:00",
        "finished_at": None,
        "elapsed_seconds": 60,
        "candidate_count": 3,
        "completed_candidate_count": 1,
        "promoted_candidate_count": 1,
        "validated_candidate_count": 0,
        "screening_rejected_count": 1,
        "timed_out_count": 0,
        "errored_count": 0,
        "validation_error_count": 0,
        "reason_code": None,
        "reason_detail": None,
    }
    payload.update(overrides)
    return payload


def test_campaign_status_rollup_stays_minimal_and_explicit():
    assert resolve_campaign_status(batches=[]) == "pending"
    assert resolve_campaign_status(batches=[_batch("pending")]) == "pending"
    assert resolve_campaign_status(batches=[_batch("completed"), _batch("pending", batch_id="batch-2", batch_index=2)]) == "running"
    assert resolve_campaign_status(batches=[_batch("completed"), _batch("completed", batch_id="batch-2", batch_index=2)]) == "completed"
    assert resolve_campaign_status(batches=[_batch("partial"), _batch("completed", batch_id="batch-2", batch_index=2)]) == "partial"
    assert resolve_campaign_status(batches=[_batch("failed"), _batch("skipped", batch_id="batch-2", batch_index=2)]) == "failed"


def test_campaign_payload_aggregates_existing_candidate_summaries():
    generated_at = datetime(2026, 4, 15, 10, 5, 0, tzinfo=UTC)
    batches = [
        _batch("partial", timed_out_count=1, finished_at="2026-04-15T10:04:00+00:00"),
        _batch(
            "completed",
            batch_id="batch-2",
            batch_index=2,
            strategy_family="trend_following",
            interval="4h",
            candidate_count=2,
            completed_candidate_count=2,
            promoted_candidate_count=1,
            validated_candidate_count=1,
            screening_rejected_count=1,
            elapsed_seconds=120,
            finished_at="2026-04-15T10:05:00+00:00",
        ),
    ]
    candidate_payload = {
        "summary": {
            "validation_candidate_count": 2,
            "validated_count": 1,
            "screening_rejected_count": 2,
        }
    }
    screening_payload = {
        "summary": {
            "rejected_count": 2,
            "timed_out_count": 1,
            "errored_count": 0,
            "skipped_count": 0,
        }
    }

    latest = build_run_campaign_payload(
        campaign_id=build_campaign_id(run_id="run-1"),
        run_id="run-1",
        generated_at_utc=generated_at,
        started_at="2026-04-15T10:00:00+00:00",
        finished_at=None,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
        source_artifacts={
            "run_batches_path": "research/run_batches_latest.v1.json",
            "run_candidates_path": "research/run_candidates_latest.v1.json",
            "run_screening_candidates_path": "research/run_screening_candidates_latest.v1.json",
        },
    )
    progress = build_run_campaign_progress_payload(
        campaign_id=build_campaign_id(run_id="run-1"),
        run_id="run-1",
        generated_at_utc=generated_at,
        started_at="2026-04-15T10:00:00+00:00",
        finished_at=None,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
    )

    assert latest["status"] == "partial"
    assert latest["finished_at"] == "2026-04-15T10:05:00+00:00"
    assert latest["summary"]["batch_count"] == 2
    assert latest["summary"]["partial_batch_count"] == 1
    assert latest["summary"]["completed_batch_count"] == 1
    assert latest["summary"]["total_candidate_count"] == 5
    assert latest["summary"]["promoted_candidate_count"] == 2
    assert latest["summary"]["rejected_candidate_count"] == 3
    assert latest["summary"]["validated_candidate_count"] == 1
    assert latest["lineage"]["source_artifacts"]["run_batches_path"] == "research/run_batches_latest.v1.json"
    assert progress["active_batch"] is None
    assert progress["summary"]["timed_out_candidate_count"] == 1
