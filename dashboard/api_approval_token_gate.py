"""N4b — Approval Token Gate API blueprint (session-protected, UNWIRED).

Session-protected Flask blueprint that exposes mint / verify / status
for the runtime approval-token gate. The blueprint is intentionally
**NOT wired into ``dashboard/dashboard.py``** in this PR; wiring is
the operator's two-line diff (per ``execution_authority.md``).

Hard guarantees (pinned by tests)
---------------------------------

* The blueprint registers exactly three routes:

    POST /api/agent-control/approval-token/mint
    POST /api/agent-control/approval-token/verify
    GET  /api/agent-control/approval-token/status

  No other HTTP method is registered. No mutating route exists
  beyond mint + verify; the verify endpoint records the nonce but
  performs NO underlying approve / reject / merge / deploy action.

* Each route requires an operator session (``session["operator_authenticated"]
  is True``). Missing session → HTTP 401 ``operator_session_required``.

* The mint and verify routes refuse to operate unless
  ``approval_token_runtime.is_configured()`` returns True. Missing
  env → HTTP 503 ``configuration_missing``. The status route is
  always reachable (it reports the configured / unconfigured state).

* Request body > :data:`_MAX_REQUEST_BYTES` (4 KiB) → HTTP 413.

* Never executes a CLI subprocess, never invokes ``gh`` / ``git``,
  never opens its own network socket, never imports a Web Push
  library, never reads the VAPID private-key env var.

* Every response payload is run through
  ``reporting.agent_audit_summary.assert_no_secrets`` before send.
  The HMAC secret never appears in any response, audit log, or
  printed line.

* The mint response carries the minted token string for the
  operator session that requested it. The token is sensitive but
  not a long-term secret (it is short-TTL, single-use, bound to
  the event_id). It travels back over the existing session-
  protected HTTPS channel.

* No approval / reject / merge / deploy decision verb call appears
  in any code path. The verify endpoint returns the outcome only;
  acting on the verified token is N5 territory.

Authentication
--------------

Auth is provided by ``flask.session["operator_authenticated"]``,
set by the existing ``/api/session/login`` endpoint in
``dashboard/dashboard.py``. The blueprint does not register any
auth itself.

The route is reachable from the PWA (which authenticates via
``/api/session/login``) and from the operator's curl invocations on
the VPS host (the PWA session cookie is the only credential).
"""

from __future__ import annotations

from typing import Any, Final

from flask import Flask, Response, jsonify, request, session

from reporting import approval_token_runtime as atr
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N4b"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Bounded body cap
# ---------------------------------------------------------------------------

#: Maximum JSON body size accepted by mint/verify. The bodies are
#: small structured envelopes (event_id + intent + bindings); 4 KiB
#: is a generous cap that still bounds the surface.
_MAX_REQUEST_BYTES: Final[int] = 4 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    assert_no_secrets(payload)
    return jsonify(payload)


def _has_operator_session() -> bool:
    """Return True iff the Flask session carries the
    ``operator_authenticated`` flag set by ``/api/session/login``."""
    try:
        return bool(session.get("operator_authenticated"))
    except Exception:
        return False


def _read_body() -> dict[str, Any] | None:
    """Read the JSON body. Returns ``None`` on any failure."""
    try:
        raw = request.get_json(force=False, silent=True)
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _too_large() -> bool:
    return (
        request.content_length is not None
        and request.content_length > _MAX_REQUEST_BYTES
    )


# ---------------------------------------------------------------------------
# View functions
# ---------------------------------------------------------------------------


def _view_status() -> Response | tuple[Response, int]:
    """GET /api/agent-control/approval-token/status."""
    if not _has_operator_session():
        return (
            _safe_jsonify(
                {
                    "kind": "approval_token_status",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "error",
                    "error": "operator_session_required",
                }
            ),
            401,
        )
    return _safe_jsonify(
        {
            "kind": "approval_token_status",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "is_configured": atr.is_configured(),
            "current_kid": atr.current_kid(),
            "step5_implementation_allowed": step5_implementation_allowed,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        }
    )


