"""Tests for research.campaign_registry (v3.15.2 COL source of truth)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.campaign_registry import (
    CAMPAIGN_OUTCOMES,
    CAMPAIGN_STATES,
    MEANINGFUL_CLASSIFICATIONS,
    CampaignRecord,
    IllegalTransitionError,
    build_campaign_id,
    fingerprint_inputs,
    has_child_of_type,
    has_duplicate,
    load_registry,
    record_outcome,
    records_for_preset,
    records_in_states,
    transition_state,
    upsert_record,
    write_registry,
)


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 12, 33, tzinfo=UTC)


def _record(**overrides) -> CampaignRecord:
    defaults = dict(
        campaign_id="col-20260424T081233000000Z-trend_equities_4h_baseline-abcdef0123",
        template_id="daily_primary__trend_equities_4h_baseline",
        preset_name="trend_equities_4h_baseline",
        campaign_type="daily_primary",
        state="pending",
        priority_tier=2,
        spawned_at_utc="2026-04-24T08:12:33Z",
        estimated_runtime_seconds=1800,
        lineage_root_campaign_id="col-20260424T081233000000Z-trend_equities_4h_baseline-abcdef0123",
        input_artifact_fingerprint="a1" * 32,
    )
    defaults.update(overrides)
    return CampaignRecord(**defaults)


def test_build_campaign_id_is_globally_unique(now_utc: datetime) -> None:
    ids = set()
    for _ in range(100):
        cid = build_campaign_id(
            preset_name="trend_equities_4h_baseline",
            now_utc=now_utc,
            parent_or_lineage_root="root",
            input_artifact_fingerprint="deadbeef",
        )
        ids.add(cid)
    assert len(ids) == 100


def test_build_campaign_id_deterministic_with_fixed_nonce(
    now_utc: datetime,
) -> None:
    a = build_campaign_id(
        preset_name="p",
        now_utc=now_utc,
        parent_or_lineage_root=None,
        input_artifact_fingerprint="x",
        attempt_nonce="fixed",
    )
    b = build_campaign_id(
        preset_name="p",
        now_utc=now_utc,
        parent_or_lineage_root=None,
        input_artifact_fingerprint="x",
        attempt_nonce="fixed",
    )
    assert a == b


def test_fingerprint_inputs_is_stable_across_orderings() -> None:
    a = fingerprint_inputs({"b.json": "hashB", "a.json": "hashA"})
    b = fingerprint_inputs({"a.json": "hashA", "b.json": "hashB"})
    assert a == b


def test_upsert_then_retrieve() -> None:
    registry: dict = {"campaigns": {}}
    record = _record()
    registry = upsert_record(registry, record)
    assert record.campaign_id in registry["campaigns"]
    assert registry["campaigns"][record.campaign_id]["preset_name"] == (
        "trend_equities_4h_baseline"
    )


def test_transition_state_respects_legal_edges(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    record = _record()
    registry = upsert_record(registry, record)
    registry = transition_state(
        registry,
        campaign_id=record.campaign_id,
        to_state="leased",
        at_utc=now_utc,
    )
    assert registry["campaigns"][record.campaign_id]["state"] == "leased"
    assert registry["campaigns"][record.campaign_id]["leased_at_utc"]


def test_transition_state_rejects_illegal_edge(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(
        registry,
        _record(state="completed"),
    )
    with pytest.raises(IllegalTransitionError):
        transition_state(
            registry,
            campaign_id=_record().campaign_id,
            to_state="running",
            at_utc=now_utc,
        )


def test_record_outcome_validates_outcomes() -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record(state="running"))
    with pytest.raises(ValueError):
        record_outcome(
            registry,
            campaign_id=_record().campaign_id,
            outcome="not_a_real_outcome",  # type: ignore[arg-type]
            meaningful="meaningful_candidate_found",
            actual_runtime_seconds=10,
        )


def test_record_outcome_writes_fields() -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record(state="running"))
    registry = record_outcome(
        registry,
        campaign_id=_record().campaign_id,
        outcome="completed_with_candidates",
        meaningful="meaningful_candidate_found",
        actual_runtime_seconds=1234,
        reason_code="none",
        run_id="20260424T000000000000Z",
    )
    record = registry["campaigns"][_record().campaign_id]
    assert record["outcome"] == "completed_with_candidates"
    assert record["meaningful_classification"] == "meaningful_candidate_found"
    assert record["actual_runtime_seconds"] == 1234


def test_has_duplicate_detects_non_archived(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record())
    assert has_duplicate(
        registry,
        campaign_type="daily_primary",
        preset_name="trend_equities_4h_baseline",
        parent_or_lineage_root=None,
        input_artifact_fingerprint="a1" * 32,
    )
    assert not has_duplicate(
        registry,
        campaign_type="daily_primary",
        preset_name="trend_equities_4h_baseline",
        parent_or_lineage_root=None,
        input_artifact_fingerprint="different",
    )


def test_has_duplicate_ignores_archived(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record(state="archived"))
    assert not has_duplicate(
        registry,
        campaign_type="daily_primary",
        preset_name="trend_equities_4h_baseline",
        parent_or_lineage_root=None,
        input_artifact_fingerprint="a1" * 32,
    )


def test_has_child_of_type(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record(state="completed"))
    child = _record(
        campaign_id="col-child",
        campaign_type="survivor_confirmation",
        state="pending",
        parent_campaign_id=_record().campaign_id,
    )
    registry = upsert_record(registry, child)
    assert has_child_of_type(
        registry,
        parent_campaign_id=_record().campaign_id,
        followup_campaign_type="survivor_confirmation",
    )
    assert not has_child_of_type(
        registry,
        parent_campaign_id=_record().campaign_id,
        followup_campaign_type="paper_followup",
    )


def test_write_registry_is_byte_reproducible(
    tmp_path: Path, now_utc: datetime
) -> None:
    registry: dict = {"campaigns": {}}
    registry = upsert_record(registry, _record())
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    write_registry(registry, generated_at_utc=now_utc, path=path_a)
    write_registry(registry, generated_at_utc=now_utc, path=path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_load_registry_returns_empty_on_missing(tmp_path: Path) -> None:
    loaded = load_registry(tmp_path / "missing.json")
    assert loaded == {"campaigns": {}}


def test_campaign_states_vocabulary_is_closed() -> None:
    assert "canceled" in CAMPAIGN_STATES
    assert "archived" in CAMPAIGN_STATES
    assert "pending" in CAMPAIGN_STATES


def test_meaningful_classifications_vocabulary_is_closed() -> None:
    assert "meaningful_candidate_found" in MEANINGFUL_CLASSIFICATIONS
    assert "uninformative_technical_failure" in MEANINGFUL_CLASSIFICATIONS
    assert "duplicate_low_value_run" in MEANINGFUL_CLASSIFICATIONS
    assert "meaningful_failure_confirmed" in MEANINGFUL_CLASSIFICATIONS


# ---------------------------------------------------------------------------
# v3.15.15.8 — registry metadata enrichment
# ---------------------------------------------------------------------------


def test_v3_15_15_8_record_defaults_for_new_metadata_fields() -> None:
    """Old call sites that don't pass the new fields must still build."""
    record = _record()
    payload = record.to_payload()
    assert payload["hypothesis_id"] is None
    assert payload["strategy_family"] is None
    assert payload["asset_class"] is None
    assert payload["universe"] == ()


