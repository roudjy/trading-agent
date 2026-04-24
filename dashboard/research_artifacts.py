from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
RUN_STATE_PATH = BASE_DIR / "research" / "run_state.v1.json"
RUN_PROGRESS_PATH = BASE_DIR / "research" / "run_progress_latest.v1.json"
RUN_MANIFEST_PATH = BASE_DIR / "research" / "run_manifest_latest.v1.json"
RUN_CAMPAIGN_PATH = BASE_DIR / "research" / "run_campaign_latest.v1.json"
RUN_CAMPAIGN_PROGRESS_PATH = BASE_DIR / "research" / "run_campaign_progress_latest.v1.json"
RESEARCH_LATEST_PATH = BASE_DIR / "research" / "research_latest.json"
EMPTY_RUN_DIAGNOSTICS_PATH = (
    BASE_DIR / "research" / "empty_run_diagnostics_latest.v1.json"
)
UNIVERSE_SNAPSHOT_PATH = BASE_DIR / "research" / "universe_snapshot_latest.v1.json"
PUBLIC_ARTIFACT_STATUS_PATH = (
    BASE_DIR / "research" / "public_artifact_status_latest.v1.json"
)


def _path_label(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def _modified_at_utc(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return None


def _artifact_state_for_payload(payload: Any) -> str:
    if payload is None:
        return "empty"
    if isinstance(payload, (dict, list, str)) and len(payload) == 0:
        return "empty"
    return "valid"


def load_json_artifact(path: Path) -> dict[str, Any]:
    response: dict[str, Any] = {
        "artifact_path": _path_label(path),
        "artifact_state": "absent",
        "artifact_available": False,
        "artifact_error": None,
        "artifact_modified_at_utc": None,
        "artifact": None,
    }

    if not path.exists():
        return response

    response["artifact_modified_at_utc"] = _modified_at_utc(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        response["artifact_state"] = "unreadable"
        response["artifact_error"] = str(exc)
        return response

    if raw.strip() == "":
        response["artifact_state"] = "empty"
        return response

    try:
        payload = json.loads(raw)
    except JSONDecodeError as exc:
        response["artifact_state"] = "invalid_json"
        response["artifact_error"] = str(exc)
        return response

    response["artifact"] = payload
    response["artifact_state"] = _artifact_state_for_payload(payload)
    response["artifact_available"] = response["artifact_state"] == "valid"
    return response


def load_run_progress_artifact() -> dict[str, Any]:
    return load_json_artifact(RUN_PROGRESS_PATH)


def load_run_state_artifact() -> dict[str, Any]:
    return load_json_artifact(RUN_STATE_PATH)


def load_run_manifest_artifact() -> dict[str, Any]:
    return load_json_artifact(RUN_MANIFEST_PATH)


def load_run_campaign_artifact() -> dict[str, Any]:
    return load_json_artifact(RUN_CAMPAIGN_PATH)


def load_run_campaign_progress_artifact() -> dict[str, Any]:
    return load_json_artifact(RUN_CAMPAIGN_PROGRESS_PATH)


def load_research_latest_artifact() -> dict[str, Any]:
    return load_json_artifact(RESEARCH_LATEST_PATH)


def load_empty_run_diagnostics_artifact() -> dict[str, Any]:
    return load_json_artifact(EMPTY_RUN_DIAGNOSTICS_PATH)


def load_universe_snapshot_artifact() -> dict[str, Any]:
    return load_json_artifact(UNIVERSE_SNAPSHOT_PATH)


def load_public_artifact_status(
    path: Path | None = None,
) -> dict[str, Any]:
    """Freshness surface for research_latest.json / strategy_matrix.csv.

    Missing status file is reported as an explicit ``state="absent"``
    payload with ``public_artifacts_stale=None`` — unknown, not false.
    This lets dashboards differentiate "verified fresh" from
    "no signal yet" instead of defaulting to an implicit ok.

    The default path is resolved at call-time (not at function-def
    time) so tests can monkeypatch ``PUBLIC_ARTIFACT_STATUS_PATH``
    without rebinding the function.
    """
    if path is None:
        path = PUBLIC_ARTIFACT_STATUS_PATH
    if not path.exists():
        return {
            "artifact_path": _path_label(path),
            "state": "absent",
            "artifact_modified_at_utc": None,
            "public_artifacts_stale": None,
            "stale_reason": None,
            "stale_since_utc": None,
            "last_attempted_run": None,
            "last_public_artifact_write": None,
            "last_public_write_age_seconds": None,
            "schema_version": None,
            "public_artifact_status_version": None,
        }

    raw_artifact = load_json_artifact(path)
    payload = raw_artifact.get("artifact")
    if not isinstance(payload, dict):
        return {
            "artifact_path": _path_label(path),
            "state": raw_artifact.get("artifact_state", "invalid_json"),
            "artifact_modified_at_utc": raw_artifact.get(
                "artifact_modified_at_utc"
            ),
            "public_artifacts_stale": None,
            "stale_reason": None,
            "stale_since_utc": None,
            "last_attempted_run": None,
            "last_public_artifact_write": None,
            "last_public_write_age_seconds": None,
            "schema_version": None,
            "public_artifact_status_version": None,
            "artifact_error": raw_artifact.get("artifact_error"),
        }

    return {
        "artifact_path": _path_label(path),
        "state": "valid",
        "artifact_modified_at_utc": raw_artifact.get(
            "artifact_modified_at_utc"
        ),
        "schema_version": payload.get("schema_version"),
        "public_artifact_status_version": payload.get(
            "public_artifact_status_version"
        ),
        "generated_at_utc": payload.get("generated_at_utc"),
        "last_attempted_run": payload.get("last_attempted_run"),
        "last_public_artifact_write": payload.get(
            "last_public_artifact_write"
        ),
        "last_public_write_age_seconds": payload.get(
            "last_public_write_age_seconds"
        ),
        "public_artifacts_stale": payload.get("public_artifacts_stale"),
        "stale_reason": payload.get("stale_reason"),
        "stale_since_utc": payload.get("stale_since_utc"),
    }
