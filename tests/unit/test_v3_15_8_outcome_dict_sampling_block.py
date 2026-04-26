"""v3.15.8 — every screening outcome dict carries a ``sampling`` block.

Pinned paths (REV 3 §5.7):

  - success aggregate (rejected or promoted)
  - per-sample exception → final_status=errored
  - candidate budget timeout → final_status=timed_out
  - no-engine fast path → final_status=passed (skipped engine)

The ``sampling`` block always has the same shape (the
_UNAVAILABLE_SAMPLING_METADATA fallback when callers do not
supply explicit metadata).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from research.candidate_pipeline import (
    COVERAGE_WARNING_GRID_UNAVAILABLE,
    SAMPLING_POLICY_GRID_UNAVAILABLE,
    sampling_plan_for_param_grid,
)
from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_PASSED,
    FINAL_STATUS_TIMED_OUT,
    _UNAVAILABLE_SAMPLING_METADATA,
    execute_screening_candidate,
    execute_screening_candidate_samples,
)


_SAMPLING_KEYS = {
    "grid_size", "sampled_count", "coverage_pct",
    "sampling_policy", "sampled_parameter_digest", "coverage_warning",
}


class _FakeClock:
    def __init__(self, when: datetime) -> None:
        self._when = when
        self._mono = 0.0

    def now(self) -> datetime:
        return self._when

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._mono += seconds


def test_no_engine_fast_path_carries_sampling_block() -> None:
    outcome = execute_screening_candidate_samples(
        candidate={"asset": "BTC-USD"},
        engine=SimpleNamespace(),  # no .run attribute
        budget_seconds=10,
        strategy_samples=iter([]),
        samples_total=0,
    )
    assert outcome["final_status"] == FINAL_STATUS_PASSED
    assert "sampling" in outcome
    assert set(outcome["sampling"].keys()) == _SAMPLING_KEYS
    assert outcome["sampling"]["sampling_policy"] == SAMPLING_POLICY_GRID_UNAVAILABLE
    assert outcome["sampling"]["coverage_warning"] == COVERAGE_WARNING_GRID_UNAVAILABLE


def test_per_sample_error_path_carries_sampling_block() -> None:
    class BrokenEngine:
        def run(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    clock = _FakeClock(datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC))
    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"a": [1]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=BrokenEngine(),
        budget_seconds=30,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )
    assert outcome["final_status"] == FINAL_STATUS_ERRORED
    assert "sampling" in outcome
    assert set(outcome["sampling"].keys()) == _SAMPLING_KEYS
    # the wrapper computes a real plan from the strategy params
    assert outcome["sampling"]["grid_size"] == 1


def test_timeout_path_carries_sampling_block() -> None:
    clock = _FakeClock(datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC))

    class SlowEngine:
        def __init__(self) -> None:
            self.last_evaluation_report = None

        def run(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            clock.advance(2)
            self.last_evaluation_report = {
                "evaluation_samples": {"daily_returns": [0.01, -0.01]},
            }
            return {"totaal_trades": 12, "goedgekeurd": True}

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"a": [1, 2, 3]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=SlowEngine(),
        budget_seconds=1,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )
    assert outcome["final_status"] == FINAL_STATUS_TIMED_OUT
    assert "sampling" in outcome
    assert set(outcome["sampling"].keys()) == _SAMPLING_KEYS
    assert outcome["sampling"]["grid_size"] == 3


def test_success_path_carries_real_plan_metadata_when_supplied() -> None:
    plan = sampling_plan_for_param_grid({"a": [1, 2]})

    class ImmediateEngine:
        def __init__(self) -> None:
            self.last_evaluation_report = None

        def run(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            self.last_evaluation_report = {
                "evaluation_samples": {"daily_returns": [0.01, -0.01]},
            }
            return {
                "totaal_trades": 12,
                "goedgekeurd": True,
                "expectancy": 0.001,
                "profit_factor": 1.5,
                "win_rate": 0.6,
                "max_drawdown": 0.1,
            }

    outcome = execute_screening_candidate_samples(
        candidate={"asset": "BTC-USD"},
        engine=ImmediateEngine(),
        budget_seconds=30,
        strategy_samples=((p, SimpleNamespace(params=p)) for p in plan.samples),
        samples_total=plan.sampled_count,
        sampling_metadata=plan.metadata(),
    )
    assert outcome["sampling"] == plan.metadata()
    assert outcome["sampling"]["coverage_pct"] == 1.0
    assert outcome["sampling"]["grid_size"] == 2


def test_unavailable_sampling_metadata_constant_shape() -> None:
    """The fallback constant must have exactly the keys that
    consumers (screening_evidence v3.15.9 + funnel_policy v3.15.10)
    rely on.
    """
    assert set(_UNAVAILABLE_SAMPLING_METADATA.keys()) == _SAMPLING_KEYS
