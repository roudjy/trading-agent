"""QRE research ontology scaffold.

This module defines deterministic, closed-vocabulary ontology helpers for
research-memory classification. It is intentionally non-authoritative:
ontology labels provide context and filtering hints, not alpha confidence,
promotion authority, strategy registration, or execution permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SCHEMA_VERSION = "1.0"


ONTOLOGY_TAGS: tuple[str, ...] = (
    "artifact",
    "basket",
    "campaign",
    "candidate",
    "data_readiness",
    "diagnostic",
    "entity_resolution",
    "evidence",
    "factor",
    "failure",
    "field_coverage",
    "hypothesis",
    "hypothesis_seed",
    "identity",
    "lineage",
    "manifest",
    "null_model",
    "operator_trust",
    "policy",
    "policy_action",
    "provider",
    "readiness",
    "recipe",
    "retrieval",
    "routing",
    "sampling",
    "source_identity",
    "source_quality",
    "state_transition",
    "strategy_context",
    "universe",
)


ASSET_CLASSES: tuple[str, ...] = (
    "equity",
    "fundamental_equity",
    "index",
    "fx",
    "commodity",
    "rate",
    "crypto_legacy",
    "unknown",
)


RESEARCH_SCOPES: tuple[str, ...] = (
    "target_equity_research",
    "target_source_data_research",
    "target_factor_research",
    "legacy_non_target_reference",
    "excluded_from_current_research_scope",
    "unknown",
)


READINESS_STATES: tuple[str, ...] = (
    "ready",
    "partial",
    "not_ready",
    "blocked",
    "unknown",
    "fail_closed",
)


BLOCKER_CLASSES: tuple[str, ...] = (
    "missing_source_manifest",
    "missing_required_field",
    "source_license_unknown",
    "source_quality_unknown",
    "missing_point_in_time_policy",
    "missing_report_lag_policy",
    "missing_restatement_policy",
    "blocked_data_readiness",
    "blocked_field_coverage",
    "blocked_identity_ambiguity",
    "lineage_missing",
    "metric_inconsistent",
    "no_survivors",
    "criteria_failed",
    "unknown",
)


CRYPTO_MARKERS: tuple[str, ...] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "ADA-USD",
    "DOGE-USD",
    "XRP-USD",
    "BNB-USD",
    "AVAX-USD",
    "MATIC-USD",
    "DOT-USD",
)


EQUITY_CONTEXT_MARKERS: tuple[str, ...] = (
    "equity",
    "equities",
    "factor",
    "fundamental",
    "provider",
    "source_manifest",
    "companyfacts",
    "openfigi",
    "euronext",
    "nasdaq",
    "nyse",
    "universe",
)


@dataclass(frozen=True)
class OntologyClassification:
    """Deterministic ontology classification for a memory/document item."""

    ontology_tags: tuple[str, ...]
    asset_class: str
    research_scope: str
    readiness_state: str
    blocker_classes: tuple[str, ...]
    explanation: str


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    upper_text = text.upper()
    return any(marker.upper() in upper_text for marker in markers)


def _normalize_tags(tags: Iterable[str] | None) -> tuple[str, ...]:
    if not tags:
        return tuple()

    allowed = set(ONTOLOGY_TAGS)
    return tuple(sorted({tag for tag in tags if tag in allowed}))


def classify_research_text(
    *,
    title: str = "",
    artifact_path: str = "",
    ontology_tags: Iterable[str] | None = None,
    text_preview: str = "",
) -> OntologyClassification:
    """Classify research-memory text into ontology context.

    Crypto-related legacy records are not deleted and not hidden. They are
    explicitly classified as crypto_legacy and excluded from the current
    equity/fundamental research scope.

    This is a research-context classifier only. It never authorizes strategy
    promotion, paper/shadow/live activation, or execution.
    """

    combined = " ".join(part for part in (title, artifact_path, text_preview) if part)
    normalized_tags = _normalize_tags(ontology_tags)

    blocker_classes: list[str] = []
    readiness_state = "unknown"

    if _contains_any(combined, CRYPTO_MARKERS):
        return OntologyClassification(
            ontology_tags=tuple(sorted(set(normalized_tags + ("strategy_context",)))),
            asset_class="crypto_legacy",
            research_scope="excluded_from_current_research_scope",
            readiness_state="blocked",
            blocker_classes=("blocked_data_readiness",),
            explanation=(
                "Crypto appears only as legacy/historical research context and "
                "is excluded from the current equity/fundamental research scope."
            ),
        )

    if _contains_any(combined, EQUITY_CONTEXT_MARKERS):
        scope = "target_equity_research"
        asset_class = "fundamental_equity"
        explanation = "Record is aligned with the current equity/fundamental research scope."
    else:
        scope = "unknown"
        asset_class = "unknown"
        explanation = "Record could not be mapped to a current target research scope."

    lower_combined = combined.lower()
    if "missing" in lower_combined or "blocked" in lower_combined:
        readiness_state = "blocked"
    elif "ready" in lower_combined:
        readiness_state = "ready"

    for blocker in BLOCKER_CLASSES:
        if blocker != "unknown" and blocker in lower_combined:
            blocker_classes.append(blocker)

    if not blocker_classes and readiness_state == "blocked":
        blocker_classes.append("unknown")

    return OntologyClassification(
        ontology_tags=normalized_tags,
        asset_class=asset_class,
        research_scope=scope,
        readiness_state=readiness_state,
        blocker_classes=tuple(sorted(set(blocker_classes))),
        explanation=explanation,
    )


def ontology_manifest() -> dict[str, object]:
    """Return deterministic ontology manifest."""

    return {
        "schema_version": SCHEMA_VERSION,
        "ontology_tags": list(ONTOLOGY_TAGS),
        "asset_classes": list(ASSET_CLASSES),
        "research_scopes": list(RESEARCH_SCOPES),
        "readiness_states": list(READINESS_STATES),
        "blocker_classes": list(BLOCKER_CLASSES),
        "crypto_policy": {
            "classification": "crypto_legacy",
            "research_scope": "excluded_from_current_research_scope",
            "behavior": "preserve_historical_records_but_do_not_target_for_current_equity_research",
            "does_not_delete_frozen_contracts": True,
            "does_not_authorize_trading": True,
        },
        "authority": {
            "ontology_is_context_only": True,
            "not_alpha_authority": True,
            "not_strategy_registration": True,
            "not_candidate_promotion": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
        },
    }
