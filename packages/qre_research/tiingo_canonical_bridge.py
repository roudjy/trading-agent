"""Bridge Tiingo research artifacts to canonical QRE contracts.

The bridge is deterministic and read-only. It maps existing Tiingo mini-loop
records into provider-agnostic canonical payloads while keeping Tiingo-specific
identifiers inside provenance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

PROVIDER_TERM: Final[str] = "tiingo"
SCHEMA_VERSION: Final[int] = 1
SAFETY: Final[dict[str, bool]] = {
    "research_only": True,
    "bridge_only": True,
    "creates_candidates": False,
    "creates_strategies": False,
    "creates_presets": False,
    "creates_campaigns": False,
    "runs_screening": False,
    "trading_authority": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}


class CanonicalBridgeError(ValueError):
    """Raised when a provider artifact cannot be safely canonicalized."""


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _required(payload: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "", [])]
    if missing:
        raise CanonicalBridgeError("missing_required_fields:" + ",".join(missing))


def _assert_provider_terms_only_in_provenance(payload: Mapping[str, Any]) -> None:
    def walk(value: Any, path: tuple[str, ...]) -> None:
        if "provenance" in path:
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                if PROVIDER_TERM in str(key).lower():
                    raise CanonicalBridgeError("provider_leakage:" + ".".join((*path, str(key))))
                walk(child, (*path, str(key)))
            return
        if isinstance(value, list | tuple):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))
            return
        if PROVIDER_TERM in str(value).lower():
            raise CanonicalBridgeError("provider_leakage:" + ".".join(path))

    walk(payload, ())


def canonicalize_tiingo_hypothesis_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    """Map a Tiingo admitted seed/lifecycle row to canonical Hypothesis."""

    _required(seed, ("hypothesis_seed_id", "source_hypothesis_id", "source_snapshot_id", "feature_family"))
    digest = seed.get("source_hypothesis_digest")
    identity_basis = {
        "source_hypothesis_id": seed["source_hypothesis_id"],
        "source_snapshot_id": seed["source_snapshot_id"],
        "feature_family": seed["feature_family"],
        "digest": digest.get("digest") if isinstance(digest, Mapping) else digest,
    }
    payload = {
        "canonical_name": "Hypothesis",
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id": "hyp_" + _digest(identity_basis),
        "mechanism": {
            "feature_family": str(seed["feature_family"]),
            "statement": "Research hypothesis admitted by provider adapter lifecycle boundary.",
        },
        "predicted_effect": "provider_neutral_research_effect_to_screen",
        "falsification_conditions": ["fails_screening_protocol", "does_not_beat_null_control"],
        "provenance": {
            "source": "qre_tiingo_hypothesis_lifecycle",
            "provider_adapter": PROVIDER_TERM,
            "hypothesis_seed_id": seed["hypothesis_seed_id"],
            "source_hypothesis_id": seed["source_hypothesis_id"],
            "source_snapshot_id": seed["source_snapshot_id"],
            "source_hypothesis_digest": digest or {},
        },
        "safety": dict(SAFETY),
    }
    _assert_provider_terms_only_in_provenance(payload)
    return payload


def canonicalize_tiingo_research_input_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Map a Tiingo input contract to canonical ResearchInputContract."""

    _required(contract, ("contract_id", "hypothesis_seed_id", "source_hypothesis_id", "source_snapshot_id", "decision"))
    if contract.get("decision") != "admitted":
        raise CanonicalBridgeError("not_admitted_contract")
    hypothesis = canonicalize_tiingo_hypothesis_seed(contract)
    identity_basis = {
        "hypothesis_id": hypothesis["hypothesis_id"],
        "decision": contract["decision"],
        "required_candidate_spec_fields": contract.get("required_candidate_spec_fields", []),
    }
    payload = {
        "canonical_name": "ResearchInputContract",
        "schema_version": SCHEMA_VERSION,
        "contract_id": "ric_" + _digest(identity_basis),
        "hypothesis_id": hypothesis["hypothesis_id"],
        "decision": "admitted",
        "required_candidate_spec_fields": list(contract.get("required_candidate_spec_fields") or []),
        "allowed_candidate_families": list(contract.get("allowed_candidate_families") or []),
        "forbidden_authorities": list(contract.get("forbidden_authorities") or []),
        "provenance": {
            "source": "qre_tiingo_candidate_research_loop",
            "provider_adapter": PROVIDER_TERM,
            "source_contract_id": contract["contract_id"],
            "hypothesis_seed_id": contract["hypothesis_seed_id"],
            "source_hypothesis_id": contract["source_hypothesis_id"],
            "source_snapshot_id": contract["source_snapshot_id"],
        },
        "safety": dict(SAFETY),
    }
    _assert_provider_terms_only_in_provenance(payload)
    return payload


