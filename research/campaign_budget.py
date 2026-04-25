"""Compute-budget allocator for the v3.15.2 Campaign OS.

Three responsibilities:

1. **Historical runtime estimator** — ``estimate_runtime_seconds`` reads
   matched ``campaign_started`` / ``campaign_completed`` pairs from the
   ledger and returns the rounded mean.
2. **Dynamic reservation** (R3.4.1) — ``remaining_for_tier`` computes
   how many seconds a tier-1 / tier-2/3 candidate may still spend, with
   follow-up reservation only applied when tier-1 candidates actually
   exist this tick.
3. **Tier-1 fairness cap** (R3.4.2) — once ``consecutive_tier1_count``
   reaches the cap, the allocator demotes tier-1 candidates for the
   next decision tick to keep tier-2 from starving.

All helpers are pure. The allocator writes
``research/campaign_budget_latest.v1.json`` through the shared sidecar
writer; the launcher persists the result under the queue file lock.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc

BUDGET_SCHEMA_VERSION: str = "1.0"
BUDGET_ARTIFACT_PATH: Path = Path("research/campaign_budget_latest.v1.json")


@dataclass(frozen=True)
class BudgetReservation:
    campaign_id: str
    estimate_seconds: int
    reserved_at_utc: str
    priority_tier: int
    is_followup: bool

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetState:
    date: str
    daily_compute_budget_seconds: int
    reserved_for_followups_seconds: int
    max_low_value_reruns_per_day: int
    tier1_fairness_cap: int
    reservations: list[BudgetReservation] = field(default_factory=list)
    consumed_seconds: int = 0
    low_value_reruns_today: int = 0
    per_template_used_today: dict[str, int] = field(default_factory=dict)
    consecutive_tier1_count: int = 0

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["reservations"] = [r.to_payload() for r in self.reservations]
        data["reserved_seconds"] = self.reserved_seconds
        data["remaining_total_seconds"] = self.remaining_total_seconds
        return data

    @property
    def reserved_seconds(self) -> int:
        return sum(int(r.estimate_seconds) for r in self.reservations)

    @property
    def remaining_total_seconds(self) -> int:
        return max(
            0,
            int(self.daily_compute_budget_seconds)
            - int(self.reserved_seconds)
            - int(self.consumed_seconds),
        )

    def open_tier1_reservations(self) -> list[BudgetReservation]:
        return [r for r in self.reservations if int(r.priority_tier) == 1]


# ---------------------------------------------------------------------------
# Estimator
# ---------------------------------------------------------------------------


def _parse_utc(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except (AttributeError, ValueError):
        return None


def _pair_runtime(
    events: list[dict[str, Any]],
    *,
    preset_name: str,
    campaign_type: str,
) -> list[int]:
    """Collect elapsed seconds for matched start/complete event pairs."""
    starts: dict[str, datetime] = {}
    runtimes: list[int] = []
    for ev in events:
        if ev.get("preset_name") != preset_name:
            continue
        if ev.get("campaign_type") != campaign_type:
            continue
        cid = str(ev.get("campaign_id") or "")
        etype = ev.get("event_type")
        ts = _parse_utc(str(ev.get("at_utc") or ""))
        if ts is None:
            continue
        if etype == "campaign_started":
            starts[cid] = ts
        elif etype == "campaign_completed" and cid in starts:
            runtimes.append(int((ts - starts[cid]).total_seconds()))
            del starts[cid]
    return [rt for rt in runtimes if rt > 0]


def estimate_runtime_seconds(
    events: list[dict[str, Any]],
    *,
    preset_name: str,
    campaign_type: str,
    fallback_seconds: int,
    window: int = 10,
    min_datapoints: int = 3,
) -> int:
    """Mean matched runtime (rounded up to nearest 60s) or fallback."""
    samples = _pair_runtime(
        events,
        preset_name=preset_name,
        campaign_type=campaign_type,
    )[-window:]
    if len(samples) < min_datapoints:
        return int(fallback_seconds)
    mean = sum(samples) / len(samples)
    return int(math.ceil(mean / 60.0) * 60)


# ---------------------------------------------------------------------------
# Allocator helpers (pure)
# ---------------------------------------------------------------------------


def dynamic_followup_reservation(
    state: BudgetState,
    *,
    active_followup_candidate_estimates: Iterable[int],
) -> int:
    """Cap-aware follow-up reservation: 0 if no active tier-1 candidates."""
    total = sum(int(e) for e in active_followup_candidate_estimates)
    if total <= 0:
        return 0
    return min(int(total), int(state.reserved_for_followups_seconds))


def remaining_for_tier(
    state: BudgetState,
    *,
    tier: int,
    active_followup_candidate_estimates: Iterable[int],
) -> int:
    """Seconds a candidate of the given tier may still consume this tick."""
    dyn_reserved = dynamic_followup_reservation(
        state,
        active_followup_candidate_estimates=active_followup_candidate_estimates,
    )
    if int(tier) == 1:
        return state.remaining_total_seconds
    return max(0, state.remaining_total_seconds - dyn_reserved)


def tier1_fairness_engaged(state: BudgetState) -> bool:
    """True when the tier-1 fairness cap should demote tier-1 this tick."""
    return state.consecutive_tier1_count >= int(state.tier1_fairness_cap)


def add_reservation(
    state: BudgetState,
    *,
    campaign_id: str,
    estimate_seconds: int,
    priority_tier: int,
    is_followup: bool,
    reserved_at_utc: datetime,
) -> BudgetState:
    """Return a copy of state with a new reservation appended."""
    new_reservation = BudgetReservation(
        campaign_id=campaign_id,
        estimate_seconds=int(estimate_seconds),
        reserved_at_utc=iso_utc(reserved_at_utc),
        priority_tier=int(priority_tier),
        is_followup=bool(is_followup),
    )
    return BudgetState(
        date=state.date,
        daily_compute_budget_seconds=state.daily_compute_budget_seconds,
        reserved_for_followups_seconds=state.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=state.max_low_value_reruns_per_day,
        tier1_fairness_cap=state.tier1_fairness_cap,
        reservations=[*state.reservations, new_reservation],
        consumed_seconds=state.consumed_seconds,
        low_value_reruns_today=state.low_value_reruns_today,
        per_template_used_today=dict(state.per_template_used_today),
        consecutive_tier1_count=state.consecutive_tier1_count,
    )


def settle_reservation(
    state: BudgetState,
    *,
    campaign_id: str,
    actual_runtime_seconds: int,
    priority_tier: int,
    template_id: str,
) -> BudgetState:
    """Remove a reservation and apply actual consumption + counters."""
    remaining = [
        r for r in state.reservations if r.campaign_id != campaign_id
    ]
    per_template = dict(state.per_template_used_today)
    per_template[template_id] = int(per_template.get(template_id, 0)) + 1
    tier1_count = (
        int(state.consecutive_tier1_count) + 1
        if int(priority_tier) == 1
        else 0
    )
    return BudgetState(
        date=state.date,
        daily_compute_budget_seconds=state.daily_compute_budget_seconds,
        reserved_for_followups_seconds=state.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=state.max_low_value_reruns_per_day,
        tier1_fairness_cap=state.tier1_fairness_cap,
        reservations=remaining,
        consumed_seconds=state.consumed_seconds + max(0, int(actual_runtime_seconds)),
        low_value_reruns_today=state.low_value_reruns_today,
        per_template_used_today=per_template,
        consecutive_tier1_count=tier1_count,
    )


def increment_low_value_rerun(state: BudgetState) -> BudgetState:
    return BudgetState(
        date=state.date,
        daily_compute_budget_seconds=state.daily_compute_budget_seconds,
        reserved_for_followups_seconds=state.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=state.max_low_value_reruns_per_day,
        tier1_fairness_cap=state.tier1_fairness_cap,
        reservations=list(state.reservations),
        consumed_seconds=state.consumed_seconds,
        low_value_reruns_today=state.low_value_reruns_today + 1,
        per_template_used_today=dict(state.per_template_used_today),
        consecutive_tier1_count=state.consecutive_tier1_count,
    )


def rollover_if_new_day(
    state: BudgetState,
    *,
    now_utc: datetime,
) -> BudgetState:
    """Reset per-day counters when crossing into a new UTC day."""
    today = now_utc.astimezone(UTC).date().isoformat()
    if today == state.date:
        return state
    # Standing reservations carry over; their eventual actual consumption
    # still counts against today's budget via ``consumed_seconds``.
    return BudgetState(
        date=today,
        daily_compute_budget_seconds=state.daily_compute_budget_seconds,
        reserved_for_followups_seconds=state.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=state.max_low_value_reruns_per_day,
        tier1_fairness_cap=state.tier1_fairness_cap,
        reservations=list(state.reservations),
        consumed_seconds=0,
        low_value_reruns_today=0,
        per_template_used_today={},
        consecutive_tier1_count=0,
    )


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def load_budget(
    *,
    now_utc: datetime,
    daily_compute_budget_seconds: int,
    reserved_for_followups_seconds: int,
    max_low_value_reruns_per_day: int,
    tier1_fairness_cap: int,
    path: Path = BUDGET_ARTIFACT_PATH,
) -> BudgetState:
    """Load the on-disk budget; default skeleton if absent or mismatched."""
    today = now_utc.astimezone(UTC).date().isoformat()
    default = BudgetState(
        date=today,
        daily_compute_budget_seconds=int(daily_compute_budget_seconds),
        reserved_for_followups_seconds=int(reserved_for_followups_seconds),
        max_low_value_reruns_per_day=int(max_low_value_reruns_per_day),
        tier1_fairness_cap=int(tier1_fairness_cap),
    )
    if not path.exists():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    reservations = [
        BudgetReservation(
            campaign_id=str(r.get("campaign_id") or ""),
            estimate_seconds=int(r.get("estimate_seconds") or 0),
            reserved_at_utc=str(r.get("reserved_at_utc") or ""),
            priority_tier=int(r.get("priority_tier") or 3),
            is_followup=bool(r.get("is_followup")),
        )
        for r in (raw.get("reservations") or [])
    ]
    state = BudgetState(
        date=str(raw.get("date") or today),
        daily_compute_budget_seconds=int(
            raw.get("daily_compute_budget_seconds") or daily_compute_budget_seconds
        ),
        reserved_for_followups_seconds=int(
            raw.get("reserved_for_followups_seconds") or reserved_for_followups_seconds
        ),
        max_low_value_reruns_per_day=int(
            raw.get("max_low_value_reruns_per_day") or max_low_value_reruns_per_day
        ),
        tier1_fairness_cap=int(
            raw.get("tier1_fairness_cap") or tier1_fairness_cap
        ),
        reservations=reservations,
        consumed_seconds=int(raw.get("consumed_seconds") or 0),
        low_value_reruns_today=int(raw.get("low_value_reruns_today") or 0),
        per_template_used_today=dict(raw.get("per_template_used_today") or {}),
        consecutive_tier1_count=int(raw.get("consecutive_tier1_count") or 0),
    )
    return rollover_if_new_day(state, now_utc=now_utc)


def write_budget(
    state: BudgetState,
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = BUDGET_ARTIFACT_PATH,
) -> None:
    pins = build_pin_block(
        schema_version=BUDGET_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    payload = {**pins, **state.to_payload()}
    write_sidecar_atomic(path, payload)


__all__ = [
    "BUDGET_ARTIFACT_PATH",
    "BUDGET_SCHEMA_VERSION",
    "BudgetReservation",
    "BudgetState",
    "add_reservation",
    "dynamic_followup_reservation",
    "estimate_runtime_seconds",
    "increment_low_value_rerun",
    "load_budget",
    "remaining_for_tier",
    "rollover_if_new_day",
    "settle_reservation",
    "tier1_fairness_engaged",
    "write_budget",
]
