from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from packages.qre_research import architecture_registry as registry
from tools import qre_funnel_architecture_audit as audit


def _payload() -> dict[str, object]:
    return json.loads(registry.DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "qre_architecture_registry.v1.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _entry(payload: dict[str, object], entry_id: str) -> dict[str, object]:
    entries = payload["entries"]
    assert isinstance(entries, list)
    for row in entries:
        assert isinstance(row, dict)
        if row["id"] == entry_id:
            return row
    raise AssertionError(entry_id)


def test_registered_surfaces_pass_closed_world_audit() -> None:
    errors = registry.validate_closed_world_audit(
        canonical_objects=audit.CANONICAL_OBJECTS,
        maturity_claims=tuple(entry.maturity_level for entry in registry.registry_entries()),
        authority_flags=tuple(flag for entry in registry.registry_entries() for flag in entry.authority_flags),
    )

    assert errors == []


def test_unregistered_producer_fails_closed_world_gate() -> None:
    errors = registry.validate_closed_world_audit(
        producer_modules=("research/new_parallel_qre_funnel.py",),
    )

    assert "unregistered_producer:research/new_parallel_qre_funnel.py" in errors


def test_unregistered_artifact_path_fails_closed_world_gate() -> None:
    errors = registry.validate_closed_world_audit(
        artifact_paths=("logs/new_parallel_qre_funnel/latest.json",),
    )

    assert "unregistered_artifact_path:logs/new_parallel_qre_funnel/latest.json" in errors


def test_unknown_canonical_object_owner_fails_closed_world_gate() -> None:
    errors = registry.validate_closed_world_audit(
        canonical_objects=("UnsettledCanonicalObject",),
    )

    assert "unknown_canonical_object_owner:UnsettledCanonicalObject" in errors


def test_duplicate_canonical_object_owner_fails_closed_world_gate() -> None:
    entries = registry.registry_entries()
    duplicate = replace(
        entries[1],
        id="duplicate_candidate_spec_owner",
        canonical_objects_owned=("CandidateSpec",),
    )

    errors = registry.validate_closed_world_audit(entries=(*entries, duplicate))

    assert any(error.startswith("duplicate_canonical_object_owner:CandidateSpec:") for error in errors)


def test_observability_research_object_producer_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "daily_status_digest_observability")
    flags = row["authority_flags"]
    assert isinstance(flags, dict)
    flags["research_object_producer_authority"] = True

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "observability_research_object_authority:daily_status_digest_observability" in errors


def test_provider_adapter_canonical_semantics_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "tiingo_hypothesis_candidate_research_mini_loop")
    row["canonical_objects_owned"] = ["CandidateSpec"]

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "provider_adapter_owns_canonical_semantics:tiingo_hypothesis_candidate_research_mini_loop" in errors


def test_fixture_empirical_evidence_claim_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "test_smoke_fixture_paths")
    flags = row["authority_flags"]
    assert isinstance(flags, dict)
    flags["empirical_evidence_authority"] = True

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "fixture_empirical_evidence_authority:test_smoke_fixture_paths" in errors


def test_legacy_canonical_ownership_without_operator_decision_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "run_research_registry_matrix")
    row["canonical_objects_owned"] = ["StrategyMatrixRow"]
    row["operator_decision_required"] = False

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "legacy_canonical_ownership_without_operator_decision:run_research_registry_matrix" in errors


def test_unknown_maturity_claim_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "canonical_contract_vocabulary")
    row["maturity_level"] = "production_ready"

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "unknown_maturity_level:canonical_contract_vocabulary:production_ready" in errors
    assert "unknown_maturity_claim:production_ready" in registry.validate_closed_world_audit(
        maturity_claims=("production_ready",),
    )


def test_unknown_authority_flag_fails(tmp_path: Path) -> None:
    payload = _payload()
    row = _entry(payload, "canonical_contract_vocabulary")
    flags = row["authority_flags"]
    assert isinstance(flags, dict)
    flags["new_unreviewed_authority"] = True

    errors = registry.validate_registry(_write_payload(tmp_path, payload))

    assert "unknown_authority_flag:canonical_contract_vocabulary:new_unreviewed_authority" in errors
    assert "unknown_authority_flag:new_unreviewed_authority" in registry.validate_closed_world_audit(
        authority_flags=("new_unreviewed_authority",),
    )


def test_audit_report_contains_passing_closed_world_section(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "research").mkdir()
    (repo / "registry.py").write_text("REGISTRY = {}\n", encoding="utf-8")
    (repo / "research" / "run_research.py").write_text("OUT='research/research_latest.json'\n", encoding="utf-8")
    (repo / "research" / "research_latest.json").write_text("{}\n", encoding="utf-8")
    (repo / "research" / "strategy_matrix.csv").write_text("a,b\n", encoding="utf-8")

    report = audit.build_report(repo)

    assert report["closed_world_audit"]["verdict"] == "pass"
    assert report["closed_world_audit"]["failures"] == []
    assert report["closed_world_audit"]["enforcement_scope"]["runtime_behavior_changed"] is False
