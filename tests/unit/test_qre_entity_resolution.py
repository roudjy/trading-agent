from research.qre_entity_resolution import (
    entity_resolution_manifest,
    resolve_entities_from_text,
)


def test_entity_resolution_manifest_is_context_only():
    manifest = entity_resolution_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "asset" in manifest["entity_types"]
    assert "provider" in manifest["entity_types"]
    assert manifest["authority"]["entity_resolution_is_context_only"] is True
    assert manifest["authority"]["not_source_identity_authority"] is True
    assert manifest["authority"]["does_not_override_identity_gates"] is True
    assert manifest["authority"]["not_candidate_promotion"] is True


def test_resolves_crypto_asset_as_context_only_entity():
    entities = resolve_entities_from_text(
        title="rsi BTC-USD 1h",
        artifact_path="research/research_latest.json",
    )

    ids = {entity.entity_id for entity in entities}
    assert "asset:BTC-USD" in ids


def test_resolves_sec_companyfacts_provider_marker():
    entities = resolve_entities_from_text(
        title="SEC Companyfacts factor coverage",
        artifact_path="artifacts/external_intelligence/source_manifests_latest.v1.json",
    )

    ids = {entity.entity_id for entity in entities}
    assert "provider:sec_companyfacts" in ids


def test_resolves_openfigi_provider_marker():
    entities = resolve_entities_from_text(title="OpenFIGI identity mapping")

    ids = {entity.entity_id for entity in entities}
    assert "provider:openfigi_symbology" in ids


def test_resolves_artifact_path():
    entities = resolve_entities_from_text(
        title="logs/qre_data_cache_manifest/latest.json",
        artifact_path="logs/qre_data_cache_manifest/latest.json",
    )

    assert any(entity.entity_type == "artifact" for entity in entities)


def test_unknown_text_returns_empty_entities():
    entities = resolve_entities_from_text(title="unclassified text")
    assert entities == ()


def test_policy_tag_is_unresolved_context_not_authority():
    entities = resolve_entities_from_text(
        title="policy action",
        ontology_tags=["policy_action"],
    )

    assert any(entity.entity_type == "policy" for entity in entities)
    assert any(entity.ambiguity_status == "unresolved" for entity in entities)