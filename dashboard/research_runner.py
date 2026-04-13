from __future__ import annotations

import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
STALE_HEARTBEAT_SECONDS = 300

_RUN_LOCK = threading.Lock()
_ACTIVE_PROCESS: subprocess.Popen[str] | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _current_process() -> subprocess.Popen[str] | None:
    with _RUN_LOCK:
        process = _ACTIVE_PROCESS
        if process is not None and process.poll() is not None:
            return None
        return process


def local_process_active() -> bool:
    return _current_process() is not None


def dashboard_observations(
    run_status_artifact: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    artifact = run_status_artifact.get("artifact")
    heartbeat_at = (
        _parse_iso_datetime(artifact.get("last_updated_at_utc"))
        if isinstance(artifact, dict)
        else None
    )
    age_seconds = None
    if heartbeat_at is not None:
        age_seconds = max(0, int(round(((now or _utc_now()) - heartbeat_at).total_seconds())))

    artifact_status = artifact.get("status") if isinstance(artifact, dict) else None
    local_active = local_process_active()
    recent_signal = (
        artifact_status == "running"
        and age_seconds is not None
        and age_seconds <= STALE_HEARTBEAT_SECONDS
    )
    stale_signal = (
        artifact_status == "running"
        and not local_active
        and (age_seconds is None or age_seconds > STALE_HEARTBEAT_SECONDS)
    )
    return {
        "local_process_active": local_active,
        "artifact_status": artifact_status,
        "progress_heartbeat_age_seconds": age_seconds,
        "recent_progress_signal": recent_signal,
        "stale_progress_signal": stale_signal,
        "stale_heartbeat_threshold_seconds": STALE_HEARTBEAT_SECONDS,
    }


def build_run_status_response(
    run_status_artifact: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    observations = dashboard_observations(run_status_artifact, now=now)
    warnings: list[str] = []
    if observations["stale_progress_signal"]:
        warnings.append(
            "Progress artifact reports running but no active local process was detected and the heartbeat appears stale."
        )
    return {
        **run_status_artifact,
        "dashboard_observations": observations,
        "warnings": warnings,
    }


def launch_research_run(
    run_status_artifact: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], int]:
    observations = dashboard_observations(run_status_artifact, now=now)
    warnings: list[str] = []

    if observations["local_process_active"] or observations["recent_progress_signal"]:
        return (
            {
                "accepted": False,
                "launch_state": "blocked_active_run",
                "observations": observations,
                "warnings": warnings,
            },
            409,
        )

    if observations["stale_progress_signal"]:
        warnings.append(
            "Stale running progress signal detected. Review run_progress_latest.v1.json before retrying."
        )
        return (
            {
                "accepted": False,
                "launch_state": "blocked_stale_signal",
                "observations": observations,
                "warnings": warnings,
            },
            409,
        )

    try:
        process = subprocess.Popen(
            [sys.executable, "research/run_research.py"],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return (
            {
                "accepted": False,
                "launch_state": "launch_failed",
                "observations": observations,
                "warnings": warnings,
                "error": str(exc),
            },
            500,
        )

    with _RUN_LOCK:
        global _ACTIVE_PROCESS
        _ACTIVE_PROCESS = process

    return (
        {
            "accepted": True,
            "launch_state": "started",
            "pid": process.pid,
            "observations": dashboard_observations(run_status_artifact, now=now),
            "warnings": warnings,
        },
        202,
    )
