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


def test_progress_sidecar_has_deterministic_structure_and_eta(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    logs: list[str] = []
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    tracker = ProgressTracker(
        path=path,
        started_at_utc=start,
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
        "status": "running",
        "run_id": "20260413T120000000000Z",
        "current_stage": "evaluation",
        "started_at_utc": "2026-04-13T12:00:00+00:00",
        "last_updated_at_utc": "2026-04-13T12:00:05+00:00",
        "progress": {
            "completed": 1,
            "total": 4,
            "percent": 25.0,
        },
        "current_item": {
            "strategy": "sma_crossover",
            "asset": "BTC-USD",
            "interval": "1h",
        },
        "timing": {
            "elapsed_seconds": 5,
            "stage_elapsed_seconds": 5,
            "eta_seconds": 15,
        },
        "failure": None,
    }
    assert logs[0] == "[research] stage stage=evaluation status=started total_items=4"
    assert logs[1] == (
        "[research] progress stage=evaluation progress=1/4 percent=25.0 "
        "elapsed_s=5 eta_s=15 current=sma_crossover BTC-USD 1h"
    )


def test_completed_state_is_written_correctly(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    tracker = ProgressTracker(
        path=path,
        started_at_utc=start,
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
    assert payload["progress"] == {"completed": 3, "total": 3, "percent": 100.0}
    assert payload["failure"] is None
    assert payload["timing"]["elapsed_seconds"] == 9


def test_failed_state_is_written_correctly(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    tracker = ProgressTracker(
        path=path,
        started_at_utc=start,
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
    assert payload["failure"] == {
        "failure_stage": "preflight",
        "error_type": "RuntimeError",
        "error_message": "boom",
    }
    assert payload["timing"]["elapsed_seconds"] == 2


def test_large_evaluation_progress_is_throttled(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start)
    path = tmp_path / "research" / "run_progress_latest.v1.json"
    tracker = ProgressTracker(
        path=path,
        started_at_utc=start,
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

    assert first["progress"]["completed"] == 1
    assert second["progress"]["completed"] == 1
