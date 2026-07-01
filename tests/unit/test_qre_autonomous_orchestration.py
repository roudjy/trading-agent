from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.qre_research import autonomous_orchestration as ao
from packages.qre_research import generated_hypothesis_paths as ghp
from packages.qre_research import generated_strategy_paths as gsp

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PAYLOADS = {
    "artifacts/cache/cache_coverage_latest.v1.json": {
        "coverage": [
            {"instrument": "ASML", "timeframe": "4h", "max_timestamp_utc": "2026-04-24T17:30:00Z"},
            {"instrument": "ASML", "timeframe": "1d", "max_timestamp_utc": "2026-05-22T21:59:59Z"},
            {"instrument": "AAPL", "timeframe": "1d", "max_timestamp_utc": "2026-05-22T21:59:59Z"},
        ]
    },
    "generated_research/campaign_execution/ledgers/oos_consumption.v1.json": {
        "rows": [
            {
                "consumption_id": "qwc_8c9fcb2e33b0bb6b",
                "window_id": "qwl_06fd2878a7332daa",
                "generated_strategy_id": "qgs_5af8f605ba82ae53",
                "campaign_cell_id": "qrcell_fdd68e20fd2724dd",
            }
        ]
    },
    "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json": {
        "executed_campaign": {"generated_strategy_id": "qgs_5af8f605ba82ae53"},
        "executed_campaign_cell": "qrcell_fdd68e20fd2724dd",
        "funnel": {"screening_passed": 1},
        "decision": {
            "failure_memory_update": {"generated_strategy_id": "qgs_5af8f605ba82ae53"},
            "contradiction_update": {"source_hypothesis_id": "atr_adaptive_trend_v0"},
        },
    },
    "generated_research/hypotheses/mechanisms/generated_mechanisms.v1.json": {"rows": [{"mechanism_id": "qm_1"}]},
    "generated_research/hypotheses/observations/generated_observations.v1.json": {"rows": [{"observation_id": "qo_1"}]},
    "generated_research/hypotheses/opportunities/generated_opportunities.v1.json": {"rows": [{"opportunity_id": "qp_1"}]},
    "generated_research/hypotheses/registry/generated_thesis_registry.v1.json": {
        "rows": [
            {
                "thesis_id": "qht_1",
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "lifecycle_state": "HYPOTHESIS_ADMITTED_AUTOMATED",
                "primitive_compatibility": "COMPILABLE_WITH_CURRENT_PRIMITIVES",
                "mechanism_class": "trend_persistence",
                "behavior_family": "trend",
            },
            {
                "thesis_id": "qht_2",
                "source_hypothesis_id": "qhc_51bc7a5c7b3f64ba",
                "lifecycle_state": "ADMITTED_GENERATION_BLOCKED",
                "primitive_compatibility": "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION",
                "mechanism_class": "cross_sectional_continuation",
                "behavior_family": "cross_sectional",
            },
        ]
    },
    "generated_research/presets/generated_research_presets.v1.json": {"rows": [{"preset_id": "qgp_3150293b47cd6923"}]},
    "generated_research/primitives/registry/generated_primitive_registry.v1.json": {
        "rows": [{"primitive_id": "cross_sectional_rank", "generated_primitive_id": "qgp_bbfb1728e13038c1", "state": "PRIMITIVE_REGISTERED_AUTOMATED"}]
    },
    "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json": {
        "rows": [
            {
                "campaign_cell_id": "qrcell_41d3efbcaa2aeddb",
                "generated_strategy_id": "qgs_5af8f605ba82ae53",
                "strategy_spec_id": "qsp_16800d656bf28677",
                "timeframe": "1d",
                "status": "BLOCKED_WINDOWS",
                "blockers": ["usable_history_below_minimum_policy_span"],
                "next_action": "launch_data_oos_capacity_expansion",
                "dataset_identity": "qds_f8a7d624458bb131",
                "snapshot_identity": "qsn_f8a7d624458bb131",
                "manifest_ready": False,
                "train_window": {},
                "validation_window": {},
                "oos_window": {},
            },
            {
                "campaign_cell_id": "qrcell_d5ded3130f132558",
                "generated_strategy_id": "qgs_5af8f605ba82ae53",
                "strategy_spec_id": "qsp_16800d656bf28677",
                "timeframe": "1h",
                "status": "BLOCKED_DATA",
                "blockers": ["cache_row_missing"],
                "next_action": "launch_data_oos_capacity_expansion",
                "dataset_identity": "",
                "snapshot_identity": "",
                "manifest_ready": False,
                "train_window": {},
                "validation_window": {},
                "oos_window": {},
            },
            {
                "campaign_cell_id": "qrcell_fdd68e20fd2724dd",
                "generated_strategy_id": "qgs_5af8f605ba82ae53",
                "strategy_spec_id": "qsp_16800d656bf28677",
                "timeframe": "4h",
                "status": "READY_FOR_PREREGISTRATION",
                "blockers": [],
                "next_action": "execute_second_preregistered_campaign",
                "dataset_identity": "qds_f8a7d624458bb131",
                "snapshot_identity": "qsn_f8a7d624458bb131",
                "manifest_ready": True,
                "train_window": {"start": "2024-05-28T13:30:00Z", "end": "2025-09-28T17:30:00Z"},
                "validation_window": {"start": "2025-10-12T17:30:00Z", "end": "2026-01-10T17:30:00Z"},
                "oos_window": {"start": "2026-01-24T17:30:00Z", "end": "2026-04-24T17:30:00Z"},
            },
            {
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "strategy_spec_id": "qsp_28cdbc0005ae7c93",
                "timeframe": "1d",
                "status": "BLOCKED_WINDOWS",
                "blockers": ["usable_history_below_minimum_policy_span"],
                "next_action": "launch_data_oos_capacity_expansion",
                "dataset_identity": "qds_cross_sectional_v1",
                "snapshot_identity": "qsn_cross_sectional_v1",
                "manifest_ready": False,
                "train_window": {},
                "validation_window": {},
                "oos_window": {},
            },
        ]
    },
    "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json": {
        "rows": [
            {
                "window_id": "qwl_06fd2878a7332daa",
                "purpose": "OOS",
                "status": "CONSUMED",
                "campaign_identity": "qcm_04f0e702e5be8884",
                "strategy_identity": "qgs_5af8f605ba82ae53",
            }
        ]
    },
    "generated_research/registry/generated_strategy_registry.v1.json": {
        "rows": [
            {"generated_strategy_id": "qgs_5af8f605ba82ae53", "thesis_id": "atr_adaptive_trend_v0"},
            {"generated_strategy_id": "qgs_e565b01bd0a162d0", "thesis_id": "qhc_51bc7a5c7b3f64ba"},
        ]
    },
}


