from research.qre_tail_entropy_hardening import (
    diagnose_tail_entropy,
    tail_entropy_manifest,
)


def test_tail_entropy_manifest_is_context_only():
    manifest = tail_entropy_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "tail_entropy_clear" in manifest["risk_states"]
    assert "tail_entropy_blocked" in manifest["risk_states"]

    authority = manifest["authority"]
    assert authority["tail_entropy_diagnostics_are_context_only"] is True
    assert authority["not_alpha_authority"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
    assert authority["does_not_fetch_data"] is True
    assert authority["does_not_mutate_candidates"] is True
    assert authority["does_not_mutate_frozen_contracts"] is True


def test_tail_entropy_clear_for_balanced_observations():
    diagnostic = diagnose_tail_entropy([0.01, -0.01, 0.02, -0.02, 0.015, -0.015])

    assert diagnostic.observation_count == 6
    assert diagnostic.negative_observation_count == 3
    assert diagnostic.risk_state == "tail_entropy_clear"


def test_tail_entropy_blocked_for_single_trade_concentration():
    diagnostic = diagnose_tail_entropy([0.90, 0.01, -0.01, 0.01, -0.01, 0.01])

    assert diagnostic.risk_state == "tail_entropy_blocked"
    assert diagnostic.largest_abs_contribution_share is not None
    assert diagnostic.largest_abs_contribution_share > 0.50


def test_tail_entropy_blocked_for_negative_contribution_concentration():
    diagnostic = diagnose_tail_entropy([-0.50, -0.20, -0.10, 0.02, 0.02, 0.01])

    assert diagnostic.risk_state == "tail_entropy_blocked"
    assert diagnostic.negative_contribution_share is not None
    assert diagnostic.negative_contribution_share > 0.70


def test_tail_entropy_blocked_for_low_sign_entropy():
    diagnostic = diagnose_tail_entropy([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])

    assert diagnostic.risk_state == "tail_entropy_blocked"
    assert diagnostic.sign_entropy_bits == 0.0


def test_tail_entropy_watch_near_threshold():
    diagnostic = diagnose_tail_entropy(
        [0.40, 0.10, -0.10, 0.10, -0.10, 0.10],
        max_single_abs_share=0.55,
    )

    assert diagnostic.risk_state in {"tail_entropy_watch", "tail_entropy_blocked"}


def test_tail_entropy_insufficient_data():
    diagnostic = diagnose_tail_entropy([0.01, -0.01], min_observations=5)

    assert diagnostic.risk_state == "insufficient_return_data"
    assert diagnostic.observation_count == 2


def test_tail_entropy_ignores_non_numeric_values():
    diagnostic = diagnose_tail_entropy([0.01, "bad", None, -0.01, 0.02, -0.02, 0.03])

    assert diagnostic.observation_count == 5


def test_tail_entropy_handles_all_zero_values():
    diagnostic = diagnose_tail_entropy([0, 0, 0, 0, 0])

    assert diagnostic.observation_count == 5
    assert diagnostic.largest_abs_contribution_share == 0.0
    assert diagnostic.negative_contribution_share == 0.0