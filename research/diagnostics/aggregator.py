"""Observability aggregator.

Reads the per-component artifacts produced by the active modules
(plus any deferred-component artifacts that may exist by chance) and
emits a top-level ``observability_summary_latest.v1.json``.

Pure descriptive logic only:

* every component is loaded with ``read_json_safe`` — never raises;
* status of each component is one of:
  ``available`` | ``unavailable`` | ``corrupt`` | ``empty`` | ``deferred``;
* ``overall_status`` is a literal lookup over component states — no
  thresholds, no interpretation;
* ``recommended_next_human_action`` is also a literal lookup.

The aggregator NEVER infers operator decisions. If the data implies a
non-trivial action, it surfaces ``"investigation_required"`` and the
operator decides.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic

from .clock import default_now_utc, to_iso_z
from .io import read_json_safe
from .paths import (
    ACTIVE_COMPONENTS,
    DEFERRED_COMPONENTS,
    OBSERVABILITY_SCHEMA_VERSION,
    OBSERVABILITY_SUMMARY_PATH,
)


# Status taxonomy — stable strings.
STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_CORRUPT = "corrupt"
STATUS_EMPTY = "empty"
STATUS_DEFERRED = "deferred"

# Overall-status taxonomy.
OVERALL_HEALTHY = "healthy"
OVERALL_DEGRADED = "degraded"
OVERALL_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
OVERALL_UNKNOWN = "unknown"

# Recommended next action taxonomy.
ACTION_NONE = "none"
ACTION_INSPECT_ARTIFACTS = "inspect_artifacts"
ACTION_INVESTIGATION_REQUIRED = "investigation_required"
ACTION_ROADMAP_DECISION_REQUIRED = "roadmap_decision_required"


def _component_state_from_read(read_state: str, payload: Any) -> str:
    if read_state == "absent":
        return STATUS_UNAVAILABLE
    if read_state == "empty":
        return STATUS_EMPTY
    if read_state == "invalid_json" or read_state == "unreadable":
        return STATUS_CORRUPT
    if read_state == "valid":
        if isinstance(payload, dict):
            return STATUS_AVAILABLE
        # Valid JSON but unexpected shape (e.g. raw list at top level)
        # is treated as corrupt for the aggregator's purposes.
        return STATUS_CORRUPT
    return STATUS_UNAVAILABLE


def _summarise_component(read_result: Any, payload: Any) -> dict[str, Any]:
    return {
        "schema_version": (
            payload.get("schema_version")
            if isinstance(payload, dict)
            else None
        ),
        "generated_at_utc": (
            payload.get("generated_at_utc")
            if isinstance(payload, dict)
            else None
        ),
        "modified_at_unix": read_result.modified_at_unix,
        "size_bytes": read_result.size_bytes,
        "error_message": read_result.error_message or None,
    }


def _classify_overall(component_status_counts: dict[str, int]) -> str:
    """Pure rule. No thresholds beyond the explicit comparisons here.

    healthy:      every active component is available
    degraded:     at least one corrupt or stale-but-readable component
    insufficient: every active component is unavailable
    unknown:      anything else
    """
    available = component_status_counts.get(STATUS_AVAILABLE, 0)
    corrupt = component_status_counts.get(STATUS_CORRUPT, 0)
    unavailable = component_status_counts.get(STATUS_UNAVAILABLE, 0)
    empty = component_status_counts.get(STATUS_EMPTY, 0)
    active_total = (
        available + corrupt + unavailable + empty
    )

    if active_total == 0:
        return OVERALL_UNKNOWN
    if corrupt > 0:
        return OVERALL_DEGRADED
    if available == active_total:
        return OVERALL_HEALTHY
    if unavailable == active_total:
        return OVERALL_INSUFFICIENT_EVIDENCE
    if empty == active_total:
        return OVERALL_INSUFFICIENT_EVIDENCE
    if available > 0:
        # Mixed — some available, some not. Descriptively: degraded.
        return OVERALL_DEGRADED
    return OVERALL_UNKNOWN


def _recommended_action(overall_status: str, corrupt_count: int) -> str:
    """Pure lookup."""
    if corrupt_count > 0:
        return ACTION_INVESTIGATION_REQUIRED
    if overall_status == OVERALL_HEALTHY:
        return ACTION_NONE
    if overall_status == OVERALL_DEGRADED:
        return ACTION_INSPECT_ARTIFACTS
    if overall_status == OVERALL_INSUFFICIENT_EVIDENCE:
        return ACTION_INSPECT_ARTIFACTS
    return ACTION_ROADMAP_DECISION_REQUIRED


def build_observability_summary(
    *,
    now_utc: datetime | None = None,
    active_components: tuple[tuple[str, str, Path], ...] | None = None,
    deferred_components: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any]:
    when = now_utc or default_now_utc()
    actives = active_components or ACTIVE_COMPONENTS
    deferreds = deferred_components or DEFERRED_COMPONENTS

    component_rows: list[dict[str, Any]] = []
    component_status_counts: dict[str, int] = {}
    critical_findings: list[str] = []
    warnings: list[str] = []
    informational: list[str] = []
    earliest_generated: str | None = None
    latest_generated: str | None = None

    for name, slug, path in actives:
        result = read_json_safe(path)
        payload = result.payload
        status = _component_state_from_read(result.state, payload)
        component_status_counts[status] = component_status_counts.get(status, 0) + 1

        meta = _summarise_component(result, payload)
        component_rows.append(
            {
                "name": name,
                "slug": slug,
                "status": status,
                "path": str(path).replace("\\", "/"),
                **meta,
            }
        )

        if status == STATUS_CORRUPT:
            critical_findings.append(
                f"component {name} is corrupt: {result.error_message or 'parse failed'}"
            )
        elif status == STATUS_UNAVAILABLE:
            warnings.append(f"component {name} is unavailable (artifact missing)")
        elif status == STATUS_EMPTY:
            warnings.append(f"component {name} produced an empty artifact")
        else:
            gen = meta["generated_at_utc"]
            if isinstance(gen, str) and gen:
                if earliest_generated is None or gen < earliest_generated:
                    earliest_generated = gen
                if latest_generated is None or gen > latest_generated:
                    latest_generated = gen

    for name, slug in deferreds:
        component_rows.append(
            {
                "name": name,
                "slug": slug,
                "status": STATUS_DEFERRED,
                "path": None,
                "schema_version": None,
                "generated_at_utc": None,
                "modified_at_unix": None,
                "size_bytes": None,
                "error_message": "scheduled for v3.15.15.4 release",
            }
        )
        informational.append(f"component {name} is deferred to v3.15.15.4")

    component_rows.sort(key=lambda r: r["name"])
    overall = _classify_overall(component_status_counts)
    action = _recommended_action(
        overall_status=overall,
        corrupt_count=component_status_counts.get(STATUS_CORRUPT, 0),
    )

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "observation_window": {
            "earliest_component_generated_at_utc": earliest_generated,
            "latest_component_generated_at_utc": latest_generated,
            "inferred_from": "active_component_generated_at_utc",
        },
        "overall_status": overall,
        "component_status_counts": dict(sorted(component_status_counts.items())),
        "components": component_rows,
        "critical_findings": sorted(critical_findings),
        "warnings": sorted(warnings),
        "informational_findings": sorted(informational),
        "recommended_next_human_action": action,
        "active_component_count": len(actives),
        "deferred_component_count": len(deferreds),
    }


def write_observability_summary(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    target = path if path is not None else OBSERVABILITY_SUMMARY_PATH
    if "observability" not in str(target).replace("\\", "/").split("/"):
        raise RuntimeError(
            "write_observability_summary refuses to write outside research/observability/"
        )
    write_sidecar_atomic(target, payload)


__all__ = [
    "ACTION_INSPECT_ARTIFACTS",
    "ACTION_INVESTIGATION_REQUIRED",
    "ACTION_NONE",
    "ACTION_ROADMAP_DECISION_REQUIRED",
    "OVERALL_DEGRADED",
    "OVERALL_HEALTHY",
    "OVERALL_INSUFFICIENT_EVIDENCE",
    "OVERALL_UNKNOWN",
    "STATUS_AVAILABLE",
    "STATUS_CORRUPT",
    "STATUS_DEFERRED",
    "STATUS_EMPTY",
    "STATUS_UNAVAILABLE",
    "build_observability_summary",
    "write_observability_summary",
]
