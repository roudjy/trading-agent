"""v3.15.16 Intelligent Routing Layer — diagnostic-aware routing
signals schema and read-only projector.

Implements the first queue-driven Roadmap v6 implementation unit
selected by A20e:

* unit id: ``u_v3_15_16_diagnostic_routing_signals_schema_001``
* phase:   ``v3.15.16`` — Intelligent Routing Layer
* authority: ``AUTO_ALLOWED`` at LOW risk (per A20c verdict)

This module is **schema and projector only**. It does NOT perform
routing decisions, does NOT mutate any campaign queue, does NOT
alter campaign execution, does NOT change research runtime
behavior, does NOT add strategy logic, and does NOT trade. The
emitted projection is a closed-vocabulary description of the
diagnostic-aware routing signal families that future v3.15.16
follow-up units may consume — once an actual deterministic
routing integration unit is approved by the operator and selected
through A20e.

Roadmap v6 + Addendum 1 anchor:

* Roadmap v6 §v3.15.16 — Intelligent Routing Layer
* Roadmap v6 Addendum §9 v3.15.16 — diagnostic-aware routing
  signals (entropy / tail / criticality / network / quorum /
  external-intelligence / dead-zone suppression).

Hard guarantees (pinned by tests):

* Stdlib only.
* No subprocess, no network, no ``gh``, no ``git``, no GitHub
  API.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``,
  ``reporting.execution_authority``.
* No LLM, no external API, no fuzzy parsing, no file-content
  parsing of any canonical roadmap document at runtime.
* Atomic write only under
  ``logs/intelligent_routing_diagnostic_signals/``.
* Deterministic output: same input + injected
  ``generated_at_utc`` → byte-identical artefact.
* Closed vocabularies for ``ROUTING_SIGNAL_FAMILY``,
  ``ROUTING_SIGNAL_STATUS``, ``ROUTING_SIGNAL_DIRECTION``,
  ``ROUTING_SIGNAL_SOURCE``, ``ROUTING_SIGNAL_TARGET_LAYER``.
* No campaign queue mutation; no strategy generation; no
  runtime / trading / paper / shadow / broker / risk / live
  authority granted (pinned by ``projection_invariants``).
* Diagnostics do not trade. External data is not alpha.

CLI::

    python -m reporting.intelligent_routing_diagnostic_signals
    python -m reporting.intelligent_routing_diagnostic_signals --no-write
    python -m reporting.intelligent_routing_diagnostic_signals --status
    python -m reporting.intelligent_routing_diagnostic_signals --indent 2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.routing_signals.0"
REPORT_KIND: Final[str] = "intelligent_routing_diagnostic_signals"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed signal-family vocabulary. Mirrors the Addendum 1
#: diagnostic families plus the routing-specific ``dead_zone`` and
#: ``external_intelligence`` buckets.
ROUTING_SIGNAL_FAMILY: Final[tuple[str, ...]] = (
    "entropy",
    "tail",
    "criticality",
    "network",
    "quorum",
    "external_intelligence",
    "dead_zone",
    "null_model",
    "barrier",
    "resonance",
    "adversarial",
    "seismic",
    "turbulence",
    "market_language",
)

#: Closed signal-status vocabulary. Every emitted signal lands in
#: ``schema_only`` today — this unit defines the schema, not the
#: runtime integration. Future approved units may lift signals to
#: other statuses through A20a/A20b/A20c amendments.
ROUTING_SIGNAL_STATUS: Final[tuple[str, ...]] = (
    "schema_only",
    "advisory_planned",
    "advisory_active",
    "suppressed",
    "deprecated",
)

#: Closed signal-direction vocabulary. Describes how a signal
#: contributes to routing priority. Never a buy/sell direction —
#: diagnostics do not trade.
ROUTING_SIGNAL_DIRECTION: Final[tuple[str, ...]] = (
    "prioritize",
    "deprioritize",
    "suppress",
    "neutral",
    "require_confirmation",
)

#: Closed signal-source vocabulary. Lists the upstream artefact
#: or module each signal logically depends on. Today every entry
#: is a future / planned module; this unit only declares the
#: shape.
ROUTING_SIGNAL_SOURCE: Final[tuple[str, ...]] = (
    "research/diagnostics/null_models.py",
    "research/diagnostics/tail.py",
    "research/diagnostics/entropy.py",
    "research/diagnostics/criticality.py",
    "research/diagnostics/network.py",
    "research/diagnostics/quorum.py",
    "research/diagnostics/barrier.py",
    "research/diagnostics/resonance.py",
    "research/diagnostics/adversarial.py",
    "research/diagnostics/seismic.py",
    "research/diagnostics/turbulence.py",
    "research/diagnostics/language.py",
    "research/external_intelligence/source_registry.py",
    "research/external_intelligence/quality_gates.py",
    "research/external_intelligence/freshness_checks.py",
    "research/external_intelligence/public_data_seed_registry.py",
)

#: Closed target-layer vocabulary. Mirrors the Roadmap v6 layer
#: stack: signals describe the layer they advise, not the layer
#: they execute on (none execute — they are diagnostics).
ROUTING_SIGNAL_TARGET_LAYER: Final[tuple[str, ...]] = (
    "market_behavior",
    "hypothesis_discovery",
    "strategy_mapping",
    "preset",
    "campaign",
    "funnel",
    "evidence",
    "policy",
)


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-signal schema.
ROUTING_DIAGNOSTIC_SIGNAL_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "family",
    "name",
    "description",
    "source",
    "target_layer",
    "direction",
    "status",
    "expected_information_gain_effect",
    "dead_zone_risk_effect",
    "orthogonality_effect",
    "public_data_quality_effect",
    "confirmation_requirement_effect",
    "allowed_use",
    "forbidden_use",
    "required_inputs",
    "missing_input_behavior",
)

#: Top-level projection schema.
ROUTING_SIGNAL_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "signals",
    "projection_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_NAME_LEN: Final[int] = 200
MAX_DESCRIPTION_LEN: Final[int] = 600
MAX_EFFECT_LEN: Final[int] = 200
MAX_ALLOWED_USE_ITEMS: Final[int] = 8
MAX_FORBIDDEN_USE_ITEMS: Final[int] = 12
MAX_REQUIRED_INPUTS: Final[int] = 6
MAX_LIST_ITEM_LEN: Final[int] = 200
MAX_MISSING_INPUT_BEHAVIOR_LEN: Final[int] = 200


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "intelligent_routing_diagnostic_signals"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/intelligent_routing_diagnostic_signals/latest.json"
)

#: Atomic-write allowlist (POSIX substring form). Any write target
#: whose path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/intelligent_routing_diagnostic_signals/"


# ---------------------------------------------------------------------------
# Projection invariants emitted on every snapshot
# ---------------------------------------------------------------------------

_BASE_PROJECTION_INVARIANTS: Final[dict[str, bool]] = {
    # Doctrinal anchors — these must remain True forever.
    "diagnostics_do_not_trade": True,
    "external_data_is_not_alpha": True,
    "read_only": True,
    # Authority pins carried forward from the A20 invariant chain.
    "no_runtime_trading_authority": True,
    "no_campaign_queue_mutation": True,
    "no_strategy_generation": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "no_routing_mutation": True,
    "no_research_runtime_change": True,
    "step5_implementation_allowed": False,
    "no_branch_creation": True,
    "no_pr_creation": True,
    "no_merge_or_deploy": True,
    "no_mutation_routes": True,
    "no_approval_buttons": True,
    "writes_only_intelligent_routing_diagnostic_signals_log": True,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _bounded_str_tuple(
    values: tuple[str, ...] | list[str], max_items: int, max_len: int
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        b = _bounded_str(v, max_len)
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(b)
        if len(out) >= max_items:
            break
    return out


# ---------------------------------------------------------------------------
# Re-usable forbidden-use baselines
# ---------------------------------------------------------------------------

_BASE_FORBIDDEN_USE: Final[tuple[str, ...]] = (
    "diagnostics may not place trades",
    "diagnostics may not mutate live risk",
    "diagnostics may not allocate capital",
    "diagnostics may not write to live/** or paper/** or shadow/** paths",
    "diagnostics may not write to broker/** or agent/risk/** or agent/execution/** paths",
    "diagnostics may not mutate research/research_latest.json or research/strategy_matrix.csv",
    "diagnostics may not be used as a direct trade trigger",
    "diagnostics may not bypass policy governance",
    "diagnostics may not bypass promotion gates",
    "diagnostics may not produce executable strategy code",
)


def _merge_forbidden_use(extra: tuple[str, ...]) -> list[str]:
    return _bounded_str_tuple(
        tuple(_BASE_FORBIDDEN_USE) + extra,
        MAX_FORBIDDEN_USE_ITEMS,
        MAX_LIST_ITEM_LEN,
    )


# ---------------------------------------------------------------------------
# Hand-encoded signal seed
# ---------------------------------------------------------------------------
#
# Closed Roadmap v6 + Addendum 1 family coverage. Each entry is a
# bounded-scalar declaration; this unit ships schema only.

_SIGNALS_SEED: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "rs_entropy_information_density",
        "family": "entropy",
        "name": "Entropy / information-density routing signal",
        "description": (
            "Shannon and approximate entropy of returns / signals as a "
            "routing input. High entropy deprioritizes directional "
            "campaigns; low entropy may prioritize trend / continuation "
            "exploration."
        ),
        "source": "research/diagnostics/entropy.py",
        "target_layer": "campaign",
        "direction": "deprioritize",
        "expected_information_gain_effect": (
            "high entropy reduces expected information gain on directional "
            "exploration"
        ),
        "dead_zone_risk_effect": "raises dead-zone risk in high-entropy regimes",
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "high entropy raises confirmation requirement for directional "
            "campaigns"
        ),
        "allowed_use": (
            "advisory routing input",
            "suppress directional campaigns in high-entropy regimes",
            "prioritize continuation campaigns in low-entropy regimes",
        ),
        "extra_forbidden_use": (
            "may not directly mute or unmute live execution",
        ),
        "required_inputs": (
            "return-series source",
            "regime-window length",
        ),
        "missing_input_behavior": (
            "if any required input is missing, signal status falls "
            "to suppressed and contributes neutral effect"
        ),
    },
    {
        "id": "rs_tail_power_law",
        "family": "tail",
        "name": "Tail / power-law routing signal",
        "description": (
            "Return / drawdown tail exponent, left-tail fragility, and "
            "tail asymmetry as routing inputs. Left-tail-fragile units "
            "are deprioritized or require stronger confirmation."
        ),
        "source": "research/diagnostics/tail.py",
        "target_layer": "evidence",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "tail-convex hypotheses gain priority when tail-fit quality is high"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk for strategies dependent on a single "
            "outlier"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "left-tail fragility raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory evidence-layer input",
            "raise confirmation requirement for left-tail-fragile candidates",
        ),
        "extra_forbidden_use": (
            "may not directly promote a candidate based on tail evidence "
            "alone",
        ),
        "required_inputs": (
            "return-series source",
            "drawdown-series source",
        ),
        "missing_input_behavior": (
            "if tail-fit quality cannot be computed, signal status falls "
            "to suppressed"
        ),
    },
    {
        "id": "rs_criticality_phase_transition",
        "family": "criticality",
        "name": "Criticality / phase-transition routing signal",
        "description": (
            "Autocorrelation drift, variance increase, and regime-switch "
            "warnings as routing inputs. Unstable regimes deprioritize "
            "fragile campaigns."
        ),
        "source": "research/diagnostics/criticality.py",
        "target_layer": "policy",
        "direction": "deprioritize",
        "expected_information_gain_effect": (
            "criticality regions raise expected information gain for "
            "regime-switch hypotheses"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk near unstable phase transitions"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "criticality warnings raise confirmation requirement"
        ),
        "allowed_use": (
            "advisory policy-layer input",
            "pause or suppress fragile campaigns near instability",
            "require regime segmentation for unstable candidates",
        ),
        "extra_forbidden_use": (
            "may not predict crashes as deterministic events",
        ),
        "required_inputs": (
            "volatility-series source",
            "regime-window length",
        ),
        "missing_input_behavior": (
            "if criticality cannot be computed, signal status falls to "
            "suppressed"
        ),
    },
    {
        "id": "rs_network_correlation_graph",
        "family": "network",
        "name": "Network / correlation-graph routing signal",
        "description": (
            "Correlation networks, MST concentration, contagion, and "
            "diversification breakdown as routing inputs. High "
            "concentration suppresses overlapping campaigns."
        ),
        "source": "research/diagnostics/network.py",
        "target_layer": "campaign",
        "direction": "suppress",
        "expected_information_gain_effect": (
            "high network concentration lowers expected information gain "
            "for redundant exploration"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk for portfolio-overlapping campaigns"
        ),
        "orthogonality_effect": "primary",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": "neutral",
        "allowed_use": (
            "advisory campaign-layer input",
            "suppress portfolio-overlapping campaigns",
            "support cross-asset behaviour hypotheses",
        ),
        "extra_forbidden_use": (
            "may not migrate capital across assets",
        ),
        "required_inputs": (
            "cross-asset return matrix",
            "correlation-window length",
        ),
        "missing_input_behavior": (
            "if the correlation matrix cannot be built, signal status "
            "falls to suppressed"
        ),
    },
    {
        "id": "rs_quorum_independent_evidence",
        "family": "quorum",
        "name": "Independent-evidence quorum routing signal",
        "description": (
            "Independent confirmations, confirmation diversity, and "
            "single-source dependency flags as routing inputs. "
            "Insufficient quorum keeps a hypothesis as a seed, never "
            "escalating to candidate."
        ),
        "source": "research/diagnostics/quorum.py",
        "target_layer": "evidence",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "quorum confirmation raises expected information gain on "
            "promotion"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk on single-source-dependent hypotheses"
        ),
        "orthogonality_effect": "primary",
        "public_data_quality_effect": "primary",
        "confirmation_requirement_effect": (
            "insufficient quorum keeps a hypothesis seed-only"
        ),
        "allowed_use": (
            "advisory evidence-layer input",
            "promotion / evidence guardrail",
            "block single-diagnostic false positives",
        ),
        "extra_forbidden_use": (
            "may not function as a live ensemble vote",
            "may not allocate capital across confirmations",
        ),
        "required_inputs": (
            "per-asset confirmation tally",
            "per-timeframe confirmation tally",
        ),
        "missing_input_behavior": (
            "if no confirmation tally is available, signal status falls "
            "to suppressed"
        ),
    },
    {
        "id": "rs_external_intelligence_routing",
        "family": "external_intelligence",
        "name": "External-intelligence routing signal",
        "description": (
            "Public / free data manifest quality, freshness, and "
            "license metadata as routing inputs. Failed quality gates "
            "suppress promotion from a public-data-seeded hypothesis."
        ),
        "source": "research/external_intelligence/source_registry.py",
        "target_layer": "campaign",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "high public-data quality raises expected information gain "
            "on seed promotion"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk on stale or single-source seeds"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "primary",
        "confirmation_requirement_effect": (
            "failed quality gates block promotion from a public-data "
            "seed"
        ),
        "allowed_use": (
            "advisory campaign-layer input",
            "block promotion when license / freshness / source-agreement "
            "gates fail",
            "support public-data-seeded hypothesis discovery",
        ),
        "extra_forbidden_use": (
            "may not treat external data as alpha",
            "may not call paid feeds or vendor-alpha endpoints",
        ),
        "required_inputs": (
            "public-source manifest",
            "public-data quality-gate verdict",
        ),
        "missing_input_behavior": (
            "if the manifest or quality-gate verdict is missing, signal "
            "status falls to suppressed and external seeds are blocked"
        ),
    },
    {
        "id": "rs_dead_zone_suppression",
        "family": "dead_zone",
        "name": "Dead-zone-aware suppression routing signal",
        "description": (
            "Aggregated dead-zone risk from upstream diagnostic "
            "failures as a routing-suppression input. High dead-zone "
            "risk suppresses further exploration in the same regime."
        ),
        "source": "research/diagnostics/null_models.py",
        "target_layer": "campaign",
        "direction": "suppress",
        "expected_information_gain_effect": (
            "high dead-zone risk lowers expected information gain"
        ),
        "dead_zone_risk_effect": (
            "primary — directly drives dead-zone suppression"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "high dead-zone risk raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory campaign-layer suppression input",
            "deprioritize known dead-zone regimes",
        ),
        "extra_forbidden_use": (
            "may not retire a candidate without policy approval",
        ),
        "required_inputs": (
            "null-model verdict",
            "regime-window length",
        ),
        "missing_input_behavior": (
            "if null-model verdict is missing, signal status falls to "
            "suppressed"
        ),
    },
    {
        "id": "rs_null_model_falsification",
        "family": "null_model",
        "name": "Null-model / Brownian-baseline routing signal",
        "description": (
            "Random-walk / shuffled-return / surrogate-data baselines "
            "as falsification routing inputs. Failure to beat a null "
            "model demotes the hypothesis family."
        ),
        "source": "research/diagnostics/null_models.py",
        "target_layer": "evidence",
        "direction": "deprioritize",
        "expected_information_gain_effect": (
            "failure to beat a null model lowers expected information "
            "gain"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk on null-model failures"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "null-model failure raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory evidence-layer input",
            "reject hypotheses that do not beat simple null models",
            "baseline for entropy / tail / phase diagnostics",
        ),
        "extra_forbidden_use": (),
        "required_inputs": (
            "shuffled-return baseline",
            "surrogate-data baseline",
        ),
        "missing_input_behavior": (
            "if any null model is missing, signal status falls to "
            "suppressed and falsification cannot fire"
        ),
    },
    {
        "id": "rs_barrier_breakout_pressure",
        "family": "barrier",
        "name": "Barrier / breakout-pressure routing signal",
        "description": (
            "Probabilistic barrier crossing, range-escape probability, "
            "and post-breakout decay as routing inputs. False-breakout "
            "regions raise confirmation requirements."
        ),
        "source": "research/diagnostics/barrier.py",
        "target_layer": "strategy_mapping",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "high barrier pressure raises expected information gain on "
            "breakout hypotheses"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk in high false-breakout regimes"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "high false-breakout rate raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory strategy-mapping input",
            "seed probabilistic breakout hypotheses",
        ),
        "extra_forbidden_use": (
            "may not create deterministic support / resistance rules",
        ),
        "required_inputs": (
            "OHLC source",
            "barrier-zone definition",
        ),
        "missing_input_behavior": (
            "if OHLC or barrier-zone source is missing, signal status "
            "falls to suppressed"
        ),
    },
    {
        "id": "rs_resonance_cycle_confluence",
        "family": "resonance",
        "name": "Resonance / cycle-confluence routing signal",
        "description": (
            "Dominant-cycle period, cycle-stability, and resonance "
            "confluence as routing inputs. Cycle fits without null-model "
            "validation are demoted."
        ),
        "source": "research/diagnostics/resonance.py",
        "target_layer": "preset",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "strong resonance raises expected information gain on "
            "cycle-confluence hypotheses"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk on unstable cycle fits"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "cycle fit without null-model validation raises confirmation "
            "requirement"
        ),
        "allowed_use": (
            "advisory preset-layer input",
            "adapt candidate preset windows to cycle regimes",
            "prioritize hypotheses where short / long cycles align",
        ),
        "extra_forbidden_use": (
            "may not assume cycle equals alpha",
        ),
        "required_inputs": (
            "price-series source",
            "cycle-window length",
        ),
        "missing_input_behavior": (
            "if cycle window cannot be computed, signal status falls to "
            "suppressed"
        ),
    },
    {
        "id": "rs_adversarial_market_behavior",
        "family": "adversarial",
        "name": "Adversarial-market-behavior routing signal",
        "description": (
            "Crowding, adverse selection, fake-breakout rate, and "
            "post-signal decay as routing inputs. Predatory regimes "
            "raise confirmation requirements."
        ),
        "source": "research/diagnostics/adversarial.py",
        "target_layer": "evidence",
        "direction": "require_confirmation",
        "expected_information_gain_effect": (
            "adversarial regimes lower expected information gain on "
            "fragile breakout hypotheses"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk in predatory regimes"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "adversarial regime raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory evidence-layer input",
            "route to liquidity-aware behaviour families",
            "evaluate signal decay in shadow",
        ),
        "extra_forbidden_use": (
            "may not randomize preset selection",
            "may not mix live strategies stochastically",
        ),
        "required_inputs": (
            "post-signal decay series",
            "fake-breakout statistic",
        ),
        "missing_input_behavior": (
            "if adversarial statistics are missing, signal status falls "
            "to suppressed"
        ),
    },
    {
        "id": "rs_seismic_shock_aftershock",
        "family": "seismic",
        "name": "Seismic shock / aftershock routing signal",
        "description": (
            "Mainshock detection, aftershock decay rate, and "
            "post-shock directional bias as routing inputs. Active "
            "aftershock regimes cool down new campaigns."
        ),
        "source": "research/diagnostics/seismic.py",
        "target_layer": "campaign",
        "direction": "suppress",
        "expected_information_gain_effect": (
            "active aftershock regimes lower expected information gain "
            "on new campaigns"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk in unstable aftershock regimes"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "active shock regime raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory campaign-layer cooldown input",
            "generate post-shock continuation / reversal hypotheses",
            "test volatility decay profiles",
        ),
        "extra_forbidden_use": (
            "may not predict crashes as deterministic events",
        ),
        "required_inputs": (
            "shock-detection statistic",
            "aftershock-decay statistic",
        ),
        "missing_input_behavior": (
            "if shock-detection statistic is missing, signal status falls "
            "to suppressed"
        ),
    },
    {
        "id": "rs_turbulence_liquidity",
        "family": "turbulence",
        "name": "Liquidity-turbulence routing signal",
        "description": (
            "Liquidity turbulence score, slippage-convexity proxy, and "
            "flow-break risk as routing inputs. Turbulent regimes defer "
            "execution-sensitive mappings."
        ),
        "source": "research/diagnostics/turbulence.py",
        "target_layer": "policy",
        "direction": "deprioritize",
        "expected_information_gain_effect": (
            "turbulent regimes lower expected information gain on "
            "execution-sensitive mappings"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk in turbulent regimes"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "turbulent regime raises confirmation requirement"
        ),
        "allowed_use": (
            "advisory policy-layer input",
            "defer execution-sensitive mappings to shadow / paper "
            "validation in their future approved phases",
        ),
        "extra_forbidden_use": (
            "may not adjust order size or order routing",
            "may not enable execution-layer behaviour outside an "
            "approved phase",
        ),
        "required_inputs": (
            "volume-imbalance series",
            "realized-volatility burst statistic",
        ),
        "missing_input_behavior": (
            "if turbulence statistics are missing, signal status falls "
            "to suppressed"
        ),
    },
    {
        "id": "rs_market_language_grammar",
        "family": "market_language",
        "name": "Market-language / grammar-shift routing signal",
        "description": (
            "Tokenized return / volatility / volume states, Zipf slope, "
            "and grammar-shift score as routing inputs. Must be "
            "null-model tested before any promotion."
        ),
        "source": "research/diagnostics/language.py",
        "target_layer": "hypothesis_discovery",
        "direction": "neutral",
        "expected_information_gain_effect": (
            "grammar shifts may raise expected information gain on "
            "symbolic-behaviour hypotheses"
        ),
        "dead_zone_risk_effect": (
            "raises dead-zone risk on rare-pattern-as-alpha assumptions"
        ),
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": (
            "raises confirmation requirement when null-model not "
            "tested"
        ),
        "allowed_use": (
            "advisory hypothesis-discovery input",
            "seed hypotheses about compression -> expansion sequences",
            "explain market behaviour in observable token language",
        ),
        "extra_forbidden_use": (
            "may not mine candle patterns",
            "may not assume rare patterns equal alpha",
            "may not enable NLP-heavy social pipelines before quality "
            "gates exist",
        ),
        "required_inputs": (
            "tokenized state-sequence source",
            "null-model token baseline",
        ),
        "missing_input_behavior": (
            "if the null-model baseline is missing, signal status falls "
            "to suppressed"
        ),
    },
)


# ---------------------------------------------------------------------------
# Signal normalisation
# ---------------------------------------------------------------------------


def _normalise_signal(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _bounded_str(raw["id"], 96),
        "family": raw["family"],
        "name": _bounded_str(raw["name"], MAX_NAME_LEN),
        "description": _bounded_str(raw["description"], MAX_DESCRIPTION_LEN),
        "source": raw["source"],
        "target_layer": raw["target_layer"],
        "direction": raw["direction"],
        # Every signal in this unit ships at status="schema_only". A
        # later approved unit may lift specific signals to
        # advisory_planned / advisory_active.
        "status": "schema_only",
        "expected_information_gain_effect": _bounded_str(
            raw["expected_information_gain_effect"], MAX_EFFECT_LEN
        ),
        "dead_zone_risk_effect": _bounded_str(
            raw["dead_zone_risk_effect"], MAX_EFFECT_LEN
        ),
        "orthogonality_effect": _bounded_str(
            raw["orthogonality_effect"], MAX_EFFECT_LEN
        ),
        "public_data_quality_effect": _bounded_str(
            raw["public_data_quality_effect"], MAX_EFFECT_LEN
        ),
        "confirmation_requirement_effect": _bounded_str(
            raw["confirmation_requirement_effect"], MAX_EFFECT_LEN
        ),
        "allowed_use": _bounded_str_tuple(
            raw["allowed_use"], MAX_ALLOWED_USE_ITEMS, MAX_LIST_ITEM_LEN
        ),
        "forbidden_use": _merge_forbidden_use(raw.get("extra_forbidden_use", ())),
        "required_inputs": _bounded_str_tuple(
            raw["required_inputs"], MAX_REQUIRED_INPUTS, MAX_LIST_ITEM_LEN
        ),
        "missing_input_behavior": _bounded_str(
            raw["missing_input_behavior"], MAX_MISSING_INPUT_BEHAVIOR_LEN
        ),
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic routing-signals projection."""
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    signals = [_normalise_signal(s) for s in _SIGNALS_SEED]
    signals.sort(key=lambda s: (s["family"], s["id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "vocabularies": {
            "routing_signal_family": list(ROUTING_SIGNAL_FAMILY),
            "routing_signal_status": list(ROUTING_SIGNAL_STATUS),
            "routing_signal_direction": list(ROUTING_SIGNAL_DIRECTION),
            "routing_signal_source": list(ROUTING_SIGNAL_SOURCE),
            "routing_signal_target_layer": list(ROUTING_SIGNAL_TARGET_LAYER),
        },
        "signals": signals,
        "projection_invariants": dict(_BASE_PROJECTION_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as sorted-key indented JSON.
    Refuses any path outside
    ``logs/intelligent_routing_diagnostic_signals/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "intelligent_routing_diagnostic_signals._atomic_write_json "
            f"refuses non-signals-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".intelligent_routing_diagnostic_signals.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(snapshot: dict[str, Any]) -> str:
    signals = snapshot["signals"]
    inv = snapshot["projection_invariants"]
    by_family: dict[str, int] = {f: 0 for f in ROUTING_SIGNAL_FAMILY}
    for s in signals:
        if s["family"] in by_family:
            by_family[s["family"]] += 1
    lines = [
        f"intelligent_routing_diagnostic_signals {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"signals={len(signals)}",
        (
            "step5_implementation_allowed="
            f"{snapshot['step5_implementation_allowed']} "
            f"step5_enabled_substage={snapshot['step5_enabled_substage']}"
        ),
        (
            "diagnostics_do_not_trade="
            f"{inv['diagnostics_do_not_trade']} "
            "external_data_is_not_alpha="
            f"{inv['external_data_is_not_alpha']}"
        ),
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_runtime={inv['no_step5_runtime']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "no_campaign_queue_mutation="
            f"{inv['no_campaign_queue_mutation']} "
            "no_strategy_generation="
            f"{inv['no_strategy_generation']} "
            "no_routing_mutation="
            f"{inv['no_routing_mutation']}"
        ),
        f"by_family={dict(sorted(by_family.items()))}",
    ]
    for s in signals:
        lines.append(
            f"  signal {s['id']} family={s['family']} "
            f"target_layer={s['target_layer']} "
            f"direction={s['direction']} status={s['status']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.intelligent_routing_diagnostic_signals",
        description=(
            "v3.15.16 Intelligent Routing Layer — diagnostic-aware "
            "routing signals schema and read-only projector. Schema "
            "and projector only; no routing mutation, no campaign "
            "queue mutation, no strategy generation, no trading "
            "behaviour. Step 5 implementation remains BLOCKED."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/intelligent_routing_diagnostic_signals/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to stdout "
            "and exit. Does not write any artefact."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snap = collect_snapshot()
    if args.status:
        sys.stdout.write(_render_status(snap))
        return 0
    indent = args.indent if args.indent and args.indent > 0 else None
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
