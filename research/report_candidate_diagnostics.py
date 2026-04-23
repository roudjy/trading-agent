"""v3.11 per-candidate diagnostics — consumer-only join of research artifacts.

This module is pure data transformation. It never re-derives metrics,
introduces thresholds, or interprets raw numeric fields. All stability,
cost, and regime flags are sourced from pre-computed booleans in the
existing sidecars; when a flag is not present in its source sidecar the
value is ``null`` — never guessed.

Layer placement:
- Reads only from ``research/*.json`` sidecars + the frozen
  ``research_latest.json`` rows + the registry's ``STRATEGIES`` list
  (for hypothesis lookup).
- Exposes a single pure function ``build_candidate_diagnostics`` that
  returns ``(per_candidate, join_stats)``. The report agent owns the
  IO and passes loaded sidecars in.
- No writes. No new schemas. No modifications to existing sidecars.
"""

from __future__ import annotations

import json
from typing import Any

from research.promotion import build_strategy_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD = 1000

# Reason-code vocabularies from the existing pipeline layers. We reuse
# these as-is to classify the rejection layer of a given row without
# introducing a new taxonomy.
_FIT_PRIOR_REASONS = frozenset({
    "requires_spread_not_outright",
    "unsupported_for_initial_lane",
})
_ELIGIBILITY_REASONS = frozenset({
    "invalid_candidate_shape",
    "universe_membership_mismatch",
    "strategy_not_applicable",
    "invalid_asset_interval",
})
_SCREENING_REASONS = frozenset({
    "candidate_budget_exceeded",
    "screening_criteria_not_met",
    "screening_error",
})

# Promotion-layer stability reason codes as defined by
# ``research.promotion._check_escalation_rules``. We consume them
# read-only from the candidate registry's reasoning dict.
_STABILITY_FLAG_CODES: dict[str, tuple[str, ...]] = {
    # report_flag_name -> reason-codes that mean "this flag is ON"
    "noise_warning": ("noise_warning_fired",),
    "psr_below_threshold": (
        "psr_below_threshold",
        "psr_unavailable",
    ),
    "dsr_canonical_below_threshold": (
        "dsr_canonical_below_threshold",
        "dsr_unavailable",
    ),
    "bootstrap_sharpe_ci_includes_zero": (
        "bootstrap_sharpe_ci_includes_zero",
        "bootstrap_sharpe_ci_unavailable",
    ),
}

_STABILITY_PASS_CODES: dict[str, tuple[str, ...]] = {
    # When any of these pass-codes appears in reasoning.passed, the
    # check was explicitly evaluated and did NOT trigger the flag.
    "noise_warning": ("noise_warning_clear",),
    "psr_below_threshold": ("psr_above_threshold",),
    "dsr_canonical_below_threshold": ("dsr_canonical_above_threshold",),
    "bootstrap_sharpe_ci_includes_zero": ("bootstrap_sharpe_ci_positive",),
}

_EMPTY_STABILITY_FLAGS: dict[str, bool | None] = {
    "noise_warning": None,
    "psr_below_threshold": None,
    "dsr_canonical_below_threshold": None,
    "bootstrap_sharpe_ci_includes_zero": None,
}

_METRIC_FIELDS: tuple[str, ...] = (
    "sharpe",
    "deflated_sharpe",
    "win_rate",
    "max_drawdown",
    "trades_per_maand",
    "totaal_trades",
    "consistentie",
)

# Verdict enum — the only four values v3.11 emits.
VERDICT_PROMOTED = "promoted"
VERDICT_NEEDS_INVESTIGATION = "needs_investigation"
VERDICT_REJECTED_PROMOTION = "rejected_promotion"
VERDICT_REJECTED_SCREENING = "rejected_screening"

_CANDIDATE_REGISTRY_STATUS_REJECTED = "rejected"
_CANDIDATE_REGISTRY_STATUS_NEEDS = "needs_investigation"
_CANDIDATE_REGISTRY_STATUS_CANDIDATE = "candidate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_params(row: dict[str, Any]) -> dict[str, Any]:
    """Best-effort parse of the ``params_json`` field into a dict.

    Returns an empty dict on missing or malformed JSON; the fallback
    (strategy_name, asset, interval) triple remains joinable.
    """
    raw = row.get("params_json")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_strategy_id(row: dict[str, Any]) -> str | None:
    """Compute the canonical strategy_id for a results row.

    Returns ``None`` if any of the required fields are missing —
    such rows cannot be matched against any sidecar and will surface
    in ``join_stats.unmatched_*``.
    """
    name = row.get("strategy_name")
    asset = row.get("asset")
    interval = row.get("interval")
    if not (isinstance(name, str) and isinstance(asset, str) and isinstance(interval, str)):
        return None
    params = _parse_params(row)
    return build_strategy_id(name, asset, interval, params)


