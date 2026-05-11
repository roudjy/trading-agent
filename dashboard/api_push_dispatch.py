"""N2b-3b — Real Web Push dispatch API blueprint (UNWIRED, loopback-only).

Flask blueprint exposing the **single** real-delivery endpoint
:code:`POST /api/push/dispatch`. The endpoint composes the existing
N2a / N2b-1 / N2b-2a / N2b-3a stack into one operator-triggered call:

* reads the latest dispatch outbox snapshot
  (``logs/notification_dispatch_outbox/latest.json``) — pure read;
* filters records with ``outbound_delivery_intent == "sent"`` (i.e.
  the stub provider accepted them offline);
* loads the active Web Push subscriptions from the gitignored
  store via :mod:`reporting.push_subscription_store`;
* for each (record × subscription) pair, builds the N2b-3a envelope
  and calls :func:`reporting.web_push_dispatch_adapter.dispatch_one`
  with a real-transport closure from
  :mod:`reporting.web_push_real_transport`;
* on any ``drop_subscription`` outcome, removes the subscription
  via ``pss.unregister_subscription``;
* writes a bounded summary to
  ``logs/notification_dispatch_real/latest.json`` (atomic,
  sentinel-restricted) and returns it (already redacted: counts +
  endpoint_hash + outcome class — never endpoint URL, never key
  material).

**The blueprint is intentionally NOT wired into**
``dashboard/dashboard.py``. Wiring is a one-line
``register_push_dispatch_routes(app)`` change that the operator adds
at PR review (the no-touch hook blocks the agent from editing the
file). Until that wiring lands, the endpoint is unreachable through
the live dashboard.

Hard guarantees (pinned by tests)
---------------------------------

* POST only — no other HTTP method is registered.
* Refuses any request whose ``request.remote_addr`` is not in
  ``{"127.0.0.1", "::1"}`` with HTTP 403. nginx is expected to
  restrict the route to ``127.0.0.1`` at the edge; this Python
  check is defense-in-depth.
* Refuses requests when
  :func:`reporting.web_push_real_transport.is_configured` returns
  False, with HTTP 503 ``configuration_missing``.
* Refuses request bodies greater than 1 KiB with HTTP 413.
* Never executes a CLI subprocess, never invokes ``gh`` or ``git``,
  never opens its own network socket (delegates to the lazy-imported
  ``pywebpush`` inside the transport module), never imports a Web
  Push library at this layer.
* Every response payload is run through ``assert_no_secrets`` from
  ``reporting.agent_audit_summary``.
* Response payload NEVER contains subscription endpoint URLs or
  keys — only ``endpoint_hash`` and outcome classes.
* No approval verb (approve / reject / merge / deploy) is accepted,
  emitted, or actionable. The endpoint delivers notifications only;
  N3 (approval inbox), N4 (token gate), and N5 (merge / deploy
  adapter) remain unimplemented.

Authentication
--------------

Auth is provided by the existing PWA session middleware applied at
the dashboard wiring layer. The blueprint does not register any auth
itself. Defense in depth: nginx is expected to restrict
``/api/push/dispatch`` to ``127.0.0.1`` and the loopback check above
re-enforces that at the Python layer. The dispatch endpoint is an
operator tool (curl from the VPS), never reachable from the public
internet.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify, request

from reporting import push_subscription_store as pss
from reporting import web_push_dispatch_adapter as wpda
from reporting import web_push_real_transport as wprt
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N2b3b"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Bounded request body limit
# ---------------------------------------------------------------------------

#: Maximum JSON body size. The dispatch endpoint accepts an empty
#: body or a small object with a future optional ``event_id`` filter;
#: anything larger is refused 413.
_MAX_REQUEST_BYTES: Final[int] = 1024


# ---------------------------------------------------------------------------
# Loopback allowlist (defense in depth on top of nginx)
# ---------------------------------------------------------------------------

_LOOPBACK_REMOTE_ADDRS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1"})


# ---------------------------------------------------------------------------
# Artefact write target (sentinel-restricted, atomic)
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "notification_dispatch_real"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatch_real/latest.json"
)
_WRITE_PREFIX: Final[str] = "logs/notification_dispatch_real/"


# ---------------------------------------------------------------------------
# Source-snapshot path (N2b-1 outbox latest)
# ---------------------------------------------------------------------------

_OUTBOX_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "notification_dispatch_outbox" / "latest.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _is_loopback(addr: str | None) -> bool:
    if not isinstance(addr, str) or not addr:
        return False
    return addr in _LOOPBACK_REMOTE_ADDRS


def _read_outbox_snapshot() -> dict[str, Any] | None:
    """Read the latest N2b-1 outbox snapshot. Best-effort; never raises."""
    if not _OUTBOX_LATEST.is_file():
        return None
    try:
        text = _OUTBOX_LATEST.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _ready_records(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Filter outbox records to those the stub provider accepted.

    Those are the only candidates for real delivery — anything else
    failed an upstream gate (schema, secret guard, rate limit, etc.)
    and must not be promoted to a real push.
    """
    if not isinstance(snapshot, dict):
        return []
    records = snapshot.get("records")
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("outbound_delivery_intent") != "sent":
            continue
        payload = r.get("payload")
        if not isinstance(payload, dict):
            continue
        eid = payload.get("event_id")
        if not isinstance(eid, str) or not eid:
            continue
        out.append(r)
    return out


