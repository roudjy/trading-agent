from pathlib import Path

import pytest

from research.qre_routing_calibration_report import (
    build_routing_calibration_report,
    render_operator_summary,
    write_outputs,
)


def test_routing_calibration_report_is_ready_and_context_only():
    report = build_routing_calibration_report()

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_routing_calibration_report"
    assert report["summary"]["routing_calibration_ready"] is True
    assert report["summary"]["final_recommendation"] == "routing_calibration_scaffold_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_queues"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_campaigns"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_presets"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["queue_mutation_forbidden"] is True
    assert safety["promotion_forbidden"] is True
    assert safety["campaign_mutation_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True


def test_routing_calibration_report_has_expected_targets():
    report = build_routing_calibration_report()

    assert report["summary"]["input_row_count"] == 5
    assert report["summary"]["calibration_count"] == 5
    assert report["summary"]["excluded_scope_archive_count"] == 1

    target_counts = report["summary"]["routing_target_counts"]
    assert target_counts["excluded_scope_archive"] == 1
    assert target_counts["sampling_calibration"] >= 4
    assert target_counts["source_quality"] >= 1
    assert target_counts["identity_resolution"] >= 1
    assert target_counts["factor_coverage"] >= 1
    assert target_counts["null_model_baseline"] >= 1
    assert target_counts["state_transition_diagnostics"] >= 1
    assert target_counts["tail_entropy_hardening"] >= 1
    assert target_counts["failure_retrieval"] >= 1


def test_routing_calibration_report_accepts_custom_rows():
    report = build_routing_calibration_report(
        rows=[
            {
                "subject_id": "candidate:custom",
                "asset_class": "equity",
                "research_scope": "target_equity_research",
                "title": "tail entropy state transition",
            }
        ]
    )

    assert report["summary"]["input_row_count"] == 1
    assert "tail_entropy_hardening" in report["calibrations"][0]["routing_targets"]
    assert "state_transition_diagnostics" in report["calibrations"][0]["routing_targets"]


def test_routing_calibration_operator_summary_renders():
    report = build_routing_calibration_report()
    text = render_operator_summary(report)

    assert "# QRE Routing Calibration" in text
    assert "excluded_scope_archive_count" in text
    assert "routing_calibration_scaffold_ready" in text


def test_routing_calibration_write_outputs_stays_in_allowlist(tmp_path: Path):
    report = build_routing_calibration_report()
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_routing_calibration/latest.json"
    assert paths["operator_summary"] == "logs/qre_routing_calibration/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_routing_calibration_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_routing_calibration_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    report = build_routing_calibration_report()

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)