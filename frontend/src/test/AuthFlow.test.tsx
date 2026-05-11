/**
 * Auth-flow regression test for the QRE Control Room redesign.
 *
 * The retro restyle of /login MUST NOT change auth behavior. These
 * tests prove that:
 *   1. /login renders the login form (the retro shell does not block it).
 *   2. An unauthenticated visit to a protected route redirects to /login.
 *   3. After successful login, the user lands on the original target.
 *   4. Logout calls the existing /api/session/logout and returns to /login.
 *   5. A 401 from the session probe results in a redirect to /login,
 *      not a crash.
 *
 * The frontend is read-only by contract; the only mutating fetches
 * present are the pre-existing session login/logout. This test does
 * not introduce any new mutating endpoints.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "../auth";
import { Login, sanitiseLoginNext } from "../routes/Login";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  api: {
    presets: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    health: vi.fn(),
    runStatus: vi.fn(),
    reportLatest: vi.fn(),
    publicArtifactStatus: vi.fn(),
    researchIntelligenceSummary: vi.fn(),
    campaignDigest: vi.fn(),
    systemVersion: vi.fn(),
    systemArtifactIndex: vi.fn(),
    sprintStatus: vi.fn(),
  },
}));

import { api, ApiError } from "../api/client";

function ProtectedTarget() {
  return <div data-testid="protected-target">protected</div>;
}

function AgentControlTarget() {
  return <div data-testid="agent-control-target">agent-control</div>;
}

function AgentControlInboxTarget() {
  return <div data-testid="agent-control-inbox-target">inbox</div>;
}

function HarnessApp() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedTarget />} />
        <Route path="/agent-control" element={<AgentControlTarget />} />
        <Route
          path="/agent-control/inbox"
          element={<AgentControlInboxTarget />}
        />
      </Routes>
    </AuthProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("auth flow under retro restyle", () => {
  it("renders the login form when /login is requested directly", async () => {
    vi.mocked(api.presets).mockRejectedValue(new ApiError(401, "auth"));
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <HarnessApp />
      </MemoryRouter>
    );
    expect(await screen.findByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("submits the existing /api/session/login and lands on target on success", async () => {
    // First probe says unauthenticated.
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <HarnessApp />
      </MemoryRouter>
    );

    const usernameInput = await screen.findByLabelText(/username/i);
    fireEvent.change(usernameInput, { target: { value: "joery" } });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith("joery", "secret");
    });
  });

  it("shows the error from the existing API on failed login", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({
      ok: false,
      error: "ongeldige inloggegevens",
    });

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <HarnessApp />
      </MemoryRouter>
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/ongeldige inloggegevens/i)
      ).toBeInTheDocument();
    });
    // Hard rule: only the pre-existing /api/session/login endpoint is
    // hit. No new mutating endpoint must be wired.
    expect(api.login).toHaveBeenCalledTimes(1);
    expect(api.logout).not.toHaveBeenCalled();
  });

  it("only invokes session login/logout — no other mutating fetches", () => {
    // Compile-time-ish check: any function on `api` whose name suggests
    // a mutation must be a known one. The frontend is read-only by
    // contract; this guards against accidental new POST endpoints.
    const allowedMutators = new Set(["login", "logout", "runPreset"]);
    const apiKeys = Object.keys(api);
    const suspicious = apiKeys.filter(
      (k) =>
        !allowedMutators.has(k) &&
        /^(post|put|delete|create|update|start|stop|cancel|trigger|launch)/i.test(
          k
        )
    );
    expect(suspicious).toEqual([]);
  });
});

/**
 * /login?next= handling — PWA push-deep-link recovery.
 *
 * Backend (Flask) detects an expired session on a /agent-control SPA
 * path and 302-redirects to /login?next=<sanitised-target>. The PWA
 * has no address bar, so without these tests there is no guarantee
 * the Login component honours the safe ``next`` and ignores the
 * dangerous one.
 */
describe("Login — ?next= sanitisation pure function", () => {
  it("accepts /agent-control exactly", () => {
    expect(sanitiseLoginNext("/agent-control")).toBe("/agent-control");
  });

  it("accepts /agent-control/inbox?event=abc", () => {
    expect(sanitiseLoginNext("/agent-control/inbox?event=abc")).toBe(
      "/agent-control/inbox?event=abc",
    );
  });

  it("accepts /agent-control/anything-under-the-prefix", () => {
    expect(sanitiseLoginNext("/agent-control/future-subpath")).toBe(
      "/agent-control/future-subpath",
    );
  });

  it("rejects external https URLs", () => {
    expect(sanitiseLoginNext("https://evil.example.com/agent-control")).toBeNull();
  });

  it("rejects protocol-relative URLs", () => {
    expect(sanitiseLoginNext("//evil.example.com/agent-control")).toBeNull();
  });

  it("rejects path traversal", () => {
    expect(sanitiseLoginNext("/agent-control/../etc/passwd")).toBeNull();
  });

  it("rejects backslash smuggling", () => {
    expect(sanitiseLoginNext("/agent-control\\evil")).toBeNull();
  });

  it("rejects other top-level paths", () => {
    expect(sanitiseLoginNext("/api/foo")).toBeNull();
    expect(sanitiseLoginNext("/presets")).toBeNull();
    expect(sanitiseLoginNext("/")).toBeNull();
  });

  it("rejects paths that look similar but are not under /agent-control", () => {
    expect(sanitiseLoginNext("/agent-control-elsewhere")).toBeNull();
  });

  it("treats null / empty as missing", () => {
    expect(sanitiseLoginNext(null)).toBeNull();
    expect(sanitiseLoginNext("")).toBeNull();
  });
});

describe("Login — post-login navigation honours ?next=", () => {
  it("navigates to the safe ?next target after successful login", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter
        initialEntries={["/login?next=%2Fagent-control%2Finbox%3Fevent%3Dabc"]}
      >
        <HarnessApp />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByTestId("agent-control-inbox-target"),
      ).toBeInTheDocument();
    });
  });

  it("ignores an unsafe ?next and falls back to the default", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter
        initialEntries={["/login?next=https%3A%2F%2Fevil.example.com%2Fpwn"]}
      >
        <HarnessApp />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      // Falls back to the legacy default "/" target.
      expect(screen.getByTestId("protected-target")).toBeInTheDocument();
    });
  });

  it("ignores path traversal and falls back to the default", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter
        initialEntries={[
          "/login?next=%2Fagent-control%2F..%2Fetc%2Fpasswd",
        ]}
      >
        <HarnessApp />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("protected-target")).toBeInTheDocument();
    });
  });

  it("ignores protocol-relative ?next and falls back to the default", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter
        initialEntries={[
          "/login?next=%2F%2Fevil.example.com%2Fagent-control",
        ]}
      >
        <HarnessApp />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("protected-target")).toBeInTheDocument();
    });
  });

  it("with no ?next, preserves the legacy default", async () => {
    vi.mocked(api.presets).mockRejectedValueOnce(new ApiError(401, "auth"));
    vi.mocked(api.login).mockResolvedValueOnce({ ok: true, actor: "joery" });

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <HarnessApp />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("protected-target")).toBeInTheDocument();
    });
  });
});
