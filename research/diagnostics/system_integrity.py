"""System integrity snapshot.

Reports VERSION + git head/branch/dirty + container/process uptime
+ disk/timezone/artifact-dir-writability. Strictly read-only:

* ``subprocess.run`` is constrained to ``git rev-parse``,
  ``git rev-parse --abbrev-ref HEAD``, and ``git status --porcelain``.
* Disk free is read via ``shutil.disk_usage`` (passive).
* Process uptime is read from ``/proc/uptime`` when available.
* Missing system info becomes ``None`` / ``"unknown"`` — never raises.

No new imports of project modules.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic

from .clock import default_now_utc, to_iso_z
from .paths import (
    OBSERVABILITY_DIR,
    OBSERVABILITY_SCHEMA_VERSION,
    SYSTEM_INTEGRITY_PATH,
)

# Resolved at module load: the project root (parent of research/).
# Computed once, used as cwd for git subprocess calls.
_BASE_DIR: Path = Path(__file__).resolve().parents[2]


def _read_version_file() -> str | None:
    p = _BASE_DIR / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _git_run(args: list[str], *, timeout: float = 2.0) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(_BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


def _git_head() -> str | None:
    return _git_run(["rev-parse", "HEAD"])


def _git_branch() -> str | None:
    branch = _git_run(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        # Detached head — return None rather than the literal string.
        return None
    return branch


def _git_dirty_flag() -> bool | None:
    out = _git_run(["status", "--porcelain"])
    if out is None:
        return None
    return bool(out.strip())


def _process_uptime_seconds() -> float | None:
    """Process uptime via /proc/<pid>/stat where available.

    Returns None on Windows or when /proc is not mounted.
    """
    try:
        if not Path("/proc/self/stat").exists():
            return None
        with open("/proc/self/stat", "r", encoding="utf-8") as fh:
            parts = fh.read().split()
        # Field 22 (0-indexed 21) is starttime in clock ticks since boot.
        starttime_ticks = float(parts[21])
        clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            system_uptime = float(fh.read().split()[0])
        process_started_seconds_after_boot = starttime_ticks / clk_tck
        return max(0.0, system_uptime - process_started_seconds_after_boot)
    except (OSError, ValueError, IndexError, KeyError):
        return None


def _container_uptime_seconds() -> float | None:
    """Best-effort container uptime via /proc/uptime.

    On Linux containers this is the process namespace uptime, which
    closely tracks container lifetime when the container's PID 1 is
    long-lived.
    """
    try:
        if not Path("/proc/uptime").exists():
            return None
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError):
        return None


def _disk_free_bytes() -> int | None:
    try:
        usage = shutil.disk_usage(str(_BASE_DIR))
        return int(usage.free)
    except OSError:
        return None


def _artifact_dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".__observability_writable_probe__"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _last_artifact_update_unix() -> float | None:
    """Latest mtime among the existing observability artifacts.

    Used as a coarse "last successful observability write" indicator.
    """
    if not OBSERVABILITY_DIR.exists():
        return None
    latest: float | None = None
    try:
        for child in OBSERVABILITY_DIR.iterdir():
            if not child.is_file():
                continue
            if child.name.endswith(".tmp"):
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if latest is None or mtime > latest:
                latest = mtime
    except OSError:
        return None
    return latest


def build_system_integrity_snapshot(
    *,
    now_utc: datetime | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    when = now_utc or default_now_utc()
    base = base_dir or _BASE_DIR

    version = _read_version_file()
    git_head = _git_head()
    git_branch = _git_branch()
    git_dirty = _git_dirty_flag()
    process_uptime = _process_uptime_seconds()
    container_uptime = _container_uptime_seconds()
    disk_free = _disk_free_bytes()
    artifact_dir_ok = _artifact_dir_writable(OBSERVABILITY_DIR)
    last_artifact_unix = _last_artifact_update_unix()

    timezone = time.strftime("%Z") or None

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "version_file": version,
        "git": {
            "head": git_head,
            "branch": git_branch,
            "dirty": git_dirty,
        },
        "uptime_seconds": {
            "process": process_uptime,
            "container": container_uptime,
        },
        "disk_free_bytes": disk_free,
        "artifact_directory_writable": artifact_dir_ok,
        "observability_dir": str(OBSERVABILITY_DIR).replace("\\", "/"),
        "last_observability_artifact_update_unix": last_artifact_unix,
        "timezone": timezone,
        "base_dir": str(base).replace("\\", "/"),
    }


def write_system_integrity(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    target = path if path is not None else SYSTEM_INTEGRITY_PATH
    if "observability" not in str(target).replace("\\", "/").split("/"):
        raise RuntimeError(
            "write_system_integrity refuses to write outside research/observability/"
        )
    write_sidecar_atomic(target, payload)


__all__ = [
    "build_system_integrity_snapshot",
    "write_system_integrity",
]
