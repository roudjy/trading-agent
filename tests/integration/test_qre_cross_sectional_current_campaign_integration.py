from __future__ import annotations

from pathlib import Path

import pytest

from packages.qre_research import empirical_evidence_pack as eep
from packages.qre_research import second_preregistered_campaign as campaign
from tests.unit import test_qre_second_preregistered_campaign as fixture_helpers


@pytest.fixture
def cross_sectional_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    for relative in fixture_helpers._COPIED_INPUTS:
        fixture_helpers._copy(repo_root, relative)
    fixture_helpers._write_manifest(repo_root)
    for relative in (
        "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
        "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
        "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
        "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
        "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
    ):
        fixture_helpers._filter_rows(repo_root, relative, campaign_cell_id="qrcell_44aa81da7c2fc7c9")
    fixture_helpers._write_window_ledger(repo_root)
    fixture_helpers._write_cache_manifest(repo_root)
    fixture_helpers._write_cache_rows(repo_root)
    monkeypatch.setattr(campaign, "_evaluate_strategy", fixture_helpers._fake_evaluate_strategy)
    monkeypatch.setattr(campaign, "validate_write_target", lambda path: None)
    monkeypatch.setattr(eep, "validate_write_target", lambda path: None)
    return repo_root


def test_cross_sectional_current_hypothesis_chain_materializes_campaign_and_evidence(
    cross_sectional_repo: Path,
) -> None:
    closeout = campaign.run_second_preregistered_campaign(repo_root=cross_sectional_repo)
    pack = eep.run_empirical_evidence_pack(repo_root=cross_sectional_repo)

    assert closeout["selection"]["source_hypothesis_id"] == "cross_sectional_momentum_v0"
    assert closeout["campaign_classification"]["current_hypothesis_campaigns_executed"] == 1
    assert pack["campaign_classification"]["historical_campaigns_consumed"] == 0
    assert pack["campaign_classification"]["fixture_campaigns_consumed"] == 0
    assert pack["campaign_identity"] == closeout["executed_campaign_identity"]
    assert (cross_sectional_repo / eep.EVIDENCE_PACK_PATH).is_file()
