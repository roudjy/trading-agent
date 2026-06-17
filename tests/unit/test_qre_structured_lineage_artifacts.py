from __future__ import annotations

import json
from pathlib import Path

from research import qre_structured_lineage_artifacts as lineage


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-lineage-001",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "approval-001",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": [
            "logs/qre_structured_lineage_artifacts/",
            "logs/qre_bounded_current_basket_generation_runner/",
        ],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-17T16:25:00Z",
        "source": "operator_approval_manifest",
    }


def test_structured_lineage_artifacts_are_deterministic_and_provisional() -> None:
    first = lineage.build_structured_lineage_artifacts(_request_payload())
    second = lineage.build_structured_lineage_artifacts(_request_payload())

    assert first == second
    assert first["report_kind"] == lineage.REPORT_KIND
    assert first["summary"]["final_recommendation"] == "structured_lineage_artifacts_provisional_no_real_evidence"
    assert first["summary"]["artifact_count"] == 2
    assert first["summary"]["provisional_count"] == 2


def test_structured_lineage_artifacts_reject_fake_campaign_identity() -> None:
    report = lineage.build_structured_lineage_artifacts(_request_payload())
    row = report["rows"][0]

    assert row["candidate_id"] == ""
    assert row["campaign_id"] == ""
    assert row["grid_run_id"] == ""
    assert "missing_candidate_id" in row["rejection_reasons"]
    assert "missing_campaign_id" in row["rejection_reasons"]
    assert "missing_grid_run_id" in row["rejection_reasons"]
    assert row["accepted_for_campaign_lineage"] is False
    assert row["can_clear_campaign_lineage_missing"] is False


def test_structured_lineage_artifacts_write_outputs_are_allowlisted(tmp_path: Path) -> None:
    report = lineage.build_structured_lineage_artifacts(_request_payload())
    paths = lineage.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_structured_lineage_artifacts/latest.json"
    assert paths["operator_summary"] == "logs/qre_structured_lineage_artifacts/operator_summary.md"
    payload = json.loads((tmp_path / "logs" / "qre_structured_lineage_artifacts" / "latest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["final_recommendation"] == "structured_lineage_artifacts_provisional_no_real_evidence"

