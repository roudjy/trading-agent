from research.qre_research_ontology import (
    ASSET_CLASSES,
    BLOCKER_CLASSES,
    ONTOLOGY_TAGS,
    RESEARCH_SCOPES,
    classify_research_text,
    ontology_manifest,
)


def test_ontology_manifest_contains_closed_vocabularies():
    manifest = ontology_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "data_readiness" in manifest["ontology_tags"]
    assert "hypothesis" in manifest["ontology_tags"]
    assert "source_identity" in manifest["ontology_tags"]
    assert "crypto_legacy" in manifest["asset_classes"]
    assert "excluded_from_current_research_scope" in manifest["research_scopes"]
    assert "missing_source_manifest" in manifest["blocker_classes"]


def test_closed_vocabularies_are_unique_and_sorted_enough():
    assert len(ONTOLOGY_TAGS) == len(set(ONTOLOGY_TAGS))
    assert len(ASSET_CLASSES) == len(set(ASSET_CLASSES))
    assert len(RESEARCH_SCOPES) == len(set(RESEARCH_SCOPES))
    assert len(BLOCKER_CLASSES) == len(set(BLOCKER_CLASSES))


def test_crypto_research_records_are_legacy_excluded_not_deleted():
    result = classify_research_text(
        title="rsi BTC-USD 1h",
        artifact_path="research/research_latest.json",
        ontology_tags=["data_readiness", "hypothesis", "strategy_context"],
    )

    assert result.asset_class == "crypto_legacy"
    assert result.research_scope == "excluded_from_current_research_scope"
    assert result.readiness_state == "blocked"
    assert "blocked_data_readiness" in result.blocker_classes
    assert "strategy_context" in result.ontology_tags
    assert "excluded" in result.explanation.lower()


def test_eth_crypto_record_is_legacy_excluded():
    result = classify_research_text(
        title="bollinger_regime ETH-USD 4h",
        artifact_path="research/research_latest.json",
    )

    assert result.asset_class == "crypto_legacy"
    assert result.research_scope == "excluded_from_current_research_scope"
    assert result.readiness_state == "blocked"


def test_equity_context_maps_to_target_equity_research():
    result = classify_research_text(
        title="SEC Companyfacts factor field coverage",
        artifact_path="artifacts/data_readiness/factor_field_coverage_latest.v1.json",
        ontology_tags=["data_readiness", "provider", "field_coverage"],
    )

    assert result.asset_class == "fundamental_equity"
    assert result.research_scope == "target_equity_research"
    assert result.readiness_state in {"unknown", "ready", "blocked"}


def test_unknown_context_remains_unknown_fail_closed_context():
    result = classify_research_text(title="unclassified historical row")

    assert result.asset_class == "unknown"
    assert result.research_scope == "unknown"
    assert result.readiness_state == "unknown"


def test_unknown_tags_are_dropped():
    result = classify_research_text(
        title="SEC Companyfacts",
        ontology_tags=["data_readiness", "not_a_real_tag"],
    )

    assert "data_readiness" in result.ontology_tags
    assert "not_a_real_tag" not in result.ontology_tags


def test_ontology_has_no_execution_authority():
    manifest = ontology_manifest()
    authority = manifest["authority"]

    assert authority["ontology_is_context_only"] is True
    assert authority["not_alpha_authority"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
