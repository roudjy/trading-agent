"""PWA root static-asset routes (read-only, unauthenticated, UNWIRED).

Adds explicit Flask routes for the root PWA assets that iOS Safari
probes during PWA install / re-install / Web Push subscribe. Before
this blueprint existed those paths fell through to Flask's
``NotFound`` exception, which the global ``@app.errorhandler(Exception)``
in ``dashboard/dashboard.py`` converted into HTTP 500 with the
generic JSON ``{"error": ..., "data": []}`` envelope. iOS then saw
the manifest / icon fetches "fail" and refused to enter the PWA
install / push subscribe state, even though the app shell itself
was healthy.

The routes here serve **only** files that already exist on disk
inside the dashboard container (or in the repo working tree). No
synthesis, no template rendering, no env access, no subprocess, no
network call. ``send_from_directory`` is used for every response,
which is the canonical Flask helper for static file serving and
includes built-in path-traversal protection — the filename is
hard-coded in every route, so an attacker cannot influence which
file is served.

Hard guarantees (pinned by tests)
---------------------------------

* Eleven GET routes, exact paths and filenames pinned:

    GET /manifest.webmanifest
    GET /agent-control-icon.svg
    GET /apple-touch-icon.png
    GET /apple-touch-icon-precomposed.png
    GET /apple-touch-icon-120x120.png
    GET /apple-touch-icon-120x120-precomposed.png
    GET /apple-touch-icon-152x152.png
    GET /apple-touch-icon-152x152-precomposed.png
    GET /apple-touch-icon-180x180.png
    GET /apple-touch-icon-180x180-precomposed.png
    GET /favicon.ico

* No mutating method is registered (POST/PUT/PATCH/DELETE → 405).
* No ``@requires_auth`` — iOS Safari fetches the manifest and
  icons WITHOUT credentials during PWA install, and an auth
  challenge would break the install flow. The served assets
  contain no secret material (manifest is the public PWA
  declaration; icons are public branding).
* ``X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`` set
  on every response, consistent with the existing SPA index
  static responses.
* Closed MIME-type vocabulary per asset class:

    manifest.webmanifest  → application/manifest+json
    *.svg                 → image/svg+xml
    *.png and favicon.ico → image/png

  (The .ico URL is served as image/png because no real .ico
  ships in the repo and modern browsers accept image/png on the
  .ico URL. This is a documented safe fallback; the alternative
  was 204 No Content which leaves Safari without a usable icon.)

* No subprocess, no network, no ``gh``, no ``git``, no
  approval-token reference, and no executable decision-verb
  call shape (the AST/source-text scan in the unit-test pins
  every forbidden pattern explicitly so they need not be
  repeated as literals here).
* No process-environment access from this module — the pin-test
  forbids the canonical env-read attribute names from appearing
  in the source.
* Importing this module does NOT flip Step 5 invariants.

Wiring
------

This blueprint is **NOT** wired into ``dashboard/dashboard.py`` in
the PR that ships it. Wiring is the operator's two-line diff (per
``execution_authority.md``):

::

    from dashboard.api_pwa_static import register_pwa_static_routes
    register_pwa_static_routes(app)

The accompanying ``tests/unit/test_dashboard_pwa_static_routes_wired.py``
uses the skip-or-enforce-consistency pattern: both the import and
the register-call must be present together, or both must be
absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, send_from_directory

MODULE_VERSION: Final[str] = "v3.15.16.pwa_static"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Source directories (absolute, derived once at import time)
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
FRONTEND_DIST: Final[Path] = REPO_ROOT / "frontend" / "dist"
DASHBOARD_STATIC: Final[Path] = REPO_ROOT / "dashboard" / "static"


# ---------------------------------------------------------------------------
# MIME-type constants (closed vocabulary)
# ---------------------------------------------------------------------------

MIME_MANIFEST: Final[str] = "application/manifest+json"
MIME_SVG: Final[str] = "image/svg+xml"
MIME_PNG: Final[str] = "image/png"

#: ``X-Robots-Tag`` value applied to every response served from this
#: blueprint. Consistent with the SPA index route in dashboard.py.
NOINDEX_HEADER: Final[str] = "noindex, nofollow, noarchive, nosnippet"


# ---------------------------------------------------------------------------
# Apple-touch-icon fallback filename
# ---------------------------------------------------------------------------

#: The single existing PNG icon we serve back for every iOS Safari
#: apple-touch-icon probe and for the .ico URL. 192×192 is the
#: largest unambiguously-installable size we have on disk; iOS
#: re-scales it on the device, so serving one size for every probe
#: path is a documented safe fallback. This filename is hard-coded
#: here so URL-controlled path-traversal is impossible.
APPLE_TOUCH_ICON_FILENAME: Final[str] = "icon-192.png"


# ---------------------------------------------------------------------------
# Route table (closed and exact)
#
# Tuple shape: (url_path, source_dir, filename, mimetype, endpoint).
# Every entry is GET-only by construction; the register helper below
# pins methods=["GET"] explicitly. Adding a new path here requires
# updating the route-pin test in tests/unit/test_dashboard_api_pwa_static.py
# in the same PR.
# ---------------------------------------------------------------------------

_PWA_STATIC_ROUTES: Final[tuple[tuple[str, Path, str, str, str], ...]] = (
    (
        "/manifest.webmanifest",
        FRONTEND_DIST,
        "manifest.webmanifest",
        MIME_MANIFEST,
        "pwa_static_manifest_webmanifest",
    ),
    (
        "/agent-control-icon.svg",
        FRONTEND_DIST,
        "agent-control-icon.svg",
        MIME_SVG,
        "pwa_static_agent_control_icon_svg",
    ),
    (
        "/apple-touch-icon.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon",
    ),
    (
        "/apple-touch-icon-precomposed.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_precomposed",
    ),
    (
        "/apple-touch-icon-120x120.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_120",
    ),
    (
        "/apple-touch-icon-120x120-precomposed.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_120_precomposed",
    ),
    (
        "/apple-touch-icon-152x152.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_152",
    ),
    (
        "/apple-touch-icon-152x152-precomposed.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_152_precomposed",
    ),
    (
        "/apple-touch-icon-180x180.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_180",
    ),
    (
        "/apple-touch-icon-180x180-precomposed.png",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        MIME_PNG,
        "pwa_static_apple_touch_icon_180_precomposed",
    ),
    (
        "/favicon.ico",
        DASHBOARD_STATIC,
        APPLE_TOUCH_ICON_FILENAME,
        # No real .ico is shipped; modern browsers accept image/png
        # on the .ico URL and treat it as a favicon. See
        # https://developer.mozilla.org/en-US/docs/Web/HTML/Element/link
        # ("Notes" on icon and shortcut-icon).
        MIME_PNG,
        "pwa_static_favicon_ico",
    ),
)


# ---------------------------------------------------------------------------
# View factory
# ---------------------------------------------------------------------------


def _make_view(
    source_dir: Path,
    filename: str,
    mimetype: str,
) -> Any:
    """Return a closure that serves the named static asset.

    The filename is captured at registration time and is NOT
    URL-controlled; ``send_from_directory`` provides defense in
    depth against any pathological filename anyway.
    """

    def view() -> Response:
        resp = send_from_directory(
            str(source_dir),
            filename,
            mimetype=mimetype,
        )
        resp.headers["X-Robots-Tag"] = NOINDEX_HEADER
        return resp

    return view


# ---------------------------------------------------------------------------
# Register helper
# ---------------------------------------------------------------------------


def register_pwa_static_routes(app: Flask) -> None:
    """Register the eleven root PWA static-asset routes.

    NOT wired into ``dashboard/dashboard.py`` in this PR. The
    operator-only two-line wiring change is:

    ::

        from dashboard.api_pwa_static import register_pwa_static_routes
        register_pwa_static_routes(app)

    Idempotent within a single ``Flask`` instance only because each
    ``endpoint`` name is unique; calling this twice on the same app
    raises ``AssertionError`` from Flask. Tests instantiate a fresh
    ``Flask`` for each call.
    """
    for path, source_dir, filename, mimetype, endpoint in _PWA_STATIC_ROUTES:
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=_make_view(source_dir, filename, mimetype),
            methods=["GET"],
        )


__all__ = [
    "APPLE_TOUCH_ICON_FILENAME",
    "DASHBOARD_STATIC",
    "FRONTEND_DIST",
    "MIME_MANIFEST",
    "MIME_PNG",
    "MIME_SVG",
    "MODULE_VERSION",
    "NOINDEX_HEADER",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "_PWA_STATIC_ROUTES",
    "register_pwa_static_routes",
    "step5_implementation_allowed",
]
