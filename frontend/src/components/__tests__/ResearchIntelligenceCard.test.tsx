import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ResearchIntelligenceCard } from "../ResearchIntelligenceCard";
import type { ResearchIntelligenceSummary } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    researchIntelligenceSummary: vi.fn(),
  },
}));

import { api } from "../../api/client";

function emptySummary(): ResearchIntelligenceSummary {
  return {
    schema_version: "1.0",
    enforcement_state: "advisory_only",
    viability: {
      status: "insufficient_data",
      reason_codes: ["fewer_than_minimum_campaigns"],
      human_summary: "No data yet.",
    },
    metrics: {},
    information_gain: {
      score: 0,
      bucket: "none",
      is_meaningful_campaign: false,
      reasons: [],
    },
    advisory_decision_count: 0,
    dead_zone_count: 0,
    ledger_summary: {},
  };
}

function promisingSummary(): ResearchIntelligenceSummary {
  return {
    schema_version: "1.0",
    enforcement_state: "advisory_only",
    viability: {
      status: "promising",
      reason_codes: ["candidate_or_paper_ready_present"],
      human_summary: "ok",
    },
    metrics: {
      campaign_count: 25,
      meaningful_campaign_rate: 0.6,
      candidate_count: 1,
      paper_ready_count: 0,
    },
    information_gain: {
      score: 0.9,
      bucket: "high",
      is_meaningful_campaign: true,
      reasons: [],
    },
    advisory_decision_count: 2,
    dead_zone_count: 1,
    ledger_summary: { campaign_count: 25 },
    spawn_proposals: {
      proposal_mode: "normal",
      proposed_count: 4,
      suppressed_zone_count: 1,
      human_review_required: false,
      top_proposals: [
        {
          preset_name: "trend_pullback_crypto_1h",
          proposal_type: "confirmation_campaign",
          spawn_reason: "confirmation_from_exploratory_pass",
          priority_tier: "HIGH",
        },
      ],
    },
  };
}

function diagnosticSummary(): ResearchIntelligenceSummary {
  return {
    schema_version: "1.0",
    enforcement_state: "advisory_only",
    viability: {
      status: "stop_or_pivot",
      reason_codes: ["large_window_no_meaningful_no_candidate"],
      human_summary: "stop_or_pivot",
    },
    metrics: { campaign_count: 100, candidate_count: 0 },
    information_gain: { score: 0.0, bucket: "none" },
    advisory_decision_count: 0,
    dead_zone_count: 3,
    ledger_summary: {},
    spawn_proposals: {
      proposal_mode: "diagnostic_only",
      proposed_count: 2,
      suppressed_zone_count: 3,
      human_review_required: true,
      top_proposals: [
        {
          preset_name: "explore_unknown_zone",
          proposal_type: "exploration_reservation_unknown_zone",
          spawn_reason: "exploration_reservation_unknown_zone",
          priority_tier: "LOW",
        },
      ],
    },
  };
}

describe("ResearchIntelligenceCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a loading state before the API resolves", () => {
    vi.mocked(api.researchIntelligenceSummary).mockReturnValue(
      new Promise(() => {})
    );
    render(<ResearchIntelligenceCard />);
    expect(
      screen.getByTestId("research-intelligence-card-loading")
    ).toBeInTheDocument();
  });

  it("renders an error state when the API rejects", async () => {
    vi.mocked(api.researchIntelligenceSummary).mockRejectedValue(
      new Error("401")
    );
    render(<ResearchIntelligenceCard />);
    await waitFor(() => {
      expect(
        screen.getByTestId("research-intelligence-card-error")
      ).toBeInTheDocument();
    });
  });

  it("renders insufficient_data verdict for an empty backend", async () => {
    vi.mocked(api.researchIntelligenceSummary).mockResolvedValue(
      emptySummary()
    );
    render(<ResearchIntelligenceCard />);
    const card = await screen.findByTestId("research-intelligence-card");
    expect(card).toHaveTextContent("insufficient_data");
    expect(card).toHaveTextContent("advisory");
    expect(card).toHaveTextContent("No data yet.");
  });

  it("renders metrics + information gain bucket when promising", async () => {
    vi.mocked(api.researchIntelligenceSummary).mockResolvedValue(
      promisingSummary()
    );
    render(<ResearchIntelligenceCard />);
    const card = await screen.findByTestId("research-intelligence-card");
    expect(card).toHaveTextContent("promising");
    expect(card).toHaveTextContent("60.0%");
    expect(card).toHaveTextContent("high");
    expect(card).toHaveTextContent("0.90");
    expect(card).toHaveTextContent("dead zones");
  });

  it("renders v3.15.12 spawn proposal block (normal mode)", async () => {
    vi.mocked(api.researchIntelligenceSummary).mockResolvedValue(
      promisingSummary()
    );
    render(<ResearchIntelligenceCard />);
    const card = await screen.findByTestId("research-intelligence-card");
    expect(card).toHaveTextContent("proposal mode");
    expect(card).toHaveTextContent("normal");
    expect(card).toHaveTextContent("spawn proposals");
    expect(card).toHaveTextContent("HIGH");
    expect(card).toHaveTextContent("confirmation_campaign");
  });

  it("renders v3.15.12 diagnostic_only mode and human-review flag", async () => {
    vi.mocked(api.researchIntelligenceSummary).mockResolvedValue(
      diagnosticSummary()
    );
    render(<ResearchIntelligenceCard />);
    const card = await screen.findByTestId("research-intelligence-card");
    expect(card).toHaveTextContent("diagnostic_only");
    expect(card).toHaveTextContent("review required");
    expect(card).toHaveTextContent("stop_or_pivot");
    expect(card).toHaveTextContent("LOW");
  });
});
