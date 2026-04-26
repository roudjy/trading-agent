"""Unified rejection taxonomy for v3.12 (extended in v3.13).

Spec §5 defines eight taxonomy codes that describe WHY a candidate
was rejected at a high level. v3.11 already produces fine-grained
"observed" reason codes (e.g. ``oos_sharpe_below_threshold``,
``psr_below_threshold``) via ``research.promotion``. This module
translates those observed codes into the eight-code taxonomy without
fabricating signals that cannot be defensibly derived.

Design points:

- ``observed_reason_codes`` are the raw codes from
  ``candidate_registry_latest.v1.json``'s ``reasoning`` dict
  (passed / failed / escalated lists). They are carried through
  unchanged for audit.

- ``taxonomy_rejection_codes`` is the conservative derived subset.
  Codes that cannot be reliably derived from existing artifacts
  (``unstable_parameter_neighborhood``, ``single_asset_dependency``)
  are deliberately NOT emitted here; they are future work for
  v3.14+.

- ``taxonomy_derivations`` documents how each emitted taxonomy code
  was produced (which observed sources, which derivation method).
  Per-entry timestamps are deliberately omitted: byte-reproducibility
  at the artifact level is more valuable than local provenance
  timestamps that would drift between reruns.

v3.13 extension
---------------

``regime_concentrated`` is now derived from the v3.13 regime
intelligence sidecar when it is present *and* the candidate has
sufficient regime evidence. Derivation rules, in order:

1. Regime intelligence sidecar **absent** for this candidate → fall
   back to the legacy ``regime_suspicion_flag`` path (unchanged).
2. Sidecar present, ``regime_assessment_status == "sufficient"`` and
   any per-axis dependency score is ≥
   :data:`research.regime_diagnostics.REGIME_CONCENTRATED_THRESHOLD`
   → emit ``regime_concentrated`` with
   ``derivation_method="classifier_output"`` and the triggering axis
   listed under ``observed_sources``.
3. Sidecar present but evidence insufficient → stay silent. We
   prefer silence to overclaiming.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


TAXONOMY_CODES: frozenset[str] = frozenset({
    "insufficient_trades",
    "no_oos_samples",
    "oos_collapse",
    "cost_sensitive",
    "unstable_parameter_neighborhood",
    "regime_concentrated",
    "single_asset_dependency",
    "low_statistical_defensibility",
})


# v3.15.5 — codes that classify a per-candidate rejection as a
# *screening-layer* rejection (vs. a promotion / paper rejection).
#
# When the campaign launcher inspects ``candidate_registry_latest.v1.json``
# after rc=0 and finds every candidate carries ``status == "rejected"``
# with ``reasoning.failed`` strictly contained in this set, the run is
# classified as ``research_rejection`` instead of ``completed_no_survivor``.
#
# These codes MUST stay synchronized with the screening layer in
# ``research/screening_runtime.py`` and ``research/candidate_pipeline.py``.
# Adding a code here that does not appear in those modules will break
# ``test_v3_15_5_screening_reason_codes_exist_in_screening_layer``. Do not
# introduce speculative future codes; only add a code once the screening
# layer actually emits it.
SCREENING_REASON_CODES: frozenset[str] = frozenset({
    # v3.15.5
    "insufficient_trades",
    "no_oos_samples",
    "screening_criteria_not_met",
    # v3.15.7 — exploratory phase failure reasons.
    # Emitted by ``research/screening_criteria.py::_exploratory_criteria``
    # via the screening dispatch in
    # ``research/screening_runtime.py::execute_screening_candidate_samples``.
    # Adding them here keeps v3.15.5
    # ``campaign_launcher._classify_research_rejection`` correctly
    # classifying exploratory-only-rejected runs as
    # ``research_rejection``.
    "expectancy_not_positive",
    "profit_factor_below_floor",
    "drawdown_above_exploratory_limit",
})


# Mapping from v3.11 observed reason codes (from promotion.py
# _check_rejection_rules / _check_escalation_rules) to the
# corresponding taxonomy code. Codes absent from this mapping are
# not translated; they remain in observed_reason_codes only.
OBSERVED_TO_TAXONOMY: dict[str, str] = {
    # Hard rejection gates
    "insufficient_trades": "insufficient_trades",
    "oos_sharpe_below_threshold": "low_statistical_defensibility",
    "drawdown_above_limit": "oos_collapse",
    # Soft escalation gates (defensibility)
    "psr_below_threshold": "low_statistical_defensibility",
    "psr_unavailable": "low_statistical_defensibility",
    "dsr_canonical_below_threshold": "low_statistical_defensibility",
    "dsr_unavailable": "low_statistical_defensibility",
    "bootstrap_sharpe_ci_includes_zero": "low_statistical_defensibility",
    "bootstrap_sharpe_ci_unavailable": "low_statistical_defensibility",
    "noise_warning_fired": "low_statistical_defensibility",
}


# Codes that v3.12 deliberately does NOT derive, even though they are
# part of the taxonomy. They are future work (noted in the post-v3.12
# handoff).
DEFERRED_TAXONOMY_CODES: frozenset[str] = frozenset({
    "unstable_parameter_neighborhood",  # needs neighborhood scan; future work
    "single_asset_dependency",          # needs breadth context; v3.13+
    "no_oos_samples",                   # not yet observable in current flow
})


@dataclass(frozen=True)
class TaxonomyDerivation:
    """How a single taxonomy code was derived.

    Per-entry timestamps are intentionally absent: byte-reproducibility
    of the artifact is enforced at the top-level ``generated_at_utc``.
    """

    taxonomy_code: str
    observed_sources: tuple[str, ...]
    derivation_method: str          # "direct_mapping" | "flag_source" | "n/a"
    caveats: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        """Return a plain dict with stable key ordering for sidecar serialization."""
        payload = asdict(self)
        # tuples -> lists for JSON
        payload["observed_sources"] = list(self.observed_sources)
        payload["caveats"] = list(self.caveats)
        return payload


def collect_observed_reason_codes(v1_entry: dict[str, Any]) -> tuple[str, ...]:
    """Return the raw promotion reason codes from a v1 registry entry.

    Pulls from ``reasoning.failed`` and ``reasoning.escalated``.
    Passed codes are not rejection-relevant and are not included here
    (they live in the registry-v2 entry separately if needed).
    """
    reasoning = v1_entry.get("reasoning") or {}
    failed = list(reasoning.get("failed") or [])
    escalated = list(reasoning.get("escalated") or [])
    return tuple(failed + escalated)


def _flag_from_sidecar(
    sidecar: dict[str, Any] | None,
    candidate_key: tuple[str, str, str],
) -> bool | None:
    """Extract a per-candidate boolean flag from an optional sidecar.

    Currently supports two shapes:
    - dict keyed by ``"strategy_name|asset|interval"`` -> {"flag": bool}
    - dict with ``"candidates": [{"strategy_name", "asset", "interval", "flag": bool}]``

    Returns None if the sidecar does not carry a flag for this candidate.
    """
    if sidecar is None:
        return None

    strategy_name, asset, interval = candidate_key
    # shape 1: flat dict keyed by composite id
    composite = f"{strategy_name}|{asset}|{interval}"
    direct = sidecar.get(composite)
    if isinstance(direct, dict) and "flag" in direct:
        value = direct["flag"]
        return bool(value) if value is not None else None

    # shape 2: list of entries
    for entry in sidecar.get("candidates") or []:
        if (
            entry.get("strategy_name") == strategy_name
            and entry.get("asset") == asset
            and entry.get("interval") == interval
            and "flag" in entry
        ):
            value = entry["flag"]
            return bool(value) if value is not None else None
    return None


def _regime_concentrated_from_intelligence(
    regime_intelligence: dict[str, Any] | None,
    candidate_id: str,
    threshold: float,
) -> tuple[bool, tuple[str, ...], str] | None:
    """Inspect the v3.13 regime intelligence sidecar for one candidate.

    Returns ``None`` when the sidecar does not carry a matching
    entry for this candidate (caller falls back to the legacy
    ``regime_suspicion_flag`` path).

    Returns a tuple ``(emit, triggering_axes, status)`` otherwise:
    - ``emit`` is True iff evidence is sufficient and at least one
      per-axis dependency score ≥ ``threshold``.
    - ``triggering_axes`` lists axes whose score met the threshold.
    - ``status`` is one of "sufficient"/"insufficient_evidence" for
      the caveats payload.
    """
    if not regime_intelligence or not candidate_id:
        return None
    for entry in regime_intelligence.get("entries") or []:
        if entry.get("candidate_id") != candidate_id:
            continue
        assessment = entry.get("regime_assessment_status")
        if assessment != "sufficient":
            return False, (), "insufficient_evidence"
        scores = entry.get("regime_dependency_scores") or {}
        triggering: list[str] = []
        for axis in ("trend", "vol", "width"):
            score = scores.get(axis)
            if isinstance(score, (int, float)) and float(score) >= threshold:
                triggering.append(axis)
        emit = bool(triggering)
        return emit, tuple(triggering), "sufficient"
    return None


def derive_taxonomy(
    v1_entry: dict[str, Any],
    regime_diag: dict[str, Any] | None,
    cost_sens: dict[str, Any] | None,
    regime_intelligence: dict[str, Any] | None = None,
    regime_concentrated_threshold: float = 0.7,
) -> tuple[tuple[str, ...], tuple[TaxonomyDerivation, ...]]:
    """Derive taxonomy codes for a single candidate.

    Returns ``(codes, derivations)`` where:
    - ``codes`` is a sorted, deduplicated tuple of taxonomy codes
    - ``derivations`` is a tuple (sorted by ``taxonomy_code``) that
      explains how each code was produced

    Only taxonomy codes that can be defensibly derived from available
    artifacts are emitted. :data:`DEFERRED_TAXONOMY_CODES` are
    deliberately skipped.

    When ``regime_intelligence`` is provided (the v3.13 sidecar) and
    carries an entry for this candidate, it takes precedence over
    the legacy ``regime_suspicion_flag`` path: the regime-concentrated
    code is emitted only when evidence is sufficient *and* a
    per-axis dependency score exceeds
    ``regime_concentrated_threshold``.
    """
    observed = collect_observed_reason_codes(v1_entry)
    buckets: dict[str, list[str]] = {}

    # Direct mapping from observed reason codes.
    for code in observed:
        mapped = OBSERVED_TO_TAXONOMY.get(code)
        if mapped is None or mapped in DEFERRED_TAXONOMY_CODES:
            continue
        buckets.setdefault(mapped, []).append(code)

    # Flag-sourced codes (cost_sensitive, regime_concentrated legacy).
    key = (
        v1_entry.get("strategy_name", ""),
        v1_entry.get("asset", ""),
        v1_entry.get("interval", ""),
    )

    cost_flag = _flag_from_sidecar(cost_sens, key)
    if cost_flag is True:
        buckets.setdefault("cost_sensitive", []).append("cost_sensitivity_flag")

    # v3.13: prefer classifier-output derivation when the regime
    # intelligence sidecar carries an entry for this candidate.
    regime_intelligence_result = _regime_concentrated_from_intelligence(
        regime_intelligence,
        str(v1_entry.get("strategy_id") or ""),
        regime_concentrated_threshold,
    )
    regime_classifier_used = False
    if regime_intelligence_result is not None:
        regime_classifier_used = True
        emit, triggering_axes, _status = regime_intelligence_result
        if emit:
            # Preserve the triggering axes in observed_sources for audit.
            buckets.setdefault("regime_concentrated", []).extend(
                f"regime_dependency_score_{axis}" for axis in triggering_axes
            )
    else:
        # Legacy flag-source fallback only when the v3.13 sidecar is
        # absent for this candidate.
        regime_flag = _flag_from_sidecar(regime_diag, key)
        if regime_flag is True:
            buckets.setdefault("regime_concentrated", []).append("regime_suspicion_flag")

    derivations: list[TaxonomyDerivation] = []
    for code, sources in buckets.items():
        if code == "regime_concentrated":
            method = (
                "classifier_output" if regime_classifier_used else "flag_source"
            )
        elif code == "cost_sensitive":
            method = "flag_source"
        else:
            method = "direct_mapping"
        caveats: tuple[str, ...] = ()
        if code == "low_statistical_defensibility" and len(sources) == 1:
            caveats = ("single_observed_signal",)
        derivations.append(
            TaxonomyDerivation(
                taxonomy_code=code,
                observed_sources=tuple(sorted(set(sources))),
                derivation_method=method,
                caveats=caveats,
            )
        )

    derivations.sort(key=lambda d: d.taxonomy_code)
    codes = tuple(d.taxonomy_code for d in derivations)
    return codes, tuple(derivations)


def all_known_codes() -> Iterable[str]:
    """Iterate the full taxonomy in sorted order (for tests and docs)."""
    return sorted(TAXONOMY_CODES)
