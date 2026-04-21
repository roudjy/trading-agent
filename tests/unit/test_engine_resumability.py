"""
V3.3a — Engine-internal resumability tests.

Covers: snapshot validation, IS window skipping, OOS re-execution,
progress deduplication, and re-interruption correctness.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.backtesting.engine import (
    BacktestEngine,
    EngineExecutionSnapshot,
    EngineInterrupted,
    EngineResumeInvalid,
    EngineRunProgress,
)
from tests._harness_helpers import build_ohlcv_frame

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASSET = "TEST"
_BAR_COUNT = 800  # default anchored config → 3 folds
_SEED = 99


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame() -> pd.DataFrame:
    return build_ohlcv_frame(length=_BAR_COUNT, seed=_SEED)


def _make_engine() -> BacktestEngine:
    """Return a fully configured engine with mocked data loading."""
    engine = BacktestEngine(start_datum="2020-01-01", eind_datum="2023-12-31")
    frame = _make_frame()
    engine._laad_data = lambda asset, interval: frame  # type: ignore[method-assign]
    return engine


def _constant_strategy(df: pd.DataFrame) -> pd.Series:
    """Simple alternating strategy that generates trades."""
    signals = [1 if i % 6 < 3 else 0 for i in range(len(df))]
    return pd.Series(signals, index=df.index, dtype=int)


def _all_is_snapshot(fold_count: int = 3) -> EngineExecutionSnapshot:
    """Snapshot where all IS folds are done and OOS has not started."""
    completed = tuple((_ASSET, "train", fi) for fi in range(fold_count))
    return EngineExecutionSnapshot(
        phase="evaluate_out_of_sample",
        asset_index=0,
        fold_index=None,
        completed_window_ids=completed,
    )


def _partial_is_snapshot(n_completed: int = 1) -> EngineExecutionSnapshot:
    """Snapshot where the first n IS folds are done."""
    completed = tuple((_ASSET, "train", fi) for fi in range(n_completed))
    return EngineExecutionSnapshot(
        phase="evaluate_in_sample",
        asset_index=0,
        fold_index=n_completed - 1,
        completed_window_ids=completed,
    )


# ---------------------------------------------------------------------------
# Regression guard
# ---------------------------------------------------------------------------

def test_no_resume_snapshot_path_unchanged() -> None:
    """resume_snapshot=None must be equivalent to the default call."""
    engine1 = _make_engine()
    engine2 = _make_engine()

    result_default = engine1.run(_constant_strategy, assets=[_ASSET])
    result_explicit_none = engine2.run(
        _constant_strategy, assets=[_ASSET], resume_snapshot=None
    )

    assert result_default == result_explicit_none


# ---------------------------------------------------------------------------
# Empty snapshot (trivial valid prefix)
# ---------------------------------------------------------------------------

def test_empty_snapshot_accepted_and_output_equals_fresh() -> None:
    """An empty snapshot is a valid prefix; resumed result must equal fresh run."""
    engine_fresh = _make_engine()
    fresh_result = engine_fresh.run(_constant_strategy, assets=[_ASSET])

    empty_snapshot = EngineExecutionSnapshot(
        phase="load_contexts",
        asset_index=None,
        fold_index=None,
        completed_window_ids=(),
    )
    engine_resumed = _make_engine()
    resumed_result = engine_resumed.run(
        _constant_strategy, assets=[_ASSET], resume_snapshot=empty_snapshot
    )

    assert resumed_result == fresh_result


# ---------------------------------------------------------------------------
# Validation: invalid snapshots must raise EngineResumeInvalid
# ---------------------------------------------------------------------------

def test_invalid_wrong_asset_raises() -> None:
    """Asset name mismatch in snapshot → EngineResumeInvalid."""
    bad_snapshot = EngineExecutionSnapshot(
        phase="evaluate_in_sample",
        asset_index=0,
        fold_index=0,
        completed_window_ids=(("WRONG_ASSET", "train", 0),),
    )
    engine = _make_engine()
    with pytest.raises(EngineResumeInvalid, match="not a valid contiguous prefix"):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=bad_snapshot)


def test_invalid_wrong_fold_order_raises() -> None:
    """Fold index out of expected order → EngineResumeInvalid."""
    bad_snapshot = EngineExecutionSnapshot(
        phase="evaluate_in_sample",
        asset_index=0,
        fold_index=1,
        completed_window_ids=((_ASSET, "train", 1),),  # fold 0 skipped
    )
    engine = _make_engine()
    with pytest.raises(EngineResumeInvalid, match="not a valid contiguous prefix"):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=bad_snapshot)


def test_invalid_too_many_windows_raises() -> None:
    """More completed windows than the total expected → EngineResumeInvalid."""
    # 3 folds × 2 phases × 1 asset = 6 total; add a 7th bogus entry
    overfull = tuple(
        [(_ASSET, "train", fi) for fi in range(3)]
        + [(_ASSET, "oos", fi) for fi in range(3)]
        + [(_ASSET, "oos", 99)]  # doesn't exist
    )
    bad_snapshot = EngineExecutionSnapshot(
        phase="finalize_result",
        asset_index=None,
        fold_index=None,
        completed_window_ids=overfull,
    )
    engine = _make_engine()
    with pytest.raises(EngineResumeInvalid, match="snapshot has"):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=bad_snapshot)


def test_invalid_oos_before_is_complete_raises() -> None:
    """OOS window present before all IS windows are done → EngineResumeInvalid."""
    bad_snapshot = EngineExecutionSnapshot(
        phase="evaluate_out_of_sample",
        asset_index=0,
        fold_index=0,
        # Only 1 of 3 IS windows done, then an OOS window — not a valid prefix
        completed_window_ids=((_ASSET, "train", 0), (_ASSET, "oos", 0)),
    )
    engine = _make_engine()
    with pytest.raises(EngineResumeInvalid, match="not a valid contiguous prefix"):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=bad_snapshot)


def test_invalid_train_after_oos_raises() -> None:
    """'train' entry appearing after 'oos' entry → EngineResumeInvalid (strict ordering)."""
    bad_snapshot = EngineExecutionSnapshot(
        phase="evaluate_out_of_sample",
        asset_index=0,
        fold_index=0,
        completed_window_ids=((_ASSET, "oos", 0), (_ASSET, "train", 0)),
    )
    engine = _make_engine()
    with pytest.raises(
        EngineResumeInvalid,
        match="'train' window appearing after an 'oos' window",
    ):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=bad_snapshot)


# ---------------------------------------------------------------------------
# Core resume: output equivalence
# ---------------------------------------------------------------------------

def test_resume_after_full_is_phase_equals_fresh_run() -> None:
    """Resuming from an all-IS-complete snapshot must produce the same public output
    as a fresh uninterrupted run.

    Determinism precondition: data loading is stable (same mocked frame), strategy
    is pure (no mutable state), fold ordering is identical.
    """
    engine_fresh = _make_engine()
    fresh_result = engine_fresh.run(_constant_strategy, assets=[_ASSET])

    snapshot = _all_is_snapshot(fold_count=3)
    engine_resumed = _make_engine()
    resumed_result = engine_resumed.run(
        _constant_strategy, assets=[_ASSET], resume_snapshot=snapshot
    )

    assert resumed_result == fresh_result


# ---------------------------------------------------------------------------
# Skip correctness: IS windows not executed
# ---------------------------------------------------------------------------

def test_completed_is_windows_are_truly_skipped() -> None:
    """Resumed run must call _simuleer_detailed fewer times for IS phase."""
    original_simuleer = BacktestEngine._simuleer_detailed  # type: ignore[attr-defined]

    counts: dict[str, int] = {"is": 0, "oos": 0}

    def counting_simuleer(
        self_inner: BacktestEngine,
        df: pd.DataFrame,
        strategie_func,
        asset: str,
        *,
        regime_window: pd.DataFrame,
        fold_index: int,
        include_trade_events: bool,
        reference_window: pd.DataFrame | None = None,
        train_frame: pd.DataFrame | None = None,
        train_reference_frame: pd.DataFrame | None = None,
    ):
        if include_trade_events:
            counts["oos"] += 1
        else:
            counts["is"] += 1
        return original_simuleer(
            self_inner,
            df,
            strategie_func,
            asset,
            regime_window=regime_window,
            fold_index=fold_index,
            include_trade_events=include_trade_events,
            reference_window=reference_window,
            train_frame=train_frame,
            train_reference_frame=train_reference_frame,
        )

    # Baseline: fresh run counts
    counts.update({"is": 0, "oos": 0})
    with patch.object(BacktestEngine, "_simuleer_detailed", counting_simuleer):
        _make_engine().run(_constant_strategy, assets=[_ASSET])
    total_is = counts["is"]
    total_oos = counts["oos"]

    # Resumed run with 1 IS fold pre-completed
    counts.update({"is": 0, "oos": 0})
    snapshot_1 = _partial_is_snapshot(n_completed=1)
    with patch.object(BacktestEngine, "_simuleer_detailed", counting_simuleer):
        _make_engine().run(
            _constant_strategy, assets=[_ASSET], resume_snapshot=snapshot_1
        )

    assert counts["is"] == total_is - 1, "exactly one IS fold should be skipped"
    assert counts["oos"] == total_oos, "all OOS folds must still execute"

    # Resumed run with all IS folds pre-completed
    counts.update({"is": 0, "oos": 0})
    snapshot_all = _all_is_snapshot(fold_count=total_is)
    with patch.object(BacktestEngine, "_simuleer_detailed", counting_simuleer):
        _make_engine().run(
            _constant_strategy, assets=[_ASSET], resume_snapshot=snapshot_all
        )

    assert counts["is"] == 0, "all IS folds must be skipped"
    assert counts["oos"] == total_oos, "all OOS folds must still execute"


# ---------------------------------------------------------------------------
# Progress state: deduplication
# ---------------------------------------------------------------------------

def test_no_duplicate_window_ids_in_progress_after_resume() -> None:
    """Progress tracker must not accumulate duplicate entries when OOS windows
    that were in the snapshot are re-executed during the resumed run."""
    # Build a snapshot with all IS and the first OOS window (interrupted mid-OOS)
    completed = (
        (_ASSET, "train", 0),
        (_ASSET, "train", 1),
        (_ASSET, "train", 2),
        (_ASSET, "oos", 0),
    )
    snapshot = EngineExecutionSnapshot(
        phase="evaluate_out_of_sample",
        asset_index=0,
        fold_index=0,
        completed_window_ids=completed,
    )

    engine = _make_engine()
    # Capture the progress object by hooking into _run_phase_finalize_result
    captured: dict[str, EngineRunProgress] = {}
    original_finalize = BacktestEngine._run_phase_finalize_result

    def capturing_finalize(self_inner, *, asset_contexts, is_summary, oos_summary, stop_control, progress, strategie_func):
        captured["progress"] = progress
        return original_finalize(
            self_inner,
            asset_contexts=asset_contexts,
            is_summary=is_summary,
            oos_summary=oos_summary,
            stop_control=stop_control,
            progress=progress,
            strategie_func=strategie_func,
        )

    with patch.object(BacktestEngine, "_run_phase_finalize_result", capturing_finalize):
        engine.run(_constant_strategy, assets=[_ASSET], resume_snapshot=snapshot)

    progress = captured["progress"]
    ids = list(progress.completed_window_ids)
    assert len(ids) == len(set(ids)), "no duplicate window IDs in progress after resume"


# ---------------------------------------------------------------------------
# Re-interruption produces a valid snapshot
# ---------------------------------------------------------------------------

def test_re_interruption_during_resumed_run_produces_valid_snapshot() -> None:
    """Interrupting a resumed run must produce a new snapshot that is itself
    a valid resume input for another run."""
    # Step 1: capture a real snapshot from a fresh interrupted run
    call_count = [0]

    def stop_after_first_is_fold() -> bool:
        call_count[0] += 1
        return call_count[0] > 5  # enough to pass load phase, interrupt in IS

    snapshot_a: EngineExecutionSnapshot | None = None
    try:
        _make_engine().run(
            _constant_strategy,
            assets=[_ASSET],
            should_stop=stop_after_first_is_fold,
        )
    except EngineInterrupted as exc:
        snapshot_a = exc.snapshot

    assert snapshot_a is not None, "expected interruption did not occur"

    # Step 2: resume from snapshot_a but interrupt again
    call_count[0] = 0

    def stop_during_resume() -> bool:
        call_count[0] += 1
        return call_count[0] > 10

    snapshot_b: EngineExecutionSnapshot | None = None
    try:
        _make_engine().run(
            _constant_strategy,
            assets=[_ASSET],
            should_stop=stop_during_resume,
            resume_snapshot=snapshot_a,
        )
    except EngineInterrupted as exc:
        snapshot_b = exc.snapshot

    # Step 3: snapshot_b must be accepted as a valid resume input
    if snapshot_b is not None:
        # If we got a new snapshot, it must be valid for another resume
        engine_final = _make_engine()
        # This must not raise EngineResumeInvalid
        engine_final.run(
            _constant_strategy, assets=[_ASSET], resume_snapshot=snapshot_b
        )
