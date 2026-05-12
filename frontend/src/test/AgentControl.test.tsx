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
  workloop_runtime: {
    status: "ok",
    data: {
      runtime_version: "v3.15.15.22",
      generated_at_utc: "2026-05-02T20:00:00Z",
      mode: "once",
      iteration: 0,
      duration_ms: 200,
      safe_to_execute: false,
      loop_health: {
        consecutive_failures: 0,
        iterations_completed: 1,
        iterations_failed: 0,
      },
      counts: { total: 7, by_state: { ok: 7 } },
      final_recommendation: "all_sources_ok",
      source_states: [
        { source: "governance_status", state: "ok" },
        { source: "approval_inbox", state: "ok" },
      ],
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
  approval_policy: {
    status: "ok",
    data: {
      module_version: "v3.15.15.24",
      schema_version: 1,
      decision_count: 14,
      approval_category_count: 18,
      high_or_unknown_is_executable: false,
      execute_safe_requires_dependabot_low_or_medium: true,
      execute_safe_requires_two_layer_opt_in: true,
    },
  },
  autonomy_metrics: {
    status: "ok",
    data: {
      module_version: "v3.15.15.25",
      metrics_version: "v1",
      generated_at_utc: "2026-05-03T08:00:00Z",
      final_recommendation: "healthy",
      safe_to_execute: false,
      throughput_summary: {
        proposals_total: 0,
        inbox_items_total: 0,
        pr_lifecycle_prs_seen: 0,
        recurring_jobs_total: 0,
        runtime_sources_total: 0,
      },
      operator_burden_summary: {
        needs_human_total: 0,
        blocked_total: 0,
        estimated_operator_actions_total: 0,
      },
      reliability_summary: {
        runtime_consecutive_failures: 0,
        missing_artifact_count: 0,
        malformed_artifact_count: 0,
      },
      safety_summary: {
        high_or_unknown_executable_count: 0,
        summary: "ok",
      },
    },
  },
  roadmap_protocol: {
    status: "ok",
    data: {
      module_version: "v3.15.15.28",
      schema_version: 1,
      generated_at_utc: "2026-05-03T08:00:00Z",
      item_id: "r_test1234",
      title: "Sample roadmap item",
      item_type: "docs_only",
      risk_class: "LOW",
      decision: "allowed_read_only",
      status_field: "proposed",
      implementation_allowed: true,
      executable: false,
      safe_to_execute: false,
      blocked_reason: null,
      proposed_release_id: "v3.15.16.0",
      proposed_branch: "fix/v3-15-16-0-r-test1234-sample-roadmap-item",
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
      {
        action_id: "a_bbbbbbbb",
        action_type: "run_dependabot_execute_safe_low_medium",
        title: "Dependabot execute-safe",
        summary: "...",
        risk_class: "MEDIUM",
        eligibility: "eligible",
        blocked_reason: null,
      },
    ],
    counts: {
      total: 2,
      by_eligibility: { eligible: 2 },
      by_risk_class: { LOW: 1, MEDIUM: 1 },
    },
  },
};

// v3.15.16.5 — Next-Up card test fixtures.
const okNextUpReadyBody = {
  kind: "agent_control_next_up",
  schema_version: 1,
  status: "ok",
  data: {
    module_version: "v3.15.16.2",
    generated_at_utc: "2026-05-05T08:00:00Z",
    final_recommendation: "ready_for_implementation",
    safe_to_execute: false,
    chosen_next_up: {
      proposal_id: "p_aaaaaaaa",
      title: "add observability metric",
      summary: "add observability monitoring for the audit log",
      proposal_type: "observability_addition",
      risk_class: "LOW",
      rationale:
        "risk LOW, type observability_addition, protocol decision allowed_read_only",
      protocol_plan_summary: {
        decision: "allowed_read_only",
        implementation_allowed: true,
        requires_human: false,
        risk_class: "LOW",
        item_type: "observability_addition",
        proposed_branch: "fix/v3-15-16-x-p-aaaaaaaa-add-observability-metric",
        proposed_release_id: "v3.15.16.x",
        required_tests: ["scripts/governance_lint.py", "tests/smoke"],
        expected_artifacts: ["docs/governance/<doc>.md"],
      },
    },
    counts: {
      proposals_total: 206,
      eligible_total: 4,
      filtered_out_total: 202,
      filtered_out_by_reason: {
        risk_high_excluded: 12,
        protocol_decision_not_allowed_read_only: 180,
      },
    },
    needs_human: false,
  },
  artifact_path: "logs/roadmap_priority/latest.json",
};

const okNextUpNothingReadyBody = {
  kind: "agent_control_next_up",
  schema_version: 1,
  status: "ok",
  data: {
    module_version: "v3.15.16.2",
    generated_at_utc: "2026-05-05T08:00:00Z",
    final_recommendation: "nothing_ready",
    safe_to_execute: false,
    chosen_next_up: null,
    counts: {
      proposals_total: 12,
      eligible_total: 0,
      filtered_out_total: 12,
      filtered_out_by_reason: { status_not_proposed: 12 },
    },
    needs_human: false,
  },
  artifact_path: "logs/roadmap_priority/latest.json",
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

describe("AgentControl — execute-safe card", () => {
  it("renders the catalog and never adds a button", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("execute-safe-cli-only")).toBeInTheDocument();
    });
    expect(screen.getByTestId("execute-safe-cli-only")).toHaveTextContent(
      /CLI-only/,
    );
    // Card surfaces both action types.
    expect(
      screen.getAllByText(/refresh_proposal_queue_dry_run/i),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByText(/run_dependabot_execute_safe_low_medium/i),
    ).not.toHaveLength(0);
    // Still exactly one button on the page (the refresh).
    expect(screen.queryAllByRole("button")).toHaveLength(1);
  });

  it("renders not_available when the execute-safe endpoint 404s", async () => {
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
      expect(
        screen.getByTestId("execute-safe-not-available"),
      ).toBeInTheDocument();
    });
  });
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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

