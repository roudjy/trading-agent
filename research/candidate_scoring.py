"""Deterministic candidate scoring for v3.12.

Scoring produces normalized 0..1 signals from existing metrics plus
a deliberately ``provisional`` composite. v3.12 does not authorize
any scoring output as a promotion signal; the composite is marked
``authoritative=False`` and ``composite_status="provisional"`` so
downstream consumers cannot mistake it for a ranking authority.

Every component is:
- deterministic (no randomness)
- pure (no IO)
- derived by simple transform of an existing metric
- ``None`` when the source metric is unavailable

No ML, no fit, no arbitrary penalty constants. Drawdown penalty, for
example, is a direct ``1 - min(1, max_dd)`` rather than a fabricated
polynomial.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCORING_FORMULA_VERSION = "v0.1-experimental"


@dataclass(frozen=True)
class ScoringComponents:
    """Normalized 0..1 signals. ``None`` when the source is missing."""

    dsr_signal: float | None
    psr_signal: float | None
    drawdown_signal: float | None
    stability_signal: float | None
    trade_density_signal: float | None
    breadth_signal: float | None
    derivation: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CandidateScore:
    """Full scoring payload for a single candidate.

    The composite carries two independent signals
    (``composite_status`` and ``authoritative``) to prevent any
    downstream consumer from treating this as a promotion authority.
    """

    components: ScoringComponents
    composite_score: float | None
    composite_status: str        # "provisional" in v3.12
    authoritative: bool          # False in v3.12
    scoring_formula_version: str
    derivation_metadata: dict[str, Any]


def _clip_unit(value: float) -> float:
    """Clip value into the [0.0, 1.0] interval."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _sigmoid_like(value: float, scale: float) -> float:
    """Smoothly squash ``value`` into [0, 1].

    Used for unbounded metrics like Sharpe-flavored signals. Returns
    0.5 when value == 0. Not a true sigmoid (no exp, keeps things
    simple and deterministic across platforms).
    """
    if scale <= 0.0:
        return 0.5
    x = value / scale
    # piecewise-linear clipped at [-1, 1]
    if x <= -1.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 0.5 + 0.5 * x


