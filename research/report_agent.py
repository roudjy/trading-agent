"""v3.10 post-run analysis / report agent.

Reads run artifacts (frozen `research_latest.json`, sidecars, run-meta)
and composes `research/report_latest.md` + `research/report_latest.json`.
Existing reporting modules (falsification / promotion / integrity /
regime / statistical / empty-run) are reused — this agent composes, it
does not re-derive strategy or statistical logic.

Layer-safety:
- Reads only from `research/*.json` + `research/*.csv` + `research/run_meta_latest.v1.json`.
- Produces a NEW adjacent artifact (markdown + json). No mutations to the
  frozen public contract.
- Best-effort: the caller wraps this in try/except so a report failure
  never fails an otherwise-successful run (see `run_research.py`).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.registry import STRATEGIES
from research.report_candidate_diagnostics import build_candidate_diagnostics
from research.run_meta import RUN_META_PATH, read_run_meta_sidecar

REPORT_MARKDOWN_PATH = Path("research/report_latest.md")
REPORT_JSON_PATH = Path("research/report_latest.json")
REPORT_SCHEMA_VERSION = "1.1"

_RESEARCH_LATEST_JSON = Path("research/research_latest.json")
_FALSIFICATION_SIDECAR = Path("research/falsification_gates_latest.v1.json")
_INTEGRITY_SIDECAR = Path("research/integrity_report_latest.v1.json")
_EMPTY_RUN_SIDECAR = Path("research/empty_run_diagnostics_latest.v1.json")
_CANDIDATE_REGISTRY_SIDECAR = Path("research/candidate_registry_latest.v1.json")
_DEFENSIBILITY_SIDECAR = Path("research/statistical_defensibility_latest.v1.json")
_REGIME_SIDECAR = Path("research/regime_diagnostics_latest.v1.json")
_RUN_FILTER_SUMMARY_SIDECAR = Path("research/run_filter_summary_latest.v1.json")
_COST_SENSITIVITY_SIDECAR = Path("research/cost_sensitivity_latest.v1.json")
_REGISTRY_V2_SIDECAR = Path("research/candidate_registry_latest.v2.json")


VERDICT_PROMOTED = "promoted"
VERDICT_CANDIDATES_NO_PROMOTION = "candidates_no_promotion"
VERDICT_NIETS_BRUIKBAARS = "niets_bruikbaars_vandaag"


def _enrich_with_v3_12_fields(
    per_candidate: list[dict[str, Any]],
    registry_v2: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Additively merge v3.12 fields into per_candidate_diagnostics entries.

    The v3.11 shape of each per_candidate entry is preserved; only new
    keys (``lifecycle_status``, ``legacy_verdict``,
    ``observed_reason_codes``, ``taxonomy_rejection_codes``, ``scores``)
    are attached when a matching v2 entry is available. Missing
    entries simply do not gain the v3.12 fields — consumers check
    with ``.get()``.
    """
    if not per_candidate or not registry_v2:
        return per_candidate

    v2_index = {
        entry.get("candidate_id"): entry
        for entry in registry_v2.get("entries") or []
        if isinstance(entry, dict)
    }
    if not v2_index:
        return per_candidate

    enriched: list[dict[str, Any]] = []
    for entry in per_candidate:
        strategy_id = entry.get("strategy_id")
        v2_entry = v2_index.get(strategy_id)
        if v2_entry is None:
            enriched.append(entry)
            continue
        merged = dict(entry)
        merged["lifecycle_status"] = v2_entry.get("lifecycle_status")
        merged["legacy_verdict"] = v2_entry.get("legacy_verdict")
        merged["observed_reason_codes"] = v2_entry.get("observed_reason_codes") or []
        merged["taxonomy_rejection_codes"] = (
            v2_entry.get("taxonomy_rejection_codes") or []
        )
        merged["scores"] = v2_entry.get("scores")
        enriched.append(merged)
    return enriched


def _lifecycle_breakdown(
    per_candidate: list[dict[str, Any]],
) -> dict[str, int] | None:
    """Count per_candidate entries by lifecycle_status (v3.12)."""
    if not per_candidate:
        return None
    counts: dict[str, int] = {}
    has_any = False
    for entry in per_candidate:
        status = entry.get("lifecycle_status")
        if status is None:
            continue
        has_any = True
        counts[status] = counts.get(status, 0) + 1
    return counts if has_any else None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _extract_rejection_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        if row.get("success") is True and row.get("goedgekeurd") is True:
            continue
        reden = row.get("reden")
        if isinstance(reden, str) and reden.strip():
            counter[reden.strip()] += 1
        else:
            error = row.get("error")
            if isinstance(error, str) and error.strip():
                counter[f"error: {error.strip()}"] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(10)
    ]


