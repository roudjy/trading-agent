/**
 * Tests for AgentControlMergeRecommendation — the N5c read-only
 * PWA surface over the existing N5a merge-recommendation API.
 *
 * Hard guarantees verified here:
 *   - Read-only banner is always rendered, in both list + detail views.
 *   - Only the read-only N5a endpoints under
 *     ``/api/agent-control/merge-recommendation/`` are fetched.
 *   - No call to any N4b ``/api/agent-control/approval-token/*`` URL,
 *     no call to the N3b ``/api/agent-control/mobile-inbox/*`` URL.
 *   - Every fetch is a same-origin GET. No POST / PUT / PATCH / DELETE.
 *   - No ``<button>`` elements with executable decision verbs (approve,
 *     reject, deploy, execute) appear in the DOM.
 *   - List renders bounded closed-schema rows from the mocked API.
 *   - Detail renders the bounded closed-schema row for status=ok.
 *   - Empty / not_available / not_found / invalid_recommendation_id /
 *     malformed / network failure all collapse to safe states.
 *   - The bounded route param is sanitised before fetch (charset +
 *     length).
 *   - A link back to /agent-control is always rendered.
 *   - navigator.sendBeacon is never called.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AgentControlMergeRecommendation } from "../routes/AgentControl/MergeRecommendation";

const mockFetch = vi.fn();
const mockSendBeacon = vi.fn();

const LIST_URL = "/api/agent-control/merge-recommendation/list";
const DETAIL_BASE = "/api/agent-control/merge-recommendation/detail/";

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
  });
}

function row(
  recommendation_id: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    recommendation_id,
    pr_number: 42,
    head_sha: "deadbeefdeadbeef0000000000000001",
    head_ref: "feature/branch-" + recommendation_id,
    base_ref: "main",
    observer_classification: "open_clean_mergeable",
    inbox_blocked_count: 0,
    inbox_critical_count: 0,
    inbox_needs_review_count: 0,
    recommendation_action: "recommend_human_merge",
    recommendation_reason: "pr_clean_and_no_blocking_inbox",
    evaluated_at: "2026-05-11T20:00:00Z",
    ...overrides,
  };
}

function listOkEnvelope(
  rows: ReturnType<typeof row>[],
  overrides: Record<string, unknown> = {},
) {
  return {
    kind: "agent_control_merge_recommendation_list",
    schema_version: 1,
    module_version: "v3.15.16.N5a",
    status: "ok",
    rows,
    counts: { rows: rows.length },
    generated_at_utc: "2026-05-11T20:30:00Z",
    artifact_path: "logs/development_merge_recommendation/latest.json",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    ...overrides,
  };
}

function detailOkEnvelope(r: ReturnType<typeof row>) {
  return {
    kind: "agent_control_merge_recommendation_detail",
    schema_version: 1,
    module_version: "v3.15.16.N5a",
    status: "ok",
    row: r,
    generated_at_utc: "2026-05-11T20:30:00Z",
    artifact_path: "logs/development_merge_recommendation/latest.json",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/agent-control/merge-recommendation"
          element={<AgentControlMergeRecommendation />}
        />
        <Route
          path="/agent-control/merge-recommendation/:recommendationId"
          element={<AgentControlMergeRecommendation />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  if (typeof navigator !== "undefined") {
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      value: mockSendBeacon,
    });
  }
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  mockFetch.mockReset();
  mockSendBeacon.mockReset();
});

// ---------------------------------------------------------------------------
// Banner + back link — always rendered
// ---------------------------------------------------------------------------

describe("AgentControlMergeRecommendation — banner + structure", () => {
  it("always renders the read-only banner on the list view", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalled(),
    );
    expect(
      screen.getByTestId("agent-control-merge-recommendation-banner"),
    ).toHaveTextContent(
      /read-only merge recommendation\. merge execution is not implemented/i,
    );
  });

  it("always renders the read-only banner on the detail view", async () => {
    mockFetch.mockResolvedValue(jsonResponse(detailOkEnvelope(row("mr_1"))));
    renderAt("/agent-control/merge-recommendation/mr_1");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-recommendation-banner"),
    ).toHaveTextContent(
      /read-only merge recommendation\. merge execution is not implemented/i,
    );
  });

  it("always renders the back link to /agent-control on list", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-recommendation-back-link"),
    ).toHaveAttribute("href", "/agent-control");
  });

  it("always renders the back link to /agent-control on detail", async () => {
    mockFetch.mockResolvedValue(jsonResponse(detailOkEnvelope(row("mr_1"))));
    renderAt("/agent-control/merge-recommendation/mr_1");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-recommendation-back-link"),
    ).toHaveAttribute("href", "/agent-control");
  });
});

// ---------------------------------------------------------------------------
// List view — happy path / empty / not_available / network / malformed
// ---------------------------------------------------------------------------

describe("AgentControlMergeRecommendation — list view", () => {
  it("fetches only the N5a list endpoint with same-origin GET", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(LIST_URL);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    expect(method).toBe("GET");
    expect((init as RequestInit | undefined)?.credentials).toBe("include");
  });

  it("renders bounded closed-schema rows from the mocked list", async () => {
    const rows = [
      row("mr_alpha", {
        pr_number: 101,
        recommendation_action: "recommend_human_merge",
        observer_classification: "open_clean_mergeable",
      }),
      row("mr_beta", {
        pr_number: 202,
        recommendation_action: "recommend_hold",
        recommendation_reason: "pr_blocked_or_dirty",
        observer_classification: "open_blocked_or_dirty",
      }),
    ];
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope(rows)));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-list"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("agent-control-merge-recommendation-row-mr_alpha"),
    ).toHaveTextContent(/PR #101/);
    expect(
      screen.getByTestId("agent-control-merge-recommendation-row-mr_beta"),
    ).toHaveTextContent(/PR #202/);
    expect(
      screen.getByTestId("agent-control-merge-recommendation-list-count"),
    ).toHaveTextContent(/2 recommendation\(s\)/);
    // Each row links to the bounded detail route.
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-link-mr_alpha",
      ),
    ).toHaveAttribute(
      "href",
      "/agent-control/merge-recommendation/mr_alpha",
    );
  });

  it("renders empty state when the API returns no rows", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("agent-control-merge-recommendation-list"),
    ).not.toBeInTheDocument();
  });

  it("renders not_available when API reports artefact missing", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        kind: "agent_control_merge_recommendation_list",
        schema_version: 1,
        status: "not_available",
        reason: "missing",
        rows: [],
        counts: { rows: 0 },
        step5_implementation_allowed: false,
        step5_enabled_substage: "none",
      }),
    );
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on network failure", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on malformed body", async () => {
    mockFetch.mockResolvedValue(
      new Response("not json", {
        status: 200,
        headers: { "content-type": "text/plain" },
      }),
    );
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// Detail view — happy path / not_found / invalid / not_available / network
// ---------------------------------------------------------------------------

describe("AgentControlMergeRecommendation — detail view", () => {
  it("fetches the detail endpoint for the bounded recommendation_id", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(row("mr_render"))),
    );
    renderAt("/agent-control/merge-recommendation/mr_render");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(`${DETAIL_BASE}mr_render`);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    expect(method).toBe("GET");
  });

  it("renders closed-schema scalars from the detail row", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        detailOkEnvelope(
          row("mr_render", {
            pr_number: 99,
            head_ref: "feature/test",
            base_ref: "main",
            observer_classification: "open_clean_mergeable",
            recommendation_action: "recommend_human_merge",
            recommendation_reason: "pr_clean_and_no_blocking_inbox",
            inbox_blocked_count: 0,
            inbox_critical_count: 1,
            inbox_needs_review_count: 2,
            evaluated_at: "2026-05-11T20:00:00Z",
          }),
        ),
      ),
    );
    renderAt("/agent-control/merge-recommendation/mr_render");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-detail"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-recommendation-id",
      ),
    ).toHaveTextContent("mr_render");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-pr-number",
      ),
    ).toHaveTextContent("99");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-head-ref",
      ),
    ).toHaveTextContent("feature/test");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-base-ref",
      ),
    ).toHaveTextContent("main");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-observer-classification",
      ),
    ).toHaveTextContent("open_clean_mergeable");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-recommendation-action",
      ),
    ).toHaveTextContent("recommend_human_merge");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-recommendation-reason",
      ),
    ).toHaveTextContent("pr_clean_and_no_blocking_inbox");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-inbox-blocked-count",
      ),
    ).toHaveTextContent("0");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-inbox-critical-count",
      ),
    ).toHaveTextContent("1");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-inbox-needs-review-count",
      ),
    ).toHaveTextContent("2");
    expect(
      screen.getByTestId(
        "agent-control-merge-recommendation-detail-evaluated-at",
      ),
    ).toHaveTextContent("2026-05-11T20:00:00Z");
  });

  it("renders not_found when the API reports an unknown recommendation_id", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_recommendation_detail",
          schema_version: 1,
          status: "not_found",
          reason: "no_matching_recommendation_id",
          artifact_path:
            "logs/development_merge_recommendation/latest.json",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 404 },
      ),
    );
    renderAt("/agent-control/merge-recommendation/mr_missing");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-detail-not-found",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders invalid state when the API rejects the recommendation_id", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_recommendation_detail",
          schema_version: 1,
          status: "invalid_recommendation_id",
          reason: "bad_charset",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 400 },
      ),
    );
    renderAt("/agent-control/merge-recommendation/mr_bad");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-detail-invalid",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on detail artefact missing", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_recommendation_detail",
          schema_version: 1,
          status: "not_available",
          reason: "missing",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 404 },
      ),
    );
    renderAt("/agent-control/merge-recommendation/mr_x");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-detail-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on network failure in the detail view", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderAt("/agent-control/merge-recommendation/mr_x");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-recommendation-detail-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// recommendation_id sanitisation
// ---------------------------------------------------------------------------

describe("AgentControlMergeRecommendation — recommendation_id sanitisation", () => {
  it("strips characters outside [A-Za-z0-9_-] before display", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_recommendation_detail",
          schema_version: 1,
          status: "not_found",
          reason: "no_matching_recommendation_id",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 404 },
      ),
    );
    renderAt("/agent-control/merge-recommendation/mr_safe<script>x");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const detailId = screen.getByTestId(
      "agent-control-merge-recommendation-detail-id",
    );
    expect((detailId.textContent || "").toLowerCase()).not.toContain(
      "<script>",
    );
  });

  it("bounds the recommendation_id to 128 characters before display", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_recommendation_detail",
          schema_version: 1,
          status: "not_found",
          reason: "no_matching_recommendation_id",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 404 },
      ),
    );
    const huge = "m".repeat(500);
    renderAt(`/agent-control/merge-recommendation/${huge}`);
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const detailId = screen.getByTestId(
      "agent-control-merge-recommendation-detail-id",
    );
    const shown = (detailId.textContent || "").replace(
      "recommendation_id: ",
      "",
    );
    expect(shown.length).toBeLessThanOrEqual(128);
  });
});

// ---------------------------------------------------------------------------
// Read-only invariants
// ---------------------------------------------------------------------------

describe("AgentControlMergeRecommendation — read-only invariants", () => {
  it("never issues a POST / PUT / PATCH / DELETE on the list view", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      const method = init?.method ?? "GET";
      expect(["GET", "HEAD"]).toContain(method);
    }
  });

  it("never issues a POST / PUT / PATCH / DELETE on the detail view", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(row("mr_safe"))),
    );
    renderAt("/agent-control/merge-recommendation/mr_safe");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      const method = init?.method ?? "GET";
      expect(["GET", "HEAD"]).toContain(method);
    }
  });

  it("never fetches an approval-token endpoint", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain("approval-token");
    }
  });

  it("never fetches a mobile-inbox endpoint from the merge-recommendation surface", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain("/api/agent-control/mobile-inbox/");
    }
  });

  it("only fetches the N5a merge-recommendation endpoints", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).toMatch(/^\/api\/agent-control\/merge-recommendation\//);
    }
  });

  it("does not call navigator.sendBeacon (list view)", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });

  it("does not call navigator.sendBeacon (detail view)", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(row("mr_safe"))),
    );
    renderAt("/agent-control/merge-recommendation/mr_safe");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });

  it("contains no executable decision-verb buttons on list", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-list"),
      ).toBeInTheDocument(),
    );
    const buttons = screen.queryAllByRole("button");
    // No <button> at all on the read-only list surface.
    expect(buttons).toHaveLength(0);
  });

  it("contains no executable decision-verb buttons on detail", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(row("mr_safe"))),
    );
    renderAt("/agent-control/merge-recommendation/mr_safe");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-detail"),
      ).toBeInTheDocument(),
    );
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });

  it("does not render the words 'approve' / 'reject' / 'deploy' on list", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([row("mr_1")])));
    renderAt("/agent-control/merge-recommendation");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-list"),
      ).toBeInTheDocument(),
    );
    const root = screen.getByTestId(
      "agent-control-merge-recommendation-root",
    );
    const text = (root.textContent || "").toLowerCase();
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
  });

  it("does not render the words 'approve' / 'reject' / 'deploy' on detail", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(row("mr_safe"))),
    );
    renderAt("/agent-control/merge-recommendation/mr_safe");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-recommendation-detail"),
      ).toBeInTheDocument(),
    );
    const root = screen.getByTestId(
      "agent-control-merge-recommendation-root",
    );
    const text = (root.textContent || "").toLowerCase();
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
  });
});
