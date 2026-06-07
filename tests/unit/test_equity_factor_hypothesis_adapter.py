from __future__ import annotations

import json

from research.hypothesis_discovery import equity_factor_hypothesis_adapter as adapter


def _base_recipe_row() -> dict[str, object]:
    return {
        "recipe_id": "test_recipe",
        "target_universe_ids": ["test_universe"],
        "required_factor_ids": ["roic"],
        "optional_factor_ids": [],
        "feasibility_status": "FEASIBLE",
        "blocked_reason_codes": [],
    }


def _fake_catalog() -> dict[str, object]:
    return {
        "instruments": [
            {
                "canonical_id": "eq_test",
                "symbol": "TEST",
                "universe_ids": ["test_universe"],
            }
        ]
    }


def _fake_quality(*, ambiguous: bool = False, fail: bool = False) -> dict[str, object]:
    return {
        "rows": [
            {
                "canonical_id": "eq_test",
                "ambiguous_mapping_warning": ambiguous,
                "eligible_for_hypothesis_seed": not ambiguous and not fail,
                "universe_readiness_status": "FAIL" if fail else "WARN" if ambiguous else "OK",
            }
        ]
    }


def _fake_readiness(*, ready: bool = True) -> dict[str, object]:
    return {
        "factor_rows": [{"factor_id": "roic"}],
        "recipe_rows": [
            {
                "recipe_id": "test_recipe",
                "readiness_status": "READY" if ready else "NOT_READY",
                "readiness_block_reasons": [] if ready else ["MISSING_SOURCE_MANIFEST"],
            }
        ],
    }


def test_build_equity_factor_hypothesis_seeds_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "build_equity_factor_recipe_catalog",
        lambda: {"rows": [_base_recipe_row()]},
    )
    monkeypatch.setattr(adapter, "build_equity_universe_catalog", _fake_catalog)
    monkeypatch.setattr(adapter, "build_equity_universe_quality", lambda: _fake_quality())
    monkeypatch.setattr(adapter, "build_fundamental_readiness", lambda: _fake_readiness())

    first = adapter.build_equity_factor_hypothesis_seeds()
    second = adapter.build_equity_factor_hypothesis_seeds()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    row = first["rows"][0]
    assert row["feasibility_status"] == "FEASIBLE"
    assert row["allowed_use"] == ["research_prior"]


def test_build_equity_factor_hypothesis_seeds_blocks_missing_data_readiness(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "build_equity_factor_recipe_catalog",
        lambda: {"rows": [_base_recipe_row()]},
    )
    monkeypatch.setattr(adapter, "build_equity_universe_catalog", _fake_catalog)
    monkeypatch.setattr(adapter, "build_equity_universe_quality", lambda: _fake_quality())
    monkeypatch.setattr(adapter, "build_fundamental_readiness", lambda: _fake_readiness(ready=False))

    row = adapter.build_equity_factor_hypothesis_seeds()["rows"][0]

    assert row["feasibility_status"] == "BLOCKED"
    assert "BLOCKED_DATA_READINESS_MISSING" in row["blocked_reason_codes"]
    assert "MISSING_SOURCE_MANIFEST" in row["blocked_reason_codes"]
    assert row["expected_research_value_score"] <= 0.49


def test_build_equity_factor_hypothesis_seeds_blocks_missing_factor_or_universe(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "build_equity_factor_recipe_catalog",
        lambda: {
            "rows": [
                {
                    **_base_recipe_row(),
                    "target_universe_ids": ["missing_universe"],
                    "required_factor_ids": ["missing_factor"],
                }
            ]
        },
    )
    monkeypatch.setattr(adapter, "build_equity_universe_catalog", _fake_catalog)
    monkeypatch.setattr(adapter, "build_equity_universe_quality", lambda: _fake_quality())
    monkeypatch.setattr(adapter, "build_fundamental_readiness", lambda: {"factor_rows": [], "recipe_rows": []})

    row = adapter.build_equity_factor_hypothesis_seeds()["rows"][0]

    assert "BLOCKED_MISSING_UNIVERSE" in row["blocked_reason_codes"]
    assert "BLOCKED_MISSING_FACTOR" in row["blocked_reason_codes"]


def test_build_equity_factor_hypothesis_seeds_blocks_identity_ambiguity(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "build_equity_factor_recipe_catalog",
        lambda: {"rows": [_base_recipe_row()]},
    )
    monkeypatch.setattr(adapter, "build_equity_universe_catalog", _fake_catalog)
    monkeypatch.setattr(adapter, "build_equity_universe_quality", lambda: _fake_quality(ambiguous=True))
    monkeypatch.setattr(adapter, "build_fundamental_readiness", lambda: _fake_readiness())

    row = adapter.build_equity_factor_hypothesis_seeds()["rows"][0]

    assert row["feasibility_status"] == "BLOCKED"
    assert "BLOCKED_IDENTITY_AMBIGUITY" in row["blocked_reason_codes"]
    assert row["required_next_action"] == "resolve_identity_ambiguity"


def test_build_equity_factor_hypothesis_seeds_blocks_universe_quality_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "build_equity_factor_recipe_catalog",
        lambda: {"rows": [_base_recipe_row()]},
    )
    monkeypatch.setattr(adapter, "build_equity_universe_catalog", _fake_catalog)
    monkeypatch.setattr(adapter, "build_equity_universe_quality", lambda: _fake_quality(fail=True))
    monkeypatch.setattr(adapter, "build_fundamental_readiness", lambda: _fake_readiness())

    row = adapter.build_equity_factor_hypothesis_seeds()["rows"][0]

    assert row["feasibility_status"] == "BLOCKED"
    assert "BLOCKED_UNIVERSE_QUALITY_FAIL" in row["blocked_reason_codes"]
    assert "strategy_signal" in row["forbidden_use"]