def _extract_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("success"):
            continue
        if not row.get("goedgekeurd"):
            continue
        promoted.append({
            "strategy_name": row.get("strategy_name"),
            "asset": row.get("asset"),
            "interval": row.get("interval"),
            "win_rate": row.get("win_rate"),
            "sharpe": row.get("sharpe"),
            "deflated_sharpe": row.get("deflated_sharpe"),
            "max_drawdown": row.get("max_drawdown"),
            "trades_per_maand": row.get("trades_per_maand"),
            "totaal_trades": row.get("totaal_trades"),
        })
    return promoted


def _summarize_counts(
    rows: list[dict[str, Any]],
    meta_summary: dict[str, int] | None,
) -> dict[str, int]:
    if isinstance(meta_summary, dict) and meta_summary:
        return {k: int(v) for k, v in meta_summary.items()}
    success_rows = [r for r in rows if r.get("success")]
    promoted_rows = [r for r in success_rows if r.get("goedgekeurd")]
    return {
        "raw": len(rows),
        "screened": len(success_rows),
        "validated": len(success_rows),
        "rejected": len(rows) - len(promoted_rows),
        "promoted": len(promoted_rows),
    }


def _summarize_screening(
    rows: list[dict[str, Any]],
    filter_summary: dict[str, Any] | None,
) -> dict[str, int]:
    """v3.11 screening-layer counts, joined from run_filter_summary.

    Falls back to deriving counts from the rows when the sidecar is
    missing. All integers; never negative.
    """
    success_rows = [r for r in rows if r.get("success")]
    if isinstance(filter_summary, dict):
        summary = filter_summary.get("summary") or {}
        raw = int(summary.get("raw_candidate_count", 0) or 0)
        eligible = int(summary.get("eligible_candidate_count", 0) or 0)
        screening = filter_summary.get("screening_decisions") or {}
        promoted = int(screening.get("promoted_to_validation", 0) or 0)
        rejected = int(screening.get("rejected_in_screening", 0) or 0)
        return {
            "raw": raw,
            "eligible": eligible,
            "screening_passed": promoted,
            "screening_rejected": rejected,
        }
    return {
        "raw": len(rows),
        "eligible": len(rows),
        "screening_passed": len(success_rows),
        "screening_rejected": len(rows) - len(success_rows),
    }


def _summarize_promotion(
    rows: list[dict[str, Any]],
    candidate_registry: dict[str, Any] | None,
) -> dict[str, int]:
    """v3.11 promotion-layer counts, joined from candidate_registry.

    Falls back to deriving counts from rows.goedgekeurd when the
    registry sidecar is missing.
    """
    success_rows = [r for r in rows if r.get("success")]
    promoted_rows = [r for r in success_rows if r.get("goedgekeurd")]
    if isinstance(candidate_registry, dict):
        summary = candidate_registry.get("summary") or {}
        total = int(summary.get("total", len(success_rows)) or 0)
        return {
            "evaluated": total,
            "promoted": int(summary.get("candidate", len(promoted_rows)) or 0),
            "needs_investigation": int(summary.get("needs_investigation", 0) or 0),
            "rejected_promotion": int(summary.get("rejected", 0) or 0),
        }
    return {
        "evaluated": len(success_rows),
        "promoted": len(promoted_rows),
        "needs_investigation": 0,
        "rejected_promotion": len(success_rows) - len(promoted_rows),
    }