def _view_mint() -> Response | tuple[Response, int]:
    """POST /api/agent-control/approval-token/mint."""
    if not _has_operator_session():
        return (
            _safe_jsonify(
                {"status": "error", "error": "operator_session_required"}
            ),
            401,
        )
    if _too_large():
        return (
            _safe_jsonify({"status": "error", "error": "payload_too_large"}),
            413,
        )
    if not atr.is_configured():
        return (
            _safe_jsonify(
                {"status": "error", "error": "configuration_missing"}
            ),
            503,
        )
    body = _read_body()
    if body is None:
        return (
            _safe_jsonify(
                {"status": "error", "error": "invalid_json_body"}
            ),
            400,
        )
    intent = body.get("intent")
    event_id = body.get("event_id")
    evidence_hash = body.get("evidence_hash")
    pr_number = body.get("pr_number")
    pr_head_sha = body.get("pr_head_sha")
    release_tag = body.get("release_tag")
    if not isinstance(intent, str):
        return (
            _safe_jsonify(
                {"status": "error", "error": "intent_must_be_string"}
            ),
            400,
        )
    if not isinstance(event_id, str):
        return (
            _safe_jsonify(
                {"status": "error", "error": "event_id_must_be_string"}
            ),
            400,
        )
    if not isinstance(evidence_hash, str):
        return (
            _safe_jsonify(
                {"status": "error", "error": "evidence_hash_must_be_string"}
            ),
            400,
        )
    if pr_number is not None and not isinstance(pr_number, int):
        return (
            _safe_jsonify(
                {"status": "error", "error": "pr_number_must_be_int_or_null"}
            ),
            400,
        )
    if pr_head_sha is not None and not isinstance(pr_head_sha, str):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "pr_head_sha_must_be_string_or_null",
                }
            ),
            400,
        )
    if release_tag is not None and not isinstance(release_tag, str):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "release_tag_must_be_string_or_null",
                }
            ),
            400,
        )
    envelope = atr.mint_runtime(
        intent=intent,
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
        release_tag=release_tag,
    )
    # Surface the closed mint-result envelope. Non-ok statuses are
    # mapped to a non-200 HTTP code so the PWA can distinguish them.
    status_code = 200 if envelope.get("status") == "ok" else 400
    return _safe_jsonify(envelope), status_code


def _view_verify() -> Response | tuple[Response, int]:
    """POST /api/agent-control/approval-token/verify."""
    if not _has_operator_session():
        return (
            _safe_jsonify(
                {"status": "error", "error": "operator_session_required"}
            ),
            401,
        )
    if _too_large():
        return (
            _safe_jsonify({"status": "error", "error": "payload_too_large"}),
            413,
        )
    if not atr.is_configured():
        return (
            _safe_jsonify(
                {"status": "error", "error": "configuration_missing"}
            ),
            503,
        )
    body = _read_body()
    if body is None:
        return (
            _safe_jsonify(
                {"status": "error", "error": "invalid_json_body"}
            ),
            400,
        )
    token = body.get("token")
    expected_event_id = body.get("expected_event_id")
    expected_evidence_hash = body.get("expected_evidence_hash")
    expected_pr_number = body.get("expected_pr_number")
    expected_pr_head_sha = body.get("expected_pr_head_sha")
    expected_release_tag = body.get("expected_release_tag")
    if not isinstance(token, str):
        return (
            _safe_jsonify(
                {"status": "error", "error": "token_must_be_string"}
            ),
            400,
        )
    if not isinstance(expected_event_id, str):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "expected_event_id_must_be_string",
                }
            ),
            400,
        )
    if not isinstance(expected_evidence_hash, str):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "expected_evidence_hash_must_be_string",
                }
            ),
            400,
        )
    if expected_pr_number is not None and not isinstance(
        expected_pr_number, int
    ):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "expected_pr_number_must_be_int_or_null",
                }
            ),
            400,
        )
    if expected_pr_head_sha is not None and not isinstance(
        expected_pr_head_sha, str
    ):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "expected_pr_head_sha_must_be_string_or_null",
                }
            ),
            400,
        )
    if expected_release_tag is not None and not isinstance(
        expected_release_tag, str
    ):
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "expected_release_tag_must_be_string_or_null",
                }
            ),
            400,
        )
    envelope = atr.verify_runtime(
        token=token,
        expected_event_id=expected_event_id,
        expected_pr_number=expected_pr_number,
        expected_pr_head_sha=expected_pr_head_sha,
        expected_evidence_hash=expected_evidence_hash,
        expected_release_tag=expected_release_tag,
    )
    status_code = 200 if envelope.get("status") == "ok" else 400
    return _safe_jsonify(envelope), status_code


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_APPROVAL_TOKEN_ROUTES: tuple[tuple[str, str, Any, str], ...] = (
    (
        "/api/agent-control/approval-token/status",
        "GET",
        _view_status,
        "agent_control_approval_token_status",
    ),
    (
        "/api/agent-control/approval-token/mint",
        "POST",
        _view_mint,
        "agent_control_approval_token_mint",
    ),
    (
        "/api/agent-control/approval-token/verify",
        "POST",
        _view_verify,
        "agent_control_approval_token_verify",
    ),
)


def register_approval_token_gate_routes(app: Flask) -> None:
    """Register the session-protected approval-token gate routes.

    NOT wired into ``dashboard/dashboard.py`` in this PR. The
    operator-only two-line wiring change is
    ``register_approval_token_gate_routes(app)`` per
    ``execution_authority.md`` (``dashboard_wiring`` = NEEDS_HUMAN).

    Runtime delivery requires:
      1. ``ADE_APPROVAL_TOKEN_HMAC_SECRET`` set in the VPS env.
      2. The two-line wiring diff applied to dashboard.py.
      3. The PWA session cookie (existing /api/session/login flow).
    """
    for path, method, handler, endpoint in _APPROVAL_TOKEN_ROUTES:
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "register_approval_token_gate_routes",
    "step5_implementation_allowed",
]
