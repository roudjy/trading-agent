"""Research presets — first-class run configurations for v3.10.

A preset is a frozen bundle of (universe, timeframe, strategy-bundle,
screening mode, cost mode) that the ``researchctl`` CLI, the Flask
preset API, and the systemd-timer all feed into ``run_research.py``.
Presets are the v3.10 replacement for the copy-paste loop between
terminal / Claude / GPT.

Layer boundaries:

- This module is pure configuration. It imports from
  ``research.registry`` (the strategy source-of-truth) for
  validation, but NEVER introduces new strategy registrations. A
  preset that names a strategy which is not yet in the registry is
  surfaced as ``status="planned"`` with a ``backlog_reason`` so the
  UI can render it and the scheduler can skip it.
- Presets do not touch the frozen ``ROW_SCHEMA`` /
  ``JSON_*_SCHEMA`` tuples in ``research/results.py``. New
  per-run metadata lands in a separate sidecar
  (``research/run_meta_latest.v1.json``) owned by
  ``research.run_state``.
- ``diagnostic_only`` / ``excluded_from_candidate_promotion`` /
  ``excluded_from_daily_scheduler`` are hard flags honoured by the
  promotion layer and the scheduler unit. The safe default on
  missing metadata is "excluded" — a diagnostic run must never be
  silently promoted (see ADR-011 §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from research.registry import STRATEGIES


ScreeningMode = Literal["strict", "lenient", "diagnostic"]
CostMode = Literal["realistic", "zero", "stress"]
PresetStatus = Literal["stable", "planned", "diagnostic", "not_executable"]
PresetClass = Literal["baseline", "diagnostic", "experimental"]


@dataclass(frozen=True)
class ResearchPreset:
    """Frozen preset descriptor consumed by CLI / API / scheduler.

    Two orthogonal classification axes:

    - ``status`` is the *lifecycle* label ("stable" / "planned" /
      "diagnostic" / "not_executable"). It answers: may the scheduler
      run this preset today? Honoured by the scheduler + promotion
      guards.
    - ``preset_class`` (v3.11) is the *research role* ("baseline" /
      "diagnostic" / "experimental"). It answers: what function does
      this preset serve in our research? A diagnostic preset may be
      ``status="stable"`` (always-on observability); an experimental
      preset may be ``status="planned"`` (backlog). Neither field is
      derived from the other.

    v3.11 hypothesis metadata (``rationale``, ``expected_behavior``,
    ``falsification``) elaborates the narrative ``hypothesis`` field.
    On enabled presets these are expected to be non-empty;
    ``validate_preset`` surfaces missing values as soft issues so the
    runner can warn without self-blocking (see ADR-011 §9 and the
    v3.11 addendum).
    """

    name: str
    hypothesis: str
    universe: tuple[str, ...]
    timeframe: str
    bundle: tuple[str, ...]
    screening_mode: ScreeningMode = "strict"
    cost_mode: CostMode = "realistic"
    status: PresetStatus = "stable"
    enabled: bool = True
    diagnostic_only: bool = False
    excluded_from_daily_scheduler: bool = False
    excluded_from_candidate_promotion: bool = False
    regime_filter: str | None = None
    regime_modes: tuple[str, ...] = field(default_factory=tuple)
    optional_bundle: tuple[str, ...] = field(default_factory=tuple)
    backlog_reason: str | None = None
    preset_class: PresetClass = "experimental"
    rationale: str = ""
    expected_behavior: str = ""
    falsification: tuple[str, ...] = field(default_factory=tuple)
    enablement_criteria: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Preset catalog
# ---------------------------------------------------------------------------

_TREND_EQUITIES_UNIVERSE: tuple[str, ...] = (
    "NVDA", "AMD", "ASML", "MSFT", "META", "AMZN", "TSM",
)

_PAIRS_EQUITIES_UNIVERSE: tuple[str, ...] = (
    "NVDA/AMD", "META/GOOGL", "AAPL/MSFT",
)

_CRYPTO_DIAGNOSTIC_UNIVERSE: tuple[str, ...] = (
    "BTC-EUR", "ETH-EUR",
)

_TREND_PULLBACK_CRYPTO_UNIVERSE: tuple[str, ...] = (
    "BTC-EUR", "ETH-EUR", "SOL-EUR",
)


PRESETS: tuple[ResearchPreset, ...] = (
    ResearchPreset(
        name="trend_equities_4h_baseline",
        hypothesis=(
            "Twee orthogonale trendstrategieen (SMA crossover + breakout "
            "momentum) capturen persistent directional moves op 4h equities "
            "zonder management-varianten. Doel: een stabiele daily default "
            "zonder strategie-explosie."
        ),
        universe=_TREND_EQUITIES_UNIVERSE,
        timeframe="4h",
        bundle=("sma_crossover", "breakout_momentum"),
        optional_bundle=("trend_pullback",),
        screening_mode="strict",
        cost_mode="realistic",
        status="stable",
        enabled=True,
        preset_class="baseline",
        rationale=(
            "Large-cap US equities tonen historisch persistente trend "
            "episodes op multi-bar timeframes (orchestrator_brief §1.1, "
            "§4.1). Twee orthogonale trend families (MA-crossover en "
            "breakout) dekken zowel gradual trend entries als "
            "range-expansion entries zonder overlap in signal construction."
        ),
        expected_behavior=(
            "Positieve OOS Sharpe op >=1 asset/interval combinatie na "
            "walk-forward + promotion gates (PSR >=0.90, DSR >0.0, "
            "drawdown <=0.35). Stability flags grotendeels schoon op "
            "gepromoveerde runs."
        ),
        falsification=(
            "Alle runs falen op insufficient_trades binnen de 4h window "
            "op dit universe.",
            "Elke run die screening haalt faalt in promotion op "
            "bootstrap_sharpe_ci_includes_zero over 3 achtereenvolgende "
            "runs.",
            "Deflated Sharpe structureel negatief ondanks volume in "
            "trending equity regimes (Q2-2026 big-tech rallies).",
        ),
    ),
    ResearchPreset(
        name="pairs_equities_daily_baseline",
        hypothesis=(
            "Equity-paren via z-score spread mean reversion. Requires OLS "
            "hedge ratio + multi-reference_asset support die niet in v3.10 "
            "scope zit (pairs_zscore is v3.6 scope-lock met fixed "
            "hedge_ratio=1.0 en reference_asset=ETH-EUR)."
        ),
        universe=_PAIRS_EQUITIES_UNIVERSE,
        timeframe="1d",
        bundle=("pairs_zscore",),
        screening_mode="strict",
        cost_mode="realistic",
        status="planned",
        enabled=False,
        backlog_reason=(
            "v3.11 equity-pairs ADR required: OLS hedge ratio + "
            "multi-reference_asset. See ADR-011 \u00a77."
        ),
        preset_class="experimental",
        rationale=(
            "Mean-reverting z-score spreads op equity-paren zijn "
            "wiskundig orthogonaal aan de trend-hypothese van "
            "trend_equities_4h_baseline en aan de crypto MR-diagnose "
            "van crypto_diagnostic_1h. Een eventueel werkende edge "
            "hier representeert een aparte strategiefamilie en mag "
            "alleen enabled worden nadat de onderliggende wiskundige "
            "voorwaarden — OLS hedge ratio, multi-reference_asset, "
            "cointegration discipline — architecturaal ondersteund "
            "zijn. Dit preset staat bewust in de catalog als "
            "product-/roadmapbeslissing: niet runnable, niet stil "
            "verborgen."
        ),
        expected_behavior=(
            "Zou — na enablement — per equity-paar een spread-signaal "
            "produceren dat statistisch onafhankelijk is van de "
            "directional trend-hypothese. Een positieve Deflated "
            "Sharpe op \u22651 paar/interval-combinatie op OOS, met "
            "cointegration-stabiliteit en bounded drawdown, zou het "
            "preset tot een eigen volwaardig research-pad maken."
        ),
        falsification=(
            "Paren vertonen geen stationaire spread: ADF of "
            "Johansen-test faalt consistent op de gekozen universe "
            "over \u22653 achtereenvolgende runs.",
            "OLS hedge ratio is fold-instabiel: beta's verschuiven "
            ">50% tussen walk-forward folds zonder economisch "
            "motief.",
            "Kosten-gevoeligheid vreet de edge op: na Bitvavo / IBKR "
            "fee-profile sluit bootstrap_sharpe_ci zero in op elk "
            "geteste paar.",
        ),
        enablement_criteria=(
            "v3.11 equity-pairs ADR geschreven en goedgekeurd: "
            "scope, hedge-ratio-methode (OLS vs rolling vs "
            "cointegration), multi-reference_asset discipline.",
            "Fitted-feature abstractie (v3.7) uitgebreid naar "
            "multi-asset fit zodat hedge_ratio per fold "
            "fit-on-train / transform-on-test volgt.",
            "Pair-universe selectiebeleid vastgelegd: statische "
            "lijst vs cointegration-geselecteerd; rebalancing-"
            "frequentie; survivorship-bias mitigatie.",
            "Pairs-specifieke screening en falsificatiegates "
            "bevestigd in rejection_taxonomy (o.a. "
            "stationarity_fail, hedge_instability, "
            "insufficient_cointegration).",
        ),
    ),
    ResearchPreset(
        name="trend_regime_filtered_equities_4h",
        hypothesis=(
            "Zelfde trendbundel als preset 1 maar onder een regime-filter "
            "(trend_only + low_vol_only afgeleid van bollinger_regime). "
            "Diagnostisch: verbetert regimefiltering de trendstrategieen? "
            "Bollinger mean-reversion is NIET primair in deze preset."
        ),
        universe=_TREND_EQUITIES_UNIVERSE,
        timeframe="4h",
        bundle=("sma_crossover", "breakout_momentum"),
        regime_filter="bollinger_regime_derived",
        regime_modes=("trend_only", "low_vol_only"),
        screening_mode="strict",
        cost_mode="realistic",
        status="stable",
        enabled=True,
        preset_class="diagnostic",
        rationale=(
            "Trend strategies zijn gevoelig voor choppy / mean-reverting "
            "regimes. Door dezelfde trendbundel te draaien onder een "
            "bollinger-afgeleid regime-filter (trend_only + low_vol_only) "
            "krijgen we een directe vergelijking met de ongefilterde "
            "baseline preset — zo kunnen we zien of regimefiltering de "
            "trend-edge versterkt dan wel beknot."
        ),
        expected_behavior=(
            "Gefilterde runs vertonen hogere OOS Sharpe en/of lagere "
            "drawdown vs de ongefilterde baseline op dezelfde "
            "asset/interval combinaties. Minder trades per maand door "
            "filtering is verwacht."
        ),
        falsification=(
            "Gefilterde runs scoren consistent lager dan ongefilterde "
            "baseline op Sharpe over 3 achtereenvolgende runs — dan is "
            "het regime-filter ruis.",
            "Regime-filter reduceert trade count onder min_oos_trades "
            "waardoor elke run in promotion faalt op insufficient_trades.",
        ),
    ),
    ResearchPreset(
        name="trend_pullback_crypto_1h",
        hypothesis=(
            "v3.15.3 controlled active_discovery: een trend pullback v1 "
            "thin strategy (max 3 parameters) test of een vol-genormaliseerde "
            "pullback in een gevestigde EMA-trend op crypto 1h een edge "
            "oplevert. Bridges naar de strategy_hypothesis_catalog row "
            "trend_pullback_v1 / family trend_pullback / status "
            "active_discovery."
        ),
        universe=_TREND_PULLBACK_CRYPTO_UNIVERSE,
        timeframe="1h",
        bundle=("trend_pullback_v1",),
        screening_mode="strict",
        cost_mode="realistic",
        status="stable",
        enabled=True,
        diagnostic_only=False,
        excluded_from_daily_scheduler=False,
        preset_class="experimental",
        rationale=(
            "Crypto 1h vertoont episodes van persistente trend afgewisseld "
            "met intra-trend pullbacks. De v3.15.3 catalog markeert "
            "trend_pullback als enige active_discovery hypothese; deze "
            "preset is het enige executable kanaal waarmee de v3.15.2 "
            "Campaign Operating Layer die hypothese autonoom kan testen, "
            "negeren, falsificeren of cooldownen. Max 3 parameters per "
            "AGENTS.md."
        ),
        expected_behavior=(
            "Per fold: long entries alleen wanneer ema_fast > ema_slow EN "
            "pullback_distance < -entry_k. Flat zodra trend breekt of "
            "pullback resolveert. Bounded grid (\u22648 combinaties) — "
            "geen brute-force search. Promotion gates uit v3.12 (PSR, DSR, "
            "drawdown) blijven leidend; geen zelfgekozen drempels."
        ),
        falsification=(
            "Drie achtereenvolgende daily_primary runs falen op "
            "insufficient_trades binnen het crypto 1h universum.",
            "Cost-sensitivity (v3.8) zet bootstrap_sharpe_ci over zero "
            "op elk asset/parameter combo \u2014 cost_fragile bevestigd.",
            "Parameter-neighborhood instabiel: top combos verschuiven "
            ">50% tussen 3 walk-forward runs zonder regime-shift.",
            "Geen baseline edge: trend_pullback_v1 onderpresteert "
            "ema_trend_baseline op alle asset/interval combinaties.",
        ),
        enablement_criteria=(
            "Hypothesis catalog status remains 'active_discovery'; "
            "promotion to other status flows via the catalog, not via "
            "this preset.",
            "v3.15.2 Campaign Operating Layer hourly tick is healthy "
            "(systemd-timer Active(running), pin block live_eligible=False).",
            "Bounded parameter grid (\u22648 combos) verified each run.",
        ),
    ),
    ResearchPreset(
        name="crypto_diagnostic_1h",
        hypothesis=(
            "Crypto 1h intraday MR is diagnostisch, niet primaire alpha-"
            "richting (orchestrator_brief). Preset loopt om rejection "
            "patronen te observeren; mag nooit promoten of auto-scheduled "
            "draaien."
        ),
        universe=_CRYPTO_DIAGNOSTIC_UNIVERSE,
        timeframe="1h",
        bundle=("rsi", "bollinger_mr"),
        screening_mode="diagnostic",
        cost_mode="stress",
        status="diagnostic",
        enabled=True,
        diagnostic_only=True,
        excluded_from_daily_scheduler=True,
        excluded_from_candidate_promotion=True,
        preset_class="diagnostic",
        rationale=(
            "Crypto 1h mean reversion is volgens orchestrator_brief "
            "§7.2 deprioriteerd als primaire alpha richting. Deze preset "
            "draait onder stress cost_mode + diagnostic screening om de "
            "rejection-patronen zichtbaar te houden, zodat we weten "
            "wanneer de aannames veranderen (bijv. marktstructuur shift)."
        ),
        expected_behavior=(
            "Alle runs falen in screening of promotion (verwachte "
            "uitkomst). Rejection reasons zijn stabiel tussen runs: "
            "voornamelijk negatieve Sharpe of insufficient_trades. "
            "Geen enkele run promoteert (excluded_from_candidate_promotion)."
        ),
        falsification=(
            "Een crypto 1h MR run promoteert ondanks diagnostic status "
            "— duidt op regressie in de exclusion pipeline.",
            "Rejection patronen wijken plotseling sterk af van historische "
            "distributie — signaal dat marktstructuur kantelt en de "
            "diagnostische hypothese herzien moet worden.",
        ),
    ),
)


_DEFAULT_DAILY_PRESET = "trend_equities_4h_baseline"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_presets() -> list[ResearchPreset]:
    return list(PRESETS)


def get_preset(name: str) -> ResearchPreset:
    for preset in PRESETS:
        if preset.name == name:
            return preset
    known = ", ".join(p.name for p in PRESETS)
    raise KeyError(f"unknown preset {name!r}; known: {known}")


def default_daily_preset() -> ResearchPreset:
    """Preset used by the systemd-timer on the VPS."""
    return get_preset(_DEFAULT_DAILY_PRESET)


def resolve_preset_bundle(preset: ResearchPreset) -> list[dict]:
    """Return the registry entries for the preset bundle.

    Bundle names that are not in the registry are silently dropped (the
    preset still carries them for UI surfacing; the resolver only returns
    executable entries). Disabled presets always return an empty list so
    no accidental execution can happen.
    """
    if not preset.enabled:
        return []
    known_by_name = {strategy["name"]: strategy for strategy in STRATEGIES}
    resolved: list[dict] = []
    for entry_name in preset.bundle:
        if entry_name in known_by_name:
            resolved.append(known_by_name[entry_name])
    return resolved


def validate_preset(preset: ResearchPreset) -> list[str]:
    """Return a list of issues; empty list means the preset is executable.

    v3.11: hypothesis metadata (rationale, expected_behavior,
    falsification, preset_class) produces *soft* issues for enabled
    presets when fields are empty. Callers treat these as warnings by
    default. The runner may elevate to hard failures when the
    ``QRE_STRICT_PRESET_VALIDATION`` env var is set (see
    ``run_research._preset_validation_is_strict``).
    """
    issues: list[str] = []
    if not preset.enabled:
        if preset.backlog_reason is None:
            issues.append("disabled preset must carry a backlog_reason")
        return issues

    known = {strategy["name"] for strategy in STRATEGIES}
    missing = [name for name in preset.bundle if name not in known]
    if missing:
        issues.append(
            f"bundle references unknown strategies: {sorted(missing)}"
        )
    resolved = resolve_preset_bundle(preset)
    if not resolved:
        issues.append("bundle has no executable strategies after resolution")

    # Pair identifiers (NVDA/AMD) only make sense for pairs strategies.
    pair_entries = [a for a in preset.universe if "/" in a]
    if pair_entries and "pairs_zscore" not in preset.bundle:
        issues.append(
            "universe contains pair identifiers but bundle does not include "
            "pairs_zscore"
        )

    if preset.diagnostic_only and not preset.excluded_from_candidate_promotion:
        issues.append(
            "diagnostic_only preset must also set "
            "excluded_from_candidate_promotion"
        )

    # v3.11 soft-issue: hypothesis metadata completeness on enabled presets.
    if not preset.rationale.strip():
        issues.append("hypothesis_metadata_missing: rationale is empty")
    if not preset.expected_behavior.strip():
        issues.append(
            "hypothesis_metadata_missing: expected_behavior is empty"
        )
    if not preset.falsification:
        issues.append(
            "hypothesis_metadata_missing: falsification criteria empty"
        )

    return issues


def hypothesis_metadata_issues(preset: ResearchPreset) -> list[str]:
    """Return only the v3.11 hypothesis-metadata soft issues.

    Helper for the runner: lets us emit a dedicated
    ``preset_validation_warning`` event distinct from structural
    issues (unknown strategies, mis-shaped universe, etc.).
    """
    return [
        issue
        for issue in validate_preset(preset)
        if issue.startswith("hypothesis_metadata_missing:")
    ]


def daily_schedulable_presets() -> list[ResearchPreset]:
    """Presets the systemd-timer is allowed to fire."""
    return [
        preset
        for preset in PRESETS
        if preset.enabled and not preset.excluded_from_daily_scheduler
    ]


def _decision_for(preset: ResearchPreset) -> dict:
    """Backend-side product-decision inference for a preset card.

    Keeps UI rendering logic out of the frontend: a disabled/planned
    preset is not a bug, it is a deliberate product / roadmap decision
    and this helper records that as a first-class field so consumers
    don't have to reconstruct it from status / enabled / backlog_reason
    themselves.

    ``kind`` vocabulary (closed):
    - ``disabled_planned``  — enabled=False with a backlog_reason.
    - ``diagnostic_only``   — enabled but flagged diagnostic, never
      promoted.
    - ``scheduler_excluded`` — enabled but held back from the daily
      scheduler.
    - ``null``              — no product decision beyond "run normally".
    """
    if not preset.enabled:
        return {
            "is_product_decision": True,
            "kind": "disabled_planned",
            "summary": (
                "Bewuste product-/roadmapbeslissing: preset staat in "
                "de catalog maar is niet runnable tot de enablement-"
                "criteria zijn voldaan. Dit is geen bug."
            ),
            "requires_enablement": True,
        }
    if preset.diagnostic_only:
        return {
            "is_product_decision": True,
            "kind": "diagnostic_only",
            "summary": (
                "Diagnostisch preset: draait voor observatie maar "
                "wordt nooit gepromoveerd naar candidate-selectie."
            ),
            "requires_enablement": False,
        }
    if preset.excluded_from_daily_scheduler:
        return {
            "is_product_decision": True,
            "kind": "scheduler_excluded",
            "summary": (
                "Preset is runnable maar bewust niet opgenomen in de "
                "dagelijkse scheduler. Start handmatig wanneer nodig."
            ),
            "requires_enablement": False,
        }
    return {
        "is_product_decision": False,
        "kind": None,
        "summary": "",
        "requires_enablement": False,
    }


def preset_to_card(preset: ResearchPreset) -> dict:
    """Flatten a preset into a JSON-safe card for the UI.

    v3.15.1 additive: ``enablement_criteria`` + ``decision`` surface.
    The ``decision`` dict carries backend-side inference so the
    frontend renders based on explicit product state, not by
    reconstructing it from (status, enabled, backlog_reason, ...).
    """
    return {
        "name": preset.name,
        "hypothesis": preset.hypothesis,
        "universe": list(preset.universe),
        "timeframe": preset.timeframe,
        "bundle": list(preset.bundle),
        "optional_bundle": list(preset.optional_bundle),
        "screening_mode": preset.screening_mode,
        "cost_mode": preset.cost_mode,
        "status": preset.status,
        "enabled": preset.enabled,
        "diagnostic_only": preset.diagnostic_only,
        "excluded_from_daily_scheduler": preset.excluded_from_daily_scheduler,
        "excluded_from_candidate_promotion": preset.excluded_from_candidate_promotion,
        "regime_filter": preset.regime_filter,
        "regime_modes": list(preset.regime_modes),
        "backlog_reason": preset.backlog_reason,
        "preset_class": preset.preset_class,
        "rationale": preset.rationale,
        "expected_behavior": preset.expected_behavior,
        "falsification": list(preset.falsification),
        "enablement_criteria": list(preset.enablement_criteria),
        "decision": _decision_for(preset),
    }


__all__ = [
    "CostMode",
    "PRESETS",
    "PresetClass",
    "PresetStatus",
    "ResearchPreset",
    "ScreeningMode",
    "daily_schedulable_presets",
    "default_daily_preset",
    "get_preset",
    "hypothesis_metadata_issues",
    "list_presets",
    "preset_to_card",
    "resolve_preset_bundle",
    "validate_preset",
]