def _dsr_signal(defensibility: dict[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    if defensibility is None:
        return None, {"source_field": "defensibility.dsr_canonical", "status": "missing"}
    raw = defensibility.get("dsr_canonical")
    if raw is None:
        return None, {"source_field": "defensibility.dsr_canonical", "status": "missing"}
    signal = _sigmoid_like(float(raw), scale=3.0)
    return signal, {
        "source_field": "defensibility.dsr_canonical",
        "status": "present",
        "transform": "piecewise_sigmoid_scale=3.0",
    }


def _psr_signal(defensibility: dict[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    if defensibility is None:
        return None, {"source_field": "defensibility.psr", "status": "missing"}
    raw = defensibility.get("psr")
    if raw is None:
        return None, {"source_field": "defensibility.psr", "status": "missing"}
    # PSR is already in [0, 1] semantically (probability); clip for safety
    signal = _clip_unit(float(raw))
    return signal, {
        "source_field": "defensibility.psr",
        "status": "present",
        "transform": "clip_unit",
    }


def _drawdown_signal(v1_entry: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    # selected_params -> not relevant; pull from joined research_latest row if available
    raw = v1_entry.get("max_drawdown")
    if raw is None:
        return None, {"source_field": "max_drawdown", "status": "missing"}
    signal = 1.0 - _clip_unit(abs(float(raw)))
    return signal, {
        "source_field": "max_drawdown",
        "status": "present",
        "transform": "1_minus_clip_unit_abs",
    }


def _trade_density_signal(v1_entry: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    raw = v1_entry.get("trades_per_maand")
    if raw is None:
        return None, {"source_field": "trades_per_maand", "status": "missing"}
    # Normalize: 10 trades/month == 1.0. Nothing magic, documented.
    signal = _clip_unit(float(raw) / 10.0)
    return signal, {
        "source_field": "trades_per_maand",
        "status": "present",
        "transform": "divide_by_10_then_clip_unit",
        "caveat": "reference_value_10_is_documented_not_tuned",
    }


def _stability_signal(
    dsr_signal: float | None,
    psr_signal: float | None,
) -> tuple[float | None, dict[str, Any]]:
    if dsr_signal is None or psr_signal is None:
        return None, {
            "source_field": "dsr_signal+psr_signal",
            "status": "missing_component",
        }
    combined = (dsr_signal + psr_signal) / 2.0
    return combined, {
        "source_field": "dsr_signal+psr_signal",
        "status": "present",
        "transform": "mean_of_two_unit_signals",
    }


def _breadth_signal(
    breadth_context: dict[str, Any] | None,
) -> tuple[float | None, dict[str, Any]]:
    if breadth_context is None:
        return None, {"source_field": "breadth_context", "status": "missing"}
    dominant_share = breadth_context.get("dominant_asset_share")
    if dominant_share is None:
        return None, {"source_field": "breadth_context.dominant_asset_share", "status": "missing"}
    # Less dominance = more breadth. share=1 -> signal=0. share=0.25 -> 0.75.
    signal = 1.0 - _clip_unit(float(dominant_share))
    return signal, {
        "source_field": "breadth_context.dominant_asset_share",
        "status": "present",
        "transform": "1_minus_clip_unit",
    }


def compute_candidate_score(
    v1_entry: dict[str, Any],
    defensibility: dict[str, Any] | None,
    breadth_context: dict[str, Any] | None,
) -> CandidateScore:
    """Compute deterministic scoring for one candidate.

    Inputs are the v1 registry entry (enriched with
    research_latest metrics), optional defensibility payload, and
    optional breadth context dict.

    The composite is the equal-weighted mean of the signals that
    could be computed; missing signals do not penalize. The result
    is marked ``authoritative=False`` and
    ``composite_status="provisional"``.
    """
    dsr, dsr_meta = _dsr_signal(defensibility)
    psr, psr_meta = _psr_signal(defensibility)
    drawdown, dd_meta = _drawdown_signal(v1_entry)
    trade_density, td_meta = _trade_density_signal(v1_entry)
    stability, stab_meta = _stability_signal(dsr, psr)
    breadth, br_meta = _breadth_signal(breadth_context)

    derivation = {
        "dsr_signal": dsr_meta,
        "psr_signal": psr_meta,
        "drawdown_signal": dd_meta,
        "stability_signal": stab_meta,
        "trade_density_signal": td_meta,
        "breadth_signal": br_meta,
    }

    components = ScoringComponents(
        dsr_signal=dsr,
        psr_signal=psr,
        drawdown_signal=drawdown,
        stability_signal=stability,
        trade_density_signal=trade_density,
        breadth_signal=breadth,
        derivation=derivation,
    )

    available = [
        v for v in (dsr, psr, drawdown, stability, trade_density, breadth) if v is not None
    ]
    composite: float | None
    if available:
        composite = sum(available) / len(available)
    else:
        composite = None

    derivation_metadata = {
        "weighting_scheme": "equal_weighted_mean_of_available_components",
        "missing_components_excluded": True,
        "component_count_available": len(available),
        "authoritative_note": "v3.12 composite is provisional; not a promotion authority",
    }

    return CandidateScore(
        components=components,
        composite_score=composite,
        composite_status="provisional",
        authoritative=False,
        scoring_formula_version=SCORING_FORMULA_VERSION,
        derivation_metadata=derivation_metadata,
    )


def score_to_payload(score: CandidateScore) -> dict[str, Any]:
    """Convert a CandidateScore into a plain dict for sidecar serialization.

    Key ordering is intentional and stable; canonical serialization
    will still sort keys, but this representation is tested for shape.
    """
    components_dict = asdict(score.components)
    # derivation is already a dict of dicts; keep as-is
    return {
        "components": components_dict,
        "composite_score": score.composite_score,
        "composite_status": score.composite_status,
        "authoritative": score.authoritative,
        "scoring_formula_version": score.scoring_formula_version,
        "derivation_metadata": score.derivation_metadata,
    }