def _screening_layer_reason_counts(
    rows: list[dict[str, Any]],
    filter_summary: dict[str, Any] | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate screening-layer rejection reasons.

    Sources read in priority order:
    1. ``run_filter_summary.screening_rejection_reasons`` (canonical)
    2. ``run_filter_summary.eligibility_rejection_reasons``
    3. ``run_filter_summary.fit_blocked_reasons``
    4. Non-empty ``reden`` strings in the rows (fallback)
    """
    counter: Counter[str] = Counter()
    if isinstance(filter_summary, dict):
        for key in (
            "screening_rejection_reasons",
            "eligibility_rejection_reasons",
            "fit_blocked_reasons",
        ):
            bucket = filter_summary.get(key)
            if isinstance(bucket, dict):
                for reason, count in bucket.items():
                    if isinstance(reason, str) and reason:
                        counter[reason] += int(count or 0)
    if not counter:
        for row in rows:
            reden = row.get("reden") if isinstance(row, dict) else None
            if isinstance(reden, str) and reden.strip():
                counter[reden.strip()] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(limit)
    ]


def _promotion_layer_reason_counts(
    candidate_registry: dict[str, Any] | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate promotion-layer rejection reasons from the candidate
    registry's per-candidate ``reasoning.failed`` + ``.escalated``
    codes. Consumer-only; we do not re-classify."""
    if not isinstance(candidate_registry, dict):
        return []
    candidates = candidate_registry.get("candidates")
    if not isinstance(candidates, list):
        return []
    counter: Counter[str] = Counter()
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        reasoning = entry.get("reasoning") or {}
        for bucket_key in ("failed", "escalated"):
            bucket = reasoning.get(bucket_key)
            if not isinstance(bucket, list):
                continue
            for code in bucket:
                if isinstance(code, str) and code:
                    counter[code] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(limit)
    ]


def _extract_red_flags() -> list[dict[str, Any]]:
    payload = _load_json(_INTEGRITY_SIDECAR)
    if not payload:
        return []
    flags: list[dict[str, Any]] = []
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        if status in {"WARN", "FAIL", "ERROR"}:
            flags.append({
                "check": check.get("name") or check.get("check"),
                "status": status,
                "message": check.get("message") or check.get("detail"),
            })
    return flags


def _statistical_diagnostics() -> dict[str, Any]:
    payload = _load_json(Path("research/statistical_defensibility_latest.v1.json"))
    if not isinstance(payload, dict):
        return {}
    return {
        "generated_at_utc": payload.get("generated_at_utc"),
        "candidate_count": payload.get("candidate_count"),
        "deflated_sharpe_threshold": payload.get("deflated_sharpe_threshold"),
    }


def _regime_diagnostics() -> dict[str, Any]:
    payload = _load_json(Path("research/regime_diagnostics_latest.v1.json"))
    if not isinstance(payload, dict):
        return {}
    return {
        "generated_at_utc": payload.get("generated_at_utc"),
        "regime_count": payload.get("regime_count"),
    }


_PROMOTION_STATISTICAL_CODES = frozenset({
    "psr_below_threshold",
    "psr_unavailable",
    "dsr_canonical_below_threshold",
    "dsr_unavailable",
    "bootstrap_sharpe_ci_includes_zero",
    "bootstrap_sharpe_ci_unavailable",
})
_PROMOTION_RISK_CODES = frozenset({
    "drawdown_above_limit",
})
_PROMOTION_TRADES_CODES = frozenset({
    "insufficient_trades",
})
_PROMOTION_NOISE_CODES = frozenset({
    "noise_warning_fired",
})


def _dominant_promotion_failure_type(
    promotion_reasons: list[dict[str, Any]] | None,
) -> str | None:
    """Return the dominant failure-type among promotion reasons.

    Uses only the pre-existing reason vocabulary — no new taxonomy.
    Returns one of {"statistical", "risk", "trades", "noise"} or None
    when the data is inconclusive (no reasons or no majority bucket).
    """
    if not isinstance(promotion_reasons, list):
        return None
    buckets = {"statistical": 0, "risk": 0, "trades": 0, "noise": 0}
    for entry in promotion_reasons:
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason")
        count = int(entry.get("count") or 0)
        if not isinstance(reason, str) or count <= 0:
            continue
        if reason in _PROMOTION_STATISTICAL_CODES:
            buckets["statistical"] += count
        elif reason in _PROMOTION_RISK_CODES:
            buckets["risk"] += count
        elif reason in _PROMOTION_TRADES_CODES:
            buckets["trades"] += count
        elif reason in _PROMOTION_NOISE_CODES:
            buckets["noise"] += count
    if not any(buckets.values()):
        return None
    dominant = max(buckets, key=lambda k: buckets[k])
    return dominant if buckets[dominant] > 0 else None


