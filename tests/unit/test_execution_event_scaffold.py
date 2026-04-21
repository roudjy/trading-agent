"""Unit tests for ``agent.backtesting.execution`` (v3.8 step 1).

These tests exercise the ExecutionEvent scaffold in isolation. No
engine path is invoked, no public artifact is written, no Tier 1
regression pin is touched. Step 2+ will add engine-emission tests as
the event stream is wired up.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.execution import (
    ALLOWED_KIND_VALUES,
    ALLOWED_REASON_CODES,
    ALLOWED_SIDE_VALUES,
    EXECUTION_EVENT_VERSION,
    ExecutionEvent,
    execution_event_from_dict,
    execution_event_to_dict,
    validate_execution_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-04-21T12:00:00+00:00"


def _accepted_kwargs(**overrides):
    base = dict(
        asset="BTC-EUR",
        side="long",
        timestamp_utc=_TS,
        sequence=0,
        intended_price=50_000.0,
        requested_size=0.1,
    )
    base.update(overrides)
    return base


def _full_fill_kwargs(**overrides):
    base = dict(
        asset="BTC-EUR",
        side="long",
        timestamp_utc=_TS,
        sequence=1,
        intended_price=50_000.0,
        requested_size=0.1,
        fill_price=50_050.0,
        filled_size=0.1,
        fee_amount=12.5,
        slippage_bps=10.0,
    )
    base.update(overrides)
    return base


def _partial_fill_kwargs(**overrides):
    base = dict(
        asset="BTC-EUR",
        side="long",
        timestamp_utc=_TS,
        sequence=2,
        intended_price=50_000.0,
        requested_size=0.1,
        fill_price=50_050.0,
        filled_size=0.05,
        fee_amount=6.25,
        slippage_bps=10.0,
    )
    base.update(overrides)
    return base


def _rejected_kwargs(**overrides):
    base = dict(
        asset="BTC-EUR",
        side="long",
        timestamp_utc=_TS,
        sequence=3,
        intended_price=50_000.0,
        requested_size=0.1,
        reason_code="NO_LIQUIDITY",
    )
    base.update(overrides)
    return base


def _canceled_kwargs(**overrides):
    base = dict(
        asset="BTC-EUR",
        side="long",
        timestamp_utc=_TS,
        sequence=4,
        intended_price=50_000.0,
        requested_size=0.1,
        reason_code="SHUTDOWN",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1-4. Vocabulary pins
# ---------------------------------------------------------------------------


def test_execution_event_version_is_pinned_string():
    assert EXECUTION_EVENT_VERSION == "1.0"
    assert isinstance(EXECUTION_EVENT_VERSION, str)


def test_allowed_kind_values_are_pinned_tuple():
    assert ALLOWED_KIND_VALUES == (
        "accepted",
        "partial_fill",
        "full_fill",
        "rejected",
        "canceled",
    )
    assert isinstance(ALLOWED_KIND_VALUES, tuple)


def test_allowed_side_values_are_pinned_tuple():
    assert ALLOWED_SIDE_VALUES == ("long", "short")
    assert isinstance(ALLOWED_SIDE_VALUES, tuple)


def test_allowed_reason_codes_are_pinned_tuple():
    assert ALLOWED_REASON_CODES == (
        "NO_LIQUIDITY",
        "MAX_ENTRY_PRICE_EXCEEDED",
        "COOLDOWN_ACTIVE",
        "INSUFFICIENT_CAPITAL",
        "SHUTDOWN",
        "SIGNAL_FLAT",
        "UNKNOWN",
    )
    assert isinstance(ALLOWED_REASON_CODES, tuple)


# ---------------------------------------------------------------------------
# 5-9. Factory builders
# ---------------------------------------------------------------------------


def test_accepted_factory_builds_minimal_valid_event():
    event = ExecutionEvent.accepted(**_accepted_kwargs())
    assert event.kind == "accepted"
    assert event.fill_price is None
    assert event.filled_size is None
    assert event.fee_amount is None
    assert event.slippage_bps is None
    assert event.reason_code is None
    assert event.version == EXECUTION_EVENT_VERSION
    assert event.event_id == f"0|BTC-EUR|{_TS}|accepted"


def test_full_fill_factory_enforces_filled_equals_requested():
    event = ExecutionEvent.full_fill(**_full_fill_kwargs())
    assert event.kind == "full_fill"
    assert event.fill_price == 50_050.0
    assert event.filled_size == event.requested_size
    assert event.fee_amount == 12.5
    assert event.slippage_bps == 10.0
    assert event.reason_code is None

    with pytest.raises(ValueError, match="filled_size"):
        ExecutionEvent.full_fill(
            **_full_fill_kwargs(filled_size=0.05)
        )


def test_partial_fill_factory_enforces_strict_inequality():
    event = ExecutionEvent.partial_fill(**_partial_fill_kwargs())
    assert event.kind == "partial_fill"
    assert 0.0 < event.filled_size < event.requested_size

    with pytest.raises(ValueError, match="filled_size"):
        ExecutionEvent.partial_fill(**_partial_fill_kwargs(filled_size=0.0))
    with pytest.raises(ValueError, match="filled_size"):
        ExecutionEvent.partial_fill(**_partial_fill_kwargs(filled_size=0.1))
    with pytest.raises(ValueError, match="filled_size"):
        ExecutionEvent.partial_fill(**_partial_fill_kwargs(filled_size=0.2))


def test_rejected_factory_requires_reason_code():
    event = ExecutionEvent.rejected(**_rejected_kwargs())
    assert event.kind == "rejected"
    assert event.reason_code == "NO_LIQUIDITY"
    assert event.fill_price is None

    with pytest.raises(ValueError, match="reason_code"):
        ExecutionEvent.rejected(**_rejected_kwargs(reason_code="NOT_A_CODE"))


def test_canceled_factory_requires_reason_code():
    event = ExecutionEvent.canceled(**_canceled_kwargs())
    assert event.kind == "canceled"
    assert event.reason_code == "SHUTDOWN"
    assert event.fee_amount is None

    with pytest.raises(ValueError, match="reason_code"):
        ExecutionEvent.canceled(**_canceled_kwargs(reason_code="BOGUS"))


# ---------------------------------------------------------------------------
# 10-19. Validator invariants
# ---------------------------------------------------------------------------


def test_validate_rejects_unknown_kind():
    event = ExecutionEvent.accepted(**_accepted_kwargs())
    # Frozen dataclass - go through __init__ with the bogus kind.
    with pytest.raises(ValueError, match="kind"):
        ExecutionEvent(
            event_id=event.event_id,
            kind="weird_kind",  # type: ignore[arg-type]
            asset=event.asset,
            side=event.side,
            timestamp_utc=event.timestamp_utc,
            sequence=event.sequence,
            fold_index=event.fold_index,
            intended_price=event.intended_price,
            requested_size=event.requested_size,
            fill_price=None,
            filled_size=None,
            fee_amount=None,
            slippage_bps=None,
            reason_code=None,
            reason_detail=None,
        )


def test_validate_rejects_unknown_side():
    with pytest.raises(ValueError, match="side"):
        ExecutionEvent.accepted(**_accepted_kwargs(side="flat"))


def test_validate_rejects_version_mismatch():
    base = ExecutionEvent.accepted(**_accepted_kwargs())
    with pytest.raises(ValueError, match="version"):
        ExecutionEvent(
            event_id=base.event_id,
            kind=base.kind,
            asset=base.asset,
            side=base.side,
            timestamp_utc=base.timestamp_utc,
            sequence=base.sequence,
            fold_index=base.fold_index,
            intended_price=base.intended_price,
            requested_size=base.requested_size,
            fill_price=None,
            filled_size=None,
            fee_amount=None,
            slippage_bps=None,
            reason_code=None,
            reason_detail=None,
            version="2.0",
            fingerprint=None,
        )


def test_validate_rejects_negative_sequence():
    with pytest.raises(ValueError, match="sequence"):
        ExecutionEvent.accepted(**_accepted_kwargs(sequence=-1))


def test_validate_rejects_non_positive_intended_price():
    with pytest.raises(ValueError, match="intended_price"):
        ExecutionEvent.accepted(**_accepted_kwargs(intended_price=0.0))
    with pytest.raises(ValueError, match="intended_price"):
        ExecutionEvent.accepted(**_accepted_kwargs(intended_price=-1.0))


def test_validate_rejects_fill_fields_on_non_fill_kinds():
    base = _accepted_kwargs()
    # Accepted event cannot carry any of the four fill fields.
    accepted = ExecutionEvent.accepted(**base)
    names = ("fill_price", "filled_size", "fee_amount", "slippage_bps")
    for field_name in names:
        with pytest.raises(ValueError, match=field_name):
            dataclasses.replace(accepted, **{field_name: 1.0})
    # Rejected / canceled events also cannot carry fill fields.
    rejected = ExecutionEvent.rejected(**_rejected_kwargs())
    with pytest.raises(ValueError, match="fill_price"):
        dataclasses.replace(rejected, fill_price=50_000.0)
    canceled = ExecutionEvent.canceled(**_canceled_kwargs())
    with pytest.raises(ValueError, match="fee_amount"):
        dataclasses.replace(canceled, fee_amount=1.0)


def test_validate_rejects_missing_fill_fields_on_fill_kinds():
    base = ExecutionEvent.full_fill(**_full_fill_kwargs())
    names = ("fill_price", "filled_size", "fee_amount", "slippage_bps")
    for field_name in names:
        with pytest.raises(ValueError, match=field_name):
            dataclasses.replace(base, **{field_name: None})
    partial = ExecutionEvent.partial_fill(**_partial_fill_kwargs())
    names = ("fill_price", "filled_size", "fee_amount", "slippage_bps")
    for field_name in names:
        with pytest.raises(ValueError, match=field_name):
            dataclasses.replace(partial, **{field_name: None})


def test_validate_rejects_nonfinite_slippage_bps():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="slippage_bps"):
            ExecutionEvent.full_fill(**_full_fill_kwargs(slippage_bps=bad))


def test_validate_rejects_unparseable_timestamp():
    with pytest.raises(ValueError, match="timestamp_utc"):
        ExecutionEvent.accepted(**_accepted_kwargs(timestamp_utc="not-a-date"))
    with pytest.raises(ValueError, match="timestamp_utc"):
        ExecutionEvent.accepted(**_accepted_kwargs(timestamp_utc=""))


def test_validate_rejects_oversized_reason_detail():
    too_long = "x" * 257
    with pytest.raises(ValueError, match="reason_detail"):
        ExecutionEvent.accepted(**_accepted_kwargs(reason_detail=too_long))
    # Boundary at 256 is accepted.
    event = ExecutionEvent.accepted(
        **_accepted_kwargs(reason_detail="x" * 256)
    )
    assert event.reason_detail is not None
    assert len(event.reason_detail) == 256


# ---------------------------------------------------------------------------
# 20. Pandas / numpy sentinel
# ---------------------------------------------------------------------------


def test_validate_rejects_pandas_or_numpy_typed_fields():
    # numpy.float64 is an isinstance(..., float) subclass - the module
    # uses type(v) is float / type(v) is int to reject it loudly.
    with pytest.raises(ValueError, match="intended_price"):
        ExecutionEvent.accepted(
            **_accepted_kwargs(intended_price=np.float64(50_000.0))
        )
    with pytest.raises(ValueError, match="requested_size"):
        ExecutionEvent.accepted(
            **_accepted_kwargs(requested_size=np.float32(0.1))
        )
    with pytest.raises(ValueError, match="fee_amount"):
        ExecutionEvent.full_fill(
            **_full_fill_kwargs(fee_amount=np.float64(1.0))
        )
    # pandas Timestamp into timestamp_utc - we require a plain str.
    with pytest.raises(ValueError, match="timestamp_utc"):
        ExecutionEvent.accepted(
            **_accepted_kwargs(timestamp_utc=pd.Timestamp("2026-04-21T12:00Z"))
        )


# ---------------------------------------------------------------------------
# 21. Immutability
# ---------------------------------------------------------------------------


def test_event_dataclass_is_frozen():
    event = ExecutionEvent.accepted(**_accepted_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = "full_fill"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.asset = "ETH-EUR"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 22. Dict round-trip (reserved for Step 2 sidecar use)
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_round_trip_bytewise():
    builders = [
        ExecutionEvent.accepted(**_accepted_kwargs()),
        ExecutionEvent.full_fill(**_full_fill_kwargs()),
        ExecutionEvent.partial_fill(**_partial_fill_kwargs()),
        ExecutionEvent.rejected(**_rejected_kwargs()),
        ExecutionEvent.canceled(**_canceled_kwargs()),
    ]
    for event in builders:
        payload = execution_event_to_dict(event)
        assert list(payload.keys()) == [
            "event_id",
            "kind",
            "asset",
            "side",
            "timestamp_utc",
            "sequence",
            "fold_index",
            "intended_price",
            "requested_size",
            "fill_price",
            "filled_size",
            "fee_amount",
            "slippage_bps",
            "reason_code",
            "reason_detail",
            "version",
            "fingerprint",
        ]
        restored = execution_event_from_dict(payload)
        assert restored == event
        # Key ordering and values determinism: second dict matches first.
        assert execution_event_to_dict(restored) == payload

    # Extra keys raise.
    bad_payload = execution_event_to_dict(builders[0])
    bad_payload["unexpected"] = "value"
    with pytest.raises(ValueError, match="unexpected"):
        execution_event_from_dict(bad_payload)

    # Missing keys raise.
    short_payload = execution_event_to_dict(builders[0])
    del short_payload["event_id"]
    with pytest.raises(ValueError, match="missing"):
        execution_event_from_dict(short_payload)


# ---------------------------------------------------------------------------
# 23. Determinism
# ---------------------------------------------------------------------------


def test_identical_inputs_produce_equal_events_and_equal_dicts():
    a = ExecutionEvent.full_fill(**_full_fill_kwargs())
    b = ExecutionEvent.full_fill(**_full_fill_kwargs())
    assert a == b
    assert hash(a) == hash(b)
    assert execution_event_to_dict(a) == execution_event_to_dict(b)


# ---------------------------------------------------------------------------
# Extras: public validate_execution_event loud-fail surface
# ---------------------------------------------------------------------------


def test_public_validate_execution_event_passes_on_valid_event():
    event = ExecutionEvent.full_fill(**_full_fill_kwargs())
    validate_execution_event(event)  # must not raise


def test_public_validate_execution_event_rejects_non_events():
    not_an_event: object = {"kind": "accepted"}
    with pytest.raises(ValueError, match="expected ExecutionEvent"):
        validate_execution_event(not_an_event)  # type: ignore[arg-type]


def test_accepted_with_reason_detail_within_cap_is_accepted():
    event = ExecutionEvent.accepted(
        **_accepted_kwargs(reason_detail="short note")
    )
    assert event.reason_detail == "short note"


def test_fold_index_must_be_non_negative_when_set():
    with pytest.raises(ValueError, match="fold_index"):
        ExecutionEvent.accepted(**_accepted_kwargs(fold_index=-1))
    event = ExecutionEvent.accepted(**_accepted_kwargs(fold_index=0))
    assert event.fold_index == 0
    event_none = ExecutionEvent.accepted(**_accepted_kwargs(fold_index=None))
    assert event_none.fold_index is None


def test_intended_price_nonfinite_is_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="intended_price"):
            ExecutionEvent.accepted(**_accepted_kwargs(intended_price=bad))
    # Sanity: a finite positive value survives.
    event = ExecutionEvent.accepted(**_accepted_kwargs(intended_price=1.0))
    assert math.isfinite(event.intended_price)