describe("AgentControl — next-up card (v3.15.16.5)", () => {
  it("renders chosen_next_up with the ready_for_implementation recommendation", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
        "/api/agent-control/next-up": () => jsonResp(okNextUpReadyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("next-up-recommendation")).toBeInTheDocument();
    });
    expect(screen.getByTestId("next-up-recommendation")).toHaveTextContent(
      "ready_for_implementation",
    );
    expect(screen.getByTestId("next-up-needs-human")).toHaveTextContent("no");
    expect(screen.getByTestId("next-up-title")).toHaveTextContent(
      /add observability metric/,
    );
    expect(screen.getByTestId("next-up-decision")).toHaveTextContent(
      "allowed_read_only",
    );
    expect(screen.getByTestId("next-up-counts")).toHaveTextContent(
      /206 proposals/,
    );
    // The card must never add an action button — only the global
    // refresh button stays.
    expect(screen.queryAllByRole("button")).toHaveLength(1);
  });

  it("renders the no-candidate empty state when nothing is ready", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
        "/api/agent-control/next-up": () => jsonResp(okNextUpNothingReadyBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("next-up-no-candidate")).toBeInTheDocument();
    });
    expect(screen.getByTestId("next-up-recommendation")).toHaveTextContent(
      "nothing_ready",
    );
  });

  it("renders not_available when the next-up endpoint 404s", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
        // Intentionally omit /api/agent-control/next-up so the
        // fetch falls through to the 404 fallback. This emulates
        // production while the v3.15.16.5 dashboard.py wiring has
        // not yet landed via its bootstrap PR.
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("next-up-not-available")).toBeInTheDocument();
    });
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
    // v3.15.15.26: ``__grid`` was replaced with bottom-nav +
    // per-section ``__sections``. The phone-first layout is
    // verified by the presence of both the nav and the
    // overview tabpanel.
    const sections = root.querySelector(".agent-control__sections");
    expect(sections).not.toBeNull();
    const nav = root.querySelector(".agent-control__nav");
    expect(nav).not.toBeNull();
  });
});


const loopClosureOpen = {
  status: "ok" as const,
  data: {
    loop_state: "open" as const,
    human_needed: {
      events_total: 1,
      by_reason: { governance_bootstrap_required: 1 },
      top_blocking_component:
        "dashboard/dashboard.py:register_roadmap_priority_routes",
      generated_at_utc: "2026-05-05T13:00:00Z",
    },
    governance_bootstrap: {
      templates_total: 1,
      top_branch_name: "governance-bootstrap/h_aaaaaaaaaa",
      generated_at_utc: "2026-05-05T13:00:00Z",
    },
    approval_inbox: {
      human_needed_derived_rows: 1,
      generated_at_utc: "2026-05-05T13:00:00Z",
    },
    last_refreshed_utc: "2026-05-05T13:00:00Z",
  },
};

