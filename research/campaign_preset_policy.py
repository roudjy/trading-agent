"""Preset-level active failure-memory policy (v3.15.2 COL).

Derives per-preset policy state from the evidence ledger each tick.
This is the surface the policy engine consults in §R3.2 step 5; it is
the only code path through which "failure memory" shows up in decisions.

Rules (R3.5 §7.1):

| Trigger                                                | Effect                                                         |
|--------------------------------------------------------|----------------------------------------------------------------|
| 3× ``insufficient_trades`` in last 10 attempts         | ``effective_cooldown *= 2`` (cap 7 d); state stays ``active``  |
| 3× ``screening_criteria_not_met`` in last 10 attempts  | ``priority_tier_delta = 1``; state = ``deprioritized``         |
| 3× consecutive ``reject_no_survivor``                  | ``effective_cooldown *= 2`` (cap 7 d); state = ``deprioritized``|
| 2× ``paper_blocked`` same reason_code                  | ``paper_followup_weekly_cap = 1``                              |
| 5× non-technical reject outcomes                       | state = ``frozen``                                             |

This module does NOT write ledger events itself — it only reads. The
caller (policy/launcher) is responsible for emitting
``preset_state_changed`` events when the derived state changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_evidence_ledger import (
    REASON_CODE_NONE,
    consecutive_outcome_streak,
    is_preset_frozen,
    last_n_outcomes_for_preset,
    reason_code_frequency,
)
from research.campaign_os_artifacts import build_pin_block

PRESET_POLICY_SCHEMA_VERSION: str = "1.0"
PRESET_POLICY_ARTIFACT_PATH: Path = Path(
    "research/preset_policy_state_latest.v1.json"
)

PresetPolicyStateLiteral = Literal["active", "deprioritized", "frozen"]

PRESET_POLICY_STATES: tuple[str, ...] = ("active", "deprioritized", "frozen")

# Thresholds — all derivable from the ledger; no hidden state.
_THRESH_INSUFFICIENT_TRADES = 3
_THRESH_SCREENING_FAIL = 3
_THRESH_NO_SURVIVOR_STREAK = 3
_THRESH_SAME_PAPER_BLOCKED = 2
_THRESH_NON_TECHNICAL_REJECTS = 5

_MAX_COOLDOWN_SECONDS = 7 * 86_400  # 7 days

# Outcomes that count as "non-technical" rejects for the freeze rule.
# v3.15.5: ``degenerate_no_survivors`` and ``research_rejection`` are
# semantically meaningful failures (the run produced a structured
# verdict — no evaluable inputs / family-falsifying screening rejects)
# and therefore count toward the freeze counter. ``technical_failure``
# is **not** included; technical failures stay excluded so an unstable
# infra path cannot freeze a preset.
_NON_TECHNICAL_REJECT_OUTCOMES: tuple[str, ...] = (
    "completed_no_survivor",
    "degenerate_no_survivors",
    "research_rejection",
    "paper_blocked",
    "integrity_failed",
)

# Reason codes that indicate a technical (not structural) failure; these
# are excluded from the freeze counter.
_TECHNICAL_REASON_CODES: frozenset[str] = frozenset(
    {
        "worker_crash",
        "timeout",
        "data_unavailable",
        "user_cancel",
        "malformed_return_stream",
        "insufficient_oos_days",
    }
)


@dataclass(frozen=True)
class PresetPolicyState:
    preset_name: str
    policy_state: PresetPolicyStateLiteral
    priority_tier_delta: int
    effective_cooldown_seconds: int
    paper_followup_weekly_cap: int
    reason: str
    consecutive_event_count: int
    last_event_ids: tuple[str, ...]
    at_utc: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_event_ids"] = list(self.last_event_ids)
        return data


def _collect_last_event_ids(
    events: list[dict[str, Any]],
    preset_name: str,
    window: int,
) -> tuple[str, ...]:
    slice_ = last_n_outcomes_for_preset(events, preset_name, window)
    return tuple(str(ev.get("event_id") or "") for ev in slice_)


def _non_technical_reject_streak(
    events: list[dict[str, Any]],
    preset_name: str,
) -> int:
    """Count tail streak of non-technical reject outcomes for a preset."""
    ordered = [
        ev
        for ev in events
        if ev.get("preset_name") == preset_name
        and ev.get("event_type") == "campaign_completed"
    ]
    ordered.sort(key=lambda ev: ev.get("at_utc", ""))
    streak = 0
    for ev in reversed(ordered):
        outcome = ev.get("outcome")
        reason = str(ev.get("reason_code") or REASON_CODE_NONE)
        if outcome in _NON_TECHNICAL_REJECT_OUTCOMES and reason not in _TECHNICAL_REASON_CODES:
            streak += 1
        else:
            break
    return streak


def _paper_blocked_same_reason_count(
    events: list[dict[str, Any]],
    preset_name: str,
    window: int = 10,
) -> tuple[int, str | None]:
    """Return the max count of same-reason paper_blocked in the window.

    Only examines the latest ``window`` ``paper_blocked`` events for
    the preset.
    """
    blocked = [
        ev
        for ev in events
        if ev.get("preset_name") == preset_name
        and ev.get("event_type") == "paper_blocked"
    ]
    blocked.sort(key=lambda ev: ev.get("at_utc", ""))
    blocked = blocked[-window:]
    if not blocked:
        return 0, None
    reasons: dict[str, int] = {}
    for ev in blocked:
        code = str(ev.get("reason_code") or REASON_CODE_NONE)
        reasons[code] = reasons.get(code, 0) + 1
    top_reason, top_count = max(reasons.items(), key=lambda kv: kv[1])
    return top_count, top_reason


def derive_preset_state(
    events: list[dict[str, Any]],
    *,
    preset_name: str,
    template_cooldown_seconds: int,
    default_paper_followup_cap: int,
    now_utc: datetime,
) -> PresetPolicyState:
    """Pure derivation of the preset's effective policy state."""
    at_utc = now_utc.astimezone(tz=None).isoformat()

    # Explicit freeze via ledger event takes precedence.
    if is_preset_frozen(events, preset_name):
        return PresetPolicyState(
            preset_name=preset_name,
            policy_state="frozen",
            priority_tier_delta=0,
            effective_cooldown_seconds=template_cooldown_seconds,
            paper_followup_weekly_cap=0,
            reason="preset_frozen_event",
            consecutive_event_count=0,
            last_event_ids=_collect_last_event_ids(events, preset_name, 5),
            at_utc=at_utc,
        )

    non_tech_streak = _non_technical_reject_streak(events, preset_name)
    if non_tech_streak >= _THRESH_NON_TECHNICAL_REJECTS:
        return PresetPolicyState(
            preset_name=preset_name,
            policy_state="frozen",
            priority_tier_delta=0,
            effective_cooldown_seconds=template_cooldown_seconds,
            paper_followup_weekly_cap=0,
            reason="five_consecutive_non_technical_rejects",
            consecutive_event_count=non_tech_streak,
            last_event_ids=_collect_last_event_ids(events, preset_name, non_tech_streak),
            at_utc=at_utc,
        )

    # Cooldown escalation: no-survivor streak.
    no_survivor_streak = consecutive_outcome_streak(
        events, preset_name, ("completed_no_survivor",)
    )
    effective_cooldown = int(template_cooldown_seconds)
    policy_state: PresetPolicyStateLiteral = "active"
    reason = "baseline"
    priority_tier_delta = 0
    if no_survivor_streak >= _THRESH_NO_SURVIVOR_STREAK:
        # Double once per streak-step past threshold, cap at MAX.
        doublings = no_survivor_streak - _THRESH_NO_SURVIVOR_STREAK + 1
        effective_cooldown = min(
            template_cooldown_seconds * (2 ** doublings),
            _MAX_COOLDOWN_SECONDS,
        )
        policy_state = "deprioritized"
        reason = f"no_survivor_streak_{no_survivor_streak}"

    # Cooldown escalation: insufficient-trades repetition.
    insufficient_count = reason_code_frequency(
        events, preset_name, window=10
    ).get("insufficient_trades", 0)
    if insufficient_count >= _THRESH_INSUFFICIENT_TRADES:
        doublings = insufficient_count - _THRESH_INSUFFICIENT_TRADES + 1
        effective_cooldown = max(
            effective_cooldown,
            min(template_cooldown_seconds * (2 ** doublings), _MAX_COOLDOWN_SECONDS),
        )
        if policy_state == "active":
            reason = f"insufficient_trades_count_{insufficient_count}"

    # Priority downgrade: repeated screening fails.
    screening_count = reason_code_frequency(
        events, preset_name, window=10
    ).get("screening_criteria_not_met", 0)
    if screening_count >= _THRESH_SCREENING_FAIL:
        priority_tier_delta = 1
        policy_state = "deprioritized"
        reason = f"screening_fail_count_{screening_count}"

    # Paper_blocked weekly-cap squeeze.
    pf_cap = int(default_paper_followup_cap)
    same_reason_count, _same_reason_code = _paper_blocked_same_reason_count(
        events, preset_name
    )
    if same_reason_count >= _THRESH_SAME_PAPER_BLOCKED:
        pf_cap = 1

    return PresetPolicyState(
        preset_name=preset_name,
        policy_state=policy_state,
        priority_tier_delta=priority_tier_delta,
        effective_cooldown_seconds=effective_cooldown,
        paper_followup_weekly_cap=pf_cap,
        reason=reason,
        consecutive_event_count=no_survivor_streak,
        last_event_ids=_collect_last_event_ids(events, preset_name, 5),
        at_utc=at_utc,
    )


