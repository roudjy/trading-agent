"""Minimal v3.15.18 Research Observability Expansion slice (reset deliverable).

Implements the **minimal slice** declared by queue item 4 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3, established by the
roadmap reset in PR #264 / #266, the research-quality sprint in
PR #267, the routing slice in PR #268, and the sampling slice in
PR #270).

This module is the **observability sibling** to
:mod:`reporting.intelligent_routing_minimal` and
:mod:`reporting.sampling_intelligence_minimal`. It is a pure,
deterministic, read-only aggregator over the artefacts those
slices already produce, plus the unified reason-records ledger.

Scope (binding, "minimal"):

* aggregate the currently-shipping observability surfaces
  (routing minimal digest, sampling minimal digest, unified
  reason-records manifest) into one operator-readable summary;
* report which subject_ids are present across multiple families
  (cross-family lineage at the read layer);
* enforce the operator-attention budget (OAB) via a
  ``visible_surfaces_per_campaign_cap`` and flag subjects that
  exceed it;
* surface the seven research-quality KPI definitions and the
  availability of any matching artefact (without computing the
  KPIs — that lands when the canonical KPI artefact exists);
* deterministic, pure, atomic-write digest;
* read-only CLI for operator inspection.

Out of scope (explicit; ADDENDUMS DEFERRED):

* no KG visualisation (Addendum 2 — DEFERRED);
* no retrieval debug surfaces (Addendum 2 — DEFERRED);
* no full lineage UI;
* no source-quality dashboards (Addendum 3 — DEFERRED);
* no candidate-promotion authority;
* no mutation routes — read-only only;
* no frontend business logic;
* no ``dashboard/dashboard.py`` modification — registration is a
  separate operator-driven governance-bootstrap PR (mirrors the
  ``register_*_routes`` pattern documented in
  :mod:`reporting.intelligent_routing_minimal`).

The module:

* is stdlib-only (no ``subprocess``, no ``gh``, no ``git``, no
  network);
* is pure / deterministic — two runs on identical inputs produce
  byte-identical output (modulo ``generated_at_utc``);
* never invokes the producer of any upstream artefact;
* writes only under ``logs/research_observability_minimal/`` (atomic
  allowlist substring);
* never imports execution-side modules;
* mutates no frozen contract.

CLI
---

::

    python -m reporting.research_observability_minimal --status
    python -m reporting.research_observability_minimal --no-write

There is no execute-safe mode; ``safe_to_execute`` is hard-coded
``false`` at the digest level.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import reason_records as _rr

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.18-ade-qre-007-operator-grade-2026-05-23"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "research_observability_minimal_digest"


# ---------------------------------------------------------------------------
# Heuristic constants (deterministic; pinned).
# ---------------------------------------------------------------------------


#: Operator-Attention Budget cap. A subject_id that appears in
#: more than this many reason-record families plus minimal-digest
#: presences is flagged ``attention_overflow``. Pinned by tests.
#: Three families (routing / sampling / scoring) + two minimal
#: digests = 5 max distinct surfaces today; cap of 3 leaves
#: headroom and is consistent with the KPI doctrine in
#: docs/governance/research_quality_kpis.md §3 (OAB).
DEFAULT_VISIBLE_SURFACES_PER_CAMPAIGN_CAP: Final[int] = 3

#: Top-N most-active subjects retained in the per-subject summary
#: block. Pinned to keep the operator surface bounded.
TOP_SUBJECTS_N: Final[int] = 16

#: Closed list of upstream artefact source identifiers surfaced by
#: this aggregator. Pinned for test specificity.
SOURCE_IDS: Final[tuple[str, ...]] = (
    "routing_minimal",
    "sampling_minimal",
    "reason_records",
    "research_quality_kpis_doc",
)

#: Closed list of KPI identifiers from
#: docs/governance/research_quality_kpis.md §3, in order. The
#: aggregator surfaces only the identifier set and availability;
#: numeric values are computed by a separate operator-driven
#: artefact (not part of the minimal v3.15.18 slice).
RESEARCH_QUALITY_KPI_IDS: Final[tuple[str, ...]] = (
    "TTFPRC",
    "OOS_DSR",
    "MASQ",
    "NMBR",
    "DZCR",
    "OAB",
    "CRSR",
)


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "research_observability_minimal"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"

#: Atomic-write allowlist substring.
_WRITE_PREFIX: Final[str] = "logs/research_observability_minimal/"

#: Upstream artefact paths (read-only).
ROUTING_MINIMAL_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "intelligent_routing_minimal" / "latest.json"
)
SAMPLING_MINIMAL_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "sampling_intelligence_minimal" / "latest.json"
)
REASON_RECORDS_MANIFEST: Final[Path] = (
    REPO_ROOT / "logs" / "reason_records" / "manifest.v1.json"
)
RESEARCH_QUALITY_KPIS_DOC: Final[Path] = (
    REPO_ROOT / "docs" / "governance" / "research_quality_kpis.md"
)
SCREENING_FAILURE_ATTRIBUTION_LATEST: Final[Path] = (
    REPO_ROOT / "research" / "screening_failure_attribution_latest.v1.json"
)
FAILURE_ACTION_MAPPING_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "failure_action_mapping_minimal" / "latest.json"
)
QRE_DATA_MANIFEST_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "qre_data_cache_manifest" / "latest.json"
)
QRE_SOURCE_QUALITY_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "qre_data_source_quality_readiness" / "latest.json"
)
QRE_RESEARCH_MEMORY_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_memory" / "latest.json"
)
QRE_RESEARCH_DIAGNOSTICS_LOOP_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_diagnostics_loop" / "latest.json"
)
ADE_QUEUE_DOC: Final[Path] = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "ade_queue_001_post_package_qre_ade_work_queue.md"
)
QRE_OPERATOR_SUMMARY_SOURCE_IDS: Final[tuple[str, ...]] = (
    "screening_failure_attribution",
    "failure_action_mapping",
    "data_manifest",
    "source_quality",
    "research_memory",
    "research_diagnostics_loop",
    "ade_queue",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "research_observability_minimal: refusing write outside "
            f"allowlist: {path!r}"
        )


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Source readers (pure)
# ---------------------------------------------------------------------------


def _read_routing_minimal(
    path: Path | None = None,
) -> dict[str, Any]:
    p = path or ROUTING_MINIMAL_LATEST
    data = _read_json(p)
    if data is None:
        return {
            "source_id": "routing_minimal",
            "available": False,
            "path": _rel(p),
            "note": "no latest snapshot",
        }
    counts = data.get("counts", {}) if isinstance(data, dict) else {}
    return {
        "source_id": "routing_minimal",
        "available": True,
        "path": _rel(p),
        "generated_at_utc": data.get("generated_at_utc"),
        "module_version": data.get("module_version"),
        "counts": {
            "total": int(counts.get("total", 0) or 0),
            "by_decision": dict(counts.get("by_decision") or {}),
        },
        "final_recommendation": data.get("final_recommendation"),
    }


def _read_sampling_minimal(
    path: Path | None = None,
) -> dict[str, Any]:
    p = path or SAMPLING_MINIMAL_LATEST
    data = _read_json(p)
    if data is None:
        return {
            "source_id": "sampling_minimal",
            "available": False,
            "path": _rel(p),
            "note": "no latest snapshot",
        }
    counts = data.get("counts", {}) if isinstance(data, dict) else {}
    return {
        "source_id": "sampling_minimal",
        "available": True,
        "path": _rel(p),
        "generated_at_utc": data.get("generated_at_utc"),
        "module_version": data.get("module_version"),
        "counts": {
            "total": int(counts.get("total", 0) or 0),
            "by_decision": dict(counts.get("by_decision") or {}),
            "actionable": int(counts.get("actionable", 0) or 0),
        },
        "final_recommendation": data.get("final_recommendation"),
    }


def _read_reason_records_manifest(
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    base = artifact_dir or (REPO_ROOT / "logs" / "reason_records")
    p = base / "manifest.v1.json"
    data = _read_json(p)
    if data is None:
        # Build an empty-but-deterministic projection from the
        # in-process reader so the aggregator stays useful even
        # before the manifest file lands.
        projection = _rr.collect_manifest(artifact_dir=base)
        return {
            "source_id": "reason_records",
            "available": False,
            "manifest_path": _rel(p),
            "total_records": int(projection.get("total_records", 0) or 0),
            "by_kind": dict(projection.get("by_kind") or {}),
            "by_decision": dict(projection.get("by_decision") or {}),
            "by_subject_id_top": dict(
                projection.get("by_subject_id_top") or {}
            ),
            "first_record_ts_utc": projection.get("first_record_ts_utc"),
            "last_record_ts_utc": projection.get("last_record_ts_utc"),
            "note": (
                "manifest file not yet materialised; reading counts "
                "from in-process projection"
            ),
        }
    return {
        "source_id": "reason_records",
        "available": True,
        "manifest_path": _rel(p),
        "total_records": int(data.get("total_records", 0) or 0),
        "by_kind": dict(data.get("by_kind") or {}),
        "by_decision": dict(data.get("by_decision") or {}),
        "by_subject_id_top": dict(data.get("by_subject_id_top") or {}),
        "first_record_ts_utc": data.get("first_record_ts_utc"),
        "last_record_ts_utc": data.get("last_record_ts_utc"),
    }


def _read_kpi_doc_status(path: Path | None = None) -> dict[str, Any]:
    p = path or RESEARCH_QUALITY_KPIS_DOC
    exists = p.is_file()
    return {
        "source_id": "research_quality_kpis_doc",
        "available": exists,
        "path": _rel(p),
        "kpi_ids": list(RESEARCH_QUALITY_KPI_IDS),
        "kpi_values_available": False,
        "note": (
            "Minimal v3.15.18 surfaces the KPI identifier set and "
            "doctrine pointer only; KPI numeric values require the "
            "canonical KPI artefact (separate operator-driven PR)."
        ),
    }


# ---------------------------------------------------------------------------
# Cross-family subject lineage + OAB enforcement
# ---------------------------------------------------------------------------


def _subject_surface_counts(
    *,
    reason_records_artifact_dir: Path | None = None,
) -> dict[str, int]:
    """Return a mapping ``subject_id -> distinct-surface-count``.

    The aggregator counts each ``decision_kind`` family that has at
    least one record for the subject as one surface. This is the
    OAB-relevant "visible surfaces per campaign" projection.
    """
    by_subject: dict[str, set[str]] = {}
    base = reason_records_artifact_dir
    for kind in _rr.DECISION_KINDS:
        for rec in _rr.read_kind(kind, artifact_dir=base):
            sid = rec.get("subject_id")
            if isinstance(sid, str) and sid:
                by_subject.setdefault(sid, set()).add(kind)
    return {sid: len(kinds) for sid, kinds in by_subject.items()}


def _enforce_oab(
    surface_counts: Mapping[str, int],
    *,
    cap: int,
) -> dict[str, Any]:
    overflow = sorted(
        sid for sid, count in surface_counts.items() if count > cap
    )
    near_cap = sorted(
        sid for sid, count in surface_counts.items() if count == cap
    )
    return {
        "visible_surfaces_per_campaign_cap": cap,
        "subjects_observed": len(surface_counts),
        "attention_overflow_subjects": overflow,
        "near_cap_subjects": near_cap,
        "attention_overflow_count": len(overflow),
        "near_cap_count": len(near_cap),
    }


# ---------------------------------------------------------------------------
# ADE-QRE operator-grade summary
# ---------------------------------------------------------------------------


def _read_qre_json_source(source_id: str, path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "source_id": source_id,
            "available": False,
            "status": "missing",
            "path": _rel(path),
            "fails_closed": True,
        }
    data = _read_json(path)
    if data is None:
        return {
            "source_id": source_id,
            "available": False,
            "status": "invalid",
            "path": _rel(path),
            "fails_closed": True,
        }
    return {
        "source_id": source_id,
        "available": True,
        "status": "present",
        "path": _rel(path),
        "fails_closed": False,
        "schema_version": data.get("schema_version"),
        "generated_at_utc": data.get("generated_at_utc"),
        "payload": data,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _screening_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "status": source.get("status", "missing"),
            "observation_count": 0,
            "unknown_observation_count": 0,
            "unknown_failure_rate": None,
            "attribution_depth_score": None,
            "primary_classification": None,
        }
    summary = payload.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    observation_count = _int(summary.get("observation_count"))
    unknown_count = _int(summary.get("unknown_observation_count"))
    return {
        "status": "ready" if observation_count else "not_ready",
        "observation_count": observation_count,
        "unknown_observation_count": unknown_count,
        "unknown_failure_rate": _ratio(unknown_count, observation_count),
        "attribution_depth_score": _attribution_depth_score(payload),
        "primary_classification": summary.get("primary_classification"),
        "recommended_next_action": payload.get("recommended_next_action"),
    }


def _attribution_depth_score(payload: Mapping[str, Any]) -> float | None:
    classifications = payload.get("classifications")
    if not isinstance(classifications, list):
        return None
    weighted_score = 0
    weighted_total = 0
    failure_actions_available = bool(payload.get("recommended_next_action"))
    for row in classifications:
        if not isinstance(row, Mapping):
            continue
        count = _int(row.get("count"))
        if count <= 0:
            continue
        classification = str(row.get("classification") or "")
        action_hint = row.get("action_hint")
        points = 0
        points += int(classification not in {"", "missing_diagnostics", "unknown_screening_failure"})
        points += int(bool(row.get("sources")))
        points += int(bool(row.get("raw_reasons")))
        points += int(isinstance(action_hint, Mapping) and bool(action_hint.get("action")))
        points += int(failure_actions_available)
        weighted_score += count * points
        weighted_total += count * 5
    return _ratio(weighted_score, weighted_total)


def _failure_action_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "status": source.get("status", "missing"),
            "total_failures": 0,
            "actionable_failure_count": 0,
            "actionable_failure_rate": None,
            "final_recommendation": None,
        }
    counts = payload.get("counts")
    counts = counts if isinstance(counts, Mapping) else {}
    total = _int(counts.get("total"))
    actionable = _int(counts.get("actionable_recommendations"))
    return {
        "status": "ready" if total else "not_ready",
        "total_failures": total,
        "actionable_failure_count": actionable,
        "actionable_failure_rate": _ratio(actionable, total),
        "final_recommendation": payload.get("final_recommendation"),
    }


def _readiness_metrics(
    manifest_source: Mapping[str, Any],
    source_quality_source: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_ready = _summary_bool(manifest_source, "research_ready")
    source_quality_ready = _summary_bool(source_quality_source, "research_ready")
    ready = manifest_ready and source_quality_ready
    return {
        "status": "ready" if ready else "not_ready",
        "research_ready": ready,
        "manifest": {
            "status": _readiness_status(manifest_source, manifest_ready),
            "research_ready": manifest_ready,
            "path": manifest_source.get("path"),
        },
        "source_quality": {
            "status": _readiness_status(source_quality_source, source_quality_ready),
            "research_ready": source_quality_ready,
            "path": source_quality_source.get("path"),
        },
    }


def _readiness_status(source: Mapping[str, Any], ready: bool) -> str:
    if not source.get("available"):
        return str(source.get("status") or "missing")
    return "ready" if ready else "not_ready"


def _summary_bool(source: Mapping[str, Any], key: str) -> bool:
    payload = source.get("payload")
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    return bool(isinstance(summary, Mapping) and summary.get(key))


def _memory_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "status": source.get("status", "missing"),
            "research_memory_ready": False,
            "prior_similar_failure_count": 0,
        }
    summary = payload.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    related = payload.get("related_failures")
    related_matches = (
        related.get("matches")
        if isinstance(related, Mapping) and isinstance(related.get("matches"), list)
        else []
    )
    failure_entries = [
        row
        for row in payload.get("entries", [])
        if isinstance(row, Mapping) and "failure" in (row.get("ontology_tags") or [])
    ]
    return {
        "status": "ready" if bool(summary.get("research_memory_ready")) else "not_ready",
        "research_memory_ready": bool(summary.get("research_memory_ready")),
        "entry_count": _int(summary.get("entry_count")),
        "prior_similar_failure_count": max(len(related_matches), len(failure_entries)),
        "related_failure_match_count": len(related_matches),
    }


def _diagnostics_loop_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "status": source.get("status", "missing"),
            "diagnostic_count": 0,
            "recommended_operator_step": "stop_collect_upstream_sidecars",
            "blocking_reasons": ["missing_research_diagnostics_loop"],
        }
    summary = payload.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    return {
        "status": str(summary.get("status") or "not_ready"),
        "diagnostic_count": _int(summary.get("diagnostic_count")),
        "recommended_operator_step": summary.get("recommended_operator_step"),
        "blocking_reasons": list(summary.get("blocking_reasons") or []),
        "primary_failure_classification": summary.get("primary_failure_classification"),
    }


def _read_queue_source(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "source_id": "ade_queue",
            "available": False,
            "status": "missing",
            "path": _rel(path),
            "fails_closed": True,
            "items": {},
        }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {
            "source_id": "ade_queue",
            "available": False,
            "status": "invalid",
            "path": _rel(path),
            "fails_closed": True,
            "items": {},
        }
    return {
        "source_id": "ade_queue",
        "available": True,
        "status": "present",
        "path": _rel(path),
        "fails_closed": False,
        "items": _parse_queue_statuses(text),
    }


def _parse_queue_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- queue id: `") and line.endswith("`"):
            current = line.removeprefix("- queue id: `").removesuffix("`")
            continue
        if current and line.startswith("- status: `") and line.endswith("`"):
            statuses[current] = line.removeprefix("- status: `").removesuffix("`")
            current = None
    return statuses


def _governance_blockers(queue_source: Mapping[str, Any]) -> dict[str, Any]:
    items = queue_source.get("items")
    items = items if isinstance(items, Mapping) else {}
    blocking_statuses = {"blocked", "operator_review"}
    blockers = [
        {"queue_item": queue_id, "status": status}
        for queue_id, status in sorted(items.items())
        if status in blocking_statuses
    ]
    return {
        "status": "blocked" if blockers else "clear",
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def _qre_source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in (
            "source_id",
            "available",
            "status",
            "path",
            "fails_closed",
            "schema_version",
            "generated_at_utc",
        )
        if key in source
    }


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _collect_qre_operator_summary(
    *,
    screening_failure_attribution_path: Path | None = None,
    failure_action_mapping_path: Path | None = None,
    data_manifest_path: Path | None = None,
    source_quality_path: Path | None = None,
    research_memory_path: Path | None = None,
    research_diagnostics_loop_path: Path | None = None,
    ade_queue_doc_path: Path | None = None,
) -> dict[str, Any]:
    sources = {
        "screening_failure_attribution": _read_qre_json_source(
            "screening_failure_attribution",
            screening_failure_attribution_path or SCREENING_FAILURE_ATTRIBUTION_LATEST,
        ),
        "failure_action_mapping": _read_qre_json_source(
            "failure_action_mapping",
            failure_action_mapping_path or FAILURE_ACTION_MAPPING_LATEST,
        ),
        "data_manifest": _read_qre_json_source(
            "data_manifest",
            data_manifest_path or QRE_DATA_MANIFEST_LATEST,
        ),
        "source_quality": _read_qre_json_source(
            "source_quality",
            source_quality_path or QRE_SOURCE_QUALITY_LATEST,
        ),
        "research_memory": _read_qre_json_source(
            "research_memory",
            research_memory_path or QRE_RESEARCH_MEMORY_LATEST,
        ),
        "research_diagnostics_loop": _read_qre_json_source(
            "research_diagnostics_loop",
            research_diagnostics_loop_path or QRE_RESEARCH_DIAGNOSTICS_LOOP_LATEST,
        ),
        "ade_queue": _read_queue_source(ade_queue_doc_path or ADE_QUEUE_DOC),
    }
    screening = _screening_metrics(sources["screening_failure_attribution"])
    actions = _failure_action_metrics(sources["failure_action_mapping"])
    data = _readiness_metrics(sources["data_manifest"], sources["source_quality"])
    memory = _memory_metrics(sources["research_memory"])
    diagnostics = _diagnostics_loop_metrics(sources["research_diagnostics_loop"])
    governance = _governance_blockers(sources["ade_queue"])
    available_count = sum(1 for source in sources.values() if source.get("available"))
    missing = [
        source_id
        for source_id, source in sorted(sources.items())
        if not bool(source.get("available"))
    ]
    return {
        "source_ids": list(QRE_OPERATOR_SUMMARY_SOURCE_IDS),
        "available_source_count": available_count,
        "missing_sources": missing,
        "unknown_failure_rate": screening["unknown_failure_rate"],
        "actionable_failure_rate": actions["actionable_failure_rate"],
        "attribution_depth_score": screening["attribution_depth_score"],
        "screening_failure_attribution": screening,
        "failure_action_mapping": actions,
        "data_readiness": data,
        "prior_similar_failures": memory,
        "diagnostics_loop": diagnostics,
        "governance_blockers": governance,
        "operator_state": _operator_state(
            available_count=available_count,
            governance=governance,
            diagnostics=diagnostics,
        ),
        "sources": {source_id: _qre_source_summary(source) for source_id, source in sources.items()},
        "safety_invariants": {
            "read_only": True,
            "dashboard_mutation_routes": False,
            "approval_buttons": False,
            "auto_execute_controls": False,
            "mutates_campaign_queue": False,
            "mutates_routing": False,
            "mutates_strategy_or_presets": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _operator_state(
    *,
    available_count: int,
    governance: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
) -> str:
    if available_count <= 1:
        return "missing_upstream_evidence"
    if governance.get("status") == "blocked":
        return "operator_gate_visible"
    if diagnostics.get("status") == "ready":
        return "operator_review_available"
    return "operator_review_limited_by_missing_diagnostics"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    routing_minimal_path: Path | None = None,
    sampling_minimal_path: Path | None = None,
    reason_records_artifact_dir: Path | None = None,
    kpi_doc_path: Path | None = None,
    screening_failure_attribution_path: Path | None = None,
    failure_action_mapping_path: Path | None = None,
    data_manifest_path: Path | None = None,
    source_quality_path: Path | None = None,
    research_memory_path: Path | None = None,
    research_diagnostics_loop_path: Path | None = None,
    ade_queue_doc_path: Path | None = None,
    visible_surfaces_per_campaign_cap: int = (
        DEFAULT_VISIBLE_SURFACES_PER_CAMPAIGN_CAP
    ),
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    """Pure, deterministic aggregation over the upstream artefacts.

    Returns a snapshot dict with closed top-level keys. Empty /
    missing sources never raise; they yield ``available: false``
    entries with deterministic placeholders.
    """
    ts = frozen_utc or _utcnow()

    routing = _read_routing_minimal(routing_minimal_path)
    sampling = _read_sampling_minimal(sampling_minimal_path)
    reason_records = _read_reason_records_manifest(
        reason_records_artifact_dir
    )
    kpi = _read_kpi_doc_status(kpi_doc_path)

    surface_counts = _subject_surface_counts(
        reason_records_artifact_dir=reason_records_artifact_dir
    )
    oab = _enforce_oab(
        surface_counts, cap=visible_surfaces_per_campaign_cap
    )
    qre_operator_summary = _collect_qre_operator_summary(
        screening_failure_attribution_path=screening_failure_attribution_path,
        failure_action_mapping_path=failure_action_mapping_path,
        data_manifest_path=data_manifest_path,
        source_quality_path=source_quality_path,
        research_memory_path=research_memory_path,
        research_diagnostics_loop_path=research_diagnostics_loop_path,
        ade_queue_doc_path=ade_queue_doc_path,
    )

    # Top-N subjects by surface count (deterministic order).
    top_subjects = sorted(
        surface_counts.items(), key=lambda kv: (-kv[1], kv[0])
    )[:TOP_SUBJECTS_N]

    # Aggregate availability + final_recommendation surfaces.
    sources_available = sum(
        1 for s in (routing, sampling, reason_records, kpi) if s["available"]
    )

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "operator_attention_budget": oab,
        "sources": {
            "routing_minimal": routing,
            "sampling_minimal": sampling,
            "reason_records": reason_records,
            "research_quality_kpis_doc": kpi,
        },
        "qre_operator_summary": qre_operator_summary,
        "cross_family_subjects": {
            "total": len(surface_counts),
            "top_by_surface_count": dict(top_subjects),
        },
        "final_recommendation": (
            "operator_review_available"
            if sources_available > 0
            else "nothing_to_review"
        ),
        "note": (
            "Minimal v3.15.18 reset slice. Read-only aggregator over "
            "routing / sampling / reason-records / KPI-doctrine "
            "surfaces; no KG visualisation, no retrieval debug "
            "surfaces, no full lineage UI, no source-quality "
            "dashboards (Addendums 2/3 are deferred)."
        ),
    }
    return snapshot


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    """Atomic write of ``latest.json`` + timestamped copy +
    history append. Mirrors
    ``reporting.sampling_intelligence_minimal``.
    """
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    json_now = base / f"{ts}.json"
    json_latest = base / ARTIFACT_LATEST.name
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    _validate_write_target(json_now)
    _validate_write_target(json_latest)
    _validate_write_target(history)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot(
    *, artifact_dir: Path | None = None
) -> dict[str, Any] | None:
    p = (artifact_dir / ARTIFACT_LATEST.name) if artifact_dir else ARTIFACT_LATEST
    return _read_json(p)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.research_observability_minimal",
        description=(
            "Minimal v3.15.18 Research Observability Expansion reset "
            "slice — deterministic projection. The CLI never executes "
            "anything; safe_to_execute is hard-coded false."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Inspect only; do not write any artefact.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Read the latest digest without re-running.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=("dry-run",),
        help="Only dry-run is allowed.",
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin the timestamp for deterministic tests.",
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "module_version": MODULE_VERSION,
                        "final_recommendation": "not_available",
                        "note": "no latest snapshot",
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
            return 0
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    snap = collect_snapshot(frozen_utc=args.frozen_utc)

    if not args.no_write:
        out = write_outputs(snap)
        snap["_artifact_paths"] = out

    print(json.dumps(snap, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
