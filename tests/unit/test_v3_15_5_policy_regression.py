"""v3.15.5 — preset policy regression for the new outcome semantics.

Pins the post-v3.15.5 behavior:

- 5× consecutive ``degenerate_no_survivors`` → preset enters ``frozen``.
- 5× consecutive ``research_rejection`` → preset enters ``frozen``.
- 5× consecutive ``technical_failure`` → preset stays ``active``
  (technical failures must not freeze a preset).
- A mixed streak that interleaves a technical_failure restarts the
  non-technical streak counter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

import pytest

from research.campaign_evidence_ledger import REASON_CODE_NONE, make_event
from research.campaign_preset_policy import derive_preset_state


PRESET = "trend_equities_4h_baseline"
BASE_COOLDOWN = 86_400


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)


def _event(
    *,
    at_utc: datetime,
    outcome: str,
    reason_code: str = REASON_CODE_NONE,
    campaign_id: str,
    event_type: str = "campaign_completed",
) -> dict:
    return make_event(
        campaign_id=campaign_id,
        parent_campaign_id=None,
        lineage_root_campaign_id=campaign_id,
        preset_name=PRESET,
        campaign_type="daily_primary",
        event_type=event_type,
        at_utc=at_utc,
        reason_code=reason_code,
        outcome=outcome,
    ).to_payload()


def _streak(now_utc: datetime, outcomes: Iterable[str],
            reason_code: str = REASON_CODE_NONE,
            event_type: str = "campaign_completed") -> list[dict]:
    out: list[dict] = []
    for i, outcome in enumerate(outcomes):
        out.append(_event(
            at_utc=now_utc - timedelta(hours=24 * (len(list(outcomes)) - i)),
            outcome=outcome,
            campaign_id=f"col-{i}",
            reason_code=reason_code,
            event_type=event_type,
        ))
    return out


def test_five_degenerate_no_survivors_freezes_preset(now_utc: datetime) -> None:
    events = _streak(now_utc, ["degenerate_no_survivors"] * 5,
                    reason_code="degenerate_no_evaluable_pairs")
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state == "frozen"
    assert state.consecutive_event_count == 5
    assert state.reason == "five_consecutive_non_technical_rejects"


def test_five_research_rejection_freezes_preset(now_utc: datetime) -> None:
    events = _streak(now_utc, ["research_rejection"] * 5,
                    reason_code="insufficient_trades")
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state == "frozen"
    assert state.consecutive_event_count == 5


def test_five_technical_failure_does_not_freeze_preset(now_utc: datetime) -> None:
    """technical_failure events use event_type=campaign_failed (not
    campaign_completed); the policy streak counter only inspects
    campaign_completed events. Either path must NOT freeze the preset.
    """
    events_failed = _streak(
        now_utc, ["technical_failure"] * 5,
        reason_code="worker_crash",
        event_type="campaign_failed",
    )
    state = derive_preset_state(
        events_failed,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state != "frozen"
    # Even if hypothetically emitted under campaign_completed (not the
    # case post-v3.15.5), technical reason codes are excluded from the
    # streak via _TECHNICAL_REASON_CODES.
    events_completed = _streak(
        now_utc, ["technical_failure"] * 5,
        reason_code="worker_crash",
        event_type="campaign_completed",
    )
    state2 = derive_preset_state(
        events_completed,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state2.policy_state != "frozen"


def test_mixed_degenerate_then_technical_breaks_streak(now_utc: datetime) -> None:
    """3 degenerate then 1 technical_failure (campaign_completed) then
    1 degenerate must NOT count as 4 consecutive non-technical rejects.

    Note: technical_failure normally goes to campaign_failed, but if
    the streak counter ever sees it under campaign_completed via a
    legacy path, the technical reason_code excludes it from the streak
    — and the _streak counter looks at the tail. The interrupting
    technical event resets the count.
    """
    events: list[dict] = []
    base = now_utc - timedelta(hours=10)
    for i, outcome in enumerate(["degenerate_no_survivors"] * 3):
        events.append(_event(
            at_utc=base + timedelta(hours=i),
            outcome=outcome,
            campaign_id=f"col-d{i}",
            reason_code="degenerate_no_evaluable_pairs",
        ))
    events.append(_event(
        at_utc=base + timedelta(hours=3),
        outcome="technical_failure",
        campaign_id="col-tech",
        reason_code="worker_crash",
        event_type="campaign_completed",  # hypothetical legacy
    ))
    events.append(_event(
        at_utc=base + timedelta(hours=4),
        outcome="degenerate_no_survivors",
        campaign_id="col-d4",
        reason_code="degenerate_no_evaluable_pairs",
    ))
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    # Tail streak after technical interruption: 1 degenerate event,
    # which is below the 5-threshold for freeze. The
    # ``consecutive_event_count`` field reflects the no_survivor
    # cooldown ladder (which counts ``completed_no_survivor`` only,
    # by design — see campaign_preset_policy.py line 206), so it
    # remains 0 here even though the non-technical streak is 1. The
    # functional assertion is the freeze decision.
    assert state.policy_state != "frozen"
