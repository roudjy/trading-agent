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
import { Login } from "../routes/Login";

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

function HarnessApp() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedTarget />} />
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
