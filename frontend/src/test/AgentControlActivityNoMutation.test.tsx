/**
 * Structural guards for the v3.15.16.A15.B2.0d Agent Activity Center
 * surface. These tests read the source files from disk and scan
 * targeted regions only — they do NOT scan whole files for generic
 * verb words (which would trip on copy like "merge candidate").
 *
 * Pins:
 *   - The AAC client section inside frontend/src/api/agent_control.ts
 *     uses only the GET-only envelope helper. No `method: "POST"` /
 *     `PUT` / `PATCH` / `DELETE` literal appears in that section.
 *   - AgentActivity.tsx does not contain direct fetch / XMLHttpRequest /
 *     sendBeacon literals — the route component must use the API
 *     client.
 *   - AgentActivity.tsx has no push-subscription / Notification
 *     permission / serviceWorker.register call patterns.
 *   - AgentActivity.tsx references zero /api/agent-control/activity/
 *     literal endpoint paths (must call only agentControlApi methods).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const REPO_ROOT = resolve(__dirname, "..", "..", "..");

function read(relativePath: string): string {
  return readFileSync(
    resolve(REPO_ROOT, "frontend", "src", ...relativePath.split("/")),
    "utf-8",
  );
}

// Marker strings used to slice out the AAC section in agent_control.ts.
const AAC_BEGIN =
  "v3.15.16.A15.B2.0d — Agent Activity Center read-only client.";
const AAC_END_BEFORE = "};";

function aacApiSection(): string {
  const src = read("api/agent_control.ts");
  const beginIdx = src.indexOf(AAC_BEGIN);
  if (beginIdx === -1) {
    throw new Error(
      "agent_control.ts is missing the AAC begin marker — cannot locate the client section",
    );
  }
  // The AAC client methods are the LAST entries in the agentControlApi
  // object literal. Slice from the begin marker to the first `};` line
  // that appears after the marker — robust against CRLF / LF line
  // endings and against unrelated `};` literals that may appear earlier
  // (e.g. inside type definitions).
  const after = src.slice(beginIdx);
  const match = after.match(/\r?\n\};\r?\n/);
  if (!match || match.index === undefined) {
    throw new Error(
      "agent_control.ts AAC section closing brace not found",
    );
  }
  return after.slice(0, match.index);
}

describe("AAC API client section: GET-only", () => {
  it("does not contain any non-GET method literal in the AAC section", () => {
    const section = aacApiSection();
    for (const forbidden of [
      'method: "POST"',
      "method: 'POST'",
      'method: "PUT"',
      "method: 'PUT'",
      'method: "PATCH"',
      "method: 'PATCH'",
      'method: "DELETE"',
      "method: 'DELETE'",
    ]) {
      expect(
        section.includes(forbidden),
        `AAC API client section contains forbidden literal ${forbidden}`,
      ).toBe(false);
    }
  });

  it("does not use postJsonEnvelope or any POST helper in the AAC section", () => {
    const section = aacApiSection();
    expect(section.includes("postJsonEnvelope")).toBe(false);
    expect(section.includes("postJson")).toBe(false);
  });

  it("uses getJsonEnvelope for every AAC method", () => {
    const section = aacApiSection();
    // Each of the six AAC methods must reference getJsonEnvelope.
    const expectedMethods = [
      "activityToday",
      "activityItemsList",
      "activityItemsDetail",
      "activityAgents",
      "activityArtifacts",
      "activityInvariants",
    ];
    for (const method of expectedMethods) {
      const idx = section.indexOf(method);
      expect(idx, `method ${method} missing from AAC section`).toBeGreaterThanOrEqual(0);
    }
    const matches = section.match(/getJsonEnvelope</g) || [];
    expect(matches.length).toBeGreaterThanOrEqual(6);
  });
});

describe("AgentActivity route file: no direct network", () => {
  it("does not contain a direct fetch( literal", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    // The route component must call only agentControlApi methods.
    expect(src.includes("fetch(")).toBe(false);
  });

  it("does not contain XMLHttpRequest construction", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    expect(src.includes("new XMLHttpRequest")).toBe(false);
    expect(src.includes("XMLHttpRequest()")).toBe(false);
  });

  it("does not contain navigator.sendBeacon", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    expect(src.includes("sendBeacon")).toBe(false);
  });

  it("does not contain push-subscription or notification-permission literals", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    for (const forbidden of [
      "pushManager.subscribe",
      "Notification.requestPermission",
      "serviceWorker.register",
    ]) {
      expect(
        src.includes(forbidden),
        `AgentActivity.tsx contains forbidden literal ${forbidden}`,
      ).toBe(false);
    }
  });

  it("references zero /api/agent-control/activity/ literal endpoint paths", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    // The route file must call methods on agentControlApi, not bare
    // endpoint URLs.
    expect(src.includes("/api/agent-control/activity")).toBe(false);
  });
});

describe("AgentActivity route file: clipboard pattern", () => {
  it("CopyOperatorPhraseButton uses navigator.clipboard.writeText", () => {
    const src = read("routes/AgentControl/AgentActivity.tsx");
    expect(src.includes("navigator.clipboard.writeText")).toBe(true);
  });
});
