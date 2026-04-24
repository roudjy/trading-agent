"""Unit tests for the shared OOS daily return stream validator."""

from __future__ import annotations

import pytest

from research._oos_stream import (
    ERROR_DUPLICATE,
    ERROR_MALFORMED,
    ERROR_MISSING,
    normalize_oos_daily_return_stream,
)


def test_empty_or_non_list_is_missing():
    assert normalize_oos_daily_return_stream(None) == ([], ERROR_MISSING)
    assert normalize_oos_daily_return_stream([]) == ([], ERROR_MISSING)
    assert normalize_oos_daily_return_stream({}) == ([], ERROR_MISSING)
    assert normalize_oos_daily_return_stream("stream") == ([], ERROR_MISSING)


def test_happy_path_sorts_ascending_by_timestamp():
    raw = [
        {"timestamp_utc": "2024-05-03T00:00:00+00:00", "return": 0.01},
        {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": -0.005},
        {"timestamp_utc": "2024-05-02T00:00:00+00:00", "return": 2},
    ]
    stream, err = normalize_oos_daily_return_stream(raw)
    assert err is None
    assert [p["timestamp_utc"] for p in stream] == [
        "2024-05-01T00:00:00+00:00",
        "2024-05-02T00:00:00+00:00",
        "2024-05-03T00:00:00+00:00",
    ]
    # ints are coerced to float
    assert stream[1]["return"] == pytest.approx(2.0)
    assert all(isinstance(p["return"], float) for p in stream)


@pytest.mark.parametrize(
    "point",
    [
        "not-a-dict",
        {"timestamp_utc": 0, "return": 0.0},          # timestamp not str
        {"timestamp_utc": "t", "return": "nope"},      # return not numeric
        {"timestamp_utc": "t"},                        # missing return
        {"return": 0.0},                               # missing timestamp
    ],
)
def test_malformed_points_are_rejected(point):
    assert normalize_oos_daily_return_stream([point]) == ([], ERROR_MALFORMED)


def test_duplicate_timestamp_rejected():
    raw = [
        {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.01},
        {"timestamp_utc": "2024-05-01T00:00:00+00:00", "return": 0.02},
    ]
    assert normalize_oos_daily_return_stream(raw) == ([], ERROR_DUPLICATE)


def test_error_codes_match_documented_strings():
    # Downstream readiness / empty-run reporting pins these exact
    # strings. Byte-identity with v3.12+ artifacts depends on it.
    assert ERROR_MISSING == "missing_oos_daily_return_stream"
    assert ERROR_MALFORMED == "malformed_oos_daily_return_stream"
    assert ERROR_DUPLICATE == "duplicate_timestamp_in_oos_daily_return_stream"
