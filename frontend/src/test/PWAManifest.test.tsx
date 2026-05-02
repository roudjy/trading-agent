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
