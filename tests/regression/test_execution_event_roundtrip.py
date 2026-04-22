"""Regression: ExecutionEvent JSON serialization must survive JSON roundtrip.

v3.8 introduced `ExecutionEvent` with frozen helpers
`execution_event_to_dict` and `execution_event_from_dict`. The helpers
already have coverage for in-memory roundtrip (`test_execution_event_scaffold.py`)
and engine emission (`test_execution_event_emission.py`). This v3.10
regression closes the last gap: serialize → json.dumps → json.loads →
from_dict must produce a bytewise-equal event, and the validator must
reject the typed corruption cases (NaN, Inf, non-UTC parseable strings,
stripped required keys, extra keys) rather than silently accept them.

The v3.10 report agent reads ExecutionEvent payloads from disk; silent
corruption here would poison the report and the UI.
"""

from __future__ import annotations

import json
import math

import pytest

from agent.backtesting.execution import (
    EXECUTION_EVENT_VERSION,
    ExecutionEvent,
    execution_event_from_dict,
    execution_event_to_dict,
)


def _sample_full_fill() -> ExecutionEvent:
    return ExecutionEvent.full_fill(
        asset="BTC-USD",
        side="long",
        timestamp_utc="2026-04-22T10:00:00+00:00",
        sequence=3,
        intended_price=100.0,
        requested_size=1.5,
        fill_price=100.25,
        filled_size=1.5,
        fee_amount=0.0125,
        slippage_bps=2.5,
        fold_index=2,
    )


def _sample_rejected() -> ExecutionEvent:
    return ExecutionEvent.rejected(
        asset="ETH-USD",
        side="short",
        timestamp_utc="2026-04-22T11:15:00+00:00",
        sequence=5,
        intended_price=2000.0,
        requested_size=0.25,
        reason_code="NO_LIQUIDITY",
        fold_index=4,
    )


def test_roundtrip_full_fill_bytewise_through_json():
    original = _sample_full_fill()
    payload = execution_event_to_dict(original)
    blob = json.dumps(payload, sort_keys=True)
    restored_payload = json.loads(blob)
    restored = execution_event_from_dict(restored_payload)
    assert restored == original
    assert execution_event_to_dict(restored) == payload


def test_roundtrip_rejected_bytewise_through_json():
    original = _sample_rejected()
    payload = execution_event_to_dict(original)
    blob = json.dumps(payload, sort_keys=True)
    restored = execution_event_from_dict(json.loads(blob))
    assert restored == original


def test_roundtrip_version_is_pinned():
    event = _sample_full_fill()
    payload = execution_event_to_dict(event)
    assert payload["version"] == EXECUTION_EVENT_VERSION
    # A version mismatch on deserialization must raise.
    payload["version"] = "99.0"
    with pytest.raises(ValueError, match="version"):
        execution_event_from_dict(payload)


@pytest.mark.parametrize(
    "field",
    ["intended_price", "requested_size", "fill_price", "filled_size",
     "fee_amount", "slippage_bps"],
)
def test_nan_in_numeric_fields_is_rejected(field):
    payload = execution_event_to_dict(_sample_full_fill())
    payload[field] = float("nan")
    with pytest.raises(ValueError):
        execution_event_from_dict(payload)


@pytest.mark.parametrize(
    "field",
    ["intended_price", "requested_size", "fill_price", "filled_size",
     "fee_amount", "slippage_bps"],
)
def test_inf_in_numeric_fields_is_rejected(field):
    payload = execution_event_to_dict(_sample_full_fill())
    payload[field] = math.inf
    with pytest.raises(ValueError):
        execution_event_from_dict(payload)


def test_unparseable_timestamp_is_rejected():
    payload = execution_event_to_dict(_sample_full_fill())
    payload["timestamp_utc"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="timestamp"):
        execution_event_from_dict(payload)


def test_missing_required_key_is_rejected():
    payload = execution_event_to_dict(_sample_full_fill())
    del payload["kind"]
    with pytest.raises(ValueError, match="missing keys"):
        execution_event_from_dict(payload)


def test_extra_key_is_rejected_loudly():
    # Additive drift must surface: callers must not silently accept
    # new fields. See execution.py::execution_event_from_dict docstring.
    payload = execution_event_to_dict(_sample_full_fill())
    payload["smuggled_field"] = "hello"
    with pytest.raises(ValueError, match="unexpected keys"):
        execution_event_from_dict(payload)


def test_non_dict_input_is_rejected():
    with pytest.raises(ValueError, match="expected dict"):
        execution_event_from_dict("not a dict")  # type: ignore[arg-type]
