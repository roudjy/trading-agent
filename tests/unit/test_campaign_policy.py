"""Tests for research.campaign_policy — invariant I6 (determinism) + rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from research._sidecar_io import serialize_canonical
from research.campaign_budget import BudgetState
from research.campaign_evidence_ledger import make_event
from research.campaign_family_policy import FamilyPolicyState
from research.campaign_policy import (
    POLICY_DECISION_PATH,
    CampaignDecision,
    decide,
    write_decision,
)
from research.campaign_preset_policy import PresetPolicyState
from research.campaign_templates import CAMPAIGN_TEMPLATES, DEFAULT_CONFIG, get_template


PRESET = "trend_equities_4h_baseline"


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


def _budget() -> BudgetState:
    return BudgetState(
        date="2026-04-24",
        daily_compute_budget_seconds=DEFAULT_CONFIG.daily_compute_budget_seconds,
        reserved_for_followups_seconds=DEFAULT_CONFIG.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=DEFAULT_CONFIG.max_low_value_reruns_per_day,
        tier1_fairness_cap=DEFAULT_CONFIG.tier1_fairness_cap,
    )


def _active_preset_state(preset: str = PRESET) -> PresetPolicyState:
    return PresetPolicyState(
        preset_name=preset,
        policy_state="active",
        priority_tier_delta=0,
        effective_cooldown_seconds=86_400,
        paper_followup_weekly_cap=2,
        reason="baseline",
        consecutive_event_count=0,
        last_event_ids=(),
        at_utc="2026-04-24T12:00:00Z",
    )


def _frozen_preset_state(preset: str = PRESET) -> PresetPolicyState:
    return PresetPolicyState(
        preset_name=preset,
        policy_state="frozen",
        priority_tier_delta=0,
        effective_cooldown_seconds=86_400,
        paper_followup_weekly_cap=0,
        reason="five_consecutive_non_technical_rejects",
        consecutive_event_count=5,
        last_event_ids=(),
        at_utc="2026-04-24T12:00:00Z",
    )


def _policy_decision_core(
    now_utc: datetime,
    *,
    registry: dict[str, Any] | None = None,
    queue: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    preset_states: dict[str, PresetPolicyState] | None = None,
    family_states: dict[str, FamilyPolicyState] | None = None,
    upstream_states: dict[str, str] | None = None,
    follow_up_specs: tuple = (),
    weekly_control_specs: tuple = (),
) -> CampaignDecision:
    return decide(
        registry=registry or {"campaigns": {}},
        queue=queue or {"queue": []},
        events=events or [],
        budget=_budget(),
        templates=CAMPAIGN_TEMPLATES,
        config=DEFAULT_CONFIG,
        preset_state_by_name=preset_states
        or {t.preset_name: _active_preset_state(t.preset_name) for t in CAMPAIGN_TEMPLATES},
        family_state_by_key=family_states or {},
        upstream_artifact_states=upstream_states or {},
        follow_up_candidate_specs=follow_up_specs,
        weekly_control_candidate_specs=weekly_control_specs,
        now_utc=now_utc,
    )


def test_empty_state_spawns_daily_primary(now_utc: datetime) -> None:
    decision = _policy_decision_core(now_utc)
    assert decision.decision.action == "spawn"
    assert decision.decision.campaign_type == "daily_primary"


def test_purity_byte_identical_across_calls(now_utc: datetime) -> None:
    """Invariant I6: same inputs → byte-identical decision artifact."""
    first = _policy_decision_core(now_utc)
    second = _policy_decision_core(now_utc)
    assert serialize_canonical(first.to_payload()) == serialize_canonical(
        second.to_payload()
    )


def test_purity_across_100_calls(now_utc: datetime) -> None:
    first = _policy_decision_core(now_utc).to_payload()
    serialized = serialize_canonical(first)
    for _ in range(100):
        again = _policy_decision_core(now_utc).to_payload()
        assert serialize_canonical(again) == serialized


def test_worker_busy_returns_idle_noop(now_utc: datetime) -> None:
    registry = {
        "campaigns": {
            "col-running": {
                "campaign_id": "col-running",
                "state": "running",
                "campaign_type": "daily_primary",
                "preset_name": PRESET,
                "priority_tier": 2,
                "spawned_at_utc": "2026-04-24T08:00:00Z",
                "input_artifact_fingerprint": "x",
            }
        }
    }
    decision = _policy_decision_core(now_utc, registry=registry)
    assert decision.decision.action == "idle_noop"
    assert decision.decision.reason == "worker_busy"


def test_stale_lease_reclaim(now_utc: datetime) -> None:
    expired_lease = {
        "lease_id": "abc",
        "worker_id": "w",
        "leased_at_utc": (now_utc - timedelta(hours=4)).isoformat(),
        "expires_utc": (now_utc - timedelta(hours=1))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "attempt": 1,
    }
    queue = {
        "queue": [
            {
                "campaign_id": "col-old",
                "state": "leased",
                "priority_tier": 2,
                "spawned_at_utc": "2026-04-24T08:00:00Z",
                "estimated_runtime_seconds": 1800,
                "lease": expired_lease,
            }
        ]
    }
    decision = _policy_decision_core(now_utc, queue=queue)
    assert decision.decision.action == "reclaim_stale_lease"
    assert decision.decision.campaign_id == "col-old"


def test_cooldown_blocks_repeat_within_24h(now_utc: datetime) -> None:
    """With only the target preset eligible for daily_primary and a
    recent spawn event on file, no daily_primary candidate survives
    cooldown and the engine falls back to weekly_retest for frozen
    peers (or idles when no weekly_retest is due).

    Narrower assertion: the target preset does not produce a new
    daily_primary this tick.
    """
    events = [
        make_event(
            campaign_id="col-prior",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-prior",
            preset_name=PRESET,
            campaign_type="daily_primary",
            event_type="campaign_spawned",
            at_utc=now_utc - timedelta(hours=2),
        ).to_payload()
    ]
    preset_states = {
        p: _active_preset_state(p)
        for p in {t.preset_name for t in CAMPAIGN_TEMPLATES}
    }
    decision = decide(
        registry={"campaigns": {}},
        queue={"queue": []},
        events=events,
        budget=_budget(),
        templates=CAMPAIGN_TEMPLATES,
        config=DEFAULT_CONFIG,
        preset_state_by_name=preset_states,
        family_state_by_key={},
        upstream_artifact_states={},
        now_utc=now_utc,
    )
    # The blocked preset must not be the one selected for daily_primary.
    if decision.decision.action == "spawn" and (
        decision.decision.campaign_type == "daily_primary"
    ):
        assert decision.decision.preset_name != PRESET


def test_frozen_daily_primary_falls_back_to_weekly_retest(
    now_utc: datetime,
) -> None:
    """Frozen presets are intentionally eligible for weekly_retest.

    When every preset is frozen and none has a recent weekly_retest
    spawn, the policy should pick a weekly_retest — this is the escape
    hatch that lets failure-memory thaw itself.
    """
    preset_states = {
        t.preset_name: _frozen_preset_state(t.preset_name)
        for t in CAMPAIGN_TEMPLATES
    }
    decision = _policy_decision_core(now_utc, preset_states=preset_states)
    assert decision.decision.action == "spawn"
    assert decision.decision.campaign_type == "weekly_retest"


def test_frozen_preset_with_recent_retest_idles(now_utc: datetime) -> None:
    """Frozen + recent weekly_retest spawn → cooldown blocks retest → idle."""
    preset_states = {
        t.preset_name: _frozen_preset_state(t.preset_name)
        for t in CAMPAIGN_TEMPLATES
    }
    events = [
        make_event(
            campaign_id=f"col-retest-{p}",
            parent_campaign_id=None,
            lineage_root_campaign_id=f"col-retest-{p}",
            preset_name=p,
            campaign_type="weekly_retest",
            event_type="campaign_spawned",
            at_utc=now_utc - timedelta(hours=1),
        ).to_payload()
        for p in {t.preset_name for t in CAMPAIGN_TEMPLATES}
    ]
    decision = _policy_decision_core(
        now_utc,
        preset_states=preset_states,
        events=events,
    )
    assert decision.decision.action == "idle_noop"


def test_upstream_stale_cancels_pending(now_utc: datetime) -> None:
    pending = {
        "campaign_id": "col-pending",
        "state": "pending",
        "priority_tier": 2,
        "spawned_at_utc": "2026-04-24T08:00:00Z",
        "estimated_runtime_seconds": 1800,
    }
    registry = {
        "campaigns": {
            "col-pending": {
                **pending,
                "campaign_type": "daily_primary",
                "preset_name": PRESET,
                "input_artifact_fingerprint": "x",
            }
        }
    }
    queue = {"queue": [pending]}
    decision = _policy_decision_core(
        now_utc,
        registry=registry,
        queue=queue,
        upstream_states={"public_artifact_status": "stale"},
    )
    assert decision.decision.action == "cancel_upstream_stale"
    assert decision.decision.campaign_id == "col-pending"


def test_budget_zero_returns_idle(now_utc: datetime) -> None:
    # Spend every second of the daily budget so no candidate fits.
    def _spent_budget() -> BudgetState:
        return BudgetState(
            date="2026-04-24",
            daily_compute_budget_seconds=DEFAULT_CONFIG.daily_compute_budget_seconds,
            reserved_for_followups_seconds=DEFAULT_CONFIG.reserved_for_followups_seconds,
            max_low_value_reruns_per_day=DEFAULT_CONFIG.max_low_value_reruns_per_day,
            tier1_fairness_cap=DEFAULT_CONFIG.tier1_fairness_cap,
            consumed_seconds=DEFAULT_CONFIG.daily_compute_budget_seconds,
        )

    decision = decide(
        registry={"campaigns": {}},
        queue={"queue": []},
        events=[],
        budget=_spent_budget(),
        templates=CAMPAIGN_TEMPLATES,
        config=DEFAULT_CONFIG,
        preset_state_by_name={
            t.preset_name: _active_preset_state(t.preset_name)
            for t in CAMPAIGN_TEMPLATES
        },
        family_state_by_key={},
        upstream_artifact_states={},
        now_utc=now_utc,
    )
    assert decision.decision.action == "idle_noop"


def test_write_decision_is_byte_reproducible(
    tmp_path: Path, now_utc: datetime
) -> None:
    decision = _policy_decision_core(now_utc)
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    write_decision(decision, generated_at_utc=now_utc, path=path_a)
    write_decision(decision, generated_at_utc=now_utc, path=path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_decision_has_rules_and_candidates_trace(now_utc: datetime) -> None:
    decision = _policy_decision_core(now_utc)
    assert len(decision.rules_evaluated) >= 3
    assert decision.tie_break_key == (
        "effective_priority_tier",
        "appended_in_phase",
        "appended_index",
        "template_id",
    )
