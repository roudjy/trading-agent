"""v3.15.8 — the subprocess payload constructed by
``_build_child_payload`` must carry the parent-computed sampling
metadata so the screening outcome dict produced inside the
subprocess matches the in-process screening_runtime path.

We don't actually spawn a subprocess here — we verify the
payload dict directly so the test is fast and deterministic.
"""

from __future__ import annotations

from agent.backtesting.engine import BacktestEngine
from research.candidate_pipeline import sampling_plan_for_param_grid
from research.screening_process import _build_child_payload


def _trivial_factory(**params):  # type: ignore[no-untyped-def]
    return None


def test_payload_contains_sampling_metadata_matching_planner() -> None:
    strategy = {
        "name": "test",
        "factory": _trivial_factory,
        "params": {"a": list(range(8))},
    }
    payload = _build_child_payload(
        strategy=strategy,
        candidate={"candidate_id": "c1", "asset": "BTC-USD", "interval": "1d"},
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=30,
        max_samples=3,
        engine_class=BacktestEngine,
        resume_state=None,
        resume_sidecar_path=None,
        batch_id="batch-1",
        plan_fingerprint="fp",
        screening_phase=None,
    )
    expected = sampling_plan_for_param_grid(
        strategy["params"], max_samples_for_legacy=3
    ).metadata()
    assert payload["sampling_metadata"] == expected
    assert payload["samples_total"] == expected["sampled_count"]


def test_payload_carries_metadata_for_legacy_large_grid() -> None:
    strategy = {
        "name": "test",
        "factory": _trivial_factory,
        "params": {"a": list(range(20))},
    }
    payload = _build_child_payload(
        strategy=strategy,
        candidate={"candidate_id": "c1", "asset": "BTC-USD", "interval": "1d"},
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=30,
        max_samples=3,
        engine_class=BacktestEngine,
        resume_state=None,
        resume_sidecar_path=None,
        batch_id="batch-1",
        plan_fingerprint="fp",
        screening_phase=None,
    )
    assert payload["sampling_metadata"]["sampling_policy"] == "legacy_large_grid"
    assert payload["sampling_metadata"]["sampled_count"] == 3
    assert payload["sampling_metadata"]["grid_size"] == 20


def test_payload_carries_metadata_for_unavailable_grid() -> None:
    strategy = {
        "name": "test",
        "factory": _trivial_factory,
        "params": {"a": 99},  # not iterable -> grid_unavailable
    }
    payload = _build_child_payload(
        strategy=strategy,
        candidate={"candidate_id": "c1", "asset": "BTC-USD", "interval": "1d"},
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=30,
        max_samples=3,
        engine_class=BacktestEngine,
        resume_state=None,
        resume_sidecar_path=None,
        batch_id="batch-1",
        plan_fingerprint="fp",
        screening_phase=None,
    )
    assert payload["sampling_metadata"]["sampling_policy"] == "grid_size_unavailable"
    assert payload["sampling_metadata"]["coverage_warning"] == "grid_size_unavailable"
