"""v3.15.9 — graceful degradation when paper_readiness sidecar is
missing/malformed (REV 3 §6.8 / MF-12).

The evidence builder accepts whatever paper_blocked_index it
receives. The run_research helper ``_read_paper_blocked_index``
returns ``{}`` on absent / unreadable / wrongly-shaped input.
The evidence artifact still writes; downstream stage_result
falls back to the screening/promotion state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research.run_research import _read_paper_blocked_index
from research.screening_evidence import build_screening_evidence_payload


def _candidate(cid: str = "c1") -> dict:
    return {
        "candidate_id": cid,
        "strategy_id": "s1",
        "strategy_name": "s1",
        "asset": "BTC",
        "interval": "1h",
    }


def _passing_record(cid: str = "c1") -> dict:
    return {
        "candidate_id": cid,
        "final_status": "passed",
        "decision": "promoted_to_validation",
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {
            "expectancy": 0.001, "profit_factor": 1.5,
            "win_rate": 0.4, "max_drawdown": 0.2,
        },
        "sampling": {"grid_size": 1, "sampled_count": 1, "coverage_pct": 1.0,
                     "sampling_policy": "full_coverage",
                     "sampled_parameter_digest": "abc",
                     "coverage_warning": None},
    }


def _build(paper_blocked_index: dict) -> dict:
    return build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[_candidate()],
        screening_records=[_passing_record()],
        screening_pass_kinds={"s1": "promotion_grade"},
        paper_blocked_index=paper_blocked_index,
    )


def test_empty_paper_blocked_index_does_not_block_artifact() -> None:
    payload = _build({})
    assert payload["candidates"][0]["promotion_guard"]["promotion_allowed"] is True
    assert payload["candidates"][0]["promotion_guard"]["blocked_by"] == []


def test_missing_sidecar_returns_empty_dict(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    # No file exists at research/paper_readiness_latest.v1.json
    assert _read_paper_blocked_index() == {}


def test_malformed_sidecar_returns_empty_dict(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("research") / "paper_readiness_latest.v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json", encoding="utf-8")
    assert _read_paper_blocked_index() == {}


def test_well_formed_sidecar_extracts_blocked_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("research") / "paper_readiness_latest.v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "candidates": [
                    {"candidate_id": "c1", "status": "blocked",
                     "blocking_reasons": ["divergence"]},
                    {"candidate_id": "c2", "status": "ready",
                     "blocking_reasons": []},
                    {"candidate_id": "c3", "status": "blocked",
                     "blocking_reasons": ["fee_drag", "spread"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    index = _read_paper_blocked_index()
    assert index == {
        "c1": ["divergence"],
        "c3": ["fee_drag", "spread"],
    }


def test_paper_blocked_promotes_to_paper_blocked_stage_result() -> None:
    payload = _build({"c1": ["divergence"]})
    assert payload["candidates"][0]["stage_result"] == "paper_blocked"
    assert payload["candidates"][0]["promotion_guard"]["blocked_by"] == ["divergence"]
    assert payload["candidates"][0]["promotion_guard"]["promotion_allowed"] is False
