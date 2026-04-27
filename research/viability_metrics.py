"""v3.15.11 — Viability Metrics (advisory observability).

Conservative, deterministic indicator of whether the research engine
is producing learnable / candidate-yielding work within the current
hypothesis space. Operator-facing — not a kill switch and not a
financial recommendation.

Verdict ladder (most-cautious first):

- ``insufficient_data``           — fewer than ``VIABILITY_MIN_CAMPAIGNS``.
- ``promising``                   — meaningful rate above the
  promising floor or any candidate / paper-ready evidence exists.
- ``weak``                        — some learning (medium IG) but
  no candidate yet.
- ``commercially_questionable``   — many repeated failures, low
  information gain, no candidates.
- ``stop_or_pivot``               — large window elapsed with no
  meaningful campaigns and no candidates.

Cost-per-X metrics divide ``estimated_compute_cost`` by the relevant
denominator and return ``None`` whenever the denominator is zero —
no NaN/inf leaks into the artifact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic
from research.dead_zone_detection import ZONE_DEAD

VIABILITY_SCHEMA_VERSION: Final[str] = "1.0"
VIABILITY_PATH: Final[Path] = Path(
    "research/campaigns/evidence/viability_latest.v1.json"
)
VIABILITY_DIGEST_PATH: Final[Path] = Path(
    "research/campaigns/digests/viability_digest_latest.md"
)

# Thresholds — single inspection point.
VIABILITY_MIN_CAMPAIGNS: Final[int] = 20
VIABILITY_MEANINGFUL_RATE_PROMISING: Final[float] = 0.50
VIABILITY_MEANINGFUL_RATE_WEAK: Final[float] = 0.10
VIABILITY_LARGE_WINDOW: Final[int] = 100

VERDICT_INSUFFICIENT: Final[str] = "insufficient_data"
VERDICT_PROMISING: Final[str] = "promising"
VERDICT_WEAK: Final[str] = "weak"
VERDICT_COMMERCIALLY_QUESTIONABLE: Final[str] = "commercially_questionable"
VERDICT_STOP_OR_PIVOT: Final[str] = "stop_or_pivot"


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    value = numerator / denominator
    if value != value:  # NaN guard
        return None
    return value


def _aggregate_from_ledger(evidence_ledger: dict[str, Any]) -> dict[str, int]:
    rows = evidence_ledger.get("hypothesis_evidence") or []
    totals = {
        "campaign_count": 0,
        "candidate_count": 0,
        "near_candidate_count": 0,
        "paper_ready_count": 0,
        "exploratory_pass_count": 0,  # nosec B105 — counter key, not a credential
        "rejection_count": 0,
        "technical_failure_count": 0,
    }
    for row in rows:
        totals["campaign_count"] += int(row.get("campaign_count") or 0)
        totals["candidate_count"] += int(row.get("promotion_candidate_count") or 0)
        totals["paper_ready_count"] += int(row.get("paper_ready_count") or 0)
        totals["exploratory_pass_count"] += int(row.get("exploratory_pass_count") or 0)
        totals["rejection_count"] += int(row.get("rejection_count") or 0)
        totals["technical_failure_count"] += int(row.get("technical_failure_count") or 0)
    return totals


def _meaningful_count(information_gain_history: list[dict[str, Any]] | None) -> int:
    if not information_gain_history:
        return 0
    return sum(
        1
        for entry in information_gain_history
        if (entry.get("information_gain") or {}).get("is_meaningful_campaign")
    )


def _dead_zone_count(dead_zones: list[dict[str, Any]] | None) -> int:
    if not dead_zones:
        return 0
    return sum(1 for z in dead_zones if z.get("zone_status") == ZONE_DEAD)


def _classify_verdict(
    *,
    campaign_count: int,
    meaningful_rate: float,
    candidate_count: int,
    rejection_count: int,
    information_gain_rate: float,
) -> tuple[str, list[str], str]:
    """Pure verdict classifier. Returns (status, reasons, summary)."""
    reasons: list[str] = []
    if campaign_count < VIABILITY_MIN_CAMPAIGNS:
        reasons.append("fewer_than_minimum_campaigns")
        summary = (
            f"Only {campaign_count} campaigns observed; need at least "
            f"{VIABILITY_MIN_CAMPAIGNS} before drawing a verdict."
        )
        return VERDICT_INSUFFICIENT, reasons, summary

    if candidate_count > 0 or meaningful_rate >= VIABILITY_MEANINGFUL_RATE_PROMISING:
        if candidate_count > 0:
            reasons.append("candidate_or_paper_ready_present")
        if meaningful_rate >= VIABILITY_MEANINGFUL_RATE_PROMISING:
            reasons.append("meaningful_rate_above_promising_floor")
        summary = (
            f"{campaign_count} campaigns, meaningful rate "
            f"{meaningful_rate:.2%}, {candidate_count} candidate(s)."
        )
        return VERDICT_PROMISING, reasons, summary

    if (
        campaign_count >= VIABILITY_LARGE_WINDOW
        and information_gain_rate <= VIABILITY_MEANINGFUL_RATE_WEAK
        and candidate_count == 0
    ):
        reasons.append("large_window_no_meaningful_no_candidate")
        summary = (
            f"{campaign_count} campaigns over the large-window threshold, "
            "no meaningful information and no candidates."
        )
        return VERDICT_STOP_OR_PIVOT, reasons, summary

    if (
        information_gain_rate <= VIABILITY_MEANINGFUL_RATE_WEAK
        and rejection_count >= campaign_count * 0.5
        and candidate_count == 0
    ):
        reasons.append("low_information_gain_high_failure_rate_no_candidate")
        summary = (
            f"{campaign_count} campaigns, "
            f"{rejection_count} research rejections, no candidates and "
            f"information gain rate {information_gain_rate:.2%}."
        )
        return VERDICT_COMMERCIALLY_QUESTIONABLE, reasons, summary

    reasons.append("learning_signal_without_candidate_yet")
    summary = (
        f"{campaign_count} campaigns, meaningful rate "
        f"{meaningful_rate:.2%}, no candidate yet."
    )
    return VERDICT_WEAK, reasons, summary


def build_viability_payload(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    evidence_ledger: dict[str, Any],
    information_gain_history: list[dict[str, Any]] | None = None,
    dead_zones: list[dict[str, Any]] | None = None,
    estimated_compute_cost: float | None = None,
    window_start_utc: str | None = None,
    window_end_utc: str | None = None,
) -> dict[str, Any]:
    totals = _aggregate_from_ledger(evidence_ledger)
    campaign_count = totals["campaign_count"]
    candidate_count = totals["candidate_count"]
    paper_ready_count = totals["paper_ready_count"]
    rejection_count = totals["rejection_count"]
    technical_failure_count = totals["technical_failure_count"]
    meaningful = _meaningful_count(information_gain_history)
    if meaningful == 0:
        # Fall back to ledger-derived signals so the verdict isn't
        # held hostage to optional IG history.
        meaningful = totals["exploratory_pass_count"] + candidate_count + paper_ready_count
    meaningful_rate = (
        _safe_div(meaningful, campaign_count) or 0.0
    )
    failure_repeat_rate = (
        _safe_div(rejection_count, campaign_count) or 0.0
    )
    technical_failure_rate = (
        _safe_div(technical_failure_count, campaign_count) or 0.0
    )

    if estimated_compute_cost is not None:
        cost_per_meaningful = _safe_div(estimated_compute_cost, meaningful)
        cost_per_candidate = _safe_div(estimated_compute_cost, candidate_count)
        cost_per_near = _safe_div(
            estimated_compute_cost, totals["near_candidate_count"]
        )
        cost_per_paper_ready = _safe_div(
            estimated_compute_cost, paper_ready_count
        )
    else:
        cost_per_meaningful = None
        cost_per_candidate = None
        cost_per_near = None
        cost_per_paper_ready = None

    verdict, reasons, summary = _classify_verdict(
        campaign_count=campaign_count,
        meaningful_rate=meaningful_rate,
        candidate_count=candidate_count + paper_ready_count,
        rejection_count=rejection_count,
        information_gain_rate=meaningful_rate,
    )

    return {
        "schema_version": VIABILITY_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "window": {
            "campaign_count": campaign_count,
            "start_utc": window_start_utc,
            "end_utc": window_end_utc,
        },
        "metrics": {
            "campaign_count": campaign_count,
            "meaningful_campaign_count": meaningful,
            "meaningful_campaign_rate": round(meaningful_rate, 4),
            "candidate_count": candidate_count,
            "near_candidate_count": totals["near_candidate_count"],
            "paper_ready_count": paper_ready_count,
            "failure_repeat_rate": round(failure_repeat_rate, 4),
            "technical_failure_rate": round(technical_failure_rate, 4),
            "information_gain_rate": round(meaningful_rate, 4),
            "dead_zone_count": _dead_zone_count(dead_zones),
            "frozen_preset_count": 0,
            "retired_hypothesis_count": 0,
            "estimated_compute_cost": estimated_compute_cost,
            "cost_per_meaningful_campaign": cost_per_meaningful,
            "cost_per_candidate": cost_per_candidate,
            "cost_per_near_candidate": cost_per_near,
            "cost_per_paper_ready_candidate": cost_per_paper_ready,
        },
        "verdict": {
            "status": verdict,
            "reason_codes": reasons,
            "human_summary": summary,
        },
    }


def write_viability_artifact(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    evidence_ledger: dict[str, Any],
    information_gain_history: list[dict[str, Any]] | None = None,
    dead_zones: list[dict[str, Any]] | None = None,
    estimated_compute_cost: float | None = None,
    window_start_utc: str | None = None,
    window_end_utc: str | None = None,
    output_path: Path = VIABILITY_PATH,
) -> dict[str, Any]:
    payload = build_viability_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        evidence_ledger=evidence_ledger,
        information_gain_history=information_gain_history,
        dead_zones=dead_zones,
        estimated_compute_cost=estimated_compute_cost,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )
    write_sidecar_atomic(output_path, payload)
    return payload


__all__ = [
    "VERDICT_COMMERCIALLY_QUESTIONABLE",
    "VERDICT_INSUFFICIENT",
    "VERDICT_PROMISING",
    "VERDICT_STOP_OR_PIVOT",
    "VERDICT_WEAK",
    "VIABILITY_DIGEST_PATH",
    "VIABILITY_LARGE_WINDOW",
    "VIABILITY_MEANINGFUL_RATE_PROMISING",
    "VIABILITY_MEANINGFUL_RATE_WEAK",
    "VIABILITY_MIN_CAMPAIGNS",
    "VIABILITY_PATH",
    "VIABILITY_SCHEMA_VERSION",
    "build_viability_payload",
    "write_viability_artifact",
]
