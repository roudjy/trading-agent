"""PR-A — pure data model + helper tests for reporting.intelligent_routing.

v3.15.16 advisory release. Verifies pure-function behavior only:

* Fields and constants follow the advisory framing (Correction 3-5).
* Behavior coordinates are provisional, not a new taxonomy
  (Correction 7).
* IG buckets agree with research.information_gain on a swept score.
* Dead-zone classification only returns the closed taxonomy.
* Orthogonality bucket boundaries are exactly novel/adjacent/saturated.
* Near-duplicate grouping is deterministic and only reads existing
  fingerprints.
"""

from __future__ import annotations

import hashlib

import pytest

from reporting import intelligent_routing as ir
from research import information_gain as upstream_ig


# ---------------------------------------------------------------------------
# Schema / constants pinning (Corrections 3, 4, 5)
# ---------------------------------------------------------------------------


def test_schema_version_pinned() -> None:
    assert ir.SCHEMA_VERSION == "1.0"
    assert ir.MODULE_VERSION == "v3.15.16"
    assert ir.REPORT_KIND == "intelligent_routing"


def test_advisory_framing_constants_pinned() -> None:
    """Correction 3 / 4 / 5: framing strings must be exact."""
    assert ir.ROUTING_EFFECT_ADVISORY_ONLY == "advisory_only"
    assert ir.QUEUE_ORDERING_EFFECT_NONE == "none"


def test_advisory_suppression_reasons_closed() -> None:
    """Only ``dead_zone`` and ``near_duplicate`` are valid reasons."""
    assert ir.SUPPRESSION_DEAD_ZONE == "dead_zone"
    assert ir.SUPPRESSION_NEAR_DUPLICATE == "near_duplicate"
    assert ir.ADVISORY_SUPPRESSION_REASONS == (
        "dead_zone",
        "near_duplicate",
    )


def test_dead_zone_taxonomy_closed() -> None:
    assert ir.DEAD_ZONE_STATUSES == (
        "insufficient_data",
        "unknown",
        "alive",
        "weak",
        "dead",
    )
    # Only ``dead`` may trigger advisory suppression.
    never = ir.NEVER_SUPPRESS_DEAD_ZONE_STATUSES
    assert "dead" not in never
    assert never == frozenset(
        {"insufficient_data", "unknown", "alive", "weak"}
    )


def test_orthogonality_bucket_taxonomy_closed() -> None:
    assert ir.ORTHOGONALITY_BUCKETS == (
        "novel",
        "adjacent",
        "saturated",
    )


def test_info_gain_buckets_closed() -> None:
    assert ir.INFO_GAIN_BUCKETS == ("none", "low", "medium", "high")


# ---------------------------------------------------------------------------
# derive_behavior_coordinates (Correction 7 — provisional, not taxonomy)
# ---------------------------------------------------------------------------


def test_behavior_coordinates_provisional_flag_always_true() -> None:
    coords = ir.derive_behavior_coordinates(
        strategy_family="ema_crossover",
        asset_class="crypto",
        timeframe="4h",
    )
    assert coords.provisional is True
    payload = coords.to_payload()
    assert payload["provisional"] is True


def test_behavior_coordinates_round_trip() -> None:
    coords = ir.derive_behavior_coordinates(
        strategy_family="rsi_extreme",
        asset_class="equities",
        timeframe="1d",
    )
    assert coords.family == "rsi_extreme"
    assert coords.asset_class == "equities"
    assert coords.timeframe == "1d"
    assert coords.as_tuple() == ("rsi_extreme", "equities", "1d")


@pytest.mark.parametrize(
    "field",
    [
        {"strategy_family": None},
        {"asset_class": None},
        {"timeframe": None},
        {"strategy_family": "  "},
        {"asset_class": ""},
        {"timeframe": "\t"},
    ],
)
def test_behavior_coordinates_missing_inputs_collapse_to_unknown(
    field: dict[str, object],
) -> None:
    coords = ir.derive_behavior_coordinates(**field)
    assert ir.UNKNOWN_COORDINATE == "unknown"
    payload = coords.to_payload()
    if "strategy_family" in field:
        assert payload["family"] == "unknown"
    if "asset_class" in field:
        assert payload["asset_class"] == "unknown"
    if "timeframe" in field:
        assert payload["timeframe"] == "unknown"


def test_behavior_coordinates_no_args_yields_unknowns() -> None:
    coords = ir.derive_behavior_coordinates()
    assert coords.family == "unknown"
    assert coords.asset_class == "unknown"
    assert coords.timeframe == "unknown"
    assert coords.provisional is True


def test_behavior_coordinates_strips_whitespace() -> None:
    coords = ir.derive_behavior_coordinates(
        strategy_family="  ema_crossover  ",
        asset_class=" crypto",
        timeframe="4h ",
    )
    assert coords.family == "ema_crossover"
    assert coords.asset_class == "crypto"
    assert coords.timeframe == "4h"


