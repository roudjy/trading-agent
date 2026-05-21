"""Behavior hypothesis objects derived from the existing catalog.

The derivation is intentionally narrow: only current
``active_discovery`` rows become proposal inputs. Planned, disabled,
and diagnostic rows remain visible in the source catalog but do not
seed Hypothesis Discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from research.hypothesis_discovery.behavior_catalog import get_behavior
from research.strategy_hypothesis_catalog import (
    StrategyHypothesis,
    list_active_discovery,
)


SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"


@dataclass(frozen=True)
class BehaviorHypothesis:
    hypothesis_id: str
    behavior_family: str
    strategy_family: str
    strategy_mapping_ref: str
    status: str
    expected_failure_modes: tuple[str, ...]
    parameter_count: int
    default_grid_size: int

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "hypothesis_id": self.hypothesis_id,
            "behavior_family": self.behavior_family,
            "strategy_family": self.strategy_family,
            "strategy_mapping_ref": self.strategy_mapping_ref,
            "status": self.status,
            "expected_failure_modes": list(self.expected_failure_modes),
            "parameter_count": self.parameter_count,
            "default_grid_size": self.default_grid_size,
        }


def _from_catalog_row(row: StrategyHypothesis) -> BehaviorHypothesis:
    behavior = get_behavior(row.strategy_family)
    return BehaviorHypothesis(
        hypothesis_id=row.hypothesis_id,
        behavior_family=behavior.behavior_family,
        strategy_family=row.strategy_family,
        strategy_mapping_ref=f"strategy_hypothesis_catalog:{row.hypothesis_id}",
        status=row.status,
        expected_failure_modes=tuple(row.expected_failure_modes),
        parameter_count=len(row.parameter_schema),
        default_grid_size=len(row.default_parameter_grid),
    )


def build_behavior_hypotheses(
    *, catalog: tuple[StrategyHypothesis, ...] | None = None
) -> list[BehaviorHypothesis]:
    rows = (
        [row for row in catalog if row.status == "active_discovery"]
        if catalog is not None
        else list_active_discovery()
    )
    hypotheses = [_from_catalog_row(row) for row in rows]
    hypotheses.sort(key=lambda h: h.hypothesis_id)
    return hypotheses


def behavior_hypotheses_payload(
    *, catalog: tuple[StrategyHypothesis, ...] | None = None
) -> dict[str, object]:
    hypotheses = build_behavior_hypotheses(catalog=catalog)
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "hypotheses": [h.to_payload() for h in hypotheses],
    }
