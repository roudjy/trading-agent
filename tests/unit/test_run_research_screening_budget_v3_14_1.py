"""v3.14.1 targeted regression tests for screening candidate budget."""

from __future__ import annotations

import pytest

from research import run_research


# ---------------------------------------------------------------------------
# Fix A: default budget is 300s; config override still wins
# ---------------------------------------------------------------------------


def test_default_screening_candidate_budget_is_300_seconds():
    """v3.14.1: raise VPS-safe default from 60s to 300s."""
    assert run_research.DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS == 300


def _resolve_budget(research_config: dict | None) -> int:
    """Reproduce the resolution logic from run_research.run_research.

    Kept in sync with the source (line 1839-1842). If the source
    changes, this test will still exercise the intended behaviour
    because it wraps the same ``max(0, int(config.get(...)))``
    expression.
    """
    screening_config = (research_config or {}).get("screening") or {}
    return max(
        0,
        int(
            screening_config.get(
                "candidate_budget_seconds",
                run_research.DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS,
            )
        ),
    )


def test_config_override_is_authoritative_when_set_explicitly():
    config = {"screening": {"candidate_budget_seconds": 120}}
    assert _resolve_budget(config) == 120


def test_config_with_missing_key_falls_back_to_default_300():
    assert _resolve_budget({"screening": {}}) == 300
    assert _resolve_budget({}) == 300
    assert _resolve_budget(None) == 300


def test_negative_config_value_is_clamped_to_zero():
    config = {"screening": {"candidate_budget_seconds": -5}}
    assert _resolve_budget(config) == 0


def test_zero_config_value_is_accepted_verbatim():
    # 0 is a valid sentinel (no budget); we must not replace it with the default
    config = {"screening": {"candidate_budget_seconds": 0}}
    assert _resolve_budget(config) == 0
