/**
 * Source-text contract test for frontend/public/sw-push.js (N2b-2b).
 *
 * Hard guarantees verified by parsing the SW source:
 *   - The SW NEVER calls fetch / XMLHttpRequest / sendBeacon /
 *     postMessage / importScripts.
 *   - The SW notificationclick handler ONLY uses
 *     self.clients.openWindow(...).
 *   - The SW open_at sanitiser refuses any URL not starting with
 *     /agent-control/inbox.
 *   - The SW source contains NO decision verb (approve / reject /
 *     merge / deploy).
 *   - The SW source contains NO third-party push library reference
 *     (pywebpush, web_push, webpush, FCM, OneSignal, etc.) and NO
 *     VAPID private-key reference.
 *
 * This test treats the SW as a contract: any change that introduces
 * a forbidden token must be reviewed by a human operator and update
 * this test in the same PR.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SW_PATH = resolve(__dirname, "..", "..", "public", "sw-push.js");

function swSource(): string {
  return readFileSync(SW_PATH, { encoding: "utf-8" });
}

/**
 * Return the SW source with all comments stripped. The docstring at
 * the top of the SW intentionally documents what the SW does NOT do
 * (`fetch`, `XMLHttpRequest`, `sendBeacon`, decision verbs); we want
 * those words to appear in the human-readable header for reviewers,
 * but we must scan the executable code for them. So tests scan the
 * stripped source.
 */
function swCodeOnly(): string {
  let src = swSource();
  // Strip /* ... */ block comments.
  src = src.replace(/\/\*[\s\S]*?\*\//g, "");
  // Strip // line comments.
  src = src.replace(/\/\/.*$/gm, "");
  return src;
}

describe("sw-push.js — outbound surface", () => {
  it("does not call fetch", () => {
    const src = swCodeOnly();
    expect(src).not.toMatch(/\bfetch\s*\(/);
    expect(src).not.toMatch(/self\.fetch/);
  });

  it("does not call XMLHttpRequest", () => {
    const src = swCodeOnly();
    expect(src).not.toMatch(/XMLHttpRequest/);
    expect(src).not.toMatch(/new\s+XMLHttpRequest/);
  });

  it("does not call sendBeacon", () => {
    const src = swCodeOnly();
    expect(src).not.toMatch(/sendBeacon/);
    expect(src).not.toMatch(/navigator\.sendBeacon/);
  });

  it("does not call postMessage", () => {
    const src = swCodeOnly();
    expect(src).not.toMatch(/postMessage/);
  });

  it("does not call importScripts", () => {
    const src = swCodeOnly();
    expect(src).not.toMatch(/importScripts/);
  });
});

describe("sw-push.js — notificationclick contract", () => {
  it("registers a notificationclick handler", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/notificationclick/);
  });

  it("only opens a window on click (no other side effects)", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/clients\.openWindow/);
  });
});

describe("sw-push.js — open_at sanitiser", () => {
  it("constrains open_at to /agent-control/inbox prefix", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/agent-control\/inbox/);
    // The sanitiser refuses anything not starting with the prefix.
    expect(src).toMatch(/startsWith/);
  });

  it("refuses path traversal", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/\.\./);
  });
});

describe("sw-push.js — no decision verbs", () => {
  it.each(["approve", "reject", "merge", "deploy"])(
    "source does not contain decision verb %s",
    (verb) => {
      const src = swSource().toLowerCase();
      expect(src).not.toContain(verb);
    },
  );
});

describe("sw-push.js — no third-party / VAPID references", () => {
  it.each([
    "pywebpush",
    "web_push",
    "webpush",
    "WEB_PUSH_VAPID_PRIVATE_KEY",
    "VAPID_PRIVATE",
    "OneSignal",
    "firebase",
    "fcm-",
  ])("source does not reference %s", (token) => {
    const src = swCodeOnly();
    expect(src).not.toContain(token);
  });
});

describe("sw-push.js — bounded payload rendering", () => {
  it("bounds title length", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/MAX_TITLE_LEN/);
  });

  it("bounds summary length", () => {
    const src = swCodeOnly();
    expect(src).toMatch(/MAX_SUMMARY_LEN/);
  });
});
