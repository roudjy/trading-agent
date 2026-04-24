import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { StaleArtifactBanner } from "../StaleArtifactBanner";
import type { PublicArtifactStatus } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    publicArtifactStatus: vi.fn(),
  },
}));

import { api } from "../../api/client";

function absentPayload(): PublicArtifactStatus {
  return {
    state: "absent",
    schema_version: null,
    public_artifact_status_version: null,
    artifact_modified_at_utc: null,
    last_attempted_run: null,
    last_public_artifact_write: null,
    last_public_write_age_seconds: null,
    public_artifacts_stale: null,
    stale_reason: null,
    stale_since_utc: null,
  };
}

function freshPayload(): PublicArtifactStatus {
  return {
    state: "valid",
    schema_version: "1.0",
    public_artifact_status_version: "v0.1",
    artifact_modified_at_utc: "2026-04-24T12:00:00+00:00",
    generated_at_utc: "2026-04-24T12:00:00+00:00",
    last_attempted_run: {
      run_id: "run-ok-1",
      attempted_at_utc: "2026-04-24T12:00:00+00:00",
      preset: "trend_equities_4h_baseline",
      outcome: "success",
      failure_stage: null,
    },
    last_public_artifact_write: {
      run_id: "run-ok-1",
      written_at_utc: "2026-04-24T12:00:00+00:00",
      preset: "trend_equities_4h_baseline",
    },
    last_public_write_age_seconds: 0,
    public_artifacts_stale: false,
    stale_reason: null,
    stale_since_utc: null,
  };
}

function stalePayload(): PublicArtifactStatus {
  return {
    state: "valid",
    schema_version: "1.0",
    public_artifact_status_version: "v0.1",
    artifact_modified_at_utc: "2026-04-24T12:00:00+00:00",
    generated_at_utc: "2026-04-24T12:00:00+00:00",
    last_attempted_run: {
      run_id: "run-degen-1",
      attempted_at_utc: "2026-04-24T12:00:00+00:00",
      preset: "trend_equities_4h_baseline",
      outcome: "degenerate",
      failure_stage: "screening_no_survivors",
    },
    last_public_artifact_write: {
      run_id: "run-ok-1",
      written_at_utc: "2026-04-23T12:00:00+00:00",
      preset: "trend_equities_4h_baseline",
    },
    last_public_write_age_seconds: 86400,
    public_artifacts_stale: true,
    stale_reason: "degenerate_run_no_public_write",
    stale_since_utc: "2026-04-24T12:00:00+00:00",
  };
}

describe("StaleArtifactBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when the status is absent (explicit unknown)", async () => {
    vi.mocked(api.publicArtifactStatus).mockResolvedValue(absentPayload());
    const { container } = render(<StaleArtifactBanner />);
    await waitFor(() => {
      expect(api.publicArtifactStatus).toHaveBeenCalled();
    });
    expect(
      screen.queryByTestId("stale-artifact-banner")
    ).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it("does not render when public artifacts are fresh", async () => {
    vi.mocked(api.publicArtifactStatus).mockResolvedValue(freshPayload());
    render(<StaleArtifactBanner />);
    await waitFor(() => {
      expect(api.publicArtifactStatus).toHaveBeenCalled();
    });
    expect(
      screen.queryByTestId("stale-artifact-banner")
    ).not.toBeInTheDocument();
  });

  it("renders with run_id, failure stage and reason when stale", async () => {
    vi.mocked(api.publicArtifactStatus).mockResolvedValue(stalePayload());
    render(<StaleArtifactBanner />);
    const banner = await screen.findByTestId("stale-artifact-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(
      "De getoonde publieke research-resultaten zijn niet van de laatste run."
    );
    expect(banner).toHaveTextContent("degenerate_run_no_public_write");
    expect(banner).toHaveTextContent("run-degen-1");
    expect(banner).toHaveTextContent("screening_no_survivors");
    expect(banner).toHaveTextContent("run-ok-1");
  });

  it("does not render when the API rejects", async () => {
    vi.mocked(api.publicArtifactStatus).mockRejectedValue(
      new Error("401")
    );
    render(<StaleArtifactBanner />);
    await waitFor(() => {
      expect(api.publicArtifactStatus).toHaveBeenCalled();
    });
    expect(
      screen.queryByTestId("stale-artifact-banner")
    ).not.toBeInTheDocument();
  });
});
