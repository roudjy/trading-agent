from __future__ import annotations

import json
from pathlib import Path

from research import qre_structured_oos_artifacts as oos


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-oos-001",
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
            "logs/qre_structured_oos_artifacts/",
            "logs/qre_bounded_current_basket_generation_runner/",
        ],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-17T16:26:00Z",
        "source": "operator_approval_manifest",
    }


def test_structured_oos_artifacts_are_deterministic_and_provisional() -> None:
    first = oos.build_structured_oos_artifacts(_request_payload())
    second = oos.build_structured_oos_artifacts(_request_payload())

    assert first == second
    assert first["report_kind"] == oos.REPORT_KIND
    assert first["summary"]["final_recommendation"] == "structured_oos_artifacts_provisional_no_real_evidence"
    assert first["summary"]["artifact_count"] == 2
    assert first["summary"]["provisional_count"] == 2


def test_structured_oos_artifacts_reject_fake_oos_evidence() -> None:
    report = oos.build_structured_oos_artifacts(_request_payload())
    row = report["rows"][0]

    assert row["oos_window"]["label"] == "provisional_missing"
    assert row["oos_metric_fields"]["oos_trade_count"] is None
    assert row["accepted_for_oos_evidence"] is False
    assert row["can_clear_no_oos_evidence"] is False
    assert "missing_oos_window" in row["rejection_reasons"]
    assert "missing_oos_metric_fields" in row["rejection_reasons"]
    assert "missing_cost_slippage_assumption_refs" in row["rejection_reasons"]


def test_structured_oos_artifacts_write_outputs_are_allowlisted(tmp_path: Path) -> None:
    report = oos.build_structured_oos_artifacts(_request_payload())
    paths = oos.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_structured_oos_artifacts/latest.json"
    assert paths["operator_summary"] == "logs/qre_structured_oos_artifacts/operator_summary.md"
    payload = json.loads((tmp_path / "logs" / "qre_structured_oos_artifacts" / "latest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["final_recommendation"] == "structured_oos_artifacts_provisional_no_real_evidence"
