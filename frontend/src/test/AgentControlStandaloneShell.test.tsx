/**
 * Standalone-shell regression tests for v3.15.15.26.2.
 *
 * Goal: prove that ``/agent-control`` renders WITHOUT the legacy
 * ``<AppShell>`` chrome (sidebar / topbar / ticker / .shell /
 * .qre-app wrappers) — the operator wanted a real mobile-first
 * standalone PWA, not the new IA embedded inside the old shell.
 *
 * Two complementary checks:
 *
 *   1. Source-text guard on ``App.tsx``: the ``/agent-control``
 *      route is wired as a parallel top-level route, NOT nested
 *      inside the wildcard route that wraps ``<AppShell>``.
 *
 *   2. End-to-end runtime: render the full ``<App>`` with auth
 *      mocked, navigate to ``/agent-control``, and assert:
 *        - ``agent-control-root`` is present;
 *        - no element with the ``shell`` class;
 *        - no element with the ``qre-app`` class;
 *        - no element with the ``shell__main`` class;
 *      then navigate to ``/`` (the dashboard root) and assert
 *      the ``.shell`` / ``.qre-app`` chrome IS present (the
 *      legacy routes must still wear it).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import appRaw from "../App.tsx?raw";

// --------------------------------------------------------------------- //
// Source-text guard                                                       //
// --------------------------------------------------------------------- //

describe("App.tsx — /agent-control is lifted out of <AppShell>", () => {
  it("declares /agent-control as a top-level route, not nested inside the wildcard", () => {
    // The /agent-control route element must appear BEFORE the
    // wildcard ``path="*"`` route element. We use a regex anchor:
    // the agent-control route must precede the wildcard route in
    // the source text.
    const agentControlIdx = appRaw.indexOf('path="/agent-control"');
    const wildcardIdx = appRaw.indexOf('path="*"');
    expect(agentControlIdx).toBeGreaterThan(0);
    expect(wildcardIdx).toBeGreaterThan(0);
    expect(agentControlIdx).toBeLessThan(wildcardIdx);
  });

  it("the /agent-control route element does NOT contain <AppShell>", () => {
    // Find the /agent-control route block and the next sibling
    // (the wildcard route). Slice between them and confirm
    // <AppShell> does not appear in that slice.
    const start = appRaw.indexOf('path="/agent-control"');
    const end = appRaw.indexOf('path="*"', start);
    expect(start).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(start);
    const slice = appRaw.slice(start, end);
    expect(slice).not.toMatch(/<AppShell\b/);
    // It MUST still wrap the route in RequireAuth so unauthenticated
    // operators get bounced to /login.
    expect(slice).toMatch(/<RequireAuth>/);
    expect(slice).toMatch(/<AgentControl\s*\/>/);
  });

  it("the wildcard route still wraps legacy routes in <AppShell>", () => {
    const wildcardIdx = appRaw.indexOf('path="*"');
    const remainder = appRaw.slice(wildcardIdx);
    expect(remainder).toMatch(/<AppShell>/);
    // Sanity: legacy routes are still inside AppShell.
    expect(remainder).toMatch(/path="\/sprint"/);
    expect(remainder).toMatch(/path="\/campaigns"/);
    expect(remainder).toMatch(/path="\/observability"/);
  });

  it("the AppShell-wrapped block does NOT contain a /agent-control route", () => {
    const wildcardIdx = appRaw.indexOf('path="*"');
    const remainder = appRaw.slice(wildcardIdx);
    expect(remainder).not.toMatch(/path="\/agent-control"/);
  });
});

// --------------------------------------------------------------------- //
// End-to-end runtime guard                                                //
// --------------------------------------------------------------------- //

const fetchSpy: Array<{ url: string; method: string }> = [];

function installFetchMock(routes: Record<string, () => Response>) {
  const fetchImpl: typeof fetch = async (input: any, init: any = {}) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    fetchSpy.push({ url, method: init.method || "GET" });
    for (const [path, build] of Object.entries(routes)) {
      if (url === path || url.endsWith(path)) {
        return build();
      }
    }
    // Default: 200 OK with empty payload — keeps AuthProvider happy
    // for /presets without exposing real data.
    return new Response(
      JSON.stringify({ status: "not_available", presets: [] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };
  // @ts-expect-error — assigning the global fetch is intentional in test scope.
  global.fetch = vi.fn(fetchImpl);
}

function jsonResp(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchSpy.length = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App runtime — /agent-control renders standalone", () => {
  it("does not render Sidebar / TopBar / Ticker / .shell / .qre-app", async () => {
    installFetchMock({
      "/api/presets": () => jsonResp({ presets: [] }),
      "/api/agent-control/status": () =>
        jsonResp({
          kind: "agent_control_status",
          schema_version: 1,
          governance_status: { status: "ok", data: {} },
          frozen_hashes: { status: "ok", data: {} },
        }),
      "/api/agent-control/activity": () =>
        jsonResp({
          kind: "agent_control_activity",
          schema_version: 1,
          status: "ok",
          data: {
            schema_version: 1,
            report_kind: "agent_audit_timeline",
            ledger_path: "logs/x.jsonl",
            ledger_present: true,
            ledger_event_count: 0,
            chain_status: "intact",
            rows: [],
          },
        }),
      "/api/agent-control/workloop": () =>
        jsonResp({
          kind: "agent_control_workloop",
          schema_version: 1,
          status: "ok",
          data: { mode: "dry-run" },
          artifact_path: "logs/x.json",
        }),
      "/api/agent-control/pr-lifecycle": () =>
        jsonResp({
          kind: "agent_control_pr_lifecycle",
          schema_version: 1,
          status: "ok",
          data: { schema_version: 1, final_recommendation: "no_open_prs", prs: [] },
          artifact_path: "logs/x.json",
        }),
      "/api/agent-control/notifications": () =>
        jsonResp({
          kind: "agent_control_notifications",
          schema_version: 1,
          status: "ok",
          mode: "placeholder",
          data: [],
        }),
      "/api/agent-control/proposals": () =>
        jsonResp({
          kind: "agent_control_proposals",
          schema_version: 1,
          status: "ok",
          data: {
            schema_version: 1,
            final_recommendation: "no_proposals",
            proposals: [],
          },
          artifact_path: "logs/x.json",
        }),
      "/api/agent-control/approval-inbox": () =>
        jsonResp({
          kind: "agent_control_approval_inbox",
          schema_version: 1,
          status: "ok",
          data: { schema_version: 1, final_recommendation: "no_items", items: [] },
          artifact_path: "logs/x.json",
        }),
      "/api/agent-control/execute-safe": () =>
        jsonResp({
          kind: "agent_control_execute_safe",
          schema_version: 1,
          status: "ok",
          data: {
            schema_version: 1,
            actions: [],
            counts: { total: 0, by_eligibility: {}, by_risk_class: {} },
          },
        }),
    });

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <App />
      </MemoryRouter>,
    );

    // AgentControl mounts via the auth probe -> /api/presets.
    const root = await screen.findByTestId("agent-control-root", {}, { timeout: 5000 });
    expect(root).toBeInTheDocument();

    // No legacy chrome wrappers.
    expect(document.querySelector(".shell")).toBeNull();
    expect(document.querySelector(".shell__main")).toBeNull();
    expect(document.querySelector(".qre-app")).toBeNull();

    // No Sidebar / TopBar / Ticker presence (their classes are
    // ``shell__sidebar`` / ``shell__topbar`` / ``ticker``;
    // none should be in the DOM at /agent-control).
    expect(document.querySelector(".shell__sidebar")).toBeNull();
    expect(document.querySelector(".shell__topbar")).toBeNull();
    expect(document.querySelector(".ticker")).toBeNull();
  });
});

describe("App runtime — legacy dashboard root still wears <AppShell>", () => {
  it("renders the .shell / .qre-app wrappers at /", async () => {
    installFetchMock({
      "/api/presets": () => jsonResp({ presets: [] }),
      // The dashboard hits a number of API endpoints; default mock
      // returns an empty 200 envelope which is enough to render the
      // shell.
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    // Wait for the shell to appear (auth probe + dashboard mount).
    await waitFor(
      () => {
        expect(document.querySelector(".qre-app")).not.toBeNull();
        expect(document.querySelector(".shell")).not.toBeNull();
      },
      { timeout: 5000 },
    );
  });
});
