from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from packages.qre_research import funnel_classification as fc

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_loop_classification_exists() -> None:
    canonical = fc.canonical_classifications()

    assert len(canonical) == 1
    assert canonical[0].funnel_id == "canonical_provider_agnostic_contract_bridge_loop"
    assert canonical[0].decision == "KEEP_AS_CANONICAL"


def test_tiingo_is_provider_adapter_not_canonical() -> None:
    row = fc.classification_by_id("tiingo_hypothesis_candidate_research_mini_loop")

    assert row.classification == "provider_adapter"
    assert row.decision == "KEEP_AS_PROVIDER_ADAPTER"
    assert row.canonical_claim_allowed is False


def test_daily_digest_is_observability_only() -> None:
    row = fc.classification_by_id("daily_status_digest_observability")

    assert row.classification == "observability_only"
    assert row.decision == "OBSERVABILITY_ONLY"
    assert row.canonical_claim_allowed is False


def test_fixture_funnels_are_fixture_only() -> None:
    row = fc.classification_by_id("test_smoke_fixture_funnels")

    assert row.classification == "fixture_only"
    assert row.decision == "TEST_FIXTURE_ONLY"
    assert row.canonical_claim_allowed is False


def test_legacy_frozen_outputs_are_protected() -> None:
    row = fc.classification_by_id("run_research_registry_matrix")

    assert row.classification == "legacy_protected"
    assert "research/research_latest.json" in row.protected_outputs
    assert "research/strategy_matrix.csv" in row.protected_outputs
    assert (REPO_ROOT / "research" / "research_latest.json").exists()
    assert (REPO_ROOT / "research" / "strategy_matrix.csv").exists()


def test_duplicate_canonical_claims_fail_validation(monkeypatch: MonkeyPatch) -> None:
    duplicate = fc.FunnelClassification(
        funnel_id="duplicate_canonical",
        name="Duplicate canonical claim",
        classification="canonical_contract_loop",
        decision="KEEP_AS_CANONICAL",
        canonical_claim_allowed=True,
        modules=(),
        protected_outputs=(),
        rationale="test duplicate",
        next_action="fail validation",
    )
    monkeypatch.setattr(fc, "FUNNEL_CLASSIFICATIONS", (*fc.FUNNEL_CLASSIFICATIONS, duplicate))

    assert "expected_exactly_one_canonical_contract_loop" in fc.validate_funnel_classifications()


def test_ambiguous_owners_remain_operator_decision_required() -> None:
    row = fc.classification_by_id("alpha_discovery_strategy_ir_campaign_lesson")

    assert row.classification == "operator_decision_required"
    assert row.canonical_claim_allowed is False
    assert row.decision == "BRIDGE_TO_CANONICAL"


def test_classification_registry_validates_cleanly() -> None:
    assert fc.validate_funnel_classifications() == []


def test_no_execution_authority_introduced() -> None:
    assert fc.SAFETY["classification_only"] is True
    assert fc.SAFETY["runtime_behavior_changed"] is False
    assert fc.SAFETY["creates_campaigns"] is False
    assert fc.SAFETY["runs_screening"] is False
    assert fc.SAFETY["trading_authority"] is False
    assert fc.SAFETY["paper_authority"] is False
    assert fc.SAFETY["shadow_authority"] is False
    assert fc.SAFETY["live_authority"] is False


def test_classification_summary_reports_no_duplicate_canonical_claims() -> None:
    summary = fc.classification_summary()

    assert summary["canonical_contract_loop"] == "canonical_provider_agnostic_contract_bridge_loop"
    assert summary["duplicate_canonical_claims"] is False
