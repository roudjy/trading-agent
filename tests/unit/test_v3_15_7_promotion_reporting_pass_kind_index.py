"""v3.15.7 — promotion_reporting threading + frozen schema guard.

Verifies that ``build_candidate_registry_payload``:

- Default behavior (no ``screening_pass_kinds``) is byte-identical
  to pre-v3.15.7.
- Accepts ``screening_pass_kinds={...}``; an exploratory
  strategy_id is downgraded to ``status="needs_investigation"``.
- The candidate registry row schema is bytewise unchanged — no
  ``pass_kind`` / ``diagnostic_metrics`` / ``screening_criteria_set``
  keys leak into the row dict.
- Top-level keys are byte-identical to pre-v3.15.7.
"""

from __future__ import annotations

from typing import Any

from research.promotion import (
    STATUS_CANDIDATE,
    STATUS_NEEDS_INVESTIGATION,
    build_strategy_id,
)
from research.promotion_reporting import build_candidate_registry_payload


def _good_oos() -> dict[str, Any]:
    return {
        "psr": 0.95,
        "sharpe": 0.8,
        "max_drawdown": 0.15,
        "totaal_trades": 30,
        "goedgekeurd": True,
    }


def _good_defensibility() -> dict:
    return {
        "psr": 0.95,
        "dsr_canonical": 0.5,
        "noise_warning": {"is_likely_noise": False, "reason": "clear"},
        "bootstrap_ci": {"sharpe": {"low": 0.1, "high": 1.2}},
    }


def _research_latest() -> dict:
    return {
        "generated_at_utc": "2026-04-26T00:00:00+00:00",
        "results": [
            {
                "strategy_name": "trend_fast",
                "asset": "BTC-USD",
                "interval": "1d",
                "params_json": '{"fast": 20, "slow": 50}',
                "success": True,
            }
        ],
    }


def _walk_forward() -> dict:
    return {
        "strategies": [
            {
                "strategy_name": "trend_fast",
                "asset": "BTC-USD",
                "interval": "1d",
                "oos_summary": _good_oos(),
                "leakage_checks_ok": True,
            }
        ]
    }


def _defensibility() -> dict:
    return {
        "families": [
            {
                "family": "trend",
                "interval": "1d",
                "members": [
                    {
                        "strategy_name": "trend_fast",
                        "asset": "BTC-USD",
                        "selected_params": {"fast": 20, "slow": 50},
                        **_good_defensibility(),
                    }
                ],
            }
        ]
    }


def _strategy_id() -> str:
    return build_strategy_id("trend_fast", "BTC-USD", "1d", {"fast": 20, "slow": 50})


# ---- backward compatibility ------------------------------------------------


def test_default_call_byte_identical_to_pre_v3_15_7():
    payload_legacy = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
    )
    payload_explicit_none = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
        screening_pass_kinds=None,
    )
    payload_empty = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
        screening_pass_kinds={},
    )
    assert payload_legacy == payload_explicit_none == payload_empty


# ---- exploratory pass downgrade -------------------------------------------


def test_exploratory_pass_kind_downgrades_to_needs_investigation():
    payload = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
        screening_pass_kinds={_strategy_id(): "exploratory"},
    )
    candidates = payload["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["status"] == STATUS_NEEDS_INVESTIGATION
    assert candidates[0]["reasoning"]["escalated"] == [
        "exploratory_pass_requires_promotion_grade_confirmation"
    ]


def test_legacy_pass_kinds_byte_identical_to_no_index():
    """``standard`` and ``promotion_grade`` and None all behave like
    the no-index call.
    """
    baseline = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
    )
    for pass_kind in ("standard", "promotion_grade", None):
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(),
            walk_forward=_walk_forward(),
            statistical_defensibility=_defensibility(),
            promotion_config=None,
            git_revision="abc",
            screening_pass_kinds={_strategy_id(): pass_kind},
        )
        assert payload == baseline


# ---- frozen schema guards --------------------------------------------------


CANDIDATE_ROW_KEYS = frozenset({
    "strategy_id",
    "strategy_name",
    "asset",
    "interval",
    "selected_params",
    "status",
    "reasoning",
})

TOP_LEVEL_KEYS = frozenset({
    "version",
    "generated_at_utc",
    "git_revision",
    "promotion_config",
    "candidates",
    "summary",
})


def test_candidate_row_does_not_carry_v3_15_7_fields():
    payload = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
        screening_pass_kinds={_strategy_id(): "exploratory"},
    )
    for row in payload["candidates"]:
        assert set(row.keys()) == CANDIDATE_ROW_KEYS, (
            f"v3.15.7 schema drift: candidate row has unexpected keys {set(row.keys())}"
        )
        assert "pass_kind" not in row
        assert "screening_criteria_set" not in row
        assert "diagnostic_metrics" not in row


def test_top_level_keys_unchanged():
    payload = build_candidate_registry_payload(
        research_latest=_research_latest(),
        walk_forward=_walk_forward(),
        statistical_defensibility=_defensibility(),
        promotion_config=None,
        git_revision="abc",
        screening_pass_kinds={_strategy_id(): "exploratory"},
    )
    assert set(payload.keys()) == TOP_LEVEL_KEYS
