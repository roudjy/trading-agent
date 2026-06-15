"""Deterministic read-only symbology resolver foundation."""

from __future__ import annotations

from typing import Any, Final, Mapping


SCHEMA_VERSION: Final[str] = "1.0"
RESOLUTION_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "VERIFIED",
    "AMBIGUOUS_BLOCKED",
    "MISSING_BLOCKED",
)
AMBIGUITY_REASON_VOCABULARY: Final[tuple[str, ...]] = (
    "multiple_candidate_aliases",
    "candidate_alias_requires_verification",
    "missing_primary_provider_symbol",
    "provider_symbol_unresolved",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def resolve_symbology_row(asset_row: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve canonical/provider symbol identity without granting authority."""

    canonical_id = _text(asset_row.get("canonical_instrument_id"))
    instrument_symbol = _text(asset_row.get("symbol"))
    provider_symbol = _text(asset_row.get("primary_data_provider_symbol"))
    aliases = _string_list(asset_row.get("provider_symbol_aliases"))
    provider_status = _text(asset_row.get("provider_symbol_status"))
    identity_status = _text(asset_row.get("source_identity_status"))

    blocking_reasons: list[str] = []
    if not provider_symbol:
        blocking_reasons.append("missing_primary_provider_symbol")
    if provider_status == "candidate_alias_requires_verification":
        blocking_reasons.append("candidate_alias_requires_verification")
        if len(aliases) > 1:
            blocking_reasons.append("multiple_candidate_aliases")
    elif provider_status not in {"verified", "provider_lookup_failed"}:
        blocking_reasons.append("provider_symbol_unresolved")
    if identity_status not in {"provider_symbol_verified"} and "candidate_alias_requires_verification" not in blocking_reasons:
        blocking_reasons.append("provider_symbol_unresolved")

    resolution_status = (
        "VERIFIED"
        if not blocking_reasons
        else "MISSING_BLOCKED"
        if "missing_primary_provider_symbol" in blocking_reasons
        else "AMBIGUOUS_BLOCKED"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "instrument_symbol": instrument_symbol,
        "canonical_instrument_id": canonical_id,
        "provider_symbol": provider_symbol or None,
        "provider_symbol_aliases": aliases,
        "provider_symbol_status": provider_status or "unknown",
        "source_identity_status": identity_status or "unknown",
        "resolution_status": resolution_status,
        "ambiguity_blocked": bool(blocking_reasons),
        "blocking_reasons": blocking_reasons,
        "operator_explanation": (
            "Canonical instrument ID and provider symbol are verified for read-only use."
            if not blocking_reasons
            else "Symbology resolution remains blocked until provider-symbol ambiguity is explicitly resolved."
        ),
        "safety_invariants": {
            "read_only": True,
            "identity_is_infrastructure_only": True,
            "not_alpha_authority": True,
            "candidate_promotion_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


__all__ = [
    "AMBIGUITY_REASON_VOCABULARY",
    "RESOLUTION_STATUS_VOCABULARY",
    "SCHEMA_VERSION",
    "resolve_symbology_row",
]
