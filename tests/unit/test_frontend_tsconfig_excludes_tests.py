"""Hotfix pin: production tsc build excludes frontend test files.

After PR #167 (N2b-2b) the production Docker frontend build failed
because ``tsc -b`` was compiling ``frontend/src/test/*.test.ts`` as
part of the production build. Test files use node-only imports
(``node:fs``, ``node:path``, ``__dirname``) that are not in the
``DOM`` lib — and they have no place in the production bundle in
the first place.

This pin asserts that ``frontend/tsconfig.json`` excludes all the
test-file globs so a future regression that re-includes them fails
at unit-test time, not at deploy time on the VPS.

The vitest pipeline is unaffected — vitest uses its own
``frontend/vitest.config.ts`` to discover and type-check tests via
esbuild, independent of tsc.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TSCONFIG_PATH = REPO_ROOT / "frontend" / "tsconfig.json"


def _tsconfig() -> dict[str, object]:
    return json.loads(TSCONFIG_PATH.read_text(encoding="utf-8"))


def test_frontend_tsconfig_exists() -> None:
    assert TSCONFIG_PATH.is_file()


def test_frontend_tsconfig_excludes_test_directories() -> None:
    """The closed exclude list must contain at minimum the four
    test-file globs. Adding more is fine; removing any of these is
    forbidden."""
    cfg = _tsconfig()
    exclude = cfg.get("exclude")
    assert isinstance(exclude, list), (
        "frontend/tsconfig.json must define an `exclude` array"
    )
    required = {
        "src/test/**",
        "src/**/__tests__/**",
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
    }
    missing = required - set(exclude)
    assert not missing, (
        f"frontend/tsconfig.json `exclude` is missing required globs: "
        f"{sorted(missing)}"
    )


def test_frontend_tsconfig_keeps_src_in_include() -> None:
    """`include` still covers `src` so production source files are
    type-checked. The exclude is the only narrowing."""
    cfg = _tsconfig()
    include = cfg.get("include")
    assert isinstance(include, list), "`include` must be present"
    assert "src" in include, "`include` must still cover `src`"


def test_frontend_tsconfig_no_emit_remains_true() -> None:
    """Production tsc is type-check-only. Emit is handled by vite."""
    cfg = _tsconfig()
    co = cfg.get("compilerOptions")
    assert isinstance(co, dict)
    assert co.get("noEmit") is True


def test_frontend_test_file_uses_node_imports() -> None:
    """Defense-in-depth: the test file that triggered the deploy
    failure (``sw_push_click.test.ts``) does in fact import node-only
    modules. If a future refactor removes those imports, the
    `exclude` becomes unnecessary; re-evaluate then. Today the
    exclude is load-bearing."""
    sw_test = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "test"
        / "sw_push_click.test.ts"
    )
    assert sw_test.is_file()
    text = sw_test.read_text(encoding="utf-8")
    # At least one node-only import must be present, otherwise the
    # exclude no longer protects this file from a production tsc
    # regression.
    has_node_imports = (
        "node:fs" in text
        or "node:path" in text
        or "__dirname" in text
    )
    assert has_node_imports, (
        "sw_push_click.test.ts no longer uses node-only imports; "
        "either re-evaluate the tsconfig exclude or document why it "
        "stays."
    )


def test_webpush_lib_uses_array_buffer_for_application_server_key() -> None:
    """The VAPID public key conversion must return an ArrayBuffer,
    not a Uint8Array, to satisfy strict tsc lib.dom.d.ts typing for
    `PushManager.subscribe({ applicationServerKey })`. This is the
    other half of the v3.15.16.N2b2b deploy fix."""
    src = (
        REPO_ROOT / "frontend" / "src" / "lib" / "webPush.ts"
    ).read_text(encoding="utf-8")
    # The exported helper exists and returns ArrayBuffer.
    assert "export function base64UrlToArrayBuffer(" in src, (
        "webPush.ts must export base64UrlToArrayBuffer"
    )
    assert "): ArrayBuffer {" in src, (
        "base64UrlToArrayBuffer must declare ArrayBuffer return type"
    )
    # The subscribe call uses the helper.
    assert "applicationServerKey: base64UrlToArrayBuffer(vapid)" in src, (
        "subscribeToPush must pass base64UrlToArrayBuffer(vapid) to "
        "PushManager.subscribe"
    )
    # The old Uint8Array-returning helper must be gone.
    assert "base64UrlToUint8Array" not in src, (
        "the old base64UrlToUint8Array helper must be removed; it "
        "returns the wrong BufferSource type"
    )
