"""Integration test for the v3.15.15.11 authority trace.

Synthesizes the falsification → catalog persistence →
campaign-state-transition flow with the trace sink configured. Verifies:

- All expected events land in the JSONL.
- Each event has a deterministic ``event_id`` and a stable
  ``evidence_hash``.
- The same logical sequence replays without producing duplicates.
- A stale catalog state (a falsified hypothesis still showing
  ``active_discovery``) is *detectable* — DOES NOT assert auto-correction.

Important non-assertions: this test does NOT trigger or verify any
catalog status mutation, falsification policy change, campaign policy
change, or promotion threshold change. The trace is observability only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.authority_trace import (
    AuthorityTraceSink,
    build_event,
    read_trace,
)
from research.strategy_hypothesis_catalog import (
    STRATEGY_HYPOTHESIS_CATALOG,
)


_T0 = datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


def _emit_synthetic_flow(
    sink: AuthorityTraceSink,
    *,
    run_id: str,
    hypothesis_id: str,
    candidate_id: str,
) -> list[bool]:
    """Emit a synthetic falsification → catalog → campaign sequence.

    Returns the list of ``emit`` results (one per event in order).
    """
    results: list[bool] = []
    # 1. Promotion classifies the candidate.
    results.append(
        sink.emit(
            build_event(
                transition_kind="promotion_classified",
                source_authority="promotion",
                target_authority="candidate_registry",
                ts_utc=_T0,
                run_id=run_id,
                candidate_id=candidate_id,
                evidence={"verdict": "candidate"},
            )
        )
    )
    # 2. Candidate registry sidecar is written.
    results.append(
        sink.emit(
            build_event(
                transition_kind="candidate_registry_written",
                source_authority="promotion",
                target_authority="candidate_registry",
                ts_utc=_T0 + timedelta(seconds=1),
                run_id=run_id,
                candidate_id=candidate_id,
                evidence={"path": "research/candidate_registry_latest.v1.json"},
            )
        )
    )
    # 3. Falsification gates emitted.
    results.append(
        sink.emit(
            build_event(
                transition_kind="falsification_payload_emitted",
                source_authority="falsification",
                target_authority="candidate_registry",
                ts_utc=_T0 + timedelta(seconds=2),
                run_id=run_id,
                candidate_id=candidate_id,
                evidence={"failed_gate_count": 1},
            )
        )
    )
    # 4. Catalog snapshot persisted.
    results.append(
        sink.emit(
            build_event(
                transition_kind="catalog_persisted",
                source_authority="catalog",
                target_authority="catalog",
                ts_utc=_T0 + timedelta(seconds=3),
                run_id=run_id,
                hypothesis_id=hypothesis_id,
                evidence={"path": "research/strategy_hypothesis_catalog_latest.v1.json"},
            )
        )
    )
    # 5. Campaign state transition (e.g. completed) recorded.
    results.append(
        sink.emit(
            build_event(
                transition_kind="campaign_state_transitioned",
                source_authority="campaign_registry",
                target_authority="campaign_registry",
                ts_utc=_T0 + timedelta(seconds=4),
                run_id=run_id,
                evidence={"from": "running", "to": "completed"},
            )
        )
    )
    return results


def test_full_flow_lands_in_jsonl(tmp_path: Path) -> None:
    trace_path = tmp_path / "authority_trace_latest.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path)
    results = _emit_synthetic_flow(
        sink,
        run_id="20260429T120000000000Z",
        hypothesis_id="trend_pullback_v1",
        candidate_id="cand-001",
    )
    assert results == [True, True, True, True, True]
    # All 5 events on disk in canonical sorted-key form.
    events = read_trace(trace_path)
    assert len(events) == 5
    expected_kinds = [
        "promotion_classified",
        "candidate_registry_written",
        "falsification_payload_emitted",
        "catalog_persisted",
        "campaign_state_transitioned",
    ]
    actual_kinds = [ev["transition_kind"] for ev in events]
    assert actual_kinds == expected_kinds
    # Every event has a unique event_id and a non-empty evidence_hash.
    ids = {ev["event_id"] for ev in events}
    assert len(ids) == 5
    for ev in events:
        assert isinstance(ev["evidence_hash"], str)
        assert len(ev["evidence_hash"]) == 64  # sha256 hex


def test_replaying_flow_is_idempotent(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path)
    args = {
        "run_id": "20260429T120000000000Z",
        "hypothesis_id": "trend_pullback_v1",
        "candidate_id": "cand-001",
    }
    first = _emit_synthetic_flow(sink, **args)
    assert all(first)
    # Replay the exact same flow; every event_id already exists → no
    # new lines written.
    second = _emit_synthetic_flow(sink, **args)
    assert second == [False, False, False, False, False]
    assert len(read_trace(trace_path)) == 5


def test_disabled_sink_emits_no_events_for_full_flow(tmp_path: Path) -> None:
    sink = AuthorityTraceSink(path=None)
    results = _emit_synthetic_flow(
        sink,
        run_id="20260429T120000000000Z",
        hypothesis_id="trend_pullback_v1",
        candidate_id="cand-001",
    )
    assert results == [False, False, False, False, False]
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Stale-authority detection (observability, not auto-correction)
# ---------------------------------------------------------------------------


def _detect_stale_active_discovery(
    trace_events: list[dict],
    catalog: tuple,
) -> list[dict]:
    """Pure detection helper. For each falsification_payload_emitted
    event tied to a hypothesis_id, check whether the catalog still
    carries that hypothesis as ``active_discovery``. Return the list
    of staleness records.

    This is observability only — it does NOT mutate the catalog.
    """
    by_id = {h.hypothesis_id: h for h in catalog}
    stale: list[dict] = []
    for ev in trace_events:
        if ev["transition_kind"] != "falsification_payload_emitted":
            continue
        hid = ev.get("hypothesis_id")
        if hid is None:
            continue
        hyp = by_id.get(hid)
        if hyp is None:
            continue
        if hyp.status == "active_discovery":
            stale.append(
                {
                    "hypothesis_id": hid,
                    "current_status": hyp.status,
                    "trace_event_id": ev["event_id"],
                }
            )
    return stale


def test_stale_authority_state_is_detectable_not_auto_corrected(
    tmp_path: Path,
) -> None:
    # Pick a real active_discovery hypothesis — must remain
    # active_discovery before AND after this test (no mutation).
    target = next(
        h for h in STRATEGY_HYPOTHESIS_CATALOG if h.status == "active_discovery"
    )
    pre_status = target.status

    trace_path = tmp_path / "trace.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path)
    # Synthesize a falsification event tagged with the real hypothesis
    # id. In a live system this would be one of many emissions; here
    # one is enough to exercise the detector.
    sink.emit(
        build_event(
            transition_kind="falsification_payload_emitted",
            source_authority="falsification",
            target_authority="candidate_registry",
            ts_utc=_T0,
            run_id="20260429T120000000000Z",
            hypothesis_id=target.hypothesis_id,
            candidate_id="cand-stale-1",
            evidence={"failed_gate_count": 3},
        )
    )

    events = read_trace(trace_path)
    stale = _detect_stale_active_discovery(events, STRATEGY_HYPOTHESIS_CATALOG)

    # Detection works: at least one staleness record surfaces.
    assert len(stale) >= 1
    assert any(s["hypothesis_id"] == target.hypothesis_id for s in stale)
    # Critical non-assertion: the catalog row was NOT mutated.
    post_status = next(
        h for h in STRATEGY_HYPOTHESIS_CATALOG if h.hypothesis_id == target.hypothesis_id
    ).status
    assert post_status == pre_status == "active_discovery"


# ---------------------------------------------------------------------------
# Replay-safety on a torn trace file
# ---------------------------------------------------------------------------


def test_torn_trace_is_replay_safe(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path)
    event = build_event(
        transition_kind="catalog_persisted",
        source_authority="catalog",
        target_authority="catalog",
        ts_utc=_T0,
        run_id="20260429T120000000000Z",
        hypothesis_id="trend_pullback_v1",
        evidence={"path": "research/strategy_hypothesis_catalog_latest.v1.json"},
    )
    sink.emit(event)
    # Simulate a torn append: write the event line again WITHOUT going
    # through emit() so the dedup-on-emit path is bypassed.
    with trace_path.open("a", encoding="utf-8", newline="\n") as h:
        h.write(json.dumps(event.to_payload(), sort_keys=True))
        h.write("\n")
    # read_trace must still return one event.
    out = read_trace(trace_path)
    assert len(out) == 1
    # Re-emit must still be a no-op (dedup picks it up).
    assert sink.emit(event) is False
