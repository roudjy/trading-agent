"""v3.15.16.1 — dead-zone coarse-lookup annotation tests.

Pins (operator hard requirements from the v3.15.16.1 plan):

* The dead-zone artifact lookup is a 2-tier resolution:
  1. exact ``(asset_class, timeframe, family)`` match
     → ``DEAD_ZONE_LOOKUP_EXACT``
  2. coarse ``(asset_class, "unknown", family)`` match
     → ``DEAD_ZONE_LOOKUP_COARSE``
  3. neither → ``DEAD_ZONE_LOOKUP_NO_MATCH``
* ``RoutingDecision.dead_zone_lookup_precision`` carries one of
  ``DEAD_ZONE_LOOKUP_PRECISION_VALUES``.
* Coarse matches MUST NOT trigger ``advisory_suppression_reason``,
  MUST NOT alter ``advisory_priority_score``, MUST NOT alter
  ``advisory_rank``.
* Exact matches preserve the existing advisory dead-zone behavior.
* The artifact still carries
  ``routing_effect = "advisory_only"`` and
  ``queue_ordering_effect = "none"``.
* Missing / malformed dead-zone artifacts degrade safely.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


# ---------------------------------------------------------------------------
# Closed vocabulary pin
# ---------------------------------------------------------------------------


def test_dead_zone_lookup_precision_values_pinned() -> None:
    assert ir.DEAD_ZONE_LOOKUP_EXACT == "exact_timeframe_match"
    assert ir.DEAD_ZONE_LOOKUP_COARSE == "coarse_unknown_timeframe_match"
    assert ir.DEAD_ZONE_LOOKUP_NO_MATCH == "no_match"
    assert ir.DEAD_ZONE_LOOKUP_PRECISION_VALUES == (
        "exact_timeframe_match",
        "coarse_unknown_timeframe_match",
        "no_match",
    )


# ---------------------------------------------------------------------------
# classify_dead_zone_status — three-tier resolution
# ---------------------------------------------------------------------------


def _coords(family: str, asset: str, timeframe: str) -> ir.BehaviorCoordinates:
    return ir.derive_behavior_coordinates(
        strategy_family=family, asset_class=asset, timeframe=timeframe,
    )


def test_classify_returns_exact_match_when_timeframed_key_present() -> None:
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "4h", "ema_crossover"): "dead",
    }
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.classify_dead_zone_status(coords, index) == (
        "dead", "exact_timeframe_match",
    )


def test_classify_returns_coarse_when_only_unknown_timeframe_key_present() -> None:
    """Mirrors the documented upstream form: zones keyed on
    (asset, "unknown", family) per
    research/dead_zone_detection.py:21-24."""
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "unknown", "ema_crossover"): "dead",
    }
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.classify_dead_zone_status(coords, index) == (
        "dead", "coarse_unknown_timeframe_match",
    )


def test_classify_prefers_exact_when_both_keys_present() -> None:
    """If the artifact has both an exact and a coarse key for the
    same (asset, family), the exact one wins. This is important so
    a future v4-enriched artifact doesn't silently fall back to the
    coarse form."""
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "4h", "ema_crossover"): "alive",
        ("crypto", "unknown", "ema_crossover"): "dead",
    }
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.classify_dead_zone_status(coords, index) == (
        "alive", "exact_timeframe_match",
    )


def test_classify_returns_no_match_when_neither_form_present() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.classify_dead_zone_status(coords, {}) == (
        "unknown", "no_match",
    )


def test_classify_with_unknown_timeframe_coords_does_not_double_match() -> None:
    """If the campaign coords *themselves* have timeframe="unknown",
    the exact lookup already matches the upstream's coarse form;
    the helper must not also report 'coarse_unknown_timeframe_match'
    in that case (that would be ambiguous)."""
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "unknown", "ema_crossover"): "dead",
    }
    coords = _coords("ema_crossover", "crypto", "unknown")
    status, precision = ir.classify_dead_zone_status(coords, index)
    assert status == "dead"
    # The coords have timeframe=unknown so the lookup IS exact for
    # those coords (no fallback needed).
    assert precision == "exact_timeframe_match"


def test_classify_coarse_with_bogus_status_normalises_to_unknown() -> None:
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "unknown", "ema_crossover"): "DEFINITELY_NOT_REAL",
    }
    coords = _coords("ema_crossover", "crypto", "4h")
    status, precision = ir.classify_dead_zone_status(coords, index)
    assert status == "unknown"
    assert precision == "coarse_unknown_timeframe_match"


# ---------------------------------------------------------------------------
# build_report integration — coarse match is observability metadata only
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _campaign_record(cid: str, spawned: str, family: str, asset: str, tf: str) -> dict:
    return {
        "campaign_id": cid,
        "preset_name": "preset_x",
        "strategy_family": family,
        "asset_class": asset,
        "extra": {"timeframe": tf},
        "input_artifact_fingerprint": "fp_" + cid,
        "spawned_at_utc": spawned,
    }


def _write_inputs(
    tmp_path: Path,
    queue: dict, registry: dict, dead_zones: dict, ig: dict,
) -> dict[str, Path]:
    paths = {
        "queue": tmp_path / "q.json",
        "registry": tmp_path / "r.json",
        "dead_zones": tmp_path / "d.json",
        "ig": tmp_path / "i.json",
    }
    paths["queue"].write_text(json.dumps(queue), encoding="utf-8")
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    paths["dead_zones"].write_text(json.dumps(dead_zones), encoding="utf-8")
    paths["ig"].write_text(json.dumps(ig), encoding="utf-8")
    return paths


def _build(
    tmp_path: Path, queue, registry, dead_zones, ig, now,
) -> ir.RoutingReport:
    paths = _write_inputs(tmp_path, queue, registry, dead_zones, ig)
    return ir.build_report(
        now_utc=now,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
    )


def test_coarse_dead_match_populates_status_but_not_suppression(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """A campaign whose (asset, family) matches a coarse
    timeframe="unknown" zone marked "dead" gets the status surfaced
    AND the precision label, but its
    advisory_suppression_reason stays None."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    dead_zones = {
        "zones": [
            {
                "asset": "crypto",
                "timeframe": "unknown",  # documented upstream form
                "strategy_family": "ema_crossover",
                "zone_status": "dead",
            },
        ],
    }
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    decision = report.decisions[0]
    assert decision.dead_zone_status == "dead"
    assert decision.dead_zone_lookup_precision == "coarse_unknown_timeframe_match"
    assert decision.advisory_suppression_reason is None
    # Summary suppression counter is unchanged by the coarse match.
    assert report.summary.advisory_suppressed_dead_zone == 0