@pytest.fixture()
def orchestration_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    for relative_path, payload in FIXTURE_PAYLOADS.items():
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return repo_root


def test_generated_strategy_paths_allow_orchestration_surface() -> None:
    gsp.validate_write_target(
        gsp.REPO_ROOT / "generated_research/orchestration/reports/daily/2026-06-30.json"
    )


def test_default_config_is_valid_and_centrally_versioned() -> None:
    config = ao.default_operations_config()
    validation = ao.validate_operations_config(config)

    assert config["config_version"] == "ade-qre-026r.config.1"
    assert config["portfolio_capacity"]["target_active_hypotheses"] == 20
    assert config["execution_capacity"]["maximum_concurrent_local_jobs"] == 2
    assert config["budgets"]["maximum_new_oos_consumptions_per_cycle"] == 1
    assert validation["valid"] is True


def test_invalid_capacity_combination_fails_validation() -> None:
    config = ao.default_operations_config()
    config["portfolio_capacity"]["target_active_hypotheses"] = 41
    config["portfolio_capacity"]["maximum_active_hypotheses"] = 40

    validation = ao.validate_operations_config(config)

    assert validation["valid"] is False
    assert "invalid_capacity:target_active_hypotheses>maximum_active_hypotheses" in validation["errors"]


def test_unified_portfolio_gives_one_current_state_per_strategy(orchestration_repo: Path) -> None:
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)

    strategy_rows = {
        row["object_identity"]: row
        for row in portfolio["strategy_rows"]
    }
    assert set(strategy_rows) >= {"qgs_5af8f605ba82ae53", "qgs_e565b01bd0a162d0"}
    assert strategy_rows["qgs_5af8f605ba82ae53"]["current_stage"] == "OOS_CAPACITY_BLOCKED"
    assert strategy_rows["qgs_5af8f605ba82ae53"]["primary_blocker"] == "oos_sample_size"
    assert strategy_rows["qgs_e565b01bd0a162d0"]["current_stage"] == "DATA_CAPACITY_BLOCKED"
    assert strategy_rows["qgs_e565b01bd0a162d0"]["primary_blocker"] == "usable_history_below_minimum_policy_span"


