"""Research-adjacent, advisory-only execution bridge for v3.12.

Scope: build artifact-only agent_definition payloads that describe
what a promoted candidate WOULD look like as an agent, WITHOUT
producing any runnable behavior.

No imports from agent.execution, execution.paper, ccxt, yfinance,
or any broker adapter. Enforced by
tests/unit/test_agent_definition_bridge.py (AST-based check).
"""

from .agent_definition import (
    AGENT_DEFINITIONS_SCHEMA_VERSION,
    ALLOWED_PRESETS,
    BridgeScopeError,
    build_agent_definition_entry,
    build_agent_definitions_payload,
)

__all__ = [
    "AGENT_DEFINITIONS_SCHEMA_VERSION",
    "ALLOWED_PRESETS",
    "BridgeScopeError",
    "build_agent_definition_entry",
    "build_agent_definitions_payload",
]