def suggest_next_experiment(
    summary: dict[str, int],
    candidates: list[dict[str, Any]],
    meta: dict[str, Any] | None,
    *,
    rejection_reasons_by_layer: dict[str, Any] | None = None,
) -> str:
    """v3.11: layer-aware + failure-type next-experiment suggestion.

    Decision tree (read-only; uses existing reason codes only):

    1. Zero rows -> universe/snapshot check.
    2. Promoted candidates -> broaden timeframe.
    3. Promotion-layer dominant failures -> subtype-aware suggestion
       (statistical / risk / trades / noise).
    4. Screening-layer dominant failures -> hypothesis-level advice.
    5. Diagnostic preset -> preserve rejection patterns.
    6. Otherwise -> try the regime-filtered baseline.
    """
    if summary.get("raw", 0) == 0:
        return (
            "Geen kandidaten gepland. Controleer universe, preset en "
            "asset-snapshot."
        )
    if summary.get("promoted", 0) >= 1:
        names = ", ".join(
            sorted({str(c.get("strategy_name")) for c in candidates})
        )
        return (
            f"Hercheck OOS voor gepromoveerde strategieen ({names}) op "
            "een bredere timeframe; bewaar fold pins voor walk-forward."
        )

    screening_reasons = (
        (rejection_reasons_by_layer or {}).get("screening_layer") or []
    )
    promotion_reasons = (
        (rejection_reasons_by_layer or {}).get("promotion_layer") or []
    )
    screening_total = sum(int(r.get("count") or 0) for r in screening_reasons)
    promotion_total = sum(int(r.get("count") or 0) for r in promotion_reasons)

    if promotion_total > 0 and promotion_total >= screening_total:
        failure_type = _dominant_promotion_failure_type(promotion_reasons)
        if failure_type == "statistical":
            return (
                "Kandidaten haalden screening maar faalden op statistische "
                "defensibility (PSR/DSR/bootstrap). Meer data of langere "
                "history nodig; smallere universe overwegen voordat aan "
                "de parameters wordt gedraaid."
            )
        if failure_type == "risk":
            return (
                "Kandidaten haalden screening maar faalden op drawdown. "
                "Dit is een risk-profiel probleem — onderzoek stop-loss "
                "discipline of positie-sizing, niet de entry-logica."
            )
        if failure_type == "trades":
            return (
                "Kandidaten haalden screening maar produceerden te weinig "
                "trades. Frequenter interval of ruimere drempel binnen de "
                "falsification-criteria; verandering mag geen re-fit zijn."
            )
        if failure_type == "noise":
            return (
                "Promotion markeert runs als waarschijnlijk ruis. "
                "Hercheck feature-kwaliteit en fold-stabiliteit voordat "
                "een volgende preset gepland wordt."
            )
        return (
            "Kandidaten haalden screening maar faalden promotion. Loop "
            "falsification_gates door en overweeg preset met regime filter "
            "('trend_regime_filtered_equities_4h')."
        )

    if screening_total > 0:
        return (
            "Screening-laag is het knelpunt. Hypothese heroverwegen: "
            "andere strategy family, andere timeframe, of gerichter "
            "universe. Drempels niet verlagen zonder falsification-update."
        )

    if summary.get("validated", 0) >= 1:
        return (
            "Kandidaten haalden screening maar faalden promotion. Loop "
            "falsification_gates door en overweeg preset met regime filter "
            "('trend_regime_filtered_equities_4h')."
        )
    if meta and meta.get("diagnostic_only"):
        return (
            "Diagnostische run; geen actie vereist. Bewaar reject-reasons "
            "voor de volgende niet-diagnostische baseline."
        )
    return (
        "Geen trades haalden screening. Overweeg timeframe-variatie of "
        "verlaag niet de drempels; begin met 'trend_regime_filtered_equities_4h'."
    )


def classify_verdict(summary: dict[str, int], meta: dict[str, Any] | None) -> str:
    if summary.get("promoted", 0) >= 1:
        return VERDICT_PROMOTED
    if summary.get("validated", 0) >= 1 or summary.get("screened", 0) >= 1:
        return VERDICT_CANDIDATES_NO_PROMOTION
    return VERDICT_NIETS_BRUIKBAARS


