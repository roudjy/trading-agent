import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { Presets } from "../Presets";
import type { PresetCard } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    presets: vi.fn(),
    runPreset: vi.fn(),
  },
}));

import { api } from "../../api/client";

function enabledPreset(): PresetCard {
  return {
    name: "trend_equities_4h_baseline",
    hypothesis: "Large-cap trend episodes on multi-bar timeframes.",
    universe: ["NVDA", "AMD"],
    timeframe: "4h",
    bundle: ["sma_crossover"],
    optional_bundle: [],
    screening_mode: "strict",
    cost_mode: "realistic",
    status: "stable",
    enabled: true,
    diagnostic_only: false,
    excluded_from_daily_scheduler: false,
    excluded_from_candidate_promotion: false,
    regime_filter: null,
    regime_modes: [],
    backlog_reason: null,
    preset_class: "baseline",
    rationale: "Trend capture rationale.",
    expected_behavior: "Positive OOS Sharpe on >=1 asset.",
    falsification: ["Negative DSR over 3 runs"],
    enablement_criteria: [],
    decision: {
      is_product_decision: false,
      kind: null,
      summary: "",
      requires_enablement: false,
    },
  };
}

function pairsPreset(): PresetCard {
  return {
    name: "pairs_equities_daily_baseline",
    hypothesis: "Equity pairs via z-score spread mean reversion.",
    universe: ["NVDA/AMD"],
    timeframe: "1d",
    bundle: ["pairs_zscore"],
    optional_bundle: [],
    screening_mode: "strict",
    cost_mode: "realistic",
    status: "planned",
    enabled: false,
    diagnostic_only: false,
    excluded_from_daily_scheduler: false,
    excluded_from_candidate_promotion: false,
    regime_filter: null,
    regime_modes: [],
    backlog_reason: "v3.11 equity-pairs ADR required.",
    preset_class: "experimental",
    rationale: "Orthogonal to trend hypothesis.",
    expected_behavior: "Spread-signal statistically independent.",
    falsification: ["Non-stationary spread"],
    enablement_criteria: [
      "v3.11 equity-pairs ADR",
      "Fitted-feature abstractie uitbreiden",
    ],
    decision: {
      is_product_decision: true,
      kind: "disabled_planned",
      summary: "Bewuste product-/roadmapbeslissing.",
      requires_enablement: true,
    },
  };
}

describe("Presets page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a decision block for a disabled/planned preset", async () => {
    vi.mocked(api.presets).mockResolvedValue({
      presets: [pairsPreset()],
    });
    render(<Presets />);
    const block = await screen.findByTestId(
      "decision-block-pairs_equities_daily_baseline"
    );
    expect(block).toBeInTheDocument();
    expect(block).toHaveAttribute("data-decision-kind", "disabled_planned");
    expect(block).toHaveTextContent("Bewuste product-/roadmapbeslissing");
    expect(block).toHaveTextContent("v3.11 equity-pairs ADR required");
    expect(block).toHaveTextContent("v3.11 equity-pairs ADR");
    expect(block).toHaveTextContent("Fitted-feature abstractie");
  });

  it("does NOT render a decision block for an enabled stable preset", async () => {
    vi.mocked(api.presets).mockResolvedValue({
      presets: [enabledPreset()],
    });
    render(<Presets />);
    await waitFor(() => {
      expect(api.presets).toHaveBeenCalled();
    });
    // The enabled baseline preset has decision.is_product_decision=false
    // → the dedicated decision-block must NOT appear.
    expect(
      screen.queryByTestId("decision-block-trend_equities_4h_baseline")
    ).not.toBeInTheDocument();
  });

  it("renders both presets side-by-side without cross-contamination", async () => {
    vi.mocked(api.presets).mockResolvedValue({
      presets: [enabledPreset(), pairsPreset()],
    });
    render(<Presets />);

    await screen.findByTestId(
      "decision-block-pairs_equities_daily_baseline"
    );
    expect(
      screen.queryByTestId("decision-block-trend_equities_4h_baseline")
    ).not.toBeInTheDocument();
  });
});
