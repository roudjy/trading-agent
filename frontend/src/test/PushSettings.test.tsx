/**
 * Tests for the v3.15.16.N2b2b PushSettings card.
 *
 * Hard guarantees verified here:
 *   - The component does NOT auto-subscribe on mount. The Enable
 *     button must be tapped explicitly.
 *   - When the backend reports `vapid_public_present=false`, the
 *     Enable button is disabled and the UI shows a clear "not
 *     configured" state.
 *   - The Disable button is hidden when no subscription is
 *     registered.
 *   - The Disable button is visible when a subscription is
 *     registered.
 *   - The Send-test-push button calls /api/push/test only.
 *   - The DOM contains NO decision verbs (approve / reject / merge /
 *     deploy).
 *   - The DOM contains the disclaimer telling the operator that
 *     approval requires re-authentication, not a notification tap.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import { PushSettings } from "../routes/AgentControl/PushSettings";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  mockFetch.mockReset();
});

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
  });
}

function statusBody(opts: {
  count?: number;
  vapid?: boolean;
  last_subscribed_at?: string;
}) {
  return {
    status: "ok",
    count: opts.count ?? 0,
    last_subscribed_at: opts.last_subscribed_at ?? "",
    vapid_public_present: opts.vapid ?? false,
    max_active_subscriptions: 16,
  };
}

describe("PushSettings — no auto-subscribe", () => {
  it("does not call /api/push/subscribe on mount", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(statusBody({ count: 0, vapid: true })),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-subscribed-state")).toBeTruthy();
    });
    // Only ONE fetch on mount: GET /api/push/status. Subscribe is
    // never called automatically.
    const calls = mockFetch.mock.calls;
    const subscribeCalls = calls.filter(
      ([url]) => typeof url === "string" && url.includes("/api/push/subscribe"),
    );
    expect(subscribeCalls.length).toBe(0);
  });
});

describe("PushSettings — VAPID-missing state", () => {
  it("disables Enable button when vapid_public_present=false", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(statusBody({ count: 0, vapid: false })),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-vapid-state").textContent).toContain(
        "not configured",
      );
    });
    const enableButton = screen.getByTestId(
      "push-enable-button",
    ) as HTMLButtonElement;
    expect(enableButton.disabled).toBe(true);
  });

  it("shows clear 'not configured' text", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(statusBody({ count: 0, vapid: false })),
    );
    render(<PushSettings />);
    await waitFor(() => {
      const txt = screen.getByTestId("push-vapid-state").textContent ?? "";
      expect(txt.toLowerCase()).toContain("not configured");
    });
  });
});

describe("PushSettings — Disable button visibility", () => {
  it("hides Disable when not subscribed", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(statusBody({ count: 0, vapid: true })),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-subscribed-state")).toBeTruthy();
    });
    expect(screen.queryByTestId("push-disable-button")).toBeNull();
  });

  it("shows Disable when subscribed (count >= 1)", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        statusBody({
          count: 1,
          vapid: true,
          last_subscribed_at: "2026-05-09T00:00:00Z",
        }),
      ),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-disable-button")).toBeTruthy();
    });
  });
});

describe("PushSettings — Send test push", () => {
  it("POSTs /api/push/test only and shows synthetic event", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        statusBody({
          count: 1,
          vapid: true,
          last_subscribed_at: "2026-05-09T00:00:00Z",
        }),
      ),
    );
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        status: "ok",
        test_event: {
          event_id: "ade_test_20260509000000",
          event_kind: "intake_candidate_eligible",
          event_severity: "push_info",
          title: "ADE test push",
          summary: "Synthetic test event.",
          open_at: "/agent-control/inbox?event=ade_test_20260509000000",
        },
        would_dispatch_via: "n2b1_outbox_stub_provider",
        real_push_sent: false,
      }),
    );

    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-test-button")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("push-test-button"));
    await waitFor(() => {
      expect(screen.getByTestId("push-flash").textContent).toContain(
        "ade_test_",
      );
    });
    // Second fetch (after the initial status) should be /api/push/test.
    const calls = mockFetch.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    const testCall = calls.find(
      ([url]) => typeof url === "string" && url.includes("/api/push/test"),
    );
    expect(testCall).toBeTruthy();
    // Did NOT call /api/push/subscribe.
    const subscribeCall = calls.find(
      ([url]) => typeof url === "string" && url.includes("/api/push/subscribe"),
    );
    expect(subscribeCall).toBeFalsy();
  });
});

describe("PushSettings — no decision verbs in DOM", () => {
  it("does not render approve / reject / merge / deploy buttons", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        statusBody({
          count: 1,
          vapid: true,
          last_subscribed_at: "2026-05-09T00:00:00Z",
        }),
      ),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-settings-card")).toBeTruthy();
    });
    const card = screen.getByTestId("push-settings-card");
    const verbs = ["approve", "reject", "merge", "deploy"];
    const clickable = card.querySelectorAll("button, a");
    for (const el of Array.from(clickable)) {
      const txt = (el.textContent ?? "").toLowerCase();
      for (const v of verbs) {
        if (txt.includes(v)) {
          throw new Error(
            "PushSettings rendered a decision verb in clickable element: " +
              JSON.stringify(txt),
          );
        }
      }
    }
  });

  it("renders the disclaimer reminding the operator that approval needs re-auth", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(statusBody({ count: 0, vapid: true })),
    );
    render(<PushSettings />);
    await waitFor(() => {
      const card = screen.getByTestId("push-settings-card");
      const txt = (card.textContent ?? "").toLowerCase();
      expect(txt).toContain("re-auth");
    });
  });
});

describe("PushSettings — fallback when status endpoint not available", () => {
  it("renders an error state without crashing", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response("not found", { status: 404 }),
    );
    render(<PushSettings />);
    await waitFor(() => {
      expect(screen.getByTestId("push-status-error")).toBeTruthy();
    });
    // Enable button still rendered but disabled.
    const enableButton = screen.getByTestId(
      "push-enable-button",
    ) as HTMLButtonElement;
    expect(enableButton.disabled).toBe(true);
  });
});