def derive_preset_states(
    events: list[dict[str, Any]],
    *,
    preset_names: list[str],
    template_cooldown_seconds_by_preset: dict[str, int],
    default_paper_followup_cap: int,
    now_utc: datetime,
) -> dict[str, PresetPolicyState]:
    """Convenience: batch-derive state for a list of preset names."""
    out: dict[str, PresetPolicyState] = {}
    for preset_name in sorted(preset_names):
        cooldown = int(
            template_cooldown_seconds_by_preset.get(preset_name, 86_400)
        )
        out[preset_name] = derive_preset_state(
            events,
            preset_name=preset_name,
            template_cooldown_seconds=cooldown,
            default_paper_followup_cap=default_paper_followup_cap,
            now_utc=now_utc,
        )
    return out


def build_preset_policy_payload(
    states: dict[str, PresetPolicyState],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
) -> dict[str, Any]:
    pins = build_pin_block(
        schema_version=PRESET_POLICY_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    return {
        **pins,
        "presets": {
            preset_name: states[preset_name].to_payload()
            for preset_name in sorted(states)
        },
    }


def write_preset_policy(
    states: dict[str, PresetPolicyState],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = PRESET_POLICY_ARTIFACT_PATH,
) -> None:
    payload = build_preset_policy_payload(
        states,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
    )
    write_sidecar_atomic(path, payload)


__all__ = [
    "PRESET_POLICY_ARTIFACT_PATH",
    "PRESET_POLICY_SCHEMA_VERSION",
    "PRESET_POLICY_STATES",
    "PresetPolicyState",
    "PresetPolicyStateLiteral",
    "build_preset_policy_payload",
    "derive_preset_state",
    "derive_preset_states",
    "write_preset_policy",
]
