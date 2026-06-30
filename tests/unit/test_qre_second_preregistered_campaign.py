from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from packages.qre_research import second_preregistered_campaign as campaign


REPO_ROOT = Path(__file__).resolve().parents[2]

_COPIED_INPUTS = (
    "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
    "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
    "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
    "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
    "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
    "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
    "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
    "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
    "generated_research/registry/generated_strategy_registry.v1.json",
    "generated_research/specs/qsp_16800d656bf28677.json",
    "generated_research/validation/qgs_5af8f605ba82ae53.json",
    "generated_research/lineage/generated_null_controls.v1.json",
    "logs/qre_data_cache_manifest/latest.json",
    "artifacts/cache/cache_coverage_latest.v1.json",
    "agent/backtesting/generated_strategies/generated_qgs_5af8f605ba82ae53.py",
    "data/cache/market/yfinance__ASML__4h__20240525__20260425__4d9f10c591dd4bf6.parquet",
)


def _copy(repo_root: Path, relative: str) -> None:
    source = REPO_ROOT / relative
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def qre025_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    for relative in _COPIED_INPUTS:
        _copy(repo_root, relative)
    monkeypatch.setattr(campaign, "validate_write_target", lambda path: None)
    return repo_root


def test_generated_strategy_paths_allow_campaign_execution_surface() -> None:
    from packages.qre_research import generated_strategy_paths as gsp

    for relative in (
        "generated_research/campaign_execution/manifest_integrity/sample.json",
        "generated_research/campaign_execution/stages/sample.json",
        "generated_research/campaign_execution/evidence/sample.json",
        "generated_research/campaign_execution/ledgers/sample.json",
        "generated_research/campaign_execution/reports/sample.json",
    ):
        gsp.validate_write_target(gsp.REPO_ROOT / Path(relative))


def test_manifest_verification_passes_on_authoritative_bundle(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["manifest_integrity"]["status"] == "MANIFEST_VERIFIED"
    assert result["executed_campaign_cell"] == "qrcell_fdd68e20fd2724dd"


def test_strategy_hash_mismatch_blocks_execution(qre025_repo: Path) -> None:
    registry_path = qre025_repo / "generated_research/registry/generated_strategy_registry.v1.json"
    payload = _read_json(registry_path)
    payload["rows"][0]["code_hash"] = "deadbeef"
    registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["manifest_integrity"]["status"] == "STRATEGY_HASH_MISMATCH"
    assert result["terminal_outcome"] == "NO_SAFE_AUTOMATED_NEXT_ACTION"


def test_only_ready_cell_executes_and_blocked_cells_remain_excluded(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    excluded = {row["campaign_cell_id"] for row in result["excluded_blocked_cells"]}
    assert excluded == {
        "qrcell_41d3efbcaa2aeddb",
        "qrcell_d5ded3130f132558",
        "qrcell_44aa81da7c2fc7c9",
    }
    assert result["executed_campaign_cell"] == "qrcell_fdd68e20fd2724dd"


def test_oos_window_is_consumed_in_canonical_ledger(qre025_repo: Path) -> None:
    campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    ledger = _read_json(
        qre025_repo
        / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json"
    )
    oos_row = next(row for row in ledger["rows"] if row["window_id"] == "qwl_06fd2878a7332daa")
    assert oos_row["status"] == "CONSUMED"
    assert oos_row["consumption_evidence"]["campaign_cell_id"] == "qrcell_fdd68e20fd2724dd"


def test_second_run_is_deterministic_for_manifest_and_closeout(qre025_repo: Path) -> None:
    first = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    second = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert first["closeout_identity"] == second["closeout_identity"]
    assert first["manifest_integrity"]["manifest_integrity_identity"] == second["manifest_integrity"]["manifest_integrity_identity"]


def test_oos_stage_uses_exact_frozen_window(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["oos_stage"]["oos_window_id"] == "qwl_06fd2878a7332daa"
    assert result["oos_stage"]["trade_count"] == 3
    assert result["oos_stage"]["validation_evidence"]["evidence_status"] == "insufficient_oos_trades"


def test_null_controls_execute_with_frozen_seed(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    rows = result["null_controls"]["rows"]
    assert {row["control_class"] for row in rows} == {
        "matched_frequency_null",
        "sign_flipped_signal",
        "cost_only_baseline",
    }
    assert all(row["deterministic_seed"] == "01e1a2972b98d302" for row in rows)


def test_feedback_routes_to_data_oos_capacity_expansion(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["decision"]["hypothesis_decision"] == "BLOCKED_SAMPLE_SIZE"
    assert result["decision"]["strategy_decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["feedback_routing"]["next_action"] == "launch_data_oos_capacity_expansion"
    assert result["terminal_outcome"] == "DATA_OR_OOS_CAPACITY_BLOCKED"


def test_campaign_execution_outputs_are_materialized(qre025_repo: Path) -> None:
    campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    for relative in (
        "generated_research/campaign_execution/manifest_integrity/second_campaign_manifest_integrity.v1.json",
        "generated_research/campaign_execution/stages/train_and_screening.v1.json",
        "generated_research/campaign_execution/stages/validation.v1.json",
        "generated_research/campaign_execution/stages/oos.v1.json",
        "generated_research/campaign_execution/stages/null_controls.v1.json",
        "generated_research/campaign_execution/evidence/evidence_reason_records.v1.json",
        "generated_research/campaign_execution/ledgers/oos_consumption.v1.json",
        "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
    ):
        assert (qre025_repo / relative).is_file(), relative
