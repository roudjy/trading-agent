"""Unit tests for research.diagnostics.failure_modes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics.failure_modes import (
    OUTCOME_CLASSES,
    build_failure_modes_artifact,
    compute_failure_mode_distribution,
)


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def test_empty_inputs(fixed_now: datetime):
    out = compute_failure_mode_distribution(now_utc=fixed_now)
    assert out["schema_version"] == "1.0"
    assert out["total_campaigns_observed"] == 0
    assert out["total_failure_events_observed"] == 0
    assert out["top_failure_reasons"] == []
    assert out["technical_vs_research_failure_counts"]["unknown"] == 0


def test_completed_no_survivor_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "completed",
                    "failure_reason": "no_survivor",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["completed_no_survivor"] == 1


def test_degenerate_no_survivor_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "completed",
                    "failure_reason": "screening_no_survivors",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["degenerate_no_survivors"] == 1


def test_technical_failure_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "failed",
                    "failure_reason": "worker_crash",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["technical_failure"] == 1
    # Surfaces in by_preset because it failed.
    by_preset_names = {p["name"] for p in out["by_preset"]}
    assert "trend_4h" in by_preset_names


def test_repeated_failure_cluster_detected(fixed_now: datetime):
    campaigns = [
        {
            "campaign_id": f"c{i}",
            "outcome": "failed",
            "failure_reason": "lease_lost",
            "preset": "ema_1h",
        }
        for i in range(4)
    ]
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": campaigns},
        now_utc=fixed_now,
    )
    clusters = out["repeated_failure_clusters"]
    assert clusters
    # v3.15.15.6 cluster row shape: outcome_class + preset_name +
    # cluster_key_quality + source. count threshold lowered to >= 2.
    assert clusters[0]["preset_name"] == "ema_1h"
    assert clusters[0]["outcome_class"] == "technical_failure"
    assert clusters[0]["count"] == 4
    assert clusters[0]["cluster_key_quality"] == "partial"
    assert clusters[0]["source"] == "registry"


def test_unknown_outcome_lands_in_unknown_bucket(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": [{"campaign_id": "c1", "outcome": "weird"}]},
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 1
    # v3.15.15.6: unknown_or_unclassified_count now ranges over ALL
    # campaigns (not just the narrow failed-records subset), so an
    # unmappable outcome correctly contributes 1.
    assert out["unknown_or_unclassified_count"] == 1


def test_ledger_events_contribute_to_failure_aggregates(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        ledger_events=[
            {
                "outcome": "failed",
                "failure_reason": "worker_crash",
                "preset": "trend_4h",
                "asset": "BTC",
                "timeframe": "1h",
            },
            {
                "outcome": "failed",
                "failure_reason": "worker_crash",
                "preset": "trend_4h",
                "asset": "ETH",
                "timeframe": "1h",
            },
        ],
        now_utc=fixed_now,
    )
    reasons = {r["name"]: r["count"] for r in out["top_failure_reasons"]}
    assert reasons.get("worker_crash") == 2
    assert {a["name"] for a in out["by_asset"]} == {"BTC", "ETH"}


def test_outcome_classes_taxonomy_stable():
    # Stable identifiers — frontends must be able to rely on these strings.
    assert "technical_failure" in OUTCOME_CLASSES
    assert "research_rejection" in OUTCOME_CLASSES
    assert "completed_with_survivor" in OUTCOME_CLASSES
    assert "unknown" in OUTCOME_CLASSES


def test_deterministic_output_for_fixed_inputs(fixed_now: datetime):
    inputs = {
        "campaigns": [
            {"campaign_id": "c1", "outcome": "completed"},
            {"campaign_id": "c2", "outcome": "failed", "failure_reason": "x", "preset": "p"},
        ]
    }
    a = compute_failure_mode_distribution(
        registry_payload=inputs, now_utc=fixed_now
    )
    b = compute_failure_mode_distribution(
        registry_payload=inputs, now_utc=fixed_now
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_build_failure_modes_artifact_with_real_files(
    tmp_path: Path, fixed_now: datetime
):
    reg = tmp_path / "registry.json"
    reg.write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "campaign_id": "c1",
                        "outcome": "failed",
                        "failure_reason": "worker_crash",
                        "preset": "trend_4h",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    led = tmp_path / "ledger.jsonl"
    led.write_text(
        json.dumps({"outcome": "failed", "failure_reason": "lease_lost", "preset": "ema_1h"})
        + "\n",
        encoding="utf-8",
    )
    out = build_failure_modes_artifact(
        now_utc=fixed_now,
        registry_path=reg,
        ledger_path=led,
    )
    assert out["total_campaigns_observed"] == 1
    assert out["total_failure_events_observed"] == 2
    assert out["source"]["ledger_state"] == "valid"
    assert out["source"]["registry_state"] == "valid"
    assert out["source"]["max_ledger_lines"] == 10000


# ---------------------------------------------------------------------------
# v3.15.15.4 — taxonomy patch tests
#
# These tests verify two things at once:
#   1. The pre-v3.15.15.4 mapping is preserved byte-for-byte (no silent
#      reinterpretation of older artifacts);
#   2. The launcher-literal outcomes the diagnostics layer used to classify
#      as ``"unknown"`` now land in their dedicated outcome class.
# ---------------------------------------------------------------------------


from research.diagnostics.failure_modes import _classify  # private API for testing


# Pre-v3.15.15.4 (outcome, failure_reason) pairs and their expected class.
# This is the entire historical surface; the regression below pins it.
_PRE_PATCH_PAIRS = [
    # (outcome, failure_reason, expected_class)
    ("completed", None, "completed_no_survivor"),
    ("completed", "no_survivor", "completed_no_survivor"),
    ("completed", "candidate_promoted", "completed_with_survivor"),
    ("completed", "promotion_pass", "completed_with_survivor"),
    ("no_signal", None, "research_rejection"),
    ("near_pass", None, "research_rejection"),
    ("failed", None, "technical_failure"),
    ("failed", "screening_no_survivors", "degenerate_no_survivors"),
    ("failed", "worker_crash", "technical_failure"),
    ("failed", "lease_lost", "technical_failure"),
    ("canceled", None, "canceled"),
    ("running", None, "running"),
    ("weird_unknown_value", None, "unknown"),
    (None, None, "unknown"),
]


@pytest.mark.parametrize(
    "outcome, failure_reason, expected_class", _PRE_PATCH_PAIRS
)
def test_pre_patch_classification_unchanged(
    outcome: str | None, failure_reason: str | None, expected_class: str
):
    """Backward-compat: every (outcome, failure_reason) pair recognised
    pre-v3.15.15.4 must classify identically post-patch."""
    assert _classify(outcome, failure_reason) == expected_class


# v3.15.15.4 — launcher-literal outcomes that previously landed in "unknown".
# Each row asserts the literal now classifies into its dedicated bucket.
_LAUNCHER_LITERAL_PAIRS = [
    # outcome, failure_reason, expected_class
    ("degenerate_no_survivors", "degenerate_no_evaluable_pairs", "degenerate_no_survivors"),
    ("technical_failure", "worker_crash", "technical_failure"),
    ("technical_failure", "timeout", "technical_failure"),
    ("completed_with_candidates", "none", "completed_with_survivor"),
    ("completed_no_survivor", "none", "completed_no_survivor"),
    ("research_rejection", "screening_failed_oos_returns", "research_rejection"),
    ("paper_blocked", "insufficient_oos_days", "paper_blocked"),
    ("paper_blocked", "excessive_divergence", "paper_blocked"),
    ("integrity_failed", "integrity_violation", "technical_failure"),
    ("aborted", "operator_aborted", "canceled"),
    ("canceled_duplicate", "duplicate_detected", "canceled"),
    ("canceled_upstream_stale", "upstream_artifact_stale", "canceled"),
    # Pre-v3.15.5 backward-compat — old ledgers may still contain this literal.
    ("worker_crashed", "worker_crash", "technical_failure"),
]


@pytest.mark.parametrize(
    "outcome, failure_reason, expected_class", _LAUNCHER_LITERAL_PAIRS
)
def test_launcher_literal_outcome_classifies_correctly(
    outcome: str, failure_reason: str | None, expected_class: str
):
    """Every launcher v3.15.5+ outcome literal lands in its dedicated class
    (not in ``unknown``)."""
    assert _classify(outcome, failure_reason) == expected_class


def test_paper_blocked_is_a_dedicated_outcome_class():
    """v3.15.15.4 introduces ``paper_blocked`` as its own class (NOT folded
    into ``completed_no_survivor``). A candidate exists but paper-readiness
    blocked promotion — that is semantically distinct from no-survivor.
    """
    assert "paper_blocked" in OUTCOME_CLASSES
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "paper_blocked",
                    "failure_reason": "insufficient_oos_days",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC),
    )
    assert out["campaigns_by_outcome_class"]["paper_blocked"] == 1
    assert out["campaigns_by_outcome_class"]["completed_no_survivor"] == 0
    assert out["campaigns_by_outcome_class"]["unknown"] == 0


def test_known_launcher_outcomes_never_land_in_unknown(fixed_now: datetime):
    """Comprehensive: feed every launcher v3.15.5+ literal once. Every
    record must land in a recognised outcome_class — none in ``unknown``."""
    launcher_literals = [
        "completed_with_candidates",
        "completed_no_survivor",
        "degenerate_no_survivors",
        "technical_failure",
        "research_rejection",
        "paper_blocked",
        "integrity_failed",
        "aborted",
        "canceled_duplicate",
        "canceled_upstream_stale",
        "worker_crashed",
    ]
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {"campaign_id": f"c{i}", "outcome": lit, "preset": "p"}
                for i, lit in enumerate(launcher_literals)
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 0


def test_unknown_outcome_still_lands_in_unknown(fixed_now: datetime):
    """The ``unknown`` bucket remains the catch-all for genuinely
    unrecognised values — the v3.15.15.4 patch only adds known ones."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {"campaign_id": "c1", "outcome": "made_up_outcome_xyz"}
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 1


