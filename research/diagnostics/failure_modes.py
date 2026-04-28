"""Failure-mode aggregation observability module.

Reads the campaign registry (JSON) and the campaign evidence ledger
(JSONL, bounded tail) and produces a descriptive failure-mode
distribution. Pure aggregation — never reclassifies anything in the
source artifacts and never recommends an action.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from research._sidecar_io import write_sidecar_atomic

from .clock import default_now_utc, to_iso_z
from .io import read_json_safe, read_jsonl_tail_safe
from .paths import (
    CAMPAIGN_EVIDENCE_LEDGER_PATH,
    CAMPAIGN_REGISTRY_PATH,
    FAILURE_MODES_PATH,
    MAX_LEDGER_LINES,
    MAX_LEDGER_TAIL_BYTES,
    OBSERVABILITY_SCHEMA_VERSION,
)

# Outcome class taxonomy. Stable list; order is the rendering order.
#
# v3.15.15.4 adds ``"paper_blocked"`` as a dedicated class. Frontend and
# downstream consumers iterate over ``campaigns_by_outcome_class`` keys
# dynamically, so the addition is non-breaking. The class captures
# campaigns where a candidate was found but paper-readiness blocked
# promotion (e.g. ``insufficient_oos_days``, ``excessive_divergence``);
# folding this into ``completed_no_survivor`` would have been
# misleading because a survivor existed.
OUTCOME_CLASSES: tuple[str, ...] = (
    "technical_failure",
    "research_rejection",
    "degenerate_no_survivors",
    "completed_no_survivor",
    "completed_with_survivor",
    "paper_blocked",
    "running",
    "canceled",
    "unknown",
)

# Mapping from raw ``outcome`` / ``state`` strings to outcome_class.
# Any value not in this table is reported as ``unknown`` — never
# silently dropped.
#
# v3.15.15.4: extends the table with the launcher's actual emitted
# outcome literals (see ``research/campaign_launcher.py`` lines
# ~1378-1453, v3.15.5+ outcome vocabulary). Existing entries are
# unchanged — a regression test guarantees identical classification
# of every previously-recognised (outcome, failure_reason) pair.
_OUTCOME_TO_CLASS: dict[str, str] = {
    # --- Existing (semantics unchanged) ---
    "completed": "completed_no_survivor",  # default; refined via failure_reason
    "no_signal": "research_rejection",
    "near_pass": "research_rejection",
    "failed": "technical_failure",  # default; refined via failure_reason
    "canceled": "canceled",
    "running": "running",
    # --- v3.15.15.4: launcher-literal outcomes (additive only) ---
    "completed_with_candidates": "completed_with_survivor",
    "completed_no_survivor": "completed_no_survivor",
    "degenerate_no_survivors": "degenerate_no_survivors",
    "technical_failure": "technical_failure",
    "research_rejection": "research_rejection",
    "paper_blocked": "paper_blocked",
    "integrity_failed": "technical_failure",
    "aborted": "canceled",
    "canceled_duplicate": "canceled",
    "canceled_upstream_stale": "canceled",
    # --- Backward-compat: pre-v3.15.5 ledgers may still contain this. ---
    "worker_crashed": "technical_failure",
}

# Failure-reason hints that flip outcome_class to a more specific
# bucket. Conservative: only well-known reason codes are remapped;
# everything else stays as the outcome's default class.
_FAILURE_REASON_TO_CLASS: dict[str, str] = {
    "screening_no_survivors": "degenerate_no_survivors",
    "no_survivor": "completed_no_survivor",
    "candidate_promoted": "completed_with_survivor",
    "promotion_pass": "completed_with_survivor",
}


def _classify(outcome: str | None, failure_reason: str | None) -> str:
    if isinstance(failure_reason, str) and failure_reason in _FAILURE_REASON_TO_CLASS:
        return _FAILURE_REASON_TO_CLASS[failure_reason]
    if isinstance(outcome, str) and outcome in _OUTCOME_TO_CLASS:
        return _OUTCOME_TO_CLASS[outcome]
    return "unknown"


def _registry_campaigns(payload: Any) -> list[dict[str, Any]]:
    """Extract a list of campaign records from registry payload.

    Tolerates both shapes the registry has used historically: a list
    under ``campaigns`` or a dict keyed by campaign_id.
    """
    if not isinstance(payload, dict):
        return []
    raw = payload.get("campaigns")
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict):
        return [c for c in raw.values() if isinstance(c, dict)]
    return []


def _ledger_failure_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter ledger events down to ones that look like failure markers.

    Conservative: include only events whose ``outcome`` is ``"failed"``
    or whose ``event_type``/``kind`` mentions failure. Everything else
    is dropped from the failure-mode aggregation (it's still counted
    in throughput separately).
    """
    out: list[dict[str, Any]] = []
    for e in events:
        outcome = e.get("outcome")
        kind = e.get("event_type") or e.get("kind") or ""
        if outcome == "failed":
            out.append(e)
        elif isinstance(kind, str) and "fail" in kind.lower():
            out.append(e)
    return out


