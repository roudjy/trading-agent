"""Compatibility import for the control-plane/QRE adapter contract.

The canonical implementation lives in
``packages.control_plane_qre_adapter_contract``. This module preserves the
ARCH-005 reporting import path until consumers migrate intentionally.
"""

from __future__ import annotations

from packages.control_plane_qre_adapter_contract import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    FORBIDDEN_CAPABILITIES,
    READ_ONLY_METHODS,
    AdapterContractDescription,
    ControlPlaneQREReadAdapter,
    ReadModelContract,
    describe_contract,
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
