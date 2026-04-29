"""Failure-mode aggregation observability module.

Reads the campaign registry (JSON), the campaign evidence ledger
(JSONL, bounded tail), and (v3.15.15.6) the campaign digest as a
fallback source for ``top_failure_reasons``. Produces a descriptive
failure-mode distribution. Pure aggregation — never reclassifies
anything in the source artifacts and never recommends an action.

v3.15.15.6 enrichments (additive, behavior-pure):

* ``reason_code`` is read as a failure-reason alias when
  ``failure_reason`` is absent. Both fields are preserved when
  present; if they conflict, ``failure_reason`` wins and a
  ``conflicting_failure_reason_fields`` limitation is emitted.
* ``lease.worker_id`` is consulted when top-level ``worker_id`` is
  missing.
* ``by_campaign_type`` and ``by_meaningful_classification`` are
  computed from ALL campaigns (not just the narrow failed-records
  filter) so dimensions are populated even in registry-only mode.
* ``_ledger_failure_events`` widens to recognise launcher-literal
  outcomes (``degenerate_no_survivors``, ``technical_failure``,
  ``worker_crashed``, ``research_rejection``, ``no_signal``,
  ``near_pass``, ``integrity_failed``, ``paper_blocked``).
* ``_repeated_failure_clusters`` uses a full / partial / weak
  fallback-key strategy and reports ``cluster_key_quality`` so
  registry-only mode produces useful clusters.
* A new ``diagnostic_context`` block documents diagnostic mode,
  evidence availability, limitations, and
  future-writer-enrichment requirements.
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
    RESEARCH_DIR,
)

# v3.15.15.6 — additional sidecar paths used as fallback / context inputs.
CAMPAIGN_DIGEST_PATH: Path = RESEARCH_DIR / "campaign_digest_latest.v1.json"
PUBLIC_ARTIFACT_STATUS_PATH: Path = (
    RESEARCH_DIR / "public_artifact_status_latest.v1.json"
)
SCREENING_EVIDENCE_PATH: Path = RESEARCH_DIR / "screening_evidence_latest.v1.json"
ROLLED_UP_LEDGER_PATH: Path = (
    RESEARCH_DIR / "campaigns" / "evidence" / "evidence_ledger_latest.v1.json"
)
SPAWN_PROPOSALS_PATH: Path = (
    RESEARCH_DIR / "campaigns" / "evidence" / "spawn_proposals_latest.v1.json"
)


# v3.15.15.6 — fields the diagnostics layer would surface if the launcher
# emitted them. Reported in ``diagnostic_context.future_writer_enrichment_required``
# whenever the corresponding value is missing across all observed records.
FUTURE_WRITER_FIELDS: tuple[str, ...] = (
    "campaign_record.hypothesis_id",
    "campaign_record.timeframe",
    "campaign_record.asset",
    "campaign_record.universe",
    "campaign_record.strategy_family (key present, always null)",
    "campaign_record.asset_class (key present, always null)",
    "campaign_evidence_ledger.jsonl (entire artifact)",
    "screening_evidence_latest.v1.json (entire artifact)",
    "campaigns/evidence/evidence_ledger_latest.v1.json (rolled-up)",
    "campaigns/evidence/spawn_proposals_latest.v1.json",
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


# v3.15.15.6 helpers ---------------------------------------------------------


def _get_first(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string under any key in ``keys``.

    Tolerates None / non-string values silently. Used by the
    dimension extractors so callers don't have to write the same
    fallback chain repeatedly.
    """
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _effective_failure_reason(
    record: dict[str, Any],
) -> tuple[str | None, bool]:
    """Resolve the effective failure-reason for a record.

    Returns ``(reason, conflicts)`` where:

    * ``reason`` is the first non-empty string in ``failure_reason``
      then ``reason_code`` (the launcher's actual emit field — see
      research/campaign_launcher.py emit paths). When both fields are
      present and disagree, ``failure_reason`` wins per the v3.15.15.6
      brief.
    * ``conflicts`` is True iff both fields are present, both are
      strings, and they differ. The aggregator emits
      ``conflicting_failure_reason_fields`` as a limitation when any
      observed record has ``conflicts=True``.
    """
    fr = record.get("failure_reason")
    rc = record.get("reason_code")
    fr_str = fr if isinstance(fr, str) and fr else None
    rc_str = rc if isinstance(rc, str) and rc else None
    if fr_str and rc_str and fr_str != rc_str:
        return fr_str, True
    return fr_str or rc_str, False


