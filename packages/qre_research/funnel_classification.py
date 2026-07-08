"""Canonical QRE funnel classification metadata.

This module quarantines duplicate funnel claims with declarative metadata. It
does not run research, create artifacts, launch campaigns, or grant execution
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Classification = Literal[
    "canonical_contract_loop",
    "provider_adapter",
    "observability_only",
    "legacy_protected",
    "fixture_only",
    "operator_decision_required",
]
Decision = Literal[
    "KEEP_AS_CANONICAL",
    "KEEP_AS_PROVIDER_ADAPTER",
    "OBSERVABILITY_ONLY",
    "KEEP_AS_LEGACY_OUTPUT_CONTRACT",
    "TEST_FIXTURE_ONLY",
    "BRIDGE_TO_CANONICAL",
    "UNKNOWN_REQUIRES_OPERATOR_DECISION",
]

SAFETY: Final[dict[str, bool]] = {
    "classification_only": True,
    "runtime_behavior_changed": False,
    "creates_candidates": False,
    "creates_strategies": False,
    "creates_presets": False,
    "creates_campaigns": False,
    "runs_screening": False,
    "runs_validation": False,
    "trading_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}


@dataclass(frozen=True, slots=True)
class FunnelClassification:
    funnel_id: str
    name: str
    classification: Classification
    decision: Decision
    canonical_claim_allowed: bool
    modules: tuple[str, ...]
    protected_outputs: tuple[str, ...]
    rationale: str
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "funnel_id": self.funnel_id,
            "name": self.name,
            "classification": self.classification,
            "decision": self.decision,
            "canonical_claim_allowed": self.canonical_claim_allowed,
            "modules": list(self.modules),
            "protected_outputs": list(self.protected_outputs),
            "rationale": self.rationale,
            "next_action": self.next_action,
        }


FUNNEL_CLASSIFICATIONS: Final[tuple[FunnelClassification, ...]] = (
    FunnelClassification(
        funnel_id="canonical_provider_agnostic_contract_bridge_loop",
        name="Canonical provider-agnostic contract/bridge/memory loop",
        classification="canonical_contract_loop",
        decision="KEEP_AS_CANONICAL",
        canonical_claim_allowed=True,
        modules=(
            "packages/qre_research/canonical_contracts.py",
            "packages/qre_research/tiingo_canonical_bridge.py",
            "packages/qre_research/candidate_planning_bridge.py",
            "packages/qre_research/evidence_memory_bridge.py",
            "packages/qre_research/memory_aware_hypothesis_generation.py",
        ),
        protected_outputs=(),
        rationale=(
            "PR A-E established canonical vocabulary and deterministic bridges "
            "through memory-aware next hypothesis ordering at the contract level."
        ),
        next_action="Use this contract path for future provider bridges; do not treat it as trading or validation authority.",
    ),
    FunnelClassification(
        funnel_id="tiingo_hypothesis_candidate_research_mini_loop",
        name="Tiingo hypothesis/candidate research mini-loop",
        classification="provider_adapter",
        decision="KEEP_AS_PROVIDER_ADAPTER",
        canonical_claim_allowed=False,
        modules=(
            "research/qre_tiingo_hypothesis_generator_e2e.py",
            "research/qre_tiingo_hypothesis_lifecycle.py",
            "research/qre_tiingo_candidate_research_loop.py",
            "packages/qre_research/tiingo_canonical_bridge.py",
        ),
        protected_outputs=(),
        rationale="Provider-specific research mini-loop remains valuable only through canonical bridge contracts.",
        next_action="Keep bridged to canonical Hypothesis, ResearchInputContract, CandidateSpec, Evidence, and Feedback contracts.",
    ),
    FunnelClassification(
        funnel_id="daily_status_digest_observability",
        name="Daily status digest / observability funnel",
        classification="observability_only",
        decision="OBSERVABILITY_ONLY",
        canonical_claim_allowed=False,
        modules=("research/qre_daily_status_digest.py",),
        protected_outputs=(),
        rationale="Digest consumes sidecars and summarizes status; it must not produce research objects.",
        next_action="Continue read-only status aggregation only.",
    ),
    FunnelClassification(
        funnel_id="run_research_registry_matrix",
        name="run_research / registry / strategy_matrix funnel",
        classification="legacy_protected",
        decision="KEEP_AS_LEGACY_OUTPUT_CONTRACT",
        canonical_claim_allowed=False,
        modules=("research/run_research.py", "registry.py", "agent/backtesting/strategies.py"),
        protected_outputs=("research/research_latest.json", "research/strategy_matrix.csv"),
        rationale="Legacy research outputs remain protected and are not mutated by canonical reconciliation work.",
        next_action="Keep protected until a separate operator-scoped settlement changes ownership.",
    ),
    FunnelClassification(
        funnel_id="alpha_discovery_strategy_ir_campaign_lesson",
        name="Alpha discovery / Strategy IR / campaign / lesson funnel",
        classification="operator_decision_required",
        decision="BRIDGE_TO_CANONICAL",
        canonical_claim_allowed=False,
        modules=("packages/qre_research/alpha_discovery",),
        protected_outputs=(),
        rationale="Older partial funnel semantics overlap canonical contracts but ownership is not fully settled.",
        next_action="Bridge or explicitly quarantine individual surfaces before treating them as canonical.",
    ),
    FunnelClassification(
        funnel_id="test_smoke_fixture_funnels",
        name="Legacy or smoke/test-only funnel patterns",
        classification="fixture_only",
        decision="TEST_FIXTURE_ONLY",
        canonical_claim_allowed=False,
        modules=("tests/",),
        protected_outputs=(),
        rationale="Fixture and smoke paths may mimic funnel semantics but cannot own production architecture.",
        next_action="Keep fixture-only assertions from becoming canonical claims.",
    ),
)


def classifications_as_dict() -> dict[str, dict[str, object]]:
    return {row.funnel_id: row.as_dict() for row in FUNNEL_CLASSIFICATIONS}


def classification_by_id(funnel_id: str) -> FunnelClassification:
    for row in FUNNEL_CLASSIFICATIONS:
        if row.funnel_id == funnel_id:
            return row
    raise KeyError(funnel_id)


def canonical_classifications() -> tuple[FunnelClassification, ...]:
    return tuple(row for row in FUNNEL_CLASSIFICATIONS if row.canonical_claim_allowed)


def validate_funnel_classifications() -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for row in FUNNEL_CLASSIFICATIONS:
        if row.funnel_id in seen:
            errors.append(f"duplicate_funnel_id:{row.funnel_id}")
        seen.add(row.funnel_id)
        if row.classification != "canonical_contract_loop" and row.canonical_claim_allowed:
            errors.append(f"noncanonical_claim_allowed:{row.funnel_id}")
        if row.classification == "observability_only" and row.canonical_claim_allowed:
            errors.append(f"observability_claims_canonical:{row.funnel_id}")
        if row.classification == "fixture_only" and row.canonical_claim_allowed:
            errors.append(f"fixture_claims_canonical:{row.funnel_id}")
    if len(canonical_classifications()) != 1:
        errors.append("expected_exactly_one_canonical_contract_loop")
    return errors


def classification_summary() -> dict[str, object]:
    counts: dict[str, int] = {}
    for row in FUNNEL_CLASSIFICATIONS:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    return {
        "classifications": counts,
        "canonical_contract_loop": canonical_classifications()[0].funnel_id if len(canonical_classifications()) == 1 else None,
        "duplicate_canonical_claims": len(canonical_classifications()) > 1,
        "safety": dict(SAFETY),
    }


__all__ = [
    "FUNNEL_CLASSIFICATIONS",
    "SAFETY",
    "FunnelClassification",
    "canonical_classifications",
    "classification_by_id",
    "classification_summary",
    "classifications_as_dict",
    "validate_funnel_classifications",
]
