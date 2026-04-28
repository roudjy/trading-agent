"""Dashboard API blueprint for read-only observability artifact exposure.

Twelve GET-only passthroughs feeding the QRE Control Room v3.15.15.3
frontend integration. Each endpoint reads exactly ONE artifact under
``research/observability/`` and returns:

    {
      "available": bool,
      "component": "<canonical name>",
      "artifact_name": "<filename>",
      "artifact_path": "research/observability/<filename>",
      "modified_at_unix": float | null,
      "size_bytes": int | null,
      "payload": <artifact JSON> | null,
      "state": "valid" | "absent" | "empty" | "invalid_json" | "unreadable",
      "error": str | null
    }

Plus one index endpoint at ``/api/observability/index``.

Hard guarantees:

* GET-only;
* imports only stdlib + flask + ``research.diagnostics.paths`` (the
  read-only single-source-of-truth for path constants);
* never imports campaign launcher / policy / queue / sprint
  orchestrator / screening runtime / strategy modules — verified by
  ``tests/unit/test_dashboard_api_observability.py``;
* never opens, parses, or mutates any artifact outside
  ``research/observability/`` (the diagnostic artifacts already
  reflect upstream state);
* returns ``available=false`` rather than raising when an artifact is
  missing or malformed, so the frontend renders an EmptyStatePanel
  instead of crashing.

Wire-up::

    from dashboard.api_observability import register_observability_routes
    register_observability_routes(app)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from flask import Flask, jsonify

from research.diagnostics.paths import (
    ARTIFACT_HEALTH_PATH,
    DEFERRED_COMPONENTS,
    FAILURE_MODES_PATH,
    OBSERVABILITY_DIR,
    OBSERVABILITY_SUMMARY_PATH,
    SYSTEM_INTEGRITY_PATH,
    THROUGHPUT_METRICS_PATH,
)

ReadState = Literal["valid", "absent", "empty", "invalid_json", "unreadable"]


def _read_artifact(path: Path) -> tuple[ReadState, Any | None, str | None, int | None, float | None]:
    """Passive read. Mirrors ``research.diagnostics.io.read_json_safe``
    semantics but is duplicated here so the dashboard blueprint does
    NOT import any aggregation/builder module — only path constants.
    """
    try:
        st = path.stat()
    except OSError:
        return "absent", None, None, None, None

    size_bytes = int(st.st_size)
    modified_at_unix = float(st.st_mtime)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "unreadable", None, str(exc), size_bytes, modified_at_unix

    if raw.strip() == "":
        return "empty", None, None, size_bytes, modified_at_unix

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return "invalid_json", None, str(exc), size_bytes, modified_at_unix

    return "valid", payload, None, size_bytes, modified_at_unix


def _component_response(
    *,
    component: str,
    artifact_name: str,
    artifact_path: Path,
) -> dict[str, Any]:
    """Build the standard component response envelope."""
    state, payload, error, size_bytes, modified_at_unix = _read_artifact(artifact_path)
    return {
        "available": state == "valid",
        "component": component,
        "artifact_name": artifact_name,
        "artifact_path": str(artifact_path).replace("\\", "/"),
        "state": state,
        "modified_at_unix": modified_at_unix,
        "size_bytes": size_bytes,
        "payload": payload,
        "error": error,
    }


def _deferred_response(component: str, slug: str) -> dict[str, Any]:
    """Stable shape for deferred components.

    The artifact will not exist until the v3.15.15.4 release ships
    the corresponding diagnostics module. Frontends render this as
    ``Unavailable — pending release`` per the brief.
    """
    return {
        "available": False,
        "component": component,
        "artifact_name": f"{component}_latest.v1.json",
        "artifact_path": f"research/observability/{component}_latest.v1.json",
        "state": "absent",
        "modified_at_unix": None,
        "size_bytes": None,
        "payload": None,
        "error": "deferred_to_v3_15_15_4",
        "slug": slug,
        "deferred": True,
    }


# Active components: real artifact paths. Order is stable; consumers
# can rely on it.
_ACTIVE_ENDPOINTS: tuple[tuple[str, str, str, Path], ...] = (
    ("artifact_health", "artifact-health", "artifact_health_latest.v1.json", ARTIFACT_HEALTH_PATH),
    ("failure_modes", "failure-modes", "failure_modes_latest.v1.json", FAILURE_MODES_PATH),
    ("throughput_metrics", "throughput", "throughput_metrics_latest.v1.json", THROUGHPUT_METRICS_PATH),
    ("system_integrity", "system-integrity", "system_integrity_latest.v1.json", SYSTEM_INTEGRITY_PATH),
    ("observability_summary", "summary", "observability_summary_latest.v1.json", OBSERVABILITY_SUMMARY_PATH),
)


def register_observability_routes(app: Flask) -> None:
    @app.route("/api/observability/summary", methods=["GET"])
    def _api_observability_summary():
        return jsonify(
            _component_response(
                component="observability_summary",
                artifact_name="observability_summary_latest.v1.json",
                artifact_path=OBSERVABILITY_SUMMARY_PATH,
            )
        )

    @app.route("/api/observability/artifact-health", methods=["GET"])
    def _api_observability_artifact_health():
        return jsonify(
            _component_response(
                component="artifact_health",
                artifact_name="artifact_health_latest.v1.json",
                artifact_path=ARTIFACT_HEALTH_PATH,
            )
        )

    @app.route("/api/observability/failure-modes", methods=["GET"])
    def _api_observability_failure_modes():
        return jsonify(
            _component_response(
                component="failure_modes",
                artifact_name="failure_modes_latest.v1.json",
                artifact_path=FAILURE_MODES_PATH,
            )
        )

    @app.route("/api/observability/throughput", methods=["GET"])
    def _api_observability_throughput():
        return jsonify(
            _component_response(
                component="throughput_metrics",
                artifact_name="throughput_metrics_latest.v1.json",
                artifact_path=THROUGHPUT_METRICS_PATH,
            )
        )

    @app.route("/api/observability/system-integrity", methods=["GET"])
    def _api_observability_system_integrity():
        return jsonify(
            _component_response(
                component="system_integrity",
                artifact_name="system_integrity_latest.v1.json",
                artifact_path=SYSTEM_INTEGRITY_PATH,
            )
        )

    # --- Deferred endpoints --------------------------------------------
    # Each returns ``available: false`` with the same envelope shape so
    # the frontend can render an "Unavailable — pending release" badge
    # without conditional logic at the consumer.

    @app.route("/api/observability/funnel", methods=["GET"])
    def _api_observability_funnel():
        return jsonify(_deferred_response("funnel_stage_summary", "funnel"))

    @app.route("/api/observability/campaign-timeline", methods=["GET"])
    def _api_observability_campaign_timeline():
        return jsonify(_deferred_response("campaign_timeline", "campaign-timeline"))

    @app.route("/api/observability/parameter-coverage", methods=["GET"])
    def _api_observability_parameter_coverage():
        return jsonify(_deferred_response("parameter_coverage", "parameter-coverage"))

    @app.route("/api/observability/data-freshness", methods=["GET"])
    def _api_observability_data_freshness():
        return jsonify(_deferred_response("data_freshness", "data-freshness"))

    @app.route("/api/observability/policy-trace", methods=["GET"])
    def _api_observability_policy_trace():
        return jsonify(_deferred_response("policy_decision_trace", "policy-trace"))

    @app.route("/api/observability/no-touch-health", methods=["GET"])
    def _api_observability_no_touch_health():
        return jsonify(_deferred_response("no_touch_health", "no-touch-health"))

    @app.route("/api/observability/index", methods=["GET"])
    def _api_observability_index():
        components: list[dict[str, Any]] = []
        for canonical, slug, filename, path in _ACTIVE_ENDPOINTS:
            try:
                st = path.stat()
                exists = True
                size_bytes: int | None = int(st.st_size)
                modified_at_unix: float | None = float(st.st_mtime)
            except OSError:
                exists = False
                size_bytes = None
                modified_at_unix = None
            components.append(
                {
                    "component": canonical,
                    "slug": slug,
                    "artifact_name": filename,
                    "artifact_path": str(path).replace("\\", "/"),
                    "exists": exists,
                    "size_bytes": size_bytes,
                    "modified_at_unix": modified_at_unix,
                    "deferred": False,
                }
            )
        for canonical, slug in DEFERRED_COMPONENTS:
            components.append(
                {
                    "component": canonical,
                    "slug": slug,
                    "artifact_name": f"{canonical}_latest.v1.json",
                    "artifact_path": str(
                        OBSERVABILITY_DIR / f"{canonical}_latest.v1.json"
                    ).replace("\\", "/"),
                    "exists": False,
                    "size_bytes": None,
                    "modified_at_unix": None,
                    "deferred": True,
                }
            )
        components.sort(key=lambda c: (c["deferred"], c["component"]))
        return jsonify(
            {
                "observability_dir": str(OBSERVABILITY_DIR).replace("\\", "/"),
                "components": components,
                "active_count": len(_ACTIVE_ENDPOINTS),
                "deferred_count": len(DEFERRED_COMPONENTS),
            }
        )


__all__ = ["register_observability_routes"]