def _atomic_write_summary(payload: dict[str, Any]) -> Path:
    """Atomic-write the dispatch summary. Sentinel-restricted."""
    path = ARTIFACT_LATEST
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "api_push_dispatch._atomic_write_summary refuses non-real-logs "
            f"output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".api_push_dispatch.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


# ---------------------------------------------------------------------------
# Core dispatch routine (test-injectable transport factory)
# ---------------------------------------------------------------------------


def _redact_record(
    *,
    event_id: str,
    endpoint_hash: str,
    outcome: str,
    provider_status_class: str,
    provider_status_code: int | None,
    attempted_at: str,
) -> dict[str, Any]:
    """Return the redacted per-attempt summary row. Never contains the
    endpoint URL, never contains key material."""
    return {
        "event_id": event_id,
        "endpoint_hash": endpoint_hash,
        "outcome": outcome,
        "provider_status_class": provider_status_class,
        "provider_status_code": provider_status_code,
        "attempted_at": attempted_at,
    }


def dispatch_ready_events(
    *,
    transport_factory: Any | None = None,
    outbox_snapshot: dict[str, Any] | None = None,
    subscriptions: list[dict[str, Any]] | None = None,
    unregister_callable: Any | None = None,
) -> dict[str, Any]:
    """Walk the latest outbox snapshot and dispatch each ready record
    to each active subscription using the real transport.

    Test-injection points (all default to the production wiring):

    * ``transport_factory`` — defaults to
      :func:`reporting.web_push_real_transport.make_transport_for_subscription`.
    * ``outbox_snapshot`` — defaults to reading
      ``logs/notification_dispatch_outbox/latest.json``.
    * ``subscriptions`` — defaults to ``pss.list_subscriptions()``.
    * ``unregister_callable`` — defaults to
      ``pss.unregister_subscription`` (only invoked on a
      ``drop_subscription`` outcome).

    Returns the bounded summary dict; the caller writes it to
    ``logs/notification_dispatch_real/latest.json``.
    """
    tf = (
        transport_factory
        if transport_factory is not None
        else wprt.make_transport_for_subscription
    )
    snap = (
        outbox_snapshot
        if outbox_snapshot is not None
        else _read_outbox_snapshot()
    )
    subs = (
        list(subscriptions)
        if subscriptions is not None
        else list(pss.list_subscriptions())
    )
    unreg = (
        unregister_callable
        if unregister_callable is not None
        else pss.unregister_subscription
    )

    ts = _utcnow()
    records = _ready_records(snap)

    attempts: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "ready_records": len(records),
        "subscriptions": len(subs),
        "attempted": 0,
        "sent": 0,
        "drop_subscription": 0,
        "failed_provider": 0,
        "retry": 0,
        "skipped_no_subscription": 0,
        "skipped_invalid_record": 0,
        "unregistered_on_410": 0,
    }

    if not records or not subs:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "generated_at_utc": ts,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": step5_implementation_allowed,
            "counts": counts,
            "attempts": attempts,
            "note": (
                "no_ready_records" if not records else "no_subscriptions"
            ),
        }

    for rec in records:
        payload = rec.get("payload") or {}
        for sub in subs:
            if not isinstance(sub, dict):
                continue
            endpoint = sub.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                continue

            transport_callable = tf(subscription=sub)
            dispatch_record = wpda.dispatch_one(
                record=payload,
                subscription=sub,
                transport=transport_callable,
                attempted_at=ts,
            )
            counts["attempted"] += 1
            outcome = str(dispatch_record.get("outcome") or "")
            if outcome in counts:
                counts[outcome] += 1

            if outcome == "drop_subscription":
                try:
                    if unreg(endpoint):
                        counts["unregistered_on_410"] += 1
                except Exception:
                    pass

            attempts.append(
                _redact_record(
                    event_id=str(dispatch_record.get("event_id") or ""),
                    endpoint_hash=str(
                        dispatch_record.get("endpoint_hash") or ""
                    ),
                    outcome=outcome,
                    provider_status_class=str(
                        dispatch_record.get("provider_status_class") or ""
                    ),
                    provider_status_code=(
                        dispatch_record.get("provider_status_code")
                        if isinstance(
                            dispatch_record.get("provider_status_code"),
                            int,
                        )
                        else None
                    ),
                    attempted_at=str(
                        dispatch_record.get("attempted_at") or ts
                    ),
                )
            )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "counts": counts,
        "attempts": attempts,
        "note": "dispatch_summary",
    }
    assert_no_secrets(summary)
    return summary


