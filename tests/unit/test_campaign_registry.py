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
