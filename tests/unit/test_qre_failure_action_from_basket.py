from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_failure_action_from_basket as failure_action


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


def test_build_failure_action_from_basket_marks_ready_basket_as_readonly_eligible(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    row = rows["AAPL"]
    assert row["recommended_action"] == "eligible_for_readonly_routing"
    assert row["actionability"]["status"] == "actionable"
    assert row["reason_record_refs"]["record_ids"]
    assert report["summary"]["actionable_count"] >= 1


def test_build_failure_action_from_basket_maps_source_identity_blockers(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=5,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    asmi = rows["ASMI"]
    assert asmi["blocker_code"] == "source_identity_blocked"
    assert asmi["recommended_action"] == "require_identity_resolution"
    assert asmi["actionability"]["status"] == "actionable"


def test_build_failure_action_from_basket_maps_missing_screening_to_collect_more_evidence(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    row = rows["AAPL"]
    assert row["recommended_action"] == "collect_more_evidence"
    assert row["actionability"]["status"] == "actionable"


def test_build_failure_action_from_basket_keeps_fail_closed_non_actionable(
    tmp_path: Path,
) -> None:
    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=1,
    )

    row = report["rows"][0]
    assert row["recommended_action"] == "keep_blocked"
    assert row["actionability"]["status"] == "non_actionable"
    assert "fail_closed" in row["actionability"]["reason_codes"]


def test_build_failure_action_from_basket_fails_closed_without_reason_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    def _empty_reason_records(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {"records": []}

    monkeypatch.setattr(
        failure_action.reason_records,
        "build_reason_records_snapshot",
        _empty_reason_records,
    )

    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=1,
    )

    row = report["rows"][0]
    assert row["recommended_action"] == "keep_blocked"
    assert row["actionability"]["status"] == "non_actionable"
    assert row["actionability"]["reason_codes"] == ["missing_reason_refs"]


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = failure_action.build_failure_action_from_basket(
        repo_root=tmp_path,
        max_candidates=1,
    )
    markdown = failure_action.render_operator_summary(report)
    paths = failure_action.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Failure Action From Basket Evidence" in markdown
    assert "## 2. Actionability counts" in markdown
    assert paths["latest"] == "logs/qre_failure_action_from_basket/latest.json"
    assert paths["operator_summary"] == "logs/qre_failure_action_from_basket/operator_summary.md"
