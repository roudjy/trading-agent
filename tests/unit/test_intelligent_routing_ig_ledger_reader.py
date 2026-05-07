"""v3.15.16.2 — Multi-campaign IG ledger reader tests.

Pins the operator-blessed contracts:

* Ledger path: ``research/campaign_evidence_ledger_latest.v1.jsonl``.
* Allowed event types: ``campaign_completed``, ``campaign_failed``.
* Mapping:
    meaningful_failure_confirmed   → 0.2 (low)
    duplicate_low_value_run        → 0.1 (low)
    uninformative_technical_failure→ 0.0 (none)
    unknown                        → 0.0 (none) + drift counter
* Aggregation: latest event per campaign with non-null
  ``meaningful_classification``; sort key is parsed ``at_utc``,
  tie-break on ``event_id``. Unordered files still produce a
  deterministic outcome.
* Tier resolution: latest_artifact > evidence_ledger > missing.
* Stdlib-only; no import of ``research.campaign_evidence_ledger``;
  no write under ``research/**``.
* Routing framing unchanged: ``routing_effect = "advisory_only"``,
  ``queue_ordering_effect = "none"``.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import json
import sys
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


# ---------------------------------------------------------------------------
# Closed-vocabulary pinning
# ---------------------------------------------------------------------------


def test_ledger_path_constant_uses_v1_jsonl_form() -> None:
    """The reader's ledger constant must be the canonical
    ``_latest.v1.jsonl`` form (matching campaign_launcher.py:146 +
    research/diagnostics/paths.py:169)."""
    rel = (
        ir.CAMPAIGN_EVIDENCE_LEDGER_PATH.resolve()
        .relative_to(ir.REPO_ROOT).as_posix()
    )
    assert rel == "research/campaign_evidence_ledger_latest.v1.jsonl"


def test_allowed_event_types_pinned() -> None:
    assert ir.LEDGER_ALLOWED_EVENT_TYPES == frozenset({
        "campaign_completed",
        "campaign_failed",
    })


def test_mapping_table_pinned() -> None:
    """Operator-blessed v3.15.16.2 mapping. Any drift here is a
    contract change requiring a new operator-approved PR."""
    assert ir.LEDGER_MEANINGFUL_CLASSIFICATION_TO_SCORE == {
        "meaningful_failure_confirmed": 0.2,
        "duplicate_low_value_run": 0.1,
        "uninformative_technical_failure": 0.0,
    }


def test_info_gain_source_constants_pinned() -> None:
    assert ir.INFO_GAIN_SOURCE_LATEST_ARTIFACT == "latest_artifact"
    assert ir.INFO_GAIN_SOURCE_EVIDENCE_LEDGER == "evidence_ledger"
    assert ir.INFO_GAIN_SOURCE_MISSING == "missing"
    assert ir.INFO_GAIN_SOURCE_VALUES == (
        "latest_artifact", "evidence_ledger", "missing",
    )


def test_info_gain_semantic_constant_pinned() -> None:
    assert ir.INFO_GAIN_SEMANTIC == "research_information_value"


def test_info_gain_projection_note_pinned() -> None:
    assert ir.INFO_GAIN_PROJECTION_NOTE_LEDGER == "ledger_simplified_projection"


# ---------------------------------------------------------------------------
# Reader does not import research.campaign_evidence_ledger
# ---------------------------------------------------------------------------


def test_reader_does_not_import_research_campaign_evidence_ledger() -> None:
    """The reader must be stdlib-only. Importing
    ``research.campaign_evidence_ledger`` would pull the project's
    heavy transitive deps (numpy/pandas/ta/ccxt) and fail on the VPS
    system Python. We assert the source file does not import that
    module either by-name or via the legacy alias path."""
    src = (
        Path(__file__).resolve().parent.parent.parent
        / "reporting" / "intelligent_routing.py"
    ).read_text(encoding="utf-8")
    import re
    forbidden = re.compile(
        r"^(?:from\s+research\.campaign_evidence_ledger"
        r"|import\s+research\.campaign_evidence_ledger)\b",
        flags=re.MULTILINE,
    )
    assert forbidden.search(src) is None


# ---------------------------------------------------------------------------
# JSONL parser semantics
# ---------------------------------------------------------------------------


def _make_event(
    *,
    campaign_id: str,
    event_type: str = "campaign_completed",
    meaningful_classification: str | None = "meaningful_failure_confirmed",
    outcome: str | None = "degenerate_no_survivors",
    reason_code: str | None = "degenerate_no_evaluable_pairs",
    at_utc: str = "2026-05-06T10:00:00.000000Z",
    event_id: str = "e0",
) -> dict:
    return {
        "event_id": event_id,
        "campaign_id": campaign_id,
        "parent_campaign_id": None,
        "lineage_root_campaign_id": campaign_id,
        "preset_name": "preset_x",
        "strategy_family": "ema",
        "asset_class": "crypto",
        "campaign_type": "hypothesis_exploration",
        "event_type": event_type,
        "reason_code": reason_code if reason_code is not None else "none",
        "outcome": outcome,
        "meaningful_classification": meaningful_classification,
        "run_id": "r1",
        "source_artifact": None,
        "at_utc": at_utc,
        "extra": {},
    }


def _write_ledger(tmp_path: Path, events: list[dict]) -> Path:
    p = tmp_path / "ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return p


def test_reader_returns_empty_for_missing_ledger(tmp_path: Path) -> None:
    out, stats = ir._index_information_gain_from_ledger(tmp_path / "nope.jsonl")
    assert out == {}
    assert stats.line_count == 0
    assert stats.parsed_line_count == 0
    assert stats.malformed_jsonl_lines == 0
    assert stats.truncated is False


def test_reader_returns_empty_for_empty_ledger(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text("", encoding="utf-8")
    out, stats = ir._index_information_gain_from_ledger(p)
    assert out == {}
    assert stats.line_count == 0


def test_reader_skips_malformed_jsonl_and_counts(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    valid_event = _make_event(campaign_id="c1")
    with p.open("w", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps(valid_event) + "\n")
        fh.write("not even close to json\n")
        fh.write("[1,2,3]\n")  # parses, but not a dict
    out, stats = ir._index_information_gain_from_ledger(p)
    assert "c1" in out
    # The single valid dict-shaped event yields one parsed entry.
    # The two non-JSON lines + one non-dict JSON line all count as
    # malformed_jsonl_lines.
    assert stats.malformed_jsonl_lines == 3
    assert stats.parsed_line_count == 1
    assert stats.line_count == 4


def test_reader_skips_null_meaningful_classification(tmp_path: Path) -> None:
    """campaign_spawned/leased/started events have null mc and must
    be excluded from per-campaign aggregation."""
    events = [
        _make_event(
            campaign_id="c1",
            event_type="campaign_spawned",
            meaningful_classification=None,
            outcome=None,
        ),
        _make_event(
            campaign_id="c1",
            event_type="campaign_completed",
            meaningful_classification="meaningful_failure_confirmed",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, _stats = ir._index_information_gain_from_ledger(p)
    assert "c1" in out
    assert out["c1"]["classification"] == "meaningful_failure_confirmed"


def test_reader_ignores_funnel_event_types(tmp_path: Path) -> None:
    """funnel_decision_emitted + funnel_technical_no_freeze must be
    ignored in v3.15.16.2 even when carrying mc fields."""
    events = [
        _make_event(
            campaign_id="c1",
            event_type="funnel_decision_emitted",
            meaningful_classification="meaningful_failure_confirmed",
        ),
        _make_event(
            campaign_id="c1",
            event_type="funnel_technical_no_freeze",
            meaningful_classification="meaningful_failure_confirmed",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, _stats = ir._index_information_gain_from_ledger(p)
    assert out == {}


def test_reader_picks_latest_at_utc_per_campaign(tmp_path: Path) -> None:
    """File order != at_utc order. Reader must compare at_utc
    explicitly and pick the newest."""
    events = [
        _make_event(
            campaign_id="c1",
            at_utc="2026-05-06T20:00:00.000000Z",
            event_id="late",
            meaningful_classification="meaningful_failure_confirmed",
        ),
        _make_event(
            campaign_id="c1",
            at_utc="2026-05-06T08:00:00.000000Z",
            event_id="early",
            meaningful_classification="duplicate_low_value_run",
        ),
    ]
    # Write in REVERSED order on disk to prove the reader doesn't
    # rely on file order.
    events_on_disk = list(reversed(events))
    p = _write_ledger(tmp_path, events_on_disk)
    out, _stats = ir._index_information_gain_from_ledger(p)
    # Latest at_utc wins regardless of file order.
    assert out["c1"]["at_utc"] == "2026-05-06T20:00:00.000000Z"
    assert out["c1"]["classification"] == "meaningful_failure_confirmed"


def test_reader_tie_breaks_on_event_id(tmp_path: Path) -> None:
    """Identical at_utc → smaller event_id wins (deterministic)."""
    events = [
        _make_event(
            campaign_id="c1",
            at_utc="2026-05-06T10:00:00.000000Z",
            event_id="zzz",
            meaningful_classification="meaningful_failure_confirmed",
        ),
        _make_event(
            campaign_id="c1",
            at_utc="2026-05-06T10:00:00.000000Z",
            event_id="aaa",
            meaningful_classification="duplicate_low_value_run",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, _stats = ir._index_information_gain_from_ledger(p)
    # Larger event_id ("zzz" > "aaa") wins per (at_utc, event_id) >
    assert out["c1"]["event_id"] == "zzz"


def test_reader_skips_malformed_at_utc(tmp_path: Path) -> None:
    events = [
        _make_event(
            campaign_id="c1",
            at_utc=None,  # missing
            meaningful_classification="meaningful_failure_confirmed",
        ),
        _make_event(
            campaign_id="c2",
            at_utc=12345,  # wrong type
            meaningful_classification="meaningful_failure_confirmed",
        ),
    ]
    # The reader treats non-string at_utc as "missing" → counted.
    p = _write_ledger(tmp_path, events)
    out, stats = ir._index_information_gain_from_ledger(p)
    # c1 has None at_utc → caught earlier (missing key check).
    # c2 has int at_utc → counted as malformed_at_utc.
    assert "c1" not in out
    assert "c2" not in out
    assert stats.malformed_at_utc_count >= 1


def test_reader_recognised_classification_score(tmp_path: Path) -> None:
    """The three blessed classifications map to the pinned scores."""
    events = [
        _make_event(
            campaign_id="cA",
            meaningful_classification="meaningful_failure_confirmed",
        ),
        _make_event(
            campaign_id="cB",
            meaningful_classification="duplicate_low_value_run",
        ),
        _make_event(
            campaign_id="cC",
            meaningful_classification="uninformative_technical_failure",
            event_type="campaign_failed",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, _stats = ir._index_information_gain_from_ledger(p)
    assert out["cA"]["score"] == 0.2
    assert out["cB"]["score"] == 0.1
    assert out["cC"]["score"] == 0.0


def test_reader_unrecognised_classification_yields_zero_and_drift(
    tmp_path: Path,
) -> None:
    """Unknown mc value → score 0.0 + drift counter increment."""
    events = [
        _make_event(
            campaign_id="cX",
            meaningful_classification="future_unforeseen_label",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, stats = ir._index_information_gain_from_ledger(p)
    assert out["cX"]["score"] == 0.0
    assert out["cX"]["classification"] == "future_unforeseen_label"
    assert stats.unrecognised_classification_count == 1


def test_reader_truncates_at_max_lines(tmp_path: Path) -> None:
    p = tmp_path / "huge.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for i in range(120):
            ev = _make_event(campaign_id=f"c{i}", event_id=f"e{i}")
            fh.write(json.dumps(ev) + "\n")
    out, stats = ir._index_information_gain_from_ledger(p, max_lines=50)
    assert stats.truncated is True
    assert stats.line_count == 50
    # First 50 events were processed.
    assert len(out) == 50


def test_reason_code_none_is_normalised_to_null(tmp_path: Path) -> None:
    """The producer uses literal 'none' as a placeholder for absent
    reason_code. The reader normalises it to Python None so the
    artifact's payload is clean."""
    events = [
        _make_event(
            campaign_id="c1",
            reason_code="none",
        ),
    ]
    p = _write_ledger(tmp_path, events)
    out, _stats = ir._index_information_gain_from_ledger(p)
    assert out["c1"]["reason_code"] is None


