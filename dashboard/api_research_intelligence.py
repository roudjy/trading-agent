"""Dashboard API blueprint for the v3.15.11+ Research Intelligence Layer.

Six read-only sidecar passthroughs plus one combined summary. v3.15.12
adds /api/research/spawn-proposals (forward-looking advisory) and
extends the summary with proposal_mode + top-3 proposals + suppressed
zone count. Zero business logic in the API layer — every artifact
already carries its full deterministic content, so the API is a
straight passthrough that does not interpret advisory recommendations.

Wire-up:

    from dashboard.api_research_intelligence import (
        register_research_intelligence_routes,
    )
    register_research_intelligence_routes(app)

Absent artifacts (e.g. before the first run that wrote them on a
freshly-deployed VPS) return an empty-but-valid structure so the
frontend card degrades gracefully instead of throwing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from research.dead_zone_detection import DEAD_ZONES_PATH
from research.funnel_spawn_proposer import (
    MODE_SHADOW,
    PROPOSAL_MODE_NORMAL,
    SPAWN_PROPOSALS_PATH,
)
from research.information_gain import INFORMATION_GAIN_PATH
from research.research_evidence_ledger import EVIDENCE_LEDGER_PATH
from research.stop_condition_engine import (
    ENFORCEMENT_STATE_ADVISORY,
    STOP_CONDITIONS_PATH,
)
from research.viability_metrics import VIABILITY_PATH


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _empty_evidence_ledger() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "hypothesis_evidence": [],
        "failure_mode_counts": [],
        "candidate_lineage": [],
        "summary": {
            "campaign_count": 0,
            "hypothesis_count": 0,
            "failure_mode_count": 0,
            "candidate_lineage_count": 0,
        },
    }


def _empty_information_gain() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "information_gain": {
            "score": 0.0,
            "bucket": "none",
            "is_meaningful_campaign": False,
            "reasons": [],
        },
        "inputs": {},
    }


def _empty_stop_conditions() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "enforcement_state": ENFORCEMENT_STATE_ADVISORY,
        "decisions": [],
    }


def _empty_dead_zones() -> dict[str, Any]:
    return {"schema_version": "1.0", "zones": []}


def _empty_viability() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "metrics": {},
        "verdict": {
            "status": "insufficient_data",
            "reason_codes": ["fewer_than_minimum_campaigns"],
            "human_summary": "No data yet.",
        },
    }


def _empty_spawn_proposals() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "enforcement_state": ENFORCEMENT_STATE_ADVISORY,
        "mode": MODE_SHADOW,
        "proposal_mode": PROPOSAL_MODE_NORMAL,
        "summary": {
            "proposed_count": 0,
            "suppressed_zone_count": 0,
            "human_review_required": False,
            "exploration_coverage": {},
            "fingerprint_cooldown_blocks": 0,
        },
        "proposed_campaigns": [],
        "suppressed_zones": [],
        "exploration_reservation": {
            "pct_target": 0.20,
            "candidate_zones": [],
        },
        "human_review_required": {"active": False, "reason_codes": []},
    }


def register_research_intelligence_routes(app: Flask) -> None:
    @app.route("/api/research/evidence-ledger")
    def _api_research_evidence_ledger():
        return jsonify(_read_json(EVIDENCE_LEDGER_PATH, _empty_evidence_ledger()))

    @app.route("/api/research/information-gain")
    def _api_research_information_gain():
        return jsonify(
            _read_json(INFORMATION_GAIN_PATH, _empty_information_gain())
        )

    @app.route("/api/research/stop-conditions")
    def _api_research_stop_conditions():
        return jsonify(
            _read_json(STOP_CONDITIONS_PATH, _empty_stop_conditions())
        )

    @app.route("/api/research/dead-zones")
    def _api_research_dead_zones():
        return jsonify(_read_json(DEAD_ZONES_PATH, _empty_dead_zones()))

    @app.route("/api/research/viability")
    def _api_research_viability():
        return jsonify(_read_json(VIABILITY_PATH, _empty_viability()))

    @app.route("/api/research/spawn-proposals")
    def _api_research_spawn_proposals():
        return jsonify(
            _read_json(SPAWN_PROPOSALS_PATH, _empty_spawn_proposals())
        )

    @app.route("/api/research/intelligence-summary")
    def _api_research_intelligence_summary():
        """Convenience endpoint: top-level metrics for the dashboard card.

        Pure JSON-merge over the six sidecars — no derived logic. The
        frontend hits this single endpoint instead of six for the
        summary card (still receives advisory enforcement_state).
        v3.15.12 adds proposal_mode + top-3 proposals + suppressed
        zone count + human-review flag.
        """
        viability = _read_json(VIABILITY_PATH, _empty_viability())
        ig = _read_json(INFORMATION_GAIN_PATH, _empty_information_gain())
        stop = _read_json(STOP_CONDITIONS_PATH, _empty_stop_conditions())
        zones = _read_json(DEAD_ZONES_PATH, _empty_dead_zones())
        ledger = _read_json(EVIDENCE_LEDGER_PATH, _empty_evidence_ledger())
        spawn = _read_json(SPAWN_PROPOSALS_PATH, _empty_spawn_proposals())
        dead_zone_count = sum(
            1 for z in (zones.get("zones") or []) if z.get("zone_status") == "dead"
        )
        proposed = spawn.get("proposed_campaigns") or []
        top_proposals = [
            {
                "preset_name": p.get("preset_name"),
                "proposal_type": p.get("proposal_type"),
                "spawn_reason": p.get("spawn_reason"),
                "priority_tier": p.get("priority_tier"),
            }
            for p in proposed[:3]
        ]
        return jsonify(
            {
                "schema_version": "1.0",
                "enforcement_state": ENFORCEMENT_STATE_ADVISORY,
                "viability": viability.get("verdict") or {},
                "metrics": viability.get("metrics") or {},
                "information_gain": ig.get("information_gain") or {},
                "advisory_decision_count": len(stop.get("decisions") or []),
                "dead_zone_count": dead_zone_count,
                "ledger_summary": ledger.get("summary") or {},
                "spawn_proposals": {
                    "proposal_mode": spawn.get("proposal_mode"),
                    "proposed_count": len(proposed),
                    "suppressed_zone_count": len(
                        spawn.get("suppressed_zones") or []
                    ),
                    "human_review_required": (
                        spawn.get("human_review_required") or {}
                    ).get("active", False),
                    "top_proposals": top_proposals,
                },
            }
        )


__all__ = ["register_research_intelligence_routes"]
