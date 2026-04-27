"""v3.15.11 — Dead-Zone Detection (advisory observability).

Surfaces (asset × timeframe × strategy_family) tuples where the
research engine is structurally finding nothing. Output is signal
only — this module **never** removes strategies, presets, or
candidates. Operators (or a future policy release) decide what to do
with the signal.

Status taxonomy:

- ``insufficient_data``  — fewer than ``DZ_MIN_CAMPAIGNS`` events.
- ``unknown``            — between min and warning thresholds, no
                           strong signal either way.
- ``alive``              — at least one promotion candidate, paper
                           ready, or recent meaningful campaign.
- ``weak``               — exploratory passes / near-candidates but
                           no promotion-grade outcome yet.
- ``dead``               — high failure density, low information
                           gain rate, no candidates.

Timeframe is currently ``"unknown"`` for every zone because the
upstream ledger event does not carry interval. v4 will enrich
ledger events with timeframe; until then the bucket gives operators
an asset+family-level view, which is the actionable scope.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

DEAD_ZONES_SCHEMA_VERSION: Final[str] = "1.0"
DEAD_ZONES_PATH: Final[Path] = Path(
    "research/campaigns/evidence/dead_zones_latest.v1.json"
)

# Conservative thresholds — dead-zone is the loudest label and
# should fire only when the evidence is unambiguous.
DZ_MIN_CAMPAIGNS: Final[int] = 5
DZ_DEAD_FAILURE_DENSITY: Final[float] = 0.80
DZ_DEAD_INFORMATION_GAIN_RATE: Final[float] = 0.10
DZ_WEAK_FAILURE_DENSITY: Final[float] = 0.50

ZONE_INSUFFICIENT_DATA: Final[str] = "insufficient_data"
ZONE_UNKNOWN: Final[str] = "unknown"
ZONE_ALIVE: Final[str] = "alive"
ZONE_WEAK: Final[str] = "weak"
ZONE_DEAD: Final[str] = "dead"

UNKNOWN_TIMEFRAME: Final[str] = "unknown"

PROMOTION_OUTCOMES: Final[frozenset[str]] = frozenset({
    "completed_with_candidates",
})
DEGENERATE_OUTCOMES: Final[frozenset[str]] = frozenset({
    "degenerate_no_survivors",
    "completed_no_survivor",
})
TECHNICAL_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset({
    "technical_failure",
    "worker_crashed",
    "aborted",
})


@dataclass
class _ZoneRoll:
    asset: str
    timeframe: str
    strategy_family: str
    campaign_count: int = 0
    candidate_count: int = 0
    exploratory_pass_count: int = 0
    near_pass_count: int = 0
    rejection_count: int = 0
    technical_failure_count: int = 0
    degenerate_count: int = 0
    meaningful_campaign_count: int = 0
    failure_reasons: Counter[str] = field(default_factory=Counter)
    run_ids: set[str] = field(default_factory=set)


def _classify_zone(
    *,
    campaign_count: int,
    failure_density: float,
    information_gain_rate: float,
    candidate_count: int,
    weak_signals: bool,
) -> tuple[str, list[str]]:
    """Pure status classifier. Returns (status, reason_codes)."""
    reasons: list[str] = []
    if campaign_count < DZ_MIN_CAMPAIGNS:
        reasons.append("insufficient_campaign_count")
        return ZONE_INSUFFICIENT_DATA, reasons
    if candidate_count > 0:
        reasons.append("candidate_or_paper_ready_present")
        return ZONE_ALIVE, reasons
    if (
        failure_density >= DZ_DEAD_FAILURE_DENSITY
        and information_gain_rate <= DZ_DEAD_INFORMATION_GAIN_RATE
    ):
        reasons.append("high_failure_density_low_information_gain")
        return ZONE_DEAD, reasons
    if weak_signals:
        reasons.append("near_or_exploratory_signal_present")
        return ZONE_WEAK, reasons
    if failure_density >= DZ_WEAK_FAILURE_DENSITY:
        reasons.append("elevated_failure_density")
        return ZONE_WEAK, reasons
    return ZONE_UNKNOWN, reasons


def _build_zone(
    roll: _ZoneRoll,
    *,
    information_gain_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    failure_density = (
        roll.rejection_count / roll.campaign_count
        if roll.campaign_count > 0
        else 0.0
    )
    information_gain_rate = 0.0
    if information_gain_history and roll.run_ids:
        ig_run_ids = {
            entry.get("run_id")
            for entry in information_gain_history
            if (entry.get("information_gain") or {}).get("is_meaningful_campaign")
        }
        meaningful_in_zone = len(roll.run_ids & {rid for rid in ig_run_ids if rid})
        information_gain_rate = meaningful_in_zone / roll.campaign_count
    elif roll.campaign_count > 0:
        information_gain_rate = (
            roll.meaningful_campaign_count / roll.campaign_count
        )

    candidate_probability = (
        roll.candidate_count / roll.campaign_count
        if roll.campaign_count > 0
        else 0.0
    )
    weak_signals = (
        roll.exploratory_pass_count > 0 or roll.near_pass_count > 0
    )
    status, reasons = _classify_zone(
        campaign_count=roll.campaign_count,
        failure_density=failure_density,
        information_gain_rate=information_gain_rate,
        candidate_count=roll.candidate_count,
        weak_signals=weak_signals,
    )
    dominant = None
    if roll.failure_reasons:
        dominant = sorted(
            roll.failure_reasons.items(), key=lambda kv: (-kv[1], kv[0])
        )[0][0]
    return {
        "asset": roll.asset,
        "timeframe": roll.timeframe,
        "strategy_family": roll.strategy_family,
        "regime": None,
        "campaign_count": roll.campaign_count,
        "meaningful_campaign_count": roll.meaningful_campaign_count,
        "candidate_count": roll.candidate_count,
        "dominant_failure_mode": dominant,
        "failure_density": round(failure_density, 4),
        "information_gain_rate": round(information_gain_rate, 4),
        "candidate_probability": round(candidate_probability, 4),
        "zone_status": status,
        "reason_codes": reasons,
    }


def _bucket_for_outcome(outcome: str | None) -> str:
    if outcome is None:
        return ZONE_UNKNOWN
    if outcome in DEGENERATE_OUTCOMES:
        return "degenerate"
    if outcome in TECHNICAL_FAILURE_OUTCOMES:
        return "technical_failure"
    if outcome in PROMOTION_OUTCOMES:
        return "promotion"
    return "research_rejection"


def _aggregate_zones(events: list[dict[str, Any]]) -> dict[tuple[str, str, str], _ZoneRoll]:
    rolls: dict[tuple[str, str, str], _ZoneRoll] = defaultdict(
        lambda: _ZoneRoll(
            asset=ZONE_UNKNOWN,
            timeframe=UNKNOWN_TIMEFRAME,
            strategy_family=ZONE_UNKNOWN,
        )
    )
    for ev in events:
        if ev.get("event_type") != "campaign_completed":
            continue
        asset = str(ev.get("asset_class") or ZONE_UNKNOWN)
        family = str(ev.get("strategy_family") or ZONE_UNKNOWN)
        key = (asset, UNKNOWN_TIMEFRAME, family)
        roll = rolls[key]
        roll.asset = asset
        roll.timeframe = UNKNOWN_TIMEFRAME
        roll.strategy_family = family
        roll.campaign_count += 1

        outcome = ev.get("outcome")
        bucket = _bucket_for_outcome(outcome)
        if bucket == "promotion":
            roll.candidate_count += 1
            roll.meaningful_campaign_count += 1
        elif bucket == "research_rejection":
            roll.rejection_count += 1
        elif bucket == "technical_failure":
            roll.technical_failure_count += 1
        elif bucket == "degenerate":
            roll.degenerate_count += 1
            roll.rejection_count += 1  # degenerate is research-meaningful

        meaningful = ev.get("meaningful_classification")
        if meaningful == "exploratory_pass":
            roll.exploratory_pass_count += 1
            roll.meaningful_campaign_count += 1
        if meaningful == "near_pass":
            roll.near_pass_count += 1
            roll.meaningful_campaign_count += 1

        reason = ev.get("reason_code")
        if reason and reason != "none":
            roll.failure_reasons[str(reason)] += 1
        run_id = ev.get("run_id")
        if isinstance(run_id, str) and run_id:
            roll.run_ids.add(run_id)
    return rolls


def derive_dead_zones(
    events: list[dict[str, Any]],
    *,
    information_gain_history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Pure derivation: ledger events (+ optional IG history) → zone rows."""
    rolls = _aggregate_zones(events)
    zones = [
        _build_zone(rolls[key], information_gain_history=information_gain_history)
        for key in sorted(rolls.keys())
    ]
    return zones


