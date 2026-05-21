"""Minimal v3.15.19 Hypothesis Discovery package.

The package is proposal-only. It builds deterministic discovery seeds
from the existing hypothesis catalog and preset universe; it does not
create candidates, strategies, campaigns, orders, or execution state.
"""

from research.hypothesis_discovery.behavior_catalog import (
    BEHAVIOR_FAMILIES,
    BehaviorDescriptor,
    get_behavior,
    list_behaviors,
)
from research.hypothesis_discovery.behavior_hypotheses import (
    BehaviorHypothesis,
    build_behavior_hypotheses,
)
from research.hypothesis_discovery.campaign_seed_proposer import (
    collect_snapshot,
    write_outputs,
)
from research.hypothesis_discovery.opportunity_scoring import (
    ACTIVE_DIAGNOSTICS,
    OpportunityScore,
    score_opportunity,
)
from research.hypothesis_discovery.preset_feasibility import (
    PresetFeasibility,
    evaluate_preset_feasibility,
)

__all__ = [
    "ACTIVE_DIAGNOSTICS",
    "BEHAVIOR_FAMILIES",
    "BehaviorDescriptor",
    "BehaviorHypothesis",
    "OpportunityScore",
    "PresetFeasibility",
    "build_behavior_hypotheses",
    "collect_snapshot",
    "evaluate_preset_feasibility",
    "get_behavior",
    "list_behaviors",
    "score_opportunity",
    "write_outputs",
]
