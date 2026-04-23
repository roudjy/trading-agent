"""Unit tests for research.candidate_returns_feed."""

from __future__ import annotations

from research.candidate_returns_feed import (
    RETURNS_ALIGNMENT,
    RETURNS_SCHEMA_VERSION,
    build_payload,
    build_record_from_evaluation,
    build_records_from_evaluations,
)
from research.candidate_registry_v2 import build_candidate_id


def _evaluation(
    strategy_name: str,
    asset: str,
    interval: str,
    params: dict,
    daily_returns: list[float],
    *,
    train: tuple[str, str] | None = None,
    test: tuple[str, str] | None = None,
) -> dict:
    folds = []
    if train is not None and test is not None:
        folds.append({"train": list(train), "test": list(test)})
    return {
        "row": {
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
        },
        "selected_params": params,
        "evaluation_report": {
            "evaluation_samples": {"daily_returns": daily_returns},
            "folds_by_asset": {asset: folds} if folds else {},
        },
    }


def test_build_record_from_evaluation_happy_path():
    record = build_record_from_evaluation(
        _evaluation(
            "trend_ma", "NVDA", "4h",
            {"lookback": 20, "threshold": 0.02},
            [0.01, -0.005, 0.002, 0.003, -0.01, 0.004],
            train=("2024-01-01", "2024-06-30"),
            test=("2024-07-01", "2024-12-31"),
        )
    )
    assert record is not None
    assert record.candidate_id == build_candidate_id(
        "trend_ma", "NVDA", "4h", {"lookback": 20, "threshold": 0.02}
    )
    assert record.daily_returns == (0.01, -0.005, 0.002, 0.003, -0.01, 0.004)
    assert record.n_obs == 6
    assert record.alignment == RETURNS_ALIGNMENT
    assert record.insufficient_returns is False
    assert record.start_date == "2024-01-01"
    assert record.end_date == "2024-12-31"


def test_build_record_returns_insufficient_when_no_returns():
    record = build_record_from_evaluation(
        _evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, [])
    )
    assert record is not None
    assert record.insufficient_returns is True
    assert record.daily_returns == ()


def test_build_record_returns_none_when_identifiers_missing():
    assert (
        build_record_from_evaluation({"evaluation_report": {"evaluation_samples": {}}})
        is None
    )


def test_build_records_deduplicates_and_sorts():
    evaluations = [
        _evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, [0.01, 0.02]),
        _evaluation("trend_ma", "AAPL", "4h", {"lookback": 10}, [0.01]),
        # Duplicate identifier — later entry wins.
        _evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, [0.05, 0.06, 0.07]),
    ]
    records = build_records_from_evaluations(evaluations)
    ids = [r.candidate_id for r in records]
    assert ids == sorted(ids)
    assert len({r.candidate_id for r in records}) == len(records)
    # "last seen wins" — NVDA must carry the 3-obs series.
    nvda = next(r for r in records if "NVDA" in r.candidate_id)
    assert nvda.n_obs == 3


def test_build_payload_canonical_shape():
    records = build_records_from_evaluations(
        [_evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, [0.01, -0.02])]
    )
    payload = build_payload(
        records=records,
        generated_at_utc="2026-04-23T20:00:00+00:00",
        run_id="run_test",
        git_revision="deadbeef",
    )
    body = payload.to_payload()
    assert body["schema_version"] == RETURNS_SCHEMA_VERSION
    assert body["alignment"] == RETURNS_ALIGNMENT
    assert body["timestamp_semantics"] == "engine_window_close_utc"
    assert body["run_id"] == "run_test"
    assert body["git_revision"] == "deadbeef"
    assert isinstance(body["entries"], list) and len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["candidate_id"].startswith("trend_ma|NVDA|4h|")
    assert entry["daily_returns"] == [0.01, -0.02]
    assert entry["insufficient_returns"] is False
