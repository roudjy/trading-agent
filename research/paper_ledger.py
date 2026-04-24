"""v3.15 paper ledger — first-class lifecycle projection.

Projects the engine-emitted ``oos_execution_events`` stream for
one or more candidates into a typed v3.15 lifecycle ledger:

- ``signal``   - strategy triggered an entry/exit decision
- ``order``    - paper-order constructed (side, size, venue)
- ``fill``     - order filled under the venue-cost profile
- ``reject``   - order rejected by a venue rule
- ``skip``     - signal withdrawn (cooldown / canceled)
- ``position`` - resulting position state after a fill

**Evidence discipline (critical).** The ledger never invents
bron-evidence that cannot be traced to the engine stream. Every
event carries:

- ``evidence_status`` in
  ``{"reconstructed", "projected_minimal",
    "projected_insufficient"}``
- ``lineage`` - a list of ``{source, stream_index}`` pointers to
  the engine stream item the event was built from

When the signal itself is not separately serialized by the engine
(v3.15 infers its existence from the presence of an ExecutionEvent),
the ledger emits a ``signal`` event with
``evidence_status="projected_minimal"`` and only verifiable fields
populated.

When venue mapping is missing for a candidate
(``asset_type ∈ {unknown, futures, index_like}``), the ledger
emits only a single ``signal`` + ``reject`` pair per execution event
with ``reason="insufficient_venue_mapping"``; readiness picks that
up as a blocking reason.

The ledger never imports or calls any broker / live / execution
code. v3.15 invariant: no live surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from research.paper_venues import (
    PAPER_VENUES_VERSION,
    VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE,
    VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS,
    VENUE_IBKR_EQUITY_FEE_PER_SIDE,
    VENUE_IBKR_EQUITY_SLIPPAGE_BPS,
    venue_name_for_asset_type,
)


PAPER_LEDGER_VERSION: str = "v0.1"
PAPER_LEDGER_SCHEMA_VERSION: str = "1.0"

# Closed v3.15 event taxonomy. Tuple order is the authoritative
# lifecycle order; same-timestamp events are sorted by this index
# so that a single full_fill projects to signal→order→fill→position
# rather than to alphabetical chaos.
LEDGER_EVENT_TYPES: tuple[str, ...] = (
    "signal",
    "order",
    "fill",
    "reject",
    "skip",
    "position",
)
_EVENT_TYPE_LIFECYCLE_INDEX: dict[str, int] = {
    etype: idx for idx, etype in enumerate(LEDGER_EVENT_TYPES)
}

# Closed evidence-status taxonomy
EVIDENCE_STATUSES: tuple[str, ...] = (
    "reconstructed",
    "projected_minimal",
    "projected_insufficient",
)

# Ledger-level reject reasons that originate within the v3.15
# layer itself (distinct from the engine's reason_codes).
LEDGER_REJECT_REASON_INSUFFICIENT_VENUE: str = "insufficient_venue_mapping"


@dataclass(frozen=True)
class LedgerEvent:
    """One v3.15 lifecycle event."""

    event_id: str
    candidate_id: str
    event_type: str
    timestamp_utc: str
    venue: str | None
    evidence_status: str
    lineage: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "candidate_id": self.candidate_id,
            "event_type": self.event_type,
            "timestamp_utc": self.timestamp_utc,
            "venue": self.venue,
            "evidence_status": self.evidence_status,
            "lineage": [dict(item) for item in self.lineage],
            "payload": dict(self.payload),
        }


def _venue_constants(venue: str | None) -> dict[str, Any]:
    if venue == "crypto_bitvavo":
        return {
            "venue_fee_per_side": VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE,
            "venue_slippage_bps": VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS,
        }
    if venue == "equity_ibkr":
        return {
            "venue_fee_per_side": VENUE_IBKR_EQUITY_FEE_PER_SIDE,
            "venue_slippage_bps": VENUE_IBKR_EQUITY_SLIPPAGE_BPS,
        }
    return {
        "venue_fee_per_side": None,
        "venue_slippage_bps": None,
    }


def _event_field(event: Any, name: str) -> Any:
    """Read a field from an ExecutionEvent (dataclass or dict)."""
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _base_event_id(candidate_id: str, source_event_id: str, suffix: str) -> str:
    return f"{candidate_id}|{source_event_id}|{suffix}"


def _lineage_entry(stream_index: int) -> dict[str, Any]:
    return {"source": "oos_execution_events", "stream_index": int(stream_index)}


def _emit_signal(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str | None,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "signal"),
        candidate_id=candidate_id,
        event_type="signal",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="projected_minimal",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "side": _event_field(source_event, "side"),
            "sequence": _event_field(source_event, "sequence"),
            "fold_index": _event_field(source_event, "fold_index"),
        },
    )


def _emit_order(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "order"),
        candidate_id=candidate_id,
        event_type="order",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="reconstructed",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "side": _event_field(source_event, "side"),
            "intended_price": _event_field(source_event, "intended_price"),
            "requested_size": _event_field(source_event, "requested_size"),
            **_venue_constants(venue),
        },
    )


def _emit_fill(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "fill"),
        candidate_id=candidate_id,
        event_type="fill",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="reconstructed",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "side": _event_field(source_event, "side"),
            "fill_price": _event_field(source_event, "fill_price"),
            "filled_size": _event_field(source_event, "filled_size"),
            "engine_fee_amount": _event_field(source_event, "fee_amount"),
            "engine_slippage_bps": _event_field(source_event, "slippage_bps"),
            "partial": _event_field(source_event, "kind") == "partial_fill",
            **_venue_constants(venue),
        },
    )


def _emit_position(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str,
) -> LedgerEvent:
    filled_size = _event_field(source_event, "filled_size") or 0.0
    side = _event_field(source_event, "side")
    signed_size = float(filled_size) if side == "long" else -float(filled_size)
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "position"),
        candidate_id=candidate_id,
        event_type="position",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="projected_minimal",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "signed_size_delta": signed_size,
            "fill_price": _event_field(source_event, "fill_price"),
        },
    )


def _emit_reject(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str | None,
    reason: str,
    reason_detail: str | None,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "reject"),
        candidate_id=candidate_id,
        event_type="reject",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="reconstructed",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "reason": reason,
            "reason_detail": reason_detail,
            "side": _event_field(source_event, "side"),
        },
    )


def _emit_skip(
    *,
    candidate_id: str,
    source_event: Any,
    source_event_id: str,
    stream_index: int,
    venue: str | None,
    reason: str,
    reason_detail: str | None,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=_base_event_id(candidate_id, source_event_id, "skip"),
        candidate_id=candidate_id,
        event_type="skip",
        timestamp_utc=str(_event_field(source_event, "timestamp_utc")),
        venue=venue,
        evidence_status="reconstructed",
        lineage=(_lineage_entry(stream_index),),
        payload={
            "reason": reason,
            "reason_detail": reason_detail,
            "side": _event_field(source_event, "side"),
        },
    )


def build_ledger_events_for_candidate(
    *,
    candidate_id: str,
    asset_type: str,
    execution_events: Iterable[Any],
) -> list[LedgerEvent]:
    """Project one candidate's engine execution events into v3.15
    ledger events.

    When ``asset_type`` has no venue mapping the ledger emits
    ``signal`` + ``reject(reason=insufficient_venue_mapping)`` per
    source event and nothing else.
    """
    venue = venue_name_for_asset_type(asset_type)
    events: list[LedgerEvent] = []
    for index, source in enumerate(execution_events):
        source_event_id = str(_event_field(source, "event_id") or f"idx{index}")
        kind = _event_field(source, "kind")
        # Always emit a projected-minimal signal
        events.append(
            _emit_signal(
                candidate_id=candidate_id,
                source_event=source,
                source_event_id=source_event_id,
                stream_index=index,
                venue=venue,
            )
        )
        if venue is None:
            # Unmapped venue → reject, nothing else
            events.append(
                _emit_reject(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=None,
                    reason=LEDGER_REJECT_REASON_INSUFFICIENT_VENUE,
                    reason_detail=f"asset_type={asset_type!r}",
                )
            )
            continue

        if kind in ("accepted", "full_fill", "partial_fill"):
            events.append(
                _emit_order(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=venue,
                )
            )
        if kind in ("full_fill", "partial_fill"):
            events.append(
                _emit_fill(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=venue,
                )
            )
            events.append(
                _emit_position(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=venue,
                )
            )
        elif kind == "rejected":
            events.append(
                _emit_reject(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=venue,
                    reason=str(_event_field(source, "reason_code") or "UNKNOWN"),
                    reason_detail=_event_field(source, "reason_detail"),
                )
            )
        elif kind == "canceled":
            events.append(
                _emit_skip(
                    candidate_id=candidate_id,
                    source_event=source,
                    source_event_id=source_event_id,
                    stream_index=index,
                    venue=venue,
                    reason=str(_event_field(source, "reason_code") or "UNKNOWN"),
                    reason_detail=_event_field(source, "reason_detail"),
                )
            )
    # Deterministic ordering: (timestamp_utc, lifecycle_index, event_id)
    events.sort(
        key=lambda e: (
            e.timestamp_utc,
            _EVENT_TYPE_LIFECYCLE_INDEX.get(e.event_type, len(LEDGER_EVENT_TYPES)),
            e.event_id,
        )
    )
    return events


def _event_counts(events: Iterable[LedgerEvent]) -> dict[str, int]:
    counts: dict[str, int] = {etype: 0 for etype in LEDGER_EVENT_TYPES}
    for event in events:
        if event.event_type in counts:
            counts[event.event_type] += 1
    return counts


def build_ledger_payload(
    *,
    entries: list[tuple[str, list[LedgerEvent]]],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> dict[str, Any]:
    """Assemble the paper ledger sidecar payload.

    ``entries`` is a list of ``(candidate_id, events)`` tuples. The
    payload preserves deterministic ordering by ``candidate_id`` and
    stable event ordering within each candidate.
    """
    sorted_entries = sorted(entries, key=lambda item: item[0])
    per_candidate = []
    overall_counts: dict[str, int] = {etype: 0 for etype in LEDGER_EVENT_TYPES}
    for candidate_id, events in sorted_entries:
        candidate_counts = _event_counts(events)
        for etype, count in candidate_counts.items():
            overall_counts[etype] += count
        per_candidate.append({
            "candidate_id": candidate_id,
            "event_counts": candidate_counts,
            "events": [event.to_payload() for event in events],
        })
    return {
        "schema_version": PAPER_LEDGER_SCHEMA_VERSION,
        "paper_ledger_version": PAPER_LEDGER_VERSION,
        "paper_venues_version": PAPER_VENUES_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "event_types": list(LEDGER_EVENT_TYPES),
        "evidence_statuses": list(EVIDENCE_STATUSES),
        "overall_event_counts": overall_counts,
        "per_candidate": per_candidate,
    }


__all__ = [
    "EVIDENCE_STATUSES",
    "LEDGER_EVENT_TYPES",
    "LEDGER_REJECT_REASON_INSUFFICIENT_VENUE",
    "LedgerEvent",
    "PAPER_LEDGER_SCHEMA_VERSION",
    "PAPER_LEDGER_VERSION",
    "build_ledger_events_for_candidate",
    "build_ledger_payload",
]
