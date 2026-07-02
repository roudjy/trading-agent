from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_candidate_operator_trust_review as trust
from research import qre_empirical_trust_closure as closure

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_candidate_operator_trust_audit_separates_portfolio_and_empirical_outcomes() -> None:
    report = trust.build_candidate_operator_trust_report(repo_root=REPO_ROOT)

    audit = report["pr3_evidence_integrity_audit"]
    corrected = audit["corrected_longitudinal_evidence"]
    readiness = report["readiness_decisions"]
    consistency = report["summary_artifact_consistency"]

    assert corrected["portfolio_planning_cycles"] >= 2
    assert corrected["empirical_research_cycles"] >= 1
    assert corrected["empirical_terminal_dispositions"] >= 1
    assert corrected["portfolio_admission_decisions"] >= 0
    assert corrected["suppressed_duplicate_decisions"] >= 0
    assert corrected["resolved_historical_blockers"] == ["DATA_OR_OOS_CAPACITY_BLOCKED"]
    assert corrected["active_contradictions"] == ["REQUEST_MORE_EVIDENCE"]
    assert readiness["operator_trust_readiness"] == "PASS"
    assert readiness["shadow_readiness"] == "INSUFFICIENT_HISTORY"
    assert readiness["pr5_entrygate_satisfied"] is False
    assert consistency["status"] == "PASS"
    assert audit["issues"]["portfolio_outcomes_vs_empirical_outcomes"]["before"]["portfolio_outcomes_reported_as_terminal_outcomes"] == 4


def test_candidate_operator_trust_acceptance_cycles_are_deterministic() -> None:
    report = trust.build_candidate_operator_trust_report(repo_root=REPO_ROOT)

    acceptance = report["acceptance_cycles"]
    rows = acceptance["rows"]

    assert len(rows) >= 5
    assert acceptance["deterministic_replay"] is True
    assert sum(1 for row in rows if row.get("cycle_kind") == "evidence_changing_acceptance_cycle") >= 2
    assert sum(1 for row in rows if row.get("cycle_kind") == "deterministic_acceptance_replay") >= 3


def test_candidate_operator_trust_falls_back_when_runtime_logs_are_missing(monkeypatch) -> None:
    real_read_json = trust._read_json

    def _read_without_logs(path: Path) -> dict[str, object]:
        if "logs/" in path.as_posix().replace("\\", "/"):
            return {}
        return real_read_json(path)

    monkeypatch.setattr(trust, "_read_json", _read_without_logs)

    report = trust.build_candidate_operator_trust_report(repo_root=REPO_ROOT)
    corrected = report["pr3_evidence_integrity_audit"]["corrected_longitudinal_evidence"]

    assert corrected["portfolio_planning_cycles"] >= 2
    assert corrected["empirical_research_cycles"] >= 1
    assert report["readiness_decisions"]["operator_trust_readiness"] == "PASS"


def test_candidate_operator_trust_ignores_noncanonical_runtime_scheduler_logs(monkeypatch) -> None:
    real_read_json = trust._read_json

    def _read_with_noncanonical_scheduler(path: Path) -> dict[str, object]:
        normalized = path.as_posix().replace("\\", "/")
        if normalized.endswith("logs/qre_historical_portfolio_scheduler/latest.json"):
            return {
                "report_kind": "qre_historical_portfolio_scheduler",
                "summary": {
                    "candidate_count": 1,
                    "cycle_count": 1,
                    "admitted_count": 1,
                    "duplicate_suppressed_count": 0,
                },
                "terminal_outcomes": [
                    {
                        "candidate_variant_id": "fixture_candidate",
                        "admission_status": "ADMITTED",
                    }
                ],
            }
        return real_read_json(path)

    monkeypatch.setattr(trust, "_read_json", _read_with_noncanonical_scheduler)

    report = trust.build_candidate_operator_trust_report(repo_root=REPO_ROOT)
    corrected = report["pr3_evidence_integrity_audit"]["corrected_longitudinal_evidence"]

    assert corrected["portfolio_planning_cycles"] >= 2
    assert corrected["portfolio_admission_decisions"] >= 0
    assert report["readiness_decisions"]["operator_trust_readiness"] == "PASS"


def test_candidate_operator_trust_policy_and_recovery_fail_closed() -> None:
    report = trust.build_candidate_operator_trust_report(repo_root=REPO_ROOT)

    policy = report["operator_trust_policy"]
    recovery = report["recovery_validation"]
    readiness = report["readiness_decisions"]

    assert policy["policy_version"] == "1.1"
    assert policy["minimum_real_empirical_campaigns"] == 5
    assert policy["minimum_distinct_real_hypotheses"] == 3
    assert len(recovery["rows"]) == 10
    assert all(row["pass"] is True for row in recovery["rows"])
    assert readiness["candidate_maturity_readiness"] == "INSUFFICIENT_HISTORY"
    assert readiness["operator_trust_readiness"] == "PASS"
    assert readiness["insufficient_history_criteria"] == []


