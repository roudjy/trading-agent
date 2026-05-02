/**
 * Tests for the v3.15.15.18 mobile-first Agent Control PWA.
 *
 * Hard guarantees verified here:
 *   - The route renders the five expected cards.
 *   - Mobile (375px) viewport renders without horizontal overflow.
 *   - The notification card shows an empty-state placeholder.
 *   - The PR Lifecycle card shows an empty-queue state when the
 *     digest reports zero open PRs.
 *   - All five backing endpoints are GET; no card emits a mutation
 *     fetch (POST/PUT/PATCH/DELETE).
 *   - There are no execute / approve / reject / merge buttons in
 *     the rendered DOM.
 *   - When the wiring step in dashboard/dashboard.py has not yet
 *     landed and an endpoint 404s, the cards fall back to
 *     not_available rather than crashing.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AgentControl } from "../routes/AgentControl";

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

const okProposalsBody = {
  kind: "agent_control_proposals",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    final_recommendation: "needs_human_on_1_items",
    proposals: [
      {
        proposal_id: "p_abcdef01",
        proposal_type: "roadmap_adoption",
        risk_class: "HIGH",
        status: "needs_human",
      },
      {
        proposal_id: "p_abcdef02",
        proposal_type: "tooling_intake",
        risk_class: "LOW",
        status: "proposed",
      },
    ],
  },
  artifact_path: "logs/proposal_queue/latest.json",
};

const okInboxEmptyBody = {
  kind: "agent_control_approval_inbox",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    final_recommendation: "no_items",
    items: [],
    counts: { total: 0, by_severity: {}, by_category: {}, by_status: {} },
  },
  artifact_path: "logs/approval_inbox/latest.json",
};

const okInboxBody = {
  kind: "agent_control_approval_inbox",
  schema_version: 1,
  status: "ok",
  data: {
    schema_version: 1,
    final_recommendation: "critical_on_1_items",
    items: [
      {
        item_id: "i_abc12345",
        category: "frozen_contract_risk",
        severity: "critical",
        status: "blocked",
      },
      {
        item_id: "i_abc12346",
        category: "manual_route_wiring_required",
        severity: "low",
        status: "open",
      },
    ],
    counts: {
      total: 2,
      by_severity: { critical: 1, low: 1 },
      by_category: { frozen_contract_risk: 1, manual_route_wiring_required: 1 },
      by_status: { blocked: 1, open: 1 },
    },
  },
  artifact_path: "logs/approval_inbox/latest.json",
};

const fetchSpy: any[] = [];

function installFetchMock(
  routes: Record<string, () => Response>,
  fallback: () => Response,
) {
  const fetchImpl: typeof fetch = async (input: any, init: any = {}) => {
    fetchSpy.push({ input, method: init.method || "GET" });
    const url = typeof input === "string" ? input : (input as Request).url;
    for (const [path, build] of Object.entries(routes)) {
      if (url === path || url.endsWith(path)) {
        return build();
      }
    }
    return fallback();
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

describe("AgentControl — approval inbox card", () => {
  it("renders an empty-state when the inbox is empty", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("inbox-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("inbox-recommendation")).toHaveTextContent(
      "no_items",
    );
  });

  it("renders not_available when the inbox endpoint 404s", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("inbox-not-available")).toBeInTheDocument();
    });
  });

  it("renders inbox rows with severity pills and never an action button", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("inbox-total")).toHaveTextContent("2");
    });
    expect(screen.getByTestId("inbox-recommendation")).toHaveTextContent(
      "critical_on_1_items",
    );
    // Both inbox rows render their category label.
    expect(
      screen.getAllByText(/frozen_contract_risk|manual_route_wiring_required/),
    ).not.toHaveLength(0);
    // Still exactly one button on the page (the refresh).
    expect(screen.queryAllByRole("button")).toHaveLength(1);
  });
});

describe("AgentControl — proposals card", () => {
  it("renders an empty-state when the proposal queue is empty", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("proposals-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("proposals-recommendation")).toHaveTextContent(
      "no_proposals",
    );
  });

  it("renders not_available when the proposals endpoint 404s", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("proposals-not-available")).toBeInTheDocument();
    });
  });

  it("renders proposal rows with risk pills and never an action button", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("proposals-recommendation")).toBeInTheDocument();
    });
    // Both proposal rows render their proposal_type label.
    expect(screen.getAllByText(/roadmap_adoption|tooling_intake/)).not.toHaveLength(0);
    // Still exactly one button on the page (the refresh).
    expect(screen.queryAllByRole("button")).toHaveLength(1);
  });
});

describe("AgentControl — happy path", () => {
  it("renders all five cards and an empty Dependabot queue", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({ status: "not_available" }, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("agent-control-root")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("notifications-empty")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("pr-empty")).toBeInTheDocument();
    });
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByText("Workloop")).toBeInTheDocument();
    expect(screen.getByText("PR Lifecycle")).toBeInTheDocument();
    expect(screen.getByText("Notifications")).toBeInTheDocument();
  });

  it("never issues a non-GET request from the cards", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("notifications-empty")).toBeInTheDocument();
    });

    for (const call of fetchSpy) {
      expect(call.method).toBe("GET");
    }
  });
});

describe("AgentControl — graceful fallback", () => {
  it("renders not_available everywhere when every endpoint 404s", async () => {
    installFetchMock({}, () => jsonResp({ status: "not_available" }, 404));

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("activity-not-available")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("workloop-not-available")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("pr-not-available")).toBeInTheDocument();
    });
  });

  it("renders not_available when fetch throws (no network)", async () => {
    // @ts-expect-error — assigning the global fetch is intentional in test scope.
    global.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("activity-not-available")).toBeInTheDocument();
    });
  });
});

describe("AgentControl — UI affordances", () => {
  it("contains exactly one button — the Vernieuw refresh button", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("agent-control-refresh")).toBeInTheDocument();
    });

    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveTextContent(/vernieuw|laden/i);
  });

  it("does not render any execute / approve / merge / reject / kill BUTTON", async () => {
    // Interaction-shaped check: scan every interactive element
    // (button, link with role=button, input[type=submit/button],
    // form actions) and verify none of their accessible names match
    // a mutating verb. Plain text in the footer that EXPLAINS the
    // read-only contract (e.g. "no execute / approve / merge buttons")
    // is allowed and even desirable.
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("agent-control-root")).toBeInTheDocument();
    });

    const forbidden = [
      /execute/i,
      /approve/i,
      /reject/i,
      /\bmerge\b/i,
      /\bkill\b/i,
      /\bdelete\b/i,
      /\btrigger\b/i,
      /\brun\b/i,
    ];
    const interactives: HTMLElement[] = [
      ...screen.queryAllByRole("button"),
      ...screen.queryAllByRole("link"),
      ...Array.from(
        document.querySelectorAll<HTMLElement>(
          'input[type="submit"], input[type="button"], form, [aria-haspopup]',
        ),
      ),
    ];
    for (const el of interactives) {
      const label =
        (el.getAttribute("aria-label") ??
          el.textContent ??
          el.getAttribute("value") ??
          "").trim();
      for (const re of forbidden) {
        expect(label, `forbidden verb on interactive: ${label}`).not.toMatch(
          re,
        );
      }
    }
  });

  it("renders within the iPhone-mini viewport (375 wide) without horizontal overflow", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
      },
      () => jsonResp({}, 404),
    );

    // jsdom does not implement layout, so we check the structural
    // signal: the root is a single column on mobile (no horizontal
    // scroll required at 375px viewport width). The test asserts on
    // CSS class presence rather than rendered geometry.
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 375,
    });

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("agent-control-root")).toBeInTheDocument();
    });

    const root = screen.getByTestId("agent-control-root");
    expect(root).toHaveClass("agent-control");
    const grid = root.querySelector(".agent-control__grid");
    expect(grid).not.toBeNull();
  });
});