# ---------------------------------------------------------------------------
# build_report tier resolution
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 7, 0, 0, 0, tzinfo=_dt.timezone.utc)


def _campaign_record(cid: str, spawned: str) -> dict:
    return {
        "campaign_id": cid,
        "preset_name": "preset_x",
        "strategy_family": "ema_crossover",
        "asset_class": "crypto",
        "extra": {"timeframe": "4h"},
        "input_artifact_fingerprint": "fp_" + cid,
        "spawned_at_utc": spawned,
    }


def _write_inputs(
    tmp_path: Path,
    queue: dict, registry: dict, dead_zones: dict, ig: dict,
    ledger_events: list[dict] | None = None,
) -> dict[str, Path]:
    paths = {
        "queue": tmp_path / "q.json",
        "registry": tmp_path / "r.json",
        "dead_zones": tmp_path / "d.json",
        "ig": tmp_path / "i.json",
        "ledger": tmp_path / "ledger.jsonl",
    }
    paths["queue"].write_text(json.dumps(queue), encoding="utf-8")
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    paths["dead_zones"].write_text(json.dumps(dead_zones), encoding="utf-8")
    paths["ig"].write_text(json.dumps(ig), encoding="utf-8")
    if ledger_events is not None:
        with paths["ledger"].open("w", encoding="utf-8") as fh:
            for ev in ledger_events:
                fh.write(json.dumps(ev) + "\n")
    return paths


