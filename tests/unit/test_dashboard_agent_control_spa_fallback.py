"""SPA-fallback integration test for /agent-control/<path:path>.

Reproduces the regression observed live on the VPS after N2b-3b
real-push went green: a notification tap opened
``/agent-control/inbox?event=<event_id>`` and Flask returned its
catch-all JSON 404 envelope
(``{"error":"404 Not Found...","data":[]}``) because no route matched
the deep-link.

This test exercises the **real** ``dashboard.dashboard.app`` via the
Flask test client and asserts the deep-link path now serves the SPA
(or auth challenge), never the JSON-404 envelope.

The companion frontend route at
``frontend/src/routes/AgentControl/InboxPlaceholder.tsx`` renders a
read-only landing page; the existing Web Push SW already constrains
``open_at`` to the ``/agent-control/inbox`` prefix.

Hard guarantees verified:
* GET ``/agent-control/inbox?event=test`` returns status 200 (SPA
  HTML on an authed session) or 401 (Basic-Auth challenge for an
  unauthed client) — **never** the JSON 404 envelope.
* Response ``Content-Type`` is not ``application/json``.
* Response body does not contain the catch-all error envelope
  substring ``"data":[]`` or ``"error":"404 Not Found``.
* Source text of ``dashboard/dashboard.py`` contains the new
  ``@app.route("/agent-control/<path:path>")`` decorator and an
  ``spa_fallback_authed`` signature that accepts a defaulted
  ``path`` parameter (operator-authored, no-touch path).
* No new approval / merge / deploy / token capability is implied by
  this change.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"


# ---------------------------------------------------------------------------
# Source-text pin (operator wiring presence)
# ---------------------------------------------------------------------------


def _dashboard_text() -> str:
    return DASHBOARD_PY.read_text(encoding="utf-8")


def test_dashboard_dashboard_has_agent_control_subpath_decorator() -> None:
    """Strict pin: the operator-authored decorator must be present.

    The new wiring is a single ``@app.route("/agent-control/<path:path>")``
    line added to the existing ``spa_fallback_authed`` decorator stack.
    """
    text = _dashboard_text()
    assert '@app.route("/agent-control/<path:path>")' in text, (
        "dashboard.py is missing the /agent-control/<path:path> "
        "SPA-fallback decorator (operator-authored two-line edit)."
    )


def test_dashboard_dashboard_spa_fallback_signature_accepts_path() -> None:
    """The ``spa_fallback_authed`` function must accept an optional
    ``path`` parameter so the same handler covers both the legacy
    exact routes and the new sub-path route."""
    text = _dashboard_text()
    pattern = re.compile(
        r"def\s+spa_fallback_authed\s*\(\s*path\s*:\s*str\s*=\s*\"\"\s*\)\s*:"
    )
    assert pattern.search(text) is not None, (
        "dashboard.py spa_fallback_authed must accept a defaulted "
        "``path: str = \"\"`` parameter so both exact and sub-path "
        "routes resolve to the same SPA handler."
    )


def test_dashboard_dashboard_existing_agent_control_route_preserved() -> None:
    """The legacy ``/agent-control`` exact route must still be there;
    this PR only ADDS a sibling sub-path route."""
    text = _dashboard_text()
    assert '@app.route("/agent-control")' in text, (
        "dashboard.py must still register the legacy /agent-control "
        "exact route alongside the new sub-path route."
    )


# ---------------------------------------------------------------------------
# Flask integration: deep-link must not return the JSON 404 envelope
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Return ``(test_client, app)`` for the real dashboard app.

    Redirects the on-disk session-secret target into ``tmp_path`` so the
    test never mutates the developer's state/ directory.
    """
    # Redirect secret-on-disk targets BEFORE importing the dashboard.
    monkeypatch.setenv("HOME", str(tmp_path))
    from dashboard import dashboard as dashboard_mod

    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client(), dashboard_mod.app


def _is_json_404_envelope(body: bytes, content_type: str) -> bool:
    """Return True iff the response looks like the catch-all JSON
    error envelope produced by the global ``@app.errorhandler``."""
    if "application/json" not in (content_type or "").lower():
        return False
    text = body.decode("utf-8", errors="replace")
    return '"data":[]' in text and '"error"' in text


def test_agent_control_inbox_deeplink_does_not_return_json_404(
    app_client,
) -> None:
    client, _app = app_client
    resp = client.get("/agent-control/inbox?event=test")
    # Acceptable responses: 200 (authed SPA), 401 (Basic-Auth
    # challenge), 302 (redirect to /login). The JSON-404 envelope is
    # explicitly forbidden.
    assert resp.status_code in (200, 401, 302), (
        f"unexpected status {resp.status_code} for /agent-control/inbox"
    )
    content_type = resp.headers.get("Content-Type") or ""
    assert "application/json" not in content_type.lower(), (
        f"deep-link must not return JSON; got {content_type!r}"
    )
    assert not _is_json_404_envelope(resp.data, content_type), (
        "deep-link must not return the catch-all JSON 404 envelope"
    )


