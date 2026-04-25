"""Tests for v3.15.3 strategy campaign metadata sidecar."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research._sidecar_io import serialize_canonical
from research.strategy_campaign_metadata import (
    CAMPAIGN_METADATA_SCHEMA_VERSION,
    STRATEGY_CAMPAIGN_METADATA,
    STRATEGY_CAMPAIGN_METADATA_VERSION,
    CampaignMetadataError,
    HypothesisCampaignMetadata,
    _validate_metadata,
    build_campaign_metadata_payload,
    get_metadata,
)
from research.strategy_failure_taxonomy import canonicalize, is_canonical
from research.strategy_hypothesis_catalog import STRATEGY_HYPOTHESIS_CATALOG


_T = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


def test_metadata_present_for_every_catalog_hypothesis() -> None:
    catalog_ids = {h.hypothesis_id for h in STRATEGY_HYPOTHESIS_CATALOG}
    meta_ids = {m.hypothesis_id for m in STRATEGY_CAMPAIGN_METADATA}
    assert catalog_ids == meta_ids


def test_get_metadata_returns_correct_entry() -> None:
    m = get_metadata("trend_pullback_v1")
    assert m.eligible_campaign_types == (
        "daily_primary",
        "survivor_confirmation",
        "weekly_retest",
    )
    assert m.cooldown_policy["base_cooldown_seconds"] == 86_400
    assert m.followup_policy["survivor_confirmation"] is True
    assert m.followup_policy["paper_followup"] is True
    assert m.priority_profile["initial_priority_tier"] == 2


def test_get_metadata_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_metadata("unknown_hypothesis_id_v0")


def test_failure_mode_mapping_resolves_to_canonical_codes() -> None:
    m = get_metadata("trend_pullback_v1")
    for raw, canonical in m.failure_mode_mapping.items():
        assert is_canonical(canonical)
        assert canonicalize(raw) == canonical


def test_payload_pin_block_invariants() -> None:
    payload = build_campaign_metadata_payload(
        generated_at_utc=_T, git_revision="abc"
    )
    assert payload["schema_version"] == CAMPAIGN_METADATA_SCHEMA_VERSION
    assert payload["live_eligible"] is False
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["strategy_campaign_metadata_version"] == (
        STRATEGY_CAMPAIGN_METADATA_VERSION
    )


def test_payload_byte_identical_across_runs() -> None:
    p1 = build_campaign_metadata_payload(generated_at_utc=_T, git_revision="r")
    p2 = build_campaign_metadata_payload(generated_at_utc=_T, git_revision="r")
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_payload_hypothesis_keys_sorted() -> None:
    payload = build_campaign_metadata_payload(
        generated_at_utc=_T, git_revision="abc"
    )
    keys = list(payload["hypotheses"].keys())
    assert keys == sorted(keys)


def test_validate_metadata_rejects_extra_entry() -> None:
    extra = HypothesisCampaignMetadata(
        hypothesis_id="not_in_catalog_v0",
        eligible_campaign_types=(),
        cooldown_policy={},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={},
    )
    with pytest.raises(CampaignMetadataError):
        _validate_metadata(
            STRATEGY_CAMPAIGN_METADATA + (extra,),
            STRATEGY_HYPOTHESIS_CATALOG,
        )


def test_validate_metadata_rejects_missing_entry() -> None:
    truncated = STRATEGY_CAMPAIGN_METADATA[:-1]
    with pytest.raises(CampaignMetadataError):
        _validate_metadata(truncated, STRATEGY_HYPOTHESIS_CATALOG)


def test_validate_metadata_rejects_non_canonical_target() -> None:
    bad = HypothesisCampaignMetadata(
        hypothesis_id="trend_pullback_v1",
        eligible_campaign_types=("daily_primary",),
        cooldown_policy={"base_cooldown_seconds": 86_400},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={"foo_bar": "not_a_canonical_code"},
    )
    others = tuple(
        m for m in STRATEGY_CAMPAIGN_METADATA
        if m.hypothesis_id != "trend_pullback_v1"
    )
    with pytest.raises(CampaignMetadataError):
        _validate_metadata(others + (bad,), STRATEGY_HYPOTHESIS_CATALOG)
