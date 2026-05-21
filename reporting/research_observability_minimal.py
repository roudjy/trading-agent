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
MODULE_VERSION: Final[str] = "v3.15.18-minimal-reset-2026-05-21"
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
# Snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    routing_minimal_path: Path | None = None,
    sampling_minimal_path: Path | None = None,
    reason_records_artifact_dir: Path | None = None,
    kpi_doc_path: Path | None = None,
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
        "cross_family_subjects": {
            "total": len(surface_counts),
            "top_by_surface_count": {sid: cnt for sid, cnt in top_subjects},
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
    base = artifact_dir or ARTIFACT_DIR
    p = base / ARTIFACT_LATEST.name
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
