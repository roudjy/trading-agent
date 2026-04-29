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
    CAMPAIGN_REGISTRY_PATH,
    DEFERRED_COMPONENTS,
    OBSERVABILITY_SCHEMA_VERSION,
    OBSERVABILITY_SUMMARY_PATH,
    RESEARCH_DIR,
    SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS,
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

# v3.15.15.6: split status fields. ``infrastructure_status`` describes
# whether the OBSERVABILITY artifacts themselves are healthy. The
# pre-existing ``overall_status`` is kept backward-compatible (same
# values, same semantics) — consumers that read it never break.
# ``diagnostic_evidence_status`` is a NEW field describing whether the
# upstream evidence (registry / ledger / screening) is rich enough to
# explain failures.
INFRA_HEALTHY = "healthy"
INFRA_DEGRADED = "degraded"
INFRA_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
INFRA_UNKNOWN = "unknown"

EVIDENCE_SUFFICIENT = "sufficient"
EVIDENCE_PARTIAL = "partial"
EVIDENCE_INSUFFICIENT = "insufficient"
EVIDENCE_UNAVAILABLE = "unavailable"

# Path to the sprint-progress sidecar — read for the freshness
# warning ONLY. Never mutated; never imported from
# research.discovery_sprint.
SPRINT_PROGRESS_PATH: Path = (
    RESEARCH_DIR / "discovery_sprints" / "discovery_sprint_progress_latest.v1.json"
)

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


def _sprint_progress_freshness(
    *,
    sprint_progress_path: Path,
    registry_path: Path,
    threshold_seconds: int,
) -> dict[str, Any]:
    """Compare sprint-progress mtime against campaign-registry mtime.

    Returns a dict that always has a stable shape so consumers can
    rely on the keys. The only side effect is reading file mtimes.

    A stale sprint progress is **only ever a warning** (never sets
    ``infrastructure_status`` to degraded) per the v3.15.15.6 brief —
    sprint progress is a sidecar, not infrastructure.
    """
    out: dict[str, Any] = {
        "available": False,
        "stale_relative_to_campaign_registry": False,
        "sprint_progress_generated_at_utc": None,
        "campaign_registry_generated_at_utc": None,
        "sprint_progress_modified_at_unix": None,
        "campaign_registry_modified_at_unix": None,
        "age_delta_seconds": None,
        "threshold_seconds": int(threshold_seconds),
    }
    sp_result = read_json_safe(sprint_progress_path)
    rg_result = read_json_safe(registry_path)
    if sp_result.state != "valid" or rg_result.state != "valid":
        return out

    out["available"] = True
    sp_mtime = sp_result.modified_at_unix
    rg_mtime = rg_result.modified_at_unix
    out["sprint_progress_modified_at_unix"] = sp_mtime
    out["campaign_registry_modified_at_unix"] = rg_mtime
    if isinstance(sp_result.payload, dict):
        gen = sp_result.payload.get("generated_at_utc")
        if isinstance(gen, str):
            out["sprint_progress_generated_at_utc"] = gen
    if isinstance(rg_result.payload, dict):
        gen = rg_result.payload.get("generated_at_utc")
        if isinstance(gen, str):
            out["campaign_registry_generated_at_utc"] = gen
    if (
        isinstance(sp_mtime, (int, float))
        and isinstance(rg_mtime, (int, float))
    ):
        delta = max(0.0, float(rg_mtime) - float(sp_mtime))
        out["age_delta_seconds"] = int(delta)
        if delta > float(threshold_seconds):
            out["stale_relative_to_campaign_registry"] = True
    return out


