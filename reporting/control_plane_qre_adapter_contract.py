"""ARCH-005 read-only contract for future control-plane/QRE adapters.

This module is intentionally a scaffold. It defines the stable shape that
future dashboard/API code can depend on before any QRE package extraction.
It imports only stdlib modules and does not import QRE, dashboard, execution,
paper, shadow, live, broker, or risk modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

CONTRACT_VERSION = "arch-005.v1"
CONTRACT_NAME = "control-plane-qre-read-adapter"

READ_ONLY_METHODS: tuple[str, ...] = (
    "list_read_models",
    "read_json",
    "describe_contract",
)

FORBIDDEN_CAPABILITIES: tuple[str, ...] = (
    "approve",
    "broker",
    "create",
    "delete",
    "dispatch",
    "enqueue",
    "execute",
    "live",
    "mutate",
    "order",
    "paper",
    "risk",
    "save",
    "shadow",
    "spawn",
    "trade",
    "update",
    "write",
)


@dataclass(frozen=True)
class ReadModelContract:
    """Read-only JSON surface exposed by a future QRE adapter."""

    name: str
    schema_version: str
    description: str


@dataclass(frozen=True)
class AdapterContractDescription:
    """Deterministic metadata for architecture tests and future adapters."""

    name: str
    version: str
    read_only_methods: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]


@runtime_checkable
class ControlPlaneQREReadAdapter(Protocol):
    """Protocol future dashboard/API code can consume without QRE imports."""

    def list_read_models(self) -> tuple[ReadModelContract, ...]:
        """Return available read-only QRE read models."""

    def read_json(self, read_model: str) -> Mapping[str, Any]:
        """Return an existing QRE read model as JSON-compatible data."""

    def describe_contract(self) -> AdapterContractDescription:
        """Return deterministic contract metadata."""


def describe_contract() -> AdapterContractDescription:
    """Return the ARCH-005 adapter contract description."""
    return AdapterContractDescription(
        name=CONTRACT_NAME,
        version=CONTRACT_VERSION,
        read_only_methods=READ_ONLY_METHODS,
        forbidden_capabilities=FORBIDDEN_CAPABILITIES,
    )


__all__ = [
    "AdapterContractDescription",
    "CONTRACT_NAME",
    "CONTRACT_VERSION",
    "ControlPlaneQREReadAdapter",
    "FORBIDDEN_CAPABILITIES",
    "READ_ONLY_METHODS",
    "ReadModelContract",
    "describe_contract",
]
