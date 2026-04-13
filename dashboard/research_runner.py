from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dashboard import research_artifacts
from research.run_state import RunStateStore

BASE_DIR = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _build_observations(
    *,
    state_artifact: dict[str, Any],
    repair_result: dict[str, Any],
) -> dict[str, Any]:
    artifact = state_artifact.get("artifact")
    status = artifact.get("status") if isinstance(artifact, dict) else None
    return {
        "authoritative_status": status,
        "pid_live": repair_result.get("pid_live"),
        "heartbeat_age_seconds": repair_result.get("heartbeat_age_seconds"),
        "stale_state_repaired": bool(repair_result.get("repaired")),
        "repair_reason": repair_result.get("repair_reason"),
    }


def build_run_status_response(*, now: datetime | None = None) -> dict[str, Any]:
    lifecycle = RunStateStore(
        state_path=research_artifacts.RUN_STATE_PATH,
        history_root=research_artifacts.RUN_STATE_PATH.parent / "history",
    )
    repair_result = lifecycle.repair_stale_run()
    state_artifact = research_artifacts.load_run_state_artifact()
    progress_artifact = research_artifacts.load_run_progress_artifact()
    warnings: list[str] = []
    if repair_result.get("repaired"):
        warnings.append(
            f"Recovered stale running state via {repair_result['repair_reason']}."
        )
    return {
        "run_state": state_artifact,
        "run_progress": progress_artifact,
        "dashboard_observations": _build_observations(
            state_artifact=state_artifact,
            repair_result=repair_result,
        ),
        "warnings": warnings,
        "as_of_utc": (now or _utc_now()).isoformat(),
    }


def launch_research_run(*, now: datetime | None = None) -> tuple[dict[str, Any], int]:
    lifecycle = RunStateStore(
        state_path=research_artifacts.RUN_STATE_PATH,
        history_root=research_artifacts.RUN_STATE_PATH.parent / "history",
    )
    repair_result = lifecycle.repair_stale_run()
    state_artifact = research_artifacts.load_run_state_artifact()
    state_payload = state_artifact.get("artifact")
    warnings: list[str] = []
    if repair_result.get("repaired"):
        warnings.append(
            f"Recovered stale running state via {repair_result['repair_reason']}."
        )

    if (
        state_artifact.get("artifact_state") == "valid"
        and isinstance(state_payload, dict)
        and state_payload.get("status") == "running"
    ):
        return (
            {
                "accepted": False,
                "launch_state": "blocked_active_run",
                "observations": _build_observations(
                    state_artifact=state_artifact,
                    repair_result=repair_result,
                ),
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
                "observations": _build_observations(
                    state_artifact=state_artifact,
                    repair_result=repair_result,
                ),
                "warnings": warnings,
                "error": str(exc),
            },
            500,
        )

    return (
        {
            "accepted": True,
            "launch_state": "started",
            "pid": process.pid,
            "observations": _build_observations(
                state_artifact=state_artifact,
                repair_result=repair_result,
            ),
            "warnings": warnings,
            "launched_at_utc": (now or _utc_now()).isoformat(),
        },
        202,
    )
