from __future__ import annotations

import json
from pathlib import Path

from research import qre_local_grid_artifact_refresh as refresh


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_refresh_fails_closed_when_grid_directory_is_missing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "grid_runs_scanned_count": 0,
            "baskets_with_matched_grid_rows": 0,
            "next_action_counts": {"run_controlled_discovery_grid": 15},
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_grid_candidate_campaign_lineage_bridge" / "latest.json",
        {
            "summary": {
                "basket_count": 15,
                "next_action_counts": {"restore_or_run_grid_artifacts": 15},
            }
        },
    )

    report = refresh.build_local_grid_artifact_refresh(repo_root=tmp_path)

    assert report["summary"]["grid_runs_directory_status"] == "missing"
    assert report["summary"]["missing_local_grid_artifacts"] is True
    assert report["rows"][0]["exact_next_action"] == "restore_or_copy_grid_run_artifacts"
    assert report["refresh_plan"][0]["manual_human_needed"] is True
    assert report["refresh_plan"][2]["status"] == "pending"


def test_refresh_detects_present_grid_directory_without_running_anything(tmp_path: Path) -> None:
    (tmp_path / "research" / "controlled_discovery_grid_runs" / "RUN-001").mkdir(parents=True)
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "grid_runs_scanned_count": 1,
            "baskets_with_matched_grid_rows": 2,
            "next_action_counts": {"keep_fail_closed": 2},
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_grid_candidate_campaign_lineage_bridge" / "latest.json",
        {
            "summary": {
                "basket_count": 2,
                "next_action_counts": {"keep_fail_closed": 2},
            }
        },
    )

    report = refresh.build_local_grid_artifact_refresh(repo_root=tmp_path)

    assert report["summary"]["grid_runs_directory_status"] == "present"
    assert report["summary"]["grid_run_count"] == 1
    assert report["summary"]["latest_grid_run_id"] == "RUN-001"
    assert report["summary"]["missing_local_grid_artifacts"] is False
    assert report["refresh_plan"][0]["status"] == "not_required"
    assert report["refresh_plan"][2]["status"] == "ready"
    assert report["safety_invariants"]["does_not_run_grid"] is True


def test_refresh_writes_outputs(tmp_path: Path) -> None:
    report = refresh.build_local_grid_artifact_refresh(repo_root=tmp_path)
    paths = refresh.write_outputs(report, repo_root=tmp_path)

    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_local_grid_artifact_refresh/latest.json"
    assert "# QRE Local Controlled Grid Artifact Refresh" in markdown
