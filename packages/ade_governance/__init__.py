"""ADE governance support contracts.

The package is stdlib-only and contains governance support surfaces that can be
shared before broader package migration.
"""

from __future__ import annotations

from packages.ade_governance.architecture_import_contracts import (
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