def test_typed_actions_include_a25_data_oos_expansion(orchestration_repo: Path) -> None:
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(
        portfolio=portfolio,
        config=ao.default_operations_config(),
    )

    row = next(
        item
        for item in actions["rows"]
        if item["source_object"] == "qgs_5af8f605ba82ae53"
    )
    assert row["action_class"] == "EXPAND_DATA_CAPACITY"
    assert row["source_blocker"] == "oos_sample_size"


def test_work_admission_and_schedule_preserve_serialization_for_conflicts(orchestration_repo: Path) -> None:
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(
        portfolio=portfolio,
        config=ao.default_operations_config(),
    )
    work_items = ao.admit_work_items(actions=actions, config=ao.default_operations_config())
    schedule = ao.build_throughput_schedule(
        work_items=work_items,
        config=ao.default_operations_config(),
    )

    first_group = schedule["groups"][0]
    assert len(first_group["work_item_ids"]) == 1
    assert any(
        row["work_class"] == "DATA_CAPACITY_EXPANSION"
        and row["admission_result"] == "ADMITTED_AUTONOMOUS"
        for row in work_items["rows"]
    )


def test_pre_oos_conservation_gate_rejects_low_capacity_case() -> None:
    decision = ao.evaluate_pre_oos_conservation_gate(
        campaign_cell_id="qrcell_fixture",
        strategy_id="qgs_fixture",
        hypothesis_id="qhc_fixture",
        train_trade_count=13,
        validation_trade_count=5,
        train_signal_count=12,
        validation_signal_count=5,
        expected_oos_trade_count=3,
        expected_oos_signal_count=3,
        expected_null_control_capacity=2,
        probability_of_conclusive_decision=0.2,
        existing_window_exposure=1,
        marginal_information_gain=0.1,
        alternative_cheaper_actions=["launch_data_oos_capacity_expansion"],
        config=ao.default_operations_config(),
    )

    assert decision["outcome"] == "REJECT_EXPECTED_SAMPLE_TOO_LOW"


def test_plan_only_mode_does_not_execute_work(orchestration_repo: Path) -> None:
    closeout = ao.run_orchestration(
        repo_root=orchestration_repo,
        mode="PLAN_ONLY",
        max_cycles=1,
        write_outputs=False,
        report_date="2026-06-30",
    )

    assert closeout["operating_mode"] == "PLAN_ONLY"
    assert closeout["work_items_executed"] == 0
    assert closeout["next_autonomous_action"] == "DATA_CAPACITY_EXPANSION"


