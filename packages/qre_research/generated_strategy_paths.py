from __future__ import annotations

from pathlib import Path
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GENERATED_RESEARCH_ROOT: Final[Path] = Path("generated_research")
GENERATED_SPECS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "specs"
GENERATED_MANIFESTS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "manifests"
GENERATED_REGISTRY_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "registry"
GENERATED_PRESETS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "presets"
GENERATED_VALIDATION_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "validation"
GENERATED_LINEAGE_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "lineage"
GENERATED_REPORTS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "reports"
GENERATED_STRATEGY_BLUEPRINTS_DIR: Final[Path] = (
    GENERATED_RESEARCH_ROOT / "strategies" / "blueprints"
)
GENERATED_STRATEGY_CANDIDATES_DIR: Final[Path] = (
    GENERATED_RESEARCH_ROOT / "strategies" / "candidates"
)
GENERATED_STRATEGY_VALIDATION_DIR: Final[Path] = (
    GENERATED_RESEARCH_ROOT / "strategies" / "validation"
)
GENERATED_STRATEGY_PROPOSALS_DIR: Final[Path] = (
    GENERATED_RESEARCH_ROOT / "strategies" / "proposals"
)
GENERATED_STRATEGY_READINESS_DIR: Final[Path] = (
    GENERATED_RESEARCH_ROOT / "strategies" / "readiness"
)

GENERATED_REGISTRY_PATH: Final[Path] = (
    GENERATED_REGISTRY_DIR / "generated_strategy_registry.v1.json"
)
GENERATED_PRESETS_PATH: Final[Path] = (
    GENERATED_PRESETS_DIR / "generated_research_presets.v1.json"
)
GENERATED_NULL_CONTROLS_PATH: Final[Path] = (
    GENERATED_LINEAGE_DIR / "generated_null_controls.v1.json"
)
GENERATED_LINEAGE_PATH: Final[Path] = (
    GENERATED_LINEAGE_DIR / "generated_campaign_lineage.v1.json"
)
GENERATED_CLOSEOUT_PATH: Final[Path] = (
    GENERATED_REPORTS_DIR / "automated_generation_closeout.v1.json"
)

GENERATED_STRATEGY_PACKAGE_DIR: Final[Path] = (
    Path("agent") / "backtesting" / "generated_strategies"
)
GENERATED_STRATEGY_TEST_DIR: Final[Path] = Path("tests") / "generated_strategies"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "generated_research/specs/",
    "generated_research/manifests/",
    "generated_research/registry/",
    "generated_research/presets/",
    "generated_research/validation/",
    "generated_research/lineage/",
    "generated_research/reports/",
    "generated_research/alpha_discovery/",
    "agent/backtesting/generated_strategies/",
    "tests/generated_strategies/",
    "generated_research/primitives/specs/",
    "generated_research/primitives/manifests/",
    "generated_research/primitives/registry/",
    "generated_research/primitives/validation/",
    "generated_research/primitives/reports/",
    "generated_research/readiness/gaps/",
    "generated_research/readiness/identity_candidates/",
    "generated_research/readiness/identity_decisions/",
    "generated_research/readiness/data_bindings/",
    "generated_research/readiness/data_capacity/",
    "generated_research/readiness/snapshots/",
    "generated_research/readiness/window_capacity/",
    "generated_research/readiness/window_ledger/",
    "generated_research/readiness/presets/",
    "generated_research/readiness/null_controls/",
    "generated_research/readiness/campaigns/",
    "generated_research/readiness/reports/",
    "generated_research/campaign_execution/manifest_integrity/",
    "generated_research/campaign_execution/stages/",
    "generated_research/campaign_execution/evidence/",
    "generated_research/campaign_execution/ledgers/",
    "generated_research/campaign_execution/reports/",
    "generated_research/orchestration/",
    "generated_research/strategies/blueprints/",
    "generated_research/strategies/candidates/",
    "generated_research/strategies/validation/",
    "generated_research/strategies/proposals/",
    "generated_research/strategies/readiness/",
    "agent/backtesting/generated_primitives/",
    "tests/generated_primitives/",
)


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def validate_write_target(path: Path) -> None:
    relative = repo_relative(path)
    if not any(relative.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"ADE-QRE-019 refuses write outside generated-research surface: {relative}")


__all__ = [
    "GENERATED_CLOSEOUT_PATH",
    "GENERATED_LINEAGE_DIR",
    "GENERATED_LINEAGE_PATH",
    "GENERATED_MANIFESTS_DIR",
    "GENERATED_NULL_CONTROLS_PATH",
    "GENERATED_PRESETS_DIR",
    "GENERATED_PRESETS_PATH",
    "GENERATED_REGISTRY_DIR",
    "GENERATED_REGISTRY_PATH",
    "GENERATED_REPORTS_DIR",
    "GENERATED_RESEARCH_ROOT",
    "GENERATED_SPECS_DIR",
    "GENERATED_STRATEGY_PACKAGE_DIR",
    "GENERATED_STRATEGY_BLUEPRINTS_DIR",
    "GENERATED_STRATEGY_CANDIDATES_DIR",
    "GENERATED_STRATEGY_PROPOSALS_DIR",
    "GENERATED_STRATEGY_READINESS_DIR",
    "GENERATED_STRATEGY_TEST_DIR",
    "GENERATED_STRATEGY_VALIDATION_DIR",
    "GENERATED_VALIDATION_DIR",
    "REPO_ROOT",
    "repo_relative",
    "validate_write_target",
]
