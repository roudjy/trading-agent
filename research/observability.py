from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _run_id(started_at_utc: datetime) -> str:
    return started_at_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


class ProgressTracker:
    """Lightweight progress sidecar + sparse console logging for research runs."""

    def __init__(
        self,
        *,
        path: Path,
        started_at_utc: datetime | None = None,
        now_source: Callable[[], datetime] | None = None,
        monotonic_source: Callable[[], float] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.path = path
        self._now_source = now_source or _utc_now
        self._monotonic_source = monotonic_source or time.monotonic
        self._log_fn = log_fn or print
        self.started_at_utc = (started_at_utc or self._now_source()).astimezone(UTC)
        self.run_id = _run_id(self.started_at_utc)
        self.status = "running"
        self.current_stage = "starting"
        self.current_item: dict[str, str | None] = {
            "strategy": None,
            "asset": None,
            "interval": None,
        }
        self.completed = 0
        self.total = 0
        self.failure: dict[str, str | None] | None = None
        self._stage_started_at_utc = self.started_at_utc
        self._stage_started_monotonic = self._monotonic_source()
        self._run_started_monotonic = self._stage_started_monotonic
        self._last_updated_at_utc = self.started_at_utc
        self._last_emitted_completed = -1
        self._write_sidecar()

    def start_stage(self, stage: str, *, total: int | None = None, **log_fields: Any) -> None:
        self.current_stage = stage
        self._stage_started_at_utc = self._now_source().astimezone(UTC)
        self._stage_started_monotonic = self._monotonic_source()
        if total is not None:
            self.total = int(total)
        self._last_updated_at_utc = self._stage_started_at_utc
        self._write_sidecar()
        self._log("stage", stage=stage, status="started", **log_fields)

    def mark_stage_completed(self, **log_fields: Any) -> None:
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_sidecar()
        self._log("stage", stage=self.current_stage, status="completed", **log_fields)

    def begin_item(self, *, strategy: str, asset: str, interval: str) -> None:
        self.current_item = {
            "strategy": strategy,
            "asset": asset,
            "interval": interval,
        }

    def advance(self, *, completed: int | None = None, total: int | None = None) -> None:
        if completed is not None:
            self.completed = int(completed)
        else:
            self.completed += 1
        if total is not None:
            self.total = int(total)
        if not self._should_emit_progress():
            return
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_sidecar()
        self._last_emitted_completed = self.completed
        self._log(
            "progress",
            stage=self.current_stage,
            progress=f"{self.completed}/{self.total}",
            percent=self._percent(),
            elapsed_s=self._elapsed_seconds(),
            eta_s=self._eta_seconds(),
            current=self._current_item_label(),
        )

    def complete(self) -> None:
        self.status = "completed"
        self.current_stage = "completed"
        self.completed = self.total
        self.current_item = {
            "strategy": None,
            "asset": None,
            "interval": None,
        }
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_sidecar()
        self._log("stage", stage="completed", status="completed", elapsed_s=self._elapsed_seconds())

    def fail(self, error: Exception, *, failure_stage: str | None = None) -> None:
        self.status = "failed"
        self.current_stage = "failed"
        self.failure = {
            "failure_stage": failure_stage or self.current_stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        self._last_updated_at_utc = self._now_source().astimezone(UTC)
        self._write_sidecar()
        self._log(
            "stage",
            stage="failed",
            status="failed",
            failure_stage=self.failure["failure_stage"],
            error_type=self.failure["error_type"],
        )

    def _should_emit_progress(self) -> bool:
        if self.total <= 0:
            return False
        if self.completed == self._last_emitted_completed:
            return False
        if self.total <= 10:
            return True
        if self.completed in {1, self.total}:
            return True
        stride = max(1, (self.total + 9) // 10)
        return self.completed % stride == 0

    def _percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round((self.completed / self.total) * 100.0, 2)

    def _elapsed_seconds(self) -> int:
        return max(0, int(round(self._monotonic_source() - self._run_started_monotonic)))

    def _stage_elapsed_seconds(self) -> int:
        return max(0, int(round(self._monotonic_source() - self._stage_started_monotonic)))

    def _eta_seconds(self) -> int | None:
        if self.status != "running" or self.current_stage != "evaluation":
            return None
        if self.completed <= 0 or self.total <= self.completed:
            return 0 if self.total > 0 and self.completed >= self.total else None
        pace = self._elapsed_seconds() / self.completed
        return max(0, int(round(pace * (self.total - self.completed))))

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
            "status": self.status,
            "run_id": self.run_id,
            "current_stage": self.current_stage,
            "started_at_utc": self.started_at_utc.isoformat(),
            "last_updated_at_utc": self._last_updated_at_utc.isoformat(),
            "progress": {
                "completed": int(self.completed),
                "total": int(self.total),
                "percent": self._percent(),
            },
            "current_item": dict(self.current_item),
            "timing": {
                "elapsed_seconds": self._elapsed_seconds(),
                "stage_elapsed_seconds": self._stage_elapsed_seconds(),
                "eta_seconds": self._eta_seconds(),
            },
            "failure": self.failure,
        }

    def _write_sidecar(self) -> None:
        payload = self._payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        try:
            os.replace(tmp_path, self.path)
        except PermissionError:
            with self.path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            if tmp_path.exists():
                tmp_path.unlink()

    def _log(self, event: str, **fields: Any) -> None:
        parts = [f"[research] {event}"]
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        self._log_fn(" ".join(parts))
