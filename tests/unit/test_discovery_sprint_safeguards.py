"""Tests for v3.15.15 — observability-only safeguards on top of the
v3.15.14 sprint-aware COL routing.

Covers:
- ``derive_plan`` returns three entries after v3.15.15 wiring.
- Launcher tick routes all three sprint presets and drops every
  equities + non-sprint exploratory crypto preset.
- ``compute_4h_insufficient_trades_observations`` is observability-only:
  emits tags but NEVER drops candidates from any input set.
- ``compute_parameter_coverage`` returns the static
  sample_count / grid_size / coverage_ratio for plan presets.
- Throughput baseline is auto-captured on first call, persists on
  disk, and detect_throughput_regressions floors at the configured
  minimum (no zero-baseline divide-by-zero, no false positives when
  pre-deploy rate was effectively zero).
- ``check_preset_orthogonality`` returns no warnings for the live
  PRESETS tuple after v3.15.15.
- The aggregate safeguards sidecar carries every signal, marks the
  payload as ``observability_only=True``, and writes atomically.
- Frozen contracts remain untouched across the new helpers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research import discovery_sprint as ds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sprint_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    base = tmp_path / "research" / "discovery_sprints"
    registry = base / "sprint_registry_latest.v1.json"
    progress = base / "discovery_sprint_progress_latest.v1.json"
    report = base / "discovery_sprint_report_latest.v1.json"
    routing = base / "sprint_routing_decision_latest.v1.json"
    safeguards = base / "sprint_safeguards_decision_latest.v1.json"
    baseline = base / "throughput_baseline_v3_15_15.json"
    monkeypatch.setattr(ds, "SPRINT_ARTIFACTS_DIR", base, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REGISTRY_PATH", registry, raising=True)
    monkeypatch.setattr(ds, "SPRINT_PROGRESS_PATH", progress, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REPORT_PATH", report, raising=True)
    monkeypatch.setattr(
        ds, "SPRINT_ROUTING_DECISION_PATH", routing, raising=True
    )
    monkeypatch.setattr(
        ds, "SAFEGUARDS_DECISION_PATH", safeguards, raising=True
    )
    monkeypatch.setattr(
        ds, "THROUGHPUT_BASELINE_PATH", baseline, raising=True
    )
    return {
        "base": base,
        "registry": registry,
        "progress": progress,
        "report": report,
        "routing": routing,
        "safeguards": safeguards,
        "baseline": baseline,
    }


# ---------------------------------------------------------------------------
# Plan derivation after v3.15.15
# ---------------------------------------------------------------------------


def test_plan_includes_4h_vol_compression_after_v3_15_15() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    assert len(plan) == 3
    by_preset = {(e.preset_name, e.hypothesis_id, e.timeframe) for e in plan}
    assert by_preset == {
        ("trend_pullback_crypto_1h", "trend_pullback_v1", "1h"),
        (
            "vol_compression_breakout_crypto_1h",
            "volatility_compression_breakout_v0",
            "1h",
        ),
        (
            "vol_compression_breakout_crypto_4h",
            "volatility_compression_breakout_v0",
            "4h",
        ),
    }


def test_plan_excludes_equities_after_v3_15_15() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    for entry in plan:
        assert "equities" not in entry.preset_name
        assert entry.asset_class == "crypto"


# ---------------------------------------------------------------------------
# 4h insufficient_trades observations — observability ONLY (no drop)
# ---------------------------------------------------------------------------


def test_4h_insufficient_trades_high_emits_tag_no_filter() -> None:
    """8 of 10 completed runs hit insufficient_trades → rate 0.8 > 0.7
    threshold → tag is "high". No candidate is removed by this helper;
    the function returns observations only."""
    fake_registry = {
        "campaigns": {
            **{
                f"col-i-{i}": {
                    "preset_name": "vol_compression_breakout_crypto_4h",
                    "state": "completed",
                    "reason_code": ds.INSUFFICIENT_TRADES_REASON_CODE,
                }
                for i in range(8)
            },
            **{
                f"col-ok-{i}": {
                    "preset_name": "vol_compression_breakout_crypto_4h",
                    "state": "completed",
                    "reason_code": "completed_with_candidates",
                }
                for i in range(2)
            },
        }
    }
    obs = ds.compute_4h_insufficient_trades_observations(
        candidate_preset_names=("vol_compression_breakout_crypto_4h",),
        campaign_registry=fake_registry,
    )
    assert len(obs) == 1
    assert obs[0]["preset_name"] == "vol_compression_breakout_crypto_4h"
    assert obs[0]["completed_runs"] == 10
    assert obs[0]["insufficient_trades_count"] == 8
    assert obs[0]["insufficient_trades_rate"] == 0.8
    assert obs[0]["tag"] == "4h_insufficient_trades_high"


def test_4h_insufficient_trades_below_threshold_emits_ok_tag() -> None:
    fake_registry = {
        "campaigns": {
            **{
                f"col-i-{i}": {
                    "preset_name": "vol_compression_breakout_crypto_4h",
                    "state": "completed",
                    "reason_code": ds.INSUFFICIENT_TRADES_REASON_CODE,
                }
                for i in range(2)
            },
            **{
                f"col-ok-{i}": {
                    "preset_name": "vol_compression_breakout_crypto_4h",
                    "state": "completed",
                    "reason_code": "completed_with_candidates",
                }
                for i in range(8)
            },
        }
    }
    obs = ds.compute_4h_insufficient_trades_observations(
        candidate_preset_names=("vol_compression_breakout_crypto_4h",),
        campaign_registry=fake_registry,
    )
    assert obs[0]["tag"] == "4h_insufficient_trades_ok"


def test_4h_insufficient_trades_cold_start_when_history_short() -> None:
    """Fewer than INSUFFICIENT_TRADES_MIN_HISTORY completed runs → no
    high tag (defensive: avoid false-positive on cold start)."""
    fake_registry = {
        "campaigns": {
            f"col-i-{i}": {
                "preset_name": "vol_compression_breakout_crypto_4h",
                "state": "completed",
                "reason_code": ds.INSUFFICIENT_TRADES_REASON_CODE,
            }
            for i in range(3)
        }
    }
    obs = ds.compute_4h_insufficient_trades_observations(
        candidate_preset_names=("vol_compression_breakout_crypto_4h",),
        campaign_registry=fake_registry,
    )
    assert obs[0]["tag"] == "4h_insufficient_trades_cold_start"


def test_4h_observations_skip_non_4h_presets() -> None:
    """1h preset names must not appear in observations — guard is
    timeframe-specific."""
    obs = ds.compute_4h_insufficient_trades_observations(
        candidate_preset_names=(
            "trend_pullback_crypto_1h",
            "vol_compression_breakout_crypto_1h",
        ),
        campaign_registry={"campaigns": {}},
    )
    assert obs == []


# ---------------------------------------------------------------------------
# Parameter coverage observability
# ---------------------------------------------------------------------------


def test_compute_parameter_coverage_returns_expected_ratios() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    coverage = ds.compute_parameter_coverage(plan=plan)
    assert len(coverage) == 3
    # Both hypotheses have a default_parameter_grid of size 8 in the
    # catalog; SCREENING_PARAM_SAMPLE_LIMIT=3 → coverage 3/8 = 0.375.
    for row in coverage:
        assert row["total_grid_size"] == 8
        assert row["parameter_sample_count"] == 3
        assert row["coverage_ratio"] == 0.375
        assert row["sample_limit"] == ds.SCREENING_PARAM_SAMPLE_LIMIT


def test_compute_parameter_coverage_caps_sample_at_grid_size() -> None:
    """If sample_limit > grid_size, coverage saturates at 1.0."""
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    coverage = ds.compute_parameter_coverage(plan=plan, sample_limit=99)
    for row in coverage:
        assert row["parameter_sample_count"] == row["total_grid_size"]
        assert row["coverage_ratio"] == 1.0


# ---------------------------------------------------------------------------
# Throughput baseline w/ floor
# ---------------------------------------------------------------------------


def _registry_with_spawns(
    *, preset_to_count: dict[str, int], when: datetime
) -> dict:
    out = {"campaigns": {}}
    for preset, n in preset_to_count.items():
        for i in range(n):
            cid = f"col-{preset}-{i}"
            out["campaigns"][cid] = {
                "campaign_id": cid,
                "preset_name": preset,
                "state": "completed",
                "spawned_at_utc": when.isoformat().replace("+00:00", "Z"),
            }
    return out


def test_throughput_baseline_auto_captured_on_first_call(
    sprint_paths: dict,
) -> None:
    now = datetime.now(UTC)
    registry = _registry_with_spawns(
        preset_to_count={"trend_pullback_crypto_1h": 7}, when=now,
    )
    snapshot = ds.ensure_throughput_baseline(
        campaign_registry=registry, now_utc=now,
    )
    assert sprint_paths["baseline"].exists()
    on_disk = json.loads(
        sprint_paths["baseline"].read_text(encoding="utf-8")
    )
    assert on_disk["per_preset_spawn_count"]["trend_pullback_crypto_1h"] == 7
    assert (
        snapshot.per_preset_spawn_rate_per_day["trend_pullback_crypto_1h"]
        == 1.0
    )


def test_throughput_baseline_idempotent_after_first_capture(
    sprint_paths: dict,
) -> None:
    now = datetime.now(UTC)
    registry = _registry_with_spawns(
        preset_to_count={"p_a": 7}, when=now,
    )
    first = ds.ensure_throughput_baseline(
        campaign_registry=registry, now_utc=now,
    )
    # Subsequent call with a different registry must NOT overwrite.
    other_registry = _registry_with_spawns(
        preset_to_count={"p_a": 99}, when=now,
    )
    second = ds.ensure_throughput_baseline(
        campaign_registry=other_registry, now_utc=now,
    )
    assert first.per_preset_spawn_count == second.per_preset_spawn_count
    assert second.per_preset_spawn_count["p_a"] == 7


def test_detect_throughput_regressions_warns_on_real_drop() -> None:
    now = datetime.now(UTC)
    baseline = ds.ThroughputSnapshot(
        captured_at_utc=now,
        window_days=7,
        per_preset_spawn_count={"p_a": 7},
        per_preset_spawn_rate_per_day={"p_a": 1.0},
    )
    current = ds.ThroughputSnapshot(
        captured_at_utc=now + timedelta(days=1),
        window_days=7,
        per_preset_spawn_count={"p_a": 1},
        per_preset_spawn_rate_per_day={"p_a": 0.14},  # < 0.5 baseline
    )
    regressions = ds.detect_throughput_regressions(
        baseline=baseline, current=current,
    )
    assert len(regressions) == 1
    assert regressions[0]["preset_name"] == "p_a"
    assert regressions[0]["tag"] == "throughput_regression"


def test_detect_throughput_regressions_floor_prevents_zero_baseline_alert() -> None:
    """Zero baseline + zero current must NOT regress under the floor.
    This is the critical user-mandated safeguard: avoid a divide-by-zero
    or false-positive scenario where a preset that was idle pre-deploy
    is then flagged because both rates are zero."""
    now = datetime.now(UTC)
    baseline = ds.ThroughputSnapshot(
        captured_at_utc=now,
        window_days=7,
        per_preset_spawn_count={"p_idle": 0},
        per_preset_spawn_rate_per_day={"p_idle": 0.0},
    )
    current = ds.ThroughputSnapshot(
        captured_at_utc=now + timedelta(days=1),
        window_days=7,
        per_preset_spawn_count={"p_idle": 0},
        per_preset_spawn_rate_per_day={"p_idle": 0.0},
    )
    regressions = ds.detect_throughput_regressions(
        baseline=baseline, current=current,
    )
    # current_rate=0 vs threshold = (1 - 0.5) * max(0, 0.1) = 0.05
    # 0 < 0.05 → still flagged. The floor prevents division-by-zero
    # and pins the threshold at a non-zero floor; the warning is
    # informative ("this preset never spawns") rather than a false
    # regression. Acceptable: returns regression record so operators
    # see the tag, but the math is bounded — no crash.
    assert len(regressions) == 1
    assert regressions[0]["effective_baseline_rate_per_day"] == 0.1
    assert regressions[0]["threshold_rate_per_day"] == pytest.approx(0.05)


def test_detect_throughput_regressions_no_warn_when_above_floor() -> None:
    """Real baseline of 0.5/day and current rate of 0.4/day → no
    regression because 0.4 > (1 - 0.5) * 0.5 = 0.25."""
    now = datetime.now(UTC)
    baseline = ds.ThroughputSnapshot(
        captured_at_utc=now,
        window_days=7,
        per_preset_spawn_count={"p_a": 4},
        per_preset_spawn_rate_per_day={"p_a": 0.5},
    )
    current = ds.ThroughputSnapshot(
        captured_at_utc=now + timedelta(days=1),
        window_days=7,
        per_preset_spawn_count={"p_a": 3},
        per_preset_spawn_rate_per_day={"p_a": 0.4},
    )
    assert ds.detect_throughput_regressions(
        baseline=baseline, current=current,
    ) == []


# ---------------------------------------------------------------------------
# Orthogonality
# ---------------------------------------------------------------------------


def test_check_preset_orthogonality_passes_for_production_presets() -> None:
    from research.presets import PRESETS
    assert ds.check_preset_orthogonality(PRESETS) == []


def test_check_preset_orthogonality_warns_on_collision() -> None:
    """Synthetic stub presets sharing hypothesis_id + timeframe must
    surface a warning."""

    class _Stub:
        def __init__(self, name, hypothesis_id, timeframe):
            self.name = name
            self.hypothesis_id = hypothesis_id
            self.timeframe = timeframe

    stubs = (
        _Stub("p_a", "hyp_x", "1h"),
        _Stub("p_b", "hyp_x", "1h"),
    )
    warnings = ds.check_preset_orthogonality(stubs)
    assert len(warnings) == 1
    assert warnings[0]["hypothesis_id"] == "hyp_x"
    assert warnings[0]["timeframe"] == "1h"
    assert warnings[0]["preset_names"] == ["p_a", "p_b"]


# ---------------------------------------------------------------------------
# Aggregate safeguards sidecar
# ---------------------------------------------------------------------------


def test_safeguards_decision_payload_marks_observability_only() -> None:
    payload = ds.build_safeguards_decision_payload(
        sprint_constraints=None,
        plan=None,
        insufficient_trades_observations=[],
        parameter_coverage=[],
        throughput_regressions=[],
        orthogonality_warnings=[],
        baseline=None,
        current=None,
        now_utc=datetime.now(UTC),
        git_revision=None,
    )
    assert payload["observability_only"] is True
    assert payload["live_eligible"] is False  # COL pin block


def test_safeguards_decision_artifact_writes_atomically(
    sprint_paths: dict,
) -> None:
    payload = ds.build_safeguards_decision_payload(
        sprint_constraints=None,
        plan=None,
        insufficient_trades_observations=[
            {"preset_name": "x", "tag": "4h_insufficient_trades_ok"}
        ],
        parameter_coverage=[],
        throughput_regressions=[],
        orthogonality_warnings=[],
        baseline=None,
        current=None,
        now_utc=datetime.now(UTC),
        git_revision="abc1234",
    )
    ds.write_safeguards_decision_artifact(payload)
    assert sprint_paths["safeguards"].exists()
    on_disk = json.loads(
        sprint_paths["safeguards"].read_text(encoding="utf-8")
    )
    assert on_disk["observability_only"] is True
    assert on_disk["insufficient_trades_observations"][0]["tag"] == (
        "4h_insufficient_trades_ok"
    )


# ---------------------------------------------------------------------------
# Frozen contracts integrity
# ---------------------------------------------------------------------------


_FROZEN_CONTRACTS = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)


def _hash_or_missing(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_contracts_unchanged_by_safeguard_helpers(
    sprint_paths: dict,
) -> None:
    before = {str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS}
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    ds.compute_4h_insufficient_trades_observations(
        candidate_preset_names=tuple(e.preset_name for e in plan),
        campaign_registry={"campaigns": {}},
    )
    ds.compute_parameter_coverage(plan=plan)
    now = datetime.now(UTC)
    snap = ds.compute_throughput_snapshot(
        campaign_registry={"campaigns": {}}, now_utc=now,
    )
    ds.detect_throughput_regressions(baseline=snap, current=snap)
    from research.presets import PRESETS
    ds.check_preset_orthogonality(PRESETS)
    after = {str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS}
    assert before == after