const loopClosureResolved = {
  status: "ok" as const,
  data: {
    loop_state: "resolved" as const,
    human_needed: {
      events_total: 0,
      by_reason: { governance_bootstrap_required: 0 },
      top_blocking_component: null,
      generated_at_utc: "2026-05-05T13:00:00Z",
    },
    governance_bootstrap: {
      templates_total: 0,
      top_branch_name: null,
      generated_at_utc: "2026-05-05T13:00:30Z",
    },
    approval_inbox: {
      human_needed_derived_rows: 0,
      generated_at_utc: "2026-05-05T13:00:45Z",
    },
    last_refreshed_utc: "2026-05-05T13:00:45Z",
  },
};

const loopClosureStale = {
  status: "ok" as const,
  data: {
    loop_state: "stale" as const,
    human_needed: {
      events_total: 0,
      by_reason: { governance_bootstrap_required: 0 },
      top_blocking_component: null,
      generated_at_utc: "2026-05-05T13:00:00Z",
    },
    governance_bootstrap: {
      templates_total: 0,
      top_branch_name: null,
      generated_at_utc: "2026-05-05T12:30:00Z",
    },
    approval_inbox: {
      human_needed_derived_rows: 0,
      generated_at_utc: "2026-05-05T13:00:30Z",
    },
    last_refreshed_utc: "2026-05-05T13:00:30Z",
  },
};

const loopClosureNotAvailable = {
  status: "not_available" as const,
  reason: "human_needed: missing",
};

function makeStatusBodyWithLoopClosure(loopClosure: unknown) {
  return { ...okStatusBody, loop_closure: loopClosure };
}