def test_outcome_classes_taxonomy_includes_paper_blocked_v3_15_15_4():
    """Pin the taxonomy size + ``paper_blocked`` membership."""
    assert "paper_blocked" in OUTCOME_CLASSES
    assert len(OUTCOME_CLASSES) == 9


# ---------------------------------------------------------------------------
# v3.15.15.6 — diagnostic_context, alias readers, fallback clusters,
# digest passthrough, by_meaningful_classification
# ---------------------------------------------------------------------------


def _vps_shape_record(
    *,
    campaign_id: str,
    outcome: str | None,
    reason_code: str | None,
    preset_name: str,
    state: str = "completed",
    campaign_type: str = "daily_primary",
    meaningful_classification: str | None = "uninformative_technical_failure",
    worker_id: str | None = "launcher-w-001",
    actual_runtime_seconds: int | None = 30,
    spawned_at_utc: str = "2026-04-28T11:00:00Z",
    finished_at_utc: str = "2026-04-28T11:01:00Z",
) -> dict:
    """Build a record matching the live VPS launcher emit shape.

    Key shape facts the v3.15.15.6 patch addresses:

    * ``reason_code`` (not ``failure_reason``) is the failure-reason
      field name.
    * ``preset_name`` (no ``preset`` alias) is the preset field.
    * ``worker_id`` lives nested in ``lease.worker_id`` only.
    * ``actual_runtime_seconds`` (not ``runtime_min``).
    * ``strategy_family``, ``asset_class``, ``hypothesis_id``,
      ``timeframe``, ``asset`` are absent or null.
    """
    record: dict = {
        "campaign_id": campaign_id,
        "preset_name": preset_name,
        "campaign_type": campaign_type,
        "state": state,
        "outcome": outcome,
        "reason_code": reason_code,
        "meaningful_classification": meaningful_classification,
        "actual_runtime_seconds": actual_runtime_seconds,
        "spawned_at_utc": spawned_at_utc,
        "started_at_utc": spawned_at_utc,
        "finished_at_utc": finished_at_utc,
        "strategy_family": None,
        "asset_class": None,
        "subtype": None,
        "lineage_root_campaign_id": campaign_id,
    }
    if worker_id is not None:
        record["lease"] = {
            "lease_id": f"lease-{campaign_id}",
            "worker_id": worker_id,
            "leased_at_utc": spawned_at_utc,
        }
    return record