def _build(
    tmp_path: Path, queue, registry, dead_zones, ig, ledger_events, now,
):
    paths = _write_inputs(
        tmp_path, queue, registry, dead_zones, ig, ledger_events,
    )
    return ir.build_report(
        now_utc=now,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
        campaign_evidence_ledger_path=paths["ledger"],
    )


def test_tier1_latest_artifact_wins_for_its_campaign(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "2026-05-06T10:00:00+00:00")}}
    ig = {
        "schema_version": "1.0",
        "col_campaign_id": "c1",
        "preset_name": "preset_x",
        "information_gain": {"score": 0.85, "bucket": "high"},
    }
    ledger_events = [
        _make_event(
            campaign_id="c1",
            meaningful_classification="meaningful_failure_confirmed",
        ),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, ig, ledger_events, fixed_now_utc)
    decision = report.decisions[0]
    assert decision.info_gain_source == "latest_artifact"
    assert decision.info_gain_score == pytest.approx(0.85)
    assert decision.info_gain_bucket == "high"
    # Tier-1 wins → no projection_note attached even though the
    # ledger had data.
    assert decision.info_gain_projection_note is None
    # Tier-1 carries no terminal-event annotations.
    assert decision.info_gain_classification is None


def test_tier2_evidence_ledger_fills_other_campaigns(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T11:00:00+00:00"},
    ]}
    registry = {"campaigns": {
        "c1": _campaign_record("c1", "2026-05-06T10:00:00+00:00"),
        "c2": _campaign_record("c2", "2026-05-06T11:00:00+00:00"),
    }}
    ig = {  # Tier-1 covers only c1
        "col_campaign_id": "c1",
        "information_gain": {"score": 0.85, "bucket": "high"},
    }
    ledger_events = [
        _make_event(campaign_id="c1", meaningful_classification="duplicate_low_value_run"),
        _make_event(
            campaign_id="c2",
            meaningful_classification="meaningful_failure_confirmed",
            outcome="degenerate_no_survivors",
            reason_code="degenerate_no_evaluable_pairs",
            at_utc="2026-05-06T20:00:00.000000Z",
        ),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, ig, ledger_events, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # c1 → Tier-1 (canonical full-fidelity).
    assert by_id["c1"].info_gain_source == "latest_artifact"
    assert by_id["c1"].info_gain_score == pytest.approx(0.85)
    # c2 → Tier-2 (ledger projection).
    assert by_id["c2"].info_gain_source == "evidence_ledger"
    assert by_id["c2"].info_gain_score == pytest.approx(0.2)
    assert by_id["c2"].info_gain_bucket == "low"
    assert by_id["c2"].info_gain_classification == "meaningful_failure_confirmed"
    assert by_id["c2"].info_gain_outcome == "degenerate_no_survivors"
    assert by_id["c2"].info_gain_reason_code == "degenerate_no_evaluable_pairs"
    assert by_id["c2"].info_gain_latest_event_utc == "2026-05-06T20:00:00.000000Z"
    assert by_id["c2"].info_gain_observation_count == 1
    assert by_id["c2"].info_gain_projection_note == "ledger_simplified_projection"


def test_missing_source_yields_score_zero_bucket_none(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c_missing", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": {
        "c_missing": _campaign_record("c_missing", "2026-05-06T10:00:00+00:00"),
    }}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, [], fixed_now_utc)
    decision = report.decisions[0]
    assert decision.info_gain_source == "missing"
    assert decision.info_gain_score == 0.0
    assert decision.info_gain_bucket == "none"
    assert decision.info_gain_observation_count == 0
    assert decision.info_gain_classification is None
    assert decision.info_gain_outcome is None
    assert decision.info_gain_reason_code is None
    assert decision.info_gain_projection_note is None


