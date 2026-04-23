"""Unit tests for research.sleeve_registry."""

from __future__ import annotations

from research.sleeve_registry import (
    ASSIGNMENT_RULE_VERSION,
    REGIME_FILTERED_SUFFIX,
    assign_sleeves,
    build_sleeve_registry_payload,
)


def _v2_entry(
    candidate_id: str,
    *,
    strategy_family: str,
    asset_class: str,
    interval: str,
    lifecycle_status: str = "candidate",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "experiment_family": f"{strategy_family}|{asset_class}",
        "interval": interval,
        "lifecycle_status": lifecycle_status,
        "strategy_name": "strat",
        "asset": candidate_id.split("_")[-1],
        "parameter_set": {},
    }


def _overlay_entry(candidate_id: str, *, status: str = "sufficient") -> dict:
    return {
        "candidate_id": candidate_id,
        "regime_assessment_status": status,
    }


def test_assign_sleeves_empty_registry():
    registry = assign_sleeves(registry_v2={"entries": []})
    assert registry.sleeves == []
    assert registry.memberships == []


def test_assign_sleeves_only_eligible_lifecycle_is_included():
    entries = [
        _v2_entry("c1", strategy_family="trend", asset_class="equities", interval="4h"),
        _v2_entry(
            "c2",
            strategy_family="trend",
            asset_class="equities",
            interval="4h",
            lifecycle_status="rejected",
        ),
        _v2_entry(
            "c3",
            strategy_family="trend",
            asset_class="equities",
            interval="4h",
            lifecycle_status="exploratory",
        ),
    ]
    registry = assign_sleeves(registry_v2={"entries": entries})
    assert len(registry.memberships) == 1
    assert registry.memberships[0].candidate_id == "c1"


def test_assign_sleeves_groups_by_experiment_family_and_interval():
    entries = [
        _v2_entry("c1", strategy_family="trend", asset_class="equities", interval="4h"),
        _v2_entry("c2", strategy_family="trend", asset_class="equities", interval="4h"),
        _v2_entry("c3", strategy_family="trend", asset_class="equities", interval="1d"),
        _v2_entry("c4", strategy_family="meanrev", asset_class="crypto", interval="4h"),
    ]
    registry = assign_sleeves(registry_v2={"entries": entries})
    sleeve_ids = [s.sleeve_id for s in registry.sleeves]
    assert sleeve_ids == sorted(sleeve_ids)
    assert "trend_equities_4h" in sleeve_ids
    assert "trend_equities_1d" in sleeve_ids
    assert "meanrev_crypto_4h" in sleeve_ids

    members_by_sleeve = {s.sleeve_id: s.member_count for s in registry.sleeves}
    assert members_by_sleeve["trend_equities_4h"] == 2
    assert members_by_sleeve["trend_equities_1d"] == 1


def test_assign_sleeves_regime_filtered_variant_only_for_sufficient_status():
    entries = [
        _v2_entry("c1", strategy_family="trend", asset_class="equities", interval="4h"),
        _v2_entry("c2", strategy_family="trend", asset_class="equities", interval="4h"),
    ]
    overlay = {
        "entries": [
            _overlay_entry("c1", status="sufficient"),
            _overlay_entry("c2", status="insufficient"),
        ]
    }
    registry = assign_sleeves(registry_v2={"entries": entries}, regime_overlay=overlay)
    regime_sleeves = [s for s in registry.sleeves if s.is_regime_filtered]
    assert len(regime_sleeves) == 1
    assert regime_sleeves[0].sleeve_id.endswith(REGIME_FILTERED_SUFFIX)
    assert regime_sleeves[0].member_count == 1


def test_assign_sleeves_determinism():
    entries = [
        _v2_entry(f"c{i}", strategy_family="trend", asset_class="equities", interval="4h")
        for i in range(5)
    ]
    registry_a = assign_sleeves(registry_v2={"entries": entries})
    registry_b = assign_sleeves(registry_v2={"entries": list(reversed(entries))})
    assert [s.sleeve_id for s in registry_a.sleeves] == [
        s.sleeve_id for s in registry_b.sleeves
    ]
    assert [(m.sleeve_id, m.candidate_id) for m in registry_a.memberships] == [
        (m.sleeve_id, m.candidate_id) for m in registry_b.memberships
    ]


def test_build_sleeve_registry_payload_canonical():
    entries = [
        _v2_entry("c1", strategy_family="trend", asset_class="equities", interval="4h"),
    ]
    registry = assign_sleeves(registry_v2={"entries": entries})
    payload = build_sleeve_registry_payload(
        registry=registry,
        generated_at_utc="2026-04-23T20:00:00+00:00",
        run_id="run_x",
        git_revision="deadbeef",
    )
    assert payload["schema_version"] == "1.0"
    assert payload["assignment_rule_version"] == ASSIGNMENT_RULE_VERSION
    assert payload["generated_at_utc"] == "2026-04-23T20:00:00+00:00"
    assert payload["sleeves"][0]["sleeve_id"] == "trend_equities_4h"
    assert payload["memberships"][0]["candidate_id"] == "c1"
