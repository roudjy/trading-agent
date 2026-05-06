"""PR-C — advisory suppression tests for reporting.intelligent_routing.

Pins the advisory framing — Correction 4:

* ``advisory_suppression_reason`` is set to ``"dead_zone"`` *iff* the
  upstream dead-zone status is ``"dead"`` AND the campaign coordinates
  match. Statuses ``alive``, ``weak``, ``unknown``,
  ``insufficient_data`` never trigger suppression.
* ``advisory_suppression_reason`` is set to ``"near_duplicate"`` for
  every member of a near-duplicate group EXCEPT the first by
  ``(spawned_at_utc, campaign_id)``. The first member always keeps
  ``None``. At-least-one survivor per group.
* Dead-zone takes precedence over near-duplicate when both would
  apply (the dead-zone signal is the louder advisory).
* The artifact still carries ``routing_effect = "advisory_only"`` and
  ``queue_ordering_effect = "none"`` after suppression is applied —
  pre/post snapshot of ``research/**`` shows zero changes.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Same closed list used by the PR-A import-safety test. Pre/post
#: snapshot proves a --write run does not mutate any frozen / no-touch
#: research artifact.
FROZEN_RESEARCH_PATHS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
    "research/campaigns/evidence/dead_zones_latest.v1.json",
    "research/campaigns/evidence/information_gain_latest.v1.json",
    "research/campaigns/evidence/viability_latest.v1.json",
    "research/campaigns/evidence/stop_conditions_latest.v1.json",
    "research/campaigns/evidence/evidence_ledger_latest.v1.json",
)


def _snapshot() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in FROZEN_RESEARCH_PATHS:
        p = REPO_ROOT / rel
        out[rel] = (
            hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        )
    return out


# ---------------------------------------------------------------------------
# derive_advisory_suppression_reason — pure helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        ("dead", "dead_zone"),
        ("alive", None),
        ("weak", None),
        ("unknown", None),
        ("insufficient_data", None),
    ],
)
def test_dead_zone_suppression_only_for_dead(status: str, expected: str | None) -> None:
    """v3.15.16.1: suppression on status==dead requires the lookup to
    have been exact_timeframe_match. This test pins the EXACT path
    (suppression fires); the coarse path is pinned separately below.
    """
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status=status,
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group=None,
        is_first_in_group=True,
    )
    assert out == expected


def test_near_duplicate_first_member_keeps_none() -> None:
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="alive",
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group="abc123",
        is_first_in_group=True,
    )
    assert out is None


def test_near_duplicate_non_first_member_is_suppressed() -> None:
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="alive",
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group="abc123",
        is_first_in_group=False,
    )
    assert out == "near_duplicate"


def test_dead_zone_takes_precedence_over_near_duplicate() -> None:
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="dead",
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group="abc123",
        is_first_in_group=False,
    )
    # Dead-zone wins.
    assert out == "dead_zone"


def test_no_group_no_suppression() -> None:
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="alive",
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group=None,
        is_first_in_group=True,
    )
    assert out is None


# ---------------------------------------------------------------------------
# v3.15.16.1 — coarse fallback NEVER triggers suppression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "precision",
    [
        # Per the v3.15.16.1 spec: only exact_timeframe_match may
        # trigger dead-zone suppression. Every other value MUST keep
        # the suppression at None even when status == dead.
        "coarse_unknown_timeframe_match",
        "no_match",
    ],
)
def test_dead_status_with_non_exact_lookup_does_not_suppress(precision: str) -> None:
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="dead",
        dead_zone_lookup_precision=precision,
        near_duplicate_group=None,
        is_first_in_group=True,
    )
    assert out is None


def test_coarse_dead_match_does_not_block_near_duplicate_suppression() -> None:
    """If the campaign is a non-first near-duplicate group member AND
    its dead-zone lookup is coarse, the near_duplicate suppression
    still fires (the coarse dead-zone match must not "shadow" the
    near-duplicate path; it just doesn't add its own
    dead_zone_suppression)."""
    out = ir.derive_advisory_suppression_reason(
        dead_zone_status="dead",
        dead_zone_lookup_precision="coarse_unknown_timeframe_match",
        near_duplicate_group="g1",
        is_first_in_group=False,
    )
    assert out == "near_duplicate"


# ---------------------------------------------------------------------------
# build_report — full-pipeline suppression behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _write_inputs(tmp_path: Path, queue: dict, registry: dict, dead_zones: dict, ig: dict) -> dict[str, Path]:
    paths = {
        "queue": tmp_path / "queue.json",
        "registry": tmp_path / "registry.json",
        "dead_zones": tmp_path / "dz.json",
        "information_gain": tmp_path / "ig.json",
    }
    paths["queue"].write_text(json.dumps(queue), encoding="utf-8")
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    paths["dead_zones"].write_text(json.dumps(dead_zones), encoding="utf-8")
    paths["information_gain"].write_text(json.dumps(ig), encoding="utf-8")
    return paths


def _build(tmp_path: Path, queue, registry, dead_zones, ig, now) -> ir.RoutingReport:
    paths = _write_inputs(tmp_path, queue, registry, dead_zones, ig)
    return ir.build_report(
        now_utc=now,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["information_gain"],
    )


def _campaign(cid: str, spawned: str, family: str, asset: str, tf: str, fp: str, preset: str = "preset_x") -> dict:
    return {
        "campaign_id": cid,
        "preset_name": preset,
        "strategy_family": family,
        "asset_class": asset,
        "extra": {"timeframe": tf},
        "input_artifact_fingerprint": fp,
        "spawned_at_utc": spawned,
    }


def test_dead_zone_suppression_in_full_report(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00", "priority_tier": 2},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00", "priority_tier": 2},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "fp1"),
        _campaign("c2", "2026-05-06T10:01:00+00:00", "rsi_extreme", "equities", "1d", "fp2"),
    ]}
    dead_zones = {"zones": [
        {"asset": "crypto", "timeframe": "4h", "strategy_family": "ema_crossover", "zone_status": "dead"},
        {"asset": "equities", "timeframe": "1d", "strategy_family": "rsi_extreme", "zone_status": "alive"},
    ]}
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    assert by_id["c1"].advisory_suppression_reason == "dead_zone"
    assert by_id["c2"].advisory_suppression_reason is None


@pytest.mark.parametrize("status", ["alive", "weak", "unknown", "insufficient_data"])
def test_no_dead_zone_suppression_for_non_dead_statuses(
    tmp_path: Path, fixed_now_utc: _dt.datetime, status: str,
) -> None:
    queue = {"queue": [{"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"}]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "fp1"),
    ]}
    dead_zones = {"zones": [
        {"asset": "crypto", "timeframe": "4h", "strategy_family": "ema_crossover", "zone_status": status},
    ]}
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    assert report.decisions[0].advisory_suppression_reason is None


def test_near_duplicate_group_first_member_survives(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """All non-first members of a near-duplicate group are suppressed,
    but at least the first member survives (Correction 6 risk #6)."""
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        {"campaign_id": "c3", "spawned_at_utc": "2026-05-06T10:02:00+00:00"},
    ]}
    registry = {"campaigns": [
        # All three share coords + fingerprint prefix → same group.
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234ff"),
        _campaign("c2", "2026-05-06T10:01:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234aa"),
        _campaign("c3", "2026-05-06T10:02:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234bb"),
    ]}
    # No dead zones in this fixture.
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # Earliest spawned wins.
    assert by_id["c1"].advisory_suppression_reason is None
    assert by_id["c2"].advisory_suppression_reason == "near_duplicate"
    assert by_id["c3"].advisory_suppression_reason == "near_duplicate"


