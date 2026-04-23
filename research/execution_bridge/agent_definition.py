"""Advisory-only agent_definition builder.

v3.12 scope: produce research-adjacent artifacts that describe what a
promoted candidate WOULD look like as an agent, WITHOUT producing any
runnable behavior.

Hard invariants enforced by tests:

- Every emitted entry carries ``runnable=false`` and
  ``execution_scope="future_paper_phase_only"``.
- The payload's ``runnable_entries`` field is always ``0``.
- This module must not import anything from ``agent.execution``,
  ``execution.paper``, ``ccxt``, ``yfinance``, or any broker adapter.
  The AST check in tests/unit/test_agent_definition_bridge.py walks
  the source and fails if any such import appears.

Scope lock:

- ``preset_origin`` must be in ``ALLOWED_PRESETS``.
- ``lifecycle_status`` must be ``"exploratory"`` or ``"candidate"``.
- The candidate's ``strategy_name`` must be registered in
  ``research.registry.STRATEGIES``.

Out-of-scope entries are either skipped (``allow_partial=True``) and
recorded in ``skipped`` with a reason, or raise ``BridgeScopeError``
(``allow_partial=False``).
"""

from __future__ import annotations

from typing import Any, Iterable

from research.registry import STRATEGIES


AGENT_DEFINITIONS_SCHEMA_VERSION = "1.0"

ALLOWED_PRESETS: frozenset[str] = frozenset({
    "trend_equities_4h_baseline",
    "regime_filter_equities_4h_experimental",
})

ALLOWED_LIFECYCLE_STATUSES: frozenset[str] = frozenset({"exploratory", "candidate"})

ADVISORY_NOTE = (
    "v3.12 artifact — not intended for execution. "
    "Paper path defined in v3.15."
)


class BridgeScopeError(Exception):
    """Raised when a candidate falls outside v3.12 bridge scope."""


def _strategy_registered(strategy_name: str) -> bool:
    return any(s.get("name") == strategy_name for s in STRATEGIES)


def _skip_reason(registry_v2_entry: dict[str, Any]) -> str | None:
    """Return a human-readable reason if an entry is out of scope; else None."""
    preset_origin = registry_v2_entry.get("preset_origin")
    lifecycle_status = registry_v2_entry.get("lifecycle_status")
    strategy_name = registry_v2_entry.get("strategy_name", "")

    if preset_origin not in ALLOWED_PRESETS:
        return f"preset_origin_not_allowed:{preset_origin!r}"
    if lifecycle_status not in ALLOWED_LIFECYCLE_STATUSES:
        return f"lifecycle_status_not_active:{lifecycle_status!r}"
    if not _strategy_registered(strategy_name):
        return f"strategy_not_registered:{strategy_name!r}"
    return None


def build_agent_definition_entry(
    registry_v2_entry: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a single advisory-only agent definition entry.

    Raises ``BridgeScopeError`` if the entry is out of scope.
    """
    reason = _skip_reason(registry_v2_entry)
    if reason is not None:
        raise BridgeScopeError(reason)

    return {
        "candidate_id": registry_v2_entry["candidate_id"],
        "strategy_name": registry_v2_entry["strategy_name"],
        "parameter_set": registry_v2_entry.get("parameter_set") or {},
        "asset_universe": list(registry_v2_entry.get("asset_universe") or []),
        "interval": registry_v2_entry.get("interval"),
        "experiment_family": registry_v2_entry.get("experiment_family"),
        "runnable": False,
        "execution_scope": "future_paper_phase_only",
        "advisory_note": ADVISORY_NOTE,
        "source_candidate_registry_v2": "research/candidate_registry_latest.v2.json",
    }


def build_agent_definitions_payload(
    registry_v2_entries: Iterable[dict[str, Any]],
    generated_at_utc: str,
    allow_partial: bool = True,
) -> dict[str, Any]:
    """Build the full advisory-only agent_definitions payload.

    ``runnable_entries`` is pinned to 0 as a structural invariant.
    """
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for v2_entry in registry_v2_entries:
        reason = _skip_reason(v2_entry)
        if reason is not None:
            if not allow_partial:
                raise BridgeScopeError(reason)
            skipped.append(
                {
                    "candidate_id": str(v2_entry.get("candidate_id", "")),
                    "reason": reason,
                }
            )
            continue
        entries.append(build_agent_definition_entry(v2_entry))

    entries.sort(key=lambda e: e["candidate_id"])
    skipped.sort(key=lambda s: s["candidate_id"])

    return {
        "schema_version": AGENT_DEFINITIONS_SCHEMA_VERSION,
        "advisory_only": True,
        "runnable_entries": 0,
        "generated_at_utc": generated_at_utc,
        "scope_allowed_presets": sorted(ALLOWED_PRESETS),
        "entries": entries,
        "skipped": skipped,
    }
