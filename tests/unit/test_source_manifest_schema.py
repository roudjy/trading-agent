from __future__ import annotations

import json

import pytest

from research.external_intelligence.fundamental_provider_registry import build_fundamental_provider_registry
from research.external_intelligence import source_manifest_registry as registry
from research.external_intelligence.source_manifest_schema import validate_source_manifest_rows


def test_source_manifest_rows_validate_deterministically() -> None:
    known_provider_ids = {
        str(row["provider_id"]) for row in build_fundamental_provider_registry()["rows"]
    }
    left = validate_source_manifest_rows(registry.SOURCE_MANIFEST_ROWS, known_provider_ids=known_provider_ids)
    right = validate_source_manifest_rows(registry.SOURCE_MANIFEST_ROWS, known_provider_ids=known_provider_ids)
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def test_unknown_provider_blocks_validation() -> None:
    known_provider_ids = {
        str(row["provider_id"]) for row in build_fundamental_provider_registry()["rows"]
    }
    bad = {**registry.SOURCE_MANIFEST_ROWS[0], "provider_id": "missing_provider"}
    with pytest.raises(ValueError, match="unknown provider_id"):
        validate_source_manifest_rows([bad], known_provider_ids=known_provider_ids)


def test_missing_allowed_use_and_reproducibility_method_block_validation() -> None:
    known_provider_ids = {
        str(row["provider_id"]) for row in build_fundamental_provider_registry()["rows"]
    }
    no_allowed = {**registry.SOURCE_MANIFEST_ROWS[0], "allowed_use": []}
    with pytest.raises(ValueError, match="missing allowed_use"):
        validate_source_manifest_rows([no_allowed], known_provider_ids=known_provider_ids)

    no_repro = {**registry.SOURCE_MANIFEST_ROWS[0], "reproducibility_method": ""}
    with pytest.raises(ValueError, match="missing reproducibility_method"):
        validate_source_manifest_rows([no_repro], known_provider_ids=known_provider_ids)


def test_identity_and_metadata_sources_must_forbid_fundamental_field_readiness() -> None:
    known_provider_ids = {
        str(row["provider_id"]) for row in build_fundamental_provider_registry()["rows"]
    }
    bad = {
        **registry.SOURCE_MANIFEST_ROWS[7],
        "forbidden_use": [item for item in registry.SOURCE_MANIFEST_ROWS[7]["forbidden_use"] if item != "fundamental_field_readiness"],
    }
    with pytest.raises(ValueError, match="must forbid fundamental_field_readiness"):
        validate_source_manifest_rows([bad], known_provider_ids=known_provider_ids)
