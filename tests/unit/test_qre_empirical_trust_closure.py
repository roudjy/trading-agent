from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_candidate_operator_trust_review as trust
from research import qre_empirical_trust_closure as etc


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_policy_v1_1_raises_empirical_floors() -> None:
    policy = etc.build_operator_trust_policy_v1_1()

    assert policy["policy_id"] == "qre_operator_trust_policy_v1_1"
    assert policy["policy_version"] == "1.1"
    assert policy["minimum_real_empirical_campaigns"] == 5
    assert policy["minimum_distinct_real_hypotheses"] == 3
    assert policy["minimum_distinct_mechanism_families"] == 3
    assert policy["minimum_evidence_changing_acceptance_cycles"] == 2
    assert policy["minimum_deterministic_acceptance_replays"] == 3


def test_acceptance_history_separates_evidence_changes_and_replays() -> None:
    before = [{"campaign_identity": "qcx_old"}]
    after = [{"campaign_identity": "qcx_old"}, {"campaign_identity": "qcx_new"}]

    payload = etc._build_acceptance_history(before, after)

    assert payload["summary"]["independent_empirical_research_cycle_count"] == 1
    assert payload["summary"]["evidence_changing_acceptance_cycle_count"] == 1
    assert payload["summary"]["deterministic_acceptance_replay_count"] == 3
    assert payload["rows"][0]["cycle_kind"] == "evidence_changing_acceptance_cycle"
    assert payload["rows"][0]["changed_evidence"] is True
    assert all(row["cycle_kind"] == "deterministic_acceptance_replay" for row in payload["rows"][1:])


def test_build_plan_blocks_identical_frozen_campaign_without_novelty(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "generated_research/registry/generated_strategy_registry.v1.json",
        {
            "rows": [
                {
                    "generated_strategy_id": "qgs_alpha",
                    "source_hypothesis_id": "alpha_v0",
                    "strategy_spec_id": "qsp_alpha",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "generated_research/specs/qsp_alpha.json",
        {
            "behavior_family": "trend_pullback",
            "source_hypothesis_id": "alpha_v0",
        },
    )
    _write_json(
        tmp_path / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {
            "rows": [
                {
                    "campaign_cell_id": "qrcell_alpha",
                    "generated_strategy_id": "qgs_alpha",
                    "status": "READY_FOR_PREREGISTRATION",
                    "blockers": [],
                }
            ]
        },
    )

    payload = etc._build_plan(
        tmp_path,
        [
            {
                "campaign_cell_id": "qrcell_alpha",
                "campaign_identity": "qcx_prior",
                "source_hypothesis_id": "alpha_v0",
            }
        ],
    )

    assert payload["summary"]["campaigns_admitted"] == 0
    assert payload["summary"]["exact_duplicates_suppressed"] == 1
    assert payload["rows"][0]["novelty"] == "NO_NOVELTY_IDENTICAL_FROZEN_CAMPAIGN"
    assert payload["rows"][0]["reason"] == "identical_frozen_campaign_already_executed"


def test_operator_trust_review_consumes_closure_artifacts_fail_closed(tmp_path: Path) -> None:
    _write_json(
        tmp_path / etc.SUMMARY_PATH,
        {
            "attribution_integrity": {
                "portfolio_planning_cycles": 2,
            },
            "portfolio_plan_summary": {
                "campaigns_admitted": 1,
                "exact_duplicates_suppressed": 1,
            },
        },
    )
    _write_json(
        tmp_path / etc.ATTRIBUTION_PATH,
        {
            "summary": {
                "total_real_empirical_campaigns_after": 2,
                "portfolio_planning_cycles": 2,
                "empirical_research_cycles": 1,
                "corrected_new_campaigns_from_pr3": 0,
                "corrected_new_campaigns_from_pr4": 0,
            }
        },
    )
    _write_json(
        tmp_path / etc.EXECUTION_PATH,
        {
            "summary": {
                "new_real_campaigns": 1,
            }
        },
    )
    _write_json(
        tmp_path / etc.ROUTING_PATH,
        {"summary": {"measurement_types": ["NOT_EVALUABLE"]}},
    )
    _write_json(
        tmp_path / etc.SAMPLING_PATH,
        {"summary": {"measurement_types": ["MEASURED"]}},
    )
    _write_json(
        tmp_path / etc.ACTION_PATH,
        {
            "summary": {
                "actions_proposed": 1,
                "actions_executed": 1,
                "actions_effective": 1,
                "action_mapped_failure_rate": 0.5,
            }
        },
    )
    _write_json(
        tmp_path / etc.ACCEPTANCE_PATH,
        {
            "rows": [
                {"cycle_kind": "evidence_changing_acceptance_cycle", "changed_evidence": True},
                {"cycle_kind": "evidence_changing_acceptance_cycle", "changed_evidence": False},
                {"cycle_kind": "deterministic_acceptance_replay", "exact_match": True},
                {"cycle_kind": "deterministic_acceptance_replay", "exact_match": True},
                {"cycle_kind": "deterministic_acceptance_replay", "exact_match": True},
            ],
            "summary": {
                "evidence_changing_acceptance_cycle_count": 1,
                "deterministic_acceptance_replay_count": 3,
            },
        },
    )
    _write_json(
        tmp_path / etc.POLICY_PATH,
        etc.build_operator_trust_policy_v1_1(),
    )
    _write_json(
        tmp_path / etc.CAMPAIGN_HISTORY_PATH,
        {
            "rows": [
                {"campaign_identity": "qcx_old", "source_hypothesis_id": "cross_v0", "mechanism_family": "relative_strength"},
                {"campaign_identity": "qcx_new", "source_hypothesis_id": "atr_v0", "mechanism_family": "trend_continuation"},
            ]
        },
    )
    _write_json(
        tmp_path / etc.LINEAGE_PATH,
        {"rows": [{"campaign_identity": "qcx_old"}, {"campaign_identity": "qcx_new"}]},
    )
    _write_json(
        tmp_path / etc.REASON_RECORDS_PATH,
        {"rows": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]},
    )
    _write_json(
        tmp_path / "logs/qre_decision_calibration_review/latest.json",
        {
            "decision_quality_kpis": {
                "false_synthesis_ready_count": 0,
            }
        },
    )
    _write_json(
        tmp_path / "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json",
        {
            "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
            "active_blockers": ["REQUEST_MORE_EVIDENCE"],
        },
    )

    report = trust.build_candidate_operator_trust_report(repo_root=tmp_path)

    assert report["operator_trust_policy"]["policy_version"] == "1.1"
    assert report["readiness_decisions"]["operator_trust_readiness"] == "INSUFFICIENT_HISTORY"
    assert report["readiness_decisions"]["shadow_readiness"] == "INSUFFICIENT_HISTORY"
    assert "real campaigns" in report["readiness_decisions"]["insufficient_history_criteria"]
    assert report["acceptance_cycles"]["deterministic_replay"] is True
