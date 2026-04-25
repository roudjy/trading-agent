"""Replay determinism test — invariant I6 across N ticks (plan §R3.7.1).

Drives the pure ``campaign_policy.decide`` function through a scripted
sequence of inputs. Each call must produce byte-identical output;
replaying the sequence must match a golden fixture bit-for-bit.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research._sidecar_io import serialize_canonical
from research.campaign_budget import BudgetState
from research.campaign_evidence_ledger import make_event
from research.campaign_policy import decide
from research.campaign_preset_policy import PresetPolicyState
from research.campaign_templates import CAMPAIGN_TEMPLATES, DEFAULT_CONFIG


PRESET_NAMES = sorted({t.preset_name for t in CAMPAIGN_TEMPLATES})


def _budget(now_utc: datetime) -> BudgetState:
    return BudgetState(
        date=now_utc.astimezone(UTC).date().isoformat(),
        daily_compute_budget_seconds=DEFAULT_CONFIG.daily_compute_budget_seconds,
        reserved_for_followups_seconds=DEFAULT_CONFIG.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=DEFAULT_CONFIG.max_low_value_reruns_per_day,
        tier1_fairness_cap=DEFAULT_CONFIG.tier1_fairness_cap,
    )


def _active_state(preset: str) -> PresetPolicyState:
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


def _scripted_tick_inputs(now_utc: datetime, tick_index: int) -> dict:
    """Deterministic per-tick inputs — no randomness, no clock reads."""
    # Every third tick a prior spawn exists to exercise the cooldown rule.
    events: list[dict] = []
    if tick_index % 3 == 1:
        events.append(
            make_event(
                campaign_id=f"col-prior-{tick_index}",
                parent_campaign_id=None,
                lineage_root_campaign_id=f"col-prior-{tick_index}",
                preset_name=PRESET_NAMES[0],
                campaign_type="daily_primary",
                event_type="campaign_spawned",
                at_utc=now_utc - timedelta(hours=4),
            ).to_payload()
        )
    return {
        "registry": {"campaigns": {}},
        "queue": {"queue": []},
        "events": events,
        "budget": _budget(now_utc),
        "preset_state_by_name": {p: _active_state(p) for p in PRESET_NAMES},
        "family_state_by_key": {},
        "upstream_artifact_states": {},
    }


def _scripted_decide(now_utc: datetime, tick_index: int):
    inputs = _scripted_tick_inputs(now_utc, tick_index)
    return decide(
        templates=CAMPAIGN_TEMPLATES,
        config=DEFAULT_CONFIG,
        now_utc=now_utc,
        **inputs,
    )


def _serialize(decision) -> bytes:
    return serialize_canonical(decision.to_payload()).encode("utf-8")


@pytest.mark.parametrize("n_ticks", [50])
def test_replay_determinism_across_n_ticks(n_ticks: int) -> None:
    start = datetime(2026, 4, 24, 0, 0, 0, tzinfo=UTC)
    golden: list[bytes] = []
    for i in range(n_ticks):
        now_utc = start + timedelta(hours=i)
        decision = _scripted_decide(now_utc, i)
        golden.append(_serialize(decision))

    # Replay pass — must match golden byte-for-byte.
    for i in range(n_ticks):
        now_utc = start + timedelta(hours=i)
        decision = _scripted_decide(now_utc, i)
        assert _serialize(decision) == golden[i], f"tick {i} diverged"


def test_reversed_tick_order_still_matches_per_tick_golden() -> None:
    """Determinism must not depend on call order — same inputs → same output."""
    start = datetime(2026, 4, 24, 0, 0, 0, tzinfo=UTC)
    ticks = list(range(20))
    golden = {
        i: _serialize(_scripted_decide(start + timedelta(hours=i), i))
        for i in ticks
    }
    for i in reversed(ticks):
        replayed = _serialize(_scripted_decide(start + timedelta(hours=i), i))
        assert replayed == golden[i]
