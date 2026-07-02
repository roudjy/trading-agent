from __future__ import annotations

from pathlib import Path

from reporting import qre_candidate_operator_trust_review as trust

REPO_ROOT = Path(__file__).resolve().parents[2]


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