def test_reason_code_alias_populates_top_failure_reasons(fixed_now: datetime):
    """Live VPS records carry ``reason_code``, not ``failure_reason``.

    Pre-v3.15.15.6 the parser missed this and ``top_failure_reasons``
    came back empty. After the alias addition, the bucket is populated.
    """
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id=f"c-degen-{i}",
                    outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="vol_compression_breakout_crypto_1h",
                )
                for i in range(15)
            ]
            + [
                _vps_shape_record(
                    campaign_id=f"c-tech-{i}",
                    outcome="worker_crashed",
                    reason_code="worker_crash",
                    preset_name="crypto_diagnostic_1h",
                    state="failed",
                )
                for i in range(4)
            ]
        },
        now_utc=fixed_now,
    )
    reasons = {r["name"]: r["count"] for r in out["top_failure_reasons"]}
    assert reasons.get("degenerate_no_evaluable_pairs") == 15
    assert reasons.get("worker_crash") == 4
    # Source label: registry-derived has no source key (digest fallback would).
    assert "source" not in out["top_failure_reasons"][0]


def test_lease_worker_id_populates_by_worker_id(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id=f"c-{i}",
                    outcome="worker_crashed",
                    reason_code="worker_crash",
                    preset_name="ema_1h",
                    state="failed",
                    worker_id=f"launcher-w-{i:02d}",
                )
                for i in range(3)
            ]
        },
        now_utc=fixed_now,
    )
    workers = {w["name"]: w["count"] for w in out["by_worker_id"]}
    assert workers == {
        "launcher-w-00": 1,
        "launcher-w-01": 1,
        "launcher-w-02": 1,
    }


