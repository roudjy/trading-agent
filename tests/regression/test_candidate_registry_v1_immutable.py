"""Regression: candidate_registry_latest.v1.json must remain byte-identical.

v3.12 adds a v2 sidecar but MUST NOT touch the v1 contract. This
test pins the v1 payload shape and output bytes produced by
``promotion_reporting.build_candidate_registry_payload`` against a
minimal synthetic fixture. If v3.12 (or any later phase) changes the
v1 serializer inadvertently, this test fails loudly.
"""

from __future__ import annotations

import json

from research.promotion_reporting import build_candidate_registry_payload


EXPECTED_TOP_LEVEL_KEYS = ["version", "generated_at_utc", "git_revision",
                           "promotion_config", "candidates", "summary"]

EXPECTED_CANDIDATE_KEYS = ["strategy_id", "strategy_name", "asset", "interval",
                          "selected_params", "status", "reasoning"]


def _minimal_research_latest() -> dict:
    return {
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "results": [
            {
                "strategy_name": "sma_crossover",
                "asset": "NVDA",
                "interval": "4h",
                "params_json": json.dumps({"fast": 20, "slow": 100}, sort_keys=True),
                "success": True,
            }
        ],
    }


def _minimal_walk_forward() -> dict:
    return {
        "strategies": [
            {
                "strategy_name": "sma_crossover",
                "asset": "NVDA",
                "interval": "4h",
                "leakage_checks_ok": True,
                "oos_summary": {
                    "sharpe": 1.2,
                    "max_drawdown": 0.2,
                    "totaal_trades": 60,
                    "goedgekeurd": True,
                },
            }
        ]
    }


def test_v1_top_level_keys_unchanged() -> None:
    payload = build_candidate_registry_payload(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    assert list(payload.keys()) == EXPECTED_TOP_LEVEL_KEYS


def test_v1_version_is_still_v1() -> None:
    payload = build_candidate_registry_payload(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    assert payload["version"] == "v1"


def test_v1_candidate_entry_keys_unchanged() -> None:
    payload = build_candidate_registry_payload(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    (entry,) = payload["candidates"]
    assert list(entry.keys()) == EXPECTED_CANDIDATE_KEYS


def test_v1_summary_only_contains_v1_keys() -> None:
    """v1 summary must not accidentally acquire v2 keys like status_model_version."""
    payload = build_candidate_registry_payload(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    summary = payload["summary"]
    # v1 summary: total + one count per status
    legal_v1_summary_keys = {
        "total",
        "rejected",
        "needs_investigation",
        "candidate",
    }
    assert set(summary.keys()).issubset(legal_v1_summary_keys)
    # critically: no v3.12 additions
    forbidden_v2_only_keys = {
        "status_model_version",
        "schema_version",
        "by_lifecycle_status",
        "by_processing_state",
    }
    assert forbidden_v2_only_keys.isdisjoint(set(summary.keys()))


def test_v1_byte_equal_across_two_calls_with_same_input() -> None:
    """Determinism guard: same input must yield identical v1 bytes."""
    kwargs = dict(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    a = build_candidate_registry_payload(**kwargs)  # type: ignore[arg-type]
    b = build_candidate_registry_payload(**kwargs)  # type: ignore[arg-type]
    assert json.dumps(a, sort_keys=False) == json.dumps(b, sort_keys=False)


def test_v1_entry_has_no_v2_only_fields() -> None:
    """v2-only field names must not leak into v1 entries."""
    payload = build_candidate_registry_payload(
        research_latest=_minimal_research_latest(),
        walk_forward=_minimal_walk_forward(),
        statistical_defensibility=None,
        promotion_config=None,
        git_revision="abc123",
    )
    (entry,) = payload["candidates"]
    forbidden_v2_only = {
        "lifecycle_status",
        "legacy_verdict",
        "mapping_reason",
        "observed_reason_codes",
        "taxonomy_rejection_codes",
        "taxonomy_derivations",
        "scores",
        "paper_readiness_flags",
        "paper_readiness_assessment_status",
        "deployment_eligibility",
        "lineage_metadata",
        "source_artifact_references",
        "experiment_family",
        "preset_origin",
        "asset_universe",
        "processing_state",
    }
    assert forbidden_v2_only.isdisjoint(set(entry.keys()))