def _extract_worker_id(record: dict[str, Any]) -> str | None:
    """Read worker_id from top-level or from the nested ``lease`` block."""
    top = record.get("worker_id")
    if isinstance(top, str) and top:
        return top
    lease = record.get("lease")
    if isinstance(lease, dict):
        nested = lease.get("worker_id")
        if isinstance(nested, str) and nested:
            return nested
    return None


def _enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with v3.15.15.6 alias keys filled in.

    The original record is not mutated. Aliases populated:

    * ``failure_reason`` — backed by ``reason_code`` when absent.
    * ``preset`` — alias of ``preset_name`` when absent.
    * ``worker_id`` — flattened from ``lease.worker_id`` when absent.
    * ``family`` — alias of ``strategy_family`` when absent.

    These are all READ aliases; the on-disk artifact is untouched.
    The function is the canonical lookup entrypoint for every
    dimension aggregation in this module.
    """
    if not isinstance(record, dict):
        return {}
    enriched = dict(record)
    if "failure_reason" not in enriched or not isinstance(
        enriched.get("failure_reason"), str
    ):
        reason, _conflict = _effective_failure_reason(record)
        if reason is not None:
            enriched["failure_reason"] = reason
    if "preset" not in enriched or not isinstance(enriched.get("preset"), str):
        preset = record.get("preset_name")
        if isinstance(preset, str) and preset:
            enriched["preset"] = preset
    worker_id = _extract_worker_id(record)
    if worker_id is not None and not isinstance(enriched.get("worker_id"), str):
        enriched["worker_id"] = worker_id
    if "family" not in enriched or not isinstance(enriched.get("family"), str):
        family = record.get("strategy_family")
        if isinstance(family, str) and family:
            enriched["family"] = family
    return enriched


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


_LEDGER_FAILURE_OUTCOMES: frozenset[str] = frozenset(
    {
        "failed",
        # v3.15.15.6: launcher-literal outcomes the original narrow
        # filter missed. _classify maps these to the right outcome
        # class; the aggregator below counts each contributing record.
        "degenerate_no_survivors",
        "technical_failure",
        "worker_crashed",
        "research_rejection",
        "no_signal",
        "near_pass",
        "integrity_failed",
        "paper_blocked",
    }
)


def _ledger_failure_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter ledger events down to ones that look like failure markers.

    v3.15.15.6 widens the filter: a ledger event counts as a failure
    if its ``outcome`` is in the launcher's failure outcome
    vocabulary (``_LEDGER_FAILURE_OUTCOMES``) OR if its
    ``event_type``/``kind`` contains "fail" / "reject". Everything
    else stays out of the failure-mode aggregation.

    Records returned are passed through ``_enrich_record`` so the
    downstream aggregations can rely on the alias-filled keys.
    """
    out: list[dict[str, Any]] = []
    for e in events:
        outcome = e.get("outcome")
        kind = e.get("event_type") or e.get("kind") or ""
        accept = False
        if isinstance(outcome, str) and outcome in _LEDGER_FAILURE_OUTCOMES:
            accept = True
        elif isinstance(kind, str):
            kl = kind.lower()
            if "fail" in kl or "reject" in kl:
                accept = True
        if accept:
            out.append(_enrich_record(e))
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


