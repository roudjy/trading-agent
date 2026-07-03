from __future__ import annotations

from packages.qre_research.alpha_discovery.contracts import ObservationSnapshot, content_id
from packages.qre_research.alpha_discovery.providers import MultiProviderHypothesisProvider


def _snapshot() -> ObservationSnapshot:
    payload = {
        "market_diagnostics": {"recent_trend": 1.0, "recent_volatility": 0.4},
        "regime_diagnostics": {"regime_signature": ["trend", "calm"]},
        "cross_asset_diagnostics": {"status": "NOT_AVAILABLE"},
        "data_coverage": {"catalog_content_identity": "catalog_fixture", "coverage_rows": 1, "ready_rows": 1, "research_ready": False},
        "source_quality": {"summary": {"status": "blocked"}},
        "identity_readiness": "ready",
        "current_queue": [],
        "recent_terminal_outcomes": [],
        "active_contradictions": [],
        "resolved_contradictions": [],
        "mechanism_coverage": {"opportunity_count": 1},
        "behavior_family_coverage": {"resolved_strategy_count": 1},
        "primitive_inventory": {"available_primitives": ["compression_ratio", "cross_sectional_rank"]},
        "executor_inventory": {"canonical_engine": "canonical"},
        "relevant_research_memory": {"summary": {}, "matches": []},
    }
    return ObservationSnapshot(
        observation_snapshot_id="qos_fixture",
        schema_version="1.1",
        policy_version="test",
        content_identity=content_id("qos", payload),
        **payload,
    )


def test_provider_ensemble_is_deterministic_and_budgeted() -> None:
    provider = MultiProviderHypothesisProvider()
    first = provider.propose(_snapshot(), {"lesson": {}}, budget=6)
    second = provider.propose(_snapshot(), {"lesson": {}}, budget=6)

    assert [item.hypothesis_id for item in first] == [item.hypothesis_id for item in second]
    assert len(first) <= 4
    assert {item.provider_id for item in first}.issubset({"anomaly", "contradiction", "coverage"})

