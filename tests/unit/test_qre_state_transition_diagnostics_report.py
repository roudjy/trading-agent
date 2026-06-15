from pathlib import Path

import pytest

from research.qre_state_transition_diagnostics_report import (
    build_state_transition_diagnostics_report,
    render_operator_summary,
    write_outputs,
)


def test_state_transition_report_is_ready_and_context_only():
    report = build_state_transition_diagnostics_report()

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_state_transition_diagnostics_report"
    assert report["summary"]["state_transition_diagnostics_ready"] is True
    assert report["summary"]["final_recommendation"] == "state_transition_sequence_duration_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_candidate_state"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["sparse_data_fails_closed"] is True
    assert safety["promotion_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True


def test_state_transition_report_has_diagnostics_and_counts():
    report = build_state_transition_diagnostics_report()

    assert report["summary"]["transition_row_count"] == 3
    assert report["summary"]["diagnostic_count"] == 3
    assert len(report["diagnostics"]) == 3
    assert report["summary"]["sequence_row_count"] == 7
    assert report["summary"]["sequence_diagnostic_count"] == 2
    assert len(report["sequence_diagnostics"]) == 2
    assert "positive_progress_transition" in report["summary"]["transition_state_counts"]
    assert "terminal_negative_transition" in report["summary"]["transition_state_counts"]
    assert "ready" in report["summary"]["sequence_state_counts"]


def test_state_transition_report_accepts_custom_rows():
    report = build_state_transition_diagnostics_report(
        transition_rows=[
            {
                "subject_id": "candidate:custom",
                "prior_state": "screened",
                "new_state": "fail_closed",
                "transition_reason": "lineage_missing",
            }
        ]
    )

    assert report["summary"]["transition_row_count"] == 1
    assert report["diagnostics"][0]["transition_state"] == "terminal_negative_transition"


def test_state_transition_report_accepts_sparse_sequence_rows():
    report = build_state_transition_diagnostics_report(
        sequence_rows=[
            {
                "subject_id": "candidate:sparse",
                "step_index": 1,
                "state": "candidate_discovered",
            }
        ]
    )

    assert report["summary"]["sequence_row_count"] == 1
    assert report["summary"]["sparse_sequence_count"] == 1
    assert report["sequence_diagnostics"][0]["sequence_state"] == "blocked"


def test_state_transition_operator_summary_renders():
    report = build_state_transition_diagnostics_report()
    text = render_operator_summary(report)

    assert "# QRE State Transition Diagnostics" in text
    assert "final_recommendation" in text
    assert "state_transition_sequence_duration_ready" in text


def test_state_transition_write_outputs_stays_in_allowlist(tmp_path: Path):
    report = build_state_transition_diagnostics_report()
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_state_transition_diagnostics/latest.json"
    assert paths["operator_summary"] == "logs/qre_state_transition_diagnostics/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_state_transition_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_state_transition_diagnostics_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    report = build_state_transition_diagnostics_report()

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)
