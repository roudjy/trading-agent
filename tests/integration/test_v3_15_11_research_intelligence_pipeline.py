"""v3.15.11 — research intelligence layer integration tests.

Lifecycle hook in run_research.py writes 5 advisory sidecars after
the v3.15.9 screening_evidence is on disk. These tests exercise the
public ``write_*_artifact`` entry points in the deterministic order
the hook calls them, against an isolated workspace.

Scope: this is a *wiring* integration test — it confirms that the
five modules compose correctly, produce JSON-valid artifacts under
the expected directory, and respect the advisory-only contract.
The end-to-end run_research smoke is verified separately in
Phase 9.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from research import campaign_policy
from research.dead_zone_detection import (
    DEAD_ZONES_SCHEMA_VERSION,
    write_dead_zones_artifact,
)
from research.information_gain import (
    INFORMATION_GAIN_SCHEMA_VERSION,
    InformationGainInputs,
    write_information_gain_artifact,
)
from research.research_evidence_ledger import (
    EVIDENCE_LEDGER_SCHEMA_VERSION,
    write_research_evidence_artifact,
)
from research.stop_condition_engine import (
    ENFORCEMENT_STATE_ADVISORY,
    STOP_CONDITIONS_SCHEMA_VERSION,
    write_stop_conditions_artifact,
)
from research.viability_metrics import (
    VIABILITY_SCHEMA_VERSION,
    write_viability_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _ledger_event(
    *,
    campaign_id: str,
    outcome: str,
    reason: str = "none",
    meaningful: str | None = None,
    asset: str = "crypto",
    family: str = "trend_pullback",
    preset: str = "trend_pullback_crypto_1h",
    run_id: str = "run_a",
    at_utc: str = "2026-04-27T11:00:00+00:00",
) -> dict[str, Any]:
    return {
        "event_id": f"id-{campaign_id}",
        "campaign_id": campaign_id,
        "parent_campaign_id": None,
        "lineage_root_campaign_id": campaign_id,
        "preset_name": preset,
        "strategy_family": family,
        "asset_class": asset,
        "campaign_type": "discovery",
        "event_type": "campaign_completed",
        "reason_code": reason,
        "outcome": outcome,
        "meaningful_classification": meaningful,
        "run_id": run_id,
        "source_artifact": None,
        "at_utc": at_utc,
        "extra": {},
    }


def _setup_workspace(tmp_path: Path, events: list[dict[str, Any]]) -> dict[str, Path]:
    """Lay out the research/ subset the lifecycle hook reads."""
    base = tmp_path / "research"
    (base / "campaigns" / "evidence").mkdir(parents=True, exist_ok=True)
    jsonl = base / "campaign_evidence_ledger.jsonl"
    with jsonl.open("w", encoding="utf-8", newline="\n") as h:
        for ev in events:
            h.write(json.dumps(ev, sort_keys=True))
            h.write("\n")
    return {
        "base": base,
        "ledger_jsonl": jsonl,
        "evidence_ledger": base / "campaigns" / "evidence" / "evidence_ledger.json",
        "information_gain": base / "campaigns" / "evidence" / "information_gain.json",
        "stop_conditions": base / "campaigns" / "evidence" / "stop_conditions.json",
        "dead_zones": base / "campaigns" / "evidence" / "dead_zones.json",
        "viability": base / "campaigns" / "evidence" / "viability.json",
    }


def _run_intelligence_pipeline(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Invoke the same write order the lifecycle hook uses."""
    evidence_payload = write_research_evidence_artifact(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision="abc",
        output_path=paths["evidence_ledger"],
        campaign_event_ledger_path=paths["ledger_jsonl"],
        campaign_registry_path=paths["base"] / "missing_registry.json",
        screening_evidence_path=paths["base"] / "missing_screening.json",
        candidate_registry_path=paths["base"] / "missing_candidates.json",
    )
    ig_payload = write_information_gain_artifact(
        run_id="run_a",
        col_campaign_id=None,
        preset_name="trend_pullback_crypto_1h",
        hypothesis_id=None,
        as_of_utc=_AS_OF,
        git_revision="abc",
        inputs=InformationGainInputs(),
        output_path=paths["information_gain"],
    )
    stop_payload = write_stop_conditions_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        evidence_ledger=evidence_payload,
        output_path=paths["stop_conditions"],
    )
    from research.campaign_evidence_ledger import load_events
    raw_events = load_events(paths["ledger_jsonl"])
    dz_payload = write_dead_zones_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        events=raw_events,
        output_path=paths["dead_zones"],
    )
    via_payload = write_viability_artifact(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision="abc",
        evidence_ledger=evidence_payload,
        dead_zones=dz_payload["zones"],
        output_path=paths["viability"],
    )
    return {
        "evidence_ledger": evidence_payload,
        "information_gain": ig_payload,
        "stop_conditions": stop_payload,
        "dead_zones": dz_payload,
        "viability": via_payload,
    }


