from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_routing_decision_quality as routing_quality
from research import qre_sampling_decision_quality as sampling_quality


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


def test_build_routing_decision_quality_marks_ready_row_as_sound(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = routing_quality.build_routing_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    row = rows["AAPL"]
    assert row["decision_quality_state"] == "ready_sound"
    assert row["routing_false_ready"] is False
    assert row["evidence_follow_through"] is True
    assert report["summary"]["routing_false_ready_count"] == 0


def test_build_routing_decision_quality_counts_duplicate_avoidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)
    baseline = routing_quality.build_routing_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )
    aapl_id = next(
        row["candidate_id"] for row in baseline["rows"] if row["symbol"] == "AAPL"
    )

    def _patched_failure_action(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {
            "rows": [
                {
                    "candidate_id": aapl_id,
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "recommended_action": "defer_as_duplicate",
                    "actionability": {"status": "actionable", "reason_codes": ["duplicate"]},
                }
            ]
        }

    monkeypatch.setattr(
        routing_quality.failure_action,
        "build_failure_action_from_basket",
        _patched_failure_action,
    )

    report = routing_quality.build_routing_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["summary"]["duplicate_avoidance_count"] == 1


def test_build_routing_decision_quality_fails_closed_without_reason_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    def _empty_reason_records(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {"records": []}

    monkeypatch.setattr(
        routing_quality.reason_records,
        "build_reason_records_snapshot",
        _empty_reason_records,
    )

    report = routing_quality.build_routing_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )

    row = next(item for item in report["rows"] if item["symbol"] == "AAPL")
    assert row["routing_false_ready"] is True
    assert "missing_reason_refs" in row["quality_reason_codes"]
    assert report["summary"]["final_recommendation"] == "routing_false_ready_items_present"


def test_build_sampling_decision_quality_marks_ready_row_as_sound(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = sampling_quality.build_sampling_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    row = rows["AAPL"]
    assert row["decision_quality_state"] == "ready_sound"
    assert row["sampling_false_ready"] is False
    assert row["evidence_follow_through"] is True
    assert report["summary"]["sampling_false_ready_count"] == 0


def test_build_sampling_decision_quality_flags_missing_oos_visibility_as_false_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)
    baseline = sampling_quality.build_sampling_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )
    aapl_id = next(
        row["candidate_id"] for row in baseline["rows"] if row["symbol"] == "AAPL"
    )

    def _patched_oos(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {
            "rows": [
                {
                    "candidate_id": aapl_id,
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "oos_status": "oos_evidence_missing",
                    "oos_blocker_class": "oos_evidence_missing",
                }
            ]
        }

    monkeypatch.setattr(
        sampling_quality.oos_blockers,
        "build_oos_evidence_blockers",
        _patched_oos,
    )

    report = sampling_quality.build_sampling_decision_quality(
        repo_root=tmp_path,
        max_candidates=2,
    )

    row = next(item for item in report["rows"] if item["symbol"] == "AAPL")
    assert row["sampling_false_ready"] is True
    assert "sampling_ready_without_oos_visibility" in row["quality_reason_codes"]


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    routing_report = routing_quality.build_routing_decision_quality(
        repo_root=tmp_path,
        max_candidates=1,
    )
    routing_markdown = routing_quality.render_operator_summary(routing_report)
    routing_paths = routing_quality.write_outputs(routing_report, repo_root=tmp_path)

    sampling_report = sampling_quality.build_sampling_decision_quality(
        repo_root=tmp_path,
        max_candidates=1,
    )
    sampling_markdown = sampling_quality.render_operator_summary(sampling_report)
    sampling_paths = sampling_quality.write_outputs(sampling_report, repo_root=tmp_path)

    assert "# QRE Routing Decision Quality Audit" in routing_markdown
    assert "## 2. Routing decision quality counts" in routing_markdown
    assert routing_paths["latest"] == "logs/qre_routing_decision_quality/latest.json"
    assert routing_paths["operator_summary"] == "logs/qre_routing_decision_quality/operator_summary.md"

    assert "# QRE Sampling Decision Quality Audit" in sampling_markdown
    assert "## 2. Sampling decision quality counts" in sampling_markdown
    assert sampling_paths["latest"] == "logs/qre_sampling_decision_quality/latest.json"
    assert sampling_paths["operator_summary"] == "logs/qre_sampling_decision_quality/operator_summary.md"
