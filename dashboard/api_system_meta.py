"""Dashboard API blueprint for read-only system metadata.

Three GET-only passthrough endpoints feeding the QRE Control Room
frontend redesign:

    GET  /api/system/version
        Reads the project ``VERSION`` file plus ``git rev-parse HEAD``.
        Reports image tag from ``QRE_IMAGE_TAG`` env var if present.
        No decision logic, no mutation.

    GET  /api/research/artifact-index
        Lists existing files in known read-only artifact directories
        (``research/`` top level + ``research/discovery_sprints/``)
        with name, relative path, mtime, and size. Filesystem
        inspection only; never opens artifact contents.

    GET  /api/research/sprint-status
        Passthrough of ``research/discovery_sprints/sprint_registry_latest.v1.json``
        and ``discovery_sprint_progress_latest.v1.json``. Returns the
        artifact JSON as-is plus an availability flag. No decision
        logic, no sprint orchestration import — only reads existing
        files.

These endpoints:

* are GET-only (no POST/PUT/DELETE/PATCH);
* do not import campaign launcher, queue, policy, sprint
  orchestrator, strategy, automation, execution, or state modules;
* never start, stop, mutate, classify, or decide anything;
* return ``{"available": false}`` instead of raising when an
  artifact is missing, so the frontend degrades gracefully.

Wire-up::

    from dashboard.api_system_meta import register_system_meta_routes
    register_system_meta_routes(app)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

BASE_DIR: Path = Path(__file__).resolve().parent.parent
VERSION_FILE: Path = BASE_DIR / "VERSION"

# Read-only artifact directories surfaced by the artifact index.
RESEARCH_DIR: Path = BASE_DIR / "research"
DISCOVERY_SPRINTS_DIR: Path = RESEARCH_DIR / "discovery_sprints"

# Sprint artifact filenames (existing, written by the orchestrator
# elsewhere). We only READ these — we never open the orchestrator
# module, so this blueprint cannot trigger sprint side effects.
SPRINT_REGISTRY_FILE: Path = (
    DISCOVERY_SPRINTS_DIR / "sprint_registry_latest.v1.json"
)
SPRINT_PROGRESS_FILE: Path = (
    DISCOVERY_SPRINTS_DIR / "discovery_sprint_progress_latest.v1.json"
)
SPRINT_REPORT_FILE: Path = (
    DISCOVERY_SPRINTS_DIR / "discovery_sprint_report_latest.v1.json"
)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    head = (result.stdout or "").strip()
    return head or None


def _file_meta(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
    except OSError:
        return {
            "name": path.name,
            "path": str(path.relative_to(BASE_DIR)).replace("\\", "/"),
            "exists": False,
            "size_bytes": None,
            "modified_at_unix": None,
        }
    return {
        "name": path.name,
        "path": str(path.relative_to(BASE_DIR)).replace("\\", "/"),
        "exists": True,
        "size_bytes": int(st.st_size),
        "modified_at_unix": float(st.st_mtime),
    }


def _list_dir_files(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists() or not directory.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        entries.append(_file_meta(entry))
    return entries


def register_system_meta_routes(app: Flask) -> None:
    @app.route("/api/system/version", methods=["GET"])
    def _api_system_version():
        file_version = _read_text(VERSION_FILE)
        meta = _file_meta(VERSION_FILE) if VERSION_FILE.exists() else None
        return jsonify(
            {
                "file_version": file_version,
                "git_head": _git_head(),
                "image_tag": os.environ.get("QRE_IMAGE_TAG"),
                "host": os.environ.get("HOSTNAME"),
                "container": os.environ.get("QRE_CONTAINER_NAME"),
                "version_file": meta,
            }
        )

    @app.route("/api/research/artifact-index", methods=["GET"])
    def _api_research_artifact_index():
        research_files = _list_dir_files(RESEARCH_DIR)
        sprint_files = _list_dir_files(DISCOVERY_SPRINTS_DIR)
        return jsonify(
            {
                "directories": [
                    {
                        "path": "research",
                        "files": research_files,
                    },
                    {
                        "path": "research/discovery_sprints",
                        "files": sprint_files,
                    },
                ],
                "file_count": len(research_files) + len(sprint_files),
            }
        )

    @app.route("/api/research/sprint-status", methods=["GET"])
    def _api_research_sprint_status():
        registry = _read_json(SPRINT_REGISTRY_FILE)
        progress = _read_json(SPRINT_PROGRESS_FILE)
        report = _read_json(SPRINT_REPORT_FILE)
        return jsonify(
            {
                "available": registry is not None or progress is not None,
                "registry": registry,
                "progress": progress,
                "report": report,
                "registry_file": _file_meta(SPRINT_REGISTRY_FILE),
                "progress_file": _file_meta(SPRINT_PROGRESS_FILE),
                "report_file": _file_meta(SPRINT_REPORT_FILE),
            }
        )


__all__ = ["register_system_meta_routes"]
