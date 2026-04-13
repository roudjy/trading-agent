from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research.observability import ProgressTracker


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start
        self.mono = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)
        self.mono += float(seconds)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FakeLifecycle:
    def __init__(self) -> None:
        self.heartbeats: list[tuple[str, str | None, str | None]] = []
        self.completed: list[str] = []
        self.failed: list[tuple[str, str, str, str]] = []

    def heartbeat(self, *, run_id: str, stage: str | None = None, status_reason: str | None = None):
        self.heartbeats.append((run_id, stage, status_reason))
        return {}

    def complete_run(self, *, run_id: str, status_reason: str = "research_run_completed", stage: str = "completed"):
        self.completed.append(run_id)
        return {}

    def fail_run(self, *, run_id: str, status_reason: str, error_type: str, error_message: str, stage: str = "failed"):
        self.failed.append((run_id, status_reason, error_type, error_message))
        return {}


def test_progress_sidecar_has_deterministic_structure_and_eta(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    logs: list[str] = []
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    lifecycle = FakeLifecycle()
    tracker = ProgressTracker(
        path=path,
        lifecycle=lifecycle,
        run_id="20260413T120000000000Z",
        started_at_utc=start,
        manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
        log_path=tmp_path / "logs" / "research" / "20260413T120000000000Z.jsonl",
        now_source=clock.now,
        monotonic_source=clock.monotonic,
        log_fn=logs.append,
    )

    tracker.start_stage("evaluation", total=4, total_items=4)
    tracker.begin_item(strategy="sma_crossover", asset="BTC-USD", interval="1h")
    clock.advance(5)
    tracker.advance(completed=1, total=4)

    payload = _load_json(path)
    assert payload == {
        "version": "v1",
        "run_id": "20260413T120000000000Z",
        "status": "running",
        "current_stage": "evaluation",
        "stage_progress": {
            "completed": 1,
            "total": 4,
            "percent": 25.0,
        },
        "total_items": 4,
        "completed_items": 1,
        "failed_items": 0,
        "current_item": {
            "strategy": "sma_crossover",
            "asset": "BTC-USD",
            "interval": "1h",
        },
        "started_at_utc": "2026-04-13T12:00:00+00:00",
        "updated_at_utc": "2026-04-13T12:00:05+00:00",
        "elapsed_seconds": 5,
        "eta_seconds": 15,
        "error": None,
    }
    assert logs[0] == "[research] stage stage=evaluation status=started total_items=4"
    assert logs[1] == (
        "[research] progress stage=evaluation progress=1/4 percent=25.0 "
        "elapsed_s=5 eta_s=15 current=sma_crossover BTC-USD 1h"
    )
    assert lifecycle.heartbeats[0] == (
        "20260413T120000000000Z",
        "evaluation",
        "stage_started:evaluation",
    )


def test_completed_state_is_written_correctly(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    lifecycle = FakeLifecycle()
    tracker = ProgressTracker(
        path=path,
        lifecycle=lifecycle,
        run_id="20260413T120000000000Z",
        started_at_utc=start,
        manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
        log_path=tmp_path / "logs" / "research" / "20260413T120000000000Z.jsonl",
        now_source=clock.now,
        monotonic_source=clock.monotonic,
        log_fn=lambda message: None,
    )

    tracker.start_stage("writing_outputs", total=3)
    clock.advance(9)
    tracker.complete()

    payload = _load_json(path)
    assert payload["status"] == "completed"
    assert payload["current_stage"] == "completed"
    assert payload["stage_progress"] == {"completed": 3, "total": 3, "percent": 100.0}
    assert payload["error"] is None
    assert payload["elapsed_seconds"] == 9
    assert lifecycle.completed == ["20260413T120000000000Z"]


def test_failed_state_is_written_correctly(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    lifecycle = FakeLifecycle()
    tracker = ProgressTracker(
        path=path,
        lifecycle=lifecycle,
        run_id="20260413T120000000000Z",
        started_at_utc=start,
        manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
        log_path=tmp_path / "logs" / "research" / "20260413T120000000000Z.jsonl",
        now_source=clock.now,
        monotonic_source=clock.monotonic,
        log_fn=lambda message: None,
    )

    tracker.start_stage("preflight", total=10)
    clock.advance(2)
    tracker.fail(RuntimeError("boom"), failure_stage="preflight")

    payload = _load_json(path)
    assert payload["status"] == "failed"
    assert payload["current_stage"] == "failed"
    assert payload["error"] == {
        "failure_stage": "preflight",
        "error_type": "RuntimeError",
        "error_message": "boom",
    }
    assert payload["elapsed_seconds"] == 2
    assert lifecycle.failed[0][0] == "20260413T120000000000Z"


def test_large_evaluation_progress_is_throttled(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    lifecycle = FakeLifecycle()
    tracker = ProgressTracker(
        path=path,
        lifecycle=lifecycle,
        run_id="20260413T120000000000Z",
        started_at_utc=start,
        manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
        log_path=tmp_path / "logs" / "research" / "20260413T120000000000Z.jsonl",
        now_source=clock.now,
        monotonic_source=clock.monotonic,
        log_fn=lambda message: None,
    )

    tracker.start_stage("evaluation", total=100)
    tracker.begin_item(strategy="rsi", asset="BTC-USD", interval="1h")
    clock.advance(1)
    tracker.advance(completed=1, total=100)
    first = _load_json(path)

    tracker.begin_item(strategy="rsi", asset="ETH-USD", interval="1h")
    clock.advance(1)
    tracker.advance(completed=2, total=100)
    second = _load_json(path)

    assert first["completed_items"] == 1
    assert second["completed_items"] == 1


def test_manifest_and_structured_log_are_written(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    manifest_path = tmp_path / "research" / "run_manifest_latest.v1.json"
    log_path = tmp_path / "logs" / "research" / "20260413T120000000000Z.jsonl"
    tracker = ProgressTracker(
        path=path,
        lifecycle=FakeLifecycle(),
        run_id="20260413T120000000000Z",
        started_at_utc=start,
        manifest_path=manifest_path,
        log_path=log_path,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
        log_fn=lambda message: None,
    )

    tracker.write_manifest(
        {
            "version": "v1",
            "run_id": "20260413T120000000000Z",
            "created_at_utc": start.isoformat(),
            "started_at_utc": start.isoformat(),
            "status": "running",
        }
    )
    tracker.start_stage("planning")

    manifest = _load_json(manifest_path)
    logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert manifest["status"] == "running"
    assert logs[0]["event"] == "manifest_written"
    assert logs[1]["event"] == "stage_started"