def _index_candidate_registry(
    registry: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(registry, dict):
        return {}
    entries = registry.get("candidates")
    if not isinstance(entries, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("strategy_id")
        if isinstance(sid, str):
            index[sid] = entry
    return index


def _index_defensibility(
    defensibility: dict[str, Any] | None,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Key ``(strategy_name, asset, interval)`` -> member dict.

    Mirrors the index shape used by
    ``research.promotion_reporting._build_defensibility_index``.
    """
    if not isinstance(defensibility, dict):
        return {}
    families = defensibility.get("families")
    if not isinstance(families, list):
        return {}
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for family in families:
        if not isinstance(family, dict):
            continue
        interval = family.get("interval")
        if not isinstance(interval, str):
            continue
        for member in family.get("members", []):
            if not isinstance(member, dict):
                continue
            name = member.get("strategy_name")
            asset = member.get("asset")
            if isinstance(name, str) and isinstance(asset, str):
                index[(name, asset, interval)] = member
    return index


def _stability_flags_from_reasoning(
    reasoning: dict[str, Any] | None,
) -> dict[str, bool | None]:
    """Read-only mapping from promotion reasoning to v3.11 stability flags.

    Rules:
    - flag = True iff any of its ON-codes appears in
      ``reasoning.failed`` or ``reasoning.escalated``.
    - flag = False iff any of its PASS-codes appears in
      ``reasoning.passed``.
    - flag = None (null) iff neither side fired — the check was not
      evaluated for this candidate, no guessing.
    """
    if not isinstance(reasoning, dict):
        return dict(_EMPTY_STABILITY_FLAGS)

    failed_codes = set(_as_str_list(reasoning.get("failed")))
    escalated_codes = set(_as_str_list(reasoning.get("escalated")))
    passed_codes = set(_as_str_list(reasoning.get("passed")))
    on_set = failed_codes | escalated_codes

    flags: dict[str, bool | None] = {}
    for flag_name, on_codes in _STABILITY_FLAG_CODES.items():
        if any(code in on_set for code in on_codes):
            flags[flag_name] = True
            continue
        pass_codes = _STABILITY_PASS_CODES.get(flag_name, ())
        if any(code in passed_codes for code in pass_codes):
            flags[flag_name] = False
            continue
        flags[flag_name] = None
    return flags


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _cost_sensitivity_flag_from_sidecar(
    sidecar: dict[str, Any] | None,
    strategy_id: str,
) -> bool | None:
    """Read a pre-computed cost-sensitivity boolean from the sidecar.

    v3.11 does NOT derive this flag from numeric stress/baseline deltas.
    If the sidecar does not expose a ready-made boolean for the given
    ``strategy_id`` the flag remains ``None``.

    Shape contract: the sidecar (when present) may expose a
    ``sensitivity_flags`` mapping keyed by ``strategy_id`` with
    boolean values. Any other shape yields ``None``.
    """
    if not isinstance(sidecar, dict):
        return None
    flags = sidecar.get("sensitivity_flags")
    if isinstance(flags, dict):
        value = flags.get(strategy_id)
        if isinstance(value, bool):
            return value
    return None


def _regime_suspicion_flag_from_sidecar(
    sidecar: dict[str, Any] | None,
    triple: tuple[str, str, str],
) -> bool | None:
    """Read a pre-computed regime-suspicion boolean from the sidecar.

    v3.11 does NOT introduce a regime classification. If the sidecar
    exposes a boolean ``regime_suspicion_flag`` per
    ``(strategy_name, asset, interval)`` triple we forward it; in all
    other shapes the value is ``None``.
    """
    if not isinstance(sidecar, dict):
        return None
    per_entry = sidecar.get("per_candidate_regime_flags")
    if isinstance(per_entry, dict):
        key = "|".join(triple)
        value = per_entry.get(key)
        if isinstance(value, bool):
            return value
    return None


# ---------------------------------------------------------------------------
# Verdict & rejection-layer mapping
# ---------------------------------------------------------------------------


def _classify_rejection_layer(
    row: dict[str, Any],
    registry_entry: dict[str, Any] | None,
) -> str | None:
    """Return one of: 'fit_prior', 'eligibility', 'screening',
    'promotion', or ``None`` (when the row was promoted)."""
    reden = row.get("reden")
    if isinstance(reden, str) and reden:
        if reden in _FIT_PRIOR_REASONS:
            return "fit_prior"
        if reden in _ELIGIBILITY_REASONS:
            return "eligibility"
        if reden in _SCREENING_REASONS:
            return "screening"
        # Unknown reason string but non-empty — treat as screening
        # (it was raised before reaching the promotion layer).
        return "screening"
    if not row.get("success"):
        return "screening"
    if registry_entry is None:
        return None if row.get("goedgekeurd") else "promotion"
    status = registry_entry.get("status")
    if status == _CANDIDATE_REGISTRY_STATUS_CANDIDATE and row.get("goedgekeurd"):
        return None
    if status in {_CANDIDATE_REGISTRY_STATUS_REJECTED, _CANDIDATE_REGISTRY_STATUS_NEEDS}:
        return "promotion"
    # candidate_registry says "candidate" but row.goedgekeurd is False.
    # This is an internal inconsistency — mark as promotion-layer
    # anomaly; rejection_reasons carries the anomaly code.
    return "promotion"


def _classify_verdict(
    row: dict[str, Any],
    registry_entry: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return (verdict, rejection_reasons).

    Pure mapping — no new interpretation. The
    ``internal_final_gate_conflict`` anomaly code is the single
    escape-hatch for an inconsistent join result; it is surfaced in
    rejection_reasons rather than hidden.
    """
    reden = row.get("reden")
    if isinstance(reden, str) and reden:
        return VERDICT_REJECTED_SCREENING, [reden]
    if not row.get("success"):
        error = row.get("error")
        reason = error if isinstance(error, str) and error else "screening_error"
        return VERDICT_REJECTED_SCREENING, [reason]

    if registry_entry is None:
        # Fallback: derive verdict from row.goedgekeurd only.
        if row.get("goedgekeurd"):
            return VERDICT_PROMOTED, []
        return VERDICT_REJECTED_PROMOTION, ["unmatched_candidate_registry"]

    status = registry_entry.get("status")
    reasoning = registry_entry.get("reasoning") if isinstance(registry_entry, dict) else None
    failed = _as_str_list((reasoning or {}).get("failed"))
    escalated = _as_str_list((reasoning or {}).get("escalated"))

    if status == _CANDIDATE_REGISTRY_STATUS_CANDIDATE:
        if row.get("goedgekeurd"):
            return VERDICT_PROMOTED, []
        # Candidate-status from promotion but final public gate
        # disagrees — surface as anomaly, do not hide.
        return VERDICT_REJECTED_PROMOTION, ["internal_final_gate_conflict"]
    if status == _CANDIDATE_REGISTRY_STATUS_NEEDS:
        return VERDICT_NEEDS_INVESTIGATION, escalated or ["needs_investigation"]
    if status == _CANDIDATE_REGISTRY_STATUS_REJECTED:
        return VERDICT_REJECTED_PROMOTION, failed or ["rejected_promotion"]
    # Unknown status in registry — anomaly.
    return VERDICT_REJECTED_PROMOTION, ["unknown_registry_status"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_candidate_diagnostics(
    *,
    rows: list[dict[str, Any]],
    candidate_registry: dict[str, Any] | None,
    defensibility: dict[str, Any] | None,
    regime: dict[str, Any] | None,
    cost_sensitivity: dict[str, Any] | None,
    strategy_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build per-candidate diagnostic rows + explicit join statistics.

    Parameters
    ----------
    rows
        The ``research_latest.json::results`` array (frozen schema).
    candidate_registry
        Parsed ``candidate_registry_latest.v1.json`` or ``None``.
    defensibility
        Parsed ``statistical_defensibility_latest.v1.json`` or ``None``.
    regime
        Parsed ``regime_diagnostics_latest.v1.json`` or ``None``.
    cost_sensitivity
        Parsed cost-sensitivity sidecar payload or ``None``. v3.11
        uses pre-computed booleans only; numeric replay is never
        re-interpreted here.
    strategy_index
        Mapping ``strategy_name -> STRATEGIES entry``. Used only to
        copy the registered ``hypothesis`` string onto each entry.

    Returns
    -------
    (per_candidate, join_stats)
        ``per_candidate`` is a list with one entry per input row;
        ``join_stats`` reports the match counts per sidecar so the
        report agent can surface mismatches without silent failures.
    """
    registry_index = _index_candidate_registry(candidate_registry)
    defensibility_index = _index_defensibility(defensibility)

    matched_registry = 0
    matched_defensibility = 0
    matched_cost_sensitivity = 0
    matched_regime = 0
    unmatched_by_strategy_id = 0

    per_candidate: list[dict[str, Any]] = []
    for row in rows:
        strategy_name = row.get("strategy_name") if isinstance(row, dict) else None
        asset = row.get("asset") if isinstance(row, dict) else None
        interval = row.get("interval") if isinstance(row, dict) else None
        if not (
            isinstance(strategy_name, str)
            and isinstance(asset, str)
            and isinstance(interval, str)
        ):
            # Malformed row; append a minimal diagnostic so reviewers
            # can see it rather than silently dropping it.
            per_candidate.append({
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "params_json": row.get("params_json") if isinstance(row, dict) else None,
                "strategy_id": None,
                "hypothesis": None,
                "verdict": VERDICT_REJECTED_SCREENING,
                "rejection_layer": "eligibility",
                "rejection_reasons": ["invalid_candidate_shape"],
                "stability_flags": dict(_EMPTY_STABILITY_FLAGS),
                "cost_sensitivity_flag": None,
                "regime_suspicion_flag": None,
                "metrics": {},
            })
            continue

        strategy_id = _row_strategy_id(row) or ""
        registry_entry = registry_index.get(strategy_id)
        if registry_entry is None:
            unmatched_by_strategy_id += 1
        else:
            matched_registry += 1

        defensibility_entry = defensibility_index.get(
            (strategy_name, asset, interval)
        )
        if defensibility_entry is not None:
            matched_defensibility += 1

        verdict, rejection_reasons = _classify_verdict(row, registry_entry)
        rejection_layer = _classify_rejection_layer(row, registry_entry)

        stability_flags = _stability_flags_from_reasoning(
            registry_entry.get("reasoning") if isinstance(registry_entry, dict) else None
        )

        cost_flag = _cost_sensitivity_flag_from_sidecar(cost_sensitivity, strategy_id)
        if cost_flag is not None:
            matched_cost_sensitivity += 1

        regime_flag = _regime_suspicion_flag_from_sidecar(
            regime, (strategy_name, asset, interval)
        )
        if regime_flag is not None:
            matched_regime += 1

        hypothesis = None
        strategy_entry = strategy_index.get(strategy_name)
        if isinstance(strategy_entry, dict):
            hypothesis_value = strategy_entry.get("hypothesis")
            if isinstance(hypothesis_value, str) and hypothesis_value.strip():
                hypothesis = hypothesis_value

        metrics = {
            key: row.get(key)
            for key in _METRIC_FIELDS
            if key in row
        }

        per_candidate.append({
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
            "params_json": row.get("params_json"),
            "strategy_id": strategy_id or None,
            "hypothesis": hypothesis,
            "verdict": verdict,
            "rejection_layer": rejection_layer,
            "rejection_reasons": rejection_reasons,
            "stability_flags": stability_flags,
            "cost_sensitivity_flag": cost_flag,
            "regime_suspicion_flag": regime_flag,
            "metrics": metrics,
        })

    join_stats: dict[str, Any] = {
        "total_rows": len(rows),
        "matched_candidate_registry": matched_registry,
        "unmatched_candidate_registry": unmatched_by_strategy_id,
        "matched_defensibility": matched_defensibility,
        "matched_regime": matched_regime,
        "matched_cost_sensitivity": matched_cost_sensitivity,
    }
    if len(rows) > LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD:
        join_stats["warning"] = "large_candidate_count"

    return per_candidate, join_stats


__all__ = [
    "LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD",
    "VERDICT_NEEDS_INVESTIGATION",
    "VERDICT_PROMOTED",
    "VERDICT_REJECTED_PROMOTION",
    "VERDICT_REJECTED_SCREENING",
    "build_candidate_diagnostics",
]
