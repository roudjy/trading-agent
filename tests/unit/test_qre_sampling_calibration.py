from research.qre_sampling_calibration import (
    calibrate_sampling_context,
    calibrate_sampling_rows,
    sampling_calibration_manifest,
)


def test_sampling_manifest_is_context_only():
    manifest = sampling_calibration_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "prefer_sampling" in manifest["sampling_decisions"]
    assert "crypto_legacy" in manifest["excluded_asset_classes"]
    assert "target_equity_research" in manifest["preferred_research_scopes"]

    authority = manifest["authority"]
    assert authority["sampling_calibration_is_context_only"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_campaign_mutation"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
    assert authority["does_not_fetch_data"] is True
    assert authority["does_not_mutate_candidates"] is True
    assert authority["does_not_mutate_campaigns"] is True
    assert authority["does_not_mutate_strategies"] is True
    assert authority["does_not_mutate_frozen_contracts"] is True


def test_crypto_legacy_is_excluded():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:crypto",
            "ontology_classification": {
                "asset_class": "crypto_legacy",
                "research_scope": "excluded_from_current_research_scope",
            },
        }
    )

    assert result.sampling_decision == "exclude_sampling"
    assert result.sampling_score == -100
    assert "asset_class:crypto_legacy" in result.penalty_axes


def test_excluded_research_scope_is_excluded():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:legacy",
            "asset_class": "equity",
            "research_scope": "legacy_non_target_reference",
        }
    )

    assert result.sampling_decision == "exclude_sampling"
    assert result.sampling_score == -100


def test_fundamental_equity_ready_europe_is_preferred():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:equity:europe",
            "asset_class": "fundamental_equity",
            "research_scope": "target_equity_research",
            "readiness_state": "ready",
            "title": "Europe fundamental factor source_manifest field_coverage",
            "metadata": {"provider": "openfigi", "exchange": "euronext"},
        }
    )

    assert result.sampling_decision == "prefer_sampling"
    assert result.sampling_score >= 60
    assert "asset_class:fundamental_equity" in result.preferred_axes
    assert "research_scope:target_equity_research" in result.preferred_axes
    assert "region:europe" in result.preferred_axes


def test_us_equity_provider_context_is_allowed_or_preferred():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:us",
            "asset_class": "equity",
            "research_scope": "target_source_data_research",
            "readiness_state": "partial",
            "title": "NASDAQ equity provider source_manifest",
        }
    )

    assert result.sampling_decision in {"allow_sampling", "prefer_sampling"}
    assert "region:united_states" in result.preferred_axes


def test_blocked_readiness_deprioritizes_otherwise_good_context():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:blocked",
            "asset_class": "fundamental_equity",
            "research_scope": "target_equity_research",
            "readiness_state": "blocked",
            "title": "fundamental factor Europe",
        }
    )

    assert result.sampling_decision in {"allow_sampling", "deprioritize_sampling"}
    assert "readiness_state:blocked" in result.penalty_axes


def test_crypto_marker_penalizes_text_even_without_crypto_asset_class():
    result = calibrate_sampling_context(
        {
            "subject_id": "candidate:textcrypto",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "readiness_state": "ready",
            "title": "BTC-USD crypto carry legacy",
        }
    )

    assert result.sampling_decision in {"deprioritize_sampling", "exclude_sampling"}
    assert "content:crypto_marker" in result.penalty_axes


def test_rows_ignore_non_mappings():
    rows = [
        {
            "subject_id": "candidate:1",
            "asset_class": "fundamental_equity",
            "research_scope": "target_equity_research",
            "title": "AEX Netherlands fundamental factor",
        },
        "bad",
    ]

    results = calibrate_sampling_rows(rows)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0].subject_id == "candidate:1"
    assert "region:netherlands" in results[0].preferred_axes