from pathlib import Path

import pytest

from research.qre_sampling_calibration_report import (
    build_sampling_calibration_report,
    render_operator_summary,
    write_outputs,
)


def test_sampling_calibration_report_is_ready_and_context_only():
    report = build_sampling_calibration_report()

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_sampling_calibration_report"
    assert report["summary"]["sampling_calibration_ready"] is True
    assert report["summary"]["final_recommendation"] == "sampling_calibration_scaffold_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_campaigns"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_presets"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["promotion_forbidden"] is True
    assert safety["campaign_mutation_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True


def test_sampling_calibration_report_excludes_crypto_and_prefers_equity_axes():
    report = build_sampling_calibration_report()

    assert report["summary"]["input_row_count"] == 5
    assert report["summary"]["calibration_count"] == 5
    assert report["summary"]["crypto_legacy_excluded_count"] == 1

    decision_counts = report["summary"]["sampling_decision_counts"]
    assert decision_counts["exclude_sampling"] >= 1
    assert decision_counts["prefer_sampling"] >= 1

    preferred_axes = report["summary"]["preferred_axis_counts"]
    assert preferred_axes["asset_class:fundamental_equity"] >= 1
    assert preferred_axes["region:netherlands"] >= 1


def test_sampling_calibration_report_accepts_custom_rows():
    report = build_sampling_calibration_report(
        rows=[
            {
                "subject_id": "candidate:custom",
                "asset_class": "fundamental_equity",
                "research_scope": "target_equity_research",
                "readiness_state": "ready",
                "title": "Europe factor source_manifest",
            }
        ]
    )

    assert report["summary"]["input_row_count"] == 1
    assert report["calibrations"][0]["sampling_decision"] == "prefer_sampling"


def test_sampling_calibration_operator_summary_renders():
    report = build_sampling_calibration_report()
    text = render_operator_summary(report)

    assert "# QRE Sampling Calibration" in text
    assert "crypto_legacy_excluded_count" in text
    assert "sampling_calibration_scaffold_ready" in text


def test_sampling_calibration_write_outputs_stays_in_allowlist(tmp_path: Path):
    report = build_sampling_calibration_report()
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_sampling_calibration/latest.json"
    assert paths["operator_summary"] == "logs/qre_sampling_calibration/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_sampling_calibration_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_sampling_calibration_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    report = build_sampling_calibration_report()

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)