def _cluster_key_for(
    record: dict[str, Any],
) -> tuple[tuple[Any, ...], str] | None:
    """Build the most specific cluster key the record can support.

    Returns ``(key_tuple, key_quality)`` or None if the record lacks
    even the weak fallback fields. ``key_tuple`` always carries six
    positional elements (with ``None`` placeholders) so the resulting
    counter can be projected back to a stable JSON shape.

    Quality tiers:

    * ``full``    — outcome_class + preset_name + hypothesis_id +
      strategy_family + timeframe + asset all present
    * ``partial`` — outcome_class + preset_name (other fields may be
      None)
    * ``weak``    — outcome_class + campaign_type (preset_name absent)
    """
    outcome_class = _classify(
        record.get("outcome"), record.get("failure_reason")
    )
    preset_name = _get_first(record, ("preset_name", "preset"))
    hypothesis_id = _get_first(record, ("hypothesis_id",))
    strategy_family = _get_first(record, ("strategy_family", "family"))
    timeframe = _get_first(record, ("timeframe",))
    asset = _get_first(record, ("asset",))
    campaign_type = _get_first(record, ("campaign_type",))

    if (
        preset_name
        and hypothesis_id
        and strategy_family
        and timeframe
        and asset
    ):
        return (
            (
                outcome_class,
                preset_name,
                hypothesis_id,
                strategy_family,
                timeframe,
                asset,
            ),
            "full",
        )
    if preset_name:
        return (
            (
                outcome_class,
                preset_name,
                hypothesis_id,
                strategy_family,
                timeframe,
                asset,
            ),
            "partial",
        )
    if campaign_type:
        return (
            (outcome_class, None, None, None, None, None),
            "weak",
        )
    return None


def _repeated_failure_clusters(
    failed_records: list[dict[str, Any]],
    *,
    min_repeat: int = 2,
) -> list[dict[str, Any]]:
    """Identify repeated failure clusters across the failed-records set.

    v3.15.15.6 enrichments:

    * Cluster key uses ``outcome_class`` instead of the raw
      ``failure_reason``, so degenerate / technical / research
      buckets aggregate cleanly.
    * Falls back to ``preset_name``-only or
      ``campaign_type``-only keys when richer fields are missing,
      reporting ``cluster_key_quality`` so the consumer knows which
      tier was used.
    * Threshold lowered to ``count >= 2`` (was 3) per the brief.

    Output rows:

    ::

        {
            "count": <int>,
            "outcome_class": <str>,
            "preset_name": <str | None>,
            "hypothesis_id": <str | None>,
            "strategy_family": <str | None>,
            "timeframe": <str | None>,
            "asset": <str | None>,
            "cluster_key_quality": "full" | "partial" | "weak",
            "source": "registry"
        }
    """
    if min_repeat < 1:
        min_repeat = 1
    counter: Counter[tuple[Any, ...]] = Counter()
    quality_for_key: dict[tuple[Any, ...], str] = {}

    for r in failed_records:
        result = _cluster_key_for(r)
        if result is None:
            continue
        key, quality = result
        counter[key] += 1
        # Keep the highest-quality observed quality for the key
        # (full > partial > weak). Records hitting the same key with
        # different quality tiers are grouped under the same row.
        ranks = {"full": 3, "partial": 2, "weak": 1}
        existing = quality_for_key.get(key)
        if existing is None or ranks[quality] > ranks[existing]:
            quality_for_key[key] = quality

    out: list[dict[str, Any]] = []
    for key, count in counter.items():
        if count < min_repeat:
            continue
        outcome_class, preset_name, hypothesis_id, family, timeframe, asset = key
        out.append(
            {
                "count": int(count),
                "outcome_class": outcome_class,
                "preset_name": preset_name,
                "hypothesis_id": hypothesis_id,
                "strategy_family": family,
                "timeframe": timeframe,
                "asset": asset,
                "cluster_key_quality": quality_for_key[key],
                "source": "registry",
            }
        )
    out.sort(
        key=lambda x: (
            -x["count"],
            x["outcome_class"] or "",
            x["preset_name"] or "",
            x["hypothesis_id"] or "",
        )
    )
    return out


