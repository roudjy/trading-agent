"""v3.13 parallel regime-sidecar façade.

Single call-site invoked from ``run_research.py`` after the v3.12
façade. Writes two artifacts atomically through the canonical
``_sidecar_io.write_sidecar_atomic`` helper, so byte-reproducibility
and canonical key ordering match every other v3.1x sidecar:

- ``research/regime_intelligence_latest.v1.json`` (primary
  candidate-centric diagnostics)
- ``research/candidate_registry_regime_overlay_latest.v1.json``
  (registry-shaped overlay — joined on ``candidate_id``)

The overlay pattern means the v3.12 registry v2 is never re-opened
and rewritten here; consumers join overlay entries on
``candidate_id`` against the v2 registry. v3.12 semantics are
untouched.

Missing-state is graceful: when ``regime_diagnostics`` is absent the
façade still writes both artifacts with per-candidate assessment
``"insufficient_regime_evidence"`` and the canonical missing-state
summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.regime_classifier import (
    REGIME_CLASSIFIER_VERSION,
    REGIME_LAYER_VERSION,
)
from research.regime_diagnostics import (
    ASSESSMENT_SUFFICIENT,
    REGIME_CONCENTRATED_THRESHOLD,
    build_candidate_diagnostics,
    summarize_diagnostics,
)
from research.regime_gating import (
    build_candidate_gating_experiments,
    gating_rule_ids,
)


REGIME_INTELLIGENCE_PATH = Path("research/regime_intelligence_latest.v1.json")
REGIME_OVERLAY_PATH = Path("research/candidate_registry_regime_overlay_latest.v1.json")

REGIME_INTELLIGENCE_SCHEMA_VERSION = "1.0"
REGIME_OVERLAY_SCHEMA_VERSION = "1.0"

SOURCE_REGISTRY_POSIX = "research/candidate_registry_latest.v2.json"


@dataclass(frozen=True)
class RegimeSidecarBuildContext:
    """All inputs the v3.13 façade needs.

    ``width_distributions`` is a per-candidate_id dict of bucket-count
    dicts produced by :mod:`research.regime_classifier`. It is
    optional; absent entries get an all-insufficient width axis.
    """

    run_id: str
    generated_at_utc: str
    git_revision: str
    registry_v2: dict[str, Any]
    regime_diagnostics: dict[str, Any] | None
    width_distributions: dict[str, dict[str, int]] | None = None


def _registry_entries(registry_v2: dict[str, Any]) -> list[dict[str, Any]]:
    entries = registry_v2.get("entries") or []
    return [e for e in entries if isinstance(e, dict) and e.get("candidate_id")]


def _regime_concentrated_status(entry_diag: dict[str, Any]) -> str:
    """Label the v3.13 regime-concentrated derivation state for a
    candidate, used inside the overlay."""
    assessment = entry_diag.get("regime_assessment_status")
    if assessment != ASSESSMENT_SUFFICIENT:
        return "insufficient_evidence"
    scores = entry_diag.get("regime_dependency_scores") or {}
    per_axis = [scores.get(axis) for axis in ("trend", "vol", "width")]
    present = [s for s in per_axis if s is not None]
    if not present:
        return "insufficient_evidence"
    if max(present) >= REGIME_CONCENTRATED_THRESHOLD:
        return "emitted"
    return "below_threshold"


def build_intelligence_payload(ctx: RegimeSidecarBuildContext) -> dict[str, Any]:
    """Assemble the primary regime-intelligence payload."""
    entries_in: list[dict[str, Any]] = _registry_entries(ctx.registry_v2)
    width_map = ctx.width_distributions or {}

    diagnostics_entries: list[dict[str, Any]] = []
    for reg_entry in entries_in:
        candidate_id = str(reg_entry["candidate_id"])
        width_dist = width_map.get(candidate_id)
        diag = build_candidate_diagnostics(
            registry_v2_entry=reg_entry,
            regime_diagnostics=ctx.regime_diagnostics,
            width_distribution=width_dist,
        )
        diag["regime_gating_experiments"] = build_candidate_gating_experiments(
            candidate_diagnostics=diag,
        )
        diagnostics_entries.append(diag)

    diagnostics_entries.sort(key=lambda e: e["candidate_id"])
    summary = summarize_diagnostics(diagnostics_entries)
    summary["gate_rule_ids"] = gating_rule_ids()

    return {
        "schema_version": REGIME_INTELLIGENCE_SCHEMA_VERSION,
        "classifier_version": REGIME_CLASSIFIER_VERSION,
        "regime_layer_version": REGIME_LAYER_VERSION,
        "generated_at_utc": ctx.generated_at_utc,
        "run_id": ctx.run_id,
        "git_revision": ctx.git_revision,
        "summary": summary,
        "entries": diagnostics_entries,
    }


def build_overlay_payload(
    intelligence_payload: dict[str, Any],
    *,
    source_regime_diagnostics_present: bool,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Assemble the registry-shaped overlay payload."""
    entries_out: list[dict[str, Any]] = []
    for diag in intelligence_payload.get("entries") or []:
        concentrated_status = _regime_concentrated_status(diag)
        if not source_regime_diagnostics_present and concentrated_status == "insufficient_evidence":
            concentrated_status = "absent_sidecar"
        entries_out.append(
            {
                "candidate_id": diag["candidate_id"],
                "regime_assessment_status": diag["regime_assessment_status"],
                "regime_dependency_scores": diag.get("regime_dependency_scores"),
                "regime_concentrated_status": concentrated_status,
                "regime_gating_summary": {
                    "rule_ids": gating_rule_ids(),
                    # best_rule intentionally always null in v3.13 —
                    # no winner-picking.
                    "best_rule": None,
                },
            }
        )
    entries_out.sort(key=lambda e: e["candidate_id"])
    return {
        "schema_version": REGIME_OVERLAY_SCHEMA_VERSION,
        "regime_layer_version": REGIME_LAYER_VERSION,
        "classifier_version": REGIME_CLASSIFIER_VERSION,
        "generated_at_utc": generated_at_utc,
        "source_registry": SOURCE_REGISTRY_POSIX,
        "entries": entries_out,
    }


def build_and_write_regime_sidecars(
    ctx: RegimeSidecarBuildContext,
    *,
    intelligence_path: Path = REGIME_INTELLIGENCE_PATH,
    overlay_path: Path = REGIME_OVERLAY_PATH,
) -> dict[str, Path]:
    """Produce and write both v3.13 sidecars atomically.

    Returns a dict mapping logical artifact name to its written path.
    Paths are parameterized so tests can isolate writes.
    """
    intelligence = build_intelligence_payload(ctx)
    write_sidecar_atomic(intelligence_path, intelligence)
    overlay = build_overlay_payload(
        intelligence,
        source_regime_diagnostics_present=ctx.regime_diagnostics is not None,
        generated_at_utc=ctx.generated_at_utc,
    )
    write_sidecar_atomic(overlay_path, overlay)
    return {
        "regime_intelligence": intelligence_path,
        "regime_overlay": overlay_path,
    }


__all__ = [
    "REGIME_INTELLIGENCE_PATH",
    "REGIME_OVERLAY_PATH",
    "REGIME_INTELLIGENCE_SCHEMA_VERSION",
    "REGIME_OVERLAY_SCHEMA_VERSION",
    "RegimeSidecarBuildContext",
    "build_intelligence_payload",
    "build_overlay_payload",
    "build_and_write_regime_sidecars",
]
