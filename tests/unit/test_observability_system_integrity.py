"""Unit tests for research.diagnostics.system_integrity."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics import system_integrity as si


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def test_snapshot_keys_stable(fixed_now: datetime):
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["schema_version"] == "1.0"
    assert snap["generated_at_utc"] == "2026-04-28T10:00:00Z"
    # Every documented top-level key is present (None is OK).
    for key in (
        "version_file",
        "git",
        "uptime_seconds",
        "disk_free_bytes",
        "artifact_directory_writable",
        "observability_dir",
        "last_observability_artifact_update_unix",
        "timezone",
        "base_dir",
    ):
        assert key in snap


def test_git_unavailable_returns_none(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime):
    monkeypatch.setattr(si, "_git_run", lambda *a, **k: None)
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["git"]["head"] is None
    assert snap["git"]["branch"] is None
    assert snap["git"]["dirty"] is None


def test_disk_free_unavailable(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime):
    monkeypatch.setattr(si, "_disk_free_bytes", lambda: None)
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["disk_free_bytes"] is None


def test_artifact_dir_writable_true(tmp_path: Path, fixed_now: datetime, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "observability"
    monkeypatch.setattr(si, "OBSERVABILITY_DIR", target)
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["artifact_directory_writable"] is True


def test_last_observability_update_present(
    tmp_path: Path,
    fixed_now: datetime,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "observability"
    target.mkdir()
    (target / "x.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(si, "OBSERVABILITY_DIR", target)
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["last_observability_artifact_update_unix"] is not None


def test_unknown_fields_do_not_raise(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime):
    """Even when every helper returns None, the build still succeeds."""
    monkeypatch.setattr(si, "_git_run", lambda *a, **k: None)
    monkeypatch.setattr(si, "_disk_free_bytes", lambda: None)
    monkeypatch.setattr(si, "_process_uptime_seconds", lambda: None)
    monkeypatch.setattr(si, "_container_uptime_seconds", lambda: None)
    monkeypatch.setattr(si, "_read_version_file", lambda: None)
    snap = si.build_system_integrity_snapshot(now_utc=fixed_now)
    assert snap["version_file"] is None
    assert snap["uptime_seconds"]["process"] is None
    assert snap["uptime_seconds"]["container"] is None
