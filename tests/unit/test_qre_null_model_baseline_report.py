from pathlib import Path

import pytest

from research.qre_null_model_baseline_report import (
    build_null_model_baseline_report,
    render_operator_summary,
    write_outputs,
)


def test_null_model_baseline_report_is_ready_and_context_only():
    report = build_null_model_baseline_report()

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_null_model_baseline_report"
    assert report["summary"]["null_model_baseline_ready"] is True
    assert report["summary"]["final_recommendation"] == "null_model_baseline_scaffold_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["promotion_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True


def test_null_model_baseline_report_has_sample_comparisons():
    report = build_null_model_baseline_report()

    assert report["summary"]["sample_row_count"] == 3
    assert len(report["sample_comparisons"]) == 3
    assert "sample_comparison_counts" in report["summary"]


def test_null_model_baseline_operator_summary_renders():
    report = build_null_model_baseline_report()
    text = render_operator_summary(report)

    assert "# QRE Null Model Baseline" in text
    assert "final_recommendation" in text
    assert "null_model_baseline_scaffold_ready" in text


def test_null_model_baseline_write_outputs_stays_in_allowlist(tmp_path: Path):
    report = build_null_model_baseline_report()
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_null_model_baseline/latest.json"
    assert paths["operator_summary"] == "logs/qre_null_model_baseline/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_null_model_baseline_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_null_model_baseline_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    report = build_null_model_baseline_report()

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)