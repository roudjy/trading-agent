"""Tests for research.candidate_status_history (v3.12 append-only history)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research._sidecar_io import serialize_canonical
from research.candidate_lifecycle import ReservedStatusError
from research.candidate_status_history import (
    STATUS_HISTORY_SCHEMA_VERSION,
    build_event_id,
    build_history_payload,
    derive_events_from_run,
    load_existing_history,
    merge_history,
    write_history,
)


RUN_ID = "20260423T120000000000Z"
NOW = "2026-04-23T12:00:00+00:00"


def _v2_entry(
    candidate_id: str,
    lifecycle_status: str,
    observed: tuple[str, ...] = (),
) -> dict:
    return {
        "candidate_id": candidate_id,
        "lifecycle_status": lifecycle_status,
        "observed_reason_codes": list(observed),
    }


def test_build_event_id_is_deterministic_across_calls() -> None:
    a = build_event_id("cid-1", None, "exploratory", RUN_ID, "insufficient_trades")
    b = build_event_id("cid-1", None, "exploratory", RUN_ID, "insufficient_trades")
    assert a == b
    assert len(a) == 64  # sha256 hex digest


def test_build_event_id_changes_when_any_component_changes() -> None:
    base = build_event_id("cid-1", None, "candidate", RUN_ID, "")
    assert base != build_event_id("cid-2", None, "candidate", RUN_ID, "")
    assert base != build_event_id("cid-1", "exploratory", "candidate", RUN_ID, "")
    assert base != build_event_id("cid-1", None, "exploratory", RUN_ID, "")
    assert base != build_event_id("cid-1", None, "candidate", "different_run", "")
    assert base != build_event_id("cid-1", None, "candidate", RUN_ID, "other_reason")


def test_derive_events_rejects_reserved_status() -> None:
    entry = _v2_entry("cid-1", "paper_ready")
    with pytest.raises(ReservedStatusError):
        derive_events_from_run([entry], run_id=RUN_ID, now_utc=NOW)


def test_derive_events_produces_one_event_per_entry() -> None:
    entries = [
        _v2_entry("cid-1", "candidate", ()),
        _v2_entry("cid-2", "rejected", ("insufficient_trades",)),
        _v2_entry("cid-3", "exploratory", ("psr_below_threshold",)),
    ]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    assert len(events) == 3
    by_candidate = {e.candidate_id: e for e in events}
    assert by_candidate["cid-1"].to_status == "candidate"
    assert by_candidate["cid-2"].to_status == "rejected"
    assert by_candidate["cid-3"].to_status == "exploratory"
    # reason_code derived from first observed code
    assert by_candidate["cid-2"].reason_code == "insufficient_trades"
    assert by_candidate["cid-1"].reason_code is None


def test_merge_history_is_idempotent_across_reruns() -> None:
    entries = [_v2_entry("cid-1", "candidate")]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    merged_once = merge_history({}, events)
    # simulate a rerun: same inputs, same run_id -> same events
    events_rerun = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    merged_twice = merge_history(merged_once, events_rerun)
    assert merged_once == merged_twice
    assert len(merged_twice["cid-1"]) == 1


def test_merge_history_adds_new_events_from_a_different_run() -> None:
    entries = [_v2_entry("cid-1", "exploratory")]
    first = derive_events_from_run(entries, run_id="run-1", now_utc="2026-04-23T12:00:00+00:00")
    second = derive_events_from_run(entries, run_id="run-2", now_utc="2026-04-24T12:00:00+00:00")
    h = merge_history({}, first)
    h = merge_history(h, second)
    assert len(h["cid-1"]) == 2


def test_merge_history_sorts_events_within_candidate_bucket() -> None:
    entries = [_v2_entry("cid-1", "candidate")]
    # Events derived out of chronological order
    ev_late = derive_events_from_run(entries, run_id="rZZZ", now_utc="2026-05-01T00:00:00+00:00")
    ev_early = derive_events_from_run(entries, run_id="rAAA", now_utc="2026-01-01T00:00:00+00:00")
    h = merge_history({}, ev_late + ev_early)
    stamps = [ev["at_utc"] for ev in h["cid-1"]]
    assert stamps == sorted(stamps)


def test_merge_history_sorts_candidate_ids_alphabetically() -> None:
    entries = [
        _v2_entry("zzz", "candidate"),
        _v2_entry("aaa", "rejected"),
        _v2_entry("mmm", "exploratory"),
    ]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    h = merge_history({}, events)
    assert list(h.keys()) == ["aaa", "mmm", "zzz"]


def test_load_existing_history_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_existing_history(tmp_path / "absent.json") == {}


def test_write_history_uses_canonical_serialization(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    entries = [_v2_entry("cid-1", "candidate")]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    payload = build_history_payload(merge_history({}, events), generated_at_utc=NOW)
    write_history(path, payload)

    on_disk = path.read_bytes()
    expected = serialize_canonical(payload).encode("utf-8")
    assert on_disk == expected


def test_build_history_payload_pins_top_level_shape() -> None:
    payload = build_history_payload({}, generated_at_utc=NOW)
    assert payload["schema_version"] == STATUS_HISTORY_SCHEMA_VERSION == "1.0"
    assert payload["generated_at_utc"] == NOW
    assert payload["status_model_version"] == "v3.12.0"
    assert payload["history"] == {}


def test_rerun_on_identical_input_produces_byte_identical_artifact(tmp_path: Path) -> None:
    entries = [_v2_entry("cid-1", "candidate"), _v2_entry("cid-2", "rejected", ("insufficient_trades",))]
    events1 = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    payload1 = build_history_payload(merge_history({}, events1), generated_at_utc=NOW)

    events2 = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    # Load the first write as the "existing" history, then merge the
    # identical second batch; a well-behaved implementation must
    # produce a byte-identical artifact.
    existing_after_first = merge_history({}, events1)
    payload2 = build_history_payload(merge_history(existing_after_first, events2), generated_at_utc=NOW)

    assert serialize_canonical(payload1) == serialize_canonical(payload2)


def test_load_existing_history_parses_prior_write(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    entries = [_v2_entry("cid-1", "candidate")]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    payload = build_history_payload(merge_history({}, events), generated_at_utc=NOW)
    write_history(path, payload)

    loaded = load_existing_history(path)
    assert "history" in loaded
    assert "cid-1" in loaded["history"]


def test_merge_history_preserves_existing_events_not_in_new_batch() -> None:
    existing = {
        "cid-1": [
            {
                "event_id": build_event_id("cid-1", None, "exploratory", "old_run", ""),
                "candidate_id": "cid-1",
                "from_status": None,
                "to_status": "exploratory",
                "reason_code": None,
                "run_id": "old_run",
                "at_utc": "2020-01-01T00:00:00+00:00",
                "source_artifact": "research/candidate_registry_latest.v2.json",
            }
        ]
    }
    entries = [_v2_entry("cid-1", "candidate")]
    new_events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    merged = merge_history(existing, new_events)
    assert len(merged["cid-1"]) == 2


def test_derive_events_reason_code_uses_first_observed() -> None:
    entries = [_v2_entry("cid-1", "rejected", ("oos_sharpe_below_threshold", "psr_below_threshold"))]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    assert events[0].reason_code == "oos_sharpe_below_threshold"


def test_event_to_payload_contains_no_timestamps_beyond_at_utc() -> None:
    entries = [_v2_entry("cid-1", "candidate")]
    events = derive_events_from_run(entries, run_id=RUN_ID, now_utc=NOW)
    payload = events[0].to_payload()
    timestamp_fields = [k for k in payload if "utc" in k or "time" in k or "at_" in k]
    # only at_utc should qualify
    assert timestamp_fields == ["at_utc"]