def test_artifact_carries_info_gain_semantic_constant(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "2026-05-06T10:00:00+00:00")}}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, [], fixed_now_utc)
    payload = report.to_payload()
    assert payload["info_gain_semantic"] == "research_information_value"


def test_summary_includes_info_gain_source_distribution(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "cA", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "cB", "spawned_at_utc": "2026-05-06T11:00:00+00:00"},
        {"campaign_id": "cC", "spawned_at_utc": "2026-05-06T12:00:00+00:00"},
    ]}
    registry = {"campaigns": {
        "cA": _campaign_record("cA", "2026-05-06T10:00:00+00:00"),
        "cB": _campaign_record("cB", "2026-05-06T11:00:00+00:00"),
        "cC": _campaign_record("cC", "2026-05-06T12:00:00+00:00"),
    }}
    ig = {"col_campaign_id": "cA", "information_gain": {"score": 0.4}}
    ledger_events = [
        _make_event(campaign_id="cB", meaningful_classification="meaningful_failure_confirmed"),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, ig, ledger_events, fixed_now_utc)
    payload = report.to_payload()
    by_src = payload["summary"]["by_info_gain_source"]
    assert by_src == {"latest_artifact": 1, "evidence_ledger": 1, "missing": 1}


def test_summary_unrecognised_classification_count(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "2026-05-06T10:00:00+00:00")}}
    ledger_events = [
        _make_event(campaign_id="c1", meaningful_classification="future_label"),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, ledger_events, fixed_now_utc)
    assert report.summary.unrecognised_classification_count == 1


