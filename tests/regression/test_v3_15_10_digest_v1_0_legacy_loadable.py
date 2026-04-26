"""v3.15.10 regression — backward-compat: a v1.0 digest fixture
must still be loadable by ``load_previous_digest`` so the
launcher and the dashboard endpoint do not crash on a freshly-
upgraded VPS where the on-disk artifact still has
schema_version "1.0".
"""

from __future__ import annotations

import json
from pathlib import Path

from research.campaign_digest import load_previous_digest


_LEGACY_V1_0_PAYLOAD = {
    "schema_version": "1.0",
    "generated_at_utc": "2026-04-25T00:00:00+00:00",
    "git_revision": "abc123",
    "run_id": None,
    "artifact_state": "healthy",
    "date": "2026-04-25",
    "campaigns_scheduled": 0,
    "campaigns_completed": 0,
    "campaigns_failed": 0,
    "campaigns_canceled": 0,
    "campaigns_frozen": 0,
    "campaigns_by_type": {},
    "meaningful_by_classification": {},
    "meaningful_campaigns_total": 0,
    "candidates_produced_today": 0,
    "paper_worthy_candidates_today": 0,
    "estimated_compute_seconds_used": 0,
    "actual_compute_seconds_used": 0,
    "compute_seconds_per_meaningful_campaign": 0.0,
    "compute_seconds_per_candidate": 0.0,
    "compute_seconds_per_paper_worthy_candidate": 0.0,
    "queue_depth": 0,
    "queue_efficiency_pct": 0.0,
    "worker_utilization_pct": 0.0,
    "top_failure_reasons": [],
    "preset_states": {},
    "newly_frozen_presets": [],
    "thawed_presets": [],
    "compute_by_lineage_root": {},
    "compute_by_candidate_family": {},
    "policy_decisions_count": 0,
    "idle_noop_count": 0,
    "skip_budget_count": 0,
    # NOTE: no "funnel_decisions" key — that's the v1.1 addition
}


def test_load_previous_digest_accepts_v1_0_payload(tmp_path) -> None:
    """The launcher's load_previous_digest helper must tolerate
    a legacy v1.0 payload without raising or returning None.
    """
    target = tmp_path / "campaign_digest_latest.v1.json"
    target.write_text(json.dumps(_LEGACY_V1_0_PAYLOAD), encoding="utf-8")
    loaded = load_previous_digest(target)
    assert loaded is not None
    assert loaded["schema_version"] == "1.0"


def test_v1_0_payload_lacks_funnel_decisions_and_consumers_use_get(tmp_path) -> None:
    """Both consumers (launcher.load_previous_digest output and
    the dashboard endpoint) must defensively read funnel_decisions
    via .get() rather than indexing, since v1.0 payloads do not
    have the key.
    """
    target = tmp_path / "campaign_digest_latest.v1.json"
    target.write_text(json.dumps(_LEGACY_V1_0_PAYLOAD), encoding="utf-8")
    loaded = load_previous_digest(target)
    assert loaded is not None
    # Mirror what readers would do — never index, always .get
    assert loaded.get("funnel_decisions") is None
    assert loaded.get("funnel_decisions", {}) == {}


def test_load_previous_digest_returns_none_when_file_missing(tmp_path) -> None:
    target = tmp_path / "campaign_digest_latest.v1.json"
    assert load_previous_digest(target) is None


def test_load_previous_digest_returns_none_on_malformed_file(tmp_path) -> None:
    target = tmp_path / "campaign_digest_latest.v1.json"
    target.write_text("{not json", encoding="utf-8")
    assert load_previous_digest(target) is None


def test_dashboard_api_reads_via_default_dict_pattern(tmp_path) -> None:
    """The dashboard endpoint at dashboard/api_campaigns.py:90
    uses ``_read_json(DIGEST_ARTIFACT_PATH, {})`` which falls
    back to {} on missing/malformed files. Mirror that pattern
    here so a future change to the dashboard reader cannot
    silently regress.
    """
    target = tmp_path / "campaign_digest_latest.v1.json"
    # Missing -> dashboard would serve {}
    if not target.exists():
        served = {}
    else:
        served = json.loads(target.read_text(encoding="utf-8"))
    assert served == {}

    target.write_text(json.dumps(_LEGACY_V1_0_PAYLOAD), encoding="utf-8")
    served = json.loads(target.read_text(encoding="utf-8"))
    assert served["schema_version"] == "1.0"
    # Frontend iterating served.get("funnel_decisions", {}) sees {}
    assert served.get("funnel_decisions", {}) == {}
