from __future__ import annotations

import json
from pathlib import Path

from research import qre_shadow_readiness_gates as gates


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_reports(
    tmp_path: Path,
    *,
    accepted_oos_count: int = 0,
    evidence_complete_count: int = 0,
    eligible_candidate_count: int = 0,
    null_status: str = "controls_incomplete",
    source_quality_ready: bool = True,
    operational_ready: bool = True,
    review_present: bool = True,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_evidence_breadth_framework" / "latest.json",
        {
            "report_kind": "qre_evidence_breadth_framework",
            "summary": {"status": "ready", "accepted_oos_ref_count": accepted_oos_count},
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_candidate_quality_framework" / "latest.json",
        {
            "report_kind": "qre_candidate_quality_framework",
            "summary": {
                "status": (
                    "eligible_for_operator_quality_review"
                    if eligible_candidate_count
                    else "blocked_evidence_incomplete"
                ),
                "eligible_candidate_count": eligible_candidate_count,
            },
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_candidate_identity_lifecycle" / "latest.json",
        {
            "report_kind": "qre_candidate_identity_lifecycle",
            "summary": {
                "candidate_count": 3,
                "evidence_complete_count": evidence_complete_count,
                "status_counts": {"evidence_incomplete": 3},
            },
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_null_control_falsification_suite" / "latest.json",
        {
            "report_kind": "qre_null_control_falsification_suite",
            "status": "suite_ready_preregistered_context",
            "evaluation": {"status": null_status},
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_trusted_loop_operational_controls" / "latest.json",
        {
            "report_kind": "qre_trusted_loop_operational_controls",
            "summary": {"trusted_loop_operational_controls_ready": operational_ready},
            "resumability": {"idempotent_reentry_ready": operational_ready, "resumable": operational_ready},
            "replayability": {"rerun_comparison_ready": operational_ready},
        },
    )
    if review_present:
        _write_json(
            tmp_path / "logs" / "qre_trusted_loop_review" / "latest.json",
            {
                "report_kind": "qre_trusted_loop_review_packet",
                "summary": {
                    "trust_verdict": "read_only_context_fail_closed",
                    "trust_blocker_count": 4,
                    "final_recommendation": "trusted_loop_operator_review_required",
                },
            },
        )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [{"symbol": "AAPL", "quality_status": "ready"}],
            "summary": {"ready_row_count": 1, "research_ready": source_quality_ready},
            "report_kind": "qre_data_source_quality_readiness",
            "status": "ready" if source_quality_ready else "not_ready",
        },
    )


def test_shadow_readiness_gates_fail_closed_on_missing_oos_and_evidence_complete(tmp_path: Path) -> None:
    _seed_reports(tmp_path)

    report = gates.build_shadow_readiness_gates(repo_root=tmp_path)

    assert report["summary"]["readiness_status"] == "shadow_readiness_deferred"
    assert report["summary"]["shadow_ready"] is False
    assert report["summary"]["can_activate_shadow"] is False
    blocker_codes = [row["blocker_code"] for row in report["blockers"]]
    assert "accepted_oos_missing" in blocker_codes
    assert "evidence_complete_scope_missing" in blocker_codes
    assert report["summary"]["exact_next_action"] == "produce_accepted_oos_and_evidence_complete_scope"


def test_shadow_readiness_gates_stay_false_without_operator_approval(tmp_path: Path) -> None:
    _seed_reports(
        tmp_path,
        accepted_oos_count=2,
        evidence_complete_count=1,
        eligible_candidate_count=1,
        null_status="controls_passed_context_only",
        source_quality_ready=True,
        operational_ready=True,
        review_present=True,
    )

    report = gates.build_shadow_readiness_gates(repo_root=tmp_path)

    assert report["summary"]["shadow_ready"] is False
    assert report["summary"]["can_activate_shadow"] is False
    blocker_codes = [row["blocker_code"] for row in report["blockers"]]
    assert blocker_codes == ["operator_shadow_approval_missing"]
    assert report["summary"]["exact_next_action"] == "retain_read_only_mode_until_explicit_operator_shadow_approval"


def test_shadow_readiness_gate_outputs_stay_in_allowlist(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    report = gates.build_shadow_readiness_gates(repo_root=tmp_path)

    paths = gates.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_shadow_readiness_gates/latest.json"
    assert paths["operator_summary"] == "logs/qre_shadow_readiness_gates/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