describe("AgentControl — loop closure subsection (v3.15.16.9b)", () => {
  it("renders open state with blocking_component and branch_name", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureOpen)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("loop-closure-state")).toBeInTheDocument();
    });
    expect(screen.getByTestId("loop-closure-state")).toHaveTextContent("open");
    expect(screen.getByTestId("loop-closure-human-needed-count")).toHaveTextContent(
      "1 event(s)",
    );
    expect(
      screen.getByTestId("loop-closure-blocking-component"),
    ).toHaveTextContent(
      "dashboard/dashboard.py:register_roadmap_priority_routes",
    );
    expect(
      screen.getByTestId("loop-closure-templates-count"),
    ).toHaveTextContent("1 template(s)");
    expect(screen.getByTestId("loop-closure-branch-name")).toHaveTextContent(
      "governance-bootstrap/h_aaaaaaaaaa",
    );
    expect(
      screen.getByTestId("loop-closure-inbox-rows-count"),
    ).toHaveTextContent("1");
    expect(
      screen.getByTestId("loop-closure-last-refreshed"),
    ).toHaveTextContent("2026-05-05T13:00:00Z");
  });

  it("renders resolved state with all zero counts", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureResolved)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("loop-closure-state")).toBeInTheDocument();
    });
    expect(screen.getByTestId("loop-closure-state")).toHaveTextContent(
      "resolved",
    );
    expect(
      screen.getByTestId("loop-closure-human-needed-count"),
    ).toHaveTextContent("0 event(s)");
    expect(
      screen.getByTestId("loop-closure-templates-count"),
    ).toHaveTextContent("0 template(s)");
    expect(
      screen.getByTestId("loop-closure-inbox-rows-count"),
    ).toHaveTextContent("0");
    // Resolved state: blocking_component and branch_name rows are
    // ABSENT (not just empty).
    expect(
      screen.queryByTestId("loop-closure-blocking-component"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("loop-closure-branch-name"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("loop-closure-last-refreshed"),
    ).toHaveTextContent("2026-05-05T13:00:45Z");
  });

  it("renders stale state when artifacts are inconsistent", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureStale)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("loop-closure-state")).toBeInTheDocument();
    });
    expect(screen.getByTestId("loop-closure-state")).toHaveTextContent(
      "stale",
    );
  });

  it("renders not_available when loop_closure status is not_available", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureNotAvailable)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("loop-closure-not-available"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("loop-closure-not-available"),
    ).toHaveTextContent("human_needed: missing");
  });

  it("does not render the loop closure block when payload omits loop_closure", async () => {
    // Backwards-compat: an older /status payload without loop_closure
    // must not crash the card.
    installFetchMock(
      {
        "/api/agent-control/status": () => jsonResp(okStatusBody),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () => jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
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
    expect(
      screen.queryByTestId("loop-closure-state"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("loop-closure-not-available"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// v3.15.16.9c — roadmap_priority route wiring subsection
// ---------------------------------------------------------------------------

const rpwOpen = {
  state: "open" as const,
  reason: null,
  event_id: "h_044e7e64e",
  blocking_component:
    "dashboard/dashboard.py:register_roadmap_priority_routes",
  source_reason: "governance_bootstrap_required",
  template_branch: "governance-bootstrap/h_044e7e64e",
  inbox_row_present: true,
};

const rpwResolved = {
  state: "resolved" as const,
  reason: null,
  event_id: null,
  blocking_component: null,
  source_reason: null,
  template_branch: null,
  inbox_row_present: false,
};

const rpwNotAvailable = {
  state: "not_available" as const,
  reason: "governance_bootstrap_lags_human_needed",
  event_id: null,
  blocking_component: null,
  source_reason: null,
  template_branch: null,
  inbox_row_present: false,
};

const loopClosureOpenWithRpwOpen = {
  ...loopClosureOpen,
  roadmap_priority_wiring: rpwOpen,
};

const loopClosureOpenWithRpwResolved = {
  ...loopClosureOpen,
  roadmap_priority_wiring: rpwResolved,
};

const loopClosureNotAvailableWithRpwNotAvailable = {
  ...loopClosureNotAvailable,
  roadmap_priority_wiring: rpwNotAvailable,
};

describe("AgentControl — roadmap_priority route wiring subsection (v3.15.16.9c)", () => {
  it("renders open state with all five canonical fields", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureOpenWithRpwOpen)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("roadmap-priority-wiring-state"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("roadmap-priority-wiring-state"),
    ).toHaveTextContent("open");
    expect(
      screen.getByTestId("roadmap-priority-wiring-event-id"),
    ).toHaveTextContent("h_044e7e64e");
    expect(
      screen.getByTestId("roadmap-priority-wiring-blocking-component"),
    ).toHaveTextContent(
      "dashboard/dashboard.py:register_roadmap_priority_routes",
    );
    expect(
      screen.getByTestId("roadmap-priority-wiring-source-reason"),
    ).toHaveTextContent("governance_bootstrap_required");
    expect(
      screen.getByTestId("roadmap-priority-wiring-template-branch"),
    ).toHaveTextContent("governance-bootstrap/h_044e7e64e");
    expect(
      screen.getByTestId("roadmap-priority-wiring-inbox-present"),
    ).toHaveTextContent("present");
    expect(
      screen.queryByTestId("roadmap-priority-wiring-reason"),
    ).not.toBeInTheDocument();
  });

  it("renders resolved state without descriptive fields", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(
            makeStatusBodyWithLoopClosure(loopClosureOpenWithRpwResolved),
          ),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("roadmap-priority-wiring-state"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("roadmap-priority-wiring-state"),
    ).toHaveTextContent("resolved");
    // Descriptive rows are absent in the resolved state.
    expect(
      screen.queryByTestId("roadmap-priority-wiring-event-id"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-blocking-component"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-source-reason"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-template-branch"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-inbox-present"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-reason"),
    ).not.toBeInTheDocument();
  });

  it("renders not_available state with the closed reason", async () => {
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(
            makeStatusBodyWithLoopClosure(
              loopClosureNotAvailableWithRpwNotAvailable,
            ),
          ),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("roadmap-priority-wiring-state"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("roadmap-priority-wiring-state"),
    ).toHaveTextContent("not_available");
    expect(
      screen.getByTestId("roadmap-priority-wiring-reason"),
    ).toHaveTextContent("governance_bootstrap_lags_human_needed");
    // No descriptive open-only fields in not_available either.
    expect(
      screen.queryByTestId("roadmap-priority-wiring-event-id"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("roadmap-priority-wiring-template-branch"),
    ).not.toBeInTheDocument();
  });

  it("does not render the wiring subsection when payload omits roadmap_priority_wiring", async () => {
    // Backwards-compat: an older /status payload without the new
    // sub-object must not crash the card.
    installFetchMock(
      {
        "/api/agent-control/status": () =>
          jsonResp(makeStatusBodyWithLoopClosure(loopClosureOpen)),
        "/api/agent-control/activity": () => jsonResp(okActivityBody),
        "/api/agent-control/workloop": () => jsonResp(okWorkloopBody),
        "/api/agent-control/pr-lifecycle": () =>
          jsonResp(okPRLifecycleEmptyBody),
        "/api/agent-control/notifications": () =>
          jsonResp(placeholderNotificationsBody),
        "/api/agent-control/proposals": () => jsonResp(okProposalsEmptyBody),
        "/api/agent-control/approval-inbox": () => jsonResp(okInboxEmptyBody),
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );
    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("loop-closure-state")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("roadmap-priority-wiring-state"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// N5c discoverability spillover — visible read-only entry to
// /agent-control/merge-recommendation from the PRs section.
// Read-only by structure: it is a <Link> (anchor), not a button, and
// the card body never issues a fetch.
// ---------------------------------------------------------------------------

describe("AgentControl — N5c discoverability link in PRs section", () => {
  it("renders a visible merge-recommendations link pointing at the N5c route", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    // The PRs section is rendered (hidden when inactive but the
    // <Link> remains queryable from RTL).
    await waitFor(() => {
      expect(
        screen.getByTestId("merge-recommendations-link"),
      ).toBeInTheDocument();
    });

    const link = screen.getByTestId("merge-recommendations-link");
    expect(link).toHaveAttribute("href", "/agent-control/merge-recommendation");
    // Anchor element, not a button — read-only by structure.
    expect(link.tagName.toLowerCase()).toBe("a");
    // Visible, accessible name describes the destination.
    expect(link).toHaveAccessibleName(
      /open read-only merge recommendations/i,
    );
    // Subtitle / description is present.
    expect(
      screen.getByTestId("merge-recommendations-description"),
    ).toHaveTextContent(/read-only/i);
  });

  it("does not add any decision-verb button to the page", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("merge-recommendations-link"),
      ).toBeInTheDocument();
    });

    // Existing surface pins exactly one button (the Vernieuw refresh
    // control). This must remain unchanged — no new button added.
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute(
      "data-testid",
      "agent-control-refresh",
    );

    // No approve / reject / deploy verbs anywhere on the page.
    const card = screen.getByTestId("merge-recommendations-link");
    const cardText = (card.textContent || "").toLowerCase();
    expect(cardText).not.toMatch(/\bapprove\b/);
    expect(cardText).not.toMatch(/\breject\b/);
    expect(cardText).not.toMatch(/\bdeploy\b/);
  });

  it("does not introduce a new fetch and does not call any token endpoint", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("merge-recommendations-link"),
      ).toBeInTheDocument();
    });

    // The discoverability card never adds a fetch. The only fetches
    // are the existing card-loader endpoints — never the
    // merge-recommendation list/detail, never an approval-token URL.
    for (const call of fetchSpy) {
      const url = String(call.input);
      expect(url).not.toContain(
        "/api/agent-control/merge-recommendation/",
      );
      expect(url).not.toContain("/api/agent-control/approval-token/");
      expect(call.method).toBe("GET");
    }
  });
});

// ---------------------------------------------------------------------------
// N4c discoverability link in the About section — visible read-only
// entry to /agent-control/approval-token-diagnostics. Same anchor-only,
// no-fetch shape as the N5c merge-recommendations link.
// ---------------------------------------------------------------------------

describe("AgentControl — N4c discoverability link in About section", () => {
  it("renders a visible approval-token-diagnostics link pointing at the N4c route", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("approval-token-diagnostics-link"),
      ).toBeInTheDocument();
    });

    const link = screen.getByTestId("approval-token-diagnostics-link");
    expect(link).toHaveAttribute(
      "href",
      "/agent-control/approval-token-diagnostics",
    );
    expect(link.tagName.toLowerCase()).toBe("a");
    expect(link).toHaveAccessibleName(
      /open approval token diagnostics/i,
    );
    expect(
      screen.getByTestId("approval-token-diagnostics-link-description"),
    ).toHaveTextContent(/claim-only/i);
  });

  it("does not add any new fetch or call the token endpoint from the discoverability card", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("approval-token-diagnostics-link"),
      ).toBeInTheDocument();
    });

    for (const call of fetchSpy) {
      const url = String(call.input);
      expect(url).not.toContain("/api/agent-control/approval-token/");
      expect(call.method).toBe("GET");
    }
  });

  it("preserves the single-button invariant (only the Vernieuw button)", async () => {
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
        "/api/agent-control/execute-safe": () => jsonResp(okExecuteSafeBody),
      },
      () => jsonResp({}, 404),
    );

    render(
      <MemoryRouter initialEntries={["/agent-control"]}>
        <AgentControl />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("approval-token-diagnostics-link"),
      ).toBeInTheDocument();
    });

    const buttons = screen.queryAllByRole("button");
    // Only the refresh button (the existing single-button invariant
    // pinned by the earlier N5c test). The discoverability link is
    // an anchor, not a button.
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute(
      "data-testid",
      "agent-control-refresh",
    );
  });
});
