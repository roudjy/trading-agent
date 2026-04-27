"""Tests for v3.15.14 — Sprint-aware COL Routing.

Covers:
- ``load_active_sprint_constraints`` matrix (no registry, expired, target
  met, canceled/completed/expired states, happy path).
- ``apply_sprint_routing`` filters templates / followups / controls
  to the active sprint plan and is a no-op when no sprint is active.
- Routing decision sidecar payload shape + write.
- ``sprint_extra_for_record`` carries sprint_id / profile_name on the
  ``CampaignRecord.extra`` mapping.
- Launcher tick: when a sprint is active, only sprint-plan templates
  reach ``decide()`` (verified through a captured-args double); when
  no sprint is active, behavior is identical (passthrough).
- Frozen contracts (``research_latest.json``, ``strategy_matrix.csv``)
  are untouched across all of the above.
"""

from __future__ import annotations

import hashlib
import io
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
    monkeypatch.setattr(ds, "SPRINT_ARTIFACTS_DIR", base, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REGISTRY_PATH", registry, raising=True)
    monkeypatch.setattr(ds, "SPRINT_PROGRESS_PATH", progress, raising=True)
    monkeypatch.setattr(ds, "SPRINT_REPORT_PATH", report, raising=True)
    monkeypatch.setattr(
        ds, "SPRINT_ROUTING_DECISION_PATH", routing, raising=True
    )
    return {
        "base": base,
        "registry": registry,
        "progress": progress,
        "report": report,
        "routing": routing,
    }


def _start_active_sprint(sprint_paths: dict) -> dict:
    """Run the sprint via cmd_run and return the on-disk registry payload."""
    rc = ds.cmd_run("crypto_exploratory_v1", out=io.StringIO())
    assert rc == 0
    return json.loads(sprint_paths["registry"].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# load_active_sprint_constraints
# ---------------------------------------------------------------------------


def test_loader_returns_none_when_no_registry(sprint_paths: dict) -> None:
    assert ds.load_active_sprint_constraints() is None


def test_loader_returns_none_when_state_canceled(sprint_paths: dict) -> None:
    reg = _start_active_sprint(sprint_paths)
    reg["state"] = "canceled"
    sprint_paths["registry"].write_text(
        json.dumps(reg, sort_keys=True), encoding="utf-8"
    )
    assert ds.load_active_sprint_constraints() is None


def test_loader_returns_none_when_state_completed(
    sprint_paths: dict,
) -> None:
    reg = _start_active_sprint(sprint_paths)
    reg["state"] = "completed"
    sprint_paths["registry"].write_text(
        json.dumps(reg, sort_keys=True), encoding="utf-8"
    )
    assert ds.load_active_sprint_constraints() is None


def test_loader_returns_none_when_window_expired(
    sprint_paths: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start_active_sprint(sprint_paths)
    far_future = datetime.now(UTC) + timedelta(days=30)
    monkeypatch.setattr(ds, "_now_utc", lambda: far_future, raising=True)
    assert ds.load_active_sprint_constraints(now_utc=far_future) is None


def test_loader_returns_none_when_target_met(sprint_paths: dict) -> None:
    reg = _start_active_sprint(sprint_paths)
    started = datetime.fromisoformat(
        reg["started_at_utc"].replace("Z", "+00:00")
    )
    finished = (started + timedelta(hours=1)).isoformat().replace(
        "+00:00", "Z"
    )
    fake_registry = {
        "campaigns": {
            f"col-{i}": {
                "campaign_id": f"col-{i}",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished,
            }
            for i in range(50)  # target_campaigns is 50
        }
    }
    fake_now = started + timedelta(hours=2)
    out = ds.load_active_sprint_constraints(
        campaign_registry=fake_registry, now_utc=fake_now
    )
    assert out is None


def test_loader_returns_constraints_for_active_sprint(
    sprint_paths: dict,
) -> None:
    reg = _start_active_sprint(sprint_paths)
    constraints = ds.load_active_sprint_constraints()
    assert constraints is not None
    assert constraints.sprint_id == reg["sprint_id"]
    assert constraints.profile_name == "crypto_exploratory_v1"
    assert "trend_pullback_crypto_1h" in constraints.plan_preset_names
    assert (
        "vol_compression_breakout_crypto_1h"
        in constraints.plan_preset_names
    )
    assert "trend_pullback_v1" in constraints.plan_hypothesis_ids
    assert (
        "volatility_compression_breakout_v0"
        in constraints.plan_hypothesis_ids
    )
    assert constraints.target_campaigns == 50
    assert constraints.observed_total == 0


def test_loader_observes_completed_campaigns(sprint_paths: dict) -> None:
    reg = _start_active_sprint(sprint_paths)
    started = datetime.fromisoformat(
        reg["started_at_utc"].replace("Z", "+00:00")
    )
    finished = (started + timedelta(hours=1)).isoformat().replace(
        "+00:00", "Z"
    )
    fake_registry = {
        "campaigns": {
            "col-1": {
                "campaign_id": "col-1",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "completed",
                "outcome": "completed_with_candidates",
                "finished_at_utc": finished,
            },
            "col-2": {
                "campaign_id": "col-2",
                "preset_name": "vol_compression_breakout_crypto_1h",
                "state": "completed",
                "outcome": "paper_blocked",
                "finished_at_utc": finished,
            },
        }
    }
    fake_now = started + timedelta(hours=2)
    constraints = ds.load_active_sprint_constraints(
        campaign_registry=fake_registry, now_utc=fake_now
    )
    assert constraints is not None
    assert constraints.observed_total == 2


# ---------------------------------------------------------------------------
# apply_sprint_routing
# ---------------------------------------------------------------------------


class _Stub:
    def __init__(self, preset_name: str) -> None:
        self.preset_name = preset_name


def _make_constraints(presets: tuple[str, ...]) -> ds.ActiveSprintConstraints:
    now = datetime.now(UTC)
    return ds.ActiveSprintConstraints(
        sprint_id="sprt-test",
        profile_name="crypto_exploratory_v1",
        plan_preset_names=frozenset(presets),
        plan_hypothesis_ids=frozenset(),
        target_campaigns=50,
        started_at_utc=now,
        expected_completion_at_utc=now + timedelta(days=5),
        observed_total=0,
    )


def test_routing_passthrough_when_no_active_sprint() -> None:
    templates = (_Stub("a"), _Stub("b"), _Stub("c"))
    follow_ups = (_Stub("a"),)
    controls = (_Stub("b"),)
    out_t, out_f, out_c, counts = ds.apply_sprint_routing(
        templates=templates,
        follow_up_specs=follow_ups,
        weekly_control_specs=controls,
        sprint_constraints=None,
    )
    assert out_t == templates
    assert out_f == follow_ups
    assert out_c == controls
    assert counts["templates_total"] == 3
    assert counts["templates_filtered"] == 3


def test_routing_filters_templates_to_sprint_plan() -> None:
    templates = (
        _Stub("trend_pullback_crypto_1h"),
        _Stub("trend_equities_4h_baseline"),  # equities, must be dropped
        _Stub("vol_compression_breakout_crypto_1h"),
        _Stub("crypto_diagnostic_1h"),  # exploratory but not in plan
    )
    constraints = _make_constraints(
        ("trend_pullback_crypto_1h", "vol_compression_breakout_crypto_1h")
    )
    out_t, _, _, counts = ds.apply_sprint_routing(
        templates=templates,
        follow_up_specs=(),
        weekly_control_specs=(),
        sprint_constraints=constraints,
    )
    surviving = {t.preset_name for t in out_t}
    assert surviving == {
        "trend_pullback_crypto_1h",
        "vol_compression_breakout_crypto_1h",
    }
    assert counts["templates_total"] == 4
    assert counts["templates_filtered"] == 2


def test_routing_excludes_equities_preset() -> None:
    constraints = _make_constraints(
        ("trend_pullback_crypto_1h", "vol_compression_breakout_crypto_1h")
    )
    templates = (_Stub("trend_equities_4h_baseline"),)
    out_t, _, _, _ = ds.apply_sprint_routing(
        templates=templates,
        follow_up_specs=(),
        weekly_control_specs=(),
        sprint_constraints=constraints,
    )
    assert out_t == ()


def test_routing_excludes_promotion_grade_preset() -> None:
    """Any preset not in the plan is dropped — promotion_grade by example."""
    constraints = _make_constraints(("trend_pullback_crypto_1h",))
    templates = (
        _Stub("trend_equities_4h_baseline"),  # promotion_grade
        _Stub("trend_pullback_crypto_1h"),
    )
    out_t, _, _, _ = ds.apply_sprint_routing(
        templates=templates,
        follow_up_specs=(),
        weekly_control_specs=(),
        sprint_constraints=constraints,
    )
    assert {t.preset_name for t in out_t} == {"trend_pullback_crypto_1h"}


def test_routing_filters_followups_and_controls() -> None:
    constraints = _make_constraints(("p_keep",))
    follow_ups = (_Stub("p_keep"), _Stub("p_drop"))
    controls = (_Stub("p_drop"), _Stub("p_keep"))
    _, out_f, out_c, counts = ds.apply_sprint_routing(
        templates=(),
        follow_up_specs=follow_ups,
        weekly_control_specs=controls,
        sprint_constraints=constraints,
    )
    assert {s.preset_name for s in out_f} == {"p_keep"}
    assert {s.preset_name for s in out_c} == {"p_keep"}
    assert counts["follow_ups_filtered"] == 1
    assert counts["controls_filtered"] == 1


# ---------------------------------------------------------------------------
# Routing decision sidecar
# ---------------------------------------------------------------------------


def test_routing_decision_payload_records_active_sprint() -> None:
    constraints = _make_constraints(("p1", "p2"))
    payload = ds.build_routing_decision_payload(
        sprint_constraints=constraints,
        counts={
            "templates_total": 5,
            "templates_filtered": 2,
            "follow_ups_total": 3,
            "follow_ups_filtered": 1,
            "controls_total": 1,
            "controls_filtered": 0,
        },
        decision_action="spawn",
        decision_preset_name="p1",
        decision_template_id="daily_primary__p1",
        decision_reason="cron_tick",
        now_utc=datetime.now(UTC),
        git_revision="abc1234",
    )
    assert payload["routing_active"] is True
    assert payload["sprint"]["sprint_id"] == "sprt-test"
    assert payload["sprint"]["profile_name"] == "crypto_exploratory_v1"
    assert payload["counts"]["templates_filtered"] == 2
    assert payload["decision"]["action"] == "spawn"
    assert payload["decision"]["preset_name"] == "p1"
    assert payload["live_eligible"] is False  # standard COL pin block


def test_routing_decision_payload_when_inactive() -> None:
    payload = ds.build_routing_decision_payload(
        sprint_constraints=None,
        counts={
            "templates_total": 5,
            "templates_filtered": 5,
            "follow_ups_total": 0,
            "follow_ups_filtered": 0,
            "controls_total": 0,
            "controls_filtered": 0,
        },
        decision_action="idle_noop",
        decision_preset_name=None,
        decision_template_id=None,
        decision_reason="no_candidates",
        now_utc=datetime.now(UTC),
        git_revision=None,
    )
    assert payload["routing_active"] is False
    assert payload["sprint"] is None


def test_routing_decision_artifact_writes_atomically(
    sprint_paths: dict,
) -> None:
    payload = {
        "schema_version": "1.0",
        "routing_active": True,
        "sprint": {"sprint_id": "sprt-x"},
    }
    ds.write_routing_decision_artifact(payload)
    assert sprint_paths["routing"].exists()
    on_disk = json.loads(sprint_paths["routing"].read_text(encoding="utf-8"))
    assert on_disk["sprint"]["sprint_id"] == "sprt-x"


# ---------------------------------------------------------------------------
# sprint_extra_for_record
# ---------------------------------------------------------------------------


def test_sprint_extra_for_record_empty_when_no_sprint() -> None:
    assert ds.sprint_extra_for_record(None) == {}


def test_sprint_extra_for_record_carries_id_and_profile() -> None:
    constraints = _make_constraints(("p1",))
    extra = ds.sprint_extra_for_record(constraints)
    assert extra == {
        "sprint_id": "sprt-test",
        "sprint_profile_name": "crypto_exploratory_v1",
        "sprint_routing": "v3.15.14",
    }


# ---------------------------------------------------------------------------
# Launcher integration — captured-args double around decide()
# ---------------------------------------------------------------------------


@pytest.fixture
def launcher_isolation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sprint_paths: dict,
) -> dict:
    """Redirect every COL artifact path used by the launcher to tmp_path
    so a tick can be exercised without touching the production tree."""
    from research import campaign_launcher as cl
    from research import campaign_registry as cr
    from research import campaign_queue as cq

    research_dir = tmp_path / "research"
    research_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(
        cr,
        "REGISTRY_ARTIFACT_PATH",
        research_dir / "campaign_registry_latest.v1.json",
        raising=True,
    )
    monkeypatch.setattr(
        cl,
        "REGISTRY_ARTIFACT_PATH",
        research_dir / "campaign_registry_latest.v1.json",
        raising=True,
    )
    monkeypatch.setattr(
        cq,
        "QUEUE_ARTIFACT_PATH",
        research_dir / "campaign_queue_latest.v1.json",
        raising=True,
    )
    monkeypatch.setattr(
        cl,
        "EVIDENCE_LEDGER_PATH",
        research_dir / "campaign_evidence_ledger_latest.v1.jsonl",
        raising=True,
    )
    monkeypatch.setattr(
        cl,
        "EVIDENCE_META_PATH",
        research_dir / "campaign_evidence_ledger_latest.v1.meta.json",
        raising=True,
    )
    monkeypatch.setattr(
        cl,
        "TEMPLATES_ARTIFACT_PATH",
        research_dir / "campaign_templates_latest.v1.json",
        raising=True,
    )
    return {"research_dir": research_dir}


def test_launcher_tick_passthrough_when_no_active_sprint(
    sprint_paths: dict,
    launcher_isolation: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No active sprint → templates passed to decide() unchanged."""
    from research import campaign_launcher as cl
    from research.campaign_templates import CAMPAIGN_TEMPLATES

    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        from research.campaign_policy import (
            CampaignDecision,
            DecisionRecord,
        )

        return CampaignDecision(
            decision=DecisionRecord(action="idle_noop", reason="no_candidates"),
            rules_evaluated=(),
            candidates_considered=(),
            tie_break_key=(),
        )

    monkeypatch.setattr(cl, "decide", _capture, raising=True)

    # Rather than invoke main(), call _tick directly with synthetic args.
    monkeypatch.setattr(cl, "_apply_decision", lambda **kw: ({}, {}, []))
    monkeypatch.setattr(cl, "write_decision", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_record_digest", lambda **k: None)
    monkeypatch.setattr(
        cl, "assert_invariants", lambda **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_preset_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_family_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(cl, "write_registry", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_queue", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_budget", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_apply_funnel_decisions", lambda **k: ())
    monkeypatch.setattr(cl, "_write_ledger", lambda *a, **k: None)

    cl._tick(
        now_utc=datetime.now(UTC),
        git_rev=None,
        templates=CAMPAIGN_TEMPLATES,
        config=cl.DEFAULT_CONFIG,
        dry_run=False,
        skip_subprocess=True,
    )

    # decide() received the full template catalog (passthrough).
    assert "templates" in captured
    assert len(captured["templates"]) == len(CAMPAIGN_TEMPLATES)


def test_launcher_tick_filters_templates_when_sprint_active(
    sprint_paths: dict,
    launcher_isolation: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active sprint → only sprint-plan templates reach decide()."""
    from research import campaign_launcher as cl
    from research.campaign_templates import CAMPAIGN_TEMPLATES

    _start_active_sprint(sprint_paths)

    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        from research.campaign_policy import (
            CampaignDecision,
            DecisionRecord,
        )

        return CampaignDecision(
            decision=DecisionRecord(action="idle_noop", reason="no_candidates"),
            rules_evaluated=(),
            candidates_considered=(),
            tie_break_key=(),
        )

    monkeypatch.setattr(cl, "decide", _capture, raising=True)
    monkeypatch.setattr(cl, "_apply_decision", lambda **kw: ({}, {}, []))
    monkeypatch.setattr(cl, "write_decision", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_record_digest", lambda **k: None)
    monkeypatch.setattr(
        cl, "assert_invariants", lambda **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_preset_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_family_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(cl, "write_registry", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_queue", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_budget", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_apply_funnel_decisions", lambda **k: ())
    monkeypatch.setattr(cl, "_write_ledger", lambda *a, **k: None)

    cl._tick(
        now_utc=datetime.now(UTC),
        git_rev=None,
        templates=CAMPAIGN_TEMPLATES,
        config=cl.DEFAULT_CONFIG,
        dry_run=False,
        skip_subprocess=True,
    )

    # Filtered templates: only sprint plan presets that ALSO have a
    # CAMPAIGN_TEMPLATES entry survive. v3.15.15 wires three
    # hypothesis-aware presets (trend_pullback_crypto_1h from v3.15.3,
    # plus vol_compression_breakout_crypto_1h and
    # vol_compression_breakout_crypto_4h from v3.15.15). The routing
    # helper drops every non-sprint preset (equities, diagnostic
    # crypto) and any sprint-plan preset that has no template yet
    # (none today, post v3.15.15).
    surviving_presets = {
        t.preset_name for t in captured["templates"]
    }
    assert "trend_pullback_crypto_1h" in surviving_presets
    assert "vol_compression_breakout_crypto_1h" in surviving_presets
    assert "vol_compression_breakout_crypto_4h" in surviving_presets
    # Equities and non-sprint crypto presets are excluded.
    assert "trend_equities_4h_baseline" not in surviving_presets
    assert "trend_regime_filtered_equities_4h" not in surviving_presets
    assert "crypto_diagnostic_1h" not in surviving_presets
    # Routing decision sidecar was written.
    assert sprint_paths["routing"].exists()
    routing = json.loads(
        sprint_paths["routing"].read_text(encoding="utf-8")
    )
    assert routing["routing_active"] is True
    assert routing["sprint"]["profile_name"] == "crypto_exploratory_v1"
    # Total templates pre-filter == full catalog (30 in v3.15.15);
    # post-filter == only the sprint-plan templates that have
    # CAMPAIGN_TEMPLATES entries (5 standard types × 3 wired sprint
    # presets = 15 in v3.15.15).
    assert routing["counts"]["templates_total"] == len(CAMPAIGN_TEMPLATES)
    assert routing["counts"]["templates_filtered"] == 15


def test_launcher_tick_no_routing_sidecar_when_no_active_sprint(
    sprint_paths: dict,
    launcher_isolation: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sprint → no sprint_routing_decision sidecar is written."""
    from research import campaign_launcher as cl
    from research.campaign_templates import CAMPAIGN_TEMPLATES
    from research.campaign_policy import (
        CampaignDecision,
        DecisionRecord,
    )

    monkeypatch.setattr(
        cl,
        "decide",
        lambda **kw: CampaignDecision(
            decision=DecisionRecord(action="idle_noop", reason="no_candidates"),
            rules_evaluated=(),
            candidates_considered=(),
            tie_break_key=(),
        ),
        raising=True,
    )
    monkeypatch.setattr(cl, "_apply_decision", lambda **kw: ({}, {}, []))
    monkeypatch.setattr(cl, "write_decision", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_record_digest", lambda **k: None)
    monkeypatch.setattr(
        cl, "assert_invariants", lambda **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_preset_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_family_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(cl, "write_registry", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_queue", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_budget", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_apply_funnel_decisions", lambda **k: ())
    monkeypatch.setattr(cl, "_write_ledger", lambda *a, **k: None)

    cl._tick(
        now_utc=datetime.now(UTC),
        git_rev=None,
        templates=CAMPAIGN_TEMPLATES,
        config=cl.DEFAULT_CONFIG,
        dry_run=False,
        skip_subprocess=True,
    )

    assert not sprint_paths["routing"].exists()


def test_launcher_tick_routing_disengages_after_sprint_canceled(
    sprint_paths: dict,
    launcher_isolation: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the sprint registry transitions to canceled, the next
    launcher tick must hand decide() the full template catalog again."""
    from research import campaign_launcher as cl
    from research.campaign_templates import CAMPAIGN_TEMPLATES

    reg = _start_active_sprint(sprint_paths)
    reg["state"] = "canceled"
    sprint_paths["registry"].write_text(
        json.dumps(reg, sort_keys=True), encoding="utf-8"
    )

    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        from research.campaign_policy import (
            CampaignDecision,
            DecisionRecord,
        )

        return CampaignDecision(
            decision=DecisionRecord(action="idle_noop", reason="no_candidates"),
            rules_evaluated=(),
            candidates_considered=(),
            tie_break_key=(),
        )

    monkeypatch.setattr(cl, "decide", _capture, raising=True)
    monkeypatch.setattr(cl, "_apply_decision", lambda **kw: ({}, {}, []))
    monkeypatch.setattr(cl, "write_decision", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_record_digest", lambda **k: None)
    monkeypatch.setattr(
        cl, "assert_invariants", lambda **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_preset_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(
        cl, "write_family_policy", lambda *a, **k: None, raising=True
    )
    monkeypatch.setattr(cl, "write_registry", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_queue", lambda *a, **k: None)
    monkeypatch.setattr(cl, "write_budget", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_apply_funnel_decisions", lambda **k: ())
    monkeypatch.setattr(cl, "_write_ledger", lambda *a, **k: None)

    cl._tick(
        now_utc=datetime.now(UTC),
        git_rev=None,
        templates=CAMPAIGN_TEMPLATES,
        config=cl.DEFAULT_CONFIG,
        dry_run=False,
        skip_subprocess=True,
    )

    # Full catalog was passed through — routing disengaged.
    assert len(captured["templates"]) == len(CAMPAIGN_TEMPLATES)


# ---------------------------------------------------------------------------
# discovery_sprint status regression
# ---------------------------------------------------------------------------


def test_discovery_sprint_status_still_works_after_v3_15_14(
    sprint_paths: dict,
) -> None:
    _start_active_sprint(sprint_paths)
    buf = io.StringIO()
    rc = ds.cmd_status(out=buf)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["state"] == "active"
    assert payload["sprint_id"].startswith("sprt-")


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


def test_frozen_contracts_unchanged_by_routing_helpers(
    sprint_paths: dict,
) -> None:
    before = {
        str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS
    }
    # Exercise the new surface end-to-end.
    _start_active_sprint(sprint_paths)
    constraints = ds.load_active_sprint_constraints()
    assert constraints is not None
    out_t, out_f, out_c, counts = ds.apply_sprint_routing(
        templates=(),
        follow_up_specs=(),
        weekly_control_specs=(),
        sprint_constraints=constraints,
    )
    payload = ds.build_routing_decision_payload(
        sprint_constraints=constraints,
        counts=counts,
        decision_action="idle_noop",
        decision_preset_name=None,
        decision_template_id=None,
        decision_reason="no_candidates",
        now_utc=datetime.now(UTC),
        git_revision=None,
    )
    ds.write_routing_decision_artifact(payload)
    after = {
        str(p): _hash_or_missing(p) for p in _FROZEN_CONTRACTS
    }
    assert before == after