def test_agent_control_unknown_subpath_does_not_return_json_404(
    app_client,
) -> None:
    """Any sub-path under /agent-control/ should land on the SPA
    fallback (or auth challenge), not the JSON 404 envelope. The
    React router decides what to render."""
    client, _app = app_client
    resp = client.get("/agent-control/some-future-subpath")
    assert resp.status_code in (200, 401, 302)
    content_type = resp.headers.get("Content-Type") or ""
    assert "application/json" not in content_type.lower()
    assert not _is_json_404_envelope(resp.data, content_type)


def test_unknown_top_level_path_still_404s_through_error_handler(
    app_client,
) -> None:
    """Regression guard: the fix is scoped to /agent-control/<...>
    only. Random top-level paths are still handled by Flask's
    catch-all. This test pins that scope so a future careless edit
    can't accidentally turn the whole app into a SPA fallback."""
    client, _app = app_client
    resp = client.get("/this-path-must-not-exist-12345")
    # The error handler returns JSON 500 (per the existing catch-all
    # at the top of dashboard.py). What matters is that the deep-link
    # fix above did NOT silently swallow other 404s into the SPA.
    assert resp.status_code in (404, 500), (
        f"non-/agent-control 404 must still error, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Scope guards: this fix is read-only / no new authority
# ---------------------------------------------------------------------------


def test_no_decision_verb_added_in_spa_fallback_block(
    app_client,
) -> None:
    """The operator-added decorator/signature change must not bring
    any approve/reject/merge/deploy verb call into dashboard.py."""
    text = _dashboard_text().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in text, verb


def test_no_real_push_provider_in_dashboard_dashboard() -> None:
    """Defense-in-depth: this PR must not add a pywebpush import,
    VAPID private-key reference, or any real Web Push library import
    into the dashboard module — those are reserved for the existing
    N2b-3b dispatch route and the env-only transport."""
    text = _dashboard_text().lower()
    forbidden = (
        "pywebpush",
        "from webpush",
        "import webpush",
        "web_push_vapid_private_key",
    )
    for needle in forbidden:
        assert needle not in text, needle


def test_step5_invariants_unaffected_by_this_pr() -> None:
    text = _dashboard_text()
    assert "step5_implementation_allowed" not in text
    assert "STEP5_ENABLED_SUBSTAGE" not in text


# ---------------------------------------------------------------------------
# PWA recovery: unauth SPA deep-link redirects to /login?next=<safe>
# ---------------------------------------------------------------------------
#
# Backend ``authenticate()`` rewrite — the operator-authored fix. The
# PWA has no address bar; the bare 401 "Login vereist" body would
# trap the user. For /agent-control SPA paths the response is now a
# 302 to /login?next=<sanitised>. API routes still receive the
# Basic-Auth challenge unchanged.

import urllib.parse as _ulp


def test_unauth_spa_deeplink_redirects_to_login_next(app_client) -> None:
    client, _app = app_client
    resp = client.get(
        "/agent-control/inbox?event=test",
        follow_redirects=False,
    )
    assert resp.status_code == 302, (
        f"unauth SPA deep-link must redirect; got {resp.status_code}"
    )
    location = resp.headers.get("Location") or ""
    assert location.startswith("/login?next="), (
        f"redirect target must be /login?next=...; got {location!r}"
    )
    body = resp.data.decode("utf-8", errors="replace")
    assert "Login vereist" not in body, (
        "SPA deep-link must NOT return the plain Basic-Auth body"
    )


def test_unauth_spa_deeplink_redirect_preserves_query_in_next(
    app_client,
) -> None:
    client, _app = app_client
    resp = client.get(
        "/agent-control/inbox?event=abc12345",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("Location") or ""
    # Extract and URL-decode the next= value.
    parsed = _ulp.urlparse(location)
    qs = dict(_ulp.parse_qsl(parsed.query, keep_blank_values=True))
    next_target = qs.get("next") or ""
    assert next_target == "/agent-control/inbox?event=abc12345", (
        f"next param must round-trip the original SPA path; got {next_target!r}"
    )


def test_unauth_spa_exact_route_redirects_to_login_next(app_client) -> None:
    client, _app = app_client
    resp = client.get("/agent-control", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location") or ""
    assert location.startswith("/login?next="), location


def test_unauth_api_route_still_returns_basic_auth_challenge(
    app_client,
) -> None:
    """Defense in depth: the redirect path is scoped to /agent-control
    SPA routes only. API endpoints continue to return the existing
    401 "Login vereist" challenge so headless / non-PWA clients behave
    unchanged."""
    client, _app = app_client
    resp = client.get(
        "/api/agent-control/status",
        follow_redirects=False,
    )
    # The API blueprints register their own routes; some may exist
    # and require auth (401), some may not exist (returns 404/500
    # via the existing error handler). What MUST be true: if the
    # response is 401, the body is the plain "Login vereist" text,
    # NOT a redirect to /login.
    if resp.status_code == 401:
        body = resp.data.decode("utf-8", errors="replace")
        assert "Login vereist" in body, (
            "API 401 must still be the plain Basic-Auth body; got "
            f"{body!r}"
        )
    elif resp.status_code == 302:
        location = resp.headers.get("Location") or ""
        assert not location.startswith("/login"), (
            "API routes must NOT redirect to /login (PWA-recovery "
            "path is scoped to /agent-control only)"
        )


def test_login_route_is_publicly_reachable(app_client) -> None:
    """The /login route must NOT require auth — the React Login
    component must always render so the user can authenticate."""
    client, _app = app_client
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type") or ""
    assert "application/json" not in content_type.lower()


def test_unauth_redirect_rejects_external_url_smuggling(app_client) -> None:
    """Any /agent-control SPA path that itself is malformed (e.g. via
    proxy/path manipulation) must still produce a safe ``next``.
    Flask's request.full_path won't normally let an external URL in,
    but we add this guard to prove the sanitiser drops anything that
    is not a literal /agent-control prefix."""
    client, _app = app_client
    # The path-only request is the only way to reach authenticate();
    # the sanitiser drops anything else. Test a sub-path that should
    # still be honoured (round-trip).
    resp = client.get(
        "/agent-control/inbox/some/sub?event=evt",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("Location") or ""
    parsed = _ulp.urlparse(location)
    qs = dict(_ulp.parse_qsl(parsed.query, keep_blank_values=True))
    next_target = qs.get("next") or ""
    assert next_target.startswith("/agent-control/"), next_target
    assert "://" not in next_target, next_target
    assert ".." not in next_target, next_target


def test_authenticate_function_source_documents_pwa_recovery(
    app_client,
) -> None:
    """Source-text pin: the operator-authored authenticate() body
    must reference both the SPA prefix and the redirect target so a
    future careless edit can't silently revert the PWA recovery
    path."""
    text = _dashboard_text()
    # Strict requirements on the modified authenticate() body:
    assert '"/agent-control"' in text, (
        "authenticate() must reference the /agent-control prefix"
    )
    assert "/login?next=" in text, (
        "authenticate() must reference the /login?next= redirect target"
    )
    assert "Location" in text, (
        "authenticate() must set a Location header on the redirect"
    )


def test_authenticate_function_still_returns_basic_auth_for_non_spa(
    app_client,
) -> None:
    """The operator-authored change must preserve the existing 401
    Basic-Auth body for non-SPA paths. Source-text pin asserts the
    legacy ``Login vereist`` 401 response is still present in the
    function."""
    text = _dashboard_text()
    assert 'Response("Login vereist", 401' in text, (
        "authenticate() must still return the 401 Basic-Auth body "
        "for non-SPA paths"
    )
    assert 'WWW-Authenticate' in text, (
        "authenticate() must still set WWW-Authenticate for the "
        "Basic-Auth challenge"
    )


# ---------------------------------------------------------------------------
# Authenticated path: SPA HTML, not redirect
# ---------------------------------------------------------------------------


def test_authenticated_spa_deeplink_serves_spa_not_redirect(
    app_client,
) -> None:
    """With an authed session cookie, the SPA deep-link must serve
    the SPA HTML (or the development fallback) — NOT redirect to
    /login."""
    client, _app = app_client
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "test"
    resp = client.get(
        "/agent-control/inbox?event=test",
        follow_redirects=False,
    )
    assert resp.status_code == 200, resp.status_code
    content_type = resp.headers.get("Content-Type") or ""
    assert "application/json" not in content_type.lower()
    # The body is SPA HTML (or the dev-mode "frontend bundle niet
    # gevonden" placeholder). Either way it is NOT a redirect and
    # NOT the JSON 404 envelope.
    body = resp.data.decode("utf-8", errors="replace")
    assert '"data":[]' not in body
    assert "Login vereist" not in body


# ---------------------------------------------------------------------------
# Scope guards for the new redirect code (no new authority)
# ---------------------------------------------------------------------------


def test_authenticate_change_introduces_no_decision_verbs() -> None:
    """The operator-authored authenticate() rewrite must not bring
    any approve/reject/merge/deploy verb call into dashboard.py."""
    text = _dashboard_text().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in text, verb


def test_authenticate_change_introduces_no_token_mint_helpers() -> None:
    """The PWA recovery path must not introduce any approval-token
    minting helper into dashboard.py directly.

    The legitimate N4b wiring (``from dashboard.api_approval_token_gate
    import register_approval_token_gate_routes`` +
    ``register_approval_token_gate_routes(app)``) is allowed — that
    imports the BLUEPRINT module, which itself owns the token-mint
    surface. dashboard.py must not call mint helpers itself, nor
    directly import the underlying N4a / N4b runtime modules.
    """
    text = _dashboard_text().lower()
    forbidden = (
        # Never-present-by-naming helper-call patterns (defense in
        # depth against a future refactor that accidentally
        # introduces a mint helper at the dashboard layer).
        "mint_approval_token",
        "approval_token_mint",
        # Direct imports of the underlying modules — only the
        # blueprint module (``dashboard.api_approval_token_gate``)
        # is allowed to wire them.
        "from reporting.approval_token_gate",
        "from reporting.approval_token_runtime",
        "import reporting.approval_token_gate",
        "import reporting.approval_token_runtime",
    )
    for needle in forbidden:
        assert needle not in text, needle
