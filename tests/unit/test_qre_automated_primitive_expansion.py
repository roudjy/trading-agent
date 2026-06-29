from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import automated_primitive_expansion as a21
from packages.qre_research.generated_primitive_paths import (
    GENERATED_PRIMITIVE_CLOSEOUT_PATH,
    GENERATED_PRIMITIVE_REGISTRY_PATH,
    validate_write_target,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generated_primitive_write_surface_refuses_research_contract_paths() -> None:
    bad = REPO_ROOT / "research" / "research_latest.json"
    try:
        validate_write_target(bad)
    except ValueError as exc:
        assert "generated primitive surfaces" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("research/** path unexpectedly accepted")


def test_validate_existing_cross_sectional_request_is_authoritative_and_closed() -> None:
    result = a21.validate_extension_request(
        repo_root=REPO_ROOT,
        extension_request_id="qpe_e4e83d0c094e8a3e",
    )
    assert result["outcome"] in a21.REQUEST_OUTCOMES
    if result["outcome"] == "VALID_EXTENSION_REQUEST":
        request = result["request"]
        assert request["required_primitive"] == "cross_sectional_rank"
        assert request["primitive_family"] == "cross_sectional_ranking"


def test_resolved_primitive_catalog_is_single_authority_view() -> None:
    catalog = a21.build_resolved_primitive_catalog(REPO_ROOT)
    origins = {row["origin"] for row in catalog["rows"]}
    assert "MANUAL" in origins
    if (REPO_ROOT / GENERATED_PRIMITIVE_REGISTRY_PATH).is_file():
        assert "GENERATED_AUTOMATED" in origins
    assert catalog["resolved_catalog_identity"].startswith("qpc_")


def test_primitive_expansion_loop_is_deterministic_after_materialization() -> None:
    left = a21.run_primitive_expansion_loop(
        repo_root=REPO_ROOT,
        extension_request_id="qpe_e4e83d0c094e8a3e",
    )
    right = a21.run_primitive_expansion_loop(
        repo_root=REPO_ROOT,
        extension_request_id="qpe_e4e83d0c094e8a3e",
    )
    assert left["primitive_spec_id"] == right["primitive_spec_id"]
    assert left["generated_primitive_id"] == right["generated_primitive_id"]
    assert left["program_outcome"] == right["program_outcome"]
    assert (REPO_ROOT / GENERATED_PRIMITIVE_CLOSEOUT_PATH).is_file()
    closeout = json.loads(
        (REPO_ROOT / GENERATED_PRIMITIVE_CLOSEOUT_PATH).read_text(encoding="utf-8")
    )
    assert closeout["program_outcome"] in {
        "PRIMITIVE_AND_STRATEGY_READY_FOR_CAMPAIGN",
        "PRIMITIVE_REGISTERED_STRATEGY_BLOCKED",
        "PRIMITIVE_EXTENSION_QUARANTINED",
        "EXTENSION_REQUEST_REJECTED",
        "AUTOMATED_CAPABILITY_EXPANSION_PARTIAL",
        "NO_VALID_EXTENSION_REQUESTS",
    }
