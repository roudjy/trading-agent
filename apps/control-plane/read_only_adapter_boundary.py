"""Control-plane read-only boundary for the QRE adapter contract.

This module is intentionally not wired into dashboard routes. It proves the
target control-plane app boundary can consume the extracted adapter contract
without importing QRE runtime modules.
"""

from __future__ import annotations

from packages.control_plane_qre_adapter_contract import (
    AdapterContractDescription,
    describe_contract,
)


def describe_read_only_adapter_boundary() -> AdapterContractDescription:
    """Return the canonical control-plane/QRE read adapter contract."""
    return describe_contract()


__all__ = ["describe_read_only_adapter_boundary"]
