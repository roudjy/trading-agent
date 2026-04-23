"""v3.12 candidate-sidecar façade.

This module is the SINGLE call-site ``run_research.py`` uses to
produce every v3.12 sidecar:

- candidate_registry_latest.v2.json
- candidate_status_history_latest.v1.json
- agent_definitions_latest.v1.json

Its sole responsibility is orchestration. All business logic lives
in the specialized builders
(``candidate_registry_v2``, ``candidate_status_history``,
``execution_bridge.agent_definition``). All writes go through
``_sidecar_io.write_sidecar_atomic`` so byte-reproducibility and
atomicity are uniform.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.candidate_registry_v2 import build_registry_v2_payload
from research.candidate_status_history import (
    build_history_payload,
    derive_events_from_run,
    load_existing_history,
    merge_history,
)
from research.execution_bridge import build_agent_definitions_payload


REGISTRY_V2_PATH = Path("research/candidate_registry_latest.v2.json")
STATUS_HISTORY_PATH = Path("research/candidate_status_history_latest.v1.json")
AGENT_DEFINITIONS_PATH = Path("research/agent_definitions_latest.v1.json")


@dataclass(frozen=True)
class SidecarBuildContext:
    """All inputs the façade needs to build the v3.12 sidecar set."""

    run_id: str
    generated_at_utc: str
    git_revision: str
    research_latest: dict[str, Any]
    candidate_registry_v1: dict[str, Any]
    run_candidates: dict[str, Any] | None
    run_meta: dict[str, Any] | None
    defensibility: dict[str, Any] | None
    regime: dict[str, Any] | None
    cost_sens: dict[str, Any] | None
    breadth_context: dict[str, Any] | None = None


def build_and_write_all(
    ctx: SidecarBuildContext,
    *,
    registry_path: Path = REGISTRY_V2_PATH,
    history_path: Path = STATUS_HISTORY_PATH,
    agent_definitions_path: Path = AGENT_DEFINITIONS_PATH,
) -> dict[str, Path]:
    """Produce and write all v3.12 sidecars atomically.

    Returns a dict mapping logical artifact name to the path written.
    Paths are configurable for test isolation; production callers
    use the module-level defaults.
    """
    # 1. Registry v2
    registry_v2 = build_registry_v2_payload(
        candidate_registry_v1=ctx.candidate_registry_v1,
        research_latest=ctx.research_latest,
        run_candidates=ctx.run_candidates,
        run_meta=ctx.run_meta,
        defensibility=ctx.defensibility,
        regime=ctx.regime,
        cost_sens=ctx.cost_sens,
        breadth_context=ctx.breadth_context,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
        generated_at_utc=ctx.generated_at_utc,
    )
    write_sidecar_atomic(registry_path, registry_v2)

    # 2. Status history (append-only, idempotent)
    v2_entries = registry_v2["entries"]
    events = derive_events_from_run(
        registry_v2_entries=v2_entries,
        run_id=ctx.run_id,
        now_utc=ctx.generated_at_utc,
        source_artifact=str(registry_path).replace("\\", "/"),
    )
    existing = load_existing_history(history_path)
    prior_bucket = existing.get("history", {}) if isinstance(existing, dict) else {}
    merged_history = merge_history(prior_bucket, events)
    history_payload = build_history_payload(
        history=merged_history,
        generated_at_utc=ctx.generated_at_utc,
    )
    write_sidecar_atomic(history_path, history_payload)

    # 3. Agent definitions (advisory-only, scope-locked)
    agent_defs = build_agent_definitions_payload(
        registry_v2_entries=v2_entries,
        generated_at_utc=ctx.generated_at_utc,
        allow_partial=True,
    )
    write_sidecar_atomic(agent_definitions_path, agent_defs)

    return {
        "candidate_registry_v2": registry_path,
        "candidate_status_history": history_path,
        "agent_definitions": agent_definitions_path,
    }
