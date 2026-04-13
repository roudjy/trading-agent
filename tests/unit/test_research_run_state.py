from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.run_state import ActiveResearchRunError, RunStateStore, write_json_atomic


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_start_run_writes_authoritative_state(tmp_path: Path):
    start = datetime(2026, 4, 13, 12, 0, tzinfo=UTC)
    store = RunStateStore(
        state_path=tmp_path / "research" / "run_state.v1.json",
        history_root=tmp_path / "research" / "history",
        now_source=lambda: start,
        pid_source=lambda: 321,
    )

    payload = store.start_run(
        progress_path=tmp_path / "research" / "run_progress_latest.v1.json",
        manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
        log_dir=tmp_path / "logs" / "research",
        heartbeat_timeout_s=300,
    )

    assert payload["status"] == "running"
    assert payload["pid"] == 321
    assert payload["heartbeat_timeout_s"] == 300
    assert _load_json(tmp_path / "research" / "run_state.v1.json")["run_id"] == payload["run_id"]


def test_repair_stale_run_marks_aborted_on_dead_pid(tmp_path: Path, monkeypatch):
    now = datetime(2026, 4, 13, 12, 5, tzinfo=UTC)
    state_path = tmp_path / "research" / "run_state.v1.json"
    write_json_atomic(
        state_path,
        {
            "version": "v1",
            "run_id": "run-1",
            "status": "running",
            "pid": 999,
            "started_at_utc": "2026-04-13T12:00:00+00:00",
            "updated_at_utc": "2026-04-13T12:04:00+00:00",
            "stage": "evaluation",
            "status_reason": "research_run_started",
            "heartbeat_timeout_s": 300,
            "progress_path": str(tmp_path / "research" / "run_progress_latest.v1.json"),
            "manifest_path": str(tmp_path / "research" / "run_manifest_latest.v1.json"),
            "log_path": str(tmp_path / "logs" / "research" / "run-1.jsonl"),
            "error": None,
        },
    )
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)
    store = RunStateStore(
        state_path=state_path,
        history_root=tmp_path / "research" / "history",
        now_source=lambda: now,
    )

    result = store.repair_stale_run()

    repaired = _load_json(state_path)
    assert result["repaired"] is True
    assert repaired["status"] == "aborted"
    assert repaired["status_reason"] == "stale_recovery_dead_process"
    assert repaired["pid"] is None


def test_repair_stale_run_marks_aborted_on_heartbeat_timeout(tmp_path: Path, monkeypatch):
    now = datetime(2026, 4, 13, 12, 10, tzinfo=UTC)
    state_path = tmp_path / "research" / "run_state.v1.json"
    write_json_atomic(
        state_path,
        {
            "version": "v1",
            "run_id": "run-2",
            "status": "running",
            "pid": 123,
            "started_at_utc": "2026-04-13T12:00:00+00:00",
            "updated_at_utc": "2026-04-13T12:00:00+00:00",
            "stage": "evaluation",
            "status_reason": "research_run_started",
            "heartbeat_timeout_s": 300,
            "progress_path": str(tmp_path / "research" / "run_progress_latest.v1.json"),
            "manifest_path": str(tmp_path / "research" / "run_manifest_latest.v1.json"),
            "log_path": str(tmp_path / "logs" / "research" / "run-2.jsonl"),
            "error": None,
        },
    )
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)
    store = RunStateStore(
        state_path=state_path,
        history_root=tmp_path / "research" / "history",
        now_source=lambda: now,
    )

    result = store.repair_stale_run()
    repaired = _load_json(state_path)
    assert result["repaired"] is True
    assert repaired["status"] == "aborted"
    assert repaired["status_reason"] == "stale_recovery_heartbeat_timeout"


def test_start_run_rejects_live_running_state(tmp_path: Path, monkeypatch):
    state_path = tmp_path / "research" / "run_state.v1.json"
    write_json_atomic(
        state_path,
        {
            "version": "v1",
            "run_id": "run-live",
            "status": "running",
            "pid": 123,
            "started_at_utc": "2026-04-13T12:00:00+00:00",
            "updated_at_utc": "2026-04-13T12:04:00+00:00",
            "stage": "evaluation",
            "status_reason": "research_run_started",
            "heartbeat_timeout_s": 300,
            "progress_path": "research/run_progress_latest.v1.json",
            "manifest_path": "research/run_manifest_latest.v1.json",
            "log_path": "logs/research/run-live.jsonl",
            "error": None,
        },
    )
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)
    store = RunStateStore(
        state_path=state_path,
        history_root=tmp_path / "research" / "history",
        now_source=lambda: datetime(2026, 4, 13, 12, 4, 30, tzinfo=UTC),
    )

    with pytest.raises(ActiveResearchRunError):
        store.start_run(
            progress_path=tmp_path / "research" / "run_progress_latest.v1.json",
            manifest_path=tmp_path / "research" / "run_manifest_latest.v1.json",
            log_dir=tmp_path / "logs" / "research",
            heartbeat_timeout_s=300,
        )