def test_candidate_operator_trust_review_writes_sidecars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(trust, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(trust, "ARTIFACT_DIR", tmp_path / "logs" / "qre_candidate_operator_trust_review")
    monkeypatch.setattr(trust, "LATEST_JSON", tmp_path / "logs" / "qre_candidate_operator_trust_review" / "latest.json")
    monkeypatch.setattr(trust, "LATEST_MD", tmp_path / "logs" / "qre_candidate_operator_trust_review" / "latest.md")

    payload = trust.run_candidate_operator_trust_review(repo_root=REPO_ROOT, write_outputs_flag=True)
    paths = payload["_artifact_paths"]

    assert paths["latest_json"] == "logs/qre_candidate_operator_trust_review/latest.json"
    assert paths["latest_markdown"] == "logs/qre_candidate_operator_trust_review/latest.md"
    assert (tmp_path / paths["latest_json"]).is_file()
    assert (tmp_path / paths["candidate_inventory.json"]).is_file()
    assert (tmp_path / paths["shadow_readiness.json"]).is_file()


def test_operator_trust_uses_cumulative_horizon_not_latest_run_only(tmp_path: Path) -> None:
    _write_json(
        tmp_path / closure.SUMMARY_PATH,
        {
            "attribution_integrity": {"portfolio_planning_cycles": 1},
            "portfolio_plan_summary": {"campaigns_admitted": 0, "exact_duplicates_suppressed": 0},
        },
    )
    _write_json(
        tmp_path / closure.ATTRIBUTION_PATH,
        {
            "summary": {
                "total_real_empirical_campaigns_after": 5,
                "portfolio_planning_cycles": 1,
                "empirical_research_cycles": 5,
                "corrected_new_campaigns_from_pr3": 0,
                "corrected_new_campaigns_from_pr4": 0,
            }
        },
    )
    _write_json(
        tmp_path / closure.EXECUTION_PATH,
        {"rows": [], "summary": {"new_real_campaigns": 0}},
    )
    _write_json(tmp_path / closure.ROUTING_PATH, {"summary": {"measurement_types": ["DERIVED"]}})
    _write_json(tmp_path / closure.SAMPLING_PATH, {"summary": {"measurement_types": ["MEASURED"]}})
    _write_json(
        tmp_path / closure.ACTION_PATH,
        {"summary": {"actions_proposed": 5, "actions_executed": 5, "actions_effective": 2}},
    )
    _write_json(
        tmp_path / closure.ACCEPTANCE_PATH,
        {
            "summary": {
                "evidence_changing_acceptance_cycle_count": 0,
                "deterministic_acceptance_replay_count": 3,
            },
            "rows": [{"cycle_kind": "deterministic_acceptance_replay", "exact_match": True}] * 3,
        },
    )
    _write_json(
        tmp_path / closure.TRUST_HORIZON_PATH,
        {
            "cumulative_campaign_count": 5,
            "cumulative_hypothesis_count": 3,
            "cumulative_family_count": 3,
            "cumulative_evidence_changing_cycle_count": 3,
            "cumulative_replay_count": 3,
        },
    )
    _write_json(
        tmp_path / closure.TRUST_HORIZON_LATEST_RUN_PATH,
        {
            "latest_run_new_campaign_count": 0,
            "latest_run_new_evidence_cycle_count": 0,
            "latest_run_replay_count": 3,
        },
    )
    _write_json(tmp_path / closure.TRUST_HORIZON_CONSISTENCY_PATH, {"status": "PASS"})
    _write_json(tmp_path / closure.POLICY_PATH, closure.build_operator_trust_policy_v1_1())
    _write_json(
        tmp_path / closure.CAMPAIGN_HISTORY_PATH,
        {
            "rows": [
                {"campaign_identity": "qcx_1", "source_hypothesis_id": "h1", "mechanism_family": "f1"},
                {"campaign_identity": "qcx_2", "source_hypothesis_id": "h2", "mechanism_family": "f2"},
                {"campaign_identity": "qcx_3", "source_hypothesis_id": "h3", "mechanism_family": "f3"},
                {"campaign_identity": "qcx_4", "source_hypothesis_id": "h1", "mechanism_family": "f1"},
                {"campaign_identity": "qcx_5", "source_hypothesis_id": "h2", "mechanism_family": "f2"},
            ]
        },
    )
    _write_json(
        tmp_path / closure.LINEAGE_PATH,
        {"rows": [{"campaign_identity": f"qcx_{index}"} for index in range(1, 6)]},
    )
    _write_json(
        tmp_path / closure.REASON_RECORDS_PATH,
        {"rows": [{"reason_record_id": f"rr_{index}"} for index in range(1, 11)]},
    )
    _write_json(
        tmp_path / "logs/qre_decision_calibration_review/latest.json",
        {"decision_quality_kpis": {"false_synthesis_ready_count": 0}},
    )
    _write_json(
        tmp_path / "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json",
        {"resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"], "active_blockers": ["REQUEST_MORE_EVIDENCE"]},
    )

    report = trust.build_candidate_operator_trust_report(repo_root=tmp_path)

    assert report["readiness_decisions"]["operator_trust_readiness"] == "PASS"
    assert report["readiness_decisions"]["shadow_readiness"] == "INSUFFICIENT_HISTORY"
    assert report["acceptance_cycles"]["final_criteria"]["evidence-changing cycles"]["actual"] == {
        "cumulative": 3,
        "latest_run": 0,
    }
