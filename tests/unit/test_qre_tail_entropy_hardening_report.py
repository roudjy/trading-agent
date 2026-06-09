from pathlib import Path

import pytest

from research.qre_tail_entropy_hardening_report import (
    build_tail_entropy_hardening_report,
    render_operator_summary,
    write_outputs,
)


def test_tail_entropy_report_is_ready_and_context_only():
    report = build_tail_entropy_hardening_report()

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_tail_entropy_hardening_report"
    assert report["summary"]["tail_entropy_hardening_ready"] is True
    assert report["summary"]["final_recommendation"] == "tail_entropy_hardening_scaffold_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_candidate_state"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["promotion_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True


def test_tail_entropy_report_has_diagnostics_and_counts():
    report = build_tail_entropy_hardening_report()

    assert report["summary"]["observation_set_count"] == 3
    assert report["summary"]["diagnostic_count"] == 3
    assert len(report["diagnostics"]) == 3
    assert "risk_state_counts" in report["summary"]
    assert "tail_entropy_blocked" in report["summary"]["risk_state_counts"]


def test_tail_entropy_report_accepts_custom_observation_sets():
    report = build_tail_entropy_hardening_report(
        observation_sets=[
            {
                "subject_id": "candidate:custom",
                "observations": [0.90, 0.01, -0.01, 0.01, -0.01, 0.01],
                "description": "custom concentrated sample",
            }
        ]
    )

    assert report["summary"]["observation_set_count"] == 1
    assert report["diagnostics"][0]["risk_state"] == "tail_entropy_blocked"


def test_tail_entropy_operator_summary_renders():
    report = build_tail_entropy_hardening_report()
    text = render_operator_summary(report)

    assert "# QRE Tail Entropy Hardening" in text
    assert "final_recommendation" in text
    assert "tail_entropy_hardening_scaffold_ready" in text


def test_tail_entropy_write_outputs_stays_in_allowlist(tmp_path: Path):
    report = build_tail_entropy_hardening_report()
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_tail_entropy_hardening/latest.json"
    assert paths["operator_summary"] == "logs/qre_tail_entropy_hardening/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_tail_entropy_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_tail_entropy_hardening_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    report = build_tail_entropy_hardening_report()

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)