def build_report_payload(
    *,
    run_id: str | None = None,
    research_latest_path: Path = _RESEARCH_LATEST_JSON,
    run_meta_path: Path = RUN_META_PATH,
) -> dict[str, Any]:
    research = _load_json(research_latest_path) or {}
    meta = read_run_meta_sidecar(run_meta_path)
    rows: list[dict[str, Any]] = list(research.get("results") or [])

    # v3.11: load sidecars read-only for screening/promotion split +
    # per-candidate diagnostics.
    candidate_registry = _load_json(_CANDIDATE_REGISTRY_SIDECAR)
    filter_summary = _load_json(_RUN_FILTER_SUMMARY_SIDECAR)
    defensibility_payload = _load_json(_DEFENSIBILITY_SIDECAR)
    regime_payload = _load_json(_REGIME_SIDECAR)
    cost_sensitivity_payload = _load_json(_COST_SENSITIVITY_SIDECAR)
    strategy_index = {entry["name"]: entry for entry in STRATEGIES}
    per_candidate, join_stats = build_candidate_diagnostics(
        rows=rows,
        candidate_registry=candidate_registry,
        defensibility=defensibility_payload,
        regime=regime_payload,
        cost_sensitivity=cost_sensitivity_payload,
        strategy_index=strategy_index,
    )

    # v3.12: additive enrichment of per_candidate_diagnostics with
    # lifecycle_status, legacy_verdict, observed_reason_codes,
    # taxonomy_rejection_codes, and scores. Report schema_version
    # stays "1.1" — these are optional fields consumers may ignore.
    registry_v2 = _load_json(_REGISTRY_V2_SIDECAR)
    per_candidate = _enrich_with_v3_12_fields(per_candidate, registry_v2)

    summary = _summarize_counts(
        rows,
        meta.get("candidate_summary") if isinstance(meta, dict) else None,
    )
    # v3.11 additive: screening + promotion counts alongside the
    # existing v3.10 raw/screened/validated/rejected/promoted keys so
    # dashboard consumers that only know v3.10 keep working.
    summary["screening"] = _summarize_screening(rows, filter_summary)
    summary["promotion"] = _summarize_promotion(rows, candidate_registry)

    legacy_rejection_reasons = (
        meta.get("top_rejection_reasons")
        if isinstance(meta, dict) and meta.get("top_rejection_reasons")
        else _extract_rejection_counts(rows)
    )
    # v3.11: same top_rejection_reasons key now carries screening and
    # promotion-layer breakdowns as a dict under ``by_layer``. The
    # flat list shape remains the default for the key itself — keeping
    # v3.10 consumers working — while ``top_rejection_reasons_by_layer``
    # is the new sibling key with the split.
    rejection_reasons_by_layer = {
        "screening_layer": _screening_layer_reason_counts(rows, filter_summary),
        "promotion_layer": _promotion_layer_reason_counts(candidate_registry),
    }

    candidates = _extract_candidates(rows)
    red_flags = _extract_red_flags()
    next_experiment = suggest_next_experiment(
        summary,
        candidates,
        meta,
        rejection_reasons_by_layer=rejection_reasons_by_layer,
    )
    verdict = classify_verdict(summary, meta)

    preset_name = meta.get("preset_name") if isinstance(meta, dict) else None

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id or (meta or {}).get("run_id"),
        "preset": preset_name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "summary": summary,
        "top_rejection_reasons": legacy_rejection_reasons,
        "top_rejection_reasons_by_layer": rejection_reasons_by_layer,
        "candidates": candidates,
        "per_candidate_diagnostics": per_candidate,
        "join_stats": join_stats,
        "red_flags": red_flags,
        "regime_diagnostics": _regime_diagnostics(),
        "statistical_diagnostics": _statistical_diagnostics(),
        "next_experiment": next_experiment,
        "verdict": verdict,
        "lifecycle_breakdown": _lifecycle_breakdown(per_candidate),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    preset = report.get("preset") or "(no preset)"
    verdict = report.get("verdict") or "unknown"
    summary = report.get("summary") or {}
    lines.append(f"# Research report — {preset}")
    lines.append("")
    lines.append(f"- run_id: `{report.get('run_id')}`")
    lines.append(f"- generated_at_utc: `{report.get('generated_at_utc')}`")
    lines.append(f"- verdict: **{verdict}**")
    lines.append("")

    _append_hypothesis_section(lines)
    _append_summary_section(lines, summary, report.get("join_stats"))

    if verdict == VERDICT_NIETS_BRUIKBAARS:
        lines.append("> **Niets bruikbaars vandaag.** Geen kandidaten haalden screening.")
        lines.append("")

    _append_what_worked_section(lines, report.get("candidates") or [])
    _append_what_didnt_work_section(
        lines,
        report.get("top_rejection_reasons_by_layer"),
        report.get("top_rejection_reasons") or [],
    )
    _append_waarom_section(lines, report.get("per_candidate_diagnostics") or [])
    _append_lifecycle_breakdown_section(lines, report.get("lifecycle_breakdown"))

    red_flags = report.get("red_flags") or []
    if red_flags:
        lines.append("## Red flags")
        for f in red_flags:
            lines.append(f"- {f.get('status')}: {f.get('check')} — {f.get('message')}")
        lines.append("")
    lines.append("## Diagnostics")
    lines.append(f"- statistical: {report.get('statistical_diagnostics') or {}}")
    lines.append(f"- regime: {report.get('regime_diagnostics') or {}}")
    lines.append("")
    lines.append("## Volgende stap")
    lines.append(f"- {report.get('next_experiment')}")
    lines.append("")
    return "\n".join(lines)