# ---------------------------------------------------------------------------
# bucket_info_gain — agrees with research.information_gain thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (-0.1, "none"),
        (0.0, "none"),
        (0.0001, "low"),
        (0.2999, "low"),
        (0.30, "medium"),
        (0.5, "medium"),
        (0.6999, "medium"),
        (0.70, "high"),
        (0.99, "high"),
        (1.0, "high"),
    ],
)
def test_bucket_info_gain_thresholds(score: float, expected: str) -> None:
    assert ir.bucket_info_gain(score) == expected


@pytest.mark.parametrize(
    "value",
    [None, "abc", float("nan"), object()],
)
def test_bucket_info_gain_garbage_collapses_to_none(value: object) -> None:
    assert ir.bucket_info_gain(value) == "none"


def test_bucket_info_gain_matches_information_gain_module() -> None:
    """Cross-check buckets agree with the upstream module on a swept
    score grid. If thresholds drift, this test fails loudly."""
    grid = [round(0.05 * i, 2) for i in range(0, 21)]  # 0.0 .. 1.0
    for score in grid:
        upstream_bucket = upstream_ig._bucket_for(score)
        assert ir.bucket_info_gain(score) == upstream_bucket, (
            f"divergence at score={score}: ir={ir.bucket_info_gain(score)} "
            f"upstream={upstream_bucket}"
        )


# ---------------------------------------------------------------------------
# classify_dead_zone_status
# ---------------------------------------------------------------------------


def _coords(family: str, asset: str, timeframe: str) -> ir.BehaviorCoordinates:
    return ir.derive_behavior_coordinates(
        strategy_family=family, asset_class=asset, timeframe=timeframe,
    )


def test_classify_dead_zone_status_lookup_hits() -> None:
    # Index keyed on (asset, timeframe, family) — same key the upstream
    # dead-zone artifact uses. v3.15.16.1: the helper returns a
    # 2-tuple (status, lookup_precision).
    index: dict[tuple[str, str, str], str] = {
        ("crypto", "4h", "ema_crossover"): "dead",
        ("equities", "1d", "rsi_extreme"): "alive",
    }
    coords1 = _coords("ema_crossover", "crypto", "4h")
    coords2 = _coords("rsi_extreme", "equities", "1d")
    assert ir.classify_dead_zone_status(coords1, index) == (
        "dead", "exact_timeframe_match",
    )
    assert ir.classify_dead_zone_status(coords2, index) == (
        "alive", "exact_timeframe_match",
    )


def test_classify_dead_zone_status_missing_collapses_to_unknown() -> None:
    coords = _coords("does_not_exist", "crypto", "4h")
    assert ir.classify_dead_zone_status(coords, {}) == (
        "unknown", "no_match",
    )


def test_classify_dead_zone_status_only_returns_closed_taxonomy() -> None:
    bogus_index: dict[tuple[str, str, str], str] = {
        ("crypto", "4h", "ema_crossover"): "DEFINITELY_NOT_A_REAL_STATUS",
    }
    coords = _coords("ema_crossover", "crypto", "4h")
    status, precision = ir.classify_dead_zone_status(coords, bogus_index)
    assert status in ir.DEAD_ZONE_STATUSES
    assert status == "unknown"
    # Bogus statuses still register the lookup as exact (the key was
    # present in the artifact); only the status itself is normalised.
    assert precision == "exact_timeframe_match"


# ---------------------------------------------------------------------------
# compute_orthogonality_bucket — exact boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prior_count,expected",
    [
        (0, "novel"),
        (1, "adjacent"),
        (2, "adjacent"),
        (3, "saturated"),
        (10, "saturated"),
    ],
)
def test_orthogonality_bucket_boundaries(
    prior_count: int, expected: str,
) -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    counts = {coords.as_tuple(): prior_count}
    assert ir.compute_orthogonality_bucket(coords, counts) == expected


def test_orthogonality_bucket_missing_coordinate_is_novel() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.compute_orthogonality_bucket(coords, {}) == "novel"


# ---------------------------------------------------------------------------
# compute_near_duplicate_group — deterministic, reads only fingerprint
# ---------------------------------------------------------------------------


def test_near_duplicate_group_none_for_missing_fingerprint() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    assert ir.compute_near_duplicate_group(coords, None) is None
    assert ir.compute_near_duplicate_group(coords, "") is None
    assert ir.compute_near_duplicate_group(coords, "   ") is None


