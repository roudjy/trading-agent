/**
 * Tests for N4c — ApprovalTokenDiagnostics PWA surface.
 *
 * Hard guarantees verified here:
 *
 *   * Status panel renders configured / unconfigured / 401 / 503 /
 *     network / malformed states correctly.
 *   * Mint posts a bounded body to /api/agent-control/approval-token/mint
 *     and the closed-envelope scalars (kid / intent / event_id /
 *     issued_at_utc / expires_at_utc) appear in the DOM.
 *   * The raw token string never appears in the rendered DOM
 *     (regression guard against accidental token leakage).
 *   * Verify, replay, and binding-mismatch all POST to
 *     /api/agent-control/approval-token/verify with the closed
 *     body shape that mirrors the operator's VPS Phase B contract:
 *     {token, expected_intent, expected_event_id, expected_evidence_hash}.
 *   * Replay verify returns HTTP 400 + outcome=replay_detected and
 *     the UI renders the precise outcome (not a generic error).
 *   * Binding-mismatch verify uses a drifted expected_event_id and
 *     returns HTTP 400 + outcome=binding_mismatch.
 *   * No localStorage / sessionStorage / cookie / pushState write
 *     happens during the diagnostic lifecycle.
 *   * console.log / warn / error never receive the token bytes.
 *   * Every fetch URL starts with /api/agent-control/approval-token/.
 *   * No fetch to merge-recommendation, mobile-inbox, merge-execution,
 *     deploy, or push endpoints.
 *   * No DOM text contains the executable verbs approve / reject /
 *     execute. (The banner contains the words "merge" and "deploy"
 *     in the phrase "no approve, merge, deploy, or execution action"
 *     — that is part of the read-only disclaimer and acceptable.
 *     Buttons must not bear those verbs.)
 *   * navigator.sendBeacon is never called.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ApprovalTokenDiagnostics } from "../routes/AgentControl/ApprovalTokenDiagnostics";

const mockFetch = vi.fn();
const mockSendBeacon = vi.fn();
const consoleLogSpy = vi.fn();
const consoleWarnSpy = vi.fn();
const consoleErrorSpy = vi.fn();
const localStorageSetSpy = vi.fn();
const sessionStorageSetSpy = vi.fn();
const cookieSetSpy = vi.fn();
const historyPushStateSpy = vi.fn();
const historyReplaceStateSpy = vi.fn();

// Sentinel token bytes used in every mint mock. We assert these
// bytes never appear in the DOM, in the URL, in console output, or
// in any storage write.
const SENTINEL_TOKEN_PREFIX = "TOKEN_SENTINEL_DO_NOT_LEAK_";
const SENTINEL_TOKEN =
  SENTINEL_TOKEN_PREFIX + "claims_b64.signature_b64_long_enough_to_grep";

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
  });
}

function statusOkBody(overrides: Record<string, unknown> = {}) {
  return {
    kind: "approval_token_status",
    schema_version: 1,
    module_version: "v3.15.16.N4b",
    status: "ok",
    is_configured: true,
    current_kid: "k1",
    step5_implementation_allowed: false,
    step5_enabled_substage: "none",
    ...overrides,
  };
}

function mintOkBody(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok",
    token: SENTINEL_TOKEN,
    kid: "k1",
    intent: "mobile_approval_dispatch",
    event_id: "evt_diagnostic_001",
    issued_at_utc: "2026-05-12T20:00:00Z",
    expires_at_utc: "2026-05-12T20:15:00Z",
    ...overrides,
  };
}

function verifyOkBody() {
  return { status: "ok", outcome: "ok", reason: "verified" };
}

function verifyReplayBody() {
  return {
    status: "rejected",
    outcome: "replay_detected",
    reason: "seen_nonce",
  };
}

function verifyBindingMismatchBody() {
  return {
    status: "rejected",
    outcome: "binding_mismatch",
    reason: "event_id",
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);

  // sendBeacon stub
  if (typeof navigator !== "undefined") {
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      value: mockSendBeacon,
    });
  }

  // console spies
  vi.spyOn(console, "log").mockImplementation((...args: unknown[]) =>
    consoleLogSpy(...args),
  );
  vi.spyOn(console, "warn").mockImplementation((...args: unknown[]) =>
    consoleWarnSpy(...args),
  );
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) =>
    consoleErrorSpy(...args),
  );

  // localStorage / sessionStorage write spies — wrap the native
  // setItem so reads still work but writes are observed.
  if (typeof window !== "undefined") {
    const localProto = Object.getPrototypeOf(window.localStorage);
    vi.spyOn(localProto, "setItem").mockImplementation(
      (...args: unknown[]) => localStorageSetSpy(...args),
    );
    const sessProto = Object.getPrototypeOf(window.sessionStorage);
    vi.spyOn(sessProto, "setItem").mockImplementation(
      (...args: unknown[]) => sessionStorageSetSpy(...args),
    );

    // cookie write spy. We can't easily spy a string accessor on
    // Document.prototype across jsdom versions, so we install a
    // configurable wrapper that records assignments.
    try {
      Object.defineProperty(document, "cookie", {
        configurable: true,
        get(): string {
          return "";
        },
        set(v: string) {
          cookieSetSpy(v);
        },
      });
    } catch {
      // Some jsdom builds make document.cookie non-configurable;
      // the no-cookie-write invariant is still verified by the
      // component never assigning to document.cookie in source.
    }

    // history pushState / replaceState spies
    vi.spyOn(window.history, "pushState").mockImplementation(
      (...args: unknown[]) => historyPushStateSpy(...args),
    );
    vi.spyOn(window.history, "replaceState").mockImplementation(
      (...args: unknown[]) => historyReplaceStateSpy(...args),
    );
  }
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  mockFetch.mockReset();
  mockSendBeacon.mockReset();
  consoleLogSpy.mockReset();
  consoleWarnSpy.mockReset();
  consoleErrorSpy.mockReset();
  localStorageSetSpy.mockReset();
  sessionStorageSetSpy.mockReset();
  cookieSetSpy.mockReset();
  historyPushStateSpy.mockReset();
  historyReplaceStateSpy.mockReset();
});

function renderUI() {
  return render(
    <MemoryRouter
      initialEntries={["/agent-control/approval-token-diagnostics"]}
    >
      <ApprovalTokenDiagnostics />
    </MemoryRouter>,
  );
}

function setFetchSequence(...responses: Array<() => Response>) {
  let i = 0;
  mockFetch.mockImplementation(async () => {
    const fn = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return fn();
  });
}

// ---------------------------------------------------------------------------
// Banner + structural elements
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — banner + structure", () => {
  it("always renders the diagnostic-only banner", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    expect(
      screen.getByTestId("approval-token-diagnostics-banner"),
    ).toHaveTextContent(
      /diagnostic only\. token verification is claim-only/i,
    );
  });

  it("renders the back link to /agent-control", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    expect(
      screen.getByTestId("approval-token-diagnostics-back-link"),
    ).toHaveAttribute("href", "/agent-control");
  });

  it("reaffirms re-authentication requirement", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    expect(
      screen.getByTestId("approval-token-diagnostics-reauth-reminder"),
    ).toHaveTextContent(/re-authentication in the pwa/i);
  });
});

// ---------------------------------------------------------------------------
// Status panel — configured / unconfigured / 401 / 503 / network
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — status panel", () => {
  it("fetches the status endpoint with same-origin credentials", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/agent-control/approval-token/status");
    expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
    expect((init as RequestInit | undefined)?.credentials).toBe("include");
  });

  it("renders configured pill + kid + step5 invariants", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-fields"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("approval-token-diagnostics-status-is-configured"),
    ).toHaveTextContent("true");
    expect(
      screen.getByTestId("approval-token-diagnostics-status-current-kid"),
    ).toHaveTextContent("k1");
    expect(
      screen.getByTestId("approval-token-diagnostics-status-step5-allowed"),
    ).toHaveTextContent("false");
    expect(
      screen.getByTestId("approval-token-diagnostics-status-step5-substage"),
    ).toHaveTextContent("none");
  });

  it("renders unconfigured state when is_configured=false", async () => {
    setFetchSequence(() =>
      jsonResponse(statusOkBody({ is_configured: false })),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-unconfigured"),
      ).toBeInTheDocument(),
    );
  });

  it("renders unconfigured state on HTTP 503 configuration_missing", async () => {
    setFetchSequence(() =>
      jsonResponse(
        { status: "error", error: "configuration_missing" },
        { status: 503 },
      ),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-unconfigured"),
      ).toBeInTheDocument(),
    );
  });

  it("renders unauthenticated state on HTTP 401", async () => {
    setFetchSequence(() =>
      jsonResponse(
        { status: "error", error: "operator_session_required" },
        { status: 401 },
      ),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId(
          "approval-token-diagnostics-status-unauthenticated",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("renders error state on network failure", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-error"),
      ).toBeInTheDocument(),
    );
  });

  it("renders error state on malformed body", async () => {
    setFetchSequence(
      () =>
        new Response("not json", {
          status: 200,
          headers: { "content-type": "text/plain" },
        }),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-error"),
      ).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// Mint — happy path + token-leakage guards
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — mint", () => {
  it("posts a bounded mint body and renders closed-schema fields", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );

    // Closed-envelope scalars rendered.
    expect(
      screen.getByTestId("approval-token-diagnostics-minted-kid"),
    ).toHaveTextContent("k1");
    expect(
      screen.getByTestId("approval-token-diagnostics-minted-intent"),
    ).toHaveTextContent("mobile_approval_dispatch");
    expect(
      screen.getByTestId("approval-token-diagnostics-minted-event-id"),
    ).toHaveTextContent("evt_diagnostic_001");
    expect(
      screen.getByTestId("approval-token-diagnostics-minted-issued-at"),
    ).toHaveTextContent("2026-05-12T20:00:00Z");
    expect(
      screen.getByTestId("approval-token-diagnostics-minted-expires-at"),
    ).toHaveTextContent("2026-05-12T20:15:00Z");

    // The mint POST went to the right URL with the right body.
    const mintCall = mockFetch.mock.calls.find(
      ([url]) => url === "/api/agent-control/approval-token/mint",
    );
    expect(mintCall).toBeDefined();
    const init = mintCall![1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      intent: "mobile_approval_dispatch",
      event_id: "evt_diagnostic_001",
      evidence_hash: "diag_evidence_001",
    });
  });

  it("never renders the raw token bytes in the DOM", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    const root = screen.getByTestId("approval-token-diagnostics-root");
    expect(root.textContent || "").not.toContain(SENTINEL_TOKEN_PREFIX);
    expect(root.innerHTML).not.toContain(SENTINEL_TOKEN_PREFIX);
  });

  it("renders mint error on HTTP 503", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () =>
        jsonResponse(
          { status: "error", error: "configuration_missing" },
          { status: 503 },
        ),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-error"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("approval-token-diagnostics-mint-error"),
    ).toHaveTextContent(/configuration_missing/);
  });
});

// ---------------------------------------------------------------------------
// Verify happy / replay / binding-mismatch (each with expected_intent)
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — verify roundtrips", () => {
  async function mintAndGetVerifyCall(
    verifyBodyFn: () => Response,
    triggerTestId: string,
  ) {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      verifyBodyFn,
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId(triggerTestId));
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-history"),
      ).toBeInTheDocument(),
    );
    return mockFetch.mock.calls.find(
      ([url]) => url === "/api/agent-control/approval-token/verify",
    );
  }

  it("verify posts {token, expected_intent, expected_event_id, expected_evidence_hash}", async () => {
    const call = await mintAndGetVerifyCall(
      () => jsonResponse(verifyOkBody()),
      "approval-token-diagnostics-verify-button",
    );
    expect(call).toBeDefined();
    const init = call![1] as RequestInit;
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      token: SENTINEL_TOKEN,
      expected_intent: "mobile_approval_dispatch",
      expected_event_id: "evt_diagnostic_001",
      expected_evidence_hash: "diag_evidence_001",
    });
  });

  it("renders outcome 'ok' on successful verify", async () => {
    await mintAndGetVerifyCall(
      () => jsonResponse(verifyOkBody()),
      "approval-token-diagnostics-verify-button",
    );
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-outcome"),
    ).toHaveTextContent("ok");
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-kind"),
    ).toHaveTextContent("verify");
  });

  it("replay posts the same body and renders replay_detected on HTTP 400", async () => {
    const call = await mintAndGetVerifyCall(
      () => jsonResponse(verifyReplayBody(), { status: 400 }),
      "approval-token-diagnostics-replay-button",
    );
    const init = call![1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body.expected_intent).toBe("mobile_approval_dispatch");
    expect(body.expected_event_id).toBe("evt_diagnostic_001");
    expect(body.expected_evidence_hash).toBe("diag_evidence_001");
    expect(body.token).toBe(SENTINEL_TOKEN);

    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-outcome"),
    ).toHaveTextContent("replay_detected");
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-kind"),
    ).toHaveTextContent("replay");
  });

  it("binding-mismatch uses drifted expected_event_id and renders binding_mismatch on HTTP 400", async () => {
    const call = await mintAndGetVerifyCall(
      () => jsonResponse(verifyBindingMismatchBody(), { status: 400 }),
      "approval-token-diagnostics-binding-mismatch-button",
    );
    const init = call![1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body.expected_intent).toBe("mobile_approval_dispatch");
    // The drifted event_id (sanitised: '_drift' is appended and then
    // bounded). The original id was 'evt_diagnostic_001' (18 chars),
    // appending '_drift' yields 24 chars, well under the 64 cap.
    expect(body.expected_event_id).toBe("evt_diagnostic_001_drift");
    expect(body.expected_event_id).not.toBe("evt_diagnostic_001");

    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-outcome"),
    ).toHaveTextContent("binding_mismatch");
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-kind"),
    ).toHaveTextContent("binding_mismatch");
  });

  it("renders multiple verify entries when verify + replay are both run", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      () => jsonResponse(verifyOkBody()),
      () => jsonResponse(verifyReplayBody(), { status: 400 }),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-verify-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-0"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-replay-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-1"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-0-outcome"),
    ).toHaveTextContent("ok");
    expect(
      screen.getByTestId("approval-token-diagnostics-verify-entry-1-outcome"),
    ).toHaveTextContent("replay_detected");
  });
});

// ---------------------------------------------------------------------------
// Persistence + leakage invariants
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — persistence + leakage guards", () => {
  it("never writes the token to localStorage / sessionStorage / cookie / pushState", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      () => jsonResponse(verifyOkBody()),
      () => jsonResponse(verifyReplayBody(), { status: 400 }),
      () => jsonResponse(verifyBindingMismatchBody(), { status: 400 }),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    // Each verify click disables the button until the fetch
    // resolves, so we must await the previous entry to appear
    // before firing the next click.
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-verify-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-0"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-replay-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-1"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId(
        "approval-token-diagnostics-binding-mismatch-button",
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-2"),
      ).toBeInTheDocument(),
    );

    // No persistence write happened anywhere.
    expect(localStorageSetSpy).not.toHaveBeenCalled();
    expect(sessionStorageSetSpy).not.toHaveBeenCalled();
    expect(cookieSetSpy).not.toHaveBeenCalled();
    expect(historyPushStateSpy).not.toHaveBeenCalled();
    expect(historyReplaceStateSpy).not.toHaveBeenCalled();
    expect(mockSendBeacon).not.toHaveBeenCalled();

    // Even if some legitimate storage write happened in the future,
    // the token bytes must not appear in any spy's call arguments.
    function assertNoTokenIn(spy: ReturnType<typeof vi.fn>) {
      for (const call of spy.mock.calls) {
        for (const arg of call) {
          expect(String(arg)).not.toContain(SENTINEL_TOKEN_PREFIX);
        }
      }
    }
    assertNoTokenIn(localStorageSetSpy);
    assertNoTokenIn(sessionStorageSetSpy);
    assertNoTokenIn(cookieSetSpy);
    assertNoTokenIn(historyPushStateSpy);
    assertNoTokenIn(historyReplaceStateSpy);
    assertNoTokenIn(mockSendBeacon);
  });

  it("never logs the token to console.log / warn / error", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      () => jsonResponse(verifyOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-verify-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-0"),
      ).toBeInTheDocument(),
    );
    function noTokenLogged(spy: ReturnType<typeof vi.fn>) {
      for (const call of spy.mock.calls) {
        for (const arg of call) {
          expect(String(arg)).not.toContain(SENTINEL_TOKEN_PREFIX);
        }
      }
    }
    noTokenLogged(consoleLogSpy);
    noTokenLogged(consoleWarnSpy);
    noTokenLogged(consoleErrorSpy);
  });

  it("discard button removes the minted-section from the DOM", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-discard-button"),
    );
    expect(
      screen.queryByTestId("approval-token-diagnostics-minted-section"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Endpoint isolation
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — endpoint isolation", () => {
  it("only fetches /api/agent-control/approval-token/*", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      () => jsonResponse(verifyOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-verify-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-0"),
      ).toBeInTheDocument(),
    );
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      expect(url).toMatch(/^\/api\/agent-control\/approval-token\//);
    }
  });

  it("never fetches merge-recommendation / mobile-inbox / merge-execution / deploy / push endpoints", async () => {
    setFetchSequence(
      () => jsonResponse(statusOkBody()),
      () => jsonResponse(mintOkBody()),
      () => jsonResponse(verifyOkBody()),
    );
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-mint-button"),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-mint-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-minted-section"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("approval-token-diagnostics-verify-button"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-verify-entry-0"),
      ).toBeInTheDocument(),
    );
    const forbiddenSubstrings = [
      "/merge-recommendation/",
      "/mobile-inbox/",
      "/merge-execution/",
      "/deploy",
      "/api/push/",
    ];
    for (const call of mockFetch.mock.calls) {
      const url = String(call[0]);
      for (const sub of forbiddenSubstrings) {
        expect(url).not.toContain(sub);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Action-surface invariants (no approve / reject / execute buttons)
// ---------------------------------------------------------------------------

describe("ApprovalTokenDiagnostics — no action-execution surface", () => {
  it("no button is labelled with an executable decision verb", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-fields"),
      ).toBeInTheDocument(),
    );
    const buttons = screen.queryAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const b of buttons) {
      const label = (b.textContent || "").toLowerCase();
      const aria = (b.getAttribute("aria-label") || "").toLowerCase();
      const txt = label + " " + aria;
      // The diagnostic surface has: mint / verify / replay /
      // binding-mismatch / discard / refresh. None of these are
      // executable decision verbs.
      expect(txt).not.toMatch(/\bapprove\b/);
      expect(txt).not.toMatch(/\breject\b/);
      expect(txt).not.toMatch(/\bexecute\b/);
    }
  });

  it("no anchor link redirects to a merge-execution / deploy / approve path", async () => {
    setFetchSequence(() => jsonResponse(statusOkBody()));
    renderUI();
    await waitFor(() =>
      expect(
        screen.getByTestId("approval-token-diagnostics-status-fields"),
      ).toBeInTheDocument(),
    );
    const anchors = screen.queryAllByRole("link");
    for (const a of anchors) {
      const href = a.getAttribute("href") || "";
      expect(href).not.toContain("/merge-execution/");
      expect(href).not.toContain("/deploy");
      expect(href).not.toMatch(/\bapprove\b/);
      expect(href).not.toMatch(/\breject\b/);
    }
  });
});
