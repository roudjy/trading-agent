from __future__ import annotations

import json
from pathlib import Path

from research import campaign_preregistered_sampling_plan as proposal

TIMESTAMP = "2026-06-24T08:00:00Z"


def _decision() -> dict[str, object]:
    return {
        "decision_status": "decision_ready",
        "recommended_action": "create_preregistered_sampling_plan",
        "action_authority": "report_only",
        "failure_class": "insufficient_window_length",
        "reason_codes": ["insufficient_window_length"],
        "prerequisites": ["larger_preregistered_local_range"],
        "selected_source": "research/campaign_level_evidence_latest.v1.json",
        "evidence_refs": [
            "research/campaign_level_evidence_latest.v1.json",
            "research/campaign_registry_latest.v1.json",
        ],
        "campaign_scope": {
            "campaign_id": "campaign-alpha",
            "hypothesis_id": "behavior_alpha_v1",
            "preset_name": "alpha_equities_4h",
            "timeframe": "4h",
            "template_id": "daily_primary__alpha_equities_4h",
            "strategy_family": "behavior_alpha",
            "asset_class": "equity",
            "universe": ["MSFT", "AAPL"],
            "lineage_root_campaign_id": "campaign-alpha",
            "parent_campaign_id": "",
            "registry_record_present": True,
        },
        "safety_invariants": {
            key: False for key in proposal.SAFETY_KEYS
        },
    }


def test_eligible_decision_builds_report_only_coverage_proposal() -> None:
    report = proposal.build_campaign_preregistered_sampling_plan(
        decision=_decision(),
        preregistration_timestamp=TIMESTAMP,
    )

    assert report["proposal_status"] == "proposal_ready_coverage_required"
    assert report["campaign_scope"]["campaign_id"] == "campaign-alpha"
    assert report["campaign_scope"]["universe"] == ["AAPL", "MSFT"]
    assert report["coverage_requirements"]["minimum_common_trading_dates"] == 40
    assert report["sampling_plan"]["behavior_id"] == "behavior_alpha"
    assert report["sampling_plan"]["preset_id"] == "alpha_equities_4h"
    assert report["sampling_plan"]["timeframe"] == "4h"
    assert report["sampling_plan"]["status"] == "blocked_insufficient_range"
    assert report["sampling_plan_validation"]["valid"] is True
    assert report["authority"]["action_authority"] == "report_only"
    assert report["safety_invariants"]["can_execute"] is False


def test_proposal_is_deterministic_and_campaign_agnostic() -> None:
    first = proposal.build_campaign_preregistered_sampling_plan(
        decision=_decision(),
        preregistration_timestamp=TIMESTAMP,
    )
    second = proposal.build_campaign_preregistered_sampling_plan(
        decision=_decision(),
        preregistration_timestamp=TIMESTAMP,
    )
    assert first == second

    other = _decision()
    other["campaign_scope"] = {
        "campaign_id": "campaign-beta",
        "hypothesis_id": "behavior_beta_v2",
        "preset_name": "beta_crypto_1h",
        "timeframe": "1h",
        "template_id": "weekly_retest__beta_crypto_1h",
        "strategy_family": "behavior_beta",
        "asset_class": "crypto",
        "universe": ["ETH-USD", "BTC-USD"],
        "lineage_root_campaign_id": "campaign-beta",
        "parent_campaign_id": "campaign-parent",
        "registry_record_present": True,
    }
    other_report = proposal.build_campaign_preregistered_sampling_plan(
        decision=other,
        preregistration_timestamp=TIMESTAMP,
    )

    assert other_report["campaign_scope"]["campaign_id"] == "campaign-beta"
    assert other_report["sampling_plan"]["behavior_id"] == "behavior_beta"
    assert other_report["sampling_plan"]["preset_id"] == "beta_crypto_1h"
    assert other_report["sampling_plan"]["timeframe"] == "1h"
    assert other_report["proposal_id"] != first["proposal_id"]


def test_unsupported_or_unsafe_decisions_fail_closed() -> None:
    unsupported = _decision()
    unsupported["recommended_action"] = "operator_review"
    report = proposal.build_campaign_preregistered_sampling_plan(
        decision=unsupported,
        preregistration_timestamp=TIMESTAMP,
    )
    assert report["proposal_status"] == "blocked_unsupported_decision"
    assert report["sampling_plan"] == {}

    unsafe = _decision()
    unsafe["safety_invariants"]["can_execute"] = True
    report = proposal.build_campaign_preregistered_sampling_plan(
        decision=unsafe,
        preregistration_timestamp=TIMESTAMP,
    )
    assert report["proposal_status"] == "blocked_unsafe_decision_authority"
    assert "decision_safety_invariant_not_false:can_execute" in report["blocked_reasons"]


def test_missing_scope_and_failure_policy_fail_closed() -> None:
    incomplete = _decision()
    incomplete["campaign_scope"]["timeframe"] = ""
    report = proposal.build_campaign_preregistered_sampling_plan(
        decision=incomplete,
        preregistration_timestamp=TIMESTAMP,
    )
    assert report["proposal_status"] == "blocked_incomplete_campaign_scope"
    assert "missing_campaign_scope:timeframe" in report["blocked_reasons"]

    unknown = _decision()
    unknown["failure_class"] = "unknown_failure"
    report = proposal.build_campaign_preregistered_sampling_plan(
        decision=unknown,
        preregistration_timestamp=TIMESTAMP,
    )
    assert report["proposal_status"] == "blocked_unsupported_failure_class"
    assert report["sampling_plan"] == {}


def test_current_artifact_status_and_sidecar_writes(tmp_path: Path) -> None:
    missing = proposal.build_from_current_decision(
        preregistration_timestamp=TIMESTAMP,
        repo_root=tmp_path,
    )
    assert missing["proposal_status"] == "blocked_missing_decision"

    decision_path = tmp_path / proposal.DECISION_PATH
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text("not-json", encoding="utf-8")
    malformed = proposal.build_from_current_decision(
        preregistration_timestamp=TIMESTAMP,
        repo_root=tmp_path,
    )
    assert malformed["proposal_status"] == "blocked_malformed_decision"

    decision_path.write_text(json.dumps(_decision()), encoding="utf-8")
    report = proposal.build_from_current_decision(
        preregistration_timestamp=TIMESTAMP,
        repo_root=tmp_path,
    )
    paths = proposal.write_outputs(report, repo_root=tmp_path)
    json_payload = json.loads((tmp_path / paths["json"]).read_text(encoding="utf-8"))
    markdown = (tmp_path / paths["markdown"]).read_text(encoding="utf-8")

    assert json_payload["proposal_id"] == report["proposal_id"]
    assert "proposal_ready_coverage_required" in markdown
    assert "can_execute: False" in markdown


def test_module_has_no_runtime_or_mutation_imports() -> None:
    source = Path(
        "research/campaign_preregistered_sampling_plan.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "qre_preregistered_multiwindow_evidence_run",
        "campaign_queue",
        "campaign_launcher",
        "agent.execution",
        "agent.risk",
        "qre_paper",
        "qre_shadow",
        "qre_live",
    )
    assert all(value not in source for value in forbidden)