def test_at_least_one_survivor_per_near_duplicate_group(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """For every group, at least one campaign keeps suppression=None."""
    queue = {"queue": [
        {"campaign_id": f"c{i}", "spawned_at_utc": f"2026-05-06T10:0{i}:00+00:00"}
        for i in range(1, 4)
    ]}
    registry = {"campaigns": [
        _campaign(f"c{i}", f"2026-05-06T10:0{i}:00+00:00", "ema_crossover", "crypto", "4h", f"abcd1234{i}")
        for i in range(1, 4)
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    by_group: dict[str, list[ir.RoutingDecision]] = {}
    for d in report.decisions:
        if d.near_duplicate_group is None:
            continue
        by_group.setdefault(d.near_duplicate_group, []).append(d)
    for gid, members in by_group.items():
        survivors = [
            m for m in members if m.advisory_suppression_reason != "near_duplicate"
        ]
        assert len(survivors) >= 1, f"group {gid} has no survivor: {members!r}"


def test_dead_zone_precedes_near_duplicate_in_report(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """When a campaign is both in a dead zone AND not the first member
    of its near-duplicate group, the suppression reason is dead_zone."""
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234"),
        _campaign("c2", "2026-05-06T10:01:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234"),
    ]}
    dead_zones = {"zones": [
        {"asset": "crypto", "timeframe": "4h", "strategy_family": "ema_crossover", "zone_status": "dead"},
    ]}
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # c1 is dead-zone; c2 is dead-zone (precedence over near-duplicate).
    assert by_id["c1"].advisory_suppression_reason == "dead_zone"
    assert by_id["c2"].advisory_suppression_reason == "dead_zone"


def test_summary_counters_match_suppression_reasons(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        {"campaign_id": "c3", "spawned_at_utc": "2026-05-06T10:02:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234"),
        _campaign("c2", "2026-05-06T10:01:00+00:00", "ema_crossover", "crypto", "4h", "abcd1234"),
        _campaign("c3", "2026-05-06T10:02:00+00:00", "rsi_extreme", "equities", "1d", "ffff"),
    ]}
    dead_zones = {"zones": [
        {"asset": "equities", "timeframe": "1d", "strategy_family": "rsi_extreme", "zone_status": "dead"},
    ]}
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    s = report.summary
    assert s.total == 3
    # c2 is near_duplicate (c1 is the survivor); c3 is dead_zone.
    assert s.advisory_suppressed_near_duplicate == 1
    assert s.advisory_suppressed_dead_zone == 1


# ---------------------------------------------------------------------------
# Framing pin: routing_effect / queue_ordering_effect remain after PR-C
# ---------------------------------------------------------------------------


def test_routing_effect_and_queue_ordering_effect_present(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "fp1"),
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["queue_ordering_effect"] == "none"


def test_pre_post_snapshot_of_research_paths_unchanged_across_build(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Calling build_report writes nothing under research/**.

    Targeted snapshot of a closed list per Critical-review item 1.
    """
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "fp1"),
    ]}
    before = _snapshot()
    _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    after = _snapshot()
    assert before == after
