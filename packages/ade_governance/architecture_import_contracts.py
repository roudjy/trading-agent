"""Compatibility shim for ADE architecture import contracts.

The canonical implementation lives in
``packages.ade_governance.import_contracts.architecture_import``.
"""

from __future__ import annotations

from packages.ade_governance.import_contracts.architecture_import import (
    DOMAIN_ADAPTER_CONTRACT,
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_GOVERNANCE_TOOLING,
    DOMAIN_QRE,
    DOMAIN_TESTS,
    DOMAIN_UNKNOWN,
    EXECUTION_PATH_ROOTS,
    BoundaryFinding,
    BoundaryReport,
    ImportEdge,
    LegacyEdgeAllowlistEntry,
)


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
