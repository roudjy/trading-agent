from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_failure_recurrence_learning as learning


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_complete_aapl_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "state": "completed",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )


def test_build_failure_recurrence_learning_tracks_blocker_recurrence(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = learning.build_failure_recurrence_learning(
        repo_root=tmp_path,
        max_candidates=15,
    )

    assert report["summary"]["false_ready_count"] == 0
    assert report["summary"]["source_blocker_recurrence_count"] >= 1
    assert report["summary"]["missing_evidence_recurrence_count"] >= 1


def test_build_failure_recurrence_learning_counts_false_ready_when_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    baseline = learning.build_failure_recurrence_learning(
        repo_root=tmp_path,
        max_candidates=15,
    )
    aapl_id = next(
        row["candidate_id"] for row in baseline["learning_rows"] if row["symbol"] == "AAPL"
    )

    def _patched_routing(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {
            "rows": [
                {
                    "candidate_id": aapl_id,
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "routing_false_ready": True,
                }
            ]
        }

    monkeypatch.setattr(
        learning.routing_quality,
        "build_routing_decision_quality",
        _patched_routing,
    )

    report = learning.build_failure_recurrence_learning(
        repo_root=tmp_path,
        max_candidates=15,
    )

    assert report["summary"]["false_ready_count"] >= 1


def test_build_source_usefulness_v0_distinguishes_useful_and_blocked_symbols(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = learning.build_failure_recurrence_learning(
        repo_root=tmp_path,
        max_candidates=15,
    )
    usefulness = learning.build_source_usefulness_v0(report, repo_root=tmp_path)

    rows = {row["symbol"]: row for row in usefulness["rows"]}
    assert rows["AAPL"]["usefulness_state"] == "useful_for_readonly_research"
    assert rows["ADYEN"]["usefulness_state"] == "blocked_by_source_identity"


def test_write_outputs_materializes_learning_and_source_reports(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = learning.build_failure_recurrence_learning(
        repo_root=tmp_path,
        max_candidates=15,
    )
    paths = learning.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_failure_recurrence_learning/latest.json"
    assert paths["source_usefulness_v0"] == "logs/qre_source_usefulness_v0/latest.json"
