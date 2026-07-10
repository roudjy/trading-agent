"""Read-only QRE architecture registry.

The registry classifies known QRE architecture surfaces. It validates only the
registered entries in PR 1; closed-world repository-wide enforcement belongs to
the follow-up audit gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

Role = Literal[
    "canonical_loop",
    "provider_adapter",
    "legacy_surface",
    "observability_only",
    "fixture_only",
    "governance_only",
]
MaturityLevel = Literal[
    "scaffold",
    "working_capability",
    "operator_trusted_capability",
    "synthesis_consideration",
    "shadow_ready",
    "paper_ready",
    "live_ready",
    "blocked",
    "reference_only",
]

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH: Final[Path] = REPO_ROOT / "docs" / "architecture" / "qre_architecture_registry.v1.json"
REGISTRY_KIND: Final[str] = "qre_architecture_registry"
SCHEMA_VERSION: Final[int] = 1

ALLOWED_ROLES: Final[tuple[str, ...]] = (
    "canonical_loop",
    "provider_adapter",
    "legacy_surface",
    "observability_only",
    "fixture_only",
    "governance_only",
)
ALLOWED_MATURITY_LEVELS: Final[tuple[str, ...]] = (
    "scaffold",
    "working_capability",
    "operator_trusted_capability",
    "synthesis_consideration",
    "shadow_ready",
    "paper_ready",
    "live_ready",
    "blocked",
    "reference_only",
)
AUTHORITY_FLAGS: Final[tuple[str, ...]] = (
    "audit_only",
    "classification_only",
    "runtime_behavior_changed",
    "creates_candidates",
    "creates_strategies",
    "creates_presets",
    "creates_campaigns",
    "runs_screening",
    "runs_validation",
    "strategy_synthesis_authority",
    "trading_authority",
    "shadow_authority",
    "paper_authority",
    "live_authority",
    "broker_authority",
    "risk_authority",
    "order_authority",
    "capital_allocation_authority",
    "dashboard_mutation_authority",
    "empirical_evidence_authority",
    "research_object_producer_authority",
)
BLOCKED_AUTHORITY_FLAGS: Final[tuple[str, ...]] = (
    "runtime_behavior_changed",
    "strategy_synthesis_authority",
    "trading_authority",
    "shadow_authority",
    "paper_authority",
    "live_authority",
    "broker_authority",
    "risk_authority",
    "order_authority",
    "capital_allocation_authority",
    "dashboard_mutation_authority",
)
FROZEN_LEGACY_OUTPUTS: Final[tuple[str, ...]] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)
REQUIRED_ENTRY_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "name",
    "role",
    "maturity_level",
    "status",
    "producer_modules",
    "consumer_modules",
    "artifact_paths",
    "canonical_objects_owned",
    "canonical_objects_consumed",
    "allowed_outputs",
    "forbidden_outputs",
    "authority_flags",
    "provider_scope",
    "operator_decision_required",
    "notes",
)
HIGH_RISK_MATURITY_LEVELS: Final[tuple[str, ...]] = (
    "operator_trusted_capability",
    "synthesis_consideration",
    "shadow_ready",
    "paper_ready",
    "live_ready",
    "blocked",
)
SETTLED_HIGH_RISK_STATUSES: Final[tuple[str, ...]] = (
    "settled_bridge_read_model_only",
    "settled_non_executable_synthesis_consideration",
)
QRE_IMPACT_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "apps/control-plane/",
    "docs/architecture/qre_",
    "docs/roadmap/",
    "packages/qre_",
    "research/qre_",
    "tests/architecture/",
    "tests/unit/test_qre_",
    "tools/qre_",
)
IGNORED_UNTRACKED_PREFIXES: Final[tuple[str, ...]] = (
    "copilot-worktrees/",
    "tmp/",
    "trading-agent/",
)


@dataclass(frozen=True, slots=True)
class ArchitectureRegistryEntry:
    id: str
    name: str
    role: Role
    maturity_level: MaturityLevel
    status: str
    producer_modules: tuple[str, ...]
    consumer_modules: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    canonical_objects_owned: tuple[str, ...]
    canonical_objects_consumed: tuple[str, ...]
    allowed_outputs: tuple[str, ...]
    forbidden_outputs: tuple[str, ...]
    authority_flags: dict[str, bool]
    provider_scope: str
    operator_decision_required: bool
    notes: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> ArchitectureRegistryEntry:
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            role=row["role"],
            maturity_level=row["maturity_level"],
            status=str(row["status"]),
            producer_modules=tuple(str(item) for item in row["producer_modules"]),
            consumer_modules=tuple(str(item) for item in row["consumer_modules"]),
            artifact_paths=tuple(str(item) for item in row["artifact_paths"]),
            canonical_objects_owned=tuple(str(item) for item in row["canonical_objects_owned"]),
            canonical_objects_consumed=tuple(str(item) for item in row["canonical_objects_consumed"]),
            allowed_outputs=tuple(str(item) for item in row["allowed_outputs"]),
            forbidden_outputs=tuple(str(item) for item in row["forbidden_outputs"]),
            authority_flags={str(key): bool(value) for key, value in row["authority_flags"].items()},
            provider_scope=str(row["provider_scope"]),
            operator_decision_required=bool(row["operator_decision_required"]),
            notes=str(row["notes"]),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "maturity_level": self.maturity_level,
            "status": self.status,
            "producer_modules": list(self.producer_modules),
            "consumer_modules": list(self.consumer_modules),
            "artifact_paths": list(self.artifact_paths),
            "canonical_objects_owned": list(self.canonical_objects_owned),
            "canonical_objects_consumed": list(self.canonical_objects_consumed),
            "allowed_outputs": list(self.allowed_outputs),
            "forbidden_outputs": list(self.forbidden_outputs),
            "authority_flags": dict(self.authority_flags),
            "provider_scope": self.provider_scope,
            "operator_decision_required": self.operator_decision_required,
            "notes": self.notes,
        }


def _read_payload(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> tuple[ArchitectureRegistryEntry, ...]:
    payload = _read_payload(path)
    return tuple(ArchitectureRegistryEntry.from_dict(row) for row in payload["entries"])


def registry_entries() -> tuple[ArchitectureRegistryEntry, ...]:
    return load_registry()


def registry_as_dict() -> dict[str, dict[str, object]]:
    return {entry.id: entry.as_dict() for entry in registry_entries()}


def registry_by_id(entry_id: str) -> ArchitectureRegistryEntry:
    for entry in registry_entries():
        if entry.id == entry_id:
            return entry
    raise KeyError(entry_id)


def protected_outputs() -> tuple[str, ...]:
    protected: set[str] = set(FROZEN_LEGACY_OUTPUTS)
    for entry in registry_entries():
        protected.update(path for path in entry.forbidden_outputs if path in FROZEN_LEGACY_OUTPUTS)
        if entry.role == "legacy_surface":
            protected.update(path for path in entry.allowed_outputs if path in FROZEN_LEGACY_OUTPUTS)
    return tuple(sorted(protected))


def registered_producer_modules() -> dict[str, str]:
    return {
        module: entry.id
        for entry in registry_entries()
        for module in entry.producer_modules
    }


def registered_artifact_paths() -> dict[str, str]:
    return {
        artifact: entry.id
        for entry in registry_entries()
        for artifact in entry.artifact_paths
    }


def canonical_ownership_index() -> dict[str, str]:
    return {
        canonical_object: entry.id
        for entry in registry_entries()
        for canonical_object in entry.canonical_objects_owned
    }


def canonical_ownership_duplicates(
    entries: tuple[ArchitectureRegistryEntry, ...] | None = None,
) -> dict[str, tuple[str, ...]]:
    selected = entries if entries is not None else registry_entries()
    owners: dict[str, list[str]] = {}
    for entry in selected:
        for canonical_object in entry.canonical_objects_owned:
            owners.setdefault(canonical_object, []).append(entry.id)
    return {
        canonical_object: tuple(entry_ids)
        for canonical_object, entry_ids in owners.items()
        if len(entry_ids) > 1
    }


def operator_decision_entries() -> tuple[ArchitectureRegistryEntry, ...]:
    return tuple(entry for entry in registry_entries() if entry.operator_decision_required)


def _validate_payload_shape(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("registry_kind") != REGISTRY_KIND:
        errors.append("invalid_registry_kind")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    if not isinstance(payload.get("entries"), list):
        errors.append("entries_must_be_list")
    return errors


def validate_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[str]:
    payload = _read_payload(path)
    errors = _validate_payload_shape(payload)
    rows = payload.get("entries", [])
    if not isinstance(rows, list):
        return errors

    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"entry_must_be_object:{index}")
            continue
        missing = [field for field in REQUIRED_ENTRY_FIELDS if field not in row]
        errors.extend(f"missing_field:{row.get('id', index)}:{field}" for field in missing)
        if missing:
            continue

        entry_id = str(row["id"])
        if entry_id in seen_ids:
            errors.append(f"duplicate_entry_id:{entry_id}")
        seen_ids.add(entry_id)
        if row["role"] not in ALLOWED_ROLES:
            errors.append(f"unknown_role:{entry_id}:{row['role']}")
        if row["maturity_level"] not in ALLOWED_MATURITY_LEVELS:
            errors.append(f"unknown_maturity_level:{entry_id}:{row['maturity_level']}")
        if not isinstance(row["operator_decision_required"], bool):
            errors.append(f"operator_decision_required_must_be_bool:{entry_id}")

        flags = row["authority_flags"]
        if not isinstance(flags, dict):
            errors.append(f"authority_flags_must_be_object:{entry_id}")
            continue
        unknown_flags = sorted(set(flags) - set(AUTHORITY_FLAGS))
        missing_flags = sorted(set(AUTHORITY_FLAGS) - set(flags))
        errors.extend(f"unknown_authority_flag:{entry_id}:{flag}" for flag in unknown_flags)
        errors.extend(f"missing_authority_flag:{entry_id}:{flag}" for flag in missing_flags)
        for flag, value in flags.items():
            if not isinstance(value, bool):
                errors.append(f"authority_flag_must_be_bool:{entry_id}:{flag}")

        if row["role"] == "observability_only" and flags.get("research_object_producer_authority"):
            errors.append(f"observability_research_object_authority:{entry_id}")
        if row["role"] == "fixture_only" and flags.get("empirical_evidence_authority"):
            errors.append(f"fixture_empirical_evidence_authority:{entry_id}")
        if row["role"] == "provider_adapter" and row["canonical_objects_owned"]:
            errors.append(f"provider_adapter_owns_canonical_semantics:{entry_id}")
        if row["role"] == "legacy_surface" and row["canonical_objects_owned"] and not row["operator_decision_required"]:
            errors.append(f"legacy_canonical_ownership_without_operator_decision:{entry_id}")
        if (
            row["maturity_level"] in HIGH_RISK_MATURITY_LEVELS
            and row["maturity_level"] != "operator_trusted_capability"
            and not row["operator_decision_required"]
            and row["status"] not in SETTLED_HIGH_RISK_STATUSES
        ):
            errors.append(f"high_risk_maturity_without_operator_decision:{entry_id}")
        for flag in BLOCKED_AUTHORITY_FLAGS:
            if flags.get(flag):
                errors.append(f"blocked_authority_enabled:{entry_id}:{flag}")

    protected = protected_outputs()
    for frozen_output in FROZEN_LEGACY_OUTPUTS:
        if frozen_output not in protected:
            errors.append(f"frozen_output_not_protected:{frozen_output}")
    return errors


def _matches_registered_path(path: str, registered_path: str) -> bool:
    if registered_path.endswith("/**"):
        return path.startswith(registered_path[:-3])
    if registered_path.endswith("/"):
        return path.startswith(registered_path)
    if "." not in Path(registered_path).name and path.startswith(registered_path.rstrip("/") + "/"):
        return True
    return path == registered_path


def is_qre_impact_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in FROZEN_LEGACY_OUTPUTS:
        return True
    if normalized.startswith(IGNORED_UNTRACKED_PREFIXES):
        return False
    return normalized.startswith(QRE_IMPACT_PATH_PREFIXES)


def registered_entry_for_producer(module_path: str) -> ArchitectureRegistryEntry | None:
    for entry in registry_entries():
        if any(_matches_registered_path(module_path, producer) for producer in entry.producer_modules):
            return entry
    return None


def registered_entry_for_artifact(artifact_path: str) -> ArchitectureRegistryEntry | None:
    for entry in registry_entries():
        registered_paths = entry.artifact_paths + entry.allowed_outputs + entry.forbidden_outputs
        if any(_matches_registered_path(artifact_path, candidate) for candidate in registered_paths):
            return entry
    return None


def registry_entries_for_paths(paths: tuple[str, ...]) -> tuple[ArchitectureRegistryEntry, ...]:
    touched: dict[str, ArchitectureRegistryEntry] = {}
    for path in paths:
        normalized = path.replace("\\", "/")
        for entry in registry_entries():
            candidates = (
                entry.producer_modules
                + entry.consumer_modules
                + entry.artifact_paths
                + entry.allowed_outputs
                + entry.forbidden_outputs
            )
            if any(_matches_registered_path(normalized, candidate) for candidate in candidates):
                touched[entry.id] = entry
    return tuple(touched[entry_id] for entry_id in sorted(touched))


def validate_closed_world_audit(
    *,
    producer_modules: tuple[str, ...] = (),
    artifact_paths: tuple[str, ...] = (),
    canonical_objects: tuple[str, ...] = (),
    maturity_claims: tuple[str, ...] = (),
    authority_flags: tuple[str, ...] = (),
    entries: tuple[ArchitectureRegistryEntry, ...] | None = None,
) -> list[str]:
    selected_entries = entries if entries is not None else registry_entries()
    registered_objects = {
        obj
        for entry in selected_entries
        for obj in entry.canonical_objects_owned + entry.canonical_objects_consumed
    }
    errors = validate_registry()

    for module_path in sorted(set(producer_modules)):
        if registered_entry_for_producer(module_path) is None:
            errors.append(f"unregistered_producer:{module_path}")
    for artifact_path in sorted(set(artifact_paths)):
        if registered_entry_for_artifact(artifact_path) is None:
            errors.append(f"unregistered_artifact_path:{artifact_path}")
    for canonical_object in sorted(set(canonical_objects)):
        if canonical_object not in registered_objects:
            errors.append(f"unknown_canonical_object_owner:{canonical_object}")
    for canonical_object, owners in canonical_ownership_duplicates(selected_entries).items():
        errors.append(f"duplicate_canonical_object_owner:{canonical_object}:{','.join(owners)}")
    for maturity_claim in sorted(set(maturity_claims)):
        if maturity_claim not in ALLOWED_MATURITY_LEVELS:
            errors.append(f"unknown_maturity_claim:{maturity_claim}")
    for authority_flag in sorted(set(authority_flags)):
        if authority_flag not in AUTHORITY_FLAGS:
            errors.append(f"unknown_authority_flag:{authority_flag}")
    return errors


def registry_summary() -> dict[str, object]:
    entries = registry_entries()
    role_counts: dict[str, int] = {}
    maturity_counts: dict[str, int] = {}
    for entry in entries:
        role_counts[entry.role] = role_counts.get(entry.role, 0) + 1
        maturity_counts[entry.maturity_level] = maturity_counts.get(entry.maturity_level, 0) + 1
    return {
        "registry_kind": REGISTRY_KIND,
        "schema_version": SCHEMA_VERSION,
        "entries": len(entries),
        "roles": role_counts,
        "maturity_levels": maturity_counts,
        "protected_outputs": list(protected_outputs()),
        "operator_decision_required": [entry.id for entry in operator_decision_entries()],
    }


__all__ = [
    "ALLOWED_MATURITY_LEVELS",
    "ALLOWED_ROLES",
    "AUTHORITY_FLAGS",
    "BLOCKED_AUTHORITY_FLAGS",
    "DEFAULT_REGISTRY_PATH",
    "FROZEN_LEGACY_OUTPUTS",
    "IGNORED_UNTRACKED_PREFIXES",
    "QRE_IMPACT_PATH_PREFIXES",
    "REGISTRY_KIND",
    "SCHEMA_VERSION",
    "ArchitectureRegistryEntry",
    "canonical_ownership_index",
    "canonical_ownership_duplicates",
    "is_qre_impact_path",
    "load_registry",
    "operator_decision_entries",
    "protected_outputs",
    "registered_entry_for_artifact",
    "registered_entry_for_producer",
    "registered_artifact_paths",
    "registered_producer_modules",
    "registry_as_dict",
    "registry_by_id",
    "registry_entries_for_paths",
    "registry_entries",
    "registry_summary",
    "validate_closed_world_audit",
    "validate_registry",
]