def build_observability_summary(
    *,
    now_utc: datetime | None = None,
    active_components: tuple[tuple[str, str, Path], ...] | None = None,
    deferred_components: tuple[tuple[str, str], ...] | None = None,
    sprint_progress_path: Path | None = None,
    campaign_registry_path: Path | None = None,
    sprint_stale_threshold_seconds: int | None = None,
) -> dict[str, Any]:
    """v3.15.15.6 enrichments (additive):

    * ``infrastructure_status`` — same semantics as the legacy
      ``overall_status`` (kept for backward-compat). Describes
      whether the OBSERVABILITY artifact set itself is healthy.
    * ``diagnostic_evidence_status`` — derived from the
      failure_modes payload's ``diagnostic_context.diagnostic_evidence_status``.
      Reports whether upstream evidence is rich enough to explain
      failures, independent of whether the diagnostics artifacts
      themselves loaded cleanly.
    * ``overall_status`` — kept identical to the legacy field for
      backward compatibility.
    * Limitation strings from
      ``failure_modes.diagnostic_context.limitations`` are propagated
      into ``warnings`` so an operator sees them on
      ``/observability``.
    * Sprint-progress mtime vs campaign-registry mtime is checked;
      a stale sprint progress emits a warning ONLY (never flips
      ``infrastructure_status`` to degraded).
    """
    when = now_utc or default_now_utc()
    actives = active_components or ACTIVE_COMPONENTS
    deferreds = deferred_components or DEFERRED_COMPONENTS
    sp_path = (
        sprint_progress_path
        if sprint_progress_path is not None
        else SPRINT_PROGRESS_PATH
    )
    rg_path = (
        campaign_registry_path
        if campaign_registry_path is not None
        else CAMPAIGN_REGISTRY_PATH
    )
    threshold = (
        sprint_stale_threshold_seconds
        if sprint_stale_threshold_seconds is not None
        else SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS
    )

    component_rows: list[dict[str, Any]] = []
    component_status_counts: dict[str, int] = {}
    critical_findings: list[str] = []
    warnings: list[str] = []
    informational: list[str] = []
    earliest_generated: str | None = None
    latest_generated: str | None = None
    failure_modes_payload: dict[str, Any] | None = None

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

        # Stash the failure_modes payload for evidence-warning
        # propagation below.
        if name == "failure_modes" and isinstance(payload, dict):
            failure_modes_payload = payload

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

    # v3.15.15.6 — infrastructure_status mirrors overall_status semantics
    # (same enum values), and diagnostic_evidence_status is sourced from
    # the failure_modes payload when available.
    infrastructure_status = overall
    diagnostic_evidence_status: str = EVIDENCE_UNAVAILABLE
    diagnostic_mode: str | None = None
    failure_modes_limitations: list[str] = []
    if failure_modes_payload is not None:
        ctx = failure_modes_payload.get("diagnostic_context")
        if isinstance(ctx, dict):
            evs = ctx.get("diagnostic_evidence_status")
            if isinstance(evs, str) and evs:
                diagnostic_evidence_status = evs
            dm = ctx.get("diagnostic_mode")
            if isinstance(dm, str) and dm:
                diagnostic_mode = dm
            lims = ctx.get("limitations")
            if isinstance(lims, list):
                failure_modes_limitations = [
                    str(x) for x in lims if isinstance(x, str)
                ]

    # Propagate failure_modes limitations into the summary's warnings
    # so an operator on /observability sees them.
    for code in failure_modes_limitations:
        warnings.append(f"diagnostic_evidence_limitation: {code}")

    # Aggregate-level "diagnostic evidence partial" warning when
    # infrastructure is healthy but evidence is partial/insufficient.
    if (
        infrastructure_status == INFRA_HEALTHY
        and diagnostic_evidence_status in (EVIDENCE_PARTIAL, EVIDENCE_INSUFFICIENT)
    ):
        warnings.append(
            f"diagnostic_evidence_{diagnostic_evidence_status}: "
            f"infrastructure healthy, evidence {diagnostic_evidence_status}"
        )

    # Sprint-progress staleness check — warning only, never degraded.
    sprint_freshness = _sprint_progress_freshness(
        sprint_progress_path=sp_path,
        registry_path=rg_path,
        threshold_seconds=threshold,
    )
    if sprint_freshness.get("stale_relative_to_campaign_registry"):
        delta = sprint_freshness.get("age_delta_seconds")
        warnings.append(
            "sprint_progress_stale_relative_to_registry: "
            f"delta_seconds={delta}, threshold_seconds={threshold}"
        )

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "observation_window": {
            "earliest_component_generated_at_utc": earliest_generated,
            "latest_component_generated_at_utc": latest_generated,
            "inferred_from": "active_component_generated_at_utc",
        },
        # Backward-compat: overall_status retains its legacy semantics
        # (== infrastructure_status). New consumers should prefer
        # ``infrastructure_status`` + ``diagnostic_evidence_status``.
        "overall_status": overall,
        "infrastructure_status": infrastructure_status,
        "diagnostic_evidence_status": diagnostic_evidence_status,
        "diagnostic_mode": diagnostic_mode,
        "component_status_counts": dict(sorted(component_status_counts.items())),
        "components": component_rows,
        "critical_findings": sorted(critical_findings),
        "warnings": sorted(warnings),
        "informational_findings": sorted(informational),
        "sprint_progress_freshness": sprint_freshness,
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
    "EVIDENCE_INSUFFICIENT",
    "EVIDENCE_PARTIAL",
    "EVIDENCE_SUFFICIENT",
    "EVIDENCE_UNAVAILABLE",
    "INFRA_DEGRADED",
    "INFRA_HEALTHY",
    "INFRA_INSUFFICIENT_EVIDENCE",
    "INFRA_UNKNOWN",
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
