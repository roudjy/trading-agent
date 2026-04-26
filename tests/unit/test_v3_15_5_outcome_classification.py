"""v3.15.5 outcome classification — pure helper tests.

Pins the post-v3.15.5 launcher mapping:

- rc=2 (EXIT_CODE_DEGENERATE_NO_SURVIVORS) → ``degenerate_no_survivors``
- rc != 0 and rc != 2 → ``technical_failure``
- rc=0 + paper_ready (owner match) → ``completed_with_candidates``
- rc=0 + paper_blocked (owner match) → ``paper_blocked``
- rc=0 + screening-only registry rejection (owner match) → ``research_rejection``
- rc=0 + everything else → ``completed_no_survivor``

The dispatch lives in ``research.campaign_launcher._apply_decision``;
these tests exercise the pure helpers it composes from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.campaign_launcher import (
    _check_rc2_origin,
    _classify_outcome_from_paper,
    _classify_research_rejection,
    _technical_failure_reason_code,
)
from research.empty_run_reporting import EXIT_CODE_DEGENERATE_NO_SURVIVORS


CID = "col-20260426T120000000000Z-trend_equities_4h_baseline-aabbccdd00"
OTHER_CID = "col-20260426T130000000000Z-different_preset-eeffgghhii"


def _write_paper(path: Path, *, status: str, owner: str | None) -> None:
    payload = {
        "schema_version": "1.0",
        "paper_readiness_version": "v0.1",
        "status": status,
        "blocking_reasons": [] if status != "blocked" else ["malformed_return_stream"],
        "col_campaign_id": owner,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_registry(path: Path, *, candidates: list[dict]) -> None:
    payload = {
        "version": "v1",
        "candidates": candidates,
        "summary": {"rejected": len(candidates), "needs_investigation": 0,
                    "candidate": 0, "total": len(candidates)},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---- exit code constant -----------------------------------------------------


def test_exit_code_degenerate_is_2():
    assert EXIT_CODE_DEGENERATE_NO_SURVIVORS == 2


# ---- _technical_failure_reason_code ----------------------------------------


def test_technical_failure_reason_code_timeout():
    assert _technical_failure_reason_code(124) == "timeout"


def test_technical_failure_reason_code_generic_crash():
    assert _technical_failure_reason_code(1) == "worker_crash"
    assert _technical_failure_reason_code(137) == "worker_crash"
    assert _technical_failure_reason_code(255) == "worker_crash"


# ---- _classify_outcome_from_paper (existing v3.15.4 contract) --------------


def test_paper_ready_with_matching_owner(tmp_path: Path):
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="ready_for_paper_promotion", owner=CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome == "completed_with_candidates"


def test_paper_blocked_with_matching_owner(tmp_path: Path):
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="blocked", owner=CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome == "paper_blocked"
    assert reason == "malformed_return_stream"


def test_paper_owner_mismatch_returns_none(tmp_path: Path):
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="ready_for_paper_promotion", owner=OTHER_CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None


def test_paper_missing_returns_none(tmp_path: Path):
    paper = tmp_path / "paper.json"
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None


# ---- _classify_research_rejection ------------------------------------------


def _screening_only_candidates() -> list[dict]:
    return [
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": ["insufficient_trades"], "passed": [],
                          "escalated": []},
        },
        {
            "strategy_id": "s2",
            "status": "rejected",
            "reasoning": {"failed": ["insufficient_trades", "no_oos_samples"],
                          "passed": [], "escalated": []},
        },
    ]


def test_research_rejection_happy_path(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    _write_registry(registry, candidates=_screening_only_candidates())
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome == "research_rejection"
    assert reason == "insufficient_trades"


def test_research_rejection_paper_owner_mismatch(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=OTHER_CID)
    _write_registry(registry, candidates=_screening_only_candidates())
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None


def test_research_rejection_paper_missing(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_registry(registry, candidates=_screening_only_candidates())
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None


def test_research_rejection_paper_owner_match_but_status_paper_ready(tmp_path: Path):
    """If paper readiness already classifies → research_rejection must NOT fire."""
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="ready_for_paper_promotion", owner=CID)
    _write_registry(registry, candidates=_screening_only_candidates())
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_paper_owner_match_but_status_blocked(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="blocked", owner=CID)
    _write_registry(registry, candidates=_screening_only_candidates())
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_registry_missing(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_empty_candidates(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    _write_registry(registry, candidates=[])
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_mixed_status(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    candidates = _screening_only_candidates()
    candidates[0]["status"] = "candidate"
    _write_registry(registry, candidates=candidates)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_non_screening_codes(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    candidates = [
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": ["psr_below_threshold"],
                          "passed": [], "escalated": []},
        },
    ]
    _write_registry(registry, candidates=candidates)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_empty_failed_union(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    candidates = [
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": [], "passed": [], "escalated": []},
        },
    ]
    _write_registry(registry, candidates=candidates)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


def test_research_rejection_dominant_alphabetical_tiebreak(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    candidates = [
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": ["no_oos_samples"], "passed": [],
                          "escalated": []},
        },
        {
            "strategy_id": "s2",
            "status": "rejected",
            "reasoning": {"failed": ["screening_criteria_not_met"], "passed": [],
                          "escalated": []},
        },
    ]
    _write_registry(registry, candidates=candidates)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome == "research_rejection"
    # Tie 1-1: alphabetical tiebreak → "no_oos_samples" sorts before
    # "screening_criteria_not_met".
    assert reason == "no_oos_samples"


def test_research_rejection_malformed_registry(tmp_path: Path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    registry.write_text("not json", encoding="utf-8")
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None


# ---- _check_rc2_origin -----------------------------------------------------


def _write_diagnostics(path: Path, *, owner: str | None = CID,
                      include_summary: bool = True,
                      include_failure_stage: bool = True) -> None:
    payload: dict = {
        "version": "v1",
        "generated_at_utc": "2026-04-26T12:00:00+00:00",
        "message": "...",
        "col_campaign_id": owner,
    }
    if include_failure_stage:
        payload["failure_stage"] = "data_loading"
    if include_summary:
        payload["summary"] = {"pair_count": 0, "evaluable_pair_count": 0}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_rc2_origin_confirmed(tmp_path: Path):
    diag = tmp_path / "diag.json"
    _write_diagnostics(diag)
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_origin_confirmed_degenerate"


def test_rc2_origin_owner_mismatch(tmp_path: Path):
    diag = tmp_path / "diag.json"
    _write_diagnostics(diag, owner=OTHER_CID)
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_unexpected_origin"


def test_rc2_origin_owner_null_is_confirmed(tmp_path: Path):
    """Null col_campaign_id is allowed (pre-stamping fallback)."""
    diag = tmp_path / "diag.json"
    _write_diagnostics(diag, owner=None)
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_origin_confirmed_degenerate"


def test_rc2_diag_missing(tmp_path: Path):
    diag = tmp_path / "diag.json"
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_unexpected_origin"


def test_rc2_diag_malformed_json(tmp_path: Path):
    diag = tmp_path / "diag.json"
    diag.write_text("not json", encoding="utf-8")
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_payload_malformed"


def test_rc2_diag_missing_failure_stage(tmp_path: Path):
    diag = tmp_path / "diag.json"
    _write_diagnostics(diag, include_failure_stage=False)
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_payload_malformed"


def test_rc2_diag_missing_summary(tmp_path: Path):
    diag = tmp_path / "diag.json"
    _write_diagnostics(diag, include_summary=False)
    assert _check_rc2_origin(diag, expected_campaign_id=CID) == \
        "rc2_payload_malformed"