def test_routing_effect_unchanged_with_ledger_reader(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [{"campaign_id": "c1", "spawned_at_utc": "t"}]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "t")}}
    ledger_events = [
        _make_event(campaign_id="c1", meaningful_classification="meaningful_failure_confirmed"),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, ledger_events, fixed_now_utc)
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["queue_ordering_effect"] == "none"


def test_advisory_suppression_unchanged_by_ig_ledger_reader(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Enabling Tier-2 must not change which rows get suppressed.
    Suppression depends on dead_zone_status + lookup_precision +
    near_duplicate_group, none of which the IG reader touches."""
    queue = {"queue": [
        {"campaign_id": "alive", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "deadzone", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
    ]}
    registry = {"campaigns": {
        "alive": _campaign_record("alive", "2026-05-06T10:00:00+00:00"),
        "deadzone": _campaign_record("deadzone", "2026-05-06T10:01:00+00:00"),
    }}
    dead_zones = {"zones": [
        {
            "asset": "crypto", "timeframe": "4h",
            "strategy_family": "ema_crossover", "zone_status": "dead",
        },
    ]}
    ledger_events = [
        _make_event(campaign_id="alive", meaningful_classification="meaningful_failure_confirmed"),
        _make_event(campaign_id="deadzone", meaningful_classification="meaningful_failure_confirmed"),
    ]
    # Both campaigns share coords (crypto/4h/ema_crossover); dead-zone hits both.
    report = _build(tmp_path, queue, registry, dead_zones, {}, ledger_events, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # Both rows have dead-zone exact match → both get advisory_suppression_reason="dead_zone"
    # regardless of IG source.
    assert by_id["alive"].advisory_suppression_reason == "dead_zone"
    assert by_id["deadzone"].advisory_suppression_reason == "dead_zone"


def test_artifact_does_not_embed_raw_ledger_events(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Sanitisation: no raw event body fields under the decision."""
    queue = {"queue": [{"campaign_id": "c1", "spawned_at_utc": "t"}]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "t")}}
    ledger_events = [
        _make_event(
            campaign_id="c1",
            meaningful_classification="meaningful_failure_confirmed",
        ),
    ]
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, ledger_events, fixed_now_utc)
    payload = report.decisions[0].to_payload()
    forbidden = {
        "event", "raw_event", "event_id", "extra", "lineage_root_campaign_id",
        "parent_campaign_id", "source_artifact",
    }
    assert not (set(payload.keys()) & forbidden)


