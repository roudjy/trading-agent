/**
 * Tests for CopyOperatorPhraseButton — B2.0d clipboard-only pins.
 *
 * Pins:
 *   - navigator.clipboard.writeText called with the exact phrase.
 *   - No fetch / no XHR / no sendBeacon when the button is clicked.
 *   - Success feedback renders then clears after the timeout.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
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

const PHRASE = "GO A18 promotion operator-promote";

const detailWithPhrase = {
  kind: "agent_control_activity_items_detail",
  schema_version: 1,
  module_version: "v3.15.16.A15.B2.0c.api",
  status: "ok",
  step5_implementation_allowed: false,
  step5_enabled_substage: "none",
  level6_enabled: false,
  work_item: {
    item_id: "wi_phrase_test",
    title: "Phrase target",
    source_kind: "generated_lane_promotion",
    source_path:
      "logs/development_generated_lane_promotion_report/latest.json",
    current_stage: "needs_human",
    owner_role: "release_gate_agent",
    risk: "medium",
    human_needed: true,
    latest_verdict: "promotion_allowed=False",
    next_action: "Operator-go required",
    updated_at: "2026-05-14T07:00:00Z",
    summary: "synthetic",
    event_ids: [],
  },
  agent_events: [],
  human_actions: [
    {
      action_id: "ha_phrase_test",
      item_id: "wi_phrase_test",
      severity: "medium",
      title: "Phrase target",
      why_required: "Promotion is operator-paced.",
      required_phrase: PHRASE,
      safe_to_ignore: false,
      copy_only: true,
      source_artifact_path:
        "logs/development_generated_lane_promotion_report/latest.json",
      suggested_role: "release_gate_agent",
      created_at: "2026-05-14T07:00:00Z",
    },
  ],
  artefacts_referenced: [],
  generated_at_utc: "2026-05-14T08:00:00Z",
  artifact_path: "logs/development_agent_activity_timeline/latest.json",
};

function _mock() {
  return agentControlApi as unknown as {
    activityItemsDetail: ReturnType<typeof vi.fn>;
  };
}

function mountTrace() {
  return render(
    <MemoryRouter
      initialEntries={["/agent-control/activity/items/wi_phrase_test"]}
    >
      <Routes>
        <Route
          path="/agent-control/activity/*"
          element={<AgentActivity />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

let originalClipboard: typeof navigator.clipboard | undefined;
let originalFetch: typeof globalThis.fetch | undefined;
let originalSendBeacon: typeof navigator.sendBeacon | undefined;
let writeTextSpy: ReturnType<typeof vi.fn>;
let fetchSpy: ReturnType<typeof vi.fn>;
let sendBeaconSpy: ReturnType<typeof vi.fn>;
let xhrSpy: ReturnType<typeof vi.fn>;
let originalXHR: typeof XMLHttpRequest;

beforeEach(() => {
  _mock().activityItemsDetail.mockResolvedValue(detailWithPhrase);

  writeTextSpy = vi.fn().mockResolvedValue(undefined);
  originalClipboard = navigator.clipboard;
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: writeTextSpy },
  });

  fetchSpy = vi.fn();
  originalFetch = globalThis.fetch;
  globalThis.fetch = fetchSpy as unknown as typeof globalThis.fetch;

  sendBeaconSpy = vi.fn();
  originalSendBeacon = navigator.sendBeacon;
  Object.defineProperty(navigator, "sendBeacon", {
    configurable: true,
    value: sendBeaconSpy,
  });

  xhrSpy = vi.fn();
  originalXHR = globalThis.XMLHttpRequest;
  globalThis.XMLHttpRequest = function (this: unknown) {
    xhrSpy();
    return originalXHR
      ? new originalXHR()
      : ({} as XMLHttpRequest);
  } as unknown as typeof XMLHttpRequest;
});

afterEach(() => {
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    });
  }
  if (originalFetch !== undefined) {
    globalThis.fetch = originalFetch;
  }
  if (originalSendBeacon !== undefined) {
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      value: originalSendBeacon,
    });
  }
  if (originalXHR !== undefined) {
    globalThis.XMLHttpRequest = originalXHR;
  }
  vi.clearAllMocks();
});

describe("CopyOperatorPhraseButton clipboard-only pins", () => {
  it("calls navigator.clipboard.writeText with the exact phrase", async () => {
    mountTrace();
    const btn = await screen.findByTestId("aac-copy-phrase");
    fireEvent.click(btn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledTimes(1);
    });
    expect(writeTextSpy).toHaveBeenCalledWith(PHRASE);
  });

  it("does not call fetch when the button is clicked", async () => {
    mountTrace();
    const btn = await screen.findByTestId("aac-copy-phrase");
    const fetchCallsBefore = fetchSpy.mock.calls.length;
    fireEvent.click(btn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledTimes(1);
    });
    expect(fetchSpy.mock.calls.length).toBe(fetchCallsBefore);
  });

  it("does not construct XMLHttpRequest when the button is clicked", async () => {
    mountTrace();
    const btn = await screen.findByTestId("aac-copy-phrase");
    const xhrCallsBefore = xhrSpy.mock.calls.length;
    fireEvent.click(btn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledTimes(1);
    });
    expect(xhrSpy.mock.calls.length).toBe(xhrCallsBefore);
  });

  it("does not call navigator.sendBeacon when the button is clicked", async () => {
    mountTrace();
    const btn = await screen.findByTestId("aac-copy-phrase");
    fireEvent.click(btn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledTimes(1);
    });
    expect(sendBeaconSpy).not.toHaveBeenCalled();
  });

  it("renders Copied feedback then reverts to Copy phrase", async () => {
    mountTrace();
    // Resolve initial render and locate the button with REAL timers
    // (findBy* uses an internal polling timer; fake timers would
    // deadlock it).
    const btn = await screen.findByTestId("aac-copy-phrase");
    // Install fake timers only AFTER the initial mount + element
    // lookup completes, so the setTimeout that reverts the "Copied"
    // label can be advanced deterministically.
    vi.useFakeTimers();
    try {
      fireEvent.click(btn);
      // Flush the clipboard microtask so the success path sets state.
      await act(async () => {
        await Promise.resolve();
      });
      expect(btn).toHaveTextContent(/Copied/);
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(btn).toHaveTextContent(/Copy phrase/);
    } finally {
      vi.useRealTimers();
    }
  });
});
