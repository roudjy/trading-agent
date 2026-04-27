"""Tests for research.discovery_sprint (v3.15.13 Sprint Orchestrator)."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research import discovery_sprint as ds


# ---------------------------------------------------------------------------
# Profile catalog
# ---------------------------------------------------------------------------


def test_builtin_profiles_only_contains_crypto_exploratory_v1() -> None:
    assert set(ds.BUILTIN_PROFILES) == {"crypto_exploratory_v1"}


def test_crypto_exploratory_v1_spec_is_exact() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    assert profile.target_campaigns == 50
    assert profile.max_days == 5
    assert profile.asset_class == "crypto"
    assert profile.timeframes == ("1h", "4h")
    assert profile.screening_phase == "exploratory"
    assert profile.hypotheses == (
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    )
    assert profile.exclude_equities is True
    assert profile.exclude_promotion_grade is True


def test_get_profile_unknown_raises_profile_error() -> None:
    with pytest.raises(ds.ProfileError):
        ds.get_profile("does_not_exist")


def test_validate_profile_rejects_zero_target() -> None:
    bad = ds.SprintProfile(
        name="bad",
        target_campaigns=0,
        max_days=1,
        asset_class="crypto",
        timeframes=("1h",),
        screening_phase="exploratory",
        hypotheses=("trend_pullback_v1",),
        exclude_equities=True,
        exclude_promotion_grade=True,
    )
    with pytest.raises(ds.ProfileError):
        ds._validate_profile(bad)


def test_validate_profile_rejects_unknown_hypothesis() -> None:
    bad = ds.SprintProfile(
        name="bad",
        target_campaigns=10,
        max_days=1,
        asset_class="crypto",
        timeframes=("1h",),
        screening_phase="exploratory",
        hypotheses=("not_in_catalog",),
        exclude_equities=True,
        exclude_promotion_grade=True,
    )
    with pytest.raises(ds.ProfileError):
        ds._validate_profile(bad)


def test_validate_profile_crypto_must_exclude_equities() -> None:
    bad = ds.SprintProfile(
        name="bad",
        target_campaigns=10,
        max_days=1,
        asset_class="crypto",
        timeframes=("1h",),
        screening_phase="exploratory",
        hypotheses=("trend_pullback_v1",),
        exclude_equities=False,
        exclude_promotion_grade=True,
    )
    with pytest.raises(ds.ProfileError):
        ds._validate_profile(bad)


def test_validate_profile_exploratory_must_exclude_promotion_grade() -> None:
    bad = ds.SprintProfile(
        name="bad",
        target_campaigns=10,
        max_days=1,
        asset_class="crypto",
        timeframes=("1h",),
        screening_phase="exploratory",
        hypotheses=("trend_pullback_v1",),
        exclude_equities=True,
        exclude_promotion_grade=False,
    )
    with pytest.raises(ds.ProfileError):
        ds._validate_profile(bad)


# ---------------------------------------------------------------------------
# Plan derivation
# ---------------------------------------------------------------------------


def test_plan_is_deterministic_across_calls() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    a = ds.derive_plan(profile)
    b = ds.derive_plan(profile)
    assert a == b
    payload_a = [e.to_payload() for e in a]
    payload_b = [e.to_payload() for e in b]
    assert json.dumps(payload_a, sort_keys=True) == json.dumps(
        payload_b, sort_keys=True
    )


def test_plan_excludes_equities_presets() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    for entry in plan:
        assert "equities" not in entry.preset_name
        assert entry.asset_class == "crypto"


def test_plan_excludes_promotion_grade_presets() -> None:
    """Plan filter rejects any preset whose screening_phase != 'exploratory'."""
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    # The crypto exploratory profile only allows screening_phase==exploratory;
    # the catalog has a non-exploratory crypto preset (crypto_diagnostic_1h
    # is exploratory too, but trend_equities_4h_baseline is promotion_grade
    # and would be excluded for being equity *and* for being promotion_grade).
    # This test asserts the post-condition.
    from research.presets import PRESETS

    plan_presets = {e.preset_name for e in plan}
    for preset in PRESETS:
        if (
            preset.name in plan_presets
            and preset.screening_phase != "exploratory"
        ):
            pytest.fail(
                f"plan contained non-exploratory preset {preset.name!r} "
                f"(phase={preset.screening_phase!r})"
            )


def test_plan_only_contains_allowed_hypotheses() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    allowed = set(profile.hypotheses)
    for entry in plan:
        assert entry.hypothesis_id in allowed


def test_plan_contains_both_target_presets() -> None:
    """Sanity: the two stable+exploratory crypto presets must be picked."""
    profile = ds.get_profile("crypto_exploratory_v1")
    plan = ds.derive_plan(profile)
    preset_names = {e.preset_name for e in plan}
    assert "trend_pullback_crypto_1h" in preset_names
    assert "vol_compression_breakout_crypto_1h" in preset_names


def test_infer_asset_class_handles_known_universes() -> None:
    assert (
        ds._infer_asset_class(("BTC-EUR", "ETH-EUR", "SOL-EUR")) == "crypto"
    )
    assert ds._infer_asset_class(("NVDA", "AMD", "MSFT")) == "equity"
    # mixed → None
    assert ds._infer_asset_class(("BTC-EUR", "AAPL")) is None
    # empty → None
    assert ds._infer_asset_class(()) is None


# ---------------------------------------------------------------------------
# Sprint id determinism + state guards
# ---------------------------------------------------------------------------


def test_compute_sprint_id_is_deterministic_for_same_inputs() -> None:
    profile = ds.get_profile("crypto_exploratory_v1")
    ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    a = ds.compute_sprint_id(profile=profile, started_at_utc=ts)
    b = ds.compute_sprint_id(profile=profile, started_at_utc=ts)
    assert a == b
    assert a.startswith("sprt-20260501T120000Z-")
    assert len(a.rsplit("-", 1)[-1]) == 10


def test_is_active_sprint_handles_missing_and_expired() -> None:
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    assert ds.is_active_sprint(registry_payload=None, now_utc=now) is False
    assert (
        ds.is_active_sprint(
            registry_payload={"state": "completed"}, now_utc=now
        )
        is False
    )
    expired = {
        "state": "active",
        "expected_completion_at_utc": "2026-04-30T00:00:00Z",
    }
    assert ds.is_active_sprint(registry_payload=expired, now_utc=now) is False
    fresh = {
        "state": "active",
        "expected_completion_at_utc": "2026-05-10T00:00:00Z",
    }
    assert ds.is_active_sprint(registry_payload=fresh, now_utc=now) is True


# ---------------------------------------------------------------------------
# CLI commands (artifact-isolated to tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def sprint_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """Redirect all sprint artifact paths under a per-test tmp dir."""
    base = tmp_path / "research" / "discovery_sprints"
    registry = base / "sprint_registry_latest.v1.json"
    progress = base / "discovery_sprint_progress_latest.v1.json"
    report = base / "discovery_sprint_report_latest.v1.json"
    monkeypatch.setattr(ds, "SPRINT_ARTIFACTS_DIR", base, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REGISTRY_PATH", registry, raising=True)
    monkeypatch.setattr(ds, "SPRINT_PROGRESS_PATH", progress, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REPORT_PATH", report, raising=True)
    return {
        "base": base,
        "registry": registry,
        "progress": progress,
        "report": report,
    }


def test_cmd_plan_emits_json_and_returns_zero(sprint_paths: dict) -> None:
    buf = io.StringIO()
    rc = ds.cmd_plan("crypto_exploratory_v1", out=buf)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["profile"]["name"] == "crypto_exploratory_v1"
    assert payload["plan"]["entry_count"] >= 1
    # plan must NOT touch artifacts
    assert not sprint_paths["registry"].exists()
    assert not sprint_paths["progress"].exists()


def test_cmd_plan_unknown_profile_returns_two(sprint_paths: dict) -> None:
    buf = io.StringIO()
    rc = ds.cmd_plan("nonexistent", out=buf)
    assert rc == 2


def test_cmd_run_writes_registry_and_progress(sprint_paths: dict) -> None:
    buf = io.StringIO()
    rc = ds.cmd_run("crypto_exploratory_v1", out=buf)
    assert rc == 0
    assert sprint_paths["registry"].exists()
    assert sprint_paths["progress"].exists()
    registry = json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))
    assert registry["state"] == "active"
    assert registry["sprint_id"].startswith("sprt-")
    assert registry["profile"]["name"] == "crypto_exploratory_v1"
    progress = json.loads(sprint_paths["progress"].read_text(encoding="utf-8"))
    assert progress["sprint_id"] == registry["sprint_id"]
    assert progress["observed_total"] == 0


def test_cmd_run_refuses_when_active_sprint_exists(
    sprint_paths: dict,
) -> None:
    first = io.StringIO()
    assert ds.cmd_run("crypto_exploratory_v1", out=first) == 0
    second = io.StringIO()
    rc = ds.cmd_run("crypto_exploratory_v1", out=second)
    assert rc == 1, f"expected refusal, got rc={rc}, stdout={second.getvalue()}"


def test_cmd_status_with_no_registry_reports_no_sprint(
    sprint_paths: dict,
) -> None:
    buf = io.StringIO()
    rc = ds.cmd_status(out=buf)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload == {"state": "no_sprint", "sprint_id": None}


def test_cmd_status_counts_observations_from_campaign_registry(
    sprint_paths: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Start a sprint
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    started_at = datetime.fromisoformat(
        json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))[
            "started_at_utc"
        ].replace("Z", "+00:00")
    )
    # Pin "now" to one hour after the sprint started so the upper-bound
    # filter in count_observations admits campaigns that finished within
    # the window.
    fake_now = started_at + timedelta(hours=2)
    monkeypatch.setattr(ds, "_now_utc", lambda: fake_now, raising=True)

    # Build a fake campaign_registry with two completed campaigns matching
    # the plan and one that doesn't.
    finished_after = (started_at + timedelta(hours=1)).isoformat().replace(
        "+00:00", "Z"
    )
    finished_before = (started_at - timedelta(hours=1)).isoformat().replace(
        "+00:00", "Z"
    )
    fake_registry = {
        "campaigns": {
            "col-1": {
                "campaign_id": "col-1",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished_after,
            },
            "col-2": {
                "campaign_id": "col-2",
                "preset_name": "vol_compression_breakout_crypto_1h",
                "state": "completed",
                "outcome": "paper_blocked",
                "finished_at_utc": finished_after,
            },
            "col-3-not-in-plan": {
                "campaign_id": "col-3-not-in-plan",
                "preset_name": "trend_equities_4h_baseline",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished_after,
            },
            "col-4-pre-sprint": {
                "campaign_id": "col-4-pre-sprint",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished_before,
            },
        }
    }
    monkeypatch.setattr(
        ds, "load_registry", lambda *_a, **_k: fake_registry, raising=True
    )

    buf = io.StringIO()
    rc = ds.cmd_status(out=buf)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["observed_total"] == 2
    assert payload["by_preset"] == {
        "trend_pullback_crypto_1h": 1,
        "vol_compression_breakout_crypto_1h": 1,
    }
    assert payload["by_hypothesis"] == {
        "trend_pullback_v1": 1,
        "volatility_compression_breakout_v0": 1,
    }


def test_cmd_status_transitions_to_completed_when_target_met(
    sprint_paths: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Use a tiny custom profile by patching the catalog → keep the real
    # crypto profile and simply fake 50 completed campaigns instead.
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    started_at = datetime.fromisoformat(
        json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))[
            "started_at_utc"
        ].replace("Z", "+00:00")
    )
    fake_now = started_at + timedelta(hours=2)
    monkeypatch.setattr(ds, "_now_utc", lambda: fake_now, raising=True)
    finished_at = (
        (started_at + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    )
    fake_registry = {
        "campaigns": {
            f"col-{i}": {
                "campaign_id": f"col-{i}",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished_at,
            }
            for i in range(50)
        }
    }
    monkeypatch.setattr(
        ds, "load_registry", lambda *_a, **_k: fake_registry, raising=True
    )

    rc = ds.cmd_status(out=io.StringIO())
    assert rc == 0
    registry = json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))
    assert registry["state"] == "completed"
    assert registry["completed_at_utc"] is not None


def test_cmd_status_transitions_to_expired_after_max_days(
    sprint_paths: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When window expires without target met, state becomes ``expired``."""
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0

    # Force "now" to be way past the expected_completion.
    far_future = datetime.now(UTC) + timedelta(days=30)
    monkeypatch.setattr(ds, "_now_utc", lambda: far_future, raising=True)

    rc = ds.cmd_status(out=io.StringIO())
    assert rc == 0
    registry = json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))
    assert registry["state"] == "expired"


