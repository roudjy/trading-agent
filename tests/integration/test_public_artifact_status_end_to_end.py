"""Integration tests for v3.15.1 public_artifact_status wiring in run_research.

Covers the lifecycle invariants pinned by the plan:
- success-path writes fresh status
- degenerate-path writes stale status, preserving the prior success write
- stale -> fresh transition after a later success-run
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import run_research as run_research_module
from research.empty_run_reporting import DegenerateResearchRunError
from research.public_artifact_status import (
    PUBLIC_ARTIFACT_STATUS_PATH,
    STALE_REASON_DEGENERATE,
    STALE_REASON_NEVER,
    read_public_artifact_status,
)


AS_OF_FIRST = datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)
AS_OF_SECOND = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


class _FakeTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit_event(self, name: str, **kwargs) -> None:
        self.events.append((name, kwargs))


@pytest.fixture
def cwd_with_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    return tmp_path


def test_success_path_writes_fresh_status(cwd_with_research: Path) -> None:
    run_research_module._write_public_artifact_status_sidecar(
        outcome="success",
        run_id="run-ok-1",
        attempted_at_utc=AS_OF_FIRST.isoformat(),
        preset_name="trend_equities_4h_baseline",
    )

    payload = read_public_artifact_status(PUBLIC_ARTIFACT_STATUS_PATH)
    assert payload is not None
    assert payload["public_artifacts_stale"] is False
    assert payload["stale_reason"] is None
    assert payload["stale_since_utc"] is None
    assert payload["last_public_artifact_write"]["run_id"] == "run-ok-1"


def test_degenerate_path_without_prior_yields_never_reason(
    cwd_with_research: Path,
) -> None:
    tracker = _FakeTracker()
    with pytest.raises(DegenerateResearchRunError):
        run_research_module._raise_degenerate_run(
            as_of_utc=AS_OF_FIRST,
            failure_stage="screening_no_survivors",
            assets=[SimpleNamespace(symbol="BTC-EUR")],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2024-01-01", "end": "2026-04-23"}},
            pair_diagnostics=[],
            run_id="run-degen-1",
            preset_name="trend_equities_4h_baseline",
            tracker=tracker,
        )

    payload = read_public_artifact_status(PUBLIC_ARTIFACT_STATUS_PATH)
    assert payload is not None
    assert payload["public_artifacts_stale"] is True
    assert payload["stale_reason"] == STALE_REASON_NEVER
    assert payload["last_attempted_run"]["run_id"] == "run-degen-1"
    assert payload["last_attempted_run"]["failure_stage"] == (
        "screening_no_survivors"
    )
    assert payload["last_public_artifact_write"]["run_id"] is None


def test_degenerate_path_after_success_preserves_last_write(
    cwd_with_research: Path,
) -> None:
    # First, simulate a successful run.
    run_research_module._write_public_artifact_status_sidecar(
        outcome="success",
        run_id="run-ok-1",
        attempted_at_utc=AS_OF_FIRST.isoformat(),
        preset_name="trend_equities_4h_baseline",
    )

    # Then the next day a degenerate run happens.
    tracker = _FakeTracker()
    with pytest.raises(DegenerateResearchRunError):
        run_research_module._raise_degenerate_run(
            as_of_utc=AS_OF_SECOND,
            failure_stage="validation_no_survivors",
            assets=[SimpleNamespace(symbol="BTC-EUR")],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2024-01-01", "end": "2026-04-24"}},
            pair_diagnostics=[],
            run_id="run-degen-1",
            preset_name="trend_equities_4h_baseline",
            tracker=tracker,
        )

    payload = read_public_artifact_status(PUBLIC_ARTIFACT_STATUS_PATH)
    assert payload is not None
    assert payload["public_artifacts_stale"] is True
    assert payload["stale_reason"] == STALE_REASON_DEGENERATE
    assert payload["last_public_artifact_write"]["run_id"] == "run-ok-1"
    assert payload["last_public_artifact_write"]["written_at_utc"] == (
        AS_OF_FIRST.isoformat()
    )
    assert payload["stale_since_utc"] == AS_OF_SECOND.isoformat()


def test_stale_to_fresh_transition_after_later_success(
    cwd_with_research: Path,
) -> None:
    # Sequence: success -> degenerate -> success
    run_research_module._write_public_artifact_status_sidecar(
        outcome="success",
        run_id="run-ok-1",
        attempted_at_utc=AS_OF_FIRST.isoformat(),
        preset_name="trend_equities_4h_baseline",
    )

    tracker = _FakeTracker()
    with pytest.raises(DegenerateResearchRunError):
        run_research_module._raise_degenerate_run(
            as_of_utc=AS_OF_SECOND,
            failure_stage="screening_no_survivors",
            assets=[SimpleNamespace(symbol="BTC-EUR")],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2024-01-01", "end": "2026-04-24"}},
            pair_diagnostics=[],
            run_id="run-degen-1",
            preset_name="trend_equities_4h_baseline",
            tracker=tracker,
        )

    # Degenerate confirmed stale.
    after_degenerate = read_public_artifact_status(PUBLIC_ARTIFACT_STATUS_PATH)
    assert after_degenerate is not None
    assert after_degenerate["public_artifacts_stale"] is True

    # Later success run recovers.
    AS_OF_THIRD = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    run_research_module._write_public_artifact_status_sidecar(
        outcome="success",
        run_id="run-ok-2",
        attempted_at_utc=AS_OF_THIRD.isoformat(),
        preset_name="trend_equities_4h_baseline",
    )

    after_recovery = read_public_artifact_status(PUBLIC_ARTIFACT_STATUS_PATH)
    assert after_recovery is not None
    assert after_recovery["public_artifacts_stale"] is False
    assert after_recovery["stale_reason"] is None
    assert after_recovery["stale_since_utc"] is None
    assert after_recovery["last_public_artifact_write"]["run_id"] == "run-ok-2"
    assert after_recovery["last_attempted_run"]["outcome"] == "success"


def test_degenerate_path_emits_tracker_event_on_sidecar_failure(
    cwd_with_research: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the status sidecar write fails, the degenerate run still raises
    and a tracker event is emitted for observability."""

    def _boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        run_research_module,
        "_write_public_artifact_status_sidecar",
        _boom,
    )

    tracker = _FakeTracker()
    with pytest.raises(DegenerateResearchRunError):
        run_research_module._raise_degenerate_run(
            as_of_utc=AS_OF_FIRST,
            failure_stage="screening_no_survivors",
            assets=[SimpleNamespace(symbol="BTC-EUR")],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2024-01-01", "end": "2026-04-23"}},
            pair_diagnostics=[],
            run_id="run-degen-1",
            preset_name="trend_equities_4h_baseline",
            tracker=tracker,
        )

    assert any(
        name == "public_artifact_status_sidecar_failed"
        for name, _ in tracker.events
    )
