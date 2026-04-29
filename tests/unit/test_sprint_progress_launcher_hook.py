"""v3.15.15.9 — sprint progress freshness hook tests.

Covers two surfaces:

1. The new ``research.discovery_sprint.update_sprint_progress`` callable —
   pure side-effect, must never raise, must return ``None`` for every
   recoverable failure (no sprint, corrupt sprint, missing timestamps).
   Returns the payload dict on the happy path.

2. Cross-cutting behaviour: ``cmd_status`` is now a thin shim over the
   callable; emit the same JSON shape as before.

Launcher-side wiring (``research.campaign_launcher`` calling
``update_sprint_progress`` after ``assert_invariants``) is exercised
indirectly by the existing functional harness; these unit tests pin
the helper's contract so a future refactor cannot regress the
"never-raise" invariant.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research import discovery_sprint as ds


@pytest.fixture
def sprint_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    base = tmp_path / "research" / "discovery_sprints"
    registry = base / "sprint_registry_latest.v1.json"
    progress = base / "discovery_sprint_progress_latest.v1.json"
    report = base / "discovery_sprint_report_latest.v1.json"
    monkeypatch.setattr(ds, "SPRINT_ARTIFACTS_DIR", base, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REGISTRY_PATH", registry, raising=True)
    monkeypatch.setattr(ds, "SPRINT_PROGRESS_PATH", progress, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REPORT_PATH", report, raising=True)
    return {
        "base": base,
        "registry": registry,
        "progress": progress,
        "report": report,
    }


def test_update_sprint_progress_returns_none_when_no_sprint(
    sprint_paths: dict,
) -> None:
    """No sprint registry artifact → return None silently, no write."""
    assert ds.update_sprint_progress() is None
    assert not sprint_paths["progress"].exists()


def test_update_sprint_progress_returns_none_on_corrupt_registry(
    sprint_paths: dict,
    capsys: pytest.CaptureFixture,
) -> None:
    """Garbage in the sprint registry must produce a stderr warning and
    a None return — never an unhandled exception."""
    sprint_paths["registry"].parent.mkdir(parents=True, exist_ok=True)
    sprint_paths["registry"].write_text(
        json.dumps({"state": "active", "sprint_id": "sprt-bad"}),
        encoding="utf-8",
    )
    result = ds.update_sprint_progress()
    assert result is None
    err = capsys.readouterr().err
    assert "WARN" in err


def test_update_sprint_progress_writes_progress_sidecar_on_happy_path(
    sprint_paths: dict,
) -> None:
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    sprint_paths["progress"].unlink()  # ensure the call writes a fresh one
    payload = ds.update_sprint_progress(
        now_utc=datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)
    )
    assert payload is not None
    assert sprint_paths["progress"].exists()
    on_disk = json.loads(
        sprint_paths["progress"].read_text(encoding="utf-8")
    )
    assert on_disk["sprint_id"] == payload["sprint_id"]
    assert payload["state"] == "active"


def test_update_sprint_progress_returns_full_summary_dict(
    sprint_paths: dict,
) -> None:
    """The returned dict must carry every key ``cmd_status`` previously
    emitted — so the CLI shim's JSON shape doesn't drift.
    """
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    payload = ds.update_sprint_progress()
    assert payload is not None
    expected_keys = {
        "sprint_id",
        "state",
        "started_at_utc",
        "expected_completion_at_utc",
        "completed_at_utc",
        "target_campaigns",
        "observed_total",
        "pct_complete",
        "days_remaining",
        "target_met",
        "expired",
        "by_hypothesis",
        "by_preset",
        "by_outcome",
    }
    assert expected_keys.issubset(payload.keys())


def test_update_sprint_progress_does_not_raise_on_io_failure(
    sprint_paths: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0

    def boom(*args, **kwargs):
        raise OSError("disk full simulated")

    monkeypatch.setattr(ds, "write_sidecar_atomic", boom, raising=True)
    result = ds.update_sprint_progress()
    assert result is None  # tolerated, not raised
    err = capsys.readouterr().err
    assert "WARN" in err


def test_cmd_status_is_thin_shim_over_update_sprint_progress(
    sprint_paths: dict,
) -> None:
    """No active sprint: ``cmd_status`` still emits the no_sprint JSON."""
    buf = io.StringIO()
    rc = ds.cmd_status(out=buf)
    assert rc == 0
    assert json.loads(buf.getvalue()) == {
        "state": "no_sprint",
        "sprint_id": None,
    }


def test_cmd_status_emits_full_summary_when_active(
    sprint_paths: dict,
) -> None:
    """Active sprint: ``cmd_status`` emits the same shape ``cmd_status``
    has historically emitted (regression guard for the v3.15.15.9
    extraction)."""
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    buf = io.StringIO()
    rc = ds.cmd_status(out=buf)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["state"] == "active"
    assert "by_hypothesis" in payload
    assert "by_preset" in payload
    assert "observed_total" in payload


def test_update_sprint_progress_state_transition_to_completed_writes_registry(
    sprint_paths: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the sprint crosses target_met, the registry sidecar must be
    rewritten to ``state="completed"`` even though the function is
    invoked from a non-CLI path."""
    from datetime import timedelta

    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    started_at = datetime.fromisoformat(
        json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))[
            "started_at_utc"
        ].replace("Z", "+00:00")
    )
    fake_now = started_at + timedelta(hours=2)
    finished_at = (
        (started_at + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    )
    fake_registry = {
        "campaigns": {
            f"col-{i}": {
                "campaign_id": f"col-{i}",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished_at,
            }
            for i in range(50)
        }
    }
    monkeypatch.setattr(
        ds, "load_registry", lambda *_a, **_k: fake_registry, raising=True
    )
    payload = ds.update_sprint_progress(now_utc=fake_now)
    assert payload is not None
    assert payload["target_met"] is True
    assert payload["state"] == "completed"
    on_disk = json.loads(
        sprint_paths["registry"].read_text(encoding="utf-8")
    )
    assert on_disk["state"] == "completed"


def test_update_sprint_progress_never_raises_on_unparseable_timestamps(
    sprint_paths: dict,
    capsys: pytest.CaptureFixture,
) -> None:
    """Hand-craft a registry payload with missing timestamps; the
    callable must skip the refresh, not crash, and emit a warning."""
    sprint_paths["registry"].parent.mkdir(parents=True, exist_ok=True)
    # Restore_profile/plan would also fail, so we minimally satisfy
    # those paths first by writing a near-real registry then nuking
    # only the timestamps.
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    raw = json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))
    raw["started_at_utc"] = None
    raw["expected_completion_at_utc"] = None
    sprint_paths["registry"].write_text(
        json.dumps(raw), encoding="utf-8"
    )
    result = ds.update_sprint_progress()
    assert result is None
    err = capsys.readouterr().err
    assert "WARN" in err