def test_local_autonomous_mode_executes_one_safe_batch_without_oos_reuse(orchestration_repo: Path) -> None:
    closeout = ao.run_orchestration(
        repo_root=orchestration_repo,
        mode="LOCAL_AUTONOMOUS",
        max_cycles=1,
        write_outputs=False,
        report_date="2026-06-30",
    )

    assert closeout["work_items_executed"] == 1
    assert closeout["overall_outcome"] == "RESEARCH_PORTFOLIO_ADVANCED"
    assert closeout["oos_budget"]["consumed"] == 1
    assert closeout["next_autonomous_action"] == "request_replacement_hypothesis"


def test_daily_report_generation_is_idempotent_for_same_inputs(orchestration_repo: Path) -> None:
    config = ao.default_operations_config()
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(portfolio=portfolio, config=config)
    work_items = ao.admit_work_items(actions=actions, config=config)
    oos_budget = ao.build_oos_budget(repo_root=orchestration_repo, portfolio=portfolio, config=config)

    first = ao.generate_daily_report(
        repo_root=orchestration_repo,
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=[],
        oos_budget=oos_budget,
        report_date="2026-06-30",
        write_outputs=False,
    )
    second = ao.generate_daily_report(
        repo_root=orchestration_repo,
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=[],
        oos_budget=oos_budget,
        report_date="2026-06-30",
        write_outputs=False,
    )

    assert first["daily_report_identity"] == second["daily_report_identity"]
    assert first["health"] == second["health"]



def test_daily_report_uses_completed_cycle_next_action_and_counts_pre_oos_rejects(
    orchestration_repo: Path,
) -> None:
    config = ao.default_operations_config()
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(portfolio=portfolio, config=config)
    work_items = ao.admit_work_items(actions=actions, config=config)
    oos_budget = ao.build_oos_budget(
        repo_root=orchestration_repo,
        portfolio=portfolio,
        config=config,
    )
    kpis = ao._compute_kpis(
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=[
            {
                "execution_status": "completed",
                "next_action": "request_replacement_hypothesis",
            }
        ],
        oos_budget=oos_budget,
        pre_oos_decisions={
            "rows": [
                {
                    "outcome": "REJECT_EXPECTED_SAMPLE_TOO_LOW",
                }
            ]
        },
    )

    assert kpis["executive_summary"]["top_next_actions"] == [
        "request_replacement_hypothesis"
    ]
    assert (
        kpis["evidence_quality"]["campaigns_deferred_by_pre_oos_gate"]
        == 1
    )


def test_status_excludes_completed_scheduled_work_item(
    orchestration_repo: Path,
) -> None:
    config = ao.default_operations_config()
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(portfolio=portfolio, config=config)
    work_items = ao.admit_work_items(actions=actions, config=config)
    oos_budget = ao.build_oos_budget(
        repo_root=orchestration_repo,
        portfolio=portfolio,
        config=config,
    )
    completed_work_item = work_items["rows"][0]["work_item_id"]

    status = ao.build_status_artifact(
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        throughput_schedule={
            "groups": [
                {
                    "group_id": "qrg_fixture",
                    "work_item_ids": [completed_work_item],
                }
            ]
        },
        oos_budget=oos_budget,
        alerts_payload={"rows": []},
        latest_daily_report={"daily_report_identity": "qrdr_fixture"},
        cycle_ledger=[
            {
                "execution_status": "completed",
                "selected_work_item": completed_work_item,
                "progress_status": "IRREDUCIBLE_BLOCKER_PROVEN",
            }
        ],
    )

    assert status["active_jobs"] == []
    assert status["next_selected_work"] == ""


def test_pause_resume_payloads_are_deterministic(orchestration_repo: Path) -> None:
    paused = ao.set_pause_state(repo_root=orchestration_repo, paused=True, write_outputs=False)
    resumed = ao.set_pause_state(repo_root=orchestration_repo, paused=False, write_outputs=False)

    assert paused["paused"] is True
    assert resumed["paused"] is False
    assert paused["control_identity"] != resumed["control_identity"]


