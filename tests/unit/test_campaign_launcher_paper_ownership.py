"""v3.15.4 — launcher cannot read a stale paper_readiness sidecar.

The campaign launcher classifies the run outcome from
``paper_readiness_latest.v1.json`` after the subprocess exits. If the
subprocess crashed before overwriting that file, the launcher would
otherwise read the verdict of a *previous* campaign and credit /
blame the wrong run. v3.15.4 hardens
``_classify_outcome_from_paper`` to require an explicit ownership
match against the spawned campaign_id; mismatched or missing
ownership stamps fall through to the conservative
``completed_no_survivor`` classification.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.campaign_launcher import _classify_outcome_from_paper


def _write_readiness(
    path: Path,
    *,
    status: str | None = "ready_for_paper_promotion",
    blocking_reasons: list[str] | None = None,
    col_campaign_id: str | None = None,
) -> None:
    payload: dict = {
        "schema_version": "1.0",
        "paper_readiness_version": "v0.1",
        "run_id": "run-x",
        "col_campaign_id": col_campaign_id,
    }
    if status is not None:
        payload["status"] = status
    if blocking_reasons is not None:
        payload["blocking_reasons"] = blocking_reasons
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_classify_returns_none_when_sidecar_missing(tmp_path: Path) -> None:
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-1"
    )
    assert outcome is None and reason is None


def test_classify_returns_completed_when_owner_matches(tmp_path: Path) -> None:
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    _write_readiness(
        sidecar,
        status="ready_for_paper_promotion",
        col_campaign_id="cid-1",
    )
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-1"
    )
    assert outcome == "completed_with_candidates"
    assert reason is None


def test_classify_rejects_mismatched_owner(tmp_path: Path) -> None:
    """The defining v3.15.4 case: a sidecar from a previous campaign
    must NOT classify the current campaign."""
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    _write_readiness(
        sidecar,
        status="ready_for_paper_promotion",
        col_campaign_id="cid-prev",
    )
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-current"
    )
    assert outcome is None and reason is None


def test_classify_rejects_missing_owner_when_expected(tmp_path: Path) -> None:
    """Pre-v3.15.4 sidecars (no col_campaign_id field) cannot classify
    a v3.15.4 spawned campaign."""
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    _write_readiness(
        sidecar,
        status="ready_for_paper_promotion",
        col_campaign_id=None,
    )
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-current"
    )
    assert outcome is None and reason is None


def test_classify_passes_blocked_reason_when_owner_matches(tmp_path: Path) -> None:
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    _write_readiness(
        sidecar,
        status="blocked",
        blocking_reasons=["malformed_return_stream"],
        col_campaign_id="cid-1",
    )
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-1"
    )
    assert outcome == "paper_blocked"
    assert reason == "malformed_return_stream"


def test_classify_back_compat_when_no_expected_campaign_id(tmp_path: Path) -> None:
    """When ``expected_campaign_id`` is None (legacy callers / direct
    CLI), the ownership check is skipped and pre-v3.15.4 behaviour is
    preserved."""
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    _write_readiness(
        sidecar,
        status="ready_for_paper_promotion",
        col_campaign_id=None,
    )
    outcome, reason = _classify_outcome_from_paper(sidecar)
    assert outcome == "completed_with_candidates"
    assert reason is None


def test_classify_handles_corrupt_sidecar(tmp_path: Path) -> None:
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    sidecar.write_text("not-json{", encoding="utf-8")
    outcome, reason = _classify_outcome_from_paper(
        sidecar, expected_campaign_id="cid-1"
    )
    assert outcome is None and reason is None
