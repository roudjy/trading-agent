/**
 * v3.15.15.21.1 — UX/styling polish + consistency tests.
 *
 * Adds the following invariants on top of the v3.15.15.18 / .19 / .20
 * AgentControl test suite:
 *
 *   1. Page exposes a top-of-page summary banner with role="status" and
 *      aria-live="polite" so screen readers announce changes.
 *   2. Banner tone reflects inbox severity: critical -> danger, high
 *      -> warn, otherwise -> ok.
 *   3. The PWA never issues a non-GET request from the cards. (The
 *      v3.15.15.18 suite already asserted this; this re-assertion
 *      lives here so the polish release re-runs the contract after
 *      the structural refactor.)
 *   4. The /agent-control route is registered in App.tsx and resolves
 *      to the AgentControl component.
 *   5. The page title element has an id matched by the main aria-labelledby.
 *   6. Refresh button carries aria-busy when loading.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AgentControl } from "../routes/AgentControl";

// --------------------------------------------------------------------- //
// Fixture bodies                                                          //
// --------------------------------------------------------------------- //

const okFrozenHashes = {
  status: "ok",
  data: {
    "research/research_latest.json":
      "4a567bd6feb98eb7aa32db4a90a3201456843088314936c5e484a2ae6a93666c",
    "research/strategy_matrix.csv":
      "ff15b8c4f35cc37b6941b712106ae71a1b82a1b5043da197731d42518d258d66",
  },
};

const okStatusBody = {
  kind: "agent_control_status",
  schema_version: 1,
  governance_status: { status: "ok", data: {} },
  frozen_hashes: okFrozenHashes,
  workloop_runtime: {
    status: "ok",
    data: {
      runtime_version: "v3.15.15.22",
      mode: "once",
      iteration: 0,
      safe_to_execute: false,
      loop_health: {
        consecutive_failures: 0,
        iterations_completed: 1,
        iterations_failed: 0,
      },
      counts: { total: 7, by_state: { ok: 7 } },
      final_recommendation: "all_sources_ok",
      source_states: [],
    },
  },
  recurring_maintenance: {
    status: "ok",
    data: {
      module_version: "v3.15.15.23",
      mode: "list",
      safe_to_execute: false,
      counts: { total: 5, by_status: { not_run: 5 } },
      final_recommendation: "all_jobs_ok",
      jobs: [],
    },
  },
};

const okActivityBody = {
  kind: "agent_control_activity",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    report_kind: "agent_audit_timeline",
    ledger_path: "logs/agent_audit.2026-05-02.jsonl",
    ledger_present: true,
    ledger_event_count: 0,
    chain_status: "intact",
    rows: [],
  },
};

const okWorkloopBody = {
  kind: "agent_control_workloop",
  schema_version: 1,
  status: "ok",
  data: {
    mode: "dry-run",
    next_recommended_item: "unknown",
    merges_performed: 0,
  },
  artifact_path: "logs/autonomous_workloop/latest.json",
};

const okPRLifecycleEmptyBody = {
  kind: "agent_control_pr_lifecycle",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    final_recommendation: "no_open_prs",
    prs: [],
  },
  artifact_path: "logs/github_pr_lifecycle/latest.json",
};

const placeholderNotificationsBody = {
  kind: "agent_control_notifications",
  schema_version: 1,
  status: "ok",
  mode: "placeholder",
  data: [],
  next_release_with_push: "v3.15.15.23",
};

const okProposalsEmptyBody = {
  kind: "agent_control_proposals",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    final_recommendation: "no_proposals",
    proposals: [],
  },
  artifact_path: "logs/proposal_queue/latest.json",
};

const okExecuteSafeBody = {
  kind: "agent_control_execute_safe",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    report_kind: "execute_safe_controls_catalog",
    module_version: "v3.15.15.21",
    git_clean: true,
    git_dirty_count: 0,
    gh_provider: { status: "available" },
    actions: [
      {
        action_id: "a_aaaaaaaa",
        action_type: "refresh_proposal_queue_dry_run",
        title: "Refresh proposal queue",
        summary: "...",
        risk_class: "LOW",
        eligibility: "eligible",
        blocked_reason: null,
      },
    ],
    counts: {
      total: 1,
      by_eligibility: { eligible: 1 },
      by_risk_class: { LOW: 1 },
    },
  },
};

function inboxBodyWithSeverity(by_severity: Record<string, number>) {
  return {
    kind: "agent_control_approval_inbox",
    schema_version: 1,
    status: "ok",
    data: {
      schema_version: 1,
      final_recommendation: "review",
      items: [],
      counts: {
        total: Object.values(by_severity).reduce((a, b) => a + b, 0),
        by_severity,
        by_category: {},
        by_status: {},
      },
    },
    artifact_path: "logs/approval_inbox/latest.json",
  };
}

// --------------------------------------------------------------------- //
// Fetch mock plumbing                                                     //
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
    return new Response(JSON.stringify({ status: "not_available" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
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

function _allOk(inbox = inboxBodyWithSeverity({})) {
  return {
    "/api/agent-control/status": () => jsonResp(okStatusBody),
    "/api/agent-control/activity": () => jsonResp(okActivityBody),
    "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
    "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
    "/api/agent-control/notifications": () => jsonResp(placeholderNotificationsBody),
    "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
    "/api/agent-control/approval-inbox": () => jsonResp(inbox),
    "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
  };
}

// --------------------------------------------------------------------- //
// Tests                                                                   //
// --------------------------------------------------------------------- //

describe("AgentControl polish — summary banner", () => {
  it("renders an ok-tone banner when nothing critical is in the inbox", async () => {
    installFetchMock(_allOk(inboxBodyWithSeverity({})));
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const banner = await screen.findByTestId("agent-control-summary");
    await waitFor(() => {
      expect(banner.className).toMatch(/agent-control__summary--ok/);
    });
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveAttribute("aria-live", "polite");
    expect(banner).toHaveTextContent(/rustig|alle/i);
  });

  it("renders a danger-tone banner when the inbox has critical items", async () => {
    installFetchMock(_allOk(inboxBodyWithSeverity({ critical: 1 })));
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const banner = await screen.findByTestId("agent-control-summary");
    await waitFor(() => {
      expect(banner.className).toMatch(/agent-control__summary--danger/);
    });
    expect(banner).toHaveTextContent(/kritiek/i);
  });

  it("renders a warn-tone banner when the inbox has high-severity items", async () => {
    installFetchMock(_allOk(inboxBodyWithSeverity({ high: 2 })));
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const banner = await screen.findByTestId("agent-control-summary");
    await waitFor(() => {
      expect(banner.className).toMatch(/agent-control__summary--warn/);
    });
    expect(banner).toHaveTextContent(/2/);
  });
});

describe("AgentControl polish — accessibility & semantic landmarks", () => {
  it("page has main + contentinfo landmarks and at least one banner", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await screen.findByTestId("agent-control-root");
    // The AgentControl component runs inside MemoryRouter directly here
    // (not inside the AppShell), so we expect exactly one main and one
    // footer / contentinfo. There may be additional banners outside the
    // component when rendered inside AppShell — assert getAllByRole.
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getAllByRole("banner").length).toBeGreaterThanOrEqual(1);
  });

  it("h1 has the id referenced by the main's aria-labelledby", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const main = await screen.findByRole("main");
    const labelId = main.getAttribute("aria-labelledby");
    expect(labelId).toBeTruthy();
    const h1 = document.getElementById(labelId!);
    expect(h1?.tagName).toBe("H1");
  });

  it("refresh button has aria-busy when loading and exposes a clear aria-label", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const btn = await screen.findByTestId("agent-control-refresh");
    // After initial load it should have aria-busy=false and a non-loading label.
    await waitFor(() => {
      expect(btn).toHaveAttribute("aria-busy", "false");
    });
    expect(btn).toHaveAttribute("aria-label");
  });

  it("grid is announced as a region with a label", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const grid = await screen.findByTestId("agent-control-grid");
    expect(grid).toHaveAttribute("aria-label");
  });
});

describe("AgentControl polish — non-GET fetch is forbidden everywhere", () => {
  it("never issues POST/PUT/PATCH/DELETE from any card", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await screen.findByTestId("agent-control-summary");
    // Initial mount triggers loadAll(); every fetch call is captured.
    for (const c of fetchSpy) {
      expect(c.method).toBe("GET");
    }
  });
});

describe("AgentControl polish — Status card runtime row (v3.15.15.22)", () => {
  it("renders the workloop_runtime row when the artifact is available", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const row = await screen.findByTestId("status-runtime-row");
    expect(row).toBeInTheDocument();
    const rec = await screen.findByTestId("status-runtime-recommendation");
    expect(rec).toHaveTextContent("all_sources_ok");
  });

  it("renders runtime row as unknown when status payload omits workloop_runtime", async () => {
    const statusBodyNoRuntime = {
      kind: "agent_control_status",
      schema_version: 1,
      governance_status: { status: "ok", data: {} },
      frozen_hashes: okFrozenHashes,
    };
    installFetchMock({
      ..._allOk(),
      "/api/agent-control/status": () => jsonResp(statusBodyNoRuntime),
    });
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const row = await screen.findByTestId("status-runtime-row");
    expect(row).toBeInTheDocument();
    // No recommendation row when runtime is not available.
    expect(
      screen.queryByTestId("status-runtime-recommendation"),
    ).not.toBeInTheDocument();
  });
});

describe("AgentControl polish — Status card maintenance row (v3.15.15.23)", () => {
  it("renders the recurring_maintenance row when the artifact is available", async () => {
    installFetchMock(_allOk());
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const row = await screen.findByTestId("status-maintenance-row");
    expect(row).toBeInTheDocument();
    const rec = await screen.findByTestId("status-maintenance-recommendation");
    expect(rec).toHaveTextContent("all_jobs_ok");
  });

  it("renders maintenance row as unknown when status payload omits recurring_maintenance", async () => {
    const statusBodyNoMaintenance = {
      kind: "agent_control_status",
      schema_version: 1,
      governance_status: { status: "ok", data: {} },
      frozen_hashes: okFrozenHashes,
    };
    installFetchMock({
      ..._allOk(),
      "/api/agent-control/status": () => jsonResp(statusBodyNoMaintenance),
    });
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    const row = await screen.findByTestId("status-maintenance-row");
    expect(row).toBeInTheDocument();
    expect(
      screen.queryByTestId("status-maintenance-recommendation"),
    ).not.toBeInTheDocument();
  });
});

describe("AgentControl polish — App.tsx wires the /agent-control route", () => {
  it("route is registered in the SPA router so deep-links resolve", async () => {
    // The App.tsx file is a static import; we read it as text via Vite's
    // ?raw query and assert the route element wires AgentControl.
    const mod = await import("../App?raw");
    const src = (mod as unknown as { default: string }).default;
    expect(src).toMatch(/<Route\s+path="\/agent-control"/);
    expect(src).toMatch(/element=\{<AgentControl\s*\/>}/);
    expect(src).toMatch(/from\s+"\.\/routes\/AgentControl"/);
  });
});