def _append_lifecycle_breakdown_section(
    lines: list[str], breakdown: dict[str, int] | None
) -> None:
    """v3.12 additive markdown section — rendered only when data is present."""
    if not breakdown:
        return
    lines.append("## Candidate Lifecycle Breakdown (v3.12)")
    for status in sorted(breakdown.keys()):
        lines.append(f"- {status}: {breakdown[status]}")
    lines.append("")


def _append_hypothesis_section(lines: list[str]) -> None:
    """Render preset-level hypothesis metadata from run_meta sidecar."""
    meta = read_run_meta_sidecar()
    lines.append("## Hypothese")
    if not isinstance(meta, dict):
        lines.append("- (run_meta sidecar ontbreekt; hypothese niet beschikbaar)")
        lines.append("")
        return
    hypothesis = meta.get("preset_hypothesis")
    preset_class = meta.get("preset_class")
    rationale = meta.get("preset_rationale")
    expected = meta.get("preset_expected_behavior")
    falsification = meta.get("preset_falsification") or []
    bundle_hypotheses = meta.get("preset_bundle_hypotheses") or []

    if preset_class:
        lines.append(f"- preset_class: `{preset_class}`")
    if isinstance(hypothesis, str) and hypothesis.strip():
        lines.append(f"- hypothesis: {hypothesis}")
    if isinstance(rationale, str) and rationale.strip():
        lines.append(f"- rationale: {rationale}")
    if isinstance(expected, str) and expected.strip():
        lines.append(f"- expected_behavior: {expected}")
    if isinstance(falsification, list) and falsification:
        lines.append("- falsification:")
        for criterion in falsification:
            if isinstance(criterion, str) and criterion.strip():
                lines.append(f"    - {criterion}")
    if isinstance(bundle_hypotheses, list) and bundle_hypotheses:
        lines.append("- bundle hypotheses:")
        for entry in bundle_hypotheses:
            if not isinstance(entry, dict):
                continue
            name = entry.get("strategy_name")
            h = entry.get("hypothesis")
            if isinstance(name, str) and isinstance(h, str):
                lines.append(f"    - `{name}`: {h}")
    lines.append("")


def _append_summary_section(
    lines: list[str],
    summary: dict[str, Any],
    join_stats: dict[str, Any] | None,
) -> None:
    lines.append("## Samenvatting")
    for key in ("raw", "screened", "validated", "rejected", "promoted"):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    screening = summary.get("screening") or {}
    promotion = summary.get("promotion") or {}
    if screening:
        lines.append("### Screening-laag")
        for key in ("raw", "eligible", "screening_passed", "screening_rejected"):
            lines.append(f"- {key}: {screening.get(key, 0)}")
    if promotion:
        lines.append("### Promotion-laag")
        for key in ("evaluated", "promoted", "needs_investigation", "rejected_promotion"):
            lines.append(f"- {key}: {promotion.get(key, 0)}")
    if isinstance(join_stats, dict) and join_stats:
        lines.append("### Join stats (artifact koppeling)")
        for key, value in sorted(join_stats.items()):
            lines.append(f"- {key}: {value}")
    lines.append("")