def test_by_campaign_type_populates_for_all_campaigns(fixed_now: datetime):
    """``by_campaign_type`` must aggregate across ALL campaigns, including
    completed degenerate ones — not just the narrow failed-records subset."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id=f"c-pri-{i}",
                    outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="trend_pullback_crypto_1h",
                    campaign_type="daily_primary",
                )
                for i in range(15)
            ]
            + [
                _vps_shape_record(
                    campaign_id=f"c-ctrl-{i}",
                    outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="trend_equities_4h_baseline",
                    campaign_type="daily_control",
                )
                for i in range(5)
            ]
        },
        now_utc=fixed_now,
    )
    types = {t["name"]: t["count"] for t in out["by_campaign_type"]}
    assert types == {"daily_primary": 15, "daily_control": 5}


def test_by_meaningful_classification_populates(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id="c-1",
                    outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="p1",
                    meaningful_classification="meaningful_failure_confirmed",
                ),
                _vps_shape_record(
                    campaign_id="c-2",
                    outcome="worker_crashed",
                    reason_code="worker_crash",
                    preset_name="p2",
                    state="failed",
                    meaningful_classification="uninformative_technical_failure",
                ),
            ]
        },
        now_utc=fixed_now,
    )
    classes = {c["name"]: c["count"] for c in out["by_meaningful_classification"]}
    assert classes == {
        "meaningful_failure_confirmed": 1,
        "uninformative_technical_failure": 1,
    }


def test_repeated_clusters_partial_quality_in_registry_only_mode(fixed_now: datetime):
    """Live VPS data has preset_name but no hypothesis_id / asset / timeframe.

    Cluster key falls back to ``partial`` quality; ``repeated_failure_clusters``
    becomes useful instead of always empty.
    """
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id=f"c-{i}",
                    outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="vol_compression_breakout_crypto_1h",
                )
                for i in range(3)
            ]
        },
        now_utc=fixed_now,
    )
    clusters = out["repeated_failure_clusters"]
    assert clusters
    cluster = clusters[0]
    assert cluster["count"] == 3
    assert cluster["outcome_class"] == "degenerate_no_survivors"
    assert cluster["preset_name"] == "vol_compression_breakout_crypto_1h"
    assert cluster["cluster_key_quality"] == "partial"
    assert cluster["timeframe"] is None  # no over-inference from preset_name
    assert cluster["asset"] is None
    assert cluster["hypothesis_id"] is None
    assert cluster["source"] == "registry"


def test_repeated_clusters_full_quality_when_all_fields_present(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": f"c-{i}",
                    "outcome": "degenerate_no_survivors",
                    "reason_code": "degenerate_no_evaluable_pairs",
                    "preset_name": "trend_4h",
                    "hypothesis_id": "h_v1",
                    "strategy_family": "trend",
                    "timeframe": "4h",
                    "asset": "BTC",
                    "campaign_type": "daily_primary",
                    "state": "completed",
                }
                for i in range(2)
            ]
        },
        now_utc=fixed_now,
    )
    clusters = out["repeated_failure_clusters"]
    assert clusters
    assert clusters[0]["cluster_key_quality"] == "full"
    assert clusters[0]["hypothesis_id"] == "h_v1"
    assert clusters[0]["timeframe"] == "4h"
    assert clusters[0]["asset"] == "BTC"


def test_repeated_clusters_weak_quality_when_only_campaign_type(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": f"c-{i}",
                    "outcome": "worker_crashed",
                    "reason_code": "worker_crash",
                    "campaign_type": "daily_primary",
                    "state": "failed",
                }
                for i in range(2)
            ]
        },
        now_utc=fixed_now,
    )
    clusters = out["repeated_failure_clusters"]
    assert clusters
    assert clusters[0]["cluster_key_quality"] == "weak"
    assert clusters[0]["preset_name"] is None


def test_diagnostic_context_registry_only_mode(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": [_vps_shape_record(
            campaign_id="c1", outcome="degenerate_no_survivors",
            reason_code="degenerate_no_evaluable_pairs", preset_name="p1")]},
        registry_state="valid",
        ledger_state="absent",
        digest_state="absent",
        screening_evidence_state="absent",
        rolled_up_ledger_state="absent",
        spawn_proposals_state="absent",
        now_utc=fixed_now,
    )
    ctx = out["diagnostic_context"]
    assert ctx["diagnostic_mode"] == "registry_only"
    assert ctx["registry_available"] is True
    assert ctx["ledger_available"] is False
    assert ctx["digest_available"] is False
    assert ctx["screening_evidence_available"] is False
    assert ctx["failure_reason_detail_available"] is True  # reason_code aliased
    assert "campaign_evidence_ledger_absent" in ctx["limitations"]
    assert "screening_evidence_absent" in ctx["limitations"]
    assert "registry_only_mode" in ctx["limitations"]
    assert "hypothesis_id_missing_from_source_artifact" in ctx["limitations"]
    assert "strategy_family_field_present_but_unpopulated_by_writer" in ctx["limitations"]
    assert "research/campaign_evidence_ledger.jsonl" in ctx["missing_evidence_artifacts"]
    assert ctx["diagnostic_evidence_status"] == "partial"
    assert "campaign_record.hypothesis_id" in ctx["future_writer_enrichment_required"]


def test_diagnostic_context_registry_plus_digest_enriched(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": [_vps_shape_record(
            campaign_id="c1", outcome="degenerate_no_survivors",
            reason_code="degenerate_no_evaluable_pairs", preset_name="p1")]},
        digest_payload={"top_failure_reasons": [{"name": "x", "count": 1}]},
        registry_state="valid",
        ledger_state="absent",
        digest_state="valid",
        screening_evidence_state="absent",
        rolled_up_ledger_state="absent",
        spawn_proposals_state="absent",
        now_utc=fixed_now,
    )
    ctx = out["diagnostic_context"]
    assert ctx["diagnostic_mode"] == "registry_plus_digest_enriched"
    assert "registry_plus_digest_only_mode" in ctx["limitations"]
    assert ctx["digest_available"] is True


def test_diagnostic_context_registry_unavailable_when_absent(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_state="absent",
        ledger_state="absent",
        digest_state="absent",
        now_utc=fixed_now,
    )
    ctx = out["diagnostic_context"]
    assert ctx["registry_available"] is False
    assert ctx["diagnostic_evidence_status"] == "unavailable"
    assert "registry_absent" in ctx["limitations"]


def test_conflicting_failure_reason_fields_emits_limitation(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "failed",
                    "failure_reason": "explicit_reason",
                    "reason_code": "different_reason",  # conflict
                    "preset_name": "p1",
                    "state": "failed",
                }
            ]
        },
        registry_state="valid",
        digest_state="absent",
        now_utc=fixed_now,
    )
    ctx = out["diagnostic_context"]
    assert "conflicting_failure_reason_fields" in ctx["limitations"]
    # failure_reason wins (primary).
    reasons = {r["name"]: r["count"] for r in out["top_failure_reasons"]}
    assert reasons.get("explicit_reason") == 1
    assert "different_reason" not in reasons


def test_digest_top_failure_reasons_used_as_fallback_when_registry_silent(
    fixed_now: datetime,
):
    """If the registry has no failure-reason detail, surface the digest's
    pre-computed counts and tag them with ``source="digest"``."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                # outcome=None → no failure_reason can be derived
                {"campaign_id": "c1", "outcome": None, "preset_name": "p1"}
            ]
        },
        digest_payload={
            "top_failure_reasons": [
                {"name": "degenerate_no_evaluable_pairs", "count": 15},
                {"name": "worker_crash", "count": 4},
            ]
        },
        registry_state="valid",
        digest_state="valid",
        now_utc=fixed_now,
    )
    reasons = out["top_failure_reasons"]
    assert reasons[0]["name"] == "degenerate_no_evaluable_pairs"
    assert reasons[0]["count"] == 15
    assert reasons[0]["source"] == "digest"


