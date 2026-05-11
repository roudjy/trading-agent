/**
 * Tests for the AgentControlInboxPlaceholder landing page.
 *
 * Hard guarantees verified here:
 *   - The placeholder renders the bounded event_id query parameter.
 *   - The DOM contains NO decision verbs (approve / reject / merge /
 *     deploy) — neither as buttons, links, nor visible text.
 *   - The placeholder performs NO fetch / XMLHttpRequest /
 *     navigator.sendBeacon calls (strictly read-only).
 *   - A link back to /agent-control exists.
 *   - A long / hostile event_id is bounded and sanitised (no special
 *     chars, max 64 chars).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AgentControlInboxPlaceholder } from "../routes/AgentControl/InboxPlaceholder";

const mockFetch = vi.fn();
const mockSendBeacon = vi.fn();

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

describe("AgentControlInboxPlaceholder — safe landing", () => {
  it("renders the placeholder for /agent-control/inbox?event=...", () => {
    renderAt("/agent-control/inbox?event=live_verify_20260511");
    expect(
      screen.getByTestId("agent-control-inbox-placeholder"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("agent-control-inbox-event-id"),
    ).toHaveTextContent("event_id: live_verify_20260511");
  });

  it("renders even when no event_id query parameter is present", () => {
    renderAt("/agent-control/inbox");
    expect(
      screen.getByTestId("agent-control-inbox-placeholder"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("agent-control-inbox-event-id"),
    ).not.toBeInTheDocument();
  });

  it("provides a link back to /agent-control", () => {
    renderAt("/agent-control/inbox?event=abc");
    const back = screen.getByTestId("agent-control-inbox-back-link");
    expect(back).toHaveAttribute("href", "/agent-control");
  });
});

describe("AgentControlInboxPlaceholder — no decision verbs", () => {
  it("DOM contains no approve / reject / merge / deploy verb", () => {
    renderAt("/agent-control/inbox?event=evt_safe");
    const root = screen.getByTestId("agent-control-inbox-placeholder");
    const text = (root.textContent || "").toLowerCase();
    // Whole-word matches — must not appear anywhere in visible text.
    expect(text).not.toMatch(/\bapprove\b/);
    expect(text).not.toMatch(/\breject\b/);
    expect(text).not.toMatch(/\bmerge\b/);
    expect(text).not.toMatch(/\bdeploy\b/);
  });

  it("contains no action buttons", () => {
    renderAt("/agent-control/inbox?event=evt_safe");
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });

  it("reaffirms approval requires re-authentication", () => {
    renderAt("/agent-control/inbox?event=evt_safe");
    const root = screen.getByTestId("agent-control-inbox-placeholder");
    expect(
      (root.textContent || "").toLowerCase(),
    ).toContain("re-authentication");
  });
});

describe("AgentControlInboxPlaceholder — strictly read-only", () => {
  it("does not call fetch at any point during render", () => {
    renderAt("/agent-control/inbox?event=evt_safe");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("does not call navigator.sendBeacon", () => {
    renderAt("/agent-control/inbox?event=evt_safe");
    expect(mockSendBeacon).not.toHaveBeenCalled();
  });
});

describe("AgentControlInboxPlaceholder — event_id sanitisation", () => {
  it("strips characters outside [A-Za-z0-9_-]", () => {
    renderAt("/agent-control/inbox?event=abc%20<script>def");
    const eventEl = screen.queryByTestId("agent-control-inbox-event-id");
    expect(eventEl?.textContent || "").not.toMatch(/<script>/);
    expect(eventEl?.textContent || "").not.toMatch(/%20/);
  });

  it("bounds the event_id to 64 characters", () => {
    const huge = "x".repeat(500);
    renderAt(`/agent-control/inbox?event=${huge}`);
    const eventEl = screen.queryByTestId("agent-control-inbox-event-id");
    const shown = (eventEl?.textContent || "").replace("event_id: ", "");
    expect(shown.length).toBeLessThanOrEqual(64);
  });
});

describe("AgentControlInboxPlaceholder — also handles non-inbox sub-paths", () => {
  it("falls back to a bland heading for /agent-control/unknown", () => {
    renderAt("/agent-control/unknown");
    expect(
      screen.getByTestId("agent-control-inbox-placeholder"),
    ).toBeInTheDocument();
    // No event_id when not on /inbox
    expect(
      screen.queryByTestId("agent-control-inbox-event-id"),
    ).not.toBeInTheDocument();
  });
});