def build_dead_zones_payload(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    events: list[dict[str, Any]],
    information_gain_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    zones = derive_dead_zones(
        events, information_gain_history=information_gain_history
    )
    return {
        "schema_version": DEAD_ZONES_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "zones": zones,
    }


def write_dead_zones_artifact(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    events: list[dict[str, Any]],
    information_gain_history: list[dict[str, Any]] | None = None,
    output_path: Path = DEAD_ZONES_PATH,
) -> dict[str, Any]:
    payload = build_dead_zones_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        events=events,
        information_gain_history=information_gain_history,
    )
    write_sidecar_atomic(output_path, payload)
    return payload


__all__ = [
    "DEAD_ZONES_PATH",
    "DEAD_ZONES_SCHEMA_VERSION",
    "DZ_DEAD_FAILURE_DENSITY",
    "DZ_DEAD_INFORMATION_GAIN_RATE",
    "DZ_MIN_CAMPAIGNS",
    "DZ_WEAK_FAILURE_DENSITY",
    "ZONE_ALIVE",
    "ZONE_DEAD",
    "ZONE_INSUFFICIENT_DATA",
    "ZONE_UNKNOWN",
    "ZONE_WEAK",
    "build_dead_zones_payload",
    "derive_dead_zones",
    "write_dead_zones_artifact",
]