def test_near_duplicate_group_deterministic() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    a = ir.compute_near_duplicate_group(coords, "abcd1234deadbeef")
    b = ir.compute_near_duplicate_group(coords, "abcd1234deadbeef")
    assert a == b
    assert a is not None
    assert len(a) == ir.NEAR_DUPLICATE_GROUP_HASH_LEN
    assert a == a.lower()
    int(a, 16)


def test_near_duplicate_group_uses_only_first_8_hex_of_fingerprint() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    short = "abcd1234"
    long_with_same_prefix = "abcd1234ffffffff"
    assert (
        ir.compute_near_duplicate_group(coords, short)
        == ir.compute_near_duplicate_group(coords, long_with_same_prefix)
    )


def test_near_duplicate_group_distinct_for_different_coordinates() -> None:
    fp = "abcd1234"
    a = ir.compute_near_duplicate_group(
        _coords("ema_crossover", "crypto", "4h"), fp,
    )
    b = ir.compute_near_duplicate_group(
        _coords("rsi_extreme", "crypto", "4h"), fp,
    )
    assert a != b


def test_near_duplicate_group_uses_sha256() -> None:
    """Verify the documented hash construction explicitly."""
    coords = _coords("ema_crossover", "crypto", "4h")
    fp = "abcd1234"
    parts = sorted(["ema_crossover", "crypto", "4h", "abcd1234"])
    expected = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[
        : ir.NEAR_DUPLICATE_GROUP_HASH_LEN
    ]
    assert ir.compute_near_duplicate_group(coords, fp) == expected


# ---------------------------------------------------------------------------
# Dataclass payloads carry the advisory framing
# ---------------------------------------------------------------------------


def test_routing_decision_payload_uses_advisory_field_names() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    decision = ir.RoutingDecision(
        campaign_id="c1",
        preset_name="preset_x",
        behavior_coordinates=coords,
        info_gain_score=0.42,
        info_gain_bucket="medium",
        dead_zone_status="alive",
        dead_zone_lookup_precision="exact_timeframe_match",
        near_duplicate_group=None,
        orthogonality_bucket="novel",
        advisory_suppression_reason=None,
        advisory_priority_score=0,
        advisory_rank=0,
        tie_break_key="2026-01-01T00:00:00Z|c1",
    )
    payload = decision.to_payload()
    assert "advisory_suppression_reason" in payload
    assert "advisory_priority_score" in payload
    assert "advisory_rank" in payload
    assert "dead_zone_lookup_precision" in payload  # v3.15.16.1
    assert payload["dead_zone_lookup_precision"] == "exact_timeframe_match"
    assert "suppression_reason" not in payload
    assert "recommended_priority" not in payload
    assert "priority" not in payload


def test_routing_report_summary_uses_advisory_field_names() -> None:
    summary = ir.RoutingReportSummary(
        total=10,
        advisory_suppressed_dead_zone=2,
        advisory_suppressed_near_duplicate=3,
        high_info_gain=4,
        novel_behavior_coordinates=5,
        metadata_gaps=1,
    )
    payload = summary.to_payload()
    assert "advisory_suppressed_dead_zone" in payload
    assert "advisory_suppressed_near_duplicate" in payload
    assert "suppressed_dead_zone" not in payload
    assert "suppressed_near_duplicate" not in payload


def test_routing_report_payload_carries_advisory_framing() -> None:
    coords = _coords("ema_crossover", "crypto", "4h")
    decision = ir.RoutingDecision(
        campaign_id="c1",
        preset_name="preset_x",
        behavior_coordinates=coords,
        info_gain_score=0.0,
        info_gain_bucket="none",
        dead_zone_status="unknown",
        dead_zone_lookup_precision="no_match",
        near_duplicate_group=None,
        orthogonality_bucket="novel",
        advisory_suppression_reason=None,
        advisory_priority_score=0,
        advisory_rank=0,
        tie_break_key="t",
    )
    summary = ir.RoutingReportSummary(
        total=1,
        advisory_suppressed_dead_zone=0,
        advisory_suppressed_near_duplicate=0,
        high_info_gain=0,
        novel_behavior_coordinates=1,
        metadata_gaps=0,
    )
    report = ir.RoutingReport(
        schema_version=ir.SCHEMA_VERSION,
        report_kind=ir.REPORT_KIND,
        version=ir.MODULE_VERSION,
        routing_effect=ir.ROUTING_EFFECT_ADVISORY_ONLY,
        queue_ordering_effect=ir.QUEUE_ORDERING_EFFECT_NONE,
        generated_at_utc="2026-01-01T00:00:00+00:00",
        provenance={},
        decisions=(decision,),
        summary=summary,
    )
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["queue_ordering_effect"] == "none"
    assert payload["schema_version"] == "1.0"
    assert payload["report_kind"] == "intelligent_routing"
    assert payload["version"] == "v3.15.16"
    assert isinstance(payload["decisions"], list)
    assert payload["summary"]["total"] == 1
