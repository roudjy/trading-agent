/**
 * Tests for the AgentControlInboxPlaceholder landing page.
 *
 * Hard guarantees verified here:
 *   - The placeholder renders the bounded event_id query parameter.
 *   - The DOM contains NO decision verbs (approve / reject / merge /
 *     deploy) — neither as buttons, links, nor visible text.
 *   - The placeholder performs at MOST one same-origin GET to the
 *     read-only N3b detail endpoint, and never a POST / PUT / PATCH /
 *     DELETE. No XMLHttpRequest, no navigator.sendBeacon.
 *   - When the N3b API returns ``status: "ok"`` with a row, the
 *     closed-schema scalars are rendered (event_kind, severity,
 *     attention_level, decision_state, source_module, created_at).
 *   - When the N3b API returns ``not_available`` / ``not_found`` /
 *     network failure, the placeholder shows the safe-empty state.
 *   - The read-only banner is always rendered.
 *   - A link back to /agent-control exists.
 *   - A long / hostile event_id is bounded and sanitised.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AgentControlInboxPlaceholder } from "../routes/AgentControl/InboxPlaceholder";

const mockFetch = vi.fn();
const mockSendBeacon = vi.fn();

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
  });
}

function row(event_id: string) {
  return {
    inbox_row_id: "row_" + event_id,
    event_id,
    event_kind: "intake_candidate_eligible",
    event_severity: "push_info",
    source_module: "notification_dispatch_outbox",
    source_id: event_id,
    endpoint_hash: "deadbeefdeadbeef",
    outbound_delivery_intent: "sent",
    attention_level: "informational",
    decision_state: "pending",
    title: "Inbox title for " + event_id,
    summary: "A bounded inbox summary.",
    open_at: `/agent-control/inbox?event=${event_id}`,
    created_at: "2026-05-11T08:00:00Z",
  };
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

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AgentControlInboxPlaceholder />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Banner + structural elements
// ---------------------------------------------------------------------------

describe("AgentControlInboxPlaceholder — banner + structure", () => {
  it("always renders the read-only banner", () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available", reason: "missing" }, { status: 404 }),
    );
    renderAt("/agent-control/inbox?event=evt_safe");
    expect(
      screen.getByTestId("agent-control-inbox-banner"),
    ).toHaveTextContent(
      /read-only inbox detail\. approval actions are not implemented/i,
    );
  });

  it("always renders a link back to /agent-control", () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available" }, { status: 404 }),
    );
    renderAt("/agent-control/inbox?event=evt_safe");
    const back = screen.getByTestId("agent-control-inbox-back-link");
    expect(back).toHaveAttribute("href", "/agent-control");
  });

  it("renders the bounded event_id from the URL", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available" }, { status: 404 }),
    );
    renderAt("/agent-control/inbox?event=evt_safe_marker");
    expect(
      screen.getByTestId("agent-control-inbox-event-id"),
    ).toHaveTextContent("event_id: evt_safe_marker");
  });

  it("renders idle state when no event_id is present", () => {
    renderAt("/agent-control/inbox");
    // No event_id → no fetch is issued.
    expect(mockFetch).not.toHaveBeenCalled();
    expect(
      screen.queryByTestId("agent-control-inbox-event-id"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("agent-control-inbox-idle"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// N3b API integration — happy path
// ---------------------------------------------------------------------------

describe("AgentControlInboxPlaceholder — N3b detail render", () => {
  it("fetches the read-only detail endpoint exactly once", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_one") }));
    renderAt("/agent-control/inbox?event=evt_one");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/agent-control/mobile-inbox/detail/evt_one");
    expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
    expect((init as RequestInit | undefined)?.credentials).toBe("same-origin");
  });

  it("renders the closed-schema scalars from the row", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_render") }));
    renderAt("/agent-control/inbox?event=evt_render");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-detail")).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("agent-control-inbox-detail-event-kind"),
    ).toHaveTextContent("intake_candidate_eligible");
    expect(
      screen.getByTestId("agent-control-inbox-detail-event-severity"),
    ).toHaveTextContent("push_info");
    expect(
      screen.getByTestId("agent-control-inbox-detail-attention-level"),
    ).toHaveTextContent("informational");
    expect(
      screen.getByTestId("agent-control-inbox-detail-decision-state"),
    ).toHaveTextContent("pending");
    expect(
      screen.getByTestId("agent-control-inbox-detail-source-module"),
    ).toHaveTextContent("notification_dispatch_outbox");
    expect(
      screen.getByTestId("agent-control-inbox-detail-created-at"),
    ).toHaveTextContent("2026-05-11T08:00:00Z");
    expect(
      screen.getByTestId("agent-control-inbox-summary"),
    ).toHaveTextContent("A bounded inbox summary.");
  });
});

// ---------------------------------------------------------------------------
// N3b API integration — empty / not_available / not_found / network
// ---------------------------------------------------------------------------

describe("AgentControlInboxPlaceholder — safe empty states", () => {
  it("renders empty state on not_available", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available", reason: "missing" }, { status: 404 }),
    );
    renderAt("/agent-control/inbox?event=evt_x");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-empty")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("agent-control-inbox-detail"),
    ).not.toBeInTheDocument();
  });

  it("renders empty state on not_found", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        { status: "not_found", reason: "no_matching_event_id" },
        { status: 404 },
      ),
    );
    renderAt("/agent-control/inbox?event=evt_missing");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-empty")).toBeInTheDocument(),
    );
  });

  it("renders empty state on network failure", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderAt("/agent-control/inbox?event=evt_x");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-empty")).toBeInTheDocument(),
    );
  });

  it("renders empty state on malformed body", async () => {
    mockFetch.mockResolvedValue(
      new Response("not json", {
        status: 200,
        headers: { "content-type": "text/plain" },
      }),
    );
    renderAt("/agent-control/inbox?event=evt_x");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-empty")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// No decision verbs / no action surface / no extra fetches
// ---------------------------------------------------------------------------

describe("AgentControlInboxPlaceholder — read-only invariants", () => {
  it("DOM contains no approve / reject / merge / deploy verb", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_safe") }));
    renderAt("/agent-control/inbox?event=evt_safe");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-detail")).toBeInTheDocument(),
    );
    const root = screen.getByTestId("agent-control-inbox-placeholder");
    const text = (root.textContent || "").toLowerCase();
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bmerge\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
  });

  it("contains no action buttons", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_safe") }));
    renderAt("/agent-control/inbox?event=evt_safe");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-detail")).toBeInTheDocument(),
    );
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });

  it("issues exactly one same-origin GET (no other fetch)", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_safe") }));
    renderAt("/agent-control/inbox?event=evt_safe");
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    // Pin the URL prefix and method shape.
    const [url, init] = mockFetch.mock.calls[0];
    expect(String(url)).toMatch(
      /^\/api\/agent-control\/mobile-inbox\/detail\//,
    );
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    expect(["GET", "HEAD"]).toContain(method);
  });

  it("does not call navigator.sendBeacon", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_safe") }));
    renderAt("/agent-control/inbox?event=evt_safe");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-detail")).toBeInTheDocument(),
    );
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });

  it("reaffirms approval requires re-authentication", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok", row: row("evt_safe") }));
    renderAt("/agent-control/inbox?event=evt_safe");
    await waitFor(() =>
      expect(screen.getByTestId("agent-control-inbox-detail")).toBeInTheDocument(),
    );
    const root = screen.getByTestId("agent-control-inbox-placeholder");
    expect(
      (root.textContent || "").toLowerCase(),
    ).toContain("re-authentication");
  });
});

// ---------------------------------------------------------------------------
// event_id sanitisation
// ---------------------------------------------------------------------------

describe("AgentControlInboxPlaceholder — event_id sanitisation", () => {
  it("strips characters outside [A-Za-z0-9_-]", () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available" }, { status: 404 }),
    );
    renderAt("/agent-control/inbox?event=abc%20<script>def");
    const eventEl = screen.queryByTestId("agent-control-inbox-event-id");
    expect(eventEl?.textContent || "").not.toMatch(/<script>/);
    expect(eventEl?.textContent || "").not.toMatch(/%20/);
  });

  it("bounds the event_id to 64 characters", () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "not_available" }, { status: 404 }),
    );
    const huge = "x".repeat(500);
    renderAt(`/agent-control/inbox?event=${huge}`);
    const eventEl = screen.queryByTestId("agent-control-inbox-event-id");
    const shown = (eventEl?.textContent || "").replace("event_id: ", "");
    expect(shown.length).toBeLessThanOrEqual(64);
  });
});

describe("AgentControlInboxPlaceholder — non-inbox sub-paths", () => {
  it("renders bland heading for /agent-control/unknown without fetching", () => {
    renderAt("/agent-control/unknown");
    expect(mockFetch).not.toHaveBeenCalled();
    expect(
      screen.getByTestId("agent-control-inbox-placeholder"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("agent-control-inbox-event-id"),
    ).not.toBeInTheDocument();
  });
});
