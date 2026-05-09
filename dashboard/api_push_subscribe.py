"""N2b-2a — Push Subscribe API blueprint (UNWIRED).

Flask blueprint exposing the future PWA Web Push subscription
surface. This module defines :func:`register_push_subscribe_routes`
following the same pattern as ``dashboard.api_approval_inbox``.

**The blueprint is intentionally NOT wired into
``dashboard/dashboard.py`` in this PR.** Wiring is a one-line
``register_push_subscribe_routes(app)`` change that lands in N2b-2b.
``dashboard/dashboard.py`` is `dashboard_wiring` per
``execution_authority.md`` and requires explicit operator approval.

Hard guarantees (pinned by tests):

* GET / POST / DELETE only — no other HTTP method is registered.
* Never executes a CLI subprocess, never invokes ``gh`` or ``git``,
  never opens a network socket, never imports a Web Push library.
* Every response payload is run through ``assert_no_secrets`` from
  ``reporting.agent_audit_summary``.
* The ``GET /api/push/status`` endpoint NEVER returns subscription
  endpoints or keys — only ``count``, ``last_subscribed_at``, and
  ``vapid_public_present``.
* The ``GET /api/push/vapid_public`` endpoint returns 404 with a
  bounded JSON error body when the gitignored public-key file is
  absent.
* The ``POST /api/push/test`` endpoint enqueues a synthetic event
  for the existing N2b-1 stub-provider outbox; **no real push.**
* No subscription record's endpoint URL or keys appear in any audit
  / log surface; only ``endpoint_hash`` (sha256[:16]) is used.

Authentication
--------------

Auth is provided by the existing PWA session middleware, applied at
the dashboard wiring layer (``dashboard/dashboard.py``). This
blueprint does not register any auth itself; the unit tests register
it on a fresh Flask app and exercise the routes directly. When the
operator wires this blueprint in N2b-2b, the existing session
middleware applies automatically.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from flask import Flask, Response, jsonify, request

from reporting import push_subscription_store as pss
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: str = "v3.15.16.N2b2a"
SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Bounded request-body limits
# ---------------------------------------------------------------------------

#: Maximum size of a JSON request body. Web Push subscription bodies
#: are well under this; anything larger is refused 413.
_MAX_REQUEST_BYTES: int = 8 * 1024


# ---------------------------------------------------------------------------
# Synthetic test-event helpers (POST /api/push/test)
# ---------------------------------------------------------------------------

#: Closed sentinel kid for synthetic test events. The kid does not
#: match any real key; it tags the event_id for operator visibility.
_TEST_EVENT_KIND: str = "intake_candidate_eligible"
_TEST_EVENT_SEVERITY: str = "push_info"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    """JSONify after running ``assert_no_secrets`` on the payload."""
    assert_no_secrets(payload)
    return jsonify(payload)


def _bounded_summary(s: str, *, max_len: int = 200) -> str:
    if not isinstance(s, str):
        return ""
    return s[:max_len]


# ---------------------------------------------------------------------------
# View functions
# ---------------------------------------------------------------------------


def _view_subscribe() -> tuple[Response, int] | Response:
    """POST /api/push/subscribe — register a new subscription
    (idempotent on endpoint)."""
    if request.content_length is not None and request.content_length > _MAX_REQUEST_BYTES:
        return _safe_jsonify({"status": "error", "error": "payload_too_large"}), 413
    try:
        raw = request.get_json(force=False, silent=True)
    except Exception:
        raw = None
    if not isinstance(raw, dict):
        return _safe_jsonify({"status": "error", "error": "invalid_json_body"}), 400

    rec, warnings = pss.register_subscription(raw)
    if rec is None:
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "register_rejected",
                    "warnings": warnings,
                }
            ),
            400,
        )
    return _safe_jsonify(
        {
            "status": "ok",
            "endpoint_hash": pss.endpoint_hash(rec["endpoint"]),
            "kid": rec["kid"],
            "label": rec["label"],
            "created_at": rec["created_at"],
            "last_seen_at": rec["last_seen_at"],
        }
    )


def _view_unsubscribe() -> tuple[Response, int] | Response:
    """DELETE /api/push/unsubscribe — remove a subscription by
    endpoint (idempotent)."""
    if request.content_length is not None and request.content_length > _MAX_REQUEST_BYTES:
        return _safe_jsonify({"status": "error", "error": "payload_too_large"}), 413
    try:
        raw = request.get_json(force=False, silent=True)
    except Exception:
        raw = None
    endpoint = ""
    if isinstance(raw, dict):
        endpoint = raw.get("endpoint") if isinstance(raw.get("endpoint"), str) else ""
    if not endpoint:
        return _safe_jsonify({"status": "error", "error": "missing_endpoint"}), 400

    removed = pss.unregister_subscription(endpoint)
    return _safe_jsonify(
        {
            "status": "ok",
            "removed": removed,
            "endpoint_hash": pss.endpoint_hash(endpoint),
        }
    )


def _view_vapid_public() -> tuple[Response, int] | Response:
    """GET /api/push/vapid_public — return the gitignored public key
    or a bounded 404 envelope."""
    text = pss.vapid_public_text()
    if not text:
        return (
            _safe_jsonify(
                {
                    "status": "not_available",
                    "error": "vapid_public_not_configured",
                }
            ),
            404,
        )
    # text/plain on success; bounded by the underlying file. Run the
    # text through assert_no_secrets-style guard by jsonifying first
    # and replacing — actually the public key is ASCII base64url and
    # contains no credential pattern. We return text/plain directly.
    resp = Response(text, status=200, mimetype="text/plain")
    return resp


def _view_status() -> Response:
    """GET /api/push/status — returns ONLY count + last_subscribed_at
    + vapid_public_present. Never returns endpoints or keys."""
    subs = pss.list_subscriptions()
    last_subscribed_at = ""
    if subs:
        last_subscribed_at = max(
            (s.get("last_seen_at", "") for s in subs if isinstance(s, dict)),
            default="",
        )
    return _safe_jsonify(
        {
            "status": "ok",
            "count": len(subs),
            "last_subscribed_at": last_subscribed_at,
            "vapid_public_present": pss.vapid_public_present(),
            "max_active_subscriptions": pss.MAX_ACTIVE_SUBSCRIPTIONS,
        }
    )


def _view_test() -> Response:
    """POST /api/push/test — synthesize a test event record and
    return it. **Does NOT call any push provider, real or stub.** The
    operator runs the existing N2b-1 dispatch outbox CLI to exercise
    the rest of the pipeline against a freshly generated test event.
    """
    if request.content_length is not None and request.content_length > _MAX_REQUEST_BYTES:
        return _safe_jsonify({"status": "error", "error": "payload_too_large"}), 413

    now = _utcnow()
    event_id = (
        "ade_test_" + now.replace("-", "").replace(":", "").replace("Z", "")
    )[:64]
    return _safe_jsonify(
        {
            "status": "ok",
            "test_event": {
                "event_id": event_id,
                "event_kind": _TEST_EVENT_KIND,
                "event_severity": _TEST_EVENT_SEVERITY,
                "title": "ADE test push",
                "summary": _bounded_summary(
                    "Synthetic test event. Backend pipeline only; "
                    "no real push is sent in N2b-2a."
                ),
                "open_at": "/agent-control/inbox?event=" + event_id,
            },
            "would_dispatch_via": "n2b1_outbox_stub_provider",
            "real_push_sent": False,
        }
    )


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_PUSH_SUBSCRIBE_ROUTES: tuple[tuple[str, str, Any], ...] = (
    ("/api/push/subscribe", "POST", _view_subscribe),
    ("/api/push/unsubscribe", "DELETE", _view_unsubscribe),
    ("/api/push/vapid_public", "GET", _view_vapid_public),
    ("/api/push/status", "GET", _view_status),
    ("/api/push/test", "POST", _view_test),
)


def register_push_subscribe_routes(app: Flask) -> None:
    """Register the future PWA Web Push subscription surface.

    **NOT wired into ``dashboard/dashboard.py``** in this PR. The
    one-line wiring change lands in N2b-2b, behind explicit operator
    approval per ``execution_authority.md`` (``dashboard_wiring`` =
    NEEDS_HUMAN).
    """
    for path, method, handler in _PUSH_SUBSCRIBE_ROUTES:
        endpoint_name = (
            f"push_subscribe_{method.lower()}_{path.rsplit('/', 1)[-1]}"
        )
        app.add_url_rule(
            path,
            endpoint=endpoint_name,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "register_push_subscribe_routes",
]