def test_exact_dead_match_still_triggers_suppression(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """When an exact (asset, timeframe, family) zone is marked dead,
    the existing advisory dead-zone suppression behaviour is
    preserved."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    dead_zones = {
        "zones": [
            {
                "asset": "crypto",
                "timeframe": "4h",  # exact match
                "strategy_family": "ema_crossover",
                "zone_status": "dead",
            },
        ],
    }
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    decision = report.decisions[0]
    assert decision.dead_zone_status == "dead"
    assert decision.dead_zone_lookup_precision == "exact_timeframe_match"
    assert decision.advisory_suppression_reason == "dead_zone"
    assert report.summary.advisory_suppressed_dead_zone == 1


def test_coarse_match_does_not_change_priority_or_rank_vs_no_match(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Same campaign coords + same suppression status (None) →
    advisory_priority_score and advisory_rank are identical
    regardless of whether the coarse fallback hit. The coarse
    match's only effect is on the metadata fields
    (dead_zone_status + dead_zone_lookup_precision)."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    coarse_zones = {
        "zones": [
            {
                "asset": "crypto",
                "timeframe": "unknown",
                "strategy_family": "ema_crossover",
                "zone_status": "dead",
            },
        ],
    }
    no_zones = {"zones": []}

    coarse_report = _build(tmp_path, queue, registry, coarse_zones, {}, fixed_now_utc)
    no_match_report = _build(tmp_path, queue, registry, no_zones, {}, fixed_now_utc)

    coarse_d = coarse_report.decisions[0]
    none_d = no_match_report.decisions[0]
    assert coarse_d.advisory_priority_score == none_d.advisory_priority_score
    assert coarse_d.advisory_rank == none_d.advisory_rank
    assert coarse_d.advisory_suppression_reason == none_d.advisory_suppression_reason
    # The metadata fields differ — that's the entire point.
    assert coarse_d.dead_zone_status == "dead"
    assert none_d.dead_zone_status == "unknown"
    assert coarse_d.dead_zone_lookup_precision == "coarse_unknown_timeframe_match"
    assert none_d.dead_zone_lookup_precision == "no_match"


def test_coarse_alive_match_is_distinguishable_from_exact_alive(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """An alive zone reached via coarse fallback must report
    coarse_unknown_timeframe_match (not exact_timeframe_match) so
    operators can distinguish the two."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "rsi_extreme", "equity", "1d",
            ),
        },
    }
    dead_zones = {
        "zones": [
            {
                "asset": "equity",
                "timeframe": "unknown",
                "strategy_family": "rsi_extreme",
                "zone_status": "alive",
            },
        ],
    }
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    decision = report.decisions[0]
    assert decision.dead_zone_status == "alive"
    assert decision.dead_zone_lookup_precision == "coarse_unknown_timeframe_match"


def test_no_zone_artifact_yields_no_match_precision(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    decision = report.decisions[0]
    assert decision.dead_zone_status == "unknown"
    assert decision.dead_zone_lookup_precision == "no_match"


def test_malformed_dead_zone_artifact_degrades_to_no_match(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """A malformed dead-zone payload must not crash the report; every
    row gets dead_zone_lookup_precision='no_match'."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    paths = {
        "queue": tmp_path / "q.json",
        "registry": tmp_path / "r.json",
        "dead_zones": tmp_path / "d.json",
        "ig": tmp_path / "i.json",
    }
    paths["queue"].write_text(json.dumps(queue), encoding="utf-8")
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    paths["dead_zones"].write_text("not json", encoding="utf-8")
    paths["ig"].write_text(json.dumps({}), encoding="utf-8")
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
    )
    assert report.decisions[0].dead_zone_lookup_precision == "no_match"


def test_artifact_still_carries_advisory_framing_with_coarse_match(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Belt-and-braces: even when coarse fallback fires for a 'dead'
    coarse zone, the artifact still carries
    routing_effect=advisory_only and queue_ordering_effect=none."""
    queue = {"queue": [{"campaign_id": "col-1", "spawned_at_utc": "t"}]}
    registry = {
        "campaigns": {
            "col-1": _campaign_record(
                "col-1", "t", "ema_crossover", "crypto", "4h",
            ),
        },
    }
    dead_zones = {
        "zones": [
            {
                "asset": "crypto",
                "timeframe": "unknown",
                "strategy_family": "ema_crossover",
                "zone_status": "dead",
            },
        ],
    }
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["queue_ordering_effect"] == "none"
    assert payload["decisions"][0]["dead_zone_lookup_precision"] == (
        "coarse_unknown_timeframe_match"
    )
