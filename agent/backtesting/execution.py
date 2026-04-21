"""Canonical execution event scaffold (v3.8 step 1).

An *execution event* is the auditable record of what happened between
"signal emitted" and "trade booked" inside the backtest engine. The
engine today goes signal -> next-bar-close fill with fees applied
inline; no intermediate artifact exists. v3.8 Step 2+ will emit events
from ``BacktestEngine._simuleer_detailed``; Step 1 lands only the
scaffold so the event shape, invariants, and validator are pinned
before any emission site is written.

Five event kinds cover the lifecycle:

- ``accepted``       - signal acknowledged, not yet filled
- ``partial_fill``   - filled less than requested_size
- ``full_fill``      - filled exactly requested_size
- ``rejected``       - refused pre-fill, with a typed reason_code
- ``canceled``       - withdrawn pre- or post-accept, with a typed
                       reason_code

This is a parallel type to ``execution.protocols.Fill``. The two layers
are deliberately disjoint:

- ``execution.protocols.Fill`` models a *live/paper-broker success
  record* (buy/sell order direction, venue, client_tag, instrument_id).
  It is consumed by ``execution/paper/polymarket_sim.py`` and the
  live/paper broker machinery.
- ``ExecutionEvent`` (this module) models a *backtest evaluation
  record* over five kinds, using position-direction vocabulary
  (``long``/``short``). It is consumed by the research path only.

Merging the two types would drag venue / instrument_id / client_tag
concerns into the backtest layer and force the live layer to carry
five-state lifecycle information it does not need. Layer separation is
preserved by keeping them disjoint and documented here.

Invariants guaranteed by this module:

- ``ExecutionEvent`` is a frozen dataclass; attribute mutation raises
  ``FrozenInstanceError``.
- All fields are plain Python scalars (str, int, float, or None). No
  pandas / numpy objects, no caller-owned references, no Series, no
  Index.
- ``version`` is pinned to ``EXECUTION_EVENT_VERSION`` at construction.
- ``kind``, ``side``, and ``reason_code`` draw from pinned vocabularies
  (``ALLOWED_KIND_VALUES``, ``ALLOWED_SIDE_VALUES``,
  ``ALLOWED_REASON_CODES``). Additions in later steps must be additive
  tuple extensions and require a deliberate re-pin.
- Fill-specific fields (``fill_price``, ``filled_size``,
  ``fee_amount``, ``slippage_bps``) are non-None exactly on
  ``partial_fill`` / ``full_fill`` kinds and None on all others.
- ``reason_code`` is non-None exactly on ``rejected`` / ``canceled``
  kinds.
- ``event_id`` is deterministic, composed from
  ``sequence|asset|timestamp_utc|kind`` - never random.

Invariants that remain caller / engine-layer responsibility (not
enforceable in this module alone):

- Monotonicity of ``sequence`` within a ``(run_id, asset, fold_index)``
  scope. Step 2 assigns sequences from the engine fold loop.
- Temporal consistency of ``timestamp_utc`` relative to fold bounds.
- Fee / slippage numerical accuracy. Step 2 computes these at emission
  time; this module only enforces type and sign shape.

Public artifacts (``research_latest.json``, 19-column CSV row schema,
integrity / falsification sidecars) and ``candidate_id`` hashing
inputs (``research.candidate_pipeline._hash_payload``) are untouched
by Step 1: events are neither emitted nor serialized from any caller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


EXECUTION_EVENT_VERSION = "1.0"

ALLOWED_SIDE_VALUES: tuple[str, ...] = ("long", "short")
ALLOWED_KIND_VALUES: tuple[str, ...] = (
    "accepted",
    "partial_fill",
    "full_fill",
    "rejected",
    "canceled",
)
ALLOWED_REASON_CODES: tuple[str, ...] = (
    "NO_LIQUIDITY",
    "MAX_ENTRY_PRICE_EXCEEDED",
    "COOLDOWN_ACTIVE",
    "INSUFFICIENT_CAPITAL",
    "SHUTDOWN",
    "SIGNAL_FLAT",
    "UNKNOWN",
)

_FILL_KINDS: frozenset[str] = frozenset({"full_fill", "partial_fill"})
_NON_FILL_KINDS: frozenset[str] = frozenset(
    {"accepted", "rejected", "canceled"}
)
_REASON_KINDS: frozenset[str] = frozenset({"rejected", "canceled"})

_REASON_DETAIL_MAX_LEN = 256

# Type aliases. Kept as ``Literal`` rather than ``Enum`` because the
# event must remain JSON-serializable as plain strings when Step 2+
# writes events to a sidecar.
ExecutionEventKind = Literal[
    "accepted",
    "partial_fill",
    "full_fill",
    "rejected",
    "canceled",
]
ExecutionReasonCode = Literal[
    "NO_LIQUIDITY",
    "MAX_ENTRY_PRICE_EXCEEDED",
    "COOLDOWN_ACTIVE",
    "INSUFFICIENT_CAPITAL",
    "SHUTDOWN",
    "SIGNAL_FLAT",
    "UNKNOWN",
]


def _reject_non_primitive_number(field_name: str, value: Any) -> None:
    """Reject pandas / numpy numeric types on a float field.

    ``type(v) is float`` (or ``int``) is used deliberately instead of
    ``isinstance``: ``numpy.float64`` is an ``isinstance(..., float)``
    subclass and would otherwise slip through. The sentinel keeps
    caller-owned numeric containers out of events by construction,
    mirroring the ``FittedParams`` pandas rejection pattern.
    """
    if value is None:
        return
    if type(value) is float or type(value) is int:
        return
    raise ValueError(
        f"ExecutionEvent.{field_name}: numeric fields must be plain "
        f"Python int/float, got {type(value).__name__} "
        f"(module={type(value).__module__}). Cast with float(x) "
        f"before constructing the event."
    )


def _validate_finite_float(field_name: str, value: Optional[float]) -> None:
    if value is None:
        return
    _reject_non_primitive_number(field_name, value)
    if not math.isfinite(float(value)):
        raise ValueError(
            f"ExecutionEvent.{field_name}: must be finite, got {value!r}"
        )


def _validate_timestamp_utc(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError(
            f"ExecutionEvent.timestamp_utc: must be str, got "
            f"{type(value).__name__}"
        )
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"ExecutionEvent.timestamp_utc: not parseable via "
            f"datetime.fromisoformat ({value!r}): {exc}"
        ) from exc


def _build_event_id(
    sequence: int, asset: str, timestamp_utc: str, kind: str
) -> str:
    return f"{sequence}|{asset}|{timestamp_utc}|{kind}"


@dataclass(frozen=True)
class ExecutionEvent:
    """Immutable, auditable execution event.

    Construct via the kind-specific factory classmethods
    (``accepted``, ``full_fill``, ``partial_fill``, ``rejected``,
    ``canceled``) - they fill in the None-shaped fields correctly for
    each kind and compute ``event_id`` deterministically. Direct
    ``__init__`` construction is supported (tests, dict round-trip)
    and runs the same validator via ``__post_init__``.

    Fields:

    - ``event_id``: deterministic id (``sequence|asset|timestamp|kind``).
    - ``kind``: one of ``ALLOWED_KIND_VALUES``.
    - ``asset``: symbol the event pertains to.
    - ``side``: ``"long"`` or ``"short"`` - position direction the
      signal requested. Present for all kinds, including rejected /
      canceled (so the intent is preserved on the record).
    - ``timestamp_utc``: ISO-8601 UTC string; parseable via
      ``datetime.fromisoformat``.
    - ``sequence``: monotone non-negative counter within a
      ``(run_id, asset, fold_index)`` scope. Step 2 assigns values.
    - ``fold_index``: fold this event belongs to; ``None`` for
      full-series contexts.
    - ``intended_price``: price the signal was evaluated at; strictly
      positive.
    - ``requested_size``: size the signal asked for; non-negative.
    - ``fill_price``: realized fill price; non-None exactly on fill
      kinds, strictly positive on those.
    - ``filled_size``: realized fill size; non-None exactly on fill
      kinds. ``full_fill`` requires ``== requested_size``;
      ``partial_fill`` requires ``0 < filled_size < requested_size``.
    - ``fee_amount``: realized fee (account ccy); non-None exactly on
      fill kinds, ``>= 0``.
    - ``slippage_bps``: signed bps vs ``intended_price`` (positive =
      adverse); non-None exactly on fill kinds, finite float.
    - ``reason_code``: one of ``ALLOWED_REASON_CODES``; non-None
      exactly on ``rejected`` / ``canceled`` kinds.
    - ``reason_detail``: optional free-form suffix, <= 256 chars.
    - ``version``: module-level ``EXECUTION_EVENT_VERSION`` pin.
    - ``fingerprint``: structural placeholder for future event-stream
      fingerprinting; unset in Step 1. Reserved so Step 2+ can begin
      populating it without a contract break.
    """

    event_id: str
    kind: ExecutionEventKind
    asset: str
    side: Literal["long", "short"]
    timestamp_utc: str
    sequence: int
    fold_index: Optional[int]
    intended_price: float
    requested_size: float
    fill_price: Optional[float]
    filled_size: Optional[float]
    fee_amount: Optional[float]
    slippage_bps: Optional[float]
    reason_code: Optional[ExecutionReasonCode]
    reason_detail: Optional[str]
    version: str = EXECUTION_EVENT_VERSION
    fingerprint: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_execution_event(self)

    # ------------------------------------------------------------------
    # Factory builders
    # ------------------------------------------------------------------

    @classmethod
    def accepted(
        cls,
        *,
        asset: str,
        side: str,
        timestamp_utc: str,
        sequence: int,
        intended_price: float,
        requested_size: float,
        fold_index: Optional[int] = None,
        reason_detail: Optional[str] = None,
    ) -> "ExecutionEvent":
        return cls(
            event_id=_build_event_id(
                sequence, asset, timestamp_utc, "accepted"
            ),
            kind="accepted",
            asset=asset,
            side=side,  # type: ignore[arg-type]
            timestamp_utc=timestamp_utc,
            sequence=sequence,
            fold_index=fold_index,
            intended_price=intended_price,
            requested_size=requested_size,
            fill_price=None,
            filled_size=None,
            fee_amount=None,
            slippage_bps=None,
            reason_code=None,
            reason_detail=reason_detail,
        )

    @classmethod
    def full_fill(
        cls,
        *,
        asset: str,
        side: str,
        timestamp_utc: str,
        sequence: int,
        intended_price: float,
        requested_size: float,
        fill_price: float,
        filled_size: float,
        fee_amount: float,
        slippage_bps: float,
        fold_index: Optional[int] = None,
        reason_detail: Optional[str] = None,
    ) -> "ExecutionEvent":
        return cls(
            event_id=_build_event_id(
                sequence, asset, timestamp_utc, "full_fill"
            ),
            kind="full_fill",
            asset=asset,
            side=side,  # type: ignore[arg-type]
            timestamp_utc=timestamp_utc,
            sequence=sequence,
            fold_index=fold_index,
            intended_price=intended_price,
            requested_size=requested_size,
            fill_price=fill_price,
            filled_size=filled_size,
            fee_amount=fee_amount,
            slippage_bps=slippage_bps,
            reason_code=None,
            reason_detail=reason_detail,
        )

    @classmethod
    def partial_fill(
        cls,
        *,
        asset: str,
        side: str,
        timestamp_utc: str,
        sequence: int,
        intended_price: float,
        requested_size: float,
        fill_price: float,
        filled_size: float,
        fee_amount: float,
        slippage_bps: float,
        fold_index: Optional[int] = None,
        reason_detail: Optional[str] = None,
    ) -> "ExecutionEvent":
        return cls(
            event_id=_build_event_id(
                sequence, asset, timestamp_utc, "partial_fill"
            ),
            kind="partial_fill",
            asset=asset,
            side=side,  # type: ignore[arg-type]
            timestamp_utc=timestamp_utc,
            sequence=sequence,
            fold_index=fold_index,
            intended_price=intended_price,
            requested_size=requested_size,
            fill_price=fill_price,
            filled_size=filled_size,
            fee_amount=fee_amount,
            slippage_bps=slippage_bps,
            reason_code=None,
            reason_detail=reason_detail,
        )

    @classmethod
    def rejected(
        cls,
        *,
        asset: str,
        side: str,
        timestamp_utc: str,
        sequence: int,
        intended_price: float,
        requested_size: float,
        reason_code: str,
        fold_index: Optional[int] = None,
        reason_detail: Optional[str] = None,
    ) -> "ExecutionEvent":
        return cls(
            event_id=_build_event_id(
                sequence, asset, timestamp_utc, "rejected"
            ),
            kind="rejected",
            asset=asset,
            side=side,  # type: ignore[arg-type]
            timestamp_utc=timestamp_utc,
            sequence=sequence,
            fold_index=fold_index,
            intended_price=intended_price,
            requested_size=requested_size,
            fill_price=None,
            filled_size=None,
            fee_amount=None,
            slippage_bps=None,
            reason_code=reason_code,  # type: ignore[arg-type]
            reason_detail=reason_detail,
        )

    @classmethod
    def canceled(
        cls,
        *,
        asset: str,
        side: str,
        timestamp_utc: str,
        sequence: int,
        intended_price: float,
        requested_size: float,
        reason_code: str,
        fold_index: Optional[int] = None,
        reason_detail: Optional[str] = None,
    ) -> "ExecutionEvent":
        return cls(
            event_id=_build_event_id(
                sequence, asset, timestamp_utc, "canceled"
            ),
            kind="canceled",
            asset=asset,
            side=side,  # type: ignore[arg-type]
            timestamp_utc=timestamp_utc,
            sequence=sequence,
            fold_index=fold_index,
            intended_price=intended_price,
            requested_size=requested_size,
            fill_price=None,
            filled_size=None,
            fee_amount=None,
            slippage_bps=None,
            reason_code=reason_code,  # type: ignore[arg-type]
            reason_detail=reason_detail,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _validate_execution_event(event: ExecutionEvent) -> None:
    """Enforce ExecutionEvent invariants; raise ValueError on any violation.

    Called from ``__post_init__`` so every construction path goes
    through the same checks. The public ``validate_execution_event``
    helper wraps this for Step 2+ engine emission call sites.
    """
    # Vocabulary pins.
    if event.kind not in ALLOWED_KIND_VALUES:
        raise ValueError(
            f"ExecutionEvent.kind: {event.kind!r} not in "
            f"ALLOWED_KIND_VALUES={ALLOWED_KIND_VALUES}"
        )
    if event.side not in ALLOWED_SIDE_VALUES:
        raise ValueError(
            f"ExecutionEvent.side: {event.side!r} not in "
            f"ALLOWED_SIDE_VALUES={ALLOWED_SIDE_VALUES}"
        )
    if event.version != EXECUTION_EVENT_VERSION:
        raise ValueError(
            f"ExecutionEvent.version: {event.version!r} does not match "
            f"module EXECUTION_EVENT_VERSION={EXECUTION_EVENT_VERSION!r}"
        )

    # String fields.
    if not isinstance(event.event_id, str) or not event.event_id:
        raise ValueError(
            f"ExecutionEvent.event_id: must be a non-empty str, got "
            f"{event.event_id!r}"
        )
    if not isinstance(event.asset, str) or not event.asset:
        raise ValueError(
            f"ExecutionEvent.asset: must be a non-empty str, got "
            f"{event.asset!r}"
        )
    _validate_timestamp_utc(event.timestamp_utc)

    # Integer / fold fields.
    if not isinstance(event.sequence, int) or isinstance(event.sequence, bool):
        raise ValueError(
            f"ExecutionEvent.sequence: must be int, got "
            f"{type(event.sequence).__name__}"
        )
    if event.sequence < 0:
        raise ValueError(
            f"ExecutionEvent.sequence: must be >= 0, got {event.sequence}"
        )
    if event.fold_index is not None:
        if not isinstance(event.fold_index, int) or isinstance(
            event.fold_index, bool
        ):
            raise ValueError(
                f"ExecutionEvent.fold_index: must be int or None, got "
                f"{type(event.fold_index).__name__}"
            )
        if event.fold_index < 0:
            raise ValueError(
                f"ExecutionEvent.fold_index: must be >= 0 when set, got "
                f"{event.fold_index}"
            )

    # Numeric base fields.
    _reject_non_primitive_number("intended_price", event.intended_price)
    if not math.isfinite(float(event.intended_price)):
        raise ValueError(
            f"ExecutionEvent.intended_price: must be finite, got "
            f"{event.intended_price!r}"
        )
    if float(event.intended_price) <= 0.0:
        raise ValueError(
            f"ExecutionEvent.intended_price: must be > 0, got "
            f"{event.intended_price!r}"
        )
    _reject_non_primitive_number("requested_size", event.requested_size)
    if not math.isfinite(float(event.requested_size)):
        raise ValueError(
            f"ExecutionEvent.requested_size: must be finite, got "
            f"{event.requested_size!r}"
        )
    if float(event.requested_size) < 0.0:
        raise ValueError(
            f"ExecutionEvent.requested_size: must be >= 0, got "
            f"{event.requested_size!r}"
        )

    # Fill-specific fields. Non-None exactly on fill kinds.
    fill_fields = {
        "fill_price": event.fill_price,
        "filled_size": event.filled_size,
        "fee_amount": event.fee_amount,
        "slippage_bps": event.slippage_bps,
    }
    if event.kind in _FILL_KINDS:
        for name, value in fill_fields.items():
            if value is None:
                raise ValueError(
                    f"ExecutionEvent.{name}: must be non-None on "
                    f"kind={event.kind!r}"
                )
        _validate_finite_float("fill_price", event.fill_price)
        _validate_finite_float("filled_size", event.filled_size)
        _validate_finite_float("fee_amount", event.fee_amount)
        _validate_finite_float("slippage_bps", event.slippage_bps)
        if float(event.fill_price) <= 0.0:  # type: ignore[arg-type]
            raise ValueError(
                f"ExecutionEvent.fill_price: must be > 0 on fill kinds, "
                f"got {event.fill_price!r}"
            )
        if float(event.fee_amount) < 0.0:  # type: ignore[arg-type]
            raise ValueError(
                f"ExecutionEvent.fee_amount: must be >= 0 on fill kinds, "
                f"got {event.fee_amount!r}"
            )
        filled = float(event.filled_size)  # type: ignore[arg-type]
        requested = float(event.requested_size)
        if event.kind == "full_fill":
            if filled != requested:
                raise ValueError(
                    f"ExecutionEvent.filled_size: full_fill requires "
                    f"filled_size == requested_size, got "
                    f"{filled!r} vs {requested!r}"
                )
        else:  # partial_fill
            if not (0.0 < filled < requested):
                raise ValueError(
                    f"ExecutionEvent.filled_size: partial_fill requires "
                    f"0 < filled_size < requested_size, got "
                    f"{filled!r} vs {requested!r}"
                )
    else:
        for name, value in fill_fields.items():
            if value is not None:
                raise ValueError(
                    f"ExecutionEvent.{name}: must be None on "
                    f"kind={event.kind!r}, got {value!r}"
                )

    # Reason code. Non-None exactly on rejected / canceled.
    if event.kind in _REASON_KINDS:
        if event.reason_code is None:
            raise ValueError(
                f"ExecutionEvent.reason_code: must be non-None on "
                f"kind={event.kind!r}"
            )
        if event.reason_code not in ALLOWED_REASON_CODES:
            raise ValueError(
                f"ExecutionEvent.reason_code: {event.reason_code!r} not "
                f"in ALLOWED_REASON_CODES={ALLOWED_REASON_CODES}"
            )
    else:
        if event.reason_code is not None:
            raise ValueError(
                f"ExecutionEvent.reason_code: must be None on "
                f"kind={event.kind!r}, got {event.reason_code!r}"
            )

    # Reason detail.
    if event.reason_detail is not None:
        if not isinstance(event.reason_detail, str):
            raise ValueError(
                f"ExecutionEvent.reason_detail: must be str or None, got "
                f"{type(event.reason_detail).__name__}"
            )
        if len(event.reason_detail) > _REASON_DETAIL_MAX_LEN:
            raise ValueError(
                f"ExecutionEvent.reason_detail: length "
                f"{len(event.reason_detail)} exceeds "
                f"MAX={_REASON_DETAIL_MAX_LEN}"
            )

    # Fingerprint placeholder.
    if event.fingerprint is not None and not isinstance(
        event.fingerprint, str
    ):
        raise ValueError(
            f"ExecutionEvent.fingerprint: must be str or None, got "
            f"{type(event.fingerprint).__name__}"
        )


def validate_execution_event(event: ExecutionEvent) -> None:
    """Loud-fail entrypoint for engine-side callers.

    Step 2 will call this before appending an event to any event
    stream. Raises ValueError on any violation. Runs the same checks
    as ``__post_init__`` so it is idempotent on already-constructed
    events; intended for call sites that accept events from
    deserialization or cross-module boundaries.
    """
    if not isinstance(event, ExecutionEvent):
        raise ValueError(
            f"validate_execution_event: expected ExecutionEvent, got "
            f"{type(event).__name__}"
        )
    _validate_execution_event(event)


# ---------------------------------------------------------------------------
# Dict round-trip helpers. Reserved for Step 2 sidecar emission.
# ---------------------------------------------------------------------------


_EVENT_FIELD_ORDER: tuple[str, ...] = (
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
)


def execution_event_to_dict(event: ExecutionEvent) -> dict[str, Any]:
    """Deterministic dict view of an event.

    Key order follows ``_EVENT_FIELD_ORDER`` (source-of-truth for
    future sidecar schema). Values are plain scalars - no pandas, no
    numpy, no nested structures. Unused in Step 1 outside tests; Step
    2+ will use this for the event-stream sidecar.
    """
    if not isinstance(event, ExecutionEvent):
        raise ValueError(
            f"execution_event_to_dict: expected ExecutionEvent, got "
            f"{type(event).__name__}"
        )
    return {name: getattr(event, name) for name in _EVENT_FIELD_ORDER}


def execution_event_from_dict(payload: dict[str, Any]) -> ExecutionEvent:
    """Inverse of ``execution_event_to_dict``.

    The dict must carry every field in ``_EVENT_FIELD_ORDER``;
    ``event_id`` and ``version`` are not recomputed or defaulted on
    this path so the round-trip is bytewise. Extra keys raise
    ValueError so future additive schema changes remain loud.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"execution_event_from_dict: expected dict, got "
            f"{type(payload).__name__}"
        )
    expected = set(_EVENT_FIELD_ORDER)
    actual = set(payload.keys())
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise ValueError(
            f"execution_event_from_dict: missing keys {sorted(missing)}"
        )
    if extra:
        raise ValueError(
            f"execution_event_from_dict: unexpected keys {sorted(extra)}"
        )
    return ExecutionEvent(**{k: payload[k] for k in _EVENT_FIELD_ORDER})


# Silence unused-import / unused-symbol warnings for the reserved
# ``field`` name; intentionally imported for future-use consistency
# with other dataclasses in this package.
_ = field


__all__ = [
    "ALLOWED_KIND_VALUES",
    "ALLOWED_REASON_CODES",
    "ALLOWED_SIDE_VALUES",
    "EXECUTION_EVENT_VERSION",
    "ExecutionEvent",
    "ExecutionEventKind",
    "ExecutionReasonCode",
    "execution_event_from_dict",
    "execution_event_to_dict",
    "validate_execution_event",
]
