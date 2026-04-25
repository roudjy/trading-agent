"""v3.15.3.1 hotfix regression: audit sidecars are written on degenerate runs.

Pin: ``_raise_degenerate_run`` writes both
``strategy_hypothesis_catalog_latest.v1.json`` and
``strategy_campaign_metadata_latest.v1.json`` BEFORE re-raising
``DegenerateResearchRunError``. The v3.15.3 ship missed this
because the original sidecar hook lived only in the post-run
success path; degenerate / no-survivor runs left the audit trail
without a catalog snapshot.

These tests do not exercise the policy engine — they only pin the
file-write side effect on the early-exit path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from research import run_research as rr
from research.empty_run_reporting import DegenerateResearchRunError


_T = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def temp_research_dir(tmp_path, monkeypatch):
    """Run inside a tmp dir so sidecar writes don't touch the real
    research/ tree. Both writers resolve their paths relative to the
    current working directory."""
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    return research_dir


def _invoke_degenerate(*, run_id: str | None = "run-test", preset_name: str | None = "trend_pullback_crypto_1h"):
    """Trigger ``_raise_degenerate_run`` with a minimal but valid input."""
    with pytest.raises(DegenerateResearchRunError):
        rr._raise_degenerate_run(
            as_of_utc=_T,
            failure_stage="screening_no_survivors",
            assets=["BTC-EUR"],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2026-04-01", "end": "2026-04-25"}},
            pair_diagnostics=[],
            evaluations_count=0,
            evaluations_with_oos_daily_returns=0,
            run_id=run_id,
            preset_name=preset_name,
            tracker=None,
        )


def test_catalog_sidecar_written_on_degenerate_run(temp_research_dir: Path) -> None:
    """The v3.15.3 catalog sidecar lands on disk even when the run
    terminates as no-survivor."""
    _invoke_degenerate()
    catalog = temp_research_dir / "strategy_hypothesis_catalog_latest.v1.json"
    assert catalog.exists(), (
        "strategy_hypothesis_catalog_latest.v1.json must be written by "
        "_raise_degenerate_run (v3.15.3.1 hotfix)"
    )


def test_campaign_metadata_sidecar_written_on_degenerate_run(
    temp_research_dir: Path,
) -> None:
    _invoke_degenerate()
    metadata = temp_research_dir / "strategy_campaign_metadata_latest.v1.json"
    assert metadata.exists(), (
        "strategy_campaign_metadata_latest.v1.json must be written by "
        "_raise_degenerate_run (v3.15.3.1 hotfix)"
    )


def test_audit_sidecar_failure_does_not_mask_degenerate_error(
    temp_research_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the v3.15.3 sidecar writer raises, the original
    ``DegenerateResearchRunError`` must still propagate. The hotfix
    uses a best-effort try/except so audit-side failures never mask
    research-side failures."""

    def _boom(*args, **kwargs):
        raise RuntimeError("forced sidecar write failure")

    monkeypatch.setattr(rr, "write_catalog_sidecar", _boom)
    # Should still raise DegenerateResearchRunError, not RuntimeError.
    _invoke_degenerate()


def test_audit_sidecar_failure_emits_tracker_event(
    temp_research_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the audit-sidecar write fails, the optional tracker is
    notified with ``v3_15_3_hypothesis_catalog_sidecars_failed`` so the
    audit-trail gap is observable."""

    def _boom(*args, **kwargs):
        raise RuntimeError("forced sidecar write failure")

    monkeypatch.setattr(rr, "write_catalog_sidecar", _boom)

    captured: list[tuple[str, dict]] = []

    class _StubTracker:
        def emit_event(self, event: str, **kwargs):
            captured.append((event, kwargs))

    with pytest.raises(DegenerateResearchRunError):
        rr._raise_degenerate_run(
            as_of_utc=_T,
            failure_stage="screening_no_survivors",
            assets=["BTC-EUR"],
            intervals=["1h"],
            interval_ranges={"1h": {"start": "2026-04-01", "end": "2026-04-25"}},
            pair_diagnostics=[],
            evaluations_count=0,
            evaluations_with_oos_daily_returns=0,
            run_id="run-x",
            preset_name="trend_pullback_crypto_1h",
            tracker=_StubTracker(),
        )

    failed_events = [
        (event, kw)
        for event, kw in captured
        if event == "v3_15_3_hypothesis_catalog_sidecars_failed"
    ]
    assert failed_events, (
        f"expected v3_15_3_hypothesis_catalog_sidecars_failed event; "
        f"got {[e for e, _ in captured]}"
    )
    _, kw = failed_events[0]
    assert kw.get("outcome") == "degenerate"
    assert kw.get("failure_stage") == "screening_no_survivors"


def test_catalog_sidecar_carries_pin_block_invariants(
    temp_research_dir: Path,
) -> None:
    """Pin: the sidecar written from the degenerate path carries the
    same v3.15.3 pin block as the success path (live_eligible=False,
    diagnostic_only=True)."""
    import json

    _invoke_degenerate()
    catalog = temp_research_dir / "strategy_hypothesis_catalog_latest.v1.json"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["live_eligible"] is False
    assert payload["diagnostic_only"] is True
    assert payload["authoritative"] is False
    assert payload["hypothesis_catalog_version"] == "v0.1"
    # Hard invariant: exactly one active_discovery hypothesis.
    actives = [
        h for h in payload["hypotheses"]
        if h["status"] == "active_discovery"
    ]
    assert len(actives) == 1


def test_catalog_sidecar_records_run_id(temp_research_dir: Path) -> None:
    """The run_id passed into _raise_degenerate_run is forwarded to the
    sidecar payload, so an operator can correlate the catalog snapshot
    with the failed run."""
    import json

    _invoke_degenerate(run_id="run-42")
    catalog = temp_research_dir / "strategy_hypothesis_catalog_latest.v1.json"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-42"
