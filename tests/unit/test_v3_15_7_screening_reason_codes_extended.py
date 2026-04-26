"""v3.15.7 — SCREENING_REASON_CODES extension + v3.15.5 classifier.

Pins:

- The three new exploratory codes are in SCREENING_REASON_CODES.
- v3.15.5 ``_classify_research_rejection`` accepts a
  fully-exploratory-rejected run as ``research_rejection``.
- The frozenset still contains the v3.15.5 base codes.
- A defensive grep over screening_runtime + screening_criteria
  guarantees every emitted reason string lives in the set.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

import research.screening_criteria as screening_criteria
import research.screening_runtime as screening_runtime
from research.campaign_launcher import _classify_research_rejection
from research.rejection_taxonomy import SCREENING_REASON_CODES


V3_15_5_BASE = {
    "insufficient_trades",
    "no_oos_samples",
    "screening_criteria_not_met",
}
V3_15_7_NEW = {
    "expectancy_not_positive",
    "profit_factor_below_floor",
    "drawdown_above_exploratory_limit",
}


def test_v3_15_5_base_codes_still_present():
    assert V3_15_5_BASE.issubset(SCREENING_REASON_CODES)


def test_v3_15_7_new_codes_added():
    assert V3_15_7_NEW.issubset(SCREENING_REASON_CODES)


def test_screening_reason_codes_is_exact_union():
    assert SCREENING_REASON_CODES == V3_15_5_BASE | V3_15_7_NEW


def test_every_emitted_screening_reason_is_in_taxonomy():
    """Defensive: extract every literal reason string set on
    ``"reason"`` keys in the screening layer source and verify it
    lives in SCREENING_REASON_CODES.
    """
    sources = [
        inspect.getsource(screening_runtime),
        inspect.getsource(screening_criteria),
    ]
    pattern = re.compile(r'"reason":\s*"([a-z_]+)"')
    found_in_runtime = set(pattern.findall(sources[0]))
    # Plus return-tuple-style emissions from screening_criteria:
    crit_pattern = re.compile(r'return False,\s*"([a-z_]+)"')
    found_in_criteria = set(crit_pattern.findall(sources[1]))
    emitted = found_in_runtime | found_in_criteria
    # The runtime also emits ``screening_candidate_error`` and
    # ``candidate_budget_exceeded`` which are technical-failure
    # reasons (NOT screening rejections); allow them through but
    # log them in the test message if missing from set.
    technical_only = {"screening_candidate_error", "candidate_budget_exceeded"}
    rejection_emitted = emitted - technical_only
    drift = rejection_emitted - SCREENING_REASON_CODES
    assert drift == set(), (
        f"v3.15.7 drift: screening layer emits reasons {drift!r} "
        f"that are NOT in SCREENING_REASON_CODES."
    )


# ---- v3.15.5 _classify_research_rejection accepts new codes ----------------


CID = "col-test-v3157"


def _write_paper(path: Path, *, status: str, owner: str | None) -> None:
    payload = {
        "schema_version": "1.0",
        "status": status,
        "blocking_reasons": [],
        "col_campaign_id": owner,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_registry_with_only_exploratory_rejections(path: Path) -> None:
    candidates = [
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": ["expectancy_not_positive"], "passed": [],
                          "escalated": []},
        },
        {
            "strategy_id": "s2",
            "status": "rejected",
            "reasoning": {"failed": ["profit_factor_below_floor",
                                     "drawdown_above_exploratory_limit"],
                          "passed": [], "escalated": []},
        },
    ]
    path.write_text(json.dumps({
        "version": "v1",
        "candidates": candidates,
        "summary": {"rejected": 2, "needs_investigation": 0,
                    "candidate": 0, "total": 2},
    }), encoding="utf-8")


def test_classify_research_rejection_accepts_v3_15_7_codes(tmp_path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    _write_registry_with_only_exploratory_rejections(registry)
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome == "research_rejection"
    # Dominant reason: alphabetical tiebreak among
    # {expectancy_not_positive, profit_factor_below_floor,
    #  drawdown_above_exploratory_limit} with counts 1 / 1 / 1
    # → "drawdown_above_exploratory_limit" sorts first.
    assert reason == "drawdown_above_exploratory_limit"