def _diagnostic_context(
    *,
    registry_state: str | None,
    ledger_state: str | None,
    digest_state: str | None,
    screening_evidence_state: str | None,
    rolled_up_ledger_state: str | None,
    spawn_proposals_state: str | None,
    has_failure_reason_anywhere: bool,
    has_conflicting_failure_reason_fields: bool,
    has_any_hypothesis_id: bool,
    has_any_timeframe: bool,
    has_any_asset: bool,
    has_any_strategy_family: bool,
    has_any_asset_class: bool,
) -> dict[str, Any]:
    """Build the v3.15.15.6 ``diagnostic_context`` block.

    Pure rule-based: every field is a literal lookup or a derived
    boolean. No interpretation beyond what the input flags say.
    """
    registry_available = registry_state == "valid"
    ledger_available = ledger_state == "valid"
    digest_available = digest_state == "valid"
    screening_evidence_available = screening_evidence_state == "valid"
    rolled_up_ledger_available = rolled_up_ledger_state == "valid"
    spawn_proposals_available = spawn_proposals_state == "valid"

    if ledger_available:
        diagnostic_mode = "ledger_enriched"
    elif digest_available and registry_available:
        diagnostic_mode = "registry_plus_digest_enriched"
    elif registry_available:
        diagnostic_mode = "registry_only"
    else:
        diagnostic_mode = "registry_only"

    missing: list[str] = []
    if not ledger_available:
        missing.append("research/campaign_evidence_ledger.jsonl")
    if not screening_evidence_available:
        missing.append("research/screening_evidence_latest.v1.json")
    if not rolled_up_ledger_available:
        missing.append("research/campaigns/evidence/evidence_ledger_latest.v1.json")
    if not spawn_proposals_available:
        missing.append("research/campaigns/evidence/spawn_proposals_latest.v1.json")

    limitations: list[str] = []
    if registry_state == "absent":
        limitations.append("registry_absent")
    elif registry_state in {"invalid_json", "unreadable"}:
        limitations.append("registry_corrupt")
    if not ledger_available:
        limitations.append("campaign_evidence_ledger_absent")
    if not screening_evidence_available:
        limitations.append("screening_evidence_absent")
    if not rolled_up_ledger_available:
        limitations.append("rolled_up_evidence_ledger_absent")
    if not spawn_proposals_available:
        limitations.append("spawn_proposals_absent")
    if diagnostic_mode == "registry_only":
        limitations.append("registry_only_mode")
    elif diagnostic_mode == "registry_plus_digest_enriched":
        limitations.append("registry_plus_digest_only_mode")
    if not has_failure_reason_anywhere and registry_available:
        limitations.append("failure_reason_detail_unavailable")
    if has_conflicting_failure_reason_fields:
        limitations.append("conflicting_failure_reason_fields")
    if registry_available and not has_any_hypothesis_id:
        limitations.append("hypothesis_id_missing_from_source_artifact")
    if registry_available and not has_any_strategy_family:
        limitations.append("strategy_family_field_present_but_unpopulated_by_writer")
    if registry_available and not has_any_asset_class:
        limitations.append("asset_class_field_present_but_unpopulated_by_writer")
    if registry_available and not has_any_timeframe:
        limitations.append("timeframe_derivable_from_preset_only")
    if registry_available and not has_any_asset and not has_any_timeframe:
        limitations.append("asset_timeframe_fields_absent")

    cluster_analysis_available = (
        registry_available or ledger_available or digest_available
    )

    # Evidence completeness:
    # sufficient = ledger+screening present
    # partial = registry+digest available, ledger/screening absent
    # insufficient = registry only with no failure_reason detail
    # unavailable = registry absent or corrupt
    if not registry_available:
        evidence_status = "unavailable"
    elif ledger_available and screening_evidence_available:
        evidence_status = "sufficient"
    elif registry_available and (
        not ledger_available or not screening_evidence_available
    ):
        evidence_status = "partial"
        if (
            not has_failure_reason_anywhere
            and not ledger_available
            and not screening_evidence_available
        ):
            evidence_status = "insufficient"
    else:
        evidence_status = "partial"

    return {
        "diagnostic_mode": diagnostic_mode,
        "evidence_available": registry_available,
        "registry_available": registry_available,
        "queue_available": False,  # set externally if needed
        "digest_available": digest_available,
        "ledger_available": ledger_available,
        "screening_evidence_available": screening_evidence_available,
        "rolled_up_ledger_available": rolled_up_ledger_available,
        "spawn_proposals_available": spawn_proposals_available,
        "failure_reason_detail_available": has_failure_reason_anywhere,
        "cluster_analysis_available": cluster_analysis_available,
        "diagnostic_evidence_status": evidence_status,
        "missing_evidence_artifacts": sorted(missing),
        "limitations": sorted(limitations),
        "future_writer_enrichment_required": list(FUTURE_WRITER_FIELDS),
    }