def _bucket_counts(
    items: Iterable[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    """Return ``[{name, count}, ...]`` sorted by (-count, name).

    Items missing the field or having a non-string value are not
    counted. Sort key is fully deterministic.
    """
    counter: Counter[str] = Counter()
    for it in items:
        value = it.get(field)
        if isinstance(value, str) and value:
            counter[value] += 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _by_outcome(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Outcome distribution across registry campaigns."""
    counter: Counter[str] = Counter()
    for r in records:
        outcome = r.get("outcome")
        if isinstance(outcome, str) and outcome:
            counter[outcome] += 1
        else:
            counter["unknown"] += 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _by_outcome_class(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {cls: 0 for cls in OUTCOME_CLASSES}
    for r in records:
        cls = _classify(r.get("outcome"), r.get("failure_reason"))
        counts[cls] = counts.get(cls, 0) + 1
    return counts


def _repeated_failure_clusters(
    failed_records: list[dict[str, Any]],
    *,
    min_repeat: int = 3,
) -> list[dict[str, Any]]:
    """Identify (preset, failure_reason) pairs that appear ``>= min_repeat`` times.

    Pure rule. ``min_repeat`` is exposed as a knob in case tests need
    a smaller cluster size.
    """
    counter: Counter[tuple[str, str]] = Counter()
    for r in failed_records:
        preset = r.get("preset") or r.get("preset_name")
        reason = r.get("failure_reason")
        if isinstance(preset, str) and isinstance(reason, str):
            counter[(preset, reason)] += 1
    out = [
        {"preset": preset, "failure_reason": reason, "count": count}
        for (preset, reason), count in counter.items()
        if count >= min_repeat
    ]
    out.sort(key=lambda x: (-x["count"], x["preset"], x["failure_reason"]))
    return out


def compute_failure_mode_distribution(
    *,
    registry_payload: Any | None = None,
    ledger_events: list[dict[str, Any]] | None = None,
    registry_state: str | None = None,
    ledger_state: str | None = None,
    ledger_meta: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Pure aggregation: compute failure-mode distribution from inputs.

    Tests call this directly with synthetic inputs to assert
    deterministic output. The CLI / production caller goes through
    ``build_failure_modes_artifact`` below to load real artifacts.
    """
    when = now_utc or default_now_utc()

    campaigns = _registry_campaigns(registry_payload)
    failed_campaigns = [
        c
        for c in campaigns
        if _classify(c.get("outcome"), c.get("failure_reason")) == "technical_failure"
        or c.get("outcome") == "failed"
    ]
    failed_events = _ledger_failure_events(ledger_events or [])

    # Combine ledger + registry-failed for richer breakdowns. Each
    # source contributes uniformly; we never weight one over the other.
    combined = failed_campaigns + failed_events

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "source": {
            "registry_state": registry_state,
            "ledger_state": ledger_state,
            "ledger_lines_consumed": (ledger_meta or {}).get("lines_consumed"),
            "ledger_truncated": (ledger_meta or {}).get("truncated"),
            "ledger_partial_trailing_dropped": (ledger_meta or {}).get(
                "partial_trailing_line_dropped"
            ),
            "ledger_parse_errors": (ledger_meta or {}).get("parse_errors"),
            "max_ledger_lines": MAX_LEDGER_LINES,
        },
        "total_campaigns_observed": len(campaigns),
        "total_failure_events_observed": len(combined),
        "campaigns_by_outcome": _by_outcome(campaigns),
        "campaigns_by_outcome_class": _by_outcome_class(campaigns),
        "top_failure_reasons": _bucket_counts(combined, "failure_reason"),
        "by_preset": _bucket_counts(combined, "preset")
        + [],  # explicit copy for clarity
        "by_preset_name": _bucket_counts(combined, "preset_name"),
        "by_hypothesis_id": _bucket_counts(combined, "hypothesis_id"),
        "by_strategy_family": _bucket_counts(combined, "family")
        + _bucket_counts(combined, "strategy_family"),
        "by_asset": _bucket_counts(combined, "asset"),
        "by_timeframe": _bucket_counts(combined, "timeframe"),
        "by_campaign_type": _bucket_counts(combined, "campaign_type"),
        "by_worker_id": _bucket_counts(combined, "worker_id"),
        "repeated_failure_clusters": _repeated_failure_clusters(combined),
        "technical_vs_research_failure_counts": {
            "technical_failure": sum(
                1
                for r in combined
                if _classify(r.get("outcome"), r.get("failure_reason"))
                == "technical_failure"
            ),
            "research_rejection": sum(
                1
                for r in combined
                if _classify(r.get("outcome"), r.get("failure_reason"))
                == "research_rejection"
            ),
            "degenerate_no_survivors": sum(
                1
                for r in combined
                if _classify(r.get("outcome"), r.get("failure_reason"))
                == "degenerate_no_survivors"
            ),
            "unknown": sum(
                1
                for r in combined
                if _classify(r.get("outcome"), r.get("failure_reason")) == "unknown"
            ),
        },
        "unknown_or_unclassified_count": sum(
            1
            for r in combined
            if _classify(r.get("outcome"), r.get("failure_reason")) == "unknown"
        ),
    }


def build_failure_modes_artifact(
    *,
    now_utc: datetime | None = None,
    registry_path: Path = CAMPAIGN_REGISTRY_PATH,
    ledger_path: Path = CAMPAIGN_EVIDENCE_LEDGER_PATH,
) -> dict[str, Any]:
    """Load real artifacts and produce the failure-mode payload."""
    registry = read_json_safe(registry_path)
    ledger = read_jsonl_tail_safe(
        ledger_path,
        max_lines=MAX_LEDGER_LINES,
        max_tail_bytes=MAX_LEDGER_TAIL_BYTES,
    )

    return compute_failure_mode_distribution(
        registry_payload=registry.payload if registry.state == "valid" else None,
        ledger_events=ledger.events,
        registry_state=registry.state,
        ledger_state=ledger.state,
        ledger_meta={
            "lines_consumed": ledger.lines_consumed,
            "truncated": ledger.truncated,
            "partial_trailing_line_dropped": ledger.partial_trailing_line_dropped,
            "parse_errors": ledger.parse_errors,
        },
        now_utc=now_utc,
    )


def write_failure_modes(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    target = path if path is not None else FAILURE_MODES_PATH
    if "observability" not in str(target).replace("\\", "/").split("/"):
        raise RuntimeError(
            "write_failure_modes refuses to write outside research/observability/"
        )
    write_sidecar_atomic(target, payload)


__all__ = [
    "OUTCOME_CLASSES",
    "build_failure_modes_artifact",
    "compute_failure_mode_distribution",
    "write_failure_modes",
]