def test_widened_failure_outcome_class_counts(fixed_now: datetime):
    """``technical_vs_research_failure_counts`` ranges over ALL campaigns
    and includes degenerate_no_survivors + paper_blocked first-class."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id="c1", outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs", preset_name="p1"),
                _vps_shape_record(
                    campaign_id="c2", outcome="worker_crashed",
                    reason_code="worker_crash", preset_name="p2", state="failed"),
                _vps_shape_record(
                    campaign_id="c3", outcome="research_rejection",
                    reason_code="hypothesis_invalidated", preset_name="p3"),
                _vps_shape_record(
                    campaign_id="c4", outcome="paper_blocked",
                    reason_code="insufficient_oos_days", preset_name="p4"),
            ]
        },
        now_utc=fixed_now,
    )
    counts = out["technical_vs_research_failure_counts"]
    assert counts["degenerate_no_survivors"] == 1
    assert counts["technical_failure"] == 1  # worker_crashed
    assert counts["research_rejection"] == 1
    assert counts["paper_blocked"] == 1
    assert counts["unknown"] == 0


def test_no_over_inference_of_timeframe_from_preset_name(fixed_now: datetime):
    """Even though ``vol_compression_breakout_crypto_1h`` encodes ``_1h``,
    diagnostics MUST NOT extract timeframe heuristically."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                _vps_shape_record(
                    campaign_id="c1", outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="vol_compression_breakout_crypto_1h"),
                _vps_shape_record(
                    campaign_id="c2", outcome="degenerate_no_survivors",
                    reason_code="degenerate_no_evaluable_pairs",
                    preset_name="vol_compression_breakout_crypto_1h"),
            ]
        },
        registry_state="valid",
        now_utc=fixed_now,
    )
    # by_timeframe must stay empty (no string field, no inference).
    assert out["by_timeframe"] == []
    # Cluster row's timeframe must be None (not "1h").
    clusters = out["repeated_failure_clusters"]
    assert clusters[0]["timeframe"] is None
    # And the limitation must be reported.
    assert (
        "timeframe_derivable_from_preset_only"
        in out["diagnostic_context"]["limitations"]
    )


