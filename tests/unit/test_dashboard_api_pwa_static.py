"""Unit tests for the dashboard.api_pwa_static blueprint (UNWIRED).

Pins the eleven unauthenticated root PWA static-asset routes that
fix the iOS Safari PWA install / push subscribe regression.
Without these explicit routes, requests to ``/manifest.webmanifest``,
``/agent-control-icon.svg`` and the various ``/apple-touch-icon*.png``
paths fell through to the global ``@app.errorhandler(Exception)``
in ``dashboard/dashboard.py``, which converted Flask's ``NotFound``
into HTTP 500 with the JSON ``{"error": ..., "data": []}`` envelope.

Tests verified here:

* exactly eleven GET routes register, by URL + method + endpoint;
* every route returns HTTP 200 (no 500, no 401, no 302 redirect);
* every route returns the closed-vocab Content-Type for its kind
  (manifest+json / svg / png);
* manifest body parses as JSON and exposes the canonical PWA
  fields the iOS install heuristic needs;
* the JSON 404-as-500 envelope is NEVER returned (the body of
  every response is the bytes of the on-disk asset, not the
  ``{"error": ...}`` shape);
* no response carries ``WWW-Authenticate`` or 401 status (auth
  must NOT be required for these assets);
* no response carries a ``Location`` header redirecting to login;
* every response carries ``X-Robots-Tag: noindex, nofollow, ...``;
* mutating methods (POST/PUT/PATCH/DELETE) return 405 on every
  route;
* source-text scan: the module does NOT import subprocess, socket,
  urllib, requests, httpx, aiohttp; does NOT reference os.environ
  or os.getenv; does NOT reference any approval-token symbol or
  decision-verb call shape (approve_(, reject_(, merge_(,
  deploy_(); does NOT reference VAPID or push_subscription_store.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_pwa_static as pwa


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


#: Synthetic install-valid manifest used as a CI-friendly stub when
#: ``frontend/dist/manifest.webmanifest`` does not exist (the unit-test
#: CI job does not run ``npm build`` so the dist artifact may be
#: missing). The stub satisfies the install-critical PWA fields the
#: tests assert on.
_SYNTHETIC_MANIFEST = (
    '{"name":"JvR Agent Control",'
    '"short_name":"AgentCtrl",'
    '"start_url":"/agent-control",'
    '"scope":"/",'
    '"display":"standalone",'
    '"icons":[{"src":"/agent-control-icon.svg",'
    '"sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'
)

#: Synthetic minimal SVG used as a CI-friendly stub. The body starts
#: with the XML prolog so the test's "starts with <?xml or <svg" check
#: passes whether the file is the real built asset or this stub.
_SYNTHETIC_SVG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 64 64" width="64" height="64">'
    '<rect width="64" height="64" fill="#0b1220"/></svg>'
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_pwa_assets_on_disk() -> None:
    """Ensure the blueprint's source files exist on disk for the test
    run. In the dev environment ``frontend/dist/*`` is populated by
    ``npm build`` and these stubs do nothing; in CI's unit job those
    files are absent and the stubs are what the blueprint serves.

    Files are written only when missing — never overwritten. The
    directory is gitignored under ``frontend/dist`` in dev; on CI the
    runner workspace is ephemeral.
    """
    targets: tuple[tuple[Path, str], ...] = (
        (pwa.FRONTEND_DIST / "manifest.webmanifest", _SYNTHETIC_MANIFEST),
        (pwa.FRONTEND_DIST / "agent-control-icon.svg", _SYNTHETIC_SVG),
    )
    for path, content in targets:
        if path.is_file():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _make_app() -> Flask:
    app = Flask(__name__)
    pwa.register_pwa_static_routes(app)
    return app


@pytest.fixture(scope="module")
def app() -> Flask:
    return _make_app()


@pytest.fixture(scope="module")
def client(app: Flask):
    return app.test_client()


# ---------------------------------------------------------------------------
# Route registration — exact route table
# ---------------------------------------------------------------------------


EXPECTED_ROUTES: tuple[tuple[str, str], ...] = (
    ("/manifest.webmanifest", "application/manifest+json"),
    ("/agent-control-icon.svg", "image/svg+xml"),
    ("/apple-touch-icon.png", "image/png"),
    ("/apple-touch-icon-precomposed.png", "image/png"),
    ("/apple-touch-icon-120x120.png", "image/png"),
    ("/apple-touch-icon-120x120-precomposed.png", "image/png"),
    ("/apple-touch-icon-152x152.png", "image/png"),
    ("/apple-touch-icon-152x152-precomposed.png", "image/png"),
    ("/apple-touch-icon-180x180.png", "image/png"),
    ("/apple-touch-icon-180x180-precomposed.png", "image/png"),
    ("/favicon.ico", "image/png"),
)


def test_register_routes_registers_exactly_eleven_routes(app: Flask) -> None:
    pwa_paths = sorted(
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule
        in {path for path, _mt in EXPECTED_ROUTES}
    )
    assert pwa_paths == sorted({path for path, _mt in EXPECTED_ROUTES}), (
        "blueprint must register exactly the eleven PWA static routes"
    )
    # Total registered URL rules from this blueprint == 11 (plus
    # Flask's auto-registered ``static`` rule which we don't count).
    blueprint_endpoints = sorted(
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith("pwa_static_")
    )
    assert len(blueprint_endpoints) == 11, (
        f"expected 11 pwa_static_* endpoints, got {blueprint_endpoints!r}"
    )


def test_no_mutating_methods_registered(app: Flask) -> None:
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("pwa_static_"):
            continue
        methods = rule.methods or set()
        assert not (methods & {"POST", "PUT", "PATCH", "DELETE"}), (
            f"unexpected mutating method on {rule.rule}: {methods}"
        )


@pytest.mark.parametrize("path,_mt", EXPECTED_ROUTES)
def test_mutating_methods_return_405(
    client: Any, path: str, _mt: str
) -> None:
    for method in ("post", "put", "patch", "delete"):
        res = getattr(client, method)(path)
        assert res.status_code == 405, (
            f"{method.upper()} {path} should be 405, got {res.status_code}"
        )


# ---------------------------------------------------------------------------
# Happy path — every route serves the on-disk asset
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,mimetype", EXPECTED_ROUTES)
def test_route_returns_200_and_correct_mimetype(
    client: Any, path: str, mimetype: str
) -> None:
    res = client.get(path)
    assert res.status_code == 200, (
        f"GET {path} should be 200 (got {res.status_code}); "
        f"body: {res.data[:200]!r}"
    )
    assert mimetype in (res.mimetype or ""), (
        f"GET {path} should have mimetype starting with {mimetype!r}, "
        f"got {res.mimetype!r}"
    )


def test_manifest_body_is_parseable_pwa_manifest(client: Any) -> None:
    """The manifest body must be valid JSON with the canonical PWA
    fields the iOS Safari install heuristic checks. We do not pin
    every field (the manifest evolves), just the install-critical
    set."""
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    body = json.loads(res.data.decode("utf-8"))
    for field in ("name", "start_url", "scope", "display", "icons"):
        assert field in body, (
            f"manifest missing install-critical field: {field!r}"
        )
    icons = body["icons"]
    assert isinstance(icons, list) and icons, (
        "manifest.icons must be a non-empty list for installability"
    )


def test_svg_body_starts_with_svg_marker(client: Any) -> None:
    res = client.get("/agent-control-icon.svg")
    assert res.status_code == 200
    head = res.data[:512].decode("utf-8", errors="replace").lstrip()
    # Either XML prolog or direct <svg root must appear in the first
    # few hundred bytes — defense in depth that we are serving the
    # actual SVG and not a stray PNG.
    assert head.startswith("<?xml") or "<svg" in head, (
        f"SVG body unexpected; first 200 bytes: {res.data[:200]!r}"
    )


@pytest.mark.parametrize(
    "path",
    [path for path, mt in EXPECTED_ROUTES if mt == "image/png"],
)
def test_png_body_starts_with_png_signature(
    client: Any, path: str
) -> None:
    """Every PNG-served route must serve a real PNG (signature
    ``\\x89PNG\\r\\n\\x1a\\n``). This includes the /favicon.ico
    fallback, which we deliberately serve as a PNG."""
    res = client.get(path)
    assert res.status_code == 200
    assert res.data[:8] == b"\x89PNG\r\n\x1a\n", (
        f"{path} did not serve a valid PNG (first 16 bytes: "
        f"{res.data[:16]!r})"
    )


# ---------------------------------------------------------------------------
# Negative pins — no JSON 404-as-500 envelope, no auth challenge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,_mt", EXPECTED_ROUTES)
def test_response_is_not_json_404_as_500_envelope(
    client: Any, path: str, _mt: str
) -> None:
    """Regression guard against the production bug: the global
    error handler in dashboard.py turns 404 into 500 with the
    ``{"error":..., "data":[]}`` JSON envelope. After this fix,
    that envelope must NEVER be the body for these paths."""
    res = client.get(path)
    assert res.status_code != 500, (
        f"GET {path} returned 500 (regression of the JSON-404-as-500 bug)"
    )
    # The asset bytes must not parse as the error envelope. A
    # response is JSON-error-envelope-shaped if it parses and
    # contains both the "error" and "data" keys at top level.
    try:
        body = json.loads(res.data.decode("utf-8", errors="replace"))
        if isinstance(body, dict):
            assert not ("error" in body and "data" in body), (
                f"GET {path} returned the JSON 404-as-500 envelope: {body!r}"
            )
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Binary asset (PNG/SVG bytes). Cannot match the envelope shape.
        pass


@pytest.mark.parametrize("path,_mt", EXPECTED_ROUTES)
def test_response_does_not_challenge_or_redirect_to_login(
    client: Any, path: str, _mt: str
) -> None:
    """iOS Safari fetches these assets WITHOUT credentials during
    PWA install. A 401 or a 302 to /login would break the install
    flow."""
    res = client.get(path)
    assert res.status_code == 200, (
        f"GET {path} should be 200; got {res.status_code}"
    )
    assert "WWW-Authenticate" not in res.headers, (
        f"GET {path} unexpectedly issued an auth challenge"
    )
    location = res.headers.get("Location", "")
    assert "/login" not in location, (
        f"GET {path} unexpectedly redirected to login: {location!r}"
    )


# ---------------------------------------------------------------------------
# X-Robots-Tag header
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,_mt", EXPECTED_ROUTES)
def test_response_carries_x_robots_tag(
    client: Any, path: str, _mt: str
) -> None:
    res = client.get(path)
    assert "X-Robots-Tag" in res.headers, (
        f"GET {path} did not set X-Robots-Tag"
    )
    tag = res.headers["X-Robots-Tag"].lower()
    for word in ("noindex", "nofollow", "noarchive", "nosnippet"):
        assert word in tag, (
            f"X-Robots-Tag on {path} missing {word!r}: {tag!r}"
        )


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants by import
# ---------------------------------------------------------------------------


def test_step5_invariants_intact_by_import() -> None:
    assert pwa.step5_implementation_allowed is False
    assert pwa.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(pwa.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_or_network_imports() -> None:
    forbidden = {
        "subprocess",
        "socket",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "selectors",
        "asyncio",
    }
    overlap = _imported_module_names() & forbidden
    assert not overlap, (
        f"api_pwa_static must not import network/subprocess modules: {overlap!r}"
    )


def test_no_forbidden_subsystem_imports() -> None:
    """No imports of dashboards's mutating subsystems or research
    paths. The blueprint is pure file-serve."""
    forbidden_prefixes = (
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
        # Push dispatch and approval surface stay out of this
        # blueprint by construction:
        "reporting.push_subscription_store",
        "reporting.web_push_dispatch",
        "reporting.approval_token_runtime",
        "reporting.approval_token_gate",
        "dashboard.api_push_subscribe",
        "dashboard.api_push_dispatch",
        "dashboard.api_approval_token_gate",
    )
    names = _imported_module_names()
    for prefix in forbidden_prefixes:
        for name in names:
            assert not (name == prefix or name.startswith(prefix + ".")), (
                f"api_pwa_static must not import {prefix!r}; got {name!r}"
            )


def test_no_env_access_in_source() -> None:
    text = _module_source()
    forbidden = ("os.environ", "os.getenv", "environ[")
    for tok in forbidden:
        assert tok not in text, (
            f"api_pwa_static must not access env: {tok!r}"
        )


def test_no_decision_verb_call_shape() -> None:
    text = _module_source().lower()
    forbidden_call_shapes = [
        "approve_(",
        "reject_(",
        "merge_(",
        "deploy_(",
        "execute_merge(",
        "execute_approve(",
    ]
    for shape in forbidden_call_shapes:
        assert shape not in text, (
            f"api_pwa_static contains a forbidden decision-verb shape: {shape!r}"
        )


def test_no_approval_token_or_vapid_reference() -> None:
    text = _module_source()
    forbidden = (
        "ADE_APPROVAL_TOKEN_HMAC_SECRET",
        "approval_token",
        "VAPID",
        "vapid_private",
        "p256dh",
        "BEGIN PRIVATE KEY",
    )
    for tok in forbidden:
        assert tok not in text, (
            f"api_pwa_static must not reference {tok!r}"
        )


def test_no_subprocess_or_gh_or_git_literal_in_source() -> None:
    text = _module_source()
    forbidden = (
        "subprocess.run",
        "subprocess.Popen",
        "gh pr ",
        "gh api ",
        "git push",
        "git fetch",
        "git reset",
    )
    for tok in forbidden:
        assert tok not in text, (
            f"api_pwa_static contains a forbidden CLI invocation: {tok!r}"
        )


def test_no_literal_ip_address() -> None:
    """No hard-coded VPS IP in the blueprint source."""
    text = _module_source()
    ip_re = re.compile(
        r"(?<![\w.])(?!127\.0\.0\.1\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    matches = ip_re.findall(text)
    assert matches == [], (
        f"api_pwa_static contains a non-loopback IP literal: {matches!r}"
    )


# ---------------------------------------------------------------------------
# On-disk source fixtures exist (sanity: tests would otherwise pass
# only because we silently 404)
# ---------------------------------------------------------------------------


def test_dashboard_static_ships_the_apple_touch_fallback() -> None:
    """The PNG icon used as the apple-touch / favicon fallback ships
    in the repo under ``dashboard/static/``; it is not a build
    artifact and must therefore be a committed file.

    The frontend ``dist/`` manifest + svg are build artifacts that
    do not ship in source control (the deploy script rebuilds the
    frontend on the VPS), so we don't assert their on-disk presence
    here — the session-scoped fixture above ensures the tests run
    deterministically whether ``dist/`` is populated or not."""
    fallback = (
        REPO_ROOT / "dashboard" / "static" / pwa.APPLE_TOUCH_ICON_FILENAME
    )
    assert fallback.is_file(), (
        f"committed apple-touch / favicon PNG fallback missing: {fallback}"
    )


# ---------------------------------------------------------------------------
# Co-existence: existing /sw.js and /sw-push.js routes in dashboard.py
# must not be shadowed by this blueprint
# ---------------------------------------------------------------------------


def test_blueprint_does_not_register_sw_or_sw_push_paths() -> None:
    """The existing service-worker routes live in dashboard.py
    (with the ``Service-Worker-Allowed`` header). The blueprint
    must NOT shadow them — registering /sw.js or /sw-push.js here
    would silently drop the SW header."""
    app = _make_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/sw.js" not in rules, (
        "api_pwa_static must not register /sw.js (lives in dashboard.py)"
    )
    assert "/sw-push.js" not in rules, (
        "api_pwa_static must not register /sw-push.js (lives in dashboard.py)"
    )
