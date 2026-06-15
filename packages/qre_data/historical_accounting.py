"""Deterministic read-only historical accounting snapshot contracts."""

from __future__ import annotations

from typing import Any, Final, Mapping


SCHEMA_VERSION: Final[str] = "1.0"
SNAPSHOT_GATE_NAMES: Final[tuple[str, ...]] = (
    "point_in_time_policy_declared",
    "report_lag_policy_supported",
    "restatement_policy_supported",
    "historical_lineage_reproducible",
    "no_lookahead_snapshot_contract",
)
SNAPSHOT_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "NOT_REQUIRED",
    "BLOCKED",
    "READY",
)
_UNKNOWN_TEXT: Final[frozenset[str]] = frozenset({"", "unknown", "none", "null", "nan"})
_FAIL_CLOSED_POLICY_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "FAIL_CLOSED",
        "POLICY_MISSING",
        "UNSUPPORTED",
        "UNKNOWN",
        "REQUIRED",
        "REVIEW_REQUIRED",
    }
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _supports_historical_accounting(manifest: Mapping[str, Any]) -> bool:
    source_type = _text(manifest.get("source_type"))
    return source_type in {"fundamental_statement_data", "fundamental_connector", "fundamentals"}


def _pit_policy_declared(manifest: Mapping[str, Any]) -> bool:
    activation_requirements = [item.lower() for item in _string_list(manifest.get("activation_requirements"))]
    required_quality_gates = [item.lower() for item in _string_list(manifest.get("required_quality_gates"))]
    return (
        "point_in_time_policy_defined" in activation_requirements
        or "point_in_time_policy_defined" in required_quality_gates
    )


def _lineage_reproducible(manifest: Mapping[str, Any]) -> bool:
    method = _text(manifest.get("reproducibility_method")).lower()
    return method not in _STATIC_REPRO_MARKERS


def _policy_gate(policy_row: Mapping[str, Any]) -> bool:
    status = _text(policy_row.get("policy_status")).upper()
    return status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}


def evaluate_historical_accounting_snapshot(
    manifest: Mapping[str, Any],
    *,
    report_lag_policy_row: Mapping[str, Any],
    restatement_policy_row: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate read-only PIT/report-lag/restatement snapshot readiness."""

    required = _supports_historical_accounting(manifest)
    gate_statuses = {
        "point_in_time_policy_declared": _pit_policy_declared(manifest),
        "report_lag_policy_supported": _policy_gate(report_lag_policy_row),
        "restatement_policy_supported": _policy_gate(restatement_policy_row),
        "historical_lineage_reproducible": _lineage_reproducible(manifest),
        "no_lookahead_snapshot_contract": False,
    }
    gate_statuses["no_lookahead_snapshot_contract"] = all(
        gate_statuses[name]
        for name in (
            "point_in_time_policy_declared",
            "report_lag_policy_supported",
            "restatement_policy_supported",
            "historical_lineage_reproducible",
        )
    )

    blocked_gates = [name for name in SNAPSHOT_GATE_NAMES if not gate_statuses[name]]
    snapshot_status = "NOT_REQUIRED"
    if required:
        snapshot_status = "READY" if not blocked_gates else "BLOCKED"

    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": _text(manifest.get("source_id")),
        "provider_id": _text(manifest.get("provider_id")),
        "source_type": _text(manifest.get("source_type")),
        "requires_historical_accounting": required,
        "report_lag_policy_status": _text(report_lag_policy_row.get("policy_status")).upper() or "UNKNOWN",
        "restatement_policy_status": _text(restatement_policy_row.get("policy_status")).upper() or "UNKNOWN",
        "report_lag_support_status": _text(report_lag_policy_row.get("support_status")).upper() or "UNKNOWN",
        "restatement_support_status": _text(restatement_policy_row.get("support_status")).upper() or "UNKNOWN",
        "point_in_time_policy_declared": gate_statuses["point_in_time_policy_declared"],
        "historical_lineage_reproducible": gate_statuses["historical_lineage_reproducible"],
        "gate_statuses": gate_statuses,
        "snapshot_contract_status": snapshot_status,
        "blocking_reasons": [] if snapshot_status != "BLOCKED" else blocked_gates,
        "operator_explanation": (
            "Historical accounting snapshot contract is not required for this source type."
            if not required
            else "Historical accounting remains fail-closed until point-in-time policy, "
            "report-lag, restatement, and reproducible lineage are all explicit."
            if blocked_gates
            else "Historical accounting snapshot contract is explicit and no-lookahead safe."
        ),
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "lookahead_contamination_forbidden": True,
        },
    }


__all__ = [
    "SCHEMA_VERSION",
    "SNAPSHOT_GATE_NAMES",
    "SNAPSHOT_STATUS_VOCABULARY",
    "evaluate_historical_accounting_snapshot",
]
