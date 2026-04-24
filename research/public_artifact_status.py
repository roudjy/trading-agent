"""v3.15.1 public-artifact freshness status.

Adjacent artifact that tracks whether the current ``research_latest.json`` /
``strategy_matrix.csv`` reflect the most recent attempted run, or whether
they are stale because the latest run was degenerate / errored and therefore
skipped the public write.

Why this sidecar exists
-----------------------
The public contracts (``research/research_latest.json``,
``research/strategy_matrix.csv``) are byte-frozen. When a run ends in a
degenerate state (``preflight_no_evaluable_pairs`` /
``screening_no_survivors`` / ``validation_no_survivors`` /
``postrun_no_oos_daily_returns``) the public writes are deliberately
skipped so the existing artifacts are *not* overwritten. That preserves the
last-good state but also means dashboards can display **stale** data
without any visible marker.

``empty_run_diagnostics_latest.v1.json`` already carries
``public_output_status.public_outputs_written=False`` but only when a run
actually reaches the degenerate path. It is not a first-class freshness
surface, it isn't written on every run, and the schema isn't optimized for
API consumption.

This module adds a small, explicit sidecar — written after **every** run
attempt, success and degenerate — that answers three operational questions:

1. What was the latest attempted run? (run_id, preset, outcome, failure stage)
2. When was the latest successful public artifact write? (may be older)
3. Are the public artifacts currently stale? If so, since when and why?

The sidecar is intentionally small and adjacent. Frozen contracts are not
touched. Dashboards / API endpoints consume it; banners render only when
``public_artifacts_stale=True``.

Schema v1.0
-----------

    {
      "schema_version": "1.0",
      "public_artifact_status_version": "v0.1",
      "generated_at_utc": str,
      "last_attempted_run": {
        "run_id": str,
        "attempted_at_utc": str,
        "preset": str | None,
        "outcome": "success" | "degenerate" | "error",
        "failure_stage": str | None
      },
      "last_public_artifact_write": {
        "run_id": str | None,
        "written_at_utc": str | None,
        "preset": str | None
      },
      "last_public_write_age_seconds": int | None,
      "public_artifacts_stale": bool,
      "stale_reason": str | None,
      "stale_since_utc": str | None
    }

Stale reason codes (closed vocabulary):
- ``degenerate_run_no_public_write`` — latest attempt ended in a named
  degenerate failure stage.
- ``error_no_public_write`` — latest attempt ended in an unexpected error
  before the public write completed.
- ``public_write_never_occurred`` — no prior public write exists on disk.

A missing status file is **not** modeled as ``stale=False``. The API
endpoint surfaces missing-state explicitly with
``state="absent"`` and ``public_artifacts_stale=None`` so dashboards can
differentiate "we know it's fresh" from "we don't know".
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from research._sidecar_io import (
    serialize_canonical,
    write_sidecar_atomic,
)

PUBLIC_ARTIFACT_STATUS_PATH = Path(
    "research/public_artifact_status_latest.v1.json"
)
PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION = "1.0"
PUBLIC_ARTIFACT_STATUS_VERSION = "v0.1"

Outcome = Literal["success", "degenerate", "error"]

STALE_REASON_DEGENERATE = "degenerate_run_no_public_write"
STALE_REASON_ERROR = "error_no_public_write"
STALE_REASON_NEVER = "public_write_never_occurred"
_VALID_STALE_REASONS = frozenset(
    {STALE_REASON_DEGENERATE, STALE_REASON_ERROR, STALE_REASON_NEVER}
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _age_seconds(written_at: str | None, now: datetime) -> int | None:
    parsed = _parse_iso(written_at)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = now - parsed
    return max(int(delta.total_seconds()), 0)


def _empty_write_block() -> dict[str, Any]:
    return {"run_id": None, "written_at_utc": None, "preset": None}


def read_public_artifact_status(
    path: Path = PUBLIC_ARTIFACT_STATUS_PATH,
) -> dict[str, Any] | None:
    """Read the current status sidecar; return ``None`` if missing / invalid."""
    if not path.exists():
        return None
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def build_public_artifact_status(
    *,
    outcome: Outcome,
    run_id: str,
    attempted_at_utc: str,
    preset: str | None,
    failure_stage: str | None = None,
    existing: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the v1.0 status payload from the current run + prior state.

    Success-run: both ``last_attempted_run`` and ``last_public_artifact_write``
    are refreshed to the current run; ``stale=False``.

    Degenerate / error-run: ``last_attempted_run`` is refreshed;
    ``last_public_artifact_write`` is preserved from the prior status file
    (or left null if no prior write exists); ``stale=True``;
    ``stale_since_utc`` is preserved across consecutive stale runs.
    """
    if outcome not in ("success", "degenerate", "error"):
        raise ValueError(f"invalid outcome: {outcome!r}")

    now = now or _utc_now()
    generated_at = _iso(now)

    attempted_block = {
        "run_id": str(run_id),
        "attempted_at_utc": attempted_at_utc,
        "preset": preset,
        "outcome": outcome,
        "failure_stage": failure_stage,
    }

    prior_write = None
    prior_stale_since = None
    if isinstance(existing, dict):
        prior_write = existing.get("last_public_artifact_write")
        prior_stale_since = existing.get("stale_since_utc")

    if outcome == "success":
        write_block = {
            "run_id": str(run_id),
            "written_at_utc": attempted_at_utc,
            "preset": preset,
        }
        age_seconds = _age_seconds(write_block["written_at_utc"], now)
        return {
            "schema_version": PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION,
            "public_artifact_status_version": PUBLIC_ARTIFACT_STATUS_VERSION,
            "generated_at_utc": generated_at,
            "last_attempted_run": attempted_block,
            "last_public_artifact_write": write_block,
            "last_public_write_age_seconds": age_seconds,
            "public_artifacts_stale": False,
            "stale_reason": None,
            "stale_since_utc": None,
        }

    if isinstance(prior_write, dict) and prior_write.get("run_id"):
        write_block = {
            "run_id": prior_write.get("run_id"),
            "written_at_utc": prior_write.get("written_at_utc"),
            "preset": prior_write.get("preset"),
        }
    else:
        write_block = _empty_write_block()

    if write_block["run_id"] is None:
        stale_reason = STALE_REASON_NEVER
    elif outcome == "error":
        stale_reason = STALE_REASON_ERROR
    else:
        stale_reason = STALE_REASON_DEGENERATE

    if isinstance(prior_stale_since, str) and prior_stale_since.strip():
        stale_since_utc = prior_stale_since
    else:
        stale_since_utc = attempted_at_utc

    age_seconds = _age_seconds(write_block["written_at_utc"], now)

    return {
        "schema_version": PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION,
        "public_artifact_status_version": PUBLIC_ARTIFACT_STATUS_VERSION,
        "generated_at_utc": generated_at,
        "last_attempted_run": attempted_block,
        "last_public_artifact_write": write_block,
        "last_public_write_age_seconds": age_seconds,
        "public_artifacts_stale": True,
        "stale_reason": stale_reason,
        "stale_since_utc": stale_since_utc,
    }


def write_public_artifact_status(
    payload: dict[str, Any],
    path: Path = PUBLIC_ARTIFACT_STATUS_PATH,
) -> Path:
    """Validate + atomically write the status payload."""
    if payload.get("schema_version") != PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION:
        raise ValueError(
            "schema_version mismatch: "
            f"expected {PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION!r}, "
            f"got {payload.get('schema_version')!r}"
        )
    stale_reason = payload.get("stale_reason")
    if stale_reason is not None and stale_reason not in _VALID_STALE_REASONS:
        raise ValueError(f"invalid stale_reason: {stale_reason!r}")
    write_sidecar_atomic(path, payload)
    return path


def serialize_public_artifact_status(payload: dict[str, Any]) -> str:
    """Canonical string form — exposed so tests can diff without disk."""
    return serialize_canonical(payload)


__all__ = [
    "PUBLIC_ARTIFACT_STATUS_PATH",
    "PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION",
    "PUBLIC_ARTIFACT_STATUS_VERSION",
    "STALE_REASON_DEGENERATE",
    "STALE_REASON_ERROR",
    "STALE_REASON_NEVER",
    "build_public_artifact_status",
    "read_public_artifact_status",
    "serialize_public_artifact_status",
    "write_public_artifact_status",
]
