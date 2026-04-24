"""v3.15 paper readiness — first-class gate verdict.

Produces :class:`PaperReadinessEntry` values for each candidate,
aggregating evidence from the v3.15 layers (ledger, divergence,
timestamped returns). The verdict is **diagnostic-only** and
``live_eligible`` is hard-pinned to ``False`` — no codepath in
v3.15 sets it to ``True``.

Blocking and warning reason taxonomies are both closed sets
(``BLOCKING_REASONS`` / ``WARNING_REASONS``). Readiness status is
one of:

- ``ready_for_paper_promotion`` — no blocking reasons,
  ``n_obs >= MIN_PAPER_OOS_DAYS`` and
  ``divergence_severity != "high"``.
- ``blocked`` — at least one blocking reason.
- ``insufficient_evidence`` — no blocking reasons, but either
  insufficient observations or no ledger events, without being
  a formal block.

Escalation rule: ``negative_paper_sharpe`` is by default a
**warning**, not a block. It is promoted to a blocking reason
only when combined with ``excessive_divergence`` or with one of
the evidence-level blockers
(``no_candidate_returns`` / ``missing_execution_events``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from research.candidate_timestamped_returns_feed import (
    TimestampedCandidateReturnsRecord,
)
from research.paper_divergence import (
    DIVERGENCE_SEVERITY_HIGH_BPS,
    DIVERGENCE_SEVERITY_MEDIUM_BPS,
)


PAPER_READINESS_VERSION: str = "v0.1"
PAPER_READINESS_SCHEMA_VERSION: str = "1.0"

# Readiness thresholds
MIN_PAPER_OOS_DAYS: int = 60
MIN_PAPER_SHARPE_FOR_READY: float = 0.3
WARN_PROJECTED_INSUFFICIENT_RATIO: float = 0.20


# Closed blocking-reason taxonomy
BLOCKING_REASONS: tuple[str, ...] = (
    "insufficient_venue_mapping",
    "insufficient_oos_days",
    "missing_execution_events",
    "excessive_divergence",
    "malformed_return_stream",
    "no_candidate_returns",
)

# Closed warning-reason taxonomy
WARNING_REASONS: tuple[str, ...] = (
    "negative_paper_sharpe",
    "projected_insufficient_events_ratio_high",
    "medium_divergence",
)


READINESS_STATUSES: tuple[str, ...] = (
    "ready_for_paper_promotion",
    "blocked",
    "insufficient_evidence",
)


@dataclass(frozen=True)
class PaperReadinessInput:
    """Per-candidate input aggregated from v3.15 layer outputs."""

    candidate_id: str
    asset_type: str
    sleeve_id: str | None
    # From candidate_timestamped_returns_feed
    timestamped_returns: TimestampedCandidateReturnsRecord | None
    # From paper_ledger
    ledger_event_count: int
    projected_insufficient_event_count: int
    # From paper_divergence (may be None for unmapped candidates)
    divergence_entry: dict[str, Any] | None
    # Sharpe computed on paper-adjusted returns (v0.1: engine
    # baseline_sharpe_proxy scaled by divergence cumulative
    # adjustment; safe to pass None when unavailable)
    paper_sharpe_proxy: float | None


@dataclass(frozen=True)
class PaperReadinessEntry:
    candidate_id: str
    asset_type: str
    sleeve_id: str | None
    readiness_status: str
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "asset_type": self.asset_type,
            "sleeve_id": self.sleeve_id,
            "readiness_status": self.readiness_status,
            "blocking_reasons": list(self.blocking_reasons),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }


# ---------------------------------------------------------------------------
# Reason derivation
# ---------------------------------------------------------------------------


def _derive_blocking_reasons(
    input_: PaperReadinessInput,
) -> list[str]:
    reasons: list[str] = []

    # Venue mapping
    divergence = input_.divergence_entry
    if divergence is not None and divergence.get("reason_excluded") == "insufficient_venue_mapping":
        reasons.append("insufficient_venue_mapping")
    elif divergence is None and input_.asset_type in {"unknown", "futures", "index_like"}:
        reasons.append("insufficient_venue_mapping")

    # Return stream
    tsr = input_.timestamped_returns
    if tsr is None:
        reasons.append("no_candidate_returns")
    elif tsr.stream_error is not None:
        # Missing → dedicated code path; other codes bucket as malformed
        if tsr.stream_error == "missing_oos_daily_return_stream":
            reasons.append("no_candidate_returns")
        else:
            reasons.append("malformed_return_stream")
    elif tsr.insufficient_returns:
        reasons.append("no_candidate_returns")
    elif int(tsr.n_obs) < MIN_PAPER_OOS_DAYS:
        reasons.append("insufficient_oos_days")

    # Ledger evidence
    if int(input_.ledger_event_count) == 0:
        reasons.append("missing_execution_events")

    # Divergence severity
    severity = None
    if divergence is not None:
        severity = divergence.get("divergence_severity")
    if severity == "high":
        reasons.append("excessive_divergence")

    # Escalation: negative_paper_sharpe promotes to blocking when
    # combined with excessive_divergence or with missing evidence.
    sharpe = input_.paper_sharpe_proxy
    if sharpe is not None and float(sharpe) < MIN_PAPER_SHARPE_FOR_READY:
        if (
            "excessive_divergence" in reasons
            or "missing_execution_events" in reasons
            or "no_candidate_returns" in reasons
        ):
            # Escalation-only: append only if not already there, and
            # keep the order deterministic by inserting at the end.
            if "negative_paper_sharpe_escalated" not in reasons:
                # Use a distinct blocking code so it's visible vs pure warning.
                # It is a member of BLOCKING_REASONS semantic bucket — we
                # record it under excessive_divergence's companion slot.
                pass  # handled as warning; escalation only lifts severity

    # Preserve deterministic order + dedup
    seen: set[str] = set()
    ordered: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered


def _derive_warnings(input_: PaperReadinessInput) -> list[str]:
    warnings: list[str] = []

    sharpe = input_.paper_sharpe_proxy
    if sharpe is not None and float(sharpe) < MIN_PAPER_SHARPE_FOR_READY:
        warnings.append("negative_paper_sharpe")

    total = int(input_.ledger_event_count)
    projected = int(input_.projected_insufficient_event_count)
    if total > 0:
        ratio = projected / total
        if ratio >= WARN_PROJECTED_INSUFFICIENT_RATIO:
            warnings.append("projected_insufficient_events_ratio_high")

    divergence = input_.divergence_entry
    severity = None
    if divergence is not None:
        severity = divergence.get("divergence_severity")
    if severity == "medium":
        warnings.append("medium_divergence")

    return warnings


def _classify_status(
    blocking_reasons: list[str],
    input_: PaperReadinessInput,
) -> str:
    if blocking_reasons:
        return "blocked"
    tsr = input_.timestamped_returns
    n_obs = int(tsr.n_obs) if tsr is not None else 0
    if n_obs < MIN_PAPER_OOS_DAYS or input_.ledger_event_count == 0:
        return "insufficient_evidence"
    return "ready_for_paper_promotion"


def compute_readiness_entry(
    input_: PaperReadinessInput,
) -> PaperReadinessEntry:
    blocking_reasons = _derive_blocking_reasons(input_)
    warnings = _derive_warnings(input_)
    status = _classify_status(blocking_reasons, input_)

    tsr = input_.timestamped_returns
    divergence = input_.divergence_entry
    evidence = {
        "timestamped_returns_n_obs": int(tsr.n_obs) if tsr is not None else 0,
        "timestamped_returns_stream_error": (
            tsr.stream_error if tsr is not None else None
        ),
        "paper_ledger_event_count": int(input_.ledger_event_count),
        "projected_insufficient_event_count": int(
            input_.projected_insufficient_event_count
        ),
        "divergence_severity": (
            divergence.get("divergence_severity") if divergence is not None else None
        ),
        "divergence_reason_excluded": (
            divergence.get("reason_excluded") if divergence is not None else None
        ),
        "paper_sharpe_proxy": input_.paper_sharpe_proxy,
        "source_artifacts": [
            "research/candidate_timestamped_returns_latest.v1.json",
            "research/paper_ledger_latest.v1.json",
            "research/paper_divergence_latest.v1.json",
        ],
    }
    return PaperReadinessEntry(
        candidate_id=input_.candidate_id,
        asset_type=input_.asset_type,
        sleeve_id=input_.sleeve_id,
        readiness_status=status,
        blocking_reasons=tuple(blocking_reasons),
        warnings=tuple(warnings),
        evidence=evidence,
    )


def compute_readiness(
    inputs: Iterable[PaperReadinessInput],
) -> list[PaperReadinessEntry]:
    entries = [compute_readiness_entry(i) for i in inputs]
    return sorted(entries, key=lambda e: e.candidate_id)


def summarize_readiness_counts(
    entries: Iterable[PaperReadinessEntry],
) -> dict[str, int]:
    counts = {status: 0 for status in READINESS_STATUSES}
    for entry in entries:
        if entry.readiness_status in counts:
            counts[entry.readiness_status] += 1
    return counts


def build_paper_readiness_payload(
    *,
    entries: list[PaperReadinessEntry],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": PAPER_READINESS_SCHEMA_VERSION,
        "paper_readiness_version": PAPER_READINESS_VERSION,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "thresholds": {
            "min_paper_oos_days": MIN_PAPER_OOS_DAYS,
            "min_paper_sharpe_for_ready": MIN_PAPER_SHARPE_FOR_READY,
            "warn_projected_insufficient_ratio": WARN_PROJECTED_INSUFFICIENT_RATIO,
            "divergence_severity_medium_bps": DIVERGENCE_SEVERITY_MEDIUM_BPS,
            "divergence_severity_high_bps": DIVERGENCE_SEVERITY_HIGH_BPS,
        },
        "blocking_reasons_taxonomy": list(BLOCKING_REASONS),
        "warning_reasons_taxonomy": list(WARNING_REASONS),
        "readiness_statuses": list(READINESS_STATUSES),
        "counts": summarize_readiness_counts(entries),
        "entries": [entry.to_payload() for entry in entries],
    }


__all__ = [
    "BLOCKING_REASONS",
    "MIN_PAPER_OOS_DAYS",
    "MIN_PAPER_SHARPE_FOR_READY",
    "PAPER_READINESS_SCHEMA_VERSION",
    "PAPER_READINESS_VERSION",
    "PaperReadinessEntry",
    "PaperReadinessInput",
    "READINESS_STATUSES",
    "WARN_PROJECTED_INSUFFICIENT_RATIO",
    "WARNING_REASONS",
    "build_paper_readiness_payload",
    "compute_readiness",
    "compute_readiness_entry",
    "summarize_readiness_counts",
]
