/**
 * Tests for AgentActivity — the v3.15.16.A15.B2.0d read-only PWA
 * surface over the six Agent Activity Center GET endpoints.
 *
 * Pins:
 *   - URL-synced routing across all 7 sub-paths + items/<id>.
 *   - Loading / not_available / ok states for every section.
 *   - Today key metrics + needs-human cap of 3 + "live merge
 *     permanently disabled" notice.
 *   - Inbox filter pills + AttentionCard.
 *   - Pipeline 11 closed-vocab stage chips + canonical empty copy
 *     for done_blocked.
 *   - Artefacts seed read-only chip.
 *   - Safety Level 6 banner + invariant cards.
 *   - Agents per-role row.
 *   - Trace header + timeline.
 *   - Bottom-nav uses <Link>; aria-current follows useLocation.
 *   - No rendered <button> has an accessible name matching
 *     approve / execute / merge / deploy / reject / admit /
 *     flip / trigger.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AgentActivity } from "../routes/AgentControl/AgentActivity";
import { agentControlApi } from "../api/agent_control";

vi.mock("../api/agent_control", async () => {
  const actual = await vi.importActual<typeof import("../api/agent_control")>(
    "../api/agent_control",
  );
  return {
    ...actual,
    agentControlApi: {
      ...actual.agentControlApi,
      activityToday: vi.fn(),
      activityItemsList: vi.fn(),
      activityItemsDetail: vi.fn(),
      activityAgents: vi.fn(),
      activityArtifacts: vi.fn(),
      activityInvariants: vi.fn(),
    },
  };
});

function _mock() {
  return agentControlApi as unknown as {
    activityToday: ReturnType<typeof vi.fn>;
    activityItemsList: ReturnType<typeof vi.fn>;
    activityItemsDetail: ReturnType<typeof vi.fn>;
    activityAgents: ReturnType<typeof vi.fn>;
    activityArtifacts: ReturnType<typeof vi.fn>;
    activityInvariants: ReturnType<typeof vi.fn>;
  };
}

const todayOk = {
  kind: "agent_control_activity_today",
  schema_version: 1,
  module_version: "v3.15.16.A15.B2.0c.api",
  status: "ok",
  step5_implementation_allowed: false,
  step5_enabled_substage: "none",
  level6_enabled: false,
  generated_at_utc: "2026-05-14T08:00:00Z",
  artifact_path: "logs/development_agent_activity_timeline/latest.json",
  counts: {
    discovered: 0,
    queued: 0,
    delegated: 0,
    planned: 1,
    dry_run_ready: 0,
    pr_proposed: 0,
    pr_opened: 0,
    ci_feedback: 0,
    needs_human: 2,
    merge_candidate: 1,
    blocked: 0,
    total_open: 4,
  },
  needs_human: [],
  merge_candidate: [],
  ci_feedback: [],
  blocked: [],
  recent_events: [],
  freshness: { any_stale: false, any_malformed: false },
  invariant_status: [],
};

function workItem(item_id: string, stage: string, human_needed = false) {
  return {
    item_id,
    title: `Title ${item_id}`,
    source_kind: "generated_lane",
    source_path: "logs/development_generated_lane_a18c/latest.json",
    current_stage: stage,
    owner_role: "release_gate_agent",
    risk: "medium",
    human_needed,
    latest_verdict: "admission_decision=needs_human",
    next_action: "Operator review",
    updated_at: "2026-05-14T07:00:00Z",
    summary: "synthetic",
    event_ids: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default mocks — every test overrides as needed.
  _mock().activityToday.mockResolvedValue(todayOk);
  _mock().activityItemsList.mockResolvedValue({
    kind: "agent_control_activity_items_list",
    schema_version: 1,
    module_version: "v3.15.16.A15.B2.0c.api",
    status: "ok",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    work_items: [],
    total_matching: 0,
    truncated: false,
    freshness: {},
    generated_at_utc: "2026-05-14T08:00:00Z",
    artifact_path: "logs/development_agent_activity_timeline/latest.json",
  });
  _mock().activityAgents.mockResolvedValue({
    kind: "agent_control_activity_agents",
    schema_version: 1,
    module_version: "v3.15.16.A15.B2.0c.api",
    status: "ok",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    rows: [],
    generated_at_utc: "2026-05-14T08:00:00Z",
    artifact_path: "logs/development_agent_activity_timeline/latest.json",
  });
  _mock().activityArtifacts.mockResolvedValue({
    kind: "agent_control_activity_artifacts",
    schema_version: 1,
    module_version: "v3.15.16.A15.B2.0c.api",
    status: "ok",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    artifact_health: [],
    generated_at_utc: "2026-05-14T08:00:00Z",
    artifact_path: "logs/development_agent_activity_timeline/latest.json",
  });
  _mock().activityInvariants.mockResolvedValue({
    kind: "agent_control_activity_invariants",
    schema_version: 1,
    module_version: "v3.15.16.A15.B2.0c.api",
    status: "ok",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    invariant_status: [],
    generated_at_utc: "2026-05-14T08:00:00Z",
    artifact_path: "logs/development_agent_activity_timeline/latest.json",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

function mount(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/agent-control/activity/*" element={<AgentActivity />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Routing / deeplink (5 tests)
// ---------------------------------------------------------------------------

describe("AgentActivity routing", () => {
  it("renders Today on the bare /agent-control/activity path", async () => {
    mount("/agent-control/activity");
    expect(await screen.findByTestId("aac-section-today")).toBeInTheDocument();
  });

  it("renders Inbox on /agent-control/activity/inbox", async () => {
    mount("/agent-control/activity/inbox");
    expect(await screen.findByTestId("aac-section-inbox")).toBeInTheDocument();
  });

  it("renders Pipeline on /agent-control/activity/pipeline", async () => {
    mount("/agent-control/activity/pipeline");
    expect(
      await screen.findByTestId("aac-section-pipeline"),
    ).toBeInTheDocument();
  });

  it("renders Trace on /agent-control/activity/items/<id>", async () => {
    _mock().activityItemsDetail.mockResolvedValue({
      kind: "agent_control_activity_items_detail",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      work_item: workItem("wi_target_1", "needs_human", true),
      agent_events: [],
      human_actions: [],
      artefacts_referenced: [],
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/items/wi_target_1");
    expect(await screen.findByTestId("aac-section-trace")).toBeInTheDocument();
    expect(_mock().activityItemsDetail).toHaveBeenCalledWith("wi_target_1");
  });

  it("redirects unknown sub-path to Today", async () => {
    mount("/agent-control/activity/totally_bogus");
    expect(await screen.findByTestId("aac-section-today")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Bottom-nav (2 tests)
// ---------------------------------------------------------------------------

describe("AgentActivity bottom-nav", () => {
  it("renders 5 tabs as <Link>s, not <button>s", async () => {
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    const nav = screen.getByTestId("aac-bottom-nav");
    const tabs = within(nav).getAllByRole("link");
    expect(tabs).toHaveLength(5);
    expect(within(nav).queryAllByRole("button")).toHaveLength(0);
  });

  it("marks active tab with aria-current=page based on pathname", async () => {
    mount("/agent-control/activity/inbox");
    await screen.findByTestId("aac-section-inbox");
    const inboxTab = screen.getByTestId("aac-tab-inbox");
    expect(inboxTab).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("aac-tab-today")).not.toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

// ---------------------------------------------------------------------------
// Today (4 tests)
// ---------------------------------------------------------------------------

describe("AgentActivity Today", () => {
  it("renders 6 metric tiles from the counts envelope", async () => {
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    expect(screen.getByTestId("aac-metric-needs-human")).toBeInTheDocument();
    expect(screen.getByTestId("aac-metric-blocked")).toBeInTheDocument();
    expect(
      screen.getByTestId("aac-metric-merge-candidate"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("aac-metric-ci-feedback")).toBeInTheDocument();
    expect(screen.getByTestId("aac-metric-planned")).toBeInTheDocument();
    expect(
      screen.getByTestId("aac-metric-dry-run-ready"),
    ).toBeInTheDocument();
  });

  it("caps needs-human section at 3 cards", async () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      workItem(`wi_h_${i}`, "needs_human", true),
    );
    _mock().activityToday.mockResolvedValue({
      ...todayOk,
      needs_human: many,
    });
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    const cards = screen
      .getAllByTestId(/^aac-item-/)
      .filter((el) => el.getAttribute("data-testid")?.startsWith("aac-item-wi_h_"));
    expect(cards).toHaveLength(3);
  });

  it("renders 'Live merge is permanently disabled' notice when merge candidates exist", async () => {
    _mock().activityToday.mockResolvedValue({
      ...todayOk,
      merge_candidate: [workItem("wi_m_1", "merge_candidate", false)],
    });
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    expect(
      screen.getByTestId("aac-live-merge-disabled-notice"),
    ).toHaveTextContent(/permanently disabled/i);
  });

  it("renders offline banner when aggregator returns not_available", async () => {
    _mock().activityToday.mockResolvedValue({
      ...todayOk,
      status: "not_available",
      reason: "missing",
    });
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    expect(screen.getByTestId("aac-banner-offline")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Inbox (3 tests)
// ---------------------------------------------------------------------------

describe("AgentActivity Inbox", () => {
  it("renders filter pills", async () => {
    mount("/agent-control/activity/inbox");
    await screen.findByTestId("aac-section-inbox");
    expect(screen.getByTestId("aac-inbox-filter-all")).toBeInTheDocument();
    expect(
      screen.getByTestId("aac-inbox-filter-required"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("aac-inbox-filter-optional"),
    ).toBeInTheDocument();
  });

  it("renders inbox-zero when work_items list is empty", async () => {
    mount("/agent-control/activity/inbox");
    await screen.findByTestId("aac-section-inbox");
    expect(screen.getByTestId("aac-inbox-empty")).toBeInTheDocument();
  });

  it("renders AttentionCard rows when human-needed items exist", async () => {
    _mock().activityItemsList.mockResolvedValue({
      kind: "agent_control_activity_items_list",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      work_items: [workItem("wi_h_a", "needs_human", true)],
      total_matching: 1,
      truncated: false,
      freshness: {},
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/inbox");
    await screen.findByTestId("aac-section-inbox");
    expect(screen.getByTestId("aac-attention-ha_wi_h_a")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Pipeline (2 tests)
// ---------------------------------------------------------------------------

describe("AgentActivity Pipeline", () => {
  it("renders 11 stage chips in closed-vocab order", async () => {
    mount("/agent-control/activity/pipeline");
    await screen.findByTestId("aac-section-pipeline");
    const expectedStages = [
      "discovered",
      "queued",
      "delegated",
      "planned",
      "dry_run_ready",
      "pr_proposed",
      "pr_opened",
      "ci_feedback",
      "needs_human",
      "merge_candidate",
      "done_blocked",
    ];
    for (const s of expectedStages) {
      expect(
        screen.getByTestId(`aac-pipeline-chip-${s}`),
      ).toBeInTheDocument();
    }
  });

  it("renders 'No promotable candidates' for empty done_blocked stage", async () => {
    mount("/agent-control/activity/pipeline");
    await screen.findByTestId("aac-section-pipeline");
    const doneChip = screen.getByTestId("aac-pipeline-chip-done_blocked");
    doneChip.click();
    expect(
      await screen.findByTestId("aac-pipeline-empty-done_blocked"),
    ).toHaveTextContent("No promotable candidates");
  });
});

// ---------------------------------------------------------------------------
// Artefacts (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity Artefacts", () => {
  it("renders read-only chip on the seed row", async () => {
    _mock().activityArtifacts.mockResolvedValue({
      kind: "agent_control_activity_artifacts",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      artifact_health: [
        {
          path: "generated_seed.jsonl",
          group: "seed",
          fresh: false,
          parse_ok: true,
          row_count: 0,
          last_modified: "",
          module_version: "",
          has_summary: false,
          read_only_warning: "Read-only · UI must not write",
        },
      ],
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/artefacts");
    await screen.findByTestId("aac-section-artefacts");
    expect(
      screen.getByTestId("aac-read-only-generated_seed.jsonl"),
    ).toHaveTextContent(/Read-only/);
  });
});

// ---------------------------------------------------------------------------
// Safety (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity Safety", () => {
  it("renders the red Level 6 banner permanently disabled", async () => {
    _mock().activityInvariants.mockResolvedValue({
      kind: "agent_control_activity_invariants",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      invariant_status: [
        {
          key: "level_6",
          label: "Level 6",
          value: "permanently_disabled",
          tone: "danger_off",
          detail: "permanently disabled",
        },
      ],
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/safety");
    await screen.findByTestId("aac-section-safety");
    expect(screen.getByTestId("aac-l6-banner")).toHaveTextContent(
      /permanently disabled/i,
    );
    expect(
      screen.getByTestId("aac-invariant-level_6"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Agents (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity Agents", () => {
  it("renders one row per agent role from the matrix envelope", async () => {
    _mock().activityAgents.mockResolvedValue({
      kind: "agent_control_activity_agents",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      rows: [
        {
          role: "release_gate_agent",
          new: 0,
          planned: 1,
          blocked: 0,
          needs_human: 1,
          pr_ready: 0,
          last_action: null,
          total: 1,
        },
        {
          role: "planner",
          new: 0,
          planned: 0,
          blocked: 0,
          needs_human: 0,
          pr_ready: 0,
          last_action: null,
          total: 0,
        },
      ],
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/agents");
    await screen.findByTestId("aac-section-agents");
    expect(
      screen.getByTestId("aac-agent-release_gate_agent"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("aac-agent-planner")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Trace (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity Trace", () => {
  it("renders header card + timeline rendered from itemsDetail envelope", async () => {
    _mock().activityItemsDetail.mockResolvedValue({
      kind: "agent_control_activity_items_detail",
      schema_version: 1,
      module_version: "v3.15.16.A15.B2.0c.api",
      status: "ok",
      step5_implementation_allowed: false,
      step5_enabled_substage: "none",
      level6_enabled: false,
      work_item: workItem("wi_t_001", "needs_human", true),
      agent_events: [
        {
          event_id: "ev_t_001",
          item_id: "wi_t_001",
          timestamp: "2026-05-14T07:00:00Z",
          agent_role: "release_gate_agent",
          module: "generated_lane_a18c",
          event_type: "verdict",
          summary: "needs_human",
          decision: "require_human",
          reason: "policy",
          artifact_path: "logs/development_generated_lane_a18c/latest.json",
          severity: "human",
        },
      ],
      human_actions: [],
      artefacts_referenced: [],
      generated_at_utc: "2026-05-14T08:00:00Z",
      artifact_path: "logs/development_agent_activity_timeline/latest.json",
    });
    mount("/agent-control/activity/items/wi_t_001");
    await screen.findByTestId("aac-section-trace");
    expect(screen.getByTestId("aac-trace-header")).toBeInTheDocument();
    expect(screen.getByTestId("aac-event-ev_t_001")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Decision-verb UI scan (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity decision-verb UI scan", () => {
  it("renders no button whose accessible name matches approve/execute/merge/deploy/reject/admit/flip/trigger", async () => {
    _mock().activityToday.mockResolvedValue({
      ...todayOk,
      needs_human: [workItem("wi_h_a", "needs_human", true)],
      merge_candidate: [workItem("wi_m_a", "merge_candidate", false)],
    });
    mount("/agent-control/activity/today");
    await screen.findByTestId("aac-section-today");
    const verbs = /^(approve|execute|merge|deploy|reject|admit|flip|trigger)\b/i;
    const buttons = screen.queryAllByRole("button");
    for (const b of buttons) {
      const name = b.getAttribute("aria-label") || b.textContent || "";
      expect(name, `button name leaks decision verb: ${name}`).not.toMatch(
        verbs,
      );
    }
  });
});

// ---------------------------------------------------------------------------
// More section + deferred Design Spec (1 test)
// ---------------------------------------------------------------------------

describe("AgentActivity More section", () => {
  it("renders Design Spec deferred item as plain info text, not a broken link", async () => {
    mount("/agent-control/activity/more");
    await screen.findByTestId("aac-section-more");
    const deferred = screen.getByTestId("aac-more-spec-deferred");
    expect(deferred).toHaveTextContent("Design Spec");
    expect(deferred).toHaveTextContent(/documented in repo/i);
    expect(deferred).toHaveTextContent(/deferred/i);
    // Confirm it is NOT an anchor or routed <Link> — no href attribute.
    expect(deferred.tagName.toLowerCase()).not.toBe("a");
  });
});
