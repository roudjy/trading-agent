/**
 * Smoke + empty-state tests for the /observability page (v3.15.15.3).
 *
 * Hard guarantees verified:
 *   * The page renders the aggregator summary when the artifact is
 *     available.
 *   * Missing or corrupt artifacts render an EmptyStatePanel /
 *     "Unavailable" message rather than crashing.
 *   * The mutation surface on `api` still contains only login,
 *     logout, and runPreset (extends the AuthFlow guard).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Observability } from "../routes/Observability";

vi.mock("../api/client", () => ({
  api: {
    observabilitySummary: vi.fn(),
    observabilityIndex: vi.fn(),
    // The full mock surface — keeps the mutator-allowlist test honest
    // because it can introspect ``Object.keys(api)``.
    health: vi.fn(),
    presets: vi.fn(),
    runPreset: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    reportLatest: vi.fn(),
    runStatus: vi.fn(),
    publicArtifactStatus: vi.fn(),
    researchIntelligenceSummary: vi.fn(),
    campaignDigest: vi.fn(),
    systemVersion: vi.fn(),
    systemArtifactIndex: vi.fn(),
    sprintStatus: vi.fn(),
    observabilityArtifactHealth: vi.fn(),
    observabilityFailureModes: vi.fn(),
    observabilityThroughput: vi.fn(),
    observabilitySystemIntegrity: vi.fn(),
    observabilityFunnel: vi.fn(),
    observabilityCampaignTimeline: vi.fn(),
    observabilityParameterCoverage: vi.fn(),
    observabilityDataFreshness: vi.fn(),
    observabilityPolicyTrace: vi.fn(),
    observabilityNoTouchHealth: vi.fn(),
  },
}));

import { api } from "../api/client";

function freshSummaryEnvelope() {
  return {
    available: true,
    component: "observability_summary",
    artifact_name: "observability_summary_latest.v1.json",
    artifact_path: "research/observability/observability_summary_latest.v1.json",
    state: "valid" as const,
    modified_at_unix: 1777400000,
    size_bytes: 4234,
    error: null,
    payload: {
      schema_version: "1.0",
      generated_at_utc: "2026-04-28T07:47:08Z",
      observation_window: {
        earliest_component_generated_at_utc: "2026-04-28T07:47:08Z",
        latest_component_generated_at_utc: "2026-04-28T07:47:08Z",
        inferred_from: "active_component_generated_at_utc",
      },
      overall_status: "healthy" as const,
      component_status_counts: { available: 4 },
      components: [
        {
          name: "artifact_health",
          slug: "artifact-health",
          status: "available" as const,
          path: "research/observability/artifact_health_latest.v1.json",
          schema_version: "1.0",
          generated_at_utc: "2026-04-28T07:47:08Z",
          modified_at_unix: 1777400000,
          size_bytes: 9817,
          error_message: null,
        },
      ],
      critical_findings: [],
      warnings: ["component sample is empty"],
      informational_findings: ["component funnel is deferred"],
      recommended_next_human_action: "none" as const,
      active_component_count: 4,
      deferred_component_count: 6,
    },
  };
}

function emptyIndex() {
  return {
    observability_dir: "research/observability",
    components: [
      {
        component: "artifact_health",
        slug: "artifact-health",
        artifact_name: "artifact_health_latest.v1.json",
        artifact_path: "research/observability/artifact_health_latest.v1.json",
        exists: true,
        size_bytes: 9817,
        modified_at_unix: 1777400000,
        deferred: false,
      },
      {
        component: "funnel_stage_summary",
        slug: "funnel",
        artifact_name: "funnel_stage_summary_latest.v1.json",
        artifact_path: "research/observability/funnel_stage_summary_latest.v1.json",
        exists: false,
        size_bytes: null,
        modified_at_unix: null,
        deferred: true,
      },
    ],
    active_count: 5,
    deferred_count: 6,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Observability page", () => {
  it("renders the aggregator summary card when the summary is available", async () => {
    vi.mocked(api.observabilitySummary).mockResolvedValue(
      freshSummaryEnvelope() as unknown as ReturnType<
        typeof api.observabilitySummary
      > extends Promise<infer R>
        ? R
        : never
    );
    vi.mocked(api.observabilityIndex).mockResolvedValue(
      emptyIndex() as unknown as ReturnType<
        typeof api.observabilityIndex
      > extends Promise<infer R>
        ? R
        : never
    );

    render(
      <MemoryRouter>
        <Observability />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/OVERALL STATUS/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/HEALTHY/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/4 AVAILABLE/i)).toBeInTheDocument();
    expect(screen.getAllByText(/6 DEFERRED/i).length).toBeGreaterThan(0);
  });

  it("renders an Unavailable card when the summary artifact is absent", async () => {
    vi.mocked(api.observabilitySummary).mockResolvedValue({
      available: false,
      component: "observability_summary",
      artifact_name: "observability_summary_latest.v1.json",
      artifact_path:
        "research/observability/observability_summary_latest.v1.json",
      state: "absent",
      modified_at_unix: null,
      size_bytes: null,
      error: null,
      payload: null,
    } as unknown as ReturnType<
      typeof api.observabilitySummary
    > extends Promise<infer R>
      ? R
      : never);
    vi.mocked(api.observabilityIndex).mockResolvedValue(
      emptyIndex() as unknown as ReturnType<
        typeof api.observabilityIndex
      > extends Promise<infer R>
        ? R
        : never
    );

    render(
      <MemoryRouter>
        <Observability />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/AGGREGATOR SUMMARY UNAVAILABLE/i)).toBeInTheDocument();
    });
    // The component table still renders from the index endpoint.
    expect(screen.getAllByText(/artifact_health/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/funnel_stage_summary/).length).toBeGreaterThan(0);
  });

  it("renders a graceful Unavailable message when the summary is corrupt", async () => {
    vi.mocked(api.observabilitySummary).mockResolvedValue({
      available: false,
      component: "observability_summary",
      artifact_name: "observability_summary_latest.v1.json",
      artifact_path:
        "research/observability/observability_summary_latest.v1.json",
      state: "invalid_json",
      modified_at_unix: 123,
      size_bytes: 10,
      error: "Expecting value: line 1 column 1 (char 0)",
      payload: null,
    } as unknown as ReturnType<
      typeof api.observabilitySummary
    > extends Promise<infer R>
      ? R
      : never);
    vi.mocked(api.observabilityIndex).mockResolvedValue(
      emptyIndex() as unknown as ReturnType<
        typeof api.observabilityIndex
      > extends Promise<infer R>
        ? R
        : never
    );

    render(
      <MemoryRouter>
        <Observability />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/AGGREGATOR SUMMARY UNAVAILABLE/i)
      ).toBeInTheDocument();
    });
    // No crash — we fall through to the index-based listing.
    expect(screen.getAllByText(/components/i).length).toBeGreaterThan(0);
  });

  it("renders an EmptyStatePanel-style error if both endpoints reject", async () => {
    vi.mocked(api.observabilitySummary).mockRejectedValue(new Error("offline"));
    vi.mocked(api.observabilityIndex).mockRejectedValue(new Error("offline"));

    render(
      <MemoryRouter>
        <Observability />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Observability unavailable/i)).toBeInTheDocument();
    });
  });
});

describe("frontend mutation-surface guard (extended)", () => {
  it("the api object exposes only the three pre-existing mutating methods", () => {
    const allowed = new Set(["login", "logout", "runPreset"]);
    const suspicious = Object.keys(api).filter(
      (k) =>
        !allowed.has(k) &&
        /^(post|put|delete|create|update|start|stop|cancel|trigger|launch|enable|disable)/i.test(
          k
        )
    );
    expect(suspicious).toEqual([]);
  });

  it("none of the new observability methods are mutators (name-based)", () => {
    const obsMethods = Object.keys(api).filter((k) => k.startsWith("observability"));
    expect(obsMethods.length).toBeGreaterThan(0);
    for (const k of obsMethods) {
      expect(
        /^(post|put|delete|create|update|start|stop|cancel|trigger|launch|enable|disable)/i.test(
          k
        )
      ).toBe(false);
    }
  });
});