# ---------------------------------------------------------------------------
# v3.15.15.7 — Evidence ledger path hotfix
#
# Pre-v3.15.15.7: ``CAMPAIGN_EVIDENCE_LEDGER_PATH`` pointed at
# ``research/campaign_evidence_ledger.jsonl`` (no ``_latest.v1`` suffix).
# The launcher writes to ``research/campaign_evidence_ledger_latest.v1.jsonl``
# — the project-wide snapshot-current convention. Result: diagnostics
# silently reported ``ledger_available=false`` and stayed in
# ``diagnostic_mode=registry_plus_digest_enriched`` even though the
# launcher had been writing 80+ events to disk since project start.
#
# These tests pin the fix end-to-end:
# 1. when the ledger exists at the real writer path and diagnostics is
#    pointed there, ``ledger_available=true`` and ``diagnostic_mode
#    =ledger_enriched``.
# 2. when only the OLD wrong filename exists on disk, diagnostics does
#    NOT silently fall back to it.
# 3. the imported runtime value of ``CAMPAIGN_EVIDENCE_LEDGER_PATH``
#    ends with the ``_latest.v1.jsonl`` suffix.
# ---------------------------------------------------------------------------


def test_ledger_available_true_when_file_exists_at_real_writer_path(
    tmp_path: Path, fixed_now: datetime, monkeypatch: pytest.MonkeyPatch
):
    """Real-path read: writer path = diagnostics path → ledger_enriched mode."""
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    real_ledger = research_dir / "campaign_evidence_ledger_latest.v1.jsonl"
    # Write three launcher-shaped events at the real writer path.
    events_lines = [
        json.dumps(
            {
                "campaign_id": "c-degen-1",
                "event_type": "campaign_completed",
                "outcome": "degenerate_no_survivors",
                "reason_code": "degenerate_no_evaluable_pairs",
                "preset_name": "vol_compression_breakout_crypto_1h",
                "campaign_type": "daily_primary",
                "at_utc": "2026-04-28T11:05:00Z",
            }
        ),
        json.dumps(
            {
                "campaign_id": "c-tech-1",
                "event_type": "campaign_failed",
                "outcome": "worker_crashed",
                "reason_code": "worker_crash",
                "preset_name": "crypto_diagnostic_1h",
                "campaign_type": "daily_primary",
                "at_utc": "2026-04-28T11:00:30Z",
            }
        ),
        json.dumps(
            {
                "campaign_id": "c-spawn-1",
                "event_type": "campaign_spawned",
                "outcome": None,
                "reason_code": "none",
                "preset_name": "trend_pullback_crypto_1h",
                "campaign_type": "daily_primary",
                "at_utc": "2026-04-28T10:00:00Z",
            }
        ),
    ]
    real_ledger.write_text("\n".join(events_lines) + "\n", encoding="utf-8")

    # Build the artifact via the high-level entry point with the ledger
    # path overridden — same shape that the CLI uses post-fix.
    payload = build_failure_modes_artifact(
        now_utc=fixed_now,
        registry_path=research_dir / "campaign_registry_latest.v1.json",  # absent
        ledger_path=real_ledger,
    )
    ctx = payload["diagnostic_context"]
    assert ctx["ledger_available"] is True, (
        "ledger at the real writer path must resolve as available; "
        "post-v3.15.15.7 behaviour"
    )
    assert ctx["diagnostic_mode"] == "ledger_enriched", (
        f"expected ledger_enriched mode, got {ctx['diagnostic_mode']!r}"
    )
    assert "campaign_evidence_ledger_absent" not in ctx["limitations"]