# ---------------------------------------------------------------------------
# Determinism + safety
# ---------------------------------------------------------------------------


def test_two_consecutive_builds_byte_identical_modulo_now(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Determinism: two consecutive ``build_report`` calls against
    the same on-disk inputs produce identical payloads modulo
    ``mtime_utc`` in provenance (which the FS sets, not the
    builder)."""
    queue = {"queue": [
        {"campaign_id": f"c{i}", "spawned_at_utc": f"2026-05-06T10:0{i}:00+00:00"}
        for i in range(3)
    ]}
    registry = {"campaigns": {
        f"c{i}": _campaign_record(f"c{i}", f"2026-05-06T10:0{i}:00+00:00")
        for i in range(3)
    }}
    ledger_events = [
        _make_event(
            campaign_id=f"c{i}",
            meaningful_classification="meaningful_failure_confirmed",
            at_utc=f"2026-05-06T11:0{i}:00.000000Z",
            event_id=f"e{i}",
        )
        for i in range(3)
    ]
    # Write inputs ONCE so mtime_utc is stable across the two
    # build_report invocations.
    paths = _write_inputs(
        tmp_path, queue, registry, {"zones": []}, {}, ledger_events,
    )
    kwargs = dict(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
        campaign_evidence_ledger_path=paths["ledger"],
    )
    a = ir.build_report(**kwargs)
    b = ir.build_report(**kwargs)
    assert a.to_payload() == b.to_payload()


def test_no_research_writes_with_ledger_reader_active(
    tmp_path: Path, fixed_now_utc: _dt.datetime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spy on builtins.open and Path.open during a build_report
    invocation that includes a ledger. Assert no path under
    research/ is opened in any write mode."""
    import builtins
    queue = {"queue": [{"campaign_id": "c1", "spawned_at_utc": "t"}]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "t")}}
    ledger_events = [
        _make_event(campaign_id="c1", meaningful_classification="meaningful_failure_confirmed"),
    ]
    forbidden_modes = {"w", "a", "x", "+"}
    bad: list[tuple[str, str]] = []
    real_open = builtins.open
    real_path_open = Path.open

    def _spy_b(file: object, mode: str = "r", *a, **kw):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            sf = str(file).replace("\\", "/")
            if "/research/" in sf or sf.startswith("research/"):
                bad.append((sf, m))
        return real_open(file, mode, *a, **kw)

    def _spy_p(self: Path, mode: str = "r", *a, **kw):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            sf = str(self).replace("\\", "/")
            if "/research/" in sf or sf.startswith("research/"):
                bad.append((sf, m))
        return real_path_open(self, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", _spy_b)
    monkeypatch.setattr(Path, "open", _spy_p)
    _build(tmp_path, queue, registry, {"zones": []}, {}, ledger_events, fixed_now_utc)
    assert bad == []


# ---------------------------------------------------------------------------
# Provenance — ledger entry has stream-stat fields
# ---------------------------------------------------------------------------


def test_provenance_ledger_entry_carries_stream_stats(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [{"campaign_id": "c1", "spawned_at_utc": "t"}]}
    registry = {"campaigns": {"c1": _campaign_record("c1", "t")}}
    ledger_events = [
        _make_event(campaign_id="c1", meaningful_classification="meaningful_failure_confirmed"),
        # malformed line will be added below by directly writing
    ]
    paths = _write_inputs(
        tmp_path, queue, registry, {"zones": []}, {}, ledger_events,
    )
    # Inject a malformed line.
    with paths["ledger"].open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
        campaign_evidence_ledger_path=paths["ledger"],
    )
    payload = report.to_payload()
    # Find the ledger provenance entry by its stream-stat keys.
    ledger_entries = [
        e for e in payload["provenance"].values()
        if "malformed_jsonl_lines" in e
    ]
    assert len(ledger_entries) == 1
    entry = ledger_entries[0]
    assert entry["status"] == "present"
    assert entry["line_count"] == 2
    assert entry["parsed_line_count"] == 1
    assert entry["malformed_jsonl_lines"] == 1
    assert entry["truncated"] is False
