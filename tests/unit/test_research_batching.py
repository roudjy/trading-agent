from __future__ import annotations

from datetime import UTC, datetime

from research.batching import (
    build_batch_manifest_payload,
    build_run_batches_payload,
    partition_execution_batches,
)


def _candidate(candidate_id: str, *, strategy_name: str, strategy_family: str, asset: str, interval: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "strategy_name": strategy_name,
        "strategy_family": strategy_family,
        "asset": asset,
        "interval": interval,
    }


def test_partition_execution_batches_is_deterministic():
    candidates = [
        _candidate("c3", strategy_name="gamma", strategy_family="trend_following", asset="ETH-USD", interval="4h"),
        _candidate("c1", strategy_name="alpha", strategy_family="breakout", asset="BTC-USD", interval="1d"),
        _candidate("c2", strategy_name="beta", strategy_family="breakout", asset="ETH-USD", interval="1d"),
    ]

    first = partition_execution_batches(candidates=candidates)
    second = partition_execution_batches(candidates=list(reversed(candidates)))

    assert first == second
    assert [batch["batch_index"] for batch in first] == [1, 2]
    assert [batch["partition"] for batch in first] == [
        {"strategy_family": "breakout", "interval": "1d"},
        {"strategy_family": "trend_following", "interval": "4h"},
    ]
    assert first[0]["candidate_ids"] == ["c1", "c2"]
    assert first[1]["candidate_ids"] == ["c3"]


def test_batch_payloads_are_deterministic_and_summary_oriented():
    batches = partition_execution_batches(
        candidates=[
            _candidate("c1", strategy_name="alpha", strategy_family="breakout", asset="BTC-USD", interval="1d"),
            _candidate("c2", strategy_name="beta", strategy_family="breakout", asset="ETH-USD", interval="1d"),
        ]
    )
    batches[0]["status"] = "partial"
    batches[0]["started_at"] = "2026-04-13T12:00:00+00:00"
    batches[0]["finished_at"] = "2026-04-13T12:01:00+00:00"
    batches[0]["elapsed_seconds"] = 60
    batches[0]["completed_candidate_count"] = 2
    batches[0]["promoted_candidate_count"] = 1
    batches[0]["validated_candidate_count"] = 1
    batches[0]["timed_out_count"] = 1
    batches[0]["result_success_count"] = 1
    batches[0]["reason_code"] = "isolated_candidate_execution_issues"
    batches[0]["reason_detail"] = "batch completed with candidate-level timeout/error isolation"

    latest_payload = build_run_batches_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 13, 12, 5, 0, tzinfo=UTC),
        batches=batches,
    )
    manifest_payload = build_batch_manifest_payload(
        run_id="run-1",
        batch=batches[0],
    )

    assert latest_payload["summary"] == {
        "batch_count": 1,
        "pending_count": 0,
        "running_count": 0,
        "completed_count": 0,
        "partial_count": 1,
        "failed_count": 0,
        "skipped_count": 0,
    }
    assert latest_payload["batches"][0]["candidate_summary"]["assets"] == ["BTC-USD", "ETH-USD"]
    assert manifest_payload["batch_id"] == batches[0]["batch_id"]
    assert manifest_payload["partition"] == {"strategy_family": "breakout", "interval": "1d"}
    assert manifest_payload["candidate_ids"] == ["c1", "c2"]
    assert manifest_payload["reason_code"] == "isolated_candidate_execution_issues"