def test_ledger_unavailable_when_only_old_wrong_path_exists(
    tmp_path: Path, fixed_now: datetime
):
    """Old-path regression guard: diagnostics does NOT silently fall back to
    the pre-v3.15.15.7 wrong filename if it happens to exist on disk."""
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    # Plant a file at the OLD wrong filename only.
    wrong_path = research_dir / "campaign_evidence_ledger.jsonl"
    wrong_path.write_text(
        json.dumps(
            {
                "campaign_id": "c-1",
                "event_type": "campaign_completed",
                "outcome": "degenerate_no_survivors",
                "reason_code": "degenerate_no_evaluable_pairs",
                "preset_name": "p1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # Real writer path is INTENTIONALLY absent.
    real_ledger = research_dir / "campaign_evidence_ledger_latest.v1.jsonl"
    assert not real_ledger.exists()

    payload = build_failure_modes_artifact(
        now_utc=fixed_now,
        registry_path=research_dir / "campaign_registry_latest.v1.json",  # absent
        ledger_path=real_ledger,
    )
    ctx = payload["diagnostic_context"]
    assert ctx["ledger_available"] is False, (
        "diagnostics must NOT silently use the pre-v3.15.15.7 wrong filename "
        "as a fallback — that would mask the regression test in paths.py"
    )
    assert "campaign_evidence_ledger_absent" in ctx["limitations"]


def test_campaign_evidence_ledger_path_constant_has_latest_v1_suffix():
    """Imported runtime value of the constant ends with the canonical suffix.

    Belt-and-braces companion to the text-only drift test in
    ``test_observability_paths.py`` — pins the actual ``Path`` object's
    filename so a future refactor (e.g. splitting the constant onto
    multiple lines, computing it at import time, adding path joining)
    cannot silently regress.
    """
    from research.diagnostics.paths import CAMPAIGN_EVIDENCE_LEDGER_PATH

    assert (
        CAMPAIGN_EVIDENCE_LEDGER_PATH.name
        == "campaign_evidence_ledger_latest.v1.jsonl"
    )
