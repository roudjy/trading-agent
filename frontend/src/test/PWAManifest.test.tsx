/**
 * PWA installability fixture tests for v3.15.15.18.
 *
 * Verified properties:
 *   - manifest.webmanifest declares the required installable fields
 *     (name, short_name, start_url, display, icons[]).
 *   - sw.js never POSTs/PUTs/PATCHes/DELETEs (only GET).
 *   - sw.js never references analytics or external services.
 *   - main.tsx contains the SW registration call.
 *   - index.html links the manifest and an icon.
 *
 * These are static-content checks. Files are loaded via Vite's
 * ``?raw`` query, which keeps the tests stdlib-free (no node: imports
 * required for the production tsc -b build).
 */

import { describe, expect, it } from "vitest";
// Vite-native raw imports — no node:fs / node:path dependency.
// These resolve at vitest-load time relative to this test file.
import manifestRaw from "../../public/manifest.webmanifest?raw";
import swRaw from "../../public/sw.js?raw";
import mainRaw from "../main.tsx?raw";
import indexHtmlRaw from "../../index.html?raw";

describe("PWA: manifest", () => {
  it("declares the installability fields", () => {
    const m = JSON.parse(manifestRaw);
    expect(typeof m.name).toBe("string");
    expect(m.name.length).toBeGreaterThan(0);
    expect(typeof m.short_name).toBe("string");
    expect(typeof m.start_url).toBe("string");
    expect(["standalone", "fullscreen", "minimal-ui"]).toContain(m.display);
    expect(Array.isArray(m.icons)).toBe(true);
    expect(m.icons.length).toBeGreaterThanOrEqual(1);
    for (const icon of m.icons) {
      expect(typeof icon.src).toBe("string");
      expect(typeof icon.sizes).toBe("string");
      expect(typeof icon.type).toBe("string");
    }
    expect(typeof m.theme_color).toBe("string");
    expect(typeof m.background_color).toBe("string");
  });

  it("index.html links the manifest and the SVG icon", () => {
    expect(indexHtmlRaw).toMatch(/<link[^>]+rel="manifest"/);
    expect(indexHtmlRaw).toMatch(/<link[^>]+rel="icon"/);
    expect(indexHtmlRaw).toMatch(/manifest\.webmanifest/);
  });
});

describe("PWA: service worker", () => {
  it("only handles GET requests (filters non-GET early)", () => {
    expect(swRaw).toMatch(/req\.method !== ["']GET["']/);
  });

  it("does not call any mutating fetch verb directly", () => {
    for (const verb of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(swRaw).not.toContain(`method: "${verb}"`);
      expect(swRaw).not.toContain(`method:'${verb}'`);
    }
  });

  it("does not reach external analytics or services", () => {
    expect(swRaw).not.toMatch(
      /google-analytics|googletagmanager|sentry|datadog|segment\.io/i,
    );
    expect(swRaw).not.toMatch(/https?:\/\//);
  });

  it("registers caches for both shell and runtime", () => {
    expect(swRaw).toMatch(/SHELL_CACHE/);
    expect(swRaw).toMatch(/RUNTIME_CACHE/);
  });
});

describe("PWA: registration", () => {
  it("main.tsx registers the service worker behind a feature check", () => {
    expect(mainRaw).toMatch(/serviceWorker/);
    expect(mainRaw).toMatch(/register\(["']\/sw\.js["']/);
    expect(mainRaw).toMatch(/\.catch\(/);
  });
});

describe("PWA: service worker cache versioning (v3.15.15.26.1)", () => {
  it("declares a versioned SW_VERSION constant tied to the release", () => {
    // The fix is anchored on a single SW_VERSION constant so future
    // releases bump exactly one place. The constant must be a real
    // version string (not the legacy "v1") so it visibly differs
    // from any installed pre-26 SW.
    expect(swRaw).toMatch(/SW_VERSION\s*=\s*["']v3\.15\.15\./);
  });

  it("uses version-stamped cache names for shell + runtime", () => {
    expect(swRaw).toMatch(/agent-control-shell-\$\{SW_VERSION\}/);
    expect(swRaw).toMatch(/agent-control-runtime-\$\{SW_VERSION\}/);
  });

  it("activate handler purges any cache name not matching the current SW_VERSION", () => {
    // The fix: instead of allowing only legacy v1 cache names, the
    // activate handler now uses a SET of known names and deletes
    // every cache whose name is NOT in that set. That is what
    // forces stale pre-26 caches to actually go away.
    expect(swRaw).toMatch(/KNOWN_CACHE_NAMES/);
    expect(swRaw).toMatch(/!KNOWN_CACHE_NAMES\.has\(k\)/);
    expect(swRaw).toMatch(/caches\.delete\(k\)/);
  });

  it("install calls skipWaiting and activate calls clients.claim for prompt update", () => {
    expect(swRaw).toMatch(/self\.skipWaiting\(\)/);
    expect(swRaw).toMatch(/self\.clients\.claim\(\)/);
  });

  it("shell HTML uses stale-while-revalidate, not permanent cache-first", () => {
    // The pre-fix bug: ``/agent-control`` was served cache-first,
    // so a new build never reached the user. The fix routes shell
    // navigation through staleWhileRevalidate.
    expect(swRaw).toMatch(/staleWhileRevalidate\s*\(/);
    // The shell-route block routes / and /agent-control through
    // stale-while-revalidate.
    expect(swRaw).toMatch(/url\.pathname === ["']\/agent-control["']/);
  });

  it("API routes are network-first, not stale-while-revalidate", () => {
    // /api/* must keep network-first semantics so the operator
    // never sees stale agent-control data.
    expect(swRaw).toMatch(/url\.pathname\.startsWith\(["']\/api\/agent-control\/["']\)/);
    expect(swRaw).toMatch(/networkFirst\s*\(\s*req\s*\)/);
  });

  it("hashed assets remain cache-first", () => {
    // Vite emits content-addressed bundles under /assets/. They
    // are immutable per build, so cache-first is safe and the
    // fastest path. A new build naturally produces a new filename
    // which the SW fetches as a cache miss.
    expect(swRaw).toMatch(/url\.pathname\.startsWith\(["']\/assets\/["']\)/);
    expect(swRaw).toMatch(/cacheFirst\s*\(\s*req\s*\)/);
  });

  it("does not introduce any mutation verb in the new SW", () => {
    // Hardening regression guard: the cache-fix release must not
    // smuggle a POST/PUT/PATCH/DELETE into the SW.
    expect(swRaw).toMatch(/req\.method !== ["']GET["']/);
    for (const verb of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(swRaw).not.toContain(`method: "${verb}"`);
      expect(swRaw).not.toContain(`method:'${verb}'`);
    }
  });

  it("does not reach external services in the new SW either", () => {
    expect(swRaw).not.toMatch(
      /google-analytics|googletagmanager|sentry|datadog|segment\.io/i,
    );
    expect(swRaw).not.toMatch(/https?:\/\//);
  });
});
