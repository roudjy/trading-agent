/**
 * Tests for AgentControlMergePreflight — the v3.15.16.N5b.phase1
 * read-only PWA surface over the existing N5b Phase 1 merge-preflight
 * API.
 *
 * Hard guarantees verified here:
 *   - Read-only banner is always rendered, in both list + detail views.
 *   - Banner literal is exactly
 *     "Dry-run only. Live merge execution is not implemented."
 *   - Only the read-only N5b endpoints under
 *     ``/api/agent-control/merge-preflight/`` are fetched.
 *   - No call to any N4b ``/api/agent-control/approval-token/*`` URL,
 *     no call to the N3b ``/api/agent-control/mobile-inbox/*`` URL,
 *     no call to any hypothetical merge-execution endpoint.
 *   - Every fetch is a same-origin GET. No POST / PUT / PATCH / DELETE.
 *   - No ``<button>`` elements appear in the DOM on either view.
 *   - No executable decision verbs (approve / reject / deploy /
 *     execute) appear in the rendered text.
 *   - List renders bounded closed-schema rows from the mocked API.
 *   - Detail renders the bounded closed-schema row for status=ok.
 *   - Empty / not_available / not_found / invalid_preflight_id /
 *     malformed / network failure all collapse to safe states.
 *   - The bounded route param is sanitised before fetch (charset +
 *     length).
 *   - Discipline invariants (dry_run_only / live_merge_implemented /
 *     deploy_coupled / level6_enabled / step5_implementation_allowed
 *     / step5_enabled_substage) surface verbatim from the envelope.
 *   - A link back to /agent-control is always rendered.
 *   - navigator.sendBeacon is never called.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AgentControlMergePreflight } from "../routes/AgentControl/MergePreflight";

const mockFetch = vi.fn();
const mockSendBeacon = vi.fn();

const LIST_URL = "/api/agent-control/merge-preflight/list";
const DETAIL_BASE = "/api/agent-control/merge-preflight/detail/";

const BANNER_LITERAL =
  "Dry-run only. Live merge execution is not implemented.";

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
  });
}

function candidate(
  preflight_id: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    preflight_id,
    recommendation_id: "rec_pr_42",
    pr_number: 42,
    expected_head_sha: "deadbeefdeadbeef0000000000000001",
    observed_head_sha: "deadbeefdeadbeef0000000000000001",
    base_ref: "main",
    head_ref: "feature/branch",
    merge_state: "CLEAN",
    checks_state: "SUCCESS",
    recommendation_action: "recommend_human_merge",
    recommendation_reason: "pr_clean_and_no_blocking_inbox",
    token_required_for_live: true,
    dry_run_verdict: "would_be_live_candidate_if_authorized",
    live_merge_implemented: false,
    stop_conditions: [
      "token_required_for_live",
      "live_merge_not_implemented",
    ],
    audit_note: "dry-run only",
    generated_at_utc: "2026-05-13T12:00:00Z",
    evidence_freshness_seconds: 30,
    ...overrides,
  };
}

function listOkEnvelope(
  rows: ReturnType<typeof candidate>[],
  overrides: Record<string, unknown> = {},
) {
  return {
    kind: "agent_control_merge_preflight_list",
    schema_version: 1,
    module_version: "v3.15.16.N5b.phase1.api",
    status: "ok",
    rows,
    counts: {
      rows: rows.length,
      by_dry_run_verdict: {
        would_block: 0,
        would_require_operator: 0,
        would_be_live_candidate_if_authorized: rows.length,
      },
    },
    generated_at_utc: "2026-05-13T12:30:00Z",
    artifact_path: "logs/development_merge_preflight/latest.json",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    dry_run_only: true,
    live_merge_implemented: false,
    deploy_coupled: false,
    ...overrides,
  };
}

function detailOkEnvelope(r: ReturnType<typeof candidate>) {
  return {
    kind: "agent_control_merge_preflight_detail",
    schema_version: 1,
    module_version: "v3.15.16.N5b.phase1.api",
    status: "ok",
    row: r,
    generated_at_utc: "2026-05-13T12:30:00Z",
    artifact_path: "logs/development_merge_preflight/latest.json",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    level6_enabled: false,
    dry_run_only: true,
    live_merge_implemented: false,
    deploy_coupled: false,
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/agent-control/merge-preflight"
          element={<AgentControlMergePreflight />}
        />
        <Route
          path="/agent-control/merge-preflight/:preflightId"
          element={<AgentControlMergePreflight />}
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
// Banner + structure — always rendered
// ---------------------------------------------------------------------------

describe("AgentControlMergePreflight — banner + structure", () => {
  it("always renders the operator-prescribed banner literal on list", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-preflight-banner"),
    ).toHaveTextContent(BANNER_LITERAL);
  });

  it("always renders the operator-prescribed banner literal on detail", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-preflight-banner"),
    ).toHaveTextContent(BANNER_LITERAL);
  });

  it("always renders the back link to /agent-control on list", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([])));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-preflight-back-link"),
    ).toHaveAttribute("href", "/agent-control");
  });

  it("always renders the back link to /agent-control on detail", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(
      screen.getByTestId("agent-control-merge-preflight-back-link"),
    ).toHaveAttribute("href", "/agent-control");
  });
});

// ---------------------------------------------------------------------------
// List view — happy path / empty / not_available / malformed / network
// ---------------------------------------------------------------------------

describe("AgentControlMergePreflight — list view", () => {
  it("fetches only the N5b list endpoint with same-origin GET", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_1_aaaa")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(LIST_URL);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    expect(method).toBe("GET");
    expect((init as RequestInit | undefined)?.credentials).toBe("include");
  });

  it("renders empty state when the API returns rows=[]", async () => {
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope([])));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("agent-control-merge-preflight-list"),
    ).not.toBeInTheDocument();
    // Discipline invariants still surface on the empty path.
    expect(
      screen.getByTestId("agent-control-merge-preflight-invariants"),
    ).toBeInTheDocument();
  });

  it("renders a would_block candidate with its stop_conditions", async () => {
    const rows = [
      candidate("pf_1_aaaaaaaaaaaa", {
        pr_number: 101,
        dry_run_verdict: "would_block",
        merge_state: "BLOCKED",
        checks_state: "FAILURE",
        stop_conditions: [
          "merge_state_not_clean",
          "checks_not_green",
          "token_required_for_live",
          "live_merge_not_implemented",
        ],
      }),
    ];
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope(rows)));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-list"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-row-pf_1_aaaaaaaaaaaa-verdict",
      ),
    ).toHaveTextContent(/would_block/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-row-pf_1_aaaaaaaaaaaa-merge-state",
      ),
    ).toHaveTextContent(/BLOCKED/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-row-pf_1_aaaaaaaaaaaa-checks-state",
      ),
    ).toHaveTextContent(/FAILURE/);
  });

  it("renders a would_be_live_candidate row with NO action button", async () => {
    const rows = [
      candidate("pf_2_bbbbbbbbbbbb", {
        pr_number: 202,
        dry_run_verdict: "would_be_live_candidate_if_authorized",
        merge_state: "CLEAN",
        checks_state: "SUCCESS",
      }),
    ];
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope(rows)));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-list"),
      ).toBeInTheDocument(),
    );
    // Verdict is rendered verbatim.
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-row-pf_2_bbbbbbbbbbbb-verdict",
      ),
    ).toHaveTextContent(/would_be_live_candidate_if_authorized/);
    // Zero buttons on the route page — even when a candidate is
    // technically a live candidate the UI exposes NO action.
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });

  it("renders the row count and each row links to the bounded detail route", async () => {
    const rows = [
      candidate("pf_a_111111111111", { pr_number: 1 }),
      candidate("pf_b_222222222222", { pr_number: 2 }),
    ];
    mockFetch.mockResolvedValue(jsonResponse(listOkEnvelope(rows)));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-list-count"),
      ).toHaveTextContent(/2 candidate\(s\)/),
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-link-pf_a_111111111111",
      ),
    ).toHaveAttribute(
      "href",
      "/agent-control/merge-preflight/pf_a_111111111111",
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-link-pf_b_222222222222",
      ),
    ).toHaveAttribute(
      "href",
      "/agent-control/merge-preflight/pf_b_222222222222",
    );
  });

  it("renders not_available when the API reports artefact missing", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        kind: "agent_control_merge_preflight_list",
        schema_version: 1,
        status: "not_available",
        reason: "missing",
        rows: [],
        counts: { rows: 0 },
        step5_implementation_allowed: false,
        step5_enabled_substage: "none",
        level6_enabled: false,
        dry_run_only: true,
        live_merge_implemented: false,
        deploy_coupled: false,
      }),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on network failure", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-not-available",
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
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("surfaces the six discipline invariants from the envelope", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_x_xxxxxxxxxxxx")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-invariants"),
      ).toBeInTheDocument(),
    );
    const text = screen.getByTestId(
      "agent-control-merge-preflight-invariants",
    ).textContent || "";
    expect(text).toMatch(/dry_run_only:\s*true/);
    expect(text).toMatch(/live_merge_implemented:\s*false/);
    expect(text).toMatch(/deploy_coupled:\s*false/);
    expect(text).toMatch(/level6_enabled:\s*false/);
    expect(text).toMatch(/step5_implementation_allowed:\s*false/);
    expect(text).toMatch(/step5_enabled_substage:\s*none/);
  });
});

// ---------------------------------------------------------------------------
// Detail view — happy / not_found / invalid / not_available / network
// ---------------------------------------------------------------------------

describe("AgentControlMergePreflight — detail view", () => {
  it("fetches only the bounded N5b detail endpoint with same-origin GET", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(`${DETAIL_BASE}pf_42_deadbeefdead`);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    expect(method).toBe("GET");
    expect((init as RequestInit | undefined)?.credentials).toBe("include");
  });

  it("renders the exact closed-schema row for status=ok", async () => {
    const row = candidate("pf_42_deadbeefdead", {
      pr_number: 77,
      merge_state: "CLEAN",
      checks_state: "SUCCESS",
      dry_run_verdict: "would_be_live_candidate_if_authorized",
    });
    mockFetch.mockResolvedValue(jsonResponse(detailOkEnvelope(row)));
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-detail"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-preflight-id",
      ),
    ).toHaveTextContent(/pf_42_deadbeefdead/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-pr-number",
      ),
    ).toHaveTextContent(/77/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-dry-run-verdict",
      ),
    ).toHaveTextContent(/would_be_live_candidate_if_authorized/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-merge-state",
      ),
    ).toHaveTextContent(/CLEAN/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-checks-state",
      ),
    ).toHaveTextContent(/SUCCESS/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-token-required-for-live",
      ),
    ).toHaveTextContent(/true/);
  });

  it("renders stop_conditions as a bulleted list", async () => {
    const row = candidate("pf_55_aaaaaaaaaaaa", {
      pr_number: 55,
      stop_conditions: [
        "merge_state_not_clean",
        "checks_not_green",
        "token_required_for_live",
        "live_merge_not_implemented",
      ],
    });
    mockFetch.mockResolvedValue(jsonResponse(detailOkEnvelope(row)));
    renderAt("/agent-control/merge-preflight/pf_55_aaaaaaaaaaaa");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-detail"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-stop-conditions",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-stop-condition-merge_state_not_clean",
      ),
    ).toHaveTextContent(/merge_state_not_clean/);
    expect(
      screen.getByTestId(
        "agent-control-merge-preflight-detail-stop-condition-checks_not_green",
      ),
    ).toHaveTextContent(/checks_not_green/);
  });

  it("renders not_found when the API rejects the preflight_id", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_preflight_detail",
          schema_version: 1,
          status: "not_found",
          reason: "no_matching_preflight_id",
          step5_implementation_allowed: false,
          step5_enabled_substage: "none",
        },
        { status: 404 },
      ),
    );
    renderAt("/agent-control/merge-preflight/pf_99_ffffffffffff");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-detail-not-found",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders invalid when the API rejects the preflight_id shape", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          kind: "agent_control_merge_preflight_detail",
          schema_version: 1,
          status: "invalid_preflight_id",
          reason: "bad_charset",
        },
        { status: 400 },
      ),
    );
    renderAt("/agent-control/merge-preflight/pf_x_yyyy");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-detail-invalid",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders not_available on network failure", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-detail-not-available",
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
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "agent-control-merge-preflight-detail-not-available",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("sanitises the route parameter against bad charset before fetch", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    // The route would normally never receive these bytes (Flask
    // refuses), but the bounded sanitisation in the component is a
    // defense-in-depth layer. Inject a path that contains forbidden
    // characters; after sanitisation, only the allowed characters
    // survive.
    renderAt("/agent-control/merge-preflight/pf!@%23_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const [url] = mockFetch.mock.calls[0];
    // The literal `!`, `@`, `%`, `#` (raw form) must NOT be present
    // in the eventual fetched URL.
    expect(url).not.toMatch(/[!@#]/);
  });

  it("surfaces the six discipline invariants from the detail envelope", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-invariants"),
      ).toBeInTheDocument(),
    );
    const text = screen.getByTestId(
      "agent-control-merge-preflight-invariants",
    ).textContent || "";
    expect(text).toMatch(/dry_run_only:\s*true/);
    expect(text).toMatch(/live_merge_implemented:\s*false/);
    expect(text).toMatch(/deploy_coupled:\s*false/);
    expect(text).toMatch(/level6_enabled:\s*false/);
    expect(text).toMatch(/step5_implementation_allowed:\s*false/);
    expect(text).toMatch(/step5_enabled_substage:\s*none/);
  });
});

// ---------------------------------------------------------------------------
// Read-only structural pins — no buttons, no decision verbs,
// no token endpoint, no mutating method, no sendBeacon.
// ---------------------------------------------------------------------------

describe("AgentControlMergePreflight — read-only structural pins", () => {
  it("never issues a POST / PUT / PATCH / DELETE on the list view", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const init = (call[1] as RequestInit | undefined) ?? {};
      const method = (init.method ?? "GET").toUpperCase();
      expect(["POST", "PUT", "PATCH", "DELETE"]).not.toContain(method);
    }
  });

  it("never issues a POST / PUT / PATCH / DELETE on the detail view", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const init = (call[1] as RequestInit | undefined) ?? {};
      const method = (init.method ?? "GET").toUpperCase();
      expect(["POST", "PUT", "PATCH", "DELETE"]).not.toContain(method);
    }
  });

  it("never fetches an approval-token endpoint", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain("approval-token");
    }
  });

  it("never fetches a mobile-inbox endpoint", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain("/api/agent-control/mobile-inbox/");
    }
  });

  it("never fetches any merge-execution / live-merge endpoint", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain("merge-execution");
      expect(url).not.toContain("/n5b/execute");
      expect(url).not.toContain("live-merge");
    }
  });

  it("does not call navigator.sendBeacon (list view)", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });

  it("does not call navigator.sendBeacon (detail view)", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });

  it("contains no buttons on list (read-only by structure)", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-list"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("contains no buttons on detail (read-only by structure)", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-detail"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("does not render the words 'approve' / 'reject' / 'deploy' / 'execute' on list", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(listOkEnvelope([candidate("pf_42_deadbeefdead")])),
    );
    renderAt("/agent-control/merge-preflight");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-list"),
      ).toBeInTheDocument(),
    );
    const text = (
      screen.getByTestId("agent-control-merge-preflight-root")
        .textContent || ""
    ).toLowerCase();
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
    expect(text).not.toMatch(/\bexecute\b/);
  });

  it("does not render the words 'approve' / 'reject' / 'deploy' / 'execute' on detail", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-detail"),
      ).toBeInTheDocument(),
    );
    const text = (
      screen.getByTestId("agent-control-merge-preflight-root")
        .textContent || ""
    ).toLowerCase();
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
    expect(text).not.toMatch(/\bexecute\b/);
  });

  it("does not embed any raw token-shaped literal in the DOM", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(detailOkEnvelope(candidate("pf_42_deadbeefdead"))),
    );
    renderAt("/agent-control/merge-preflight/pf_42_deadbeefdead");
    await waitFor(() =>
      expect(
        screen.getByTestId("agent-control-merge-preflight-detail"),
      ).toBeInTheDocument(),
    );
    const text =
      screen.getByTestId("agent-control-merge-preflight-root").textContent ||
      "";
    expect(text).not.toMatch(/Bearer\s+/);
    // Two-dot JWT-style header.payload.signature.
    expect(text).not.toMatch(/[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/);
  });
});
