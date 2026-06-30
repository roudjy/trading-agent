from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from packages.qre_research import autonomous_orchestration as ao
from packages.qre_research import generated_strategy_paths as gsp

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def orchestration_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "generated_research", repo_root / "generated_research")
    (repo_root / "artifacts" / "cache").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO_ROOT / "artifacts" / "cache" / "cache_coverage_latest.v1.json",
        repo_root / "artifacts" / "cache" / "cache_coverage_latest.v1.json",
    )
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
