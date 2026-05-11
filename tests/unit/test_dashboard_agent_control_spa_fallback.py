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