def _append_what_worked_section(
    lines: list[str],
    candidates: list[dict[str, Any]],
) -> None:
    lines.append("## Wat werkte")
    if not candidates:
        lines.append("Geen kandidaten gepromoveerd.")
        lines.append("")
        return
    for c in candidates:
        lines.append(
            f"- `{c.get('strategy_name')}` op `{c.get('asset')}` "
            f"({c.get('interval')}) — sharpe {c.get('sharpe')}, "
            f"win_rate {c.get('win_rate')}"
        )
    lines.append("")


def _append_what_didnt_work_section(
    lines: list[str],
    by_layer: dict[str, Any] | None,
    legacy_flat: list[dict[str, Any]],
) -> None:
    lines.append("## Wat werkte niet")
    screening_reasons = (
        (by_layer or {}).get("screening_layer") or []
    )
    promotion_reasons = (
        (by_layer or {}).get("promotion_layer") or []
    )
    if not screening_reasons and not promotion_reasons and not legacy_flat:
        lines.append("Geen rejection reasons geregistreerd.")
        lines.append("")
        return

    lines.append("### Screening-laag")
    if screening_reasons:
        for item in screening_reasons:
            lines.append(f"- {item.get('reason')} ({item.get('count')})")
    else:
        lines.append("(geen screening-laag rejecties)")

    lines.append("### Promotion-laag")
    if promotion_reasons:
        for item in promotion_reasons:
            lines.append(f"- {item.get('reason')} ({item.get('count')})")
    else:
        lines.append("(geen promotion-laag rejecties)")
    lines.append("")


def _append_waarom_section(
    lines: list[str],
    per_candidate: list[dict[str, Any]],
) -> None:
    """v3.11 per-candidate 'why' section.

    Renders verdict + rejection_layer + top 2 reasons +
    stability/cost/regime flags per row, without re-deriving anything.
    """
    lines.append("## Waarom (per candidate)")
    if not per_candidate:
        lines.append("Geen per-candidate diagnostics beschikbaar.")
        lines.append("")
        return
    for entry in per_candidate:
        name = entry.get("strategy_name")
        asset = entry.get("asset")
        interval = entry.get("interval")
        verdict = entry.get("verdict")
        layer = entry.get("rejection_layer") or "—"
        reasons = entry.get("rejection_reasons") or []
        top_reasons = ", ".join(str(r) for r in reasons[:2]) if reasons else "—"
        flags = entry.get("stability_flags") or {}
        active_flags = [
            key for key, value in flags.items() if value is True
        ]
        flag_str = ", ".join(active_flags) if active_flags else "geen"
        cost_flag = entry.get("cost_sensitivity_flag")
        regime_flag = entry.get("regime_suspicion_flag")
        lines.append(
            f"- `{name}` / `{asset}` / `{interval}` — "
            f"verdict=**{verdict}** (layer={layer}); "
            f"reasons=[{top_reasons}]; "
            f"stability_flags=[{flag_str}]; "
            f"cost_sensitivity={cost_flag}; "
            f"regime_suspicion={regime_flag}"
        )
    lines.append("")


def write_report(
    report: dict[str, Any],
    *,
    markdown_path: Path = REPORT_MARKDOWN_PATH,
    json_path: Path = REPORT_JSON_PATH,
) -> tuple[Path, Path]:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return markdown_path, json_path


def generate_post_run_report(
    run_id: str | None = None,
    *,
    research_latest_path: Path = _RESEARCH_LATEST_JSON,
    run_meta_path: Path = RUN_META_PATH,
    markdown_path: Path = REPORT_MARKDOWN_PATH,
    json_path: Path = REPORT_JSON_PATH,
) -> dict[str, Any]:
    report = build_report_payload(
        run_id=run_id,
        research_latest_path=research_latest_path,
        run_meta_path=run_meta_path,
    )
    write_report(report, markdown_path=markdown_path, json_path=json_path)
    return report


__all__ = [
    "REPORT_JSON_PATH",
    "REPORT_MARKDOWN_PATH",
    "REPORT_SCHEMA_VERSION",
    "VERDICT_CANDIDATES_NO_PROMOTION",
    "VERDICT_NIETS_BRUIKBAARS",
    "VERDICT_PROMOTED",
    "build_report_payload",
    "classify_verdict",
    "generate_post_run_report",
    "render_markdown",
    "suggest_next_experiment",
    "write_report",
]
