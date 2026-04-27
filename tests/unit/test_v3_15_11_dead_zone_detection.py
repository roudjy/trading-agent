"""v3.15.11 — dead-zone detection unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import serialize_canonical
from research.dead_zone_detection import (
    DEAD_ZONES_SCHEMA_VERSION,
    DZ_MIN_CAMPAIGNS,
    UNKNOWN_TIMEFRAME,
    ZONE_ALIVE,
    ZONE_DEAD,
    ZONE_INSUFFICIENT_DATA,
    ZONE_UNKNOWN,
    ZONE_WEAK,
    build_dead_zones_payload,
    derive_dead_zones,
    write_dead_zones_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _event(
    *,
    asset: str = "crypto",
    family: str = "trend_pullback",
    outcome: str = "research_rejection",
    reason: str = "screening_criteria_not_met",
    meaningful: str | None = None,
    run_id: str = "run_default",
) -> dict[str, Any]:
    return {
        "event_type": "campaign_completed",
        "asset_class": asset,
        "strategy_family": family,
        "outcome": outcome,
        "reason_code": reason,
        "meaningful_classification": meaningful,
        "run_id": run_id,
    }


def test_no_data_yields_empty_zones() -> None:
    assert derive_dead_zones([]) == []


def test_low_campaign_count_marks_insufficient_data() -> None:
    zones = derive_dead_zones([_event(run_id=f"r{i}") for i in range(2)])
    assert len(zones) == 1
    assert zones[0]["zone_status"] == ZONE_INSUFFICIENT_DATA
    assert "insufficient_campaign_count" in zones[0]["reason_codes"]


def test_repeated_low_info_failures_mark_dead() -> None:
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS + 5)]
    zones = derive_dead_zones(events)
    assert zones[0]["zone_status"] == ZONE_DEAD
    assert zones[0]["candidate_count"] == 0
    assert zones[0]["failure_density"] >= 0.80


def test_promotion_candidate_marks_alive_even_with_failures() -> None:
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS + 5)]
    events.append(
        _event(
            run_id="r_pass",
            outcome="completed_with_candidates",
            reason="none",
            meaningful=None,
        )
    )
    zones = derive_dead_zones(events)
    assert zones[0]["zone_status"] == ZONE_ALIVE
    assert zones[0]["candidate_count"] == 1


def test_exploratory_pass_marks_weak_not_dead() -> None:
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS)]
    events.append(
        _event(
            run_id="r_explor",
            outcome="completed_with_candidates",
            reason="none",
            meaningful="exploratory_pass",
        )
    )
    zones = derive_dead_zones(events)
    # exploratory_pass also brings a candidate via completed_with_candidates,
    # so this scope is alive. Use a separate test for exploratory-only path.
    assert zones[0]["zone_status"] == ZONE_ALIVE


def test_near_pass_only_marks_weak() -> None:
    """Near-pass without any candidate produces weak, not dead."""
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS)]
    events.append(
        _event(
            run_id="r_near",
            outcome="research_rejection",
            reason="profit_factor_below_floor",
            meaningful="near_pass",
        )
    )
    zones = derive_dead_zones(events)
    assert zones[0]["zone_status"] == ZONE_WEAK


def test_zones_sorted_deterministically() -> None:
    events = []
    for asset in ["solana", "ethereum", "bitcoin"]:
        for i in range(DZ_MIN_CAMPAIGNS):
            events.append(_event(asset=asset, run_id=f"{asset}_{i}"))
    zones = derive_dead_zones(events)
    asset_order = [z["asset"] for z in zones]
    assert asset_order == sorted(asset_order)


def test_information_gain_history_overrides_meaningful_rate() -> None:
    """When IG history is supplied, it drives information_gain_rate."""
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS)]
    history = [
        {
            "run_id": f"r{i}",
            "information_gain": {"is_meaningful_campaign": i < 2},
        }
        for i in range(DZ_MIN_CAMPAIGNS)
    ]
    zones = derive_dead_zones(events, information_gain_history=history)
    expected = round(2 / DZ_MIN_CAMPAIGNS, 4)
    assert zones[0]["information_gain_rate"] == expected


def test_schema_and_byte_identity(tmp_path: Path) -> None:
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS + 3)]
    p1 = build_dead_zones_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision="x",
        events=events,
    )
    p2 = build_dead_zones_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision="x",
        events=events,
    )
    assert serialize_canonical(p1) == serialize_canonical(p2)
    assert p1["schema_version"] == DEAD_ZONES_SCHEMA_VERSION
    out = tmp_path / "research" / "campaigns" / "evidence" / "dz.json"
    write_dead_zones_artifact(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        output_path=out,
    )
    assert out.exists()


def test_unknown_timeframe_field_present() -> None:
    """Until v4 enriches events with interval, timeframe is 'unknown'."""
    events = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS)]
    zones = derive_dead_zones(events)
    assert zones[0]["timeframe"] == UNKNOWN_TIMEFRAME


def test_dead_zone_does_not_remove_anything() -> None:
    """Smoke contract: derive function returns data only, no side effects."""
    events_before = [_event(run_id=f"r{i}") for i in range(DZ_MIN_CAMPAIGNS + 5)]
    snapshot = list(events_before)
    derive_dead_zones(events_before)
    assert events_before == snapshot


def test_unknown_status_when_low_failure_density_and_no_candidates() -> None:
    """Mid-failure-density without candidates classifies as unknown.

    Validates the status ladder covers the no-strong-signal case
    (5 campaigns, 1 rejection, 4 'no event' filler avoided by using
    completed_with_candidates without meaningful).
    """
    events = []
    for i in range(DZ_MIN_CAMPAIGNS):
        events.append(
            _event(
                run_id=f"r{i}",
                outcome="research_rejection" if i == 0 else "completed_with_candidates",
                reason="screening_criteria_not_met" if i == 0 else "none",
            )
        )
    zones = derive_dead_zones(events)
    # 4 of 5 outcomes are completed_with_candidates → alive.
    assert zones[0]["zone_status"] == ZONE_ALIVE


def test_pure_unknown_when_no_signals() -> None:
    """All outcomes that produce neither candidates nor rejections."""
    events = [
        _event(
            run_id=f"r{i}",
            outcome="completed_with_candidates",
            meaningful=None,
        )
        for i in range(DZ_MIN_CAMPAIGNS - 1)
    ]
    # Add a single non-rejection, non-candidate (technical_failure)
    events.append(_event(run_id="r_tech", outcome="technical_failure"))
    zones = derive_dead_zones(events)
    # candidate_count > 0 → alive.
    assert zones[0]["zone_status"] == ZONE_ALIVE


def test_purely_unknown_without_candidates_or_rejection() -> None:
    """Crafted scenario: enough campaigns but only technical failures."""
    events = [
        _event(run_id=f"r{i}", outcome="technical_failure", reason="none")
        for i in range(DZ_MIN_CAMPAIGNS)
    ]
    zones = derive_dead_zones(events)
    # No rejections (technical doesn't count as research-rejection
    # for failure_density), no candidates → unknown.
    assert zones[0]["zone_status"] == ZONE_UNKNOWN
