from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any


class ActiveResearchRunError(RuntimeError):
    """Raised when a live research run already holds the lifecycle lock."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _run_id(started_at_utc: datetime) -> str:
    return started_at_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _path_label(path: Path) -> str:
    return path.as_posix()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
    for attempt in range(3):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def _append_jsonl_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=False))
        handle.write("\n")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _pid_is_live(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class RunStateStore:
    def __init__(
        self,
        *,
        state_path: Path = Path("research/run_state.v1.json"),
        history_root: Path = Path("research/history"),
        now_source=_utc_now,
        pid_source=os.getpid,
    ) -> None:
        self.state_path = state_path
        self.history_root = history_root
        self._now_source = now_source
        self._pid_source = pid_source

    def load_state(self) -> dict[str, Any] | None:
        return _load_json(self.state_path)

    def repair_stale_run(self) -> dict[str, Any]:
        state = self.load_state()
        observations = {
            "repaired": False,
            "repair_reason": None,
            "pid_live": None,
            "heartbeat_age_seconds": None,
        }
        if not isinstance(state, dict) or state.get("status") != "running":
            return observations

        pid = state.get("pid")
        pid_live = _pid_is_live(pid if isinstance(pid, int) else None)
        observations["pid_live"] = pid_live

        updated_at = _parse_datetime(state.get("updated_at_utc"))
        timeout_s = int(state.get("heartbeat_timeout_s") or 0)
        if updated_at is not None and timeout_s > 0:
            observations["heartbeat_age_seconds"] = max(
                0,
                int(round((self._now_source() - updated_at).total_seconds())),
            )

        if not pid_live:
            reason = "stale_recovery_dead_process"
        elif updated_at is None:
            reason = "stale_recovery_missing_heartbeat"
        elif timeout_s > 0 and observations["heartbeat_age_seconds"] is not None and observations["heartbeat_age_seconds"] > timeout_s:
            reason = "stale_recovery_heartbeat_timeout"
        else:
            return observations

        self.abort_run(
            run_id=str(state.get("run_id") or ""),
            status_reason=reason,
            stage="aborted",
        )
        observations["repaired"] = True
        observations["repair_reason"] = reason
        return observations

    def start_run(
        self,
        *,
        progress_path: Path,
        manifest_path: Path,
        log_dir: Path,
        heartbeat_timeout_s: int,
        stage: str = "starting",
        status_reason: str = "research_run_started",
    ) -> dict[str, Any]:
        self.repair_stale_run()
        current = self.load_state()
        if isinstance(current, dict) and current.get("status") == "running":
            pid = current.get("pid")
            if _pid_is_live(pid if isinstance(pid, int) else None):
                raise ActiveResearchRunError(
                    f"active research run already exists run_id={current.get('run_id')} pid={pid}"
                )

        started_at = self._now_source()
        run_id = _run_id(started_at)
        log_path = log_dir / f"{run_id}.jsonl"
        payload = {
            "version": "v1",
            "run_id": run_id,
            "status": "running",
            "pid": int(self._pid_source()),
            "started_at_utc": started_at.isoformat(),
            "updated_at_utc": started_at.isoformat(),
            "stage": stage,
            "status_reason": status_reason,
            "heartbeat_timeout_s": int(heartbeat_timeout_s),
            "progress_path": _path_label(progress_path),
            "manifest_path": _path_label(manifest_path),
            "log_path": _path_label(log_path),
            "error": None,
        }
        write_json_atomic(self.state_path, payload)
        self._log_event(
            payload,
            event="run_created",
            status_reason=status_reason,
            stage=stage,
        )
        return payload

    def heartbeat(
        self,
        *,
        run_id: str,
        stage: str | None = None,
        status_reason: str | None = None,
    ) -> dict[str, Any]:
        state = self.load_state()
        if not isinstance(state, dict) or state.get("run_id") != run_id:
            return state or {}
        state["updated_at_utc"] = self._now_source().isoformat()
        if stage is not None:
            state["stage"] = stage
        if status_reason is not None:
            state["status_reason"] = status_reason
        write_json_atomic(self.state_path, state)
        return state

    def complete_run(
        self,
        *,
        run_id: str,
        status_reason: str = "research_run_completed",
        stage: str = "completed",
    ) -> dict[str, Any]:
        return self._write_terminal_state(
            run_id=run_id,
            status="completed",
            status_reason=status_reason,
            stage=stage,
            error=None,
            log_event="run_completed",
        )

    def fail_run(
        self,
        *,
        run_id: str,
        status_reason: str,
        error_type: str,
        error_message: str,
        stage: str = "failed",
    ) -> dict[str, Any]:
        return self._write_terminal_state(
            run_id=run_id,
            status="failed",
            status_reason=status_reason,
            stage=stage,
            error={
                "error_type": error_type,
                "error_message": error_message,
            },
            log_event="run_failed",
        )

    def abort_run(
        self,
        *,
        run_id: str,
        status_reason: str,
        stage: str = "aborted",
    ) -> dict[str, Any]:
        return self._write_terminal_state(
            run_id=run_id,
            status="aborted",
            status_reason=status_reason,
            stage=stage,
            error=None,
            log_event="run_aborted",
        )

    def _write_terminal_state(
        self,
        *,
        run_id: str,
        status: str,
        status_reason: str,
        stage: str,
        error: dict[str, Any] | None,
        log_event: str,
    ) -> dict[str, Any]:
        state = self.load_state() or {}
        if state.get("run_id") and state.get("run_id") != run_id:
            return state
        now = self._now_source()
        state.update(
            {
                "version": "v1",
                "run_id": run_id or str(state.get("run_id") or ""),
                "status": status,
                "pid": None,
                "started_at_utc": state.get("started_at_utc") or now.isoformat(),
                "updated_at_utc": now.isoformat(),
                "stage": stage,
                "status_reason": status_reason,
                "heartbeat_timeout_s": int(state.get("heartbeat_timeout_s") or 0),
                "progress_path": state.get("progress_path"),
                "manifest_path": state.get("manifest_path"),
                "log_path": state.get("log_path"),
                "error": error,
            }
        )
        write_json_atomic(self.state_path, state)
        self._log_event(state, event=log_event, status_reason=status_reason, stage=stage, error=error)
        self._write_history_copies(state)
        return state

    def _log_event(self, state: dict[str, Any], *, event: str, **fields: Any) -> None:
        log_path_value = state.get("log_path")
        if not isinstance(log_path_value, str) or log_path_value.strip() == "":
            return
        payload = {
            "timestamp_utc": self._now_source().isoformat(),
            "event": event,
            "run_id": state.get("run_id"),
            "status": state.get("status"),
            "stage": state.get("stage"),
            **fields,
        }
        _append_jsonl_event(Path(log_path_value), payload)

    def _write_history_copies(self, state: dict[str, Any]) -> None:
        run_id = str(state.get("run_id") or "")
        if run_id == "":
            return
        target_dir = self.history_root / run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target_dir / "run_state.v1.json", state)

        manifest_path = state.get("manifest_path")
        progress_path = state.get("progress_path")
        if isinstance(manifest_path, str) and Path(manifest_path).exists():
            shutil.copy2(Path(manifest_path), target_dir / "run_manifest.v1.json")
        if isinstance(progress_path, str) and Path(progress_path).exists():
            shutil.copy2(Path(progress_path), target_dir / "run_progress.v1.json")