def test_selection_explanation_links_to_selected_work_item(orchestration_repo: Path) -> None:
    portfolio = ao.build_unified_portfolio(repo_root=orchestration_repo)
    actions = ao.build_typed_next_actions(portfolio=portfolio, config=ao.default_operations_config())
    work_items = ao.admit_work_items(actions=actions, config=ao.default_operations_config())
    selected_id = work_items["rows"][0]["work_item_id"]

    explanation = ao.explain_selection(work_items=work_items, selected_work_item_id=selected_id)

    assert explanation["status"] == "present"
    assert explanation["selected_work_item_id"] == selected_id


def test_persisted_lifecycle_does_not_repeat_terminal_work_and_executes_bounded_hypothesis_generation(
    orchestration_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        gsp,
        "REPO_ROOT",
        orchestration_repo,
    )
    monkeypatch.setattr(
        ghp,
        "REPO_ROOT",
        orchestration_repo,
    )

    first_closeout = ao.run_orchestration(
        repo_root=orchestration_repo,
        mode="LOCAL_AUTONOMOUS",
        max_cycles=1,
        write_outputs=True,
        report_date="2026-06-30",
    )

    first_ledger = ao._read_json(
        ao._scoped_path(
            ao.CYCLE_LEDGER_PATH,
            repo_root=orchestration_repo,
        )
    )
    first_rows = list((first_ledger or {}).get("rows") or [])

    assert first_closeout["work_items_executed"] == 1
    assert len(first_rows) == 1

    first_work_item_id = str(first_rows[0].get("selected_work_item") or "")
    assert first_work_item_id

    second_closeout = ao.run_orchestration(
        repo_root=orchestration_repo,
        mode="LOCAL_AUTONOMOUS",
        max_cycles=1,
        write_outputs=True,
        report_date="2026-06-30",
    )

    second_ledger = ao._read_json(
        ao._scoped_path(
            ao.CYCLE_LEDGER_PATH,
            repo_root=orchestration_repo,
        )
    )
    second_rows = list((second_ledger or {}).get("rows") or [])

    assert second_closeout["work_items_executed"] == 1
    assert len(second_rows) == 2

    selected_work_item_ids = [
        str(row.get("selected_work_item") or "")
        for row in second_rows
    ]
    assert selected_work_item_ids.count(first_work_item_id) == 1
    assert len(set(selected_work_item_ids)) == len(selected_work_item_ids)

    latest_row = second_rows[-1]
    assert latest_row["remediation"] == "BOUNDED_HYPOTHESIS_GENERATION"
    assert latest_row["execution_status"] == "completed"
    assert latest_row["progress_status"] in {
        "RESOLVED_BLOCKER",
        "NO_CAUSAL_PROGRESS",
        "DOWNSTREAM_BLOCKER_EXPOSED",
    }
    assert latest_row["validation"]["outcome"] == "VALIDATED_AND_COMPOSED"
    assert latest_row["next_action"]

    trusted_loop_summary = ao._read_json(
        orchestration_repo
        / "generated_research/hypotheses/lifecycle/trusted_loop_summary.v1.json"
    )
    assert trusted_loop_summary
    assert trusted_loop_summary["report_kind"] == "qre_generated_hypothesis_trusted_loop_summary"

    hypothesis_registry = ao._read_json(
        orchestration_repo
        / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json"
    )
    assert hypothesis_registry
    assert hypothesis_registry["report_kind"] == "qre_generated_thesis_registry"

    lifecycle_dir = orchestration_repo / "generated_research/hypotheses/lifecycle"
    assert lifecycle_dir.is_dir()

    persisted_invocations = ao._read_json(
        ao._scoped_path(
            ao.INVOCATION_LEDGER_PATH,
            repo_root=orchestration_repo,
        )
    )
    invocation_rows = list(
        (persisted_invocations or {}).get("rows") or []
    )
    invocation_identities = [
        str(row.get("invocation_identity") or "")
        for row in invocation_rows
    ]

    assert len(invocation_rows) == 2
    assert len(set(invocation_identities)) == len(invocation_identities)
