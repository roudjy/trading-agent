"""Addendum 4 maturity validation for QRE architecture surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from packages.qre_research.architecture_registry import (
    DEFAULT_REGISTRY_PATH,
    ArchitectureRegistryEntry,
    registry_entries,
)

EVIDENCE_REQUIREMENTS: Final[tuple[str, ...]] = (
    "persistent_artifacts",
    "explainable_decisions",
    "repeatable_outputs",
    "evidence_backed_disposition",
    "policy_auditable_lineage",
    "contradiction_visibility",
    "failure_traceability",
    "operator_verifiable_summary",
)
ADDENDUM_4_POLICY_KEY: Final[str] = "addendum_4_maturity_policy"


def load_maturity_policy(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    policy = payload.get(ADDENDUM_4_POLICY_KEY, {})
    return policy if isinstance(policy, dict) else {}


def validate_maturity_policy(policy: dict[str, Any] | None = None) -> list[str]:
    selected = policy if policy is not None else load_maturity_policy()
    errors: list[str] = []
    requirements = selected.get("evidence_requirements")
    if not isinstance(requirements, list):
        errors.append("missing_evidence_requirements")
        requirements = []
    missing = set(EVIDENCE_REQUIREMENTS) - set(requirements)
    errors.extend(f"missing_evidence_requirement:{name}" for name in sorted(missing))
    for key in (
        "shadow_ready_default_disabled_required",
        "paper_ready_blocked",
        "live_ready_blocked",
        "dashboard_mutation_blocked",
    ):
        if selected.get(key) is not True:
            errors.append(f"policy_flag_not_enabled:{key}")
    if not isinstance(selected.get("operator_trusted_slice_ids"), list):
        errors.append("operator_trusted_slice_ids_must_be_list")
    return errors


def validate_maturity_entry(
    entry: ArchitectureRegistryEntry,
    policy: dict[str, Any] | None = None,
) -> list[str]:
    selected_policy = policy if policy is not None else load_maturity_policy()
    errors: list[str] = []
    flags = entry.authority_flags

    if entry.maturity_level == "scaffold" and "operator_trusted" in entry.status:
        errors.append(f"scaffold_claims_operator_trusted:{entry.id}")
    if entry.maturity_level == "working_capability":
        if flags.get("strategy_authoritative") or flags.get("creates_strategies"):
            errors.append(f"working_capability_claims_strategy_authoritative:{entry.id}")
        if flags.get("deployment_authoritative") or flags.get("trading_authority"):
            errors.append(f"working_capability_claims_deployment_authoritative:{entry.id}")
    if entry.maturity_level == "operator_trusted_capability":
        trusted_ids = selected_policy.get("operator_trusted_slice_ids", [])
        if entry.id not in trusted_ids:
            errors.append(f"operator_trusted_not_slice_specific:{entry.id}")
        if validate_maturity_policy(selected_policy):
            errors.append(f"operator_trusted_missing_policy_requirements:{entry.id}")
        if not entry.notes:
            errors.append(f"operator_trusted_missing_reason:{entry.id}")
        if not entry.artifact_paths:
            errors.append(f"operator_trusted_missing_evidence:{entry.id}")
        if not (entry.canonical_objects_consumed or entry.canonical_objects_owned):
            errors.append(f"operator_trusted_missing_lineage:{entry.id}")
    if entry.maturity_level == "synthesis_consideration":
        if not entry.operator_decision_required:
            errors.append(f"synthesis_consideration_without_operator_decision:{entry.id}")
        if flags.get("strategy_synthesis_authority") or flags.get("creates_strategies"):
            errors.append(f"synthesis_consideration_claims_executable_strategy_authority:{entry.id}")
        if not entry.canonical_objects_consumed:
            errors.append(f"synthesis_consideration_missing_evidence_backed_eligibility:{entry.id}")
    if entry.maturity_level == "shadow_ready":
        if selected_policy.get("shadow_ready_default_disabled_required") is not True:
            errors.append(f"shadow_ready_missing_default_disabled_gate:{entry.id}")
        if flags.get("order_authority") or flags.get("capital_allocation_authority"):
            errors.append(f"shadow_ready_claims_order_or_capital_authority:{entry.id}")
    if entry.maturity_level == "paper_ready":
        errors.append(f"paper_ready_blocked_in_architecture_sequence:{entry.id}")
    if entry.maturity_level == "live_ready":
        errors.append(f"live_ready_blocked_in_architecture_sequence:{entry.id}")
    if flags.get("dashboard_mutation_authority"):
        errors.append(f"dashboard_mutation_authority_blocked:{entry.id}")
    return errors


def validate_maturity_gate(
    entries: tuple[ArchitectureRegistryEntry, ...] | None = None,
    policy: dict[str, Any] | None = None,
) -> list[str]:
    selected_entries = entries if entries is not None else registry_entries()
    selected_policy = policy if policy is not None else load_maturity_policy()
    errors = validate_maturity_policy(selected_policy)
    for entry in selected_entries:
        errors.extend(validate_maturity_entry(entry, selected_policy))
    return errors


__all__ = [
    "ADDENDUM_4_POLICY_KEY",
    "EVIDENCE_REQUIREMENTS",
    "load_maturity_policy",
    "validate_maturity_entry",
    "validate_maturity_gate",
    "validate_maturity_policy",
]