def test_v3_15_15_8_record_round_trips_with_metadata_populated() -> None:
    record = _record(
        hypothesis_id="trend_pullback_v1",
        strategy_family="trend_pullback",
        asset_class="crypto",
        universe=("BTC-EUR", "ETH-EUR"),
    )
    payload = record.to_payload()
    assert payload["hypothesis_id"] == "trend_pullback_v1"
    assert payload["strategy_family"] == "trend_pullback"
    assert payload["asset_class"] == "crypto"
    # asdict converts inner mutable types but leaves top-level tuple
    # untouched. JSON serialization downstream renders it as a list.
    assert tuple(payload["universe"]) == ("BTC-EUR", "ETH-EUR")


def test_v3_15_15_8_legacy_record_without_new_keys_loads_via_dict_get() -> None:
    """Mixed-registry coexistence: old records lack the new keys.

    Consumers must read via ``record.get("...")`` which yields ``None``
    for missing keys; the new fields must NOT be required positional
    keys for any consumer.
    """
    legacy = {
        "campaign_id": "col-legacy",
        "template_id": "tpl",
        "preset_name": "trend_equities_4h_baseline",
        "campaign_type": "daily_primary",
        "state": "completed",
        "priority_tier": 2,
        "spawned_at_utc": "2026-04-29T00:00:00Z",
        # NB: no hypothesis_id, no strategy_family, no asset_class,
        # no universe — this is the live-VPS legacy shape.
    }
    assert legacy.get("hypothesis_id") is None
    assert legacy.get("strategy_family") is None
    assert legacy.get("asset_class") is None
    assert legacy.get("universe") is None  # i.e. no ``KeyError``


def test_v3_15_15_8_write_registry_byte_reproducible_with_metadata(
    tmp_path: Path, now_utc: datetime,
) -> None:
    registry: dict = {"campaigns": {}}
    record = _record(
        hypothesis_id="trend_pullback_v1",
        strategy_family="trend_pullback",
        asset_class="crypto",
        universe=("BTC-EUR", "ETH-EUR"),
    )
    registry = upsert_record(registry, record)
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_registry(registry, generated_at_utc=now_utc, path=a)
    write_registry(registry, generated_at_utc=now_utc, path=b)
    assert a.read_bytes() == b.read_bytes()


def test_v3_15_15_8_transition_state_preserves_metadata(
    now_utc: datetime,
) -> None:
    """A leased→running transition must NOT drop the metadata keys."""
    registry: dict = {"campaigns": {}}
    record = _record(
        state="leased",
        hypothesis_id="trend_pullback_v1",
        strategy_family="trend_pullback",
        asset_class="crypto",
        universe=("BTC-EUR",),
    )
    registry = upsert_record(registry, record)
    registry = transition_state(
        registry,
        campaign_id=record.campaign_id,
        to_state="running",
        at_utc=now_utc,
    )
    persisted = registry["campaigns"][record.campaign_id]
    assert persisted["hypothesis_id"] == "trend_pullback_v1"
    assert persisted["strategy_family"] == "trend_pullback"
    assert persisted["asset_class"] == "crypto"
    assert tuple(persisted["universe"]) == ("BTC-EUR",)


def test_v3_15_15_8_record_outcome_preserves_metadata(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    record = _record(
        state="running",
        hypothesis_id="volatility_compression_breakout_v0",
        strategy_family="volatility_compression_breakout",
        asset_class="crypto",
        universe=("BTC-EUR",),
    )
    registry = upsert_record(registry, record)
    registry = record_outcome(
        registry,
        campaign_id=record.campaign_id,
        outcome="degenerate_no_survivors",
        meaningful="meaningful_failure_confirmed",
        actual_runtime_seconds=42,
    )
    persisted = registry["campaigns"][record.campaign_id]
    assert persisted["hypothesis_id"] == "volatility_compression_breakout_v0"
    assert persisted["strategy_family"] == "volatility_compression_breakout"
    assert persisted["asset_class"] == "crypto"
