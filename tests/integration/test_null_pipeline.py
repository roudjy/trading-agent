"""Minimal null-pipeline integration coverage.

Pins ADR-019's falsifiability requirement for the v3.15.19 minimal
Hypothesis Discovery slice: deterministic surrogate diagnostics and
their shuffled-control counterpart must not produce distinguishable
Discovery scores.
"""

from __future__ import annotations

from research.hypothesis_discovery import campaign_seed_proposer as csp
from research.hypothesis_discovery import opportunity_scoring as oscore


def _surrogate_diagnostics() -> dict[str, float | int]:
    return {
        "null_model_beat_margin": 0.25,
        "tail_fragility_score": 0.50,
        "entropy_conflict_score": 0.50,
        "evidence_quorum_count": 1,
        "multiplicity_budget_remaining": 5,
    }


def test_hypothesis_discovery_scores_surrogate_and_shuffle_equally() -> None:
    surrogate = oscore.normalise_inputs(
        _surrogate_diagnostics(),
        preset_feasible=True,
    )
    shuffled_control = dict(reversed(list(surrogate.items())))

    assert oscore.opportunity_probability_score(
        surrogate
    ) == oscore.opportunity_probability_score(shuffled_control)


def test_hypothesis_discovery_enabled_does_not_execute_on_surrogate(
    tmp_path,
) -> None:
    snap = csp.collect_snapshot(
        {
            "trend_pullback_v1": _surrogate_diagnostics(),
            "volatility_compression_breakout_v0": _surrogate_diagnostics(),
        },
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
    )

    assert snap["safe_to_execute"] is False
    assert snap["proposal_only"] is True
    assert snap["score_semantics"] == "expected_research_value_not_probability"
    assert all(
        row["score"]["opportunity_probability_score"]
        == snap["items"][0]["score"]["opportunity_probability_score"]
        for row in snap["items"]
    )
