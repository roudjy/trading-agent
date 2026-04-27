"""v3.15.11 — Research evidence ledger (advisory observability).

Aggregated, deterministic snapshot of campaign-level evidence rolled up
from the existing append-only ``campaign_evidence_ledger.jsonl`` plus
the v3.15.9 ``screening_evidence_latest.v1.json`` and the v3.15.7
``candidate_registry_latest.v1.json``.

Positioning (REV: advisory observability, not autonomous control):

- This module is NOT a source of truth. The append-only
  ``campaign_evidence_ledger.jsonl`` remains authoritative for
  campaign events; this module produces a *queryable rolled-up
  snapshot* consumed by Information Gain, Stop-Condition Engine,
  Dead-Zone Detection, and Viability Metrics.
- Pure builder (``build_research_evidence_payload``) — no I/O.
  Thin IO wrapper (``write_research_evidence_artifact``) loads the
  source artifacts and writes via
  ``research._sidecar_io.write_sidecar_atomic``.
- Read-only consumer. Frozen contracts and the source ledger are
  never mutated.
- Missing optional inputs collapse to ``unknown``/empty; the builder
  must never crash a research run.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

EVIDENCE_LEDGER_SCHEMA_VERSION: Final[str] = "1.0"
EVIDENCE_LEDGER_PATH: Final[Path] = Path(
    "research/campaigns/evidence/evidence_ledger_latest.v1.json"
)

CAMPAIGN_EVENT_LEDGER_PATH: Final[Path] = Path(
    "research/campaign_evidence_ledger.jsonl"
)
CAMPAIGN_REGISTRY_PATH: Final[Path] = Path(
    "research/campaign_registry_latest.v1.json"
)
SCREENING_EVIDENCE_PATH: Final[Path] = Path(
    "research/screening_evidence_latest.v1.json"
)
CANDIDATE_REGISTRY_PATH: Final[Path] = Path(
    "research/candidate_registry_latest.v1.json"
)

UNKNOWN: Final[str] = "unknown"

# Outcome buckets derived from campaign_registry literals + ledger
# event types. Kept local so the ledger stays read-only against
# upstream taxonomy mutation.
DEGENERATE_OUTCOMES: Final[frozenset[str]] = frozenset({
    "degenerate_no_survivors",
    "completed_no_survivor",
})
TECHNICAL_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset({
    "technical_failure",
    "worker_crashed",  # legacy, never re-emitted post-v3.15.5; counted if seen.
    "aborted",
})
RESEARCH_REJECTION_OUTCOMES: Final[frozenset[str]] = frozenset({
    "research_rejection",
    "paper_blocked",
    "integrity_failed",
})
PROMOTION_OUTCOMES: Final[frozenset[str]] = frozenset({
    "completed_with_candidates",
})

CANDIDATE_STAGE_EXPLORATORY: Final[str] = "exploratory"
CANDIDATE_STAGE_SHORTLIST: Final[str] = "shortlist"
CANDIDATE_STAGE_PROMOTION: Final[str] = "promotion"
CANDIDATE_STAGE_PAPER: Final[str] = "paper"
CANDIDATE_STAGE_REJECTED: Final[str] = "rejected"


@dataclass(frozen=True)
class _SourceArtifacts:
    """Resolved paths used in the artifact's source_artifacts block."""

    campaign_event_ledger: Path
    campaign_registry: Path
    screening_evidence: Path
    candidate_registry: Path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file. Missing or unreadable → ``[]``."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _load_json(path: Path) -> dict[str, Any] | None:
    """Parse a JSON file. Missing or unreadable → ``None``."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _bucket_for_outcome(outcome: str | None) -> str:
    if outcome is None:
        return UNKNOWN
    if outcome in DEGENERATE_OUTCOMES:
        return "degenerate"
    if outcome in TECHNICAL_FAILURE_OUTCOMES:
        return "technical_failure"
    if outcome in RESEARCH_REJECTION_OUTCOMES:
        return "research_rejection"
    if outcome in PROMOTION_OUTCOMES:
        return "completed_with_candidates"
    return outcome


def _max_iso(a: str | None, b: str | None) -> str | None:
    """Return the larger ISO-8601 string by lexical compare (UTC-Z)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _aggregate_hypothesis_evidence(
    *,
    events: list[dict[str, Any]],
    screening_evidence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Roll up per-(preset_name, hypothesis_id, strategy_family) bucket.

    Hypothesis-id enrichment uses screening_evidence per-candidate
    records when available; otherwise the row reports
    ``hypothesis_id = "unknown"`` and counts only at preset level.
    """
    preset_to_hypothesis: dict[str, str] = {}
    if screening_evidence is not None:
        candidates = screening_evidence.get("candidates") or []
        for record in candidates:
            preset = record.get("preset_name")
            hyp = record.get("hypothesis_id")
            if (
                isinstance(preset, str)
                and isinstance(hyp, str)
                and hyp
                and preset not in preset_to_hypothesis
            ):
                preset_to_hypothesis[preset] = hyp

    @dataclass
    class _Roll:
        preset_name: str
        hypothesis_id: str
        strategy_family: str
        campaign_count: int = 0
        exploratory_pass_count: int = 0
        promotion_candidate_count: int = 0
        paper_ready_count: int = 0
        rejection_count: int = 0
        technical_failure_count: int = 0
        degenerate_count: int = 0
        last_outcome: str = UNKNOWN
        last_seen_at_utc: str | None = None
        reason_counter: Counter[str] = field(default_factory=Counter)

    bucket: dict[tuple[str, str, str], _Roll] = {}

    for ev in events:
        if ev.get("event_type") != "campaign_completed":
            # Only completed campaigns contribute to outcome counts.
            # Spawned/leased/started events feed lineage, not roll-ups.
            continue
        preset = str(ev.get("preset_name") or UNKNOWN)
        family = str(ev.get("strategy_family") or UNKNOWN)
        hypothesis = preset_to_hypothesis.get(preset, UNKNOWN)
        key = (preset, hypothesis, family)
        roll = bucket.get(key)
        if roll is None:
            roll = _Roll(
                preset_name=preset,
                hypothesis_id=hypothesis,
                strategy_family=family,
            )
            bucket[key] = roll
        roll.campaign_count += 1
        outcome = ev.get("outcome")
        bucket_label = _bucket_for_outcome(outcome)
        if bucket_label == "degenerate":
            roll.degenerate_count += 1
        elif bucket_label == "technical_failure":
            roll.technical_failure_count += 1
        elif bucket_label == "research_rejection":
            roll.rejection_count += 1
        elif bucket_label == "completed_with_candidates":
            roll.promotion_candidate_count += 1
        meaningful = ev.get("meaningful_classification")
        if meaningful == "exploratory_pass":
            roll.exploratory_pass_count += 1
        elif meaningful == "paper_ready":
            roll.paper_ready_count += 1
        reason = ev.get("reason_code")
        if reason and reason != "none":
            roll.reason_counter[str(reason)] += 1
        at_utc = ev.get("at_utc")
        if isinstance(at_utc, str) and (
            roll.last_seen_at_utc is None or at_utc > roll.last_seen_at_utc
        ):
            roll.last_seen_at_utc = at_utc
            roll.last_outcome = bucket_label

    rows: list[dict[str, Any]] = []
    for key in sorted(bucket.keys()):
        roll = bucket[key]
        if roll.reason_counter:
            dominant = sorted(
                roll.reason_counter.items(), key=lambda kv: (-kv[1], kv[0])
            )[0][0]
        else:
            dominant = None
        rows.append({
            "hypothesis_id": roll.hypothesis_id,
            "preset_name": roll.preset_name,
            "strategy_family": roll.strategy_family,
            "campaign_count": roll.campaign_count,
            "exploratory_pass_count": roll.exploratory_pass_count,
            "promotion_candidate_count": roll.promotion_candidate_count,
            "paper_ready_count": roll.paper_ready_count,
            "rejection_count": roll.rejection_count,
            "technical_failure_count": roll.technical_failure_count,
            "degenerate_count": roll.degenerate_count,
            "dominant_failure_mode": dominant,
            "last_outcome": roll.last_outcome,
            "last_seen_at_utc": roll.last_seen_at_utc,
        })
    return rows


def _aggregate_failure_modes(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-(scope_type, scope_id, failure_mode) counter with ``last_seen``.

    Scopes: ``preset`` (preset_name), ``strategy_family``,
    ``asset_timeframe`` (currently asset_class only — interval is
    not on ledger events; left as ``"unknown"``-suffix until v4
    enrichment).
    """
    rolled: dict[tuple[str, str, str], dict[str, Any]] = {}

    def _bump(scope_type: str, scope_id: str, mode: str, at_utc: str | None) -> None:
        key = (scope_type, scope_id, mode)
        existing = rolled.get(key)
        if existing is None:
            rolled[key] = {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "failure_mode": mode,
                "count": 1,
                "last_seen_at_utc": at_utc,
            }
            return
        existing["count"] = int(existing["count"]) + 1
        existing["last_seen_at_utc"] = _max_iso(existing.get("last_seen_at_utc"), at_utc)

    for ev in events:
        if ev.get("event_type") != "campaign_completed":
            continue
        outcome = ev.get("outcome")
        if outcome is None or outcome in PROMOTION_OUTCOMES:
            continue
        bucket = _bucket_for_outcome(outcome)
        if bucket == "completed_with_candidates":
            continue
        reason = ev.get("reason_code")
        mode = str(reason) if reason and reason != "none" else bucket
        if mode == UNKNOWN:
            continue
        at_utc = ev.get("at_utc") if isinstance(ev.get("at_utc"), str) else None
        preset = ev.get("preset_name")
        family = ev.get("strategy_family")
        asset = ev.get("asset_class")
        if isinstance(preset, str) and preset:
            _bump("preset", preset, mode, at_utc)
        if isinstance(family, str) and family:
            _bump("strategy_family", family, mode, at_utc)
        if isinstance(asset, str) and asset:
            _bump("asset_timeframe", f"{asset}|{UNKNOWN}", mode, at_utc)

    return sorted(
        rolled.values(),
        key=lambda r: (r["scope_type"], r["scope_id"], r["failure_mode"]),
    )


def _candidate_stage(record: dict[str, Any]) -> str:
    """Map a candidate registry record to a coarse pipeline stage."""
    status = record.get("status") or record.get("classification")
    if isinstance(status, str):
        status_lower = status.lower()
        if status_lower in {"rejected", "screening_reject", "demoted"}:
            return CANDIDATE_STAGE_REJECTED
        if status_lower in {"paper", "paper_validating", "paper_ready"}:
            return CANDIDATE_STAGE_PAPER
        if status_lower in {"candidate", "promoted", "promotion_candidate"}:
            return CANDIDATE_STAGE_PROMOTION
        if status_lower in {"needs_investigation", "shortlist"}:
            return CANDIDATE_STAGE_SHORTLIST
        if status_lower in {"exploratory", "exploratory_pass"}:
            return CANDIDATE_STAGE_EXPLORATORY
    return UNKNOWN


def _aggregate_candidate_lineage(
    *,
    candidate_registry: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One row per candidate observed in the candidate registry.

    Evidence count = number of events on the campaign ledger whose
    ``run_id`` matches the candidate's ``last_run_id`` (or 0 if no
    such linkage is available).
    """
    if candidate_registry is None:
        return []
    rows: list[dict[str, Any]] = []
    candidates = (
        candidate_registry.get("candidates")
        or candidate_registry.get("records")
        or []
    )
    if not isinstance(candidates, list):
        return []
    events_by_run: Counter[str] = Counter()
    for ev in events:
        run_id = ev.get("run_id")
        if isinstance(run_id, str) and run_id:
            events_by_run[run_id] += 1
    for record in candidates:
        if not isinstance(record, dict):
            continue
        candidate_id = record.get("candidate_id")
        if candidate_id is None:
            continue
        run_id = record.get("last_run_id") or record.get("run_id")
        evidence_count = events_by_run.get(str(run_id), 0) if run_id else 0
        rows.append({
            "candidate_id": str(candidate_id),
            "hypothesis_id": (
                str(record.get("hypothesis_id"))
                if record.get("hypothesis_id") is not None
                else UNKNOWN
            ),
            "preset_name": (
                str(record.get("preset_name"))
                if record.get("preset_name") is not None
                else UNKNOWN
            ),
            "origin_campaign_id": (
                str(record.get("origin_campaign_id"))
                if record.get("origin_campaign_id") is not None
                else None
            ),
            "current_stage": _candidate_stage(record),
            "last_verdict": (
                str(record.get("status") or record.get("classification") or UNKNOWN)
            ),
            "evidence_count": int(evidence_count),
        })
    rows.sort(key=lambda r: (r["preset_name"], r["candidate_id"]))
    return rows


def build_research_evidence_payload(
    *,
    run_id: str | None,
    col_campaign_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    events: list[dict[str, Any]],
    screening_evidence: dict[str, Any] | None,
    candidate_registry: dict[str, Any] | None,
    sources: _SourceArtifacts | None = None,
) -> dict[str, Any]:
    """Build the full evidence ledger payload (pure, no I/O)."""
    src = sources or _SourceArtifacts(
        campaign_event_ledger=CAMPAIGN_EVENT_LEDGER_PATH,
        campaign_registry=CAMPAIGN_REGISTRY_PATH,
        screening_evidence=SCREENING_EVIDENCE_PATH,
        candidate_registry=CANDIDATE_REGISTRY_PATH,
    )

    hypothesis_evidence = _aggregate_hypothesis_evidence(
        events=events,
        screening_evidence=screening_evidence,
    )
    failure_mode_counts = _aggregate_failure_modes(events)
    candidate_lineage = _aggregate_candidate_lineage(
        candidate_registry=candidate_registry,
        events=events,
    )

    payload: dict[str, Any] = {
        "schema_version": EVIDENCE_LEDGER_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "col_campaign_id": col_campaign_id,
        "source_artifacts": {
            "campaign_event_ledger": str(src.campaign_event_ledger).replace(
                "\\", "/"
            ),
            "campaign_registry": str(src.campaign_registry).replace("\\", "/"),
            "screening_evidence": str(src.screening_evidence).replace(
                "\\", "/"
            ),
            "candidate_registry": str(src.candidate_registry).replace(
                "\\", "/"
            ),
        },
        "summary": {
            "campaign_count": sum(
                int(row["campaign_count"]) for row in hypothesis_evidence
            ),
            "hypothesis_count": len(hypothesis_evidence),
            "failure_mode_count": len(failure_mode_counts),
            "candidate_lineage_count": len(candidate_lineage),
        },
        "hypothesis_evidence": hypothesis_evidence,
        "failure_mode_counts": failure_mode_counts,
        "candidate_lineage": candidate_lineage,
    }
    return payload


def write_research_evidence_artifact(
    *,
    run_id: str | None,
    col_campaign_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    output_path: Path = EVIDENCE_LEDGER_PATH,
    campaign_event_ledger_path: Path = CAMPAIGN_EVENT_LEDGER_PATH,
    campaign_registry_path: Path = CAMPAIGN_REGISTRY_PATH,
    screening_evidence_path: Path = SCREENING_EVIDENCE_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
) -> dict[str, Any]:
    """Load source artifacts, build payload, write atomic sidecar.

    Returns the written payload so callers (lifecycle hook, tests)
    can chain further analysis without re-reading from disk.
    """
    events = _load_jsonl(campaign_event_ledger_path)
    screening = _load_json(screening_evidence_path)
    candidates = _load_json(candidate_registry_path)
    sources = _SourceArtifacts(
        campaign_event_ledger=campaign_event_ledger_path,
        campaign_registry=campaign_registry_path,
        screening_evidence=screening_evidence_path,
        candidate_registry=candidate_registry_path,
    )
    payload = build_research_evidence_payload(
        run_id=run_id,
        col_campaign_id=col_campaign_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        events=events,
        screening_evidence=screening,
        candidate_registry=candidates,
        sources=sources,
    )
    write_sidecar_atomic(output_path, payload)
    return payload


__all__ = [
    "CANDIDATE_STAGE_EXPLORATORY",
    "CANDIDATE_STAGE_PAPER",
    "CANDIDATE_STAGE_PROMOTION",
    "CANDIDATE_STAGE_REJECTED",
    "CANDIDATE_STAGE_SHORTLIST",
    "DEGENERATE_OUTCOMES",
    "EVIDENCE_LEDGER_PATH",
    "EVIDENCE_LEDGER_SCHEMA_VERSION",
    "PROMOTION_OUTCOMES",
    "RESEARCH_REJECTION_OUTCOMES",
    "TECHNICAL_FAILURE_OUTCOMES",
    "UNKNOWN",
    "build_research_evidence_payload",
    "write_research_evidence_artifact",
]
