"""PR-C — advisory priority + rank tests for reporting.intelligent_routing.

Pins:

* ``compute_advisory_priority_score`` is total-ordering: high IG novel
  > medium IG novel > medium IG saturated > low > suppressed.
* Suppressed campaigns receive ``SUPPRESSED_PRIORITY_SCORE`` (-1)
  unconditionally.
* ``advisory_rank`` is 1-indexed and assigned in
  ``(-priority, tie_break_key)`` order — stable tie-breaks by
  ``(spawned_at_utc, campaign_id)``.
* High-IG novel beats low-IG saturated.
* The artifact still carries ``queue_ordering_effect = "none"`` —
  ranking is annotation only.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


# ---------------------------------------------------------------------------
# compute_advisory_priority_score — pure helper
# ---------------------------------------------------------------------------


def test_priority_score_for_suppressed_is_minus_one() -> None:
    assert ir.compute_advisory_priority_score(
        advisory_suppression_reason="dead_zone",
        info_gain_bucket="high",
        orthogonality_bucket="novel",
    ) == ir.SUPPRESSED_PRIORITY_SCORE
    assert ir.compute_advisory_priority_score(
        advisory_suppression_reason="near_duplicate",
        info_gain_bucket="high",
        orthogonality_bucket="novel",
    ) == ir.SUPPRESSED_PRIORITY_SCORE
    assert ir.SUPPRESSED_PRIORITY_SCORE == -1


def test_priority_score_high_ig_novel_is_max() -> None:
    high_novel = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket="high",
        orthogonality_bucket="novel",
    )
    none_saturated = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket="none",
        orthogonality_bucket="saturated",
    )
    assert high_novel > none_saturated


def test_priority_score_ig_dominates_orthogonality() -> None:
    """An IG-bucket step always outranks any orthogonality difference."""
    medium_novel = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket="medium",
        orthogonality_bucket="novel",
    )
    high_saturated = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket="high",
        orthogonality_bucket="saturated",
    )
    # high beats medium even with worst orthogonality vs best.
    assert high_saturated > medium_novel


def test_priority_score_unknown_buckets_default_to_zero_weight() -> None:
    out = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket="bogus_bucket",
        orthogonality_bucket="another_bogus",
    )
    assert out == 0


@pytest.mark.parametrize("ig_bucket,ortho_bucket,expected", [
    ("none", "saturated", 0),
    ("none", "adjacent", 1),
    ("none", "novel", 2),
    ("low", "saturated", 10),
    ("low", "novel", 12),
    ("medium", "saturated", 20),
    ("medium", "novel", 22),
    ("high", "saturated", 30),
    ("high", "adjacent", 31),
    ("high", "novel", 32),
])
def test_priority_score_explicit_bucket_grid(
    ig_bucket: str, ortho_bucket: str, expected: int,
) -> None:
    out = ir.compute_advisory_priority_score(
        advisory_suppression_reason=None,
        info_gain_bucket=ig_bucket,
        orthogonality_bucket=ortho_bucket,
    )
    assert out == expected


# ---------------------------------------------------------------------------
# advisory_rank — total ordering + stable tie-breaks via build_report
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _campaign(cid: str, spawned: str, family: str, asset: str, tf: str, fp: str) -> dict:
    return {
        "campaign_id": cid,
        "preset_name": "preset_x",
        "strategy_family": family,
        "asset_class": asset,
        "extra": {"timeframe": tf},
        "input_artifact_fingerprint": fp,
        "spawned_at_utc": spawned,
    }


def _build(tmp_path: Path, queue, registry, dead_zones, ig, now) -> ir.RoutingReport:
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
    return ir.build_report(
        now_utc=now,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["information_gain"],
    )


def test_high_ig_novel_outranks_low_ig_saturated(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "low_sat", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "high_novel", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        # Three more saturated campaigns share coords with low_sat
        # (4 total) → each sees ≥3 priors → saturated.
        {"campaign_id": "extra1", "spawned_at_utc": "2026-05-06T10:02:00+00:00"},
        {"campaign_id": "extra2", "spawned_at_utc": "2026-05-06T10:03:00+00:00"},
        {"campaign_id": "extra3", "spawned_at_utc": "2026-05-06T10:04:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("low_sat", "2026-05-06T10:00:00+00:00", "f1", "a1", "t1", "fp_a"),
        _campaign("extra1", "2026-05-06T10:02:00+00:00", "f1", "a1", "t1", "fp_b"),
        _campaign("extra2", "2026-05-06T10:03:00+00:00", "f1", "a1", "t1", "fp_c"),
        _campaign("extra3", "2026-05-06T10:04:00+00:00", "f1", "a1", "t1", "fp_d"),
        _campaign("high_novel", "2026-05-06T10:01:00+00:00", "f2", "a2", "t2", "fp_z"),
    ]}
    # IG payload only carries one campaign; give "high_novel" a high score.
    ig = {"col_campaign_id": "high_novel", "information_gain": {"score": 0.9, "bucket": "high"}}
    report = _build(tmp_path, queue, registry, {"zones": []}, ig, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    assert by_id["high_novel"].orthogonality_bucket == "novel"
    assert by_id["high_novel"].info_gain_bucket == "high"
    # low_sat shares coords with extras → saturated.
    assert by_id["low_sat"].orthogonality_bucket == "saturated"
    assert by_id["high_novel"].advisory_priority_score > by_id["low_sat"].advisory_priority_score
    assert by_id["high_novel"].advisory_rank < by_id["low_sat"].advisory_rank


def test_advisory_rank_is_total_ordering_one_indexed(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        {"campaign_id": "c3", "spawned_at_utc": "2026-05-06T10:02:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "f1", "a1", "t1", "fp1"),
        _campaign("c2", "2026-05-06T10:01:00+00:00", "f2", "a2", "t2", "fp2"),
        _campaign("c3", "2026-05-06T10:02:00+00:00", "f3", "a3", "t3", "fp3"),
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    ranks = sorted(d.advisory_rank for d in report.decisions)
    assert ranks == [1, 2, 3]
    # All ranks distinct.
    assert len({d.advisory_rank for d in report.decisions}) == 3


def test_suppressed_campaigns_rank_below_non_suppressed(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "deadzone", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "alive", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("deadzone", "2026-05-06T10:00:00+00:00", "ema_crossover", "crypto", "4h", "fp1"),
        _campaign("alive", "2026-05-06T10:01:00+00:00", "rsi_extreme", "equities", "1d", "fp2"),
    ]}
    dead_zones = {"zones": [
        {"asset": "crypto", "timeframe": "4h", "strategy_family": "ema_crossover", "zone_status": "dead"},
        {"asset": "equities", "timeframe": "1d", "strategy_family": "rsi_extreme", "zone_status": "alive"},
    ]}
    report = _build(tmp_path, queue, registry, dead_zones, {}, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # alive ranks higher (lower number) than deadzone.
    assert by_id["alive"].advisory_rank < by_id["deadzone"].advisory_rank
    assert by_id["deadzone"].advisory_priority_score == ir.SUPPRESSED_PRIORITY_SCORE


def test_tie_break_is_stable_by_spawned_at_then_campaign_id(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Two campaigns with identical priority scores break ties on
    ``(spawned_at_utc, campaign_id)``."""
    # Two distinct coords → both novel + IG bucket none → identical scores.
    queue = {"queue": [
        # b before a alphabetically but later in time → time wins.
        {"campaign_id": "b1", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        {"campaign_id": "a1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("a1", "2026-05-06T10:00:00+00:00", "f1", "a1", "t1", "fpA"),
        _campaign("b1", "2026-05-06T10:01:00+00:00", "f2", "a2", "t2", "fpB"),
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # Same score (both novel, none IG).
    assert by_id["a1"].advisory_priority_score == by_id["b1"].advisory_priority_score
    # Earlier spawned_at_utc gets rank 1.
    assert by_id["a1"].advisory_rank == 1
    assert by_id["b1"].advisory_rank == 2


def test_decisions_list_sorted_by_advisory_rank_in_artifact(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        {"campaign_id": "c2", "spawned_at_utc": "2026-05-06T10:01:00+00:00"},
        {"campaign_id": "c3", "spawned_at_utc": "2026-05-06T10:02:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign(f"c{i}", f"2026-05-06T10:0{i-1}:00+00:00", f"f{i}", f"a{i}", f"t{i}", f"fp{i}")
        for i in range(1, 4)
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    ranks = [d.advisory_rank for d in report.decisions]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Framing pin still carried after priority/rank derivation
# ---------------------------------------------------------------------------


def test_queue_ordering_effect_remains_none_after_ranking(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    queue = {"queue": [
        {"campaign_id": "c1", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
    ]}
    registry = {"campaigns": [
        _campaign("c1", "2026-05-06T10:00:00+00:00", "f1", "a1", "t1", "fp1"),
    ]}
    report = _build(tmp_path, queue, registry, {"zones": []}, {}, fixed_now_utc)
    payload = report.to_payload()
    assert payload["queue_ordering_effect"] == "none"
    assert payload["routing_effect"] == "advisory_only"
