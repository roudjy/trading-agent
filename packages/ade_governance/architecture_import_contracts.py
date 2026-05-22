"""Frozen contracts for deterministic architecture import scans.

This module intentionally contains only immutable vocabulary and data shapes.
Scanner traversal, policy evaluation, allowlists, and CLI behavior remain in
``reporting.architecture_import_scan``.
"""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN_ADE = "ADE"
DOMAIN_QRE = "QRE"
DOMAIN_CONTROL_PLANE = "control-plane"
DOMAIN_EXECUTION = "execution"
DOMAIN_ADAPTER_CONTRACT = "adapter-contract"
DOMAIN_TESTS = "tests"
DOMAIN_GOVERNANCE_TOOLING = "governance tooling"
DOMAIN_UNKNOWN = "unknown"

EXECUTION_PATH_ROOTS = frozenset(
    {
        "agent.execution",
        "agent.risk",
        "automation.live_gate",
        "broker",
        "execution",
        "live",
        "paper",
        "risk",
        "shadow",
    }
)


@dataclass(frozen=True)
class ImportEdge:
    source_module: str
    target_module: str
    source_path: str
    source_domain: str
    target_domain: str
    target_root: str
    line: int
    import_kind: str
    target_path: str | None = None


@dataclass(frozen=True)
class BoundaryFinding:
    source_module: str
    target_module: str
    source_path: str
    source_domain: str
    target_domain: str
    target_root: str
    line: int
    rule: str


@dataclass(frozen=True)
class BoundaryReport:
    edges: tuple[ImportEdge, ...]
    forbidden_edges: tuple[BoundaryFinding, ...]
    legacy_edges: tuple[BoundaryFinding, ...]


@dataclass(frozen=True)
class LegacyEdgeAllowlistEntry:
    source_module: str
    target_module: str
    rule: str
    status: str
    reason: str
    sunset: str


__all__ = [
    "BoundaryFinding",
    "BoundaryReport",
    "DOMAIN_ADAPTER_CONTRACT",
    "DOMAIN_ADE",
    "DOMAIN_CONTROL_PLANE",
    "DOMAIN_EXECUTION",
    "DOMAIN_GOVERNANCE_TOOLING",
    "DOMAIN_QRE",
    "DOMAIN_TESTS",
    "DOMAIN_UNKNOWN",
    "EXECUTION_PATH_ROOTS",
    "ImportEdge",
    "LegacyEdgeAllowlistEntry",
]