def _by_meaningful_classification(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate ``meaningful_classification`` across records.

    Distinct from ``meaningful_by_classification_from_digest`` (which
    is a passthrough); this one is computed from the registry records
    diagnostics actually saw, so it stays consistent with
    ``total_campaigns_observed``.
    """
    counter: Counter[str] = Counter()
    for r in records:
        v = r.get("meaningful_classification")
        if isinstance(v, str) and v:
            counter[v] += 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _digest_top_failure_reasons(
    digest_payload: Any | None,
) -> list[dict[str, Any]]:
    """Extract ``top_failure_reasons`` from the digest as a labelled fallback.

    Each row is tagged ``source="digest"`` so consumers can tell that
    these counts came from the launcher's per-tick digest aggregation
    rather than from registry / ledger processing here.
    """
    if not isinstance(digest_payload, dict):
        return []
    raw = digest_payload.get("top_failure_reasons")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("reason") or entry.get("failure_reason")
        count = entry.get("count")
        if isinstance(name, str) and name and isinstance(count, (int, float)):
            out.append({"name": name, "count": int(count), "source": "digest"})
    return out


def compute_failure_mode_distribution(
    *,
    registry_payload: Any | None = None,
    ledger_events: list[dict[str, Any]] | None = None,
    digest_payload: Any | None = None,
    registry_state: str | None = None,
    ledger_state: str | None = None,
    digest_state: str | None = None,
    screening_evidence_state: str | None = None,
    rolled_up_ledger_state: str | None = None,
    spawn_proposals_state: str | None = None,
    ledger_meta: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Pure aggregation: compute failure-mode distribution from inputs.

    Tests call this directly with synthetic inputs to assert
    deterministic output. The CLI / production caller goes through
    ``build_failure_modes_artifact`` below to load real artifacts.

    v3.15.15.6 changes:

    * Records are passed through ``_enrich_record`` so ``reason_code``
      and ``lease.worker_id`` aliases populate downstream buckets.
    * ``by_campaign_type`` and ``by_meaningful_classification`` aggregate
      across ALL campaigns (not just the failed-records subset) so they
      stay populated in registry-only mode.
    * ``technical_vs_research_failure_counts`` is now computed against
      ALL campaigns and includes new buckets for
      ``degenerate_no_survivors`` and ``paper_blocked``.
    * ``top_failure_reasons`` falls back to the digest's pre-computed
      ``top_failure_reasons`` when registry-derived reasons are empty.
    * A new ``diagnostic_context`` block reports diagnostic mode,
      evidence availability, limitations, and
      future-writer-enrichment requirements.
    """
    when = now_utc or default_now_utc()

    raw_campaigns = _registry_campaigns(registry_payload)
    campaigns = [_enrich_record(c) for c in raw_campaigns]
    failed_campaigns = [
        c
        for c in campaigns
        if _classify(c.get("outcome"), c.get("failure_reason"))
        in (
            "technical_failure",
            "degenerate_no_survivors",
            "research_rejection",
            "paper_blocked",
        )
        or c.get("outcome") == "failed"
    ]
    failed_events = _ledger_failure_events(ledger_events or [])

    # Combine ledger + registry-failed for richer breakdowns. Each
    # source contributes uniformly; we never weight one over the other.
    combined = failed_campaigns + failed_events

    # Detect whether ANY observed record carries failure_reason detail
    # (after the reason_code alias fill-in done by _enrich_record).
    has_failure_reason_anywhere = any(
        isinstance(r.get("failure_reason"), str) and r.get("failure_reason")
        for r in combined
    )
    # Detect whether any record had failure_reason and reason_code
    # diverging — emit ``conflicting_failure_reason_fields`` if so.
    has_conflict = False
    for raw in raw_campaigns:
        _, conflict = _effective_failure_reason(raw)
        if conflict:
            has_conflict = True
            break
    if not has_conflict:
        for ev in ledger_events or []:
            _, conflict = _effective_failure_reason(ev)
            if conflict:
                has_conflict = True
                break

    has_any_hypothesis_id = any(
        isinstance(c.get("hypothesis_id"), str) and c.get("hypothesis_id")
        for c in campaigns
    )
    has_any_timeframe = any(
        isinstance(c.get("timeframe"), str) and c.get("timeframe")
        for c in campaigns
    )
    has_any_asset = any(
        isinstance(c.get("asset"), str) and c.get("asset") for c in campaigns
    )
    has_any_strategy_family = any(
        isinstance(c.get("strategy_family"), str) and c.get("strategy_family")
        for c in campaigns
    )
    has_any_asset_class = any(
        isinstance(c.get("asset_class"), str) and c.get("asset_class")
        for c in campaigns
    )

    # top_failure_reasons: registry-derived first, digest fallback
    # appended when registry produces nothing.
    registry_reasons = _bucket_counts(combined, "failure_reason")
    if not registry_reasons:
        digest_reasons = _digest_top_failure_reasons(digest_payload)
        top_failure_reasons = digest_reasons
    else:
        top_failure_reasons = registry_reasons

    # technical_vs_research_failure_counts now ranges over ALL campaigns
    # (not just `combined`) and adds ``degenerate_no_survivors`` and
    # ``paper_blocked`` as first-class entries per the brief §2.
    def _count_class(cls: str) -> int:
        return sum(
            1
            for r in campaigns
            if _classify(r.get("outcome"), r.get("failure_reason")) == cls
        )

    diagnostic_context = _diagnostic_context(
        registry_state=registry_state,
        ledger_state=ledger_state,
        digest_state=digest_state,
        screening_evidence_state=screening_evidence_state,
        rolled_up_ledger_state=rolled_up_ledger_state,
        spawn_proposals_state=spawn_proposals_state,
        has_failure_reason_anywhere=has_failure_reason_anywhere,
        has_conflicting_failure_reason_fields=has_conflict,
        has_any_hypothesis_id=has_any_hypothesis_id,
        has_any_timeframe=has_any_timeframe,
        has_any_asset=has_any_asset,
        has_any_strategy_family=has_any_strategy_family,
        has_any_asset_class=has_any_asset_class,
    )

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "source": {
            "registry_state": registry_state,
            "ledger_state": ledger_state,
            "digest_state": digest_state,
            "ledger_lines_consumed": (ledger_meta or {}).get("lines_consumed"),
            "ledger_truncated": (ledger_meta or {}).get("truncated"),
            "ledger_partial_trailing_dropped": (ledger_meta or {}).get(
                "partial_trailing_line_dropped"
            ),
            "ledger_parse_errors": (ledger_meta or {}).get("parse_errors"),
            "max_ledger_lines": MAX_LEDGER_LINES,
        },
        "diagnostic_context": diagnostic_context,
        "total_campaigns_observed": len(campaigns),
        "total_failure_events_observed": len(combined),
        "campaigns_by_outcome": _by_outcome(campaigns),
        "campaigns_by_outcome_class": _by_outcome_class(campaigns),
        "top_failure_reasons": top_failure_reasons,
        "by_preset": _bucket_counts(combined, "preset"),
        "by_preset_name": _bucket_counts(combined, "preset_name"),
        "by_hypothesis_id": _bucket_counts(combined, "hypothesis_id"),
        "by_strategy_family": _bucket_counts(combined, "family")
        + _bucket_counts(combined, "strategy_family"),
        "by_asset": _bucket_counts(combined, "asset"),
        "by_timeframe": _bucket_counts(combined, "timeframe"),
        # by_campaign_type is over ALL campaigns (not the failed subset)
        # so registry-only mode populates this dimension.
        "by_campaign_type": _bucket_counts(campaigns, "campaign_type"),
        "by_worker_id": _bucket_counts(combined, "worker_id"),
        "by_meaningful_classification": _by_meaningful_classification(campaigns),
        "repeated_failure_clusters": _repeated_failure_clusters(combined),
        "technical_vs_research_failure_counts": {
            "technical_failure": _count_class("technical_failure"),
            "research_rejection": _count_class("research_rejection"),
            "degenerate_no_survivors": _count_class("degenerate_no_survivors"),
            "paper_blocked": _count_class("paper_blocked"),
            "unknown": _count_class("unknown"),
        },
        "unknown_or_unclassified_count": _count_class("unknown"),
    }


