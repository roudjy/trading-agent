"""v3.10 run-meta sidecar — adjacent artifact next to the frozen contract.

The public output contracts (``research_latest.json`` + ``strategy_matrix.csv``)
are byte-identical to pre-v3.10; we are NOT adding new fields there. The
per-run preset metadata, completion timestamp, candidate summary, and top
rejection reasons all live in this new sidecar at
``research/run_meta_latest.v1.json``.

Schema v1.0 (stable within the v3.10 release line):

    {
      "schema_version": "1.0",
      "run_id": str,
      "preset_name": str | None,
      "preset_hypothesis": str | None,
      "preset_universe": [str, ...],
      "preset_bundle": [str, ...],
      "preset_optional_bundle": [str, ...],
      "preset_status": str | None,
      "diagnostic_only": bool,
      "excluded_from_candidate_promotion": bool,
      "screening_mode": str | None,
      "cost_mode": str | None,
      "regime_filter": str | None,
      "regime_modes": [str, ...],
      "started_at_utc": str,
      "completed_at_utc": str | None,
      "git_revision": str | None,
      "config_hash": str | None,
      "candidate_summary": {
        "raw": int, "screened": int, "validated": int,
        "rejected": int, "promoted": int
      },
      "top_rejection_reasons": [{"reason": str, "count": int}, ...],
      "artifact_paths": {
        "run_state": str, "run_candidates": str,
        "run_manifest": str, "report_markdown": str, "report_json": str
      }
    }

Consumers (promotion layer, report agent, dashboard API, researchctl history)
treat this sidecar as the source of truth for preset metadata. If the file
is missing, the safe default for any exclusion flag is ``True`` — a run
without metadata must never be silently promoted. See ADR-011 §9.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.presets import ResearchPreset

RUN_META_PATH = Path("research/run_meta_latest.v1.json")
RUN_META_SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_run_meta_payload(
    *,
    run_id: str,
    preset: ResearchPreset | None,
    started_at_utc: str,
    completed_at_utc: str | None,
    git_revision: str | None,
    config_hash: str | None,
    candidate_summary: dict[str, int] | None,
    top_rejection_reasons: list[dict[str, Any]] | None,
    artifact_paths: dict[str, str] | None,
) -> dict[str, Any]:
    preset_fields: dict[str, Any]
    if preset is None:
        preset_fields = {
            "preset_name": None,
            "preset_hypothesis": None,
            "preset_universe": [],
            "preset_bundle": [],
            "preset_optional_bundle": [],
            "preset_status": None,
            "diagnostic_only": False,
            "excluded_from_candidate_promotion": True,
            "screening_mode": None,
            "cost_mode": None,
            "regime_filter": None,
            "regime_modes": [],
        }
    else:
        preset_fields = {
            "preset_name": preset.name,
            "preset_hypothesis": preset.hypothesis,
            "preset_universe": list(preset.universe),
            "preset_bundle": list(preset.bundle),
            "preset_optional_bundle": list(preset.optional_bundle),
            "preset_status": preset.status,
            "diagnostic_only": preset.diagnostic_only,
            "excluded_from_candidate_promotion": preset.excluded_from_candidate_promotion,
            "screening_mode": preset.screening_mode,
            "cost_mode": preset.cost_mode,
            "regime_filter": preset.regime_filter,
            "regime_modes": list(preset.regime_modes),
        }

    return {
        "schema_version": RUN_META_SCHEMA_VERSION,
        "run_id": str(run_id),
        **preset_fields,
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "git_revision": git_revision,
        "config_hash": config_hash,
        "candidate_summary": dict(candidate_summary or {
            "raw": 0, "screened": 0, "validated": 0,
            "rejected": 0, "promoted": 0,
        }),
        "top_rejection_reasons": list(top_rejection_reasons or []),
        "artifact_paths": dict(artifact_paths or {}),
    }


def write_run_meta_sidecar(payload: dict[str, Any], path: Path = RUN_META_PATH) -> Path:
    """Atomically write the sidecar to disk; return the written path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def read_run_meta_sidecar(path: Path = RUN_META_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_run_excluded_from_promotion(path: Path = RUN_META_PATH) -> bool:
    """Safe-default promotion-exclusion check.

    Returns True when the sidecar is missing, unreadable, or explicitly
    marks the run as diagnostic / promotion-excluded. A missing sidecar
    MUST block promotion (see ADR-011 §9).
    """
    payload = read_run_meta_sidecar(path)
    if payload is None:
        return True
    if bool(payload.get("excluded_from_candidate_promotion", True)):
        return True
    if bool(payload.get("diagnostic_only", False)):
        return True
    return False


def summarize_candidates(
    *,
    raw: int = 0,
    screened: int = 0,
    validated: int = 0,
    rejected: int = 0,
    promoted: int = 0,
) -> dict[str, int]:
    return {
        "raw": int(raw),
        "screened": int(screened),
        "validated": int(validated),
        "rejected": int(rejected),
        "promoted": int(promoted),
    }


def rollup_rejection_reasons(
    rows: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Count non-empty ``reden`` values across output rows."""
    counter: Counter[str] = Counter()
    for row in rows:
        reden = row.get("reden") if isinstance(row, dict) else None
        if isinstance(reden, str) and reden.strip():
            counter[reden.strip()] += 1
    top = counter.most_common(limit)
    return [{"reason": reason, "count": int(count)} for reason, count in top]


__all__ = [
    "RUN_META_PATH",
    "RUN_META_SCHEMA_VERSION",
    "build_run_meta_payload",
    "is_run_excluded_from_promotion",
    "read_run_meta_sidecar",
    "rollup_rejection_reasons",
    "summarize_candidates",
    "write_run_meta_sidecar",
]