def canonicalize_tiingo_candidate_spec(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Map a Tiingo candidate spec to canonical CandidateSpec."""

    _required(
        candidate,
        (
            "candidate_id",
            "parent_contract_id",
            "parent_hypothesis_seed_id",
            "source_hypothesis_id",
            "source_snapshot_id",
            "signal_definition",
            "selection_rule",
        ),
    )
    if candidate.get("trading_authority") is not False or candidate.get("research_only") is not True:
        raise CanonicalBridgeError("unsafe_candidate_authority")
    semantic_payload = {
        "signal_definition": candidate["signal_definition"],
        "selection_rule": candidate["selection_rule"],
        "rebalance_rule": candidate.get("rebalance_rule", {}),
        "holding_period": candidate.get("holding_period", {}),
        "benchmark": candidate.get("benchmark", {}),
        "variant_parameters": candidate.get("variant_parameters", {}),
    }
    semantic_probe = {"canonical_name": "CandidateSpec", **semantic_payload}
    _assert_provider_terms_only_in_provenance(semantic_probe)
    identity_basis = {
        "parent_contract_id": candidate["parent_contract_id"],
        "semantics": semantic_payload,
    }
    payload = {
        "canonical_name": "CandidateSpec",
        "schema_version": SCHEMA_VERSION,
        "candidate_id": "cand_" + _digest(identity_basis),
        "parent_contract_id": "ric_" + _digest(
            {
                "source_contract_id": candidate["parent_contract_id"],
                "hypothesis_seed_id": candidate["parent_hypothesis_seed_id"],
            }
        ),
        **semantic_payload,
        "screening_protocol": candidate.get("screening_protocol", "canonical_research_screening_v1"),
        "research_only": True,
        "screening_only": True,
        "not_trade_signal": True,
        "provenance": {
            "source": "qre_tiingo_candidate_research_loop",
            "provider_adapter": PROVIDER_TERM,
            "source_candidate_id": candidate["candidate_id"],
            "source_contract_id": candidate["parent_contract_id"],
            "hypothesis_seed_id": candidate["parent_hypothesis_seed_id"],
            "source_hypothesis_id": candidate["source_hypothesis_id"],
            "source_snapshot_id": candidate["source_snapshot_id"],
            "candidate_digest": candidate.get("candidate_digest"),
        },
        "safety": dict(SAFETY),
    }
    _assert_provider_terms_only_in_provenance(payload)
    return payload


def canonicalize_tiingo_report(report: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Canonicalize bridgeable Tiingo report collections without side effects."""

    input_contracts = report.get("input_contracts")
    candidate_specs = report.get("candidate_specs")
    if not isinstance(input_contracts, list) or not isinstance(candidate_specs, list):
        raise CanonicalBridgeError("missing_bridge_collections")
    return {
        "hypotheses": [canonicalize_tiingo_hypothesis_seed(row) for row in input_contracts],
        "research_input_contracts": [canonicalize_tiingo_research_input_contract(row) for row in input_contracts],
        "candidate_specs": [canonicalize_tiingo_candidate_spec(row) for row in candidate_specs],
    }


__all__ = [
    "CanonicalBridgeError",
    "SAFETY",
    "canonicalize_tiingo_candidate_spec",
    "canonicalize_tiingo_hypothesis_seed",
    "canonicalize_tiingo_report",
    "canonicalize_tiingo_research_input_contract",
]
