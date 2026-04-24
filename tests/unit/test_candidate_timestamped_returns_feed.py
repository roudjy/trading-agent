"""v3.15 unit tests: candidate_timestamped_returns_feed."""

from __future__ import annotations

import pytest

from research.candidate_timestamped_returns_feed import (
    TIMESTAMPED_RETURNS_ALIGNMENT,
    TIMESTAMPED_RETURNS_SCHEMA_VERSION,
    TIMESTAMPED_RETURNS_TIMESTAMP_SEMANTICS,
    TimestampedCandidateReturnsRecord,
    build_payload,
    build_record_from_evaluation,
    build_records_from_evaluations,
)


def _evaluation(
    *,
    strategy_name: str = "ema_trend",
    asset: str = "BTC/EUR",
    interval: str = "1d",
    selected_params: dict | None = None,
    stream: list[dict] | None = None,
) -> dict:
    return {
        "row": {
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
        },
        "selected_params": selected_params or {"ema_fast": 10, "ema_slow": 50},
        "evaluation_report": {
            "evaluation_streams": {
                "oos_daily_returns": stream if stream is not None else [
                    {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.01},
                    {"timestamp_utc": "2024-05-02T00:00:00+00:00", "return": -0.005},
                    {"timestamp_utc": "2024-05-03T00:00:00+00:00", "return": 0.008},
                ],
            },
        },
    }


def test_record_shape_happy_path():
    record = build_record_from_evaluation(_evaluation())
    assert isinstance(record, TimestampedCandidateReturnsRecord)
    assert record.n_obs == 3
    assert record.insufficient_returns is False
    assert record.stream_error is None
    assert record.alignment == TIMESTAMPED_RETURNS_ALIGNMENT
    assert len(record.timestamps) == len(record.daily_returns) == 3
    assert record.start_date == record.timestamps[0]
    assert record.end_date == record.timestamps[-1]
    # Payload round-trips the arrays
    payload = record.to_payload()
    assert payload["timestamps"] == list(record.timestamps)
    assert payload["daily_returns"] == list(record.daily_returns)
    assert payload["stream_error"] is None


def test_missing_stream_marks_insufficient():
    ev = _evaluation(stream=[])
    record = build_record_from_evaluation(ev)
    assert record is not None
    assert record.insufficient_returns is True
    assert record.n_obs == 0
    assert record.timestamps == ()
    assert record.daily_returns == ()
    assert record.stream_error == "missing_oos_daily_return_stream"


def test_duplicate_timestamp_is_flagged_as_stream_error():
    raw = [
        {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.01},
        {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.02},
    ]
    record = build_record_from_evaluation(_evaluation(stream=raw))
    assert record is not None
    assert record.insufficient_returns is True
    assert record.n_obs == 0
    assert record.stream_error == "duplicate_timestamp_in_oos_daily_return_stream"


def test_canonical_ordering_and_dedup_last_seen_wins():
    ev_a = _evaluation(
        strategy_name="alpha",
        asset="BTC/EUR",
        stream=[{"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.01}],
    )
    ev_b_first = _evaluation(
        strategy_name="beta",
        asset="ETH/EUR",
        stream=[{"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.02}],
    )
    ev_b_latest = _evaluation(
        strategy_name="beta",
        asset="ETH/EUR",
        stream=[{"timestamp_utc": "2024-05-02T00:00:00+00:00", "return": 0.03}],
    )
    records = build_records_from_evaluations([ev_b_first, ev_a, ev_b_latest])
    # Canonical order: by candidate_id (alpha < beta)
    assert records[0].candidate_id < records[1].candidate_id
    # Last-seen wins for duplicate candidate_id (beta latest stream kept)
    beta = records[1]
    assert beta.daily_returns[0] == pytest.approx(0.03)


def test_build_payload_schema_pins():
    record = build_record_from_evaluation(_evaluation())
    payload = build_payload(
        records=[record],
        generated_at_utc="2026-04-24T10:00:00+00:00",
        run_id="run-xyz",
        git_revision="deadbeef",
    ).to_payload()
    assert payload["schema_version"] == TIMESTAMPED_RETURNS_SCHEMA_VERSION == "1.0"
    assert payload["alignment"] == TIMESTAMPED_RETURNS_ALIGNMENT
    assert payload["timestamp_semantics"] == TIMESTAMPED_RETURNS_TIMESTAMP_SEMANTICS
    assert payload["run_id"] == "run-xyz"
    assert payload["git_revision"] == "deadbeef"
    assert payload["generated_at_utc"] == "2026-04-24T10:00:00+00:00"
    assert len(payload["entries"]) == 1


def test_missing_identifiers_returns_none():
    ev = _evaluation()
    ev["row"]["strategy_name"] = None
    ev["strategy_name"] = None
    assert build_record_from_evaluation(ev) is None
