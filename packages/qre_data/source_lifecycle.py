"""Deterministic read-only source lifecycle and transition gates."""

from __future__ import annotations

from typing import Any, Final, Mapping


SCHEMA_VERSION: Final[str] = "1.0"
LIFECYCLE_STATES: Final[tuple[str, ...]] = (
    "candidate",
    "manual_research_only",
    "staging",
    "quality_gated",
    "active_read_only",
    "deprecated",
    "blocked",
)

ACTIVE_READ_ONLY_GATE_NAMES: Final[tuple[str, ...]] = (
    "manifest_completeness",
    "allowed_use_declared",
    "forbidden_use_declared",
    "quality_gates_declared",
    "quality_gates_passed",
    "identity_mapping_present",
    "historical_lineage_present",
)

_UNKNOWN_TEXT: Final[frozenset[str]] = frozenset({"", "unknown", "none", "null", "nan"})
_IDENTITY_MARKERS: Final[tuple[str, ...]] = (
    "identity_mapping",
    "issuer_to_symbol_mapping",
    "symbol_mapping",
    "alias_resolution",
    "figi",
    "isin",
    "ticker",
)
_STATIC_REPRO_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "",
        "unknown",
        "static_registry_stub_only",
        "manual_only",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _known_text(value: Any) -> bool:
    return _text(value).lower() not in _UNKNOWN_TEXT


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _manifest_completeness(manifest: Mapping[str, Any]) -> bool:
    return (
        _text(manifest.get("manifest_status")) == "VALID"
        and _known_text(manifest.get("source_id"))
        and _known_text(manifest.get("provider_id"))
        and _known_text(manifest.get("license_terms_reference"))
        and _known_text(manifest.get("schema_version"))
        and bool(_string_list(manifest.get("required_quality_gates")))
        and bool(_string_list(manifest.get("activation_requirements")))
        and len(_string_list(manifest.get("manifest_block_reasons"))) == 0
    )


def _identity_mapping_present(manifest: Mapping[str, Any]) -> bool:
    texts = (
        _string_list(manifest.get("allowed_use"))
        + _string_list(manifest.get("required_quality_gates"))
        + _string_list(manifest.get("activation_requirements"))
        + _string_list(manifest.get("factor_field_coverage_claims"))
    )
    lowered = " ".join(item.lower() for item in texts)
    return any(marker in lowered for marker in _IDENTITY_MARKERS)


def _historical_lineage_present(manifest: Mapping[str, Any]) -> bool:
    method = _text(manifest.get("reproducibility_method")).lower()
    return method not in _STATIC_REPRO_MARKERS


def _required_forbidden_use_present(
    manifest: Mapping[str, Any],
    *,
    required_forbidden_use: tuple[str, ...],
) -> bool:
    forbidden = set(_string_list(manifest.get("forbidden_use")))
    return set(required_forbidden_use).issubset(forbidden)


def evaluate_source_lifecycle(
    manifest: Mapping[str, Any],
    *,
    required_forbidden_use: tuple[str, ...],
    source_quality_ready: bool,
    license_allows_quality_gate: bool,
    license_allows_active_read_only: bool,
) -> dict[str, Any]:
    """Evaluate deterministic lifecycle gates for one source manifest row."""

    current_state = _text(manifest.get("source_status")) or "unknown"
    if current_state not in LIFECYCLE_STATES:
        current_state = "blocked"

    gate_statuses = {
        "manifest_completeness": _manifest_completeness(manifest),
        "allowed_use_declared": bool(_string_list(manifest.get("allowed_use"))),
        "forbidden_use_declared": _required_forbidden_use_present(
            manifest,
            required_forbidden_use=required_forbidden_use,
        ),
        "quality_gates_declared": bool(_string_list(manifest.get("required_quality_gates"))),
        "quality_gates_passed": bool(source_quality_ready and license_allows_quality_gate),
        "identity_mapping_present": _identity_mapping_present(manifest),
        "historical_lineage_present": _historical_lineage_present(manifest),
    }

    blocked_gate_reasons = [
        gate_name for gate_name in ACTIVE_READ_ONLY_GATE_NAMES if not gate_statuses[gate_name]
    ]

    quality_gated_allowed = (
        current_state in {"candidate", "manual_research_only", "staging", "quality_gated", "active_read_only"}
        and gate_statuses["manifest_completeness"]
        and gate_statuses["allowed_use_declared"]
        and gate_statuses["forbidden_use_declared"]
        and gate_statuses["quality_gates_declared"]
        and license_allows_quality_gate
    )

    active_read_only_allowed = (
        current_state in {"quality_gated", "active_read_only"}
        and not blocked_gate_reasons
        and license_allows_active_read_only
    )

    transition_targets = {
        "quality_gated": {
            "allowed": bool(quality_gated_allowed),
            "blocking_reasons": [] if quality_gated_allowed else sorted(
                {
                    *(
                        reason
                        for reason in (
                            "manifest_completeness",
                            "allowed_use_declared",
                            "forbidden_use_declared",
                            "quality_gates_declared",
                        )
                        if not gate_statuses[reason]
                    ),
                    *([] if license_allows_quality_gate else ["license_allows_quality_gate"]),
                }
            ),
        },
        "active_read_only": {
            "allowed": bool(active_read_only_allowed),
            "blocking_reasons": [] if active_read_only_allowed else sorted(
                {
                    *blocked_gate_reasons,
                    *(
                        []
                        if current_state in {"quality_gated", "active_read_only"}
                        else ["transition_requires_quality_gated_state"]
                    ),
                    *([] if license_allows_active_read_only else ["license_allows_active_read_only"]),
                }
            ),
        },
    }

    lifecycle_status = (
        "active_read_only_ready"
        if transition_targets["active_read_only"]["allowed"]
        else "quality_gated_ready"
        if transition_targets["quality_gated"]["allowed"]
        else "blocked"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": _text(manifest.get("source_id")),
        "provider_id": _text(manifest.get("provider_id")),
        "current_state": current_state,
        "lifecycle_status": lifecycle_status,
        "gate_statuses": gate_statuses,
        "transition_targets": transition_targets,
        "license_allows_quality_gate": bool(license_allows_quality_gate),
        "license_allows_active_read_only": bool(license_allows_active_read_only),
        "source_quality_ready": bool(source_quality_ready),
        "operator_explanation": (
            "Source lifecycle gates are satisfied for active_read_only."
            if transition_targets["active_read_only"]["allowed"]
            else "Source lifecycle remains fail-closed until manifest, quality, identity, "
            "and historical lineage gates are explicit."
        ),
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "promotes_candidates": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


__all__ = [
    "ACTIVE_READ_ONLY_GATE_NAMES",
    "LIFECYCLE_STATES",
    "SCHEMA_VERSION",
    "evaluate_source_lifecycle",
]
