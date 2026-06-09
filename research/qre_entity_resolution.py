"""Deterministic QRE entity resolution scaffold.

This module provides lightweight, fail-closed entity classification for research
memory entries. It does not establish truth authority, does not override source
identity gates, and does not authorize candidate promotion or execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


SCHEMA_VERSION = "1.0"


ENTITY_TYPES: tuple[str, ...] = (
    "asset",
    "provider",
    "source",
    "factor",
    "recipe",
    "universe",
    "basket",
    "campaign",
    "candidate",
    "hypothesis",
    "artifact",
    "policy",
    "diagnostic",
    "unknown",
)


CRYPTO_SYMBOLS: tuple[str, ...] = (
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


PROVIDER_MARKERS: dict[str, str] = {
    "sec_companyfacts": "provider:sec_companyfacts",
    "companyfacts": "provider:sec_companyfacts",
    "openfigi": "provider:openfigi_symbology",
    "euronext": "provider:euronext_issuer_metadata",
    "nasdaq": "provider:nasdaq_listings_metadata",
    "nyse": "provider:nyse_listings_metadata",
    "yfinance": "provider:yfinance_context",
    "yahoo": "provider:yfinance_context",
}


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    entity_type: str
    label: str
    confidence: str
    ambiguity_status: str
    evidence: tuple[str, ...]


def _combined_text(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _add_unique(entities: list[ResolvedEntity], entity: ResolvedEntity) -> None:
    existing_ids = {item.entity_id for item in entities}
    if entity.entity_id not in existing_ids:
        entities.append(entity)


def resolve_entities_from_text(
    *,
    title: str = "",
    artifact_path: str = "",
    text_preview: str = "",
    ontology_tags: Iterable[str] | None = None,
) -> tuple[ResolvedEntity, ...]:
    """Resolve deterministic entities from research-memory text.

    Resolution is intentionally conservative. Ambiguity remains visible and no
    resolved entity becomes source-of-truth authority.
    """

    text = _combined_text(title, artifact_path, text_preview)
    lower_text = text.lower()
    entities: list[ResolvedEntity] = []

    for symbol in CRYPTO_SYMBOLS:
        if symbol.lower() in lower_text:
            _add_unique(
                entities,
                ResolvedEntity(
                    entity_id=f"asset:{symbol}",
                    entity_type="asset",
                    label=symbol,
                    confidence="HIGH",
                    ambiguity_status="resolved",
                    evidence=(f"matched_symbol:{symbol}",),
                ),
            )

    for marker, entity_id in PROVIDER_MARKERS.items():
        if marker in lower_text:
            _add_unique(
                entities,
                ResolvedEntity(
                    entity_id=entity_id,
                    entity_type="provider",
                    label=entity_id.split(":", 1)[1],
                    confidence="MEDIUM",
                    ambiguity_status="resolved",
                    evidence=(f"matched_marker:{marker}",),
                ),
            )

    artifact_match = re.search(
        r"(research/[^\s]+|artifacts/[^\s]+|logs/[^\s]+|docs/[^\s]+)",
        text,
    )
    if artifact_match:
        artifact_path_match = artifact_match.group(1).rstrip(".,)")
        _add_unique(
            entities,
            ResolvedEntity(
                entity_id=f"artifact:{artifact_path_match}",
                entity_type="artifact",
                label=artifact_path_match,
                confidence="HIGH",
                ambiguity_status="resolved",
                evidence=(f"matched_artifact_path:{artifact_path_match}",),
            ),
        )

    if ontology_tags:
        for tag in sorted(set(ontology_tags)):
            if tag in {"policy", "policy_action"}:
                _add_unique(
                    entities,
                    ResolvedEntity(
                        entity_id=f"policy:{tag}",
                        entity_type="policy",
                        label=tag,
                        confidence="LOW",
                        ambiguity_status="unresolved",
                        evidence=(f"ontology_tag:{tag}",),
                    ),
                )

    return tuple(entities)


def entity_resolution_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "entity_types": list(ENTITY_TYPES),
        "authority": {
            "entity_resolution_is_context_only": True,
            "not_source_identity_authority": True,
            "does_not_override_identity_gates": True,
            "not_candidate_promotion": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
        },
    }