"""N2b-2b — dashboard.py wiring diff guard.

This test file pins two layers of guarantees:

1. **Always-on guards** (run regardless of wiring state):
   * every existing ``register_*_routes`` import + call must remain
     in dashboard.py;
   * dashboard.py must not contain a real Web Push provider library
     or VAPID-private-key reference;
   * importing dashboard.py must not flip Step 5 invariants
     (asserted via source-text scan; the live import path is
     covered by other Step 5 tests);
   * the companion governance doc states the load-bearing rules.

2. **Conditional pins** (active only when the operator has added
   the two-line wiring change):
   * the file contains EXACTLY one new import + one new register
     call (no duplicates, no other edits);
   * the new register call appears after the last existing register
     call;
   * the new import sits alongside the existing
     ``from dashboard.api_*`` imports.

Why the conditional shape: the no-touch hook prevents the agent
from editing ``dashboard/dashboard.py`` directly. The operator
makes that edit at PR review. Until then, the conditional pins
return early (still passing). Once the operator edits, the pins
fire and actively enforce the exact diff. This is a strict pin, not
a skip — there is no path by which a wrong wiring can land green.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"

EXPECTED_IMPORT_LINE = (
    "from dashboard.api_push_subscribe import register_push_subscribe_routes"
)
EXPECTED_REGISTER_CALL = "register_push_subscribe_routes(app)"

# These lines MUST remain in dashboard.py post-edit. Removing or
# reordering any of them is forbidden. The N2b-2b push-subscribe
# wiring is now part of this required-list so a future edit cannot
# accidentally drop or reorder it.
EXISTING_REGISTRATIONS_REQUIRED: tuple[str, ...] = (
    "from dashboard.api_campaigns import register_campaign_routes",
    "from dashboard.api_research_intelligence import (",
    "from dashboard.api_observability import register_observability_routes",
    "from dashboard.api_system_meta import register_system_meta_routes",
    "from dashboard.api_agent_control import register_agent_control_routes",
    "from dashboard.api_proposal_queue import register_proposal_queue_routes",
    "from dashboard.api_approval_inbox import register_approval_inbox_routes",
    "from dashboard.api_push_subscribe import register_push_subscribe_routes",
    "from dashboard.api_roadmap_priority import "
    "register_roadmap_priority_routes",
    "register_campaign_routes(app)",
    "register_research_intelligence_routes(app)",
    "register_system_meta_routes(app)",
    "register_observability_routes(app)",
    "register_agent_control_routes(app)",
    "register_proposal_queue_routes(app)",
    "register_approval_inbox_routes(app)",
    "register_roadmap_priority_routes(app)",
    "register_push_subscribe_routes(app)",
)


def _dashboard_text() -> str:
    return DASHBOARD_PY.read_text(encoding="utf-8")


def _wiring_present() -> bool:
    text = _dashboard_text()
    return EXPECTED_IMPORT_LINE in text and EXPECTED_REGISTER_CALL in text


# ---------------------------------------------------------------------------
# Always-on guards
# ---------------------------------------------------------------------------


def test_dashboard_dashboard_exists() -> None:
    assert DASHBOARD_PY.is_file()


def test_existing_dashboard_registrations_unchanged() -> None:
    """Every existing register-routes import + call must still be
    present in dashboard.py, in the same relative order. This guard
    runs in BOTH modes (wiring present or absent) — removing an
    existing registration is never allowed."""
    text = _dashboard_text()
    last_pos = -1
    for needle in EXISTING_REGISTRATIONS_REQUIRED:
        pos = text.find(needle)
        assert pos != -1, (
            f"missing required line in dashboard.py: {needle!r}"
        )
        assert pos > last_pos, (
            f"existing registration out of order in dashboard.py: "
            f"{needle!r}"
        )
        last_pos = pos


def test_dashboard_api_push_dispatch_module_present() -> None:
    """N2b-3b: the real-delivery endpoint module exists at
    ``dashboard/api_push_dispatch.py``. After this PR the module is
    wired into ``dashboard/dashboard.py`` via the strict-enforce
    pins below — runtime delivery still requires the env vars and
    the nginx ``127.0.0.1`` lock to fire.
    """
    module_path = REPO_ROOT / "dashboard" / "api_push_dispatch.py"
    assert module_path.is_file(), (
        "dashboard/api_push_dispatch.py is N2b-3b territory and must "
        "exist."
    )


def test_no_real_push_provider_in_dashboard_dashboard() -> None:
    """dashboard.py must not contain any reference to a real Web Push
    provider library or VAPID private key — defense in depth on top
    of the api blueprint pin tests."""
    text = _dashboard_text().lower()
    forbidden = (
        "pywebpush",
        "from webpush",
        "import webpush",
        "web_push_vapid_private_key",
    )
    for needle in forbidden:
        assert needle not in text, (
            f"dashboard.py must not reference {needle!r} (N2b-3 "
            "territory)"
        )


def test_step5_invariants_unaffected_by_dashboard_dashboard_text() -> None:
    """dashboard.py must not contain code that touches Step 5
    invariants. The Step 5 invariants are pinned by their own tests;
    here we just rule out a wiring-time accidental edit."""
    text = _dashboard_text()
    assert "step5_implementation_allowed" not in text
    assert "STEP5_ENABLED_SUBSTAGE" not in text


# ---------------------------------------------------------------------------
# Conditional pins — fire only when wiring is present
# ---------------------------------------------------------------------------


def test_wiring_diff_is_exactly_one_import_and_one_register_call() -> None:
    """Once the wiring lands, the file must contain EXACTLY one
    occurrence of each of the two new lines. This catches accidental
    duplication or stray edits."""
    if not _wiring_present():
        # Wiring not yet added by the operator. Conditional pin
        # returns early; the test still passes. Once the operator
        # adds the two lines, this branch is no longer taken and the
        # assertions below fire.
        return
    text = _dashboard_text()
    assert text.count(EXPECTED_IMPORT_LINE) == 1, (
        "dashboard.py must contain exactly one new import line"
    )
    assert text.count(EXPECTED_REGISTER_CALL) == 1, (
        "dashboard.py must contain exactly one new register call"
    )


def test_wiring_register_call_after_existing_registrations() -> None:
    if not _wiring_present():
        return
    text = _dashboard_text()
    anchor = "register_roadmap_priority_routes(app)"
    anchor_pos = text.find(anchor)
    new_pos = text.find(EXPECTED_REGISTER_CALL)
    assert anchor_pos != -1
    assert new_pos != -1
    assert new_pos > anchor_pos, (
        "new push-subscribe register call must appear AFTER the "
        "existing register_roadmap_priority_routes(app) anchor"
    )


def test_wiring_import_grouped_with_dashboard_api_imports() -> None:
    if not _wiring_present():
        return
    text = _dashboard_text()
    pos = text.find(EXPECTED_IMPORT_LINE)
    anchor = (
        "from dashboard.api_roadmap_priority import "
        "register_roadmap_priority_routes"
    )
    anchor_pos = text.find(anchor)
    assert pos != -1
    assert anchor_pos != -1
    diff_lines = abs(
        text[:pos].count("\n") - text[:anchor_pos].count("\n")
    )
    assert diff_lines <= 10, (
        "new push-subscribe import should sit alongside existing "
        "dashboard.api_* imports (≤10 lines from the "
        "api_roadmap_priority anchor)"
    )


def test_wiring_no_other_dashboard_dashboard_modifications() -> None:
    """When the wiring lands, the diff to dashboard.py must include
    ONLY the two expected new lines. Detection is approximate: we
    count the number of lines that mention ``register_push_subscribe``
    or ``api_push_subscribe`` and assert it equals exactly 2 (one
    import, one register call)."""
    if not _wiring_present():
        return
    text = _dashboard_text()
    push_lines = [
        line
        for line in text.splitlines()
        if "register_push_subscribe" in line
        or "api_push_subscribe" in line
    ]
    assert len(push_lines) == 2, (
        f"dashboard.py must contain exactly 2 push-subscribe lines; "
        f"found {len(push_lines)}: {push_lines}"
    )


# ---------------------------------------------------------------------------
# N2b-3b dispatch-wiring strict pins (operator wired this PR)
# ---------------------------------------------------------------------------
#
# These pins were dual-mode (skip-or-enforce) until the operator added
# the two-line wiring diff in this PR. They are now STRICT: removing
# either line will fail CI. The wiring shape is exactly:
#
#     from dashboard.api_push_dispatch import register_push_dispatch_routes
#     ...
#     register_push_dispatch_routes(app)
#
# Runtime delivery still requires (a) ``WEB_PUSH_VAPID_PRIVATE_KEY`` and
# ``WEB_PUSH_VAPID_SUBJECT`` in the VPS env, and (b) the nginx
# ``127.0.0.1`` lock on ``/api/push/dispatch``. Without either, the
# wired endpoint still refuses with 503 ``configuration_missing`` or
# 403 ``remote_not_loopback`` — pinned by the api_push_dispatch unit
# tests.

EXPECTED_DISPATCH_IMPORT_LINE = (
    "from dashboard.api_push_dispatch import register_push_dispatch_routes"
)
EXPECTED_DISPATCH_REGISTER_CALL = "register_push_dispatch_routes(app)"


def _dispatch_wiring_present() -> bool:
    text = _dashboard_text()
    return (
        EXPECTED_DISPATCH_IMPORT_LINE in text
        and EXPECTED_DISPATCH_REGISTER_CALL in text
    )


def test_dispatch_wiring_present() -> None:
    """Strict-enforce: dashboard.py must contain BOTH the import and
    the register call. Operator-added two-line diff."""
    text = _dashboard_text()
    assert EXPECTED_DISPATCH_IMPORT_LINE in text, (
        "dashboard.py is missing the dispatch import line: "
        f"{EXPECTED_DISPATCH_IMPORT_LINE!r}"
    )
    assert EXPECTED_DISPATCH_REGISTER_CALL in text, (
        "dashboard.py is missing the dispatch register call: "
        f"{EXPECTED_DISPATCH_REGISTER_CALL!r}"
    )


def test_dispatch_wiring_exactly_one_import_and_one_register_call() -> None:
    """No duplicate dispatch route registration."""
    text = _dashboard_text()
    assert text.count(EXPECTED_DISPATCH_IMPORT_LINE) == 1, (
        "dashboard.py must contain exactly one new dispatch import line"
    )
    assert text.count(EXPECTED_DISPATCH_REGISTER_CALL) == 1, (
        "dashboard.py must contain exactly one new dispatch register call"
    )


def test_dispatch_register_call_after_push_subscribe_call() -> None:
    """The new dispatch register call must appear AFTER the existing
    ``register_push_subscribe_routes(app)`` anchor (the N2b-2b
    wiring). Catches an accidental reorder that would put dispatch
    above the subscription surface or replace it entirely."""
    text = _dashboard_text()
    subscribe_anchor = "register_push_subscribe_routes(app)"
    subscribe_pos = text.find(subscribe_anchor)
    dispatch_pos = text.find(EXPECTED_DISPATCH_REGISTER_CALL)
    assert subscribe_pos != -1, (
        "dashboard.py must still contain the N2b-2b push-subscribe "
        "register call as the anchor"
    )
    assert dispatch_pos != -1
    assert dispatch_pos > subscribe_pos, (
        "the new dispatch register call must appear AFTER the "
        "existing register_push_subscribe_routes(app) anchor"
    )


def test_dispatch_wiring_no_other_dashboard_dashboard_modifications() -> None:
    """The dispatch wiring must add exactly 2 lines mentioning the
    new blueprint (one import + one register call); anything else
    signals a stray edit."""
    text = _dashboard_text()
    push_dispatch_lines = [
        line
        for line in text.splitlines()
        if "register_push_dispatch" in line
        or "api_push_dispatch" in line
    ]
    assert len(push_dispatch_lines) == 2, (
        f"dashboard.py must contain exactly 2 push-dispatch lines; "
        f"found {len(push_dispatch_lines)}: {push_dispatch_lines}"
    )


# ---------------------------------------------------------------------------
# N3b mobile-approval-inbox wiring conditional pins (skip-or-enforce)
# ---------------------------------------------------------------------------
#
# Same dual-mode pattern as the N2b-3b dispatch wiring above. Until
# the operator adds the two-line
# ``register_mobile_approval_inbox_routes(app)`` diff, these pins
# return early. Once added, they enforce the exact wiring shape.
# The blueprint at ``dashboard/api_mobile_approval_inbox.py`` is
# READ-ONLY and exposes only GET routes; runtime delivery still
# requires (a) the existing PWA session middleware and (b) the
# operator wiring this blueprint into ``dashboard/dashboard.py``.

EXPECTED_MOBILE_INBOX_IMPORT_LINE = (
    "from dashboard.api_mobile_approval_inbox "
    "import register_mobile_approval_inbox_routes"
)
EXPECTED_MOBILE_INBOX_REGISTER_CALL = (
    "register_mobile_approval_inbox_routes(app)"
)


def _mobile_inbox_wiring_present() -> bool:
    text = _dashboard_text()
    return (
        EXPECTED_MOBILE_INBOX_IMPORT_LINE in text
        and EXPECTED_MOBILE_INBOX_REGISTER_CALL in text
    )


def test_mobile_inbox_wiring_exactly_one_import_and_one_register_call() -> None:
    if not _mobile_inbox_wiring_present():
        # Operator has not yet added the two-line diff. Conditional
        # pin returns early; the test still passes. Once the operator
        # commits the wiring, this branch is no longer taken and the
        # assertions below fire.
        return
    text = _dashboard_text()
    assert text.count(EXPECTED_MOBILE_INBOX_IMPORT_LINE) == 1, (
        "dashboard.py must contain exactly one new mobile-inbox "
        "import line"
    )
    assert text.count(EXPECTED_MOBILE_INBOX_REGISTER_CALL) == 1, (
        "dashboard.py must contain exactly one new mobile-inbox "
        "register call"
    )


def test_mobile_inbox_wiring_no_other_dashboard_dashboard_modifications() -> None:
    if not _mobile_inbox_wiring_present():
        return
    text = _dashboard_text()
    mobile_inbox_lines = [
        line
        for line in text.splitlines()
        if "register_mobile_approval_inbox" in line
        or "api_mobile_approval_inbox" in line
    ]
    assert len(mobile_inbox_lines) == 2, (
        f"dashboard.py must contain exactly 2 mobile-inbox lines; "
        f"found {len(mobile_inbox_lines)}: {mobile_inbox_lines}"
    )


# ---------------------------------------------------------------------------
# N4b approval-token-gate wiring conditional pins (skip-or-enforce)
# ---------------------------------------------------------------------------
#
# Same dual-mode pattern as the N3b/N2b-3b wirings above. Until the
# operator adds the two-line ``register_approval_token_gate_routes(app)``
# diff, these pins return early. Once added, they enforce the exact
# wiring shape.
#
# Runtime delivery additionally requires the env secret
# ``ADE_APPROVAL_TOKEN_HMAC_SECRET`` to be exported on the VPS; the
# wired endpoint refuses with HTTP 503 ``configuration_missing`` when
# the env is absent — pinned by the api_approval_token_gate unit
# tests.

EXPECTED_TOKEN_GATE_IMPORT_LINE = (
    "from dashboard.api_approval_token_gate "
    "import register_approval_token_gate_routes"
)
EXPECTED_TOKEN_GATE_REGISTER_CALL = (
    "register_approval_token_gate_routes(app)"
)


def _token_gate_wiring_present() -> bool:
    text = _dashboard_text()
    return (
        EXPECTED_TOKEN_GATE_IMPORT_LINE in text
        and EXPECTED_TOKEN_GATE_REGISTER_CALL in text
    )


def test_token_gate_wiring_exactly_one_import_and_one_register_call() -> None:
    if not _token_gate_wiring_present():
        return
    text = _dashboard_text()
    assert text.count(EXPECTED_TOKEN_GATE_IMPORT_LINE) == 1, (
        "dashboard.py must contain exactly one new token-gate "
        "import line"
    )
    assert text.count(EXPECTED_TOKEN_GATE_REGISTER_CALL) == 1, (
        "dashboard.py must contain exactly one new token-gate "
        "register call"
    )


def test_token_gate_wiring_no_other_dashboard_dashboard_modifications() -> None:
    if not _token_gate_wiring_present():
        return
    text = _dashboard_text()
    token_gate_lines = [
        line
        for line in text.splitlines()
        if "register_approval_token_gate" in line
        or "api_approval_token_gate" in line
    ]
    assert len(token_gate_lines) == 2, (
        f"dashboard.py must contain exactly 2 token-gate lines; "
        f"found {len(token_gate_lines)}: {token_gate_lines}"
    )


# ---------------------------------------------------------------------------
# Companion doc invariants (always on)
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "notification_dispatch_pwa.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
        or "no approval can happen from a notification click alone" in text
    )


def test_doc_states_no_real_push_in_n2b2b() -> None:
    text = _doc_text().lower()
    assert "no real push" in text or "no real web push" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window


def test_doc_lists_n2b3_n3_n4_n5_as_unimplemented() -> None:
    text = _doc_text().lower()
    for marker in ("n2b-3", "n3", "n4", "n5"):
        assert marker in text, marker
    assert "unimplemented" in text or "out of scope" in text or "future" in text


# ---------------------------------------------------------------------------
# Service-worker URL reachability (operator-authored Flask route)
# ---------------------------------------------------------------------------
#
# webPush.ts registers ``/sw-push.js`` with scope ``/agent-control/``.
# Flask must expose that exact URL, must serve the file from
# ``FRONTEND_DIST``, and must include the
# ``Service-Worker-Allowed: /agent-control/`` header so the wider
# scope is honoured by the browser. This block strictly pins all
# four invariants so a future regression that breaks the SW URL
# (e.g. typo in the route, wrong source dir, missing header) fails
# loudly at unit-test time, not at runtime in the operator's PWA.

WEBPUSH_TS_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "webPush.ts"


def _webpush_ts() -> str:
    return WEBPUSH_TS_PATH.read_text(encoding="utf-8")


def test_webpush_ts_registers_exact_sw_path() -> None:
    """The frontend must register the SW at exactly ``/sw-push.js``.
    Catches a frontend-only edit that would point to a different
    URL (e.g. ``/sw-push.mjs`` or ``/agent-control/sw-push.js``).
    """
    src = _webpush_ts()
    assert 'const SW_PATH = "/sw-push.js"' in src, (
        "frontend/src/lib/webPush.ts must register exactly /sw-push.js"
    )


def test_dashboard_dashboard_serves_sw_push_route() -> None:
    """dashboard.py must contain @app.route(\"/sw-push.js\").

    Pinned by literal substring search to keep the test independent
    of Flask import side-effects."""
    text = _dashboard_text()
    assert '@app.route("/sw-push.js")' in text, (
        "dashboard/dashboard.py must declare @app.route(\"/sw-push.js\")"
    )


def test_dashboard_dashboard_sw_push_serves_from_frontend_dist() -> None:
    """The /sw-push.js handler must read from ``FRONTEND_DIST``.

    Anchored by the route declaration; we check the surrounding
    handler body. This rules out accidentally reading from
    ``dashboard/static/`` (where ``sw-push.js`` does not live in the
    Vite build pipeline) or from any other folder.
    """
    text = _dashboard_text()
    route_idx = text.find('@app.route("/sw-push.js")')
    assert route_idx != -1
    handler_window = text[route_idx : route_idx + 600]
    assert 'send_from_directory(FRONTEND_DIST, "sw-push.js"' in handler_window, (
        "the /sw-push.js handler must call "
        "send_from_directory(FRONTEND_DIST, \"sw-push.js\", ...)"
    )


def test_dashboard_dashboard_sw_push_sets_service_worker_allowed_scope() -> None:
    """The /sw-push.js response must set
    ``Service-Worker-Allowed: /agent-control/``. Without this header
    the browser refuses the wider SW scope and the subscribe flow
    breaks at runtime.
    """
    text = _dashboard_text()
    route_idx = text.find('@app.route("/sw-push.js")')
    assert route_idx != -1
    handler_window = text[route_idx : route_idx + 600]
    assert (
        'resp.headers["Service-Worker-Allowed"] = "/agent-control/"'
        in handler_window
    ), (
        "the /sw-push.js handler must set "
        'resp.headers["Service-Worker-Allowed"] = "/agent-control/"'
    )


def test_dashboard_dashboard_sw_push_route_distinct_from_existing_sw() -> None:
    """The /sw-push.js route must be a distinct route from /sw.js
    and must not overwrite or alias the existing service worker
    handler. Both must coexist."""
    text = _dashboard_text()
    assert '@app.route("/sw.js")' in text, "/sw.js route must remain"
    assert '@app.route("/sw-push.js")' in text, "/sw-push.js route required"
    # Each route appears exactly once.
    assert text.count('@app.route("/sw.js")') == 1
    assert text.count('@app.route("/sw-push.js")') == 1


def test_webpush_scope_matches_dashboard_service_worker_allowed_header() -> None:
    """The frontend's registered scope and the backend's
    Service-Worker-Allowed header must match. Drift here breaks
    subscribe at runtime even though both ends are individually
    well-formed."""
    src = _webpush_ts()
    text = _dashboard_text()
    assert 'const SW_SCOPE = "/agent-control/"' in src, (
        "webPush.ts must set SW_SCOPE = \"/agent-control/\""
    )
    assert (
        'resp.headers["Service-Worker-Allowed"] = "/agent-control/"' in text
    ), (
        "dashboard.py must set Service-Worker-Allowed: /agent-control/ "
        "to match the frontend SW_SCOPE"
    )
