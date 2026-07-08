from __future__ import annotations

from pathlib import Path

import pytest

from packages.qre_research import canonical_contracts
from packages.qre_research.tiingo_canonical_bridge import (
    CanonicalBridgeError,
    canonicalize_tiingo_candidate_spec,
    canonicalize_tiingo_hypothesis_seed,
    canonicalize_tiingo_report,
    canonicalize_tiingo_research_input_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _contract() -> dict[str, object]:
    return {
        "contract_id": "contract_tiingo_abc",
        "schema_version": 1,
        "source": "qre_tiingo_hypothesis_lifecycle",
        "hypothesis_seed_id": "seed_tiingo_cross_sectional_momentum",
        "source_hypothesis_id": "tiingo_hyp_001",
        "source_snapshot_id": "qdsnap_tiingo_001",
        "feature_family": "cross_sectional_momentum",
        "status": "admissible_for_research_candidate_formulation",
        "decision": "admitted",
        "source_hypothesis_digest": {"digest": "sha256:source"},
        "required_candidate_spec_fields": ["signal_definition", "selection_rule"],
        "allowed_candidate_families": ["cross_sectional_momentum"],
        "forbidden_authorities": ["trading_authority"],
        "research_only": True,
        "screening_only": True,
        "trading_authority": False,
    }


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "cand_tiingo_abc",
        "candidate_schema_version": 1,
        "parent_contract_id": "contract_tiingo_abc",
        "parent_hypothesis_seed_id": "seed_tiingo_cross_sectional_momentum",
        "source_hypothesis_id": "tiingo_hyp_001",
        "source_snapshot_id": "qdsnap_tiingo_001",
        "feature_family": "cross_sectional_momentum",
        "candidate_family": "cross_sectional_momentum",
        "signal_definition": {"lookback_window": 60, "return_basis": "adjusted_return"},
        "selection_rule": {"rank": "top", "count": 3},
        "rebalance_rule": {"every_n_trading_days": 20},
        "holding_period": {"trading_days": 20},
        "benchmark": {"kind": "equal_weight_universe"},
        "variant_parameters": {},
        "screening_protocol": "research_candidate_screening_v1",
        "research_only": True,
        "screening_only": True,
        "not_trade_signal": True,
        "trading_authority": False,
        "candidate_digest": "sha256:candidate",
    }


def _assert_no_provider_terms_outside_provenance(payload: object, in_provenance: bool = False) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            nested = in_provenance or key == "provenance"
            if not nested:
                assert "tiingo" not in str(key).lower()
            _assert_no_provider_terms_outside_provenance(value, nested)
        return
    if isinstance(payload, list):
        for item in payload:
            _assert_no_provider_terms_outside_provenance(item, in_provenance)
        return
    if not in_provenance:
        assert "tiingo" not in str(payload).lower()


def test_canonicalize_tiingo_hypothesis_seed() -> None:
    payload = canonicalize_tiingo_hypothesis_seed(_contract())

    assert payload["canonical_name"] == "Hypothesis"
    assert str(payload["hypothesis_id"]).startswith("hyp_")
    assert payload["mechanism"]["feature_family"] == "cross_sectional_momentum"
    assert payload["provenance"]["provider_adapter"] == "tiingo"
    _assert_no_provider_terms_outside_provenance(payload)


def test_canonicalize_tiingo_research_input_contract() -> None:
    payload = canonicalize_tiingo_research_input_contract(_contract())

    assert payload["canonical_name"] == "ResearchInputContract"
    assert str(payload["contract_id"]).startswith("ric_")
    assert payload["decision"] == "admitted"
    assert payload["provenance"]["source_contract_id"] == "contract_tiingo_abc"
    _assert_no_provider_terms_outside_provenance(payload)


def test_canonicalize_tiingo_candidate_spec() -> None:
    payload = canonicalize_tiingo_candidate_spec(_candidate())

    assert payload["canonical_name"] == "CandidateSpec"
    assert str(payload["candidate_id"]).startswith("cand_")
    assert "tiingo" not in str(payload["candidate_id"]).lower()
    assert payload["research_only"] is True
    assert payload["safety"]["trading_authority"] is False
    assert payload["provenance"]["source_candidate_id"] == "cand_tiingo_abc"
    _assert_no_provider_terms_outside_provenance(payload)


def test_canonical_ids_are_deterministic() -> None:
    assert canonicalize_tiingo_hypothesis_seed(_contract()) == canonicalize_tiingo_hypothesis_seed(_contract())
    assert canonicalize_tiingo_research_input_contract(_contract()) == canonicalize_tiingo_research_input_contract(_contract())
    assert canonicalize_tiingo_candidate_spec(_candidate()) == canonicalize_tiingo_candidate_spec(_candidate())


def test_missing_required_fields_fail_closed() -> None:
    bad = _contract()
    bad.pop("source_snapshot_id")

    with pytest.raises(CanonicalBridgeError, match="missing_required_fields"):
        canonicalize_tiingo_hypothesis_seed(bad)


def test_forbidden_provider_leakage_fails_closed() -> None:
    bad = _candidate()
    bad["signal_definition"] = {"provider": "tiingo"}

    with pytest.raises(CanonicalBridgeError, match="provider_leakage"):
        canonicalize_tiingo_candidate_spec(bad)


def test_unsafe_candidate_authority_fails_closed() -> None:
    bad = _candidate()
    bad["trading_authority"] = True

    with pytest.raises(CanonicalBridgeError, match="unsafe_candidate_authority"):
        canonicalize_tiingo_candidate_spec(bad)


def test_report_bridge_is_stable_and_read_only() -> None:
    report = {"input_contracts": [_contract()], "candidate_specs": [_candidate()]}

    first = canonicalize_tiingo_report(report)
    second = canonicalize_tiingo_report(report)

    assert first == second
    assert len(first["hypotheses"]) == 1
    assert len(first["research_input_contracts"]) == 1
    assert len(first["candidate_specs"]) == 1


def test_daily_digest_remains_observability_only() -> None:
    digest = canonical_contracts.contract_by_name("DailyDigestInput")
    summary = canonical_contracts.contract_by_name("OperatorSummary")

    assert canonical_contracts.observability_contract_is_read_only(digest)
    assert canonical_contracts.observability_contract_is_read_only(summary)


def test_frozen_outputs_are_untouched_by_bridge() -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS}

    canonicalize_tiingo_report({"input_contracts": [_contract()], "candidate_specs": [_candidate()]})

    after = {path: (REPO_ROOT / path).read_bytes() for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS}
    assert after == before
