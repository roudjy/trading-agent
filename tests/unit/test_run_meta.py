"""Unit tests for the v3.10 run_meta sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.presets import get_preset
from research.run_meta import (
    RUN_META_PATH,
    RUN_META_SCHEMA_VERSION,
    build_run_meta_payload,
    is_run_excluded_from_promotion,
    read_run_meta_sidecar,
    rollup_rejection_reasons,
    summarize_candidates,
    write_run_meta_sidecar,
)


def _sample_payload(preset_name: str = "trend_equities_4h_baseline"):
    preset = get_preset(preset_name) if preset_name else None
    return build_run_meta_payload(
        run_id="run-test-1",
        preset=preset,
        started_at_utc="2026-04-22T06:00:00+00:00",
        completed_at_utc="2026-04-22T06:40:00+00:00",
        git_revision="abc123",
        config_hash="hash0",
        candidate_summary=summarize_candidates(raw=10, screened=6, validated=6, rejected=5, promoted=1),
        top_rejection_reasons=[{"reason": "deflated_sharpe_fail", "count": 3}],
        artifact_paths={"run_state": "research/run_state.v1.json"},
    )


def test_payload_matches_schema_v1():
    payload = _sample_payload()
    assert payload["schema_version"] == RUN_META_SCHEMA_VERSION
    assert payload["preset_name"] == "trend_equities_4h_baseline"
    assert payload["preset_bundle"] == ["sma_crossover", "breakout_momentum"]
    assert payload["candidate_summary"]["promoted"] == 1


def test_payload_without_preset_blocks_promotion_by_default():
    payload = build_run_meta_payload(
        run_id="run-no-preset",
        preset=None,
        started_at_utc="2026-04-22T00:00:00+00:00",
        completed_at_utc=None,
        git_revision=None,
        config_hash=None,
        candidate_summary=None,
        top_rejection_reasons=None,
        artifact_paths=None,
    )
    assert payload["preset_name"] is None
    assert payload["excluded_from_candidate_promotion"] is True  # safe default


def test_write_and_read_roundtrip(tmp_path: Path):
    payload = _sample_payload()
    path = tmp_path / "run_meta_latest.v1.json"
    write_run_meta_sidecar(payload, path=path)
    restored = read_run_meta_sidecar(path)
    assert restored == payload


def test_promotion_excluded_when_sidecar_missing(tmp_path: Path):
    absent = tmp_path / "does_not_exist.json"
    assert is_run_excluded_from_promotion(absent) is True


def test_promotion_excluded_when_diagnostic_flag_set(tmp_path: Path):
    payload = _sample_payload("crypto_diagnostic_1h")
    path = tmp_path / "run_meta_latest.v1.json"
    write_run_meta_sidecar(payload, path=path)
    assert is_run_excluded_from_promotion(path) is True


def test_promotion_allowed_when_preset_is_promoteable(tmp_path: Path):
    payload = _sample_payload("trend_equities_4h_baseline")
    path = tmp_path / "run_meta_latest.v1.json"
    write_run_meta_sidecar(payload, path=path)
    assert is_run_excluded_from_promotion(path) is False


def test_rollup_rejection_reasons_orders_by_count():
    rows = [
        {"reden": "deflated_sharpe_fail"},
        {"reden": "deflated_sharpe_fail"},
        {"reden": "max_drawdown_fail"},
        {"reden": ""},
        {"reden": None},
    ]
    rollup = rollup_rejection_reasons(rows, limit=5)
    assert rollup[0]["reason"] == "deflated_sharpe_fail"
    assert rollup[0]["count"] == 2
    assert rollup[1]["reason"] == "max_drawdown_fail"
    assert rollup[1]["count"] == 1
    assert len(rollup) == 2


def test_summarize_candidates_defaults_to_zero():
    summary = summarize_candidates()
    assert summary == {
        "raw": 0, "screened": 0, "validated": 0, "rejected": 0, "promoted": 0,
    }


def test_sidecar_atomic_write_produces_json(tmp_path: Path):
    payload = _sample_payload()
    path = tmp_path / "nested" / "run_meta.json"
    write_run_meta_sidecar(payload, path=path)
    assert path.exists()
    blob = json.loads(path.read_text(encoding="utf-8"))
    assert blob["run_id"] == "run-test-1"


def test_default_run_meta_path_is_adjacent_to_frozen_artifacts():
    assert RUN_META_PATH == Path("research/run_meta_latest.v1.json")
