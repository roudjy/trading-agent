from __future__ import annotations

from pathlib import Path

from packages.qre_research.alpha_discovery.contracts import (
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    CoverageDecision,
    MechanisticHypothesis,
    content_id,
)
from packages.qre_research.alpha_discovery.experiment_compiler import CanonicalExperimentPlanner
from packages.qre_research.alpha_discovery.runner import (
    _run_empirical_campaign_via_canonical_orchestrator,
)


def test_empirical_runner_uses_research_run_research(monkeypatch, tmp_path: Path) -> None:
    calls: list[object] = []

    class _FakeRunner:
        def run_research(self, *, preset_override):
            calls.append(preset_override)

    def _fake_import(name: str):
        if name == "research.presets":
            from research import presets as real_presets

            return real_presets
        if name == "research.run_research":
            return _FakeRunner()
        raise AssertionError(name)

    monkeypatch.setattr("packages.qre_research.alpha_discovery.runner.importlib.import_module", _fake_import)

    hypothesis = MechanisticHypothesis(
        hypothesis_id="qah_fixture",
        schema_version="1.1",
        provider_id="fixture",
        generation_policy_version="fixture",
        parent_hypothesis_id=None,
        mechanism_family="volatility_breakout",
        behavior_family="compression_release",
        causal_mechanism_statement="fixture",
        predicted_observable_effect="fixture observable",
        expected_direction="long_only",
        universe_intent="single_asset_liquid_cache_universe",
        timeframe_intent="1d",
        regime_scope="trend",
        required_features=("compression_ratio",),
        required_controls=("regime_filter",),
        null_hypothesis="fixture null",
        falsification_conditions=("fixture falsification",),
        confounders=("cost drag",),
        minimum_activity_expectation="fixture",
        cost_sensitivity_expectation="fixture",
        support_observation_refs=("qos_fixture",),
        contradicting_observation_refs=(),
        related_hypotheses=(),
        related_campaigns=(),
        novelty_dimensions=("new mechanism",),
        parameter_schema=(),
        parameter_count=0,
        content_identity=content_id("qah", "fixture"),
        stable_fingerprint="fixture",
    )
    experiment = CanonicalExperimentPlanner().plan(hypothesis, requested_execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING)
    data_plan = CoverageDecision(
        decision="CACHE_READY",
        coverage_decision="CACHE_READY",
        requested_execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        admissible_execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        tier_downgrade_reasons=(),
        reason_codes=("ready_cache_row_selected",),
        selected_data={"selected_row": {"instrument": "AAPL", "timeframe": "1d"}},
        approved_fetch=False,
        dataset_inventory=(),
        content_identity=content_id("qdc", "fixture"),
    )

    result = _run_empirical_campaign_via_canonical_orchestrator(tmp_path, hypothesis=hypothesis, experiment=experiment, data_plan=data_plan)

    assert calls, "expected run_research to be called"
    assert result["canonical_orchestrator"] == "research.run_research.run_research"
