"""v3.15 unit tests: paper_ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from research.paper_ledger import (
    EVIDENCE_STATUSES,
    LEDGER_EVENT_TYPES,
    LEDGER_REJECT_REASON_INSUFFICIENT_VENUE,
    PAPER_LEDGER_SCHEMA_VERSION,
    PAPER_LEDGER_VERSION,
    LedgerEvent,
    build_ledger_events_for_candidate,
    build_ledger_payload,
)


@dataclass
class _FakeExecutionEvent:
    event_id: str
    kind: str
    asset: str
    side: str
    timestamp_utc: str
    sequence: int
    fold_index: int | None
    intended_price: float
    requested_size: float
    fill_price: float | None
    filled_size: float | None
    fee_amount: float | None
    slippage_bps: float | None
    reason_code: str | None
    reason_detail: str | None


def _full_fill(
    *,
    asset: str = "BTC/EUR",
    timestamp: str = "2024-05-01T00:00:00+00:00",
    sequence: int = 0,
) -> _FakeExecutionEvent:
    return _FakeExecutionEvent(
        event_id=f"{sequence}|{asset}|{timestamp}|full_fill",
        kind="full_fill",
        asset=asset,
        side="long",
        timestamp_utc=timestamp,
        sequence=sequence,
        fold_index=0,
        intended_price=50000.0,
        requested_size=1.0,
        fill_price=50010.0,
        filled_size=1.0,
        fee_amount=125.0,
        slippage_bps=2.0,
        reason_code=None,
        reason_detail=None,
    )


def _rejected() -> _FakeExecutionEvent:
    return _FakeExecutionEvent(
        event_id="1|BTC/EUR|2024-05-02T00:00:00+00:00|rejected",
        kind="rejected",
        asset="BTC/EUR",
        side="long",
        timestamp_utc="2024-05-02T00:00:00+00:00",
        sequence=1,
        fold_index=0,
        intended_price=50050.0,
        requested_size=1.0,
        fill_price=None,
        filled_size=None,
        fee_amount=None,
        slippage_bps=None,
        reason_code="INSUFFICIENT_CAPITAL",
        reason_detail="equity below min",
    )


def _canceled() -> _FakeExecutionEvent:
    return _FakeExecutionEvent(
        event_id="2|BTC/EUR|2024-05-03T00:00:00+00:00|canceled",
        kind="canceled",
        asset="BTC/EUR",
        side="long",
        timestamp_utc="2024-05-03T00:00:00+00:00",
        sequence=2,
        fold_index=0,
        intended_price=50100.0,
        requested_size=1.0,
        fill_price=None,
        filled_size=None,
        fee_amount=None,
        slippage_bps=None,
        reason_code="COOLDOWN_ACTIVE",
        reason_detail=None,
    )


def test_taxonomies_are_closed_sets_and_stable():
    assert LEDGER_EVENT_TYPES == (
        "signal", "order", "fill", "reject", "skip", "position",
    )
    assert EVIDENCE_STATUSES == (
        "reconstructed", "projected_minimal", "projected_insufficient",
    )
    assert PAPER_LEDGER_VERSION == "v0.1"
    assert PAPER_LEDGER_SCHEMA_VERSION == "1.0"
    assert LEDGER_REJECT_REASON_INSUFFICIENT_VENUE == "insufficient_venue_mapping"


def test_full_fill_emits_signal_order_fill_position_reconstructed():
    events = build_ledger_events_for_candidate(
        candidate_id="cand-1",
        asset_type="crypto",
        execution_events=[_full_fill()],
    )
    types = [e.event_type for e in events]
    assert types == ["signal", "order", "fill", "position"]
    # All venues tagged
    assert all(e.venue == "crypto_bitvavo" for e in events)
    # Evidence statuses: signal + position projected_minimal; order + fill reconstructed
    assert events[0].evidence_status == "projected_minimal"
    assert events[1].evidence_status == "reconstructed"
    assert events[2].evidence_status == "reconstructed"
    assert events[3].evidence_status == "projected_minimal"
    # Fill payload keeps engine fee/slippage and carries venue constants
    fill = events[2]
    assert fill.payload["engine_fee_amount"] == pytest.approx(125.0)
    assert fill.payload["engine_slippage_bps"] == pytest.approx(2.0)
    assert fill.payload["venue_fee_per_side"] is not None
    assert fill.payload["venue_slippage_bps"] is not None
    # Lineage points back at stream_index 0
    assert fill.lineage[0]["source"] == "oos_execution_events"
    assert fill.lineage[0]["stream_index"] == 0


def test_rejected_emits_signal_plus_reject_no_fill():
    events = build_ledger_events_for_candidate(
        candidate_id="cand-2",
        asset_type="crypto",
        execution_events=[_rejected()],
    )
    types = [e.event_type for e in events]
    assert types == ["reject", "signal"] or types == ["signal", "reject"]
    # Find the reject event
    reject = next(e for e in events if e.event_type == "reject")
    assert reject.payload["reason"] == "INSUFFICIENT_CAPITAL"
    assert reject.payload["reason_detail"] == "equity below min"
    assert reject.evidence_status == "reconstructed"


def test_canceled_emits_skip_not_reject():
    events = build_ledger_events_for_candidate(
        candidate_id="cand-3",
        asset_type="equity",
        execution_events=[_canceled()],
    )
    types = sorted([e.event_type for e in events])
    assert "skip" in types
    assert "reject" not in types
    assert all(e.venue == "equity_ibkr" for e in events)
    skip = next(e for e in events if e.event_type == "skip")
    assert skip.payload["reason"] == "COOLDOWN_ACTIVE"


def test_unknown_asset_type_triggers_insufficient_venue_mapping_reject():
    events = build_ledger_events_for_candidate(
        candidate_id="cand-4",
        asset_type="unknown",
        execution_events=[_full_fill()],
    )
    # For unmapped venues: only signal + reject(insufficient_venue_mapping)
    assert {e.event_type for e in events} == {"signal", "reject"}
    reject = next(e for e in events if e.event_type == "reject")
    assert reject.payload["reason"] == LEDGER_REJECT_REASON_INSUFFICIENT_VENUE
    assert reject.venue is None
    assert reject.payload["reason_detail"] == "asset_type='unknown'"


def test_deterministic_ordering_across_multiple_events():
    inputs = [_canceled(), _full_fill(), _rejected()]  # unordered timestamps
    events_a = build_ledger_events_for_candidate(
        candidate_id="cand-5",
        asset_type="crypto",
        execution_events=inputs,
    )
    events_b = build_ledger_events_for_candidate(
        candidate_id="cand-5",
        asset_type="crypto",
        execution_events=inputs,
    )
    # Byte-identical rebuild
    assert [e.to_payload() for e in events_a] == [e.to_payload() for e in events_b]
    # Ordering rule: (timestamp_utc, event_id) ascending
    timestamps = [e.timestamp_utc for e in events_a]
    assert timestamps == sorted(timestamps)


def test_empty_execution_events_yields_empty_ledger():
    assert build_ledger_events_for_candidate(
        candidate_id="cand-6",
        asset_type="crypto",
        execution_events=[],
    ) == []


def test_build_ledger_payload_aggregates_counts_and_pins_flags():
    events_c1 = build_ledger_events_for_candidate(
        candidate_id="c1",
        asset_type="crypto",
        execution_events=[_full_fill(), _rejected()],
    )
    events_c2 = build_ledger_events_for_candidate(
        candidate_id="c2",
        asset_type="equity",
        execution_events=[_canceled()],
    )
    payload = build_ledger_payload(
        entries=[("c2", events_c2), ("c1", events_c1)],  # deliberately swapped
        generated_at_utc="2026-04-24T10:00:00+00:00",
        run_id="run-xyz",
        git_revision="deadbeef",
    )
    assert payload["schema_version"] == PAPER_LEDGER_SCHEMA_VERSION
    assert payload["paper_ledger_version"] == PAPER_LEDGER_VERSION
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["live_eligible"] is False
    # Canonical candidate ordering
    assert [entry["candidate_id"] for entry in payload["per_candidate"]] == ["c1", "c2"]
    # Overall aggregated counts add up across candidates
    overall = payload["overall_event_counts"]
    assert overall["signal"] == 3
    assert overall["fill"] == 1
    assert overall["reject"] == 1
    assert overall["skip"] == 1
    assert overall["position"] == 1
    # Payload is JSON-serializable (no dataclass leakage)
    json.dumps(payload)
