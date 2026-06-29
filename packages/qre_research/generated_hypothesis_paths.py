from __future__ import annotations

from pathlib import Path
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GENERATED_RESEARCH_ROOT: Final[Path] = REPO_ROOT / "generated_research"
GENERATED_HYPOTHESIS_ROOT: Final[Path] = GENERATED_RESEARCH_ROOT / "hypotheses"

GENERATED_HYPOTHESIS_OPPORTUNITIES_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "opportunities"
)
GENERATED_HYPOTHESIS_OBSERVATIONS_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "observations"
)
GENERATED_HYPOTHESIS_MECHANISMS_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "mechanisms"
)
GENERATED_HYPOTHESIS_CANDIDATES_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "candidates"
)
GENERATED_HYPOTHESIS_REGISTRY_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "registry"
)
GENERATED_HYPOTHESIS_REJECTIONS_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "rejections"
)
GENERATED_HYPOTHESIS_PRIORITIES_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "priorities"
)
GENERATED_HYPOTHESIS_FEEDBACK_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "feedback"
)
GENERATED_HYPOTHESIS_REPORTS_DIR: Final[Path] = (
    GENERATED_HYPOTHESIS_ROOT / "reports"
)

EVIDENCE_SNAPSHOT_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REPORTS_DIR / "evidence_snapshot.v1.json"
)
OPPORTUNITIES_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_OPPORTUNITIES_DIR / "generated_opportunities.v1.json"
)
OBSERVATIONS_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_OBSERVATIONS_DIR / "generated_observations.v1.json"
)
MECHANISMS_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_MECHANISMS_DIR / "generated_mechanisms.v1.json"
)
CANDIDATES_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_CANDIDATES_DIR / "generated_candidates.v1.json"
)
GENERATED_THESIS_REGISTRY_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REGISTRY_DIR / "generated_thesis_registry.v1.json"
)
RESOLVED_THESIS_CATALOG_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REGISTRY_DIR / "resolved_thesis_catalog.v1.json"
)
REJECTIONS_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REJECTIONS_DIR / "generated_thesis_rejections.v1.json"
)
PRIORITIES_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_PRIORITIES_DIR / "generated_thesis_priorities.v1.json"
)
PRIMITIVE_EXTENSION_REQUESTS_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_PRIORITIES_DIR / "primitive_extension_requests.v1.json"
)
FEEDBACK_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_FEEDBACK_DIR / "generated_hypothesis_feedback.v1.json"
)
INTEGRATED_CLOSEOUT_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REPORTS_DIR / "automated_hypothesis_generation_closeout.v1.json"
)
INTEGRATED_CLOSEOUT_MD_PATH: Final[Path] = (
    GENERATED_HYPOTHESIS_REPORTS_DIR / "automated_hypothesis_generation_closeout.v1.md"
)

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "generated_research/hypotheses/opportunities/",
    "generated_research/hypotheses/observations/",
    "generated_research/hypotheses/mechanisms/",
    "generated_research/hypotheses/candidates/",
    "generated_research/hypotheses/registry/",
    "generated_research/hypotheses/rejections/",
    "generated_research/hypotheses/priorities/",
    "generated_research/hypotheses/feedback/",
    "generated_research/hypotheses/reports/",
)


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def validate_write_target(path: Path) -> None:
    relative = repo_relative(path)
    if not any(relative.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(
            "ADE-QRE-020 refuses write outside generated hypothesis surfaces: "
            f"{relative}"
        )


__all__ = [
    "CANDIDATES_PATH",
    "EVIDENCE_SNAPSHOT_PATH",
    "FEEDBACK_PATH",
    "GENERATED_HYPOTHESIS_CANDIDATES_DIR",
    "GENERATED_HYPOTHESIS_FEEDBACK_DIR",
    "GENERATED_HYPOTHESIS_MECHANISMS_DIR",
    "GENERATED_HYPOTHESIS_OBSERVATIONS_DIR",
    "GENERATED_HYPOTHESIS_OPPORTUNITIES_DIR",
    "GENERATED_HYPOTHESIS_REGISTRY_DIR",
    "GENERATED_HYPOTHESIS_REJECTIONS_DIR",
    "GENERATED_HYPOTHESIS_REPORTS_DIR",
    "GENERATED_HYPOTHESIS_ROOT",
    "GENERATED_HYPOTHESIS_PRIORITIES_DIR",
    "GENERATED_RESEARCH_ROOT",
    "GENERATED_THESIS_REGISTRY_PATH",
    "INTEGRATED_CLOSEOUT_MD_PATH",
    "INTEGRATED_CLOSEOUT_PATH",
    "MECHANISMS_PATH",
    "OBSERVATIONS_PATH",
    "OPPORTUNITIES_PATH",
    "PRIMITIVE_EXTENSION_REQUESTS_PATH",
    "PRIORITIES_PATH",
    "REJECTIONS_PATH",
    "REPO_ROOT",
    "RESOLVED_THESIS_CATALOG_PATH",
    "WRITE_PREFIXES",
    "repo_relative",
    "validate_write_target",
]
