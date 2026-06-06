from __future__ import annotations

import json
from pathlib import Path

from research import qre_hypothesis_seed_feasibility as feasibility


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


def test_build_hypothesis_seed_feasibility_marks_trend_pullback_as_feasible(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = feasibility.build_hypothesis_seed_feasibility(
        repo_root=tmp_path,
        max_candidates=15,
    )

    rows = {row["hypothesis_id"]: row for row in report["rows"]}
    row = rows["trend_pullback_behavior_v1"]
    assert row["feasibility_state"] == "feasible_for_readonly_research"
    assert row["maps_to_basket"] is True
    assert row["data_ready"] is True
    assert row["source_ready"] is True
    assert row["catalog_bridge_status"] == "linked_catalog_active_discovery"


def test_build_hypothesis_seed_feasibility_keeps_source_identity_blocked_seed_explicit(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = feasibility.build_hypothesis_seed_feasibility(
        repo_root=tmp_path,
        max_candidates=15,
    )

    rows = {row["hypothesis_id"]: row for row in report["rows"]}
    row = rows["relative_strength_sector_behavior_v1"]
    assert row["feasibility_state"] == "blocked_source_identity"
    assert row["recommended_follow_up"] == "require_identity_resolution"


def test_build_hypothesis_seed_feasibility_distinguishes_seed_only_hypotheses(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = feasibility.build_hypothesis_seed_feasibility(
        repo_root=tmp_path,
        max_candidates=15,
    )

    rows = {row["hypothesis_id"]: row for row in report["rows"]}
    row = rows["relative_strength_region_behavior_v1"]
    assert row["catalog_bridge_status"] == "seed_only_no_executable_hypothesis"
    assert row["maps_to_basket"] is True


def test_build_behavior_family_coverage_summarizes_feasible_and_blocked_families(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = feasibility.build_hypothesis_seed_feasibility(
        repo_root=tmp_path,
        max_candidates=15,
    )
    coverage = feasibility.build_behavior_family_coverage(report)

    rows = {row["behavior_family"]: row for row in coverage["rows"]}
    assert rows["trend_pullback"]["feasible_seed_count"] == 1
    assert rows["relative_strength_sector"]["blocked_seed_count"] == 1


def test_write_outputs_materializes_feasibility_and_behavior_reports(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = feasibility.build_hypothesis_seed_feasibility(
        repo_root=tmp_path,
        max_candidates=15,
    )
    paths = feasibility.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_hypothesis_seed_feasibility/latest.json"
    assert paths["behavior_family_coverage"] == "logs/qre_behavior_family_coverage/latest.json"