def test_all_five_artifacts_written_for_completed_campaign(tmp_path: Path) -> None:
    events = [
        _ledger_event(
            campaign_id="c1",
            outcome="completed_with_candidates",
            meaningful="exploratory_pass",
        )
    ]
    paths = _setup_workspace(tmp_path, events)
    payloads = _run_intelligence_pipeline(paths)
    for name, p in (
        ("evidence_ledger", paths["evidence_ledger"]),
        ("information_gain", paths["information_gain"]),
        ("stop_conditions", paths["stop_conditions"]),
        ("dead_zones", paths["dead_zones"]),
        ("viability", paths["viability"]),
    ):
        assert p.exists(), f"{name} artifact missing: {p}"
    assert payloads["evidence_ledger"]["schema_version"] == EVIDENCE_LEDGER_SCHEMA_VERSION
    assert payloads["information_gain"]["schema_version"] == INFORMATION_GAIN_SCHEMA_VERSION
    assert payloads["stop_conditions"]["schema_version"] == STOP_CONDITIONS_SCHEMA_VERSION
    assert payloads["dead_zones"]["schema_version"] == DEAD_ZONES_SCHEMA_VERSION
    assert payloads["viability"]["schema_version"] == VIABILITY_SCHEMA_VERSION


def test_degenerate_outcome_not_classified_as_technical_failure(
    tmp_path: Path,
) -> None:
    events = [
        _ledger_event(
            campaign_id=f"c{i}",
            outcome="degenerate_no_survivors",
            run_id=f"r{i}",
        )
        for i in range(5)
    ]
    paths = _setup_workspace(tmp_path, events)
    payloads = _run_intelligence_pipeline(paths)
    hyp_row = payloads["evidence_ledger"]["hypothesis_evidence"][0]
    assert hyp_row["degenerate_count"] == 5
    assert hyp_row["technical_failure_count"] == 0


def test_technical_failure_does_not_recommend_retire(tmp_path: Path) -> None:
    events = [
        _ledger_event(
            campaign_id=f"c{i}",
            outcome="technical_failure",
            run_id=f"r{i}",
        )
        for i in range(10)  # well above retire threshold
    ]
    paths = _setup_workspace(tmp_path, events)
    payloads = _run_intelligence_pipeline(paths)
    decisions = payloads["stop_conditions"]["decisions"]
    kinds = {d["recommended_decision"] for d in decisions}
    assert "REVIEW_REQUIRED" in kinds
    assert "RETIRE_HYPOTHESIS" not in kinds
    assert "RETIRE_FAMILY" not in kinds
    for d in decisions:
        assert d["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY


def test_missing_optional_artifacts_yield_valid_payloads(tmp_path: Path) -> None:
    paths = _setup_workspace(tmp_path, events=[])
    payloads = _run_intelligence_pipeline(paths)
    assert payloads["evidence_ledger"]["hypothesis_evidence"] == []
    assert payloads["dead_zones"]["zones"] == []
    assert payloads["viability"]["verdict"]["status"] == "insufficient_data"


def test_lifecycle_hook_does_not_mutate_campaign_policy_module() -> None:
    """Regression: importing the intelligence layer must not patch policy."""
    import inspect

    sig_before = inspect.signature(campaign_policy.decide)
    # Re-import the lifecycle wiring; this is the import sequence
    # run_research.py executes when it loads. If any of the new
    # modules monkey-patches campaign_policy.decide, the signature
    # would change.
    import importlib

    importlib.import_module("research.research_evidence_ledger")
    importlib.import_module("research.information_gain")
    importlib.import_module("research.stop_condition_engine")
    importlib.import_module("research.dead_zone_detection")
    importlib.import_module("research.viability_metrics")
    sig_after = inspect.signature(campaign_policy.decide)
    assert sig_before == sig_after


def test_run_research_imports_intelligence_layer_modules() -> None:
    """Regression: lifecycle wiring is present in run_research.py."""
    import research.run_research as rr

    assert hasattr(rr, "write_research_evidence_artifact")
    assert hasattr(rr, "write_information_gain_artifact")
    assert hasattr(rr, "write_stop_conditions_artifact")
    assert hasattr(rr, "write_dead_zones_artifact")
    assert hasattr(rr, "write_viability_artifact")
    assert hasattr(rr, "InformationGainInputs")


def test_advisory_decisions_carry_recommended_decision_field(tmp_path: Path) -> None:
    events = [
        _ledger_event(
            campaign_id=f"c{i}",
            outcome="research_rejection",
            reason="screening_criteria_not_met",
            run_id=f"r{i}",
        )
        for i in range(6)  # above freeze threshold
    ]
    paths = _setup_workspace(tmp_path, events)
    payloads = _run_intelligence_pipeline(paths)
    stop = payloads["stop_conditions"]
    assert stop["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
    for d in stop["decisions"]:
        assert "recommended_decision" in d
        assert "decision" not in d
        assert d["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
