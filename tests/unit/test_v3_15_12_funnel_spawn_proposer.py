"""v3.15.12 — funnel spawn proposer unit tests.

Covers all 11 rules plus the six operator-review hardenings:

1. strong proposal_fingerprint over 6 fields
2. per-fingerprint cooldown via append-only JSONL history
3. exploration coverage over BOTH pct AND scope spread
4. dead-zone suppression decays after DEAD_ZONE_DECAY_DAYS
5. viability == stop_or_pivot toggles proposal_mode = diagnostic_only
6. deterministic priority_tier enum + reason_trace on every proposal
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from research._sidecar_io import serialize_canonical
from research.funnel_spawn_proposer import (
    DEAD_ZONE_DECAY_DAYS,
    ENFORCEMENT_STATE_ADVISORY,
    EXPLORATION_MIN_DISTINCT_ASSETS,
    EXPLORATION_MIN_DISTINCT_FAMILIES,
    EXPLORATION_RESERVATION_PCT,
    FINGERPRINT_COOLDOWN_DAYS,
    MAX_PROPOSALS_PER_RUN_DIAGNOSTIC,
    MAX_PROPOSALS_PER_RUN_NORMAL,
    MODE_SHADOW,
    PRIORITY_TIER_ORDER,
    PROPOSAL_MODE_DIAGNOSTIC,
    PROPOSAL_MODE_NORMAL,
    PROPOSAL_TYPE_CONFIRMATION,
    PROPOSAL_TYPE_DEAD_ZONE_REVISIT,
    PROPOSAL_TYPE_EXPLORATION,
    PROPOSAL_TYPE_PARAM_RETRY,
    SPAWN_PROPOSALS_SCHEMA_VERSION,
    append_proposal_history,
    build_spawn_proposals_payload,
    compute_proposal_fingerprint,
    load_recent_proposal_fingerprints,
    write_spawn_proposals_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _candidate(
    *,
    preset: str = "trend_pullback_crypto_1h",
    asset: str = "crypto",
    interval: str = "1h",
    family: str = "trend_pullback",
    hypothesis: str = "hyp_42",
    stage_result: str = "needs_investigation",
    pass_kind: str | None = "exploratory",
    near: dict[str, Any] | None = None,
    grid_digest: str = "abc123",
) -> dict[str, Any]:
    return {
        "preset_name": preset,
        "asset": asset,
        "interval": interval,
        "strategy_family": family,
        "hypothesis_id": hypothesis,
        "stage_result": stage_result,
        "pass_kind": pass_kind,
        "near_pass": near
        or {"is_near_pass": False, "distance": None, "nearest_failed_criterion": None},
        "sampling": {"sampled_parameter_digest": grid_digest},
    }


def _screening(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"candidates": candidates}


def _zones(zones: list[dict[str, Any]]) -> dict[str, Any]:
    return {"zones": zones}


def _ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"hypothesis_evidence": rows}


def _basic_kwargs(
    *,
    screening: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    ig: dict[str, Any] | None = None,
    stop: dict[str, Any] | None = None,
    dead: dict[str, Any] | None = None,
    via: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    cooldown: set[str] | None = None,
) -> dict[str, Any]:
    return dict(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence=screening,
        evidence_ledger=ledger,
        information_gain=ig,
        stop_conditions=stop,
        dead_zones=dead,
        viability=via,
        campaign_registry=registry,
        cooldown_fingerprints=cooldown,
    )


# ── R1: confirmation from exploratory pass ─────────────────────────────


def test_r1_exploratory_pass_yields_high_tier_confirmation() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]))
    )
    proposals = payload["proposed_campaigns"]
    assert len(proposals) == 1
    p = proposals[0]
    assert p["proposal_type"] == PROPOSAL_TYPE_CONFIRMATION
    assert p["priority_tier"] == "HIGH"
    assert "exploratory_pass_detected" in p["reason_trace"]
    assert p["spawn_reason"] == "confirmation_from_exploratory_pass"


# ── R2: near-pass parameter retry ──────────────────────────────────────


def test_r2_near_pass_yields_medium_tier_param_retry() -> None:
    near = {
        "is_near_pass": True,
        "distance": 0.001,
        "nearest_failed_criterion": "profit_factor_below_floor",
    }
    cand = _candidate(stage_result="near_pass", pass_kind=None, near=near)
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([cand]))
    )
    proposals = payload["proposed_campaigns"]
    assert len(proposals) == 1
    assert proposals[0]["proposal_type"] == PROPOSAL_TYPE_PARAM_RETRY
    assert proposals[0]["priority_tier"] == "MEDIUM"
    assert any(
        "nearest_failed_criterion=profit_factor_below_floor" in t
        for t in proposals[0]["reason_trace"]
    )


# ── R3: stop_conditions blocks proposals ───────────────────────────────


def test_r3_stop_condition_freeze_blocks_confirmation() -> None:
    stop = {
        "decisions": [
            {
                "scope_type": "preset",
                "scope_id": "trend_pullback_crypto_1h",
                "recommended_decision": "FREEZE_PRESET",
                "enforcement_state": "advisory_only",
            }
        ]
    }
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]), stop=stop)
    )
    assert payload["proposed_campaigns"] == []


# ── R4: dead-zone suppression with decay ───────────────────────────────


def test_r4_active_dead_zone_suppresses_within_decay_window() -> None:
    """Recent dead-zone activity → suppression entry, no proposal."""
    last_seen = (_AS_OF - timedelta(days=2)).isoformat()
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            ledger=_ledger(
                [
                    {
                        "preset_name": "p1",
                        "strategy_family": "momentum",
                        "hypothesis_id": "h",
                        "campaign_count": 5,
                        "rejection_count": 5,
                        "technical_failure_count": 0,
                        "promotion_candidate_count": 0,
                        "paper_ready_count": 0,
                        "exploratory_pass_count": 0,
                        "degenerate_count": 0,
                        "last_outcome": "research_rejection",
                        "last_seen_at_utc": last_seen,
                    }
                ]
            ),
            dead=_zones(
                [
                    {
                        "asset": "crypto",
                        "strategy_family": "momentum",
                        "zone_status": "dead",
                    }
                ]
            ),
        )
    )
    suppressed = payload["suppressed_zones"]
    assert len(suppressed) == 1
    assert suppressed[0]["asset"] == "crypto"
    assert suppressed[0]["time_since_last_attempt_days"] == 2
    assert "dead_zone_active_within_decay_window" in suppressed[0]["reason_codes"]


def test_r4_decay_dead_zone_after_threshold_yields_low_revisit() -> None:
    """Dead zone older than DEAD_ZONE_DECAY_DAYS → LOW revisit proposal."""
    last_seen = (_AS_OF - timedelta(days=DEAD_ZONE_DECAY_DAYS + 5)).isoformat()
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            ledger=_ledger(
                [
                    {
                        "preset_name": "p1",
                        "strategy_family": "momentum",
                        "hypothesis_id": "h",
                        "campaign_count": 5,
                        "rejection_count": 5,
                        "technical_failure_count": 0,
                        "promotion_candidate_count": 0,
                        "paper_ready_count": 0,
                        "exploratory_pass_count": 0,
                        "degenerate_count": 0,
                        "last_outcome": "research_rejection",
                        "last_seen_at_utc": last_seen,
                    }
                ]
            ),
            dead=_zones(
                [
                    {
                        "asset": "crypto",
                        "strategy_family": "momentum",
                        "zone_status": "dead",
                    }
                ]
            ),
        )
    )
    proposals = payload["proposed_campaigns"]
    revisits = [
        p for p in proposals if p["proposal_type"] == PROPOSAL_TYPE_DEAD_ZONE_REVISIT
    ]
    assert len(revisits) == 1
    assert revisits[0]["priority_tier"] == "LOW"
    assert "dead_zone_decay_passed" in revisits[0]["reason_trace"]
    assert payload["suppressed_zones"] == []


# ── R5: weak zone yields adjacent ──────────────────────────────────────


def test_r5_weak_zone_yields_medium_adjacent_preset() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "weak",
                    }
                ]
            )
        )
    )
    proposals = payload["proposed_campaigns"]
    assert len(proposals) == 1
    assert proposals[0]["priority_tier"] == "MEDIUM"
    assert proposals[0]["proposal_type"] == "adjacent_preset_campaign"


# ── R6 + R6-IG: unknown / high-IG expansion ────────────────────────────


def test_r6_unknown_zone_yields_low_exploration() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            )
        )
    )
    proposals = payload["proposed_campaigns"]
    assert len(proposals) == 1
    assert proposals[0]["priority_tier"] == "LOW"
    assert proposals[0]["proposal_type"] == PROPOSAL_TYPE_EXPLORATION


def test_r6_ig_high_alive_zone_with_stale_attempt_yields_expansion() -> None:
    last_seen = (_AS_OF - timedelta(days=10)).isoformat()
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            ledger=_ledger(
                [
                    {
                        "preset_name": "p_alive",
                        "strategy_family": "trend",
                        "campaign_count": 30,
                        "promotion_candidate_count": 1,
                        "paper_ready_count": 0,
                        "rejection_count": 0,
                        "technical_failure_count": 0,
                        "exploratory_pass_count": 1,
                        "degenerate_count": 0,
                        "hypothesis_id": "h",
                        "last_outcome": "completed_with_candidates",
                        "last_seen_at_utc": last_seen,
                    }
                ]
            ),
            ig={"information_gain": {"bucket": "high"}},
            dead=_zones(
                [
                    {
                        "asset": "crypto",
                        "strategy_family": "trend",
                        "zone_status": "alive",
                    }
                ]
            ),
        )
    )
    proposals = payload["proposed_campaigns"]
    expansions = [
        p for p in proposals if p["spawn_reason"] == "high_information_gain_expansion"
    ]
    assert len(expansions) == 1
    assert expansions[0]["priority_tier"] == "MEDIUM"


# ── R7: exploration coverage records shortfalls ────────────────────────


def test_r7_records_scope_shortfalls_when_coverage_low() -> None:
    """Single exploratory_pass → no exploration → shortfalls reported."""
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]))
    )
    summary = payload["summary"]["exploration_coverage"]
    assert summary["pct_target"] == EXPLORATION_RESERVATION_PCT
    assert summary["distinct_families_target"] == EXPLORATION_MIN_DISTINCT_FAMILIES
    assert summary["distinct_assets_target"] == EXPLORATION_MIN_DISTINCT_ASSETS
    shortfalls = summary["shortfall_reason_codes"]
    assert "exploration_reservation_pct_below_target" in shortfalls
    assert "distinct_families_below_target" in shortfalls
    assert "distinct_assets_below_target" in shortfalls


def test_r7_pct_satisfied_when_only_exploration_proposals() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            )
        )
    )
    summary = payload["summary"]["exploration_coverage"]
    assert summary["pct_actual"] == 1.0
    assert (
        "exploration_reservation_pct_below_target"
        not in summary["shortfall_reason_codes"]
    )


# ── R8: viability stop_or_pivot toggles diagnostic_only ────────────────


def test_r8_stop_or_pivot_toggles_diagnostic_only_and_drops_high() -> None:
    via = {
        "verdict": {
            "status": "stop_or_pivot",
            "reason_codes": ["large_window_no_meaningful_no_candidate"],
            "human_summary": "...",
        }
    }
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            screening=_screening([_candidate()]),
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            ),
            via=via,
        )
    )
    assert payload["proposal_mode"] == PROPOSAL_MODE_DIAGNOSTIC
    assert payload["human_review_required"]["active"] is True
    # HIGH (confirmation) and MEDIUM (none here) dropped; only LOW remains.
    tiers = {p["priority_tier"] for p in payload["proposed_campaigns"]}
    assert tiers <= {"LOW"}
    # Cap enforced.
    assert len(payload["proposed_campaigns"]) <= MAX_PROPOSALS_PER_RUN_DIAGNOSTIC


def test_r8_normal_mode_when_viability_promising() -> None:
    via = {
        "verdict": {
            "status": "promising",
            "reason_codes": [],
            "human_summary": "ok",
        }
    }
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]), via=via)
    )
    assert payload["proposal_mode"] == PROPOSAL_MODE_NORMAL
    assert payload["human_review_required"]["active"] is False


# ── R9-cooldown: per-fingerprint cooldown ──────────────────────────────


def test_r9_cooldown_blocks_fingerprint_within_window() -> None:
    cand = _candidate()
    fp = compute_proposal_fingerprint(
        hypothesis_id=cand["hypothesis_id"],
        preset_name=cand["preset_name"],
        parameter_grid_signature=cand["sampling"]["sampled_parameter_digest"],
        timeframe=cand["interval"],
        asset=cand["asset"],
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([cand]), cooldown={fp})
    )
    assert payload["proposed_campaigns"] == []
    assert payload["summary"]["fingerprint_cooldown_blocks"] == 1


# ── R9-active: registry duplicate blocked ──────────────────────────────


def test_r9_active_registry_match_blocks_duplicate(tmp_path: Path) -> None:
    cand = _candidate()
    registry = {
        "campaigns": {
            "c1": {
                "preset_name": cand["preset_name"],
                "hypothesis_id": cand["hypothesis_id"],
                "asset_class": cand["asset"],
                "timeframe": cand["interval"],
                "parameter_grid_signature": cand["sampling"][
                    "sampled_parameter_digest"
                ],
                "spawned_at_utc": _AS_OF.isoformat(),
            }
        }
    }
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([cand]), registry=registry)
    )
    assert payload["proposed_campaigns"] == []


# ── R10: deterministic sort + cap ──────────────────────────────────────


def test_r10_sort_orders_high_before_low_then_fingerprint_asc() -> None:
    cands = [_candidate(preset=f"preset_z_{i}", hypothesis=f"h{i}") for i in range(3)]
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            screening=_screening(cands),
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            ),
        )
    )
    tiers = [p["priority_tier"] for p in payload["proposed_campaigns"]]
    # All HIGH first, then LOW.
    assert tiers == sorted(
        tiers, key=lambda t: PRIORITY_TIER_ORDER.index(t)
    )


def test_r10_cap_normal_mode() -> None:
    cands = [
        _candidate(preset=f"preset_{i:02d}", hypothesis=f"h{i:02d}")
        for i in range(MAX_PROPOSALS_PER_RUN_NORMAL + 5)
    ]
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening(cands))
    )
    assert len(payload["proposed_campaigns"]) == MAX_PROPOSALS_PER_RUN_NORMAL


# ── Six hardenings (cross-cutting) ─────────────────────────────────────


def test_h1_proposal_fingerprint_includes_six_fields() -> None:
    fp_a = compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g1",
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )
    fp_b = compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g2",  # different
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )
    fp_c = compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g1",
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_PARAM_RETRY,  # different proposal type
    )
    assert fp_a != fp_b
    assert fp_a != fp_c
    assert fp_a == compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g1",
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )


def test_h2_history_persistence_drives_cooldown(tmp_path: Path) -> None:
    history = tmp_path / "spawn_proposal_history.jsonl"
    fp = compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g",
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "fingerprint": fp,
        "generated_at_utc": (_AS_OF - timedelta(days=2)).isoformat(),
        "run_id": "old",
    }
    history.write_text(json.dumps(record) + "\n", encoding="utf-8")
    loaded = load_recent_proposal_fingerprints(
        history_path=history, now_utc=_AS_OF
    )
    assert fp in loaded


def test_h2_old_fingerprint_outside_cooldown_window_not_loaded(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.jsonl"
    fp = compute_proposal_fingerprint(
        hypothesis_id="h",
        preset_name="p",
        parameter_grid_signature="g",
        timeframe="1h",
        asset="crypto",
        proposal_type=PROPOSAL_TYPE_CONFIRMATION,
    )
    record = {
        "fingerprint": fp,
        "generated_at_utc": (
            _AS_OF - timedelta(days=FINGERPRINT_COOLDOWN_DAYS + 5)
        ).isoformat(),
        "run_id": "old",
    }
    history.write_text(json.dumps(record) + "\n", encoding="utf-8")
    loaded = load_recent_proposal_fingerprints(
        history_path=history, now_utc=_AS_OF
    )
    assert fp not in loaded


def test_h3_scope_spread_targets_visible_in_summary() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]))
    )
    cov = payload["summary"]["exploration_coverage"]
    for key in (
        "pct_target",
        "pct_actual",
        "distinct_families_target",
        "distinct_families_actual",
        "distinct_assets_target",
        "distinct_assets_actual",
        "distinct_timeframes_target",
        "distinct_timeframes_actual",
        "shortfall_reason_codes",
    ):
        assert key in cov


def test_h4_dead_zone_decay_documented_in_constants() -> None:
    assert DEAD_ZONE_DECAY_DAYS > 0
    assert isinstance(DEAD_ZONE_DECAY_DAYS, int)


def test_h5_diagnostic_mode_caps_at_three() -> None:
    via = {"verdict": {"status": "stop_or_pivot", "reason_codes": []}}
    cands = [
        _candidate(preset=f"p{i:02d}", hypothesis=f"h{i:02d}")
        for i in range(20)
    ]
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            screening=_screening(cands),
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            ),
            via=via,
        )
    )
    assert len(payload["proposed_campaigns"]) <= MAX_PROPOSALS_PER_RUN_DIAGNOSTIC
    assert payload["proposal_mode"] == PROPOSAL_MODE_DIAGNOSTIC


def test_h6_priority_tier_enum_no_integer_priority_field() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(screening=_screening([_candidate()]))
    )
    p = payload["proposed_campaigns"][0]
    assert p["priority_tier"] in PRIORITY_TIER_ORDER
    assert "priority_delta" not in p
    assert "priority" not in p


def test_h6_reason_trace_present_on_every_proposal() -> None:
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            screening=_screening([_candidate()]),
            dead=_zones(
                [
                    {
                        "asset": "stocks",
                        "strategy_family": "mean_reversion",
                        "zone_status": "insufficient_data",
                    }
                ]
            ),
        )
    )
    for p in payload["proposed_campaigns"]:
        assert isinstance(p["reason_trace"], list)
        assert p["reason_trace"], "reason_trace must be non-empty"
        # priority_tier_assigned step is the last trace entry.
        assert any("priority_tier_assigned" in t for t in p["reason_trace"])


def test_h6_reason_trace_present_on_suppressed_zones() -> None:
    last_seen = (_AS_OF - timedelta(days=2)).isoformat()
    payload = build_spawn_proposals_payload(
        **_basic_kwargs(
            ledger=_ledger(
                [
                    {
                        "preset_name": "p",
                        "strategy_family": "momentum",
                        "hypothesis_id": "h",
                        "campaign_count": 5,
                        "rejection_count": 5,
                        "last_seen_at_utc": last_seen,
                    }
                ]
            ),
            dead=_zones(
                [
                    {
                        "asset": "crypto",
                        "strategy_family": "momentum",
                        "zone_status": "dead",
                    }
                ]
            ),
        )
    )
    for s in payload["suppressed_zones"]:
        assert isinstance(s["reason_trace"], list)
        assert s["reason_trace"], "suppressed zone trace must be non-empty"


# ── Top-level invariants ───────────────────────────────────────────────


def test_top_level_enforcement_state_is_advisory_only() -> None:
    payload = build_spawn_proposals_payload(**_basic_kwargs())
    assert payload["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
    assert payload["mode"] == MODE_SHADOW
    assert payload["schema_version"] == SPAWN_PROPOSALS_SCHEMA_VERSION


def test_byte_identical_payload_for_repeated_build() -> None:
    inputs = _basic_kwargs(screening=_screening([_candidate()]))
    p1 = build_spawn_proposals_payload(**inputs)
    p2 = build_spawn_proposals_payload(**inputs)
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_io_wrapper_writes_artifact_and_appends_history(tmp_path: Path) -> None:
    out = tmp_path / "research" / "campaigns" / "evidence" / "spawn.json"
    history = tmp_path / "research" / "campaigns" / "evidence" / "history.jsonl"
    payload = write_spawn_proposals_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence=_screening([_candidate()]),
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones=None,
        viability=None,
        campaign_registry=None,
        output_path=out,
        history_path=history,
    )
    assert out.exists()
    assert history.exists()
    history_lines = [
        json.loads(line)
        for line in history.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(history_lines) == len(payload["proposed_campaigns"])
    # Second run with same inputs should be cooldown-blocked.
    payload_2 = write_spawn_proposals_artifact(
        run_id="run_b",
        as_of_utc=_AS_OF + timedelta(hours=1),
        git_revision="abc",
        screening_evidence=_screening([_candidate()]),
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones=None,
        viability=None,
        campaign_registry=None,
        output_path=out,
        history_path=history,
    )
    assert payload_2["summary"]["fingerprint_cooldown_blocks"] >= 1


def test_append_only_history_helper(tmp_path: Path) -> None:
    """append_proposal_history writes one JSONL line per proposal."""
    from research.funnel_spawn_proposer import ProposedCampaign

    history = tmp_path / "h.jsonl"
    proposals = [
        ProposedCampaign(
            preset_name="p",
            hypothesis_id="h",
            asset="crypto",
            timeframe="1h",
            strategy_family="trend",
            parameter_grid_signature="g",
            proposal_type=PROPOSAL_TYPE_CONFIRMATION,
            spawn_reason="x",
            priority_tier="HIGH",
            lineage={},
            rationale_codes=[],
            reason_trace=["x"],
            expected_information_gain_bucket=None,
            source_signal="screening_evidence",
            proposal_fingerprint="sha1:test",
        )
    ]
    written = append_proposal_history(
        history_path=history,
        proposals=proposals,
        run_id="r",
        generated_at_utc=_AS_OF,
    )
    assert written == 1
    assert history.read_text(encoding="utf-8").strip().count("\n") == 0
    record = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert record["fingerprint"] == "sha1:test"
    assert record["run_id"] == "r"
