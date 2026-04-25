"""Dashboard API blueprint for the v3.15.2 Campaign Operating Layer.

Five read-only endpoints, each returning the corresponding COL artifact
as JSON. Zero business logic in the API layer — the artifacts already
carry the full pin block, state, and decisions, so the API is a straight
passthrough.

Wire-up:
    from dashboard.api_campaigns import register_campaign_routes
    register_campaign_routes(app)

Absent artifacts (e.g. before the first launcher tick ever runs) return
an empty-but-valid structure so the frontend card degrades gracefully
instead of throwing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from research.campaign_budget import BUDGET_ARTIFACT_PATH
from research.campaign_digest import DIGEST_ARTIFACT_PATH
from research.campaign_family_policy import FAMILY_POLICY_ARTIFACT_PATH
from research.campaign_policy import POLICY_DECISION_PATH
from research.campaign_preset_policy import PRESET_POLICY_ARTIFACT_PATH
from research.campaign_queue import QUEUE_ARTIFACT_PATH
from research.campaign_registry import REGISTRY_ARTIFACT_PATH

EVIDENCE_LEDGER_PATH = Path(
    "research/campaign_evidence_ledger_latest.v1.jsonl"
)
TEMPLATES_ARTIFACT_PATH = Path(
    "research/campaign_templates_latest.v1.json"
)

_DEFAULT_EVIDENCE_LIMIT = 50
_MAX_EVIDENCE_LIMIT = 500


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_jsonl_tail(
    path: Path,
    *,
    limit: int,
    preset_filter: str | None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if preset_filter and event.get("preset_name") != preset_filter:
                continue
            events.append(event)
    return events[-limit:]


def register_campaign_routes(app: Flask) -> None:
    @app.route("/api/campaigns/registry")
    def _api_campaigns_registry():
        return jsonify(
            _read_json(REGISTRY_ARTIFACT_PATH, {"campaigns": {}})
        )

    @app.route("/api/campaigns/queue")
    def _api_campaigns_queue():
        return jsonify(_read_json(QUEUE_ARTIFACT_PATH, {"queue": []}))

    @app.route("/api/campaigns/digest")
    def _api_campaigns_digest():
        return jsonify(_read_json(DIGEST_ARTIFACT_PATH, {}))

    @app.route("/api/campaigns/budget")
    def _api_campaigns_budget():
        return jsonify(_read_json(BUDGET_ARTIFACT_PATH, {}))

    @app.route("/api/campaigns/templates")
    def _api_campaigns_templates():
        return jsonify(
            _read_json(TEMPLATES_ARTIFACT_PATH, {"templates": []})
        )

    @app.route("/api/campaigns/policy/latest")
    def _api_campaigns_policy_latest():
        return jsonify(_read_json(POLICY_DECISION_PATH, {}))

    @app.route("/api/campaigns/preset-state")
    def _api_campaigns_preset_state():
        return jsonify(
            _read_json(PRESET_POLICY_ARTIFACT_PATH, {"presets": {}})
        )

    @app.route("/api/campaigns/family-state")
    def _api_campaigns_family_state():
        return jsonify(
            _read_json(FAMILY_POLICY_ARTIFACT_PATH, {"families": {}})
        )

    @app.route("/api/campaigns/evidence")
    def _api_campaigns_evidence():
        preset_filter = request.args.get("preset")
        try:
            limit = int(request.args.get("limit") or _DEFAULT_EVIDENCE_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_EVIDENCE_LIMIT
        limit = max(1, min(int(limit), _MAX_EVIDENCE_LIMIT))
        events = _read_jsonl_tail(
            EVIDENCE_LEDGER_PATH,
            limit=limit,
            preset_filter=preset_filter,
        )
        return jsonify(
            {
                "events": events,
                "count": len(events),
                "preset_filter": preset_filter,
                "limit": limit,
            }
        )


__all__ = ["register_campaign_routes"]