# ---------------------------------------------------------------------------
# View function
# ---------------------------------------------------------------------------


def _view_dispatch() -> tuple[Response, int] | Response:
    """POST /api/push/dispatch — operator-triggered real delivery."""
    if not _is_loopback(request.remote_addr):
        return (
            _safe_jsonify(
                {"status": "error", "error": "remote_not_loopback"}
            ),
            403,
        )
    if request.content_length is not None and (
        request.content_length > _MAX_REQUEST_BYTES
    ):
        return (
            _safe_jsonify(
                {"status": "error", "error": "payload_too_large"}
            ),
            413,
        )
    if not wprt.is_configured():
        return (
            _safe_jsonify(
                {"status": "error", "error": "configuration_missing"}
            ),
            503,
        )

    try:
        summary = dispatch_ready_events()
    except Exception as exc:  # defense in depth
        return (
            _safe_jsonify(
                {
                    "status": "error",
                    "error": "dispatch_exception",
                    "exc_class": exc.__class__.__name__,
                }
            ),
            500,
        )

    try:
        _atomic_write_summary(summary)
    except Exception:
        # Best-effort: summary write failure does not undo the dispatch.
        pass

    return _safe_jsonify({"status": "ok", "summary": summary})


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_PUSH_DISPATCH_ROUTES: tuple[tuple[str, str, Any], ...] = (
    ("/api/push/dispatch", "POST", _view_dispatch),
)


def register_push_dispatch_routes(app: Flask) -> None:
    """Register the real Web Push dispatch surface.

    **NOT wired into ``dashboard/dashboard.py``** in this PR. The
    one-line wiring change ``register_push_dispatch_routes(app)`` is
    operator-only per ``execution_authority.md`` (``dashboard_wiring``
    = NEEDS_HUMAN). The blueprint becomes session-protected (and
    nginx-loopback-restricted) once that wiring lands.
    """
    for path, method, handler in _PUSH_DISPATCH_ROUTES:
        endpoint_name = (
            f"push_dispatch_{method.lower()}_{path.rsplit('/', 1)[-1]}"
        )
        app.add_url_rule(
            path,
            endpoint=endpoint_name,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "ARTIFACT_LATEST",
    "ARTIFACT_RELATIVE_PATH",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "dispatch_ready_events",
    "register_push_dispatch_routes",
    "step5_implementation_allowed",
]
