"""v3.15.12 — funnel spawn proposer integration test.

Exercises the lifecycle write order against an isolated workspace,
plus the cross-version regression that campaign_policy.decide()
remains unchanged. Same shape as the v3.15.11 integration test.
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from research import campaign_policy
from research.funnel_spawn_proposer import (
    ENFORCEMENT_STATE_ADVISORY,
    MODE_SHADOW,
    PROPOSAL_MODE_DIAGNOSTIC,
    PROPOSAL_MODE_NORMAL,
    SPAWN_PROPOSALS_SCHEMA_VERSION,
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
) -> dict[str, Any]:
    return {
        "preset_name": preset,
        "asset": asset,
        "interval": interval,
        "strategy_family": family,
        "hypothesis_id": hypothesis,
        "stage_result": stage_result,
        "pass_kind": pass_kind,
        "near_pass": {
            "is_near_pass": False,
            "distance": None,
            "nearest_failed_criterion": None,
        },
        "sampling": {"sampled_parameter_digest": "abc"},
    }


def _setup_workspace(tmp_path: Path) -> dict[str, Path]:
    base = tmp_path / "research" / "campaigns" / "evidence"
    base.mkdir(parents=True, exist_ok=True)
    return {
        "out": base / "spawn_proposals.json",
        "history": base / "spawn_proposal_history.jsonl",
    }


def test_pipeline_writes_artifact_and_history(tmp_path: Path) -> None:
    paths = _setup_workspace(tmp_path)
    payload = write_spawn_proposals_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence={"candidates": [_candidate()]},
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones=None,
        viability=None,
        campaign_registry=None,
        output_path=paths["out"],
        history_path=paths["history"],
    )
    assert paths["out"].exists()
    assert paths["history"].exists()
    assert payload["schema_version"] == SPAWN_PROPOSALS_SCHEMA_VERSION
    assert payload["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
    assert payload["mode"] == MODE_SHADOW
    assert payload["proposal_mode"] == PROPOSAL_MODE_NORMAL


def test_pipeline_diagnostic_mode_under_stop_or_pivot(tmp_path: Path) -> None:
    paths = _setup_workspace(tmp_path)
    payload = write_spawn_proposals_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence={"candidates": [_candidate()]},
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones={
            "zones": [
                {
                    "asset": "stocks",
                    "strategy_family": "mean_reversion",
                    "zone_status": "insufficient_data",
                }
            ]
        },
        viability={
            "verdict": {
                "status": "stop_or_pivot",
                "reason_codes": ["large_window_no_meaningful_no_candidate"],
                "human_summary": "...",
            }
        },
        campaign_registry=None,
        output_path=paths["out"],
        history_path=paths["history"],
    )
    assert payload["proposal_mode"] == PROPOSAL_MODE_DIAGNOSTIC
    assert payload["human_review_required"]["active"] is True
    tiers = {p["priority_tier"] for p in payload["proposed_campaigns"]}
    assert tiers <= {"LOW"}


def test_pipeline_idempotent_via_history_cooldown(tmp_path: Path) -> None:
    paths = _setup_workspace(tmp_path)
    cand = _candidate()
    write_spawn_proposals_artifact(
        run_id="r1",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence={"candidates": [cand]},
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones=None,
        viability=None,
        campaign_registry=None,
        output_path=paths["out"],
        history_path=paths["history"],
    )
    payload_2 = write_spawn_proposals_artifact(
        run_id="r2",
        as_of_utc=_AS_OF,
        git_revision="abc",
        screening_evidence={"candidates": [cand]},
        evidence_ledger=None,
        information_gain=None,
        stop_conditions=None,
        dead_zones=None,
        viability=None,
        campaign_registry=None,
        output_path=paths["out"],
        history_path=paths["history"],
    )
    # First run wrote 1 history line; second run cooldown-blocks.
    assert payload_2["summary"]["fingerprint_cooldown_blocks"] == 1
    assert len(payload_2["proposed_campaigns"]) == 0


def test_lifecycle_wiring_present_in_run_research() -> None:
    """Regression: run_research.py imports the proposer entry point."""
    import research.run_research as rr

    assert hasattr(rr, "write_spawn_proposals_artifact")


def test_campaign_policy_decide_signature_still_pinned_after_v3_15_12() -> None:
    """Re-pin the v3.15.11 invariant: this release does not consume
    advisory output in policy. If a future release wires the proposer
    output into policy.decide(), this test must be updated alongside it.
    """
    sig = inspect.signature(campaign_policy.decide)
    forbidden = {
        "spawn_proposals",
        "proposed_campaigns",
        "advisory_decisions",
        "stop_conditions",
    }
    assert forbidden.intersection(sig.parameters.keys()) == set()