def build_failure_modes_artifact(
    *,
    now_utc: datetime | None = None,
    registry_path: Path | None = None,
    ledger_path: Path | None = None,
    digest_path: Path | None = None,
    screening_evidence_path: Path | None = None,
    rolled_up_ledger_path: Path | None = None,
    spawn_proposals_path: Path | None = None,
) -> dict[str, Any]:
    """Load real artifacts and produce the failure-mode payload.

    v3.15.15.6: also reads campaign_digest_latest.v1.json (used as a
    ``top_failure_reasons`` fallback) and stat-checks the four
    additional sidecars whose presence drives ``diagnostic_context``.
    Path defaults resolve at call time so monkeypatching is honoured.
    """
    reg_path = registry_path if registry_path is not None else CAMPAIGN_REGISTRY_PATH
    led_path = ledger_path if ledger_path is not None else CAMPAIGN_EVIDENCE_LEDGER_PATH
    dig_path = digest_path if digest_path is not None else CAMPAIGN_DIGEST_PATH
    scr_path = (
        screening_evidence_path
        if screening_evidence_path is not None
        else SCREENING_EVIDENCE_PATH
    )
    rul_path = (
        rolled_up_ledger_path
        if rolled_up_ledger_path is not None
        else ROLLED_UP_LEDGER_PATH
    )
    sp_path = (
        spawn_proposals_path
        if spawn_proposals_path is not None
        else SPAWN_PROPOSALS_PATH
    )

    registry = read_json_safe(reg_path)
    ledger = read_jsonl_tail_safe(
        led_path,
        max_lines=MAX_LEDGER_LINES,
        max_tail_bytes=MAX_LEDGER_TAIL_BYTES,
    )
    digest = read_json_safe(dig_path)
    screening = read_json_safe(scr_path)
    rolled_up = read_json_safe(rul_path)
    spawn = read_json_safe(sp_path)

    return compute_failure_mode_distribution(
        registry_payload=registry.payload if registry.state == "valid" else None,
        ledger_events=ledger.events,
        digest_payload=digest.payload if digest.state == "valid" else None,
        registry_state=registry.state,
        ledger_state=ledger.state,
        digest_state=digest.state,
        screening_evidence_state=screening.state,
        rolled_up_ledger_state=rolled_up.state,
        spawn_proposals_state=spawn.state,
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