def test_cmd_report_refuses_while_active(sprint_paths: dict) -> None:
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    rc = ds.cmd_report(out=io.StringIO())
    assert rc == 1
    assert not sprint_paths["report"].exists()


def test_cmd_report_writes_artifact_after_completion(
    sprint_paths: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    far_future = datetime.now(UTC) + timedelta(days=30)
    monkeypatch.setattr(ds, "_now_utc", lambda: far_future, raising=True)
    assert ds.cmd_status(out=io.StringIO()) == 0
    rc = ds.cmd_report(out=io.StringIO())
    assert rc == 0
    assert sprint_paths["report"].exists()
    payload = json.loads(sprint_paths["report"].read_text(encoding="utf-8"))
    assert payload["sprint_id"]
    assert payload["state"] == "expired"
    assert "outcome_summary" in payload


# ---------------------------------------------------------------------------
# Frozen-contract guard
# ---------------------------------------------------------------------------


_FROZEN_CONTRACTS = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)


def _hash_or_missing(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_contracts_unchanged_by_run(
    sprint_paths: dict,
) -> None:
    """Running the orchestrator must not touch the frozen contracts."""
    before = {
        str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS
    }
    assert ds.cmd_plan("crypto_exploratory_v1", out=io.StringIO()) == 0
    assert ds.cmd_run("crypto_exploratory_v1", out=io.StringIO()) == 0
    assert ds.cmd_status(out=io.StringIO()) == 0
    after = {
        str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS
    }
    assert before == after, (
        f"frozen contracts changed: before={before}, after={after}"
    )


def test_orchestrator_does_not_mutate_campaign_queue_or_registry(
    sprint_paths: dict, tmp_path: Path
) -> None:
    """Negative test: no v3.15.2 COL artifact is in the orchestrator's
    write set. We assert by inspecting the source for forbidden writes
    and by verifying the orchestrator API exposes none."""
    # API surface: there's no public symbol that mutates COL state.
    forbidden_substrings = (
        "write_queue",
        "write_registry",
        "write_decision",
        "append_events",
        "transition_state",
        "record_outcome",
    )
    src = Path("research/discovery_sprint.py").read_text(encoding="utf-8")
    for needle in forbidden_substrings:
        assert needle not in src, (
            f"discovery_sprint.py must not call COL mutator {needle!r}"
        )
