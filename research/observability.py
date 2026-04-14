from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from research.run_state import RunStateStore, write_json_atomic


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProgressTracker:
    """Progress, manifest, and structured logging for research runs."""

    def __init__(
        self,
        *,
        path: Path,
        lifecycle: RunStateStore,
        run_id: str,
        started_at_utc: datetime,
        manifest_path: Path,
        log_path: Path,
        now_source: Callable[[], datetime] | None = None,
        monotonic_source: Callable[[], float] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.path = path
        self.lifecycle = lifecycle
        self.run_id = run_id
        self.manifest_path = manifest_path
        self.log_path = log_path
        self._now_source = now_source or _utc_now
        self._monotonic_source = monotonic_source or time.monotonic
        self._log_fn = log_fn or print
        self.started_at_utc = started_at_utc.astimezone(UTC)
        self.status = "running"
        self.current_stage = "starting"
        self.current_item: dict[str, str | None] = {
            "strategy": None,
            "asset": None,
            "interval": None,
        }
        self.completed_items = 0
        self.total_items = 0
        self.failed_items = 0
        self.error: dict[str, str | None] | None = None
        self._stage_started_at_utc = self.started_at_utc
        self._stage_started_monotonic = self._monotonic_source()
        self._run_started_monotonic = self._stage_started_monotonic
        self._last_updated_at_utc = self.started_at_utc
        self._last_emitted_completed = -1
        self._write_progress()

    def write_manifest(self, payload: dict[str, Any]) -> None:
        write_json_atomic(self.manifest_path, payload)
        self._log_event("manifest_written", status=payload.get("status"))

    def finalize_manifest(self, status: str) -> None:
        if not self.manifest_path.exists():
            return
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        payload["status"] = status
        payload["finished_at_utc"] = self._now_source().astimezone(UTC).isoformat()
        write_json_atomic(self.manifest_path, payload)

    def start_stage(self, stage: str, *, total: int | None = None, **log_fields: Any) -> None:
        self.current_stage = stage
        self._stage_started_at_utc = self._now_source().astimezone(UTC)
        self._stage_started_monotonic = self._monotonic_source()
        if total is not None:
            self.total_items = int(total)
        self._last_updated_at_utc = self._stage_started_at_utc
        self.lifecycle.heartbeat(
            run_id=self.run_id,
            stage=stage,
            status_reason=f"stage_started:{stage}",
        )
        self._write_progress()
        self._log("stage", stage=stage, status="started", **log_fields)
        self._log_event("stage_started", stage=stage, **log_fields)

    def mark_stage_completed(self, **log_fields: Any) -> None:
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self.lifecycle.heartbeat(
            run_id=self.run_id,
            stage=self.current_stage,
            status_reason=f"stage_completed:{self.current_stage}",
        )
        self._write_progress()
        self._log("stage", stage=self.current_stage, status="completed", **log_fields)
        self._log_event("stage_completed", stage=self.current_stage, **log_fields)

    def begin_item(self, *, strategy: str, asset: str, interval: str) -> None:
        self.current_item = {
            "strategy": strategy,
            "asset": asset,
            "interval": interval,
        }

    def advance(self, *, completed: int | None = None, total: int | None = None) -> None:
        if completed is not None:
            self.completed_items = int(completed)
        else:
            self.completed_items += 1
        if total is not None:
            self.total_items = int(total)
        self.lifecycle.heartbeat(
            run_id=self.run_id,
            stage=self.current_stage,
            status_reason=f"progress_update:{self.current_stage}",
        )
        if not self._should_emit_progress():
            return
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_progress()
        self._last_emitted_completed = self.completed_items
        self._log(
            "progress",
            stage=self.current_stage,
            progress=f"{self.completed_items}/{self.total_items}",
            percent=self._percent(),
            elapsed_s=self._elapsed_seconds(),
            eta_s=self._eta_seconds(),
            current=self._current_item_label(),
        )
        self._log_event(
            "progress_update",
            stage=self.current_stage,
            completed_items=self.completed_items,
            total_items=self.total_items,
            percent=self._percent(),
        )

    def complete(self) -> None:
        self.status = "completed"
        self.current_stage = "completed"
        self.completed_items = self.total_items
        self.current_item = {
            "strategy": None,
            "asset": None,
            "interval": None,
        }
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_progress()
        self.finalize_manifest("completed")
        self.lifecycle.complete_run(run_id=self.run_id, status_reason="research_run_completed")
        self._log("stage", stage="completed", status="completed", elapsed_s=self._elapsed_seconds())

    def fail(self, error: Exception, *, failure_stage: str | None = None) -> None:
        self.status = "failed"
        self.current_stage = "failed"
        self.error = {
            "failure_stage": failure_stage or self.current_stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self.failed_items += 1
        self._write_progress()
        self.finalize_manifest("failed")
        self.lifecycle.fail_run(
            run_id=self.run_id,
            status_reason=f"research_run_failed:{self.error['failure_stage']}",
            error_type=self.error["error_type"] or "Exception",
            error_message=self.error["error_message"] or "",
        )
        self._log(
            "stage",
            stage="failed",
            status="failed",
            failure_stage=self.error["failure_stage"],
            error_type=self.error["error_type"],
        )

    def _should_emit_progress(self) -> bool:
        if self.total_items <= 0:
            return False
        if self.completed_items == self._last_emitted_completed:
            return False
        if self.total_items <= 10:
            return True
        if self.completed_items in {1, self.total_items}:
            return True
        stride = max(1, (self.total_items + 9) // 10)
        return self.completed_items % stride == 0

    def _percent(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return round((self.completed_items / self.total_items) * 100.0, 2)

    def _elapsed_seconds(self) -> int:
        return max(0, int(round(self._monotonic_source() - self._run_started_monotonic)))

    def _eta_seconds(self) -> int | None:
        if self.status != "running" or self.current_stage not in {"screening", "validation", "evaluation"}:
            return None
        if self.completed_items <= 0 or self.total_items <= self.completed_items:
            return 0 if self.total_items > 0 and self.completed_items >= self.total_items else None
        pace = self._elapsed_seconds() / self.completed_items
        return max(0, int(round(pace * (self.total_items - self.completed_items))))

    def _current_item_label(self) -> str | None:
        strategy = self.current_item["strategy"]
        asset = self.current_item["asset"]
        interval = self.current_item["interval"]
        if not strategy or not asset or not interval:
            return None
        return f"{strategy} {asset} {interval}"

    def _payload(self) -> dict[str, Any]:
        return {
            "version": "v1",
            "run_id": self.run_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "stage_progress": {
                "completed": int(self.completed_items),
                "total": int(self.total_items),
                "percent": self._percent(),
            },
            "total_items": int(self.total_items),
            "completed_items": int(self.completed_items),
            "failed_items": int(self.failed_items),
            "current_item": dict(self.current_item),
            "started_at_utc": self.started_at_utc.isoformat(),
            "updated_at_utc": self._last_updated_at_utc.isoformat(),
            "elapsed_seconds": self._elapsed_seconds(),
            "eta_seconds": self._eta_seconds(),
            "error": self.error,
        }

    def _write_progress(self) -> None:
        write_json_atomic(self.path, self._payload())

    def _log(self, event: str, **fields: Any) -> None:
        parts = [f"[research] {event}"]
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        self._log_fn(" ".join(parts))

    def _log_event(self, event: str, **fields: Any) -> None:
        payload = {
            "timestamp_utc": self._now_source().astimezone(UTC).isoformat(),
            "event": event,
            "run_id": self.run_id,
            "status": self.status,
            "stage": self.current_stage,
            **fields,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=False))
            handle.write("\n")
