from __future__ import annotations

from pathlib import Path
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GENERATED_RESEARCH_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "primitives"
GENERATED_PRIMITIVE_SPECS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "specs"
GENERATED_PRIMITIVE_MANIFESTS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "manifests"
GENERATED_PRIMITIVE_REGISTRY_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "registry"
GENERATED_PRIMITIVE_VALIDATION_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "validation"
GENERATED_PRIMITIVE_REPORTS_DIR: Final[Path] = GENERATED_RESEARCH_ROOT / "reports"

GENERATED_PRIMITIVE_REGISTRY_PATH: Final[Path] = (
    GENERATED_PRIMITIVE_REGISTRY_DIR / "generated_primitive_registry.v1.json"
)
GENERATED_PRIMITIVE_CLOSEOUT_PATH: Final[Path] = (
    GENERATED_PRIMITIVE_REPORTS_DIR / "automated_primitive_expansion_closeout.v1.json"
)
GENERATED_PRIMITIVE_PACKAGE_DIR: Final[Path] = (
    REPO_ROOT / "agent" / "backtesting" / "generated_primitives"
)
GENERATED_PRIMITIVE_TEST_DIR: Final[Path] = (
    REPO_ROOT / "tests" / "generated_primitives"
)

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "generated_research/primitives/specs/",
    "generated_research/primitives/manifests/",
    "generated_research/primitives/registry/",
    "generated_research/primitives/validation/",
    "generated_research/primitives/reports/",
    "agent/backtesting/generated_primitives/",
    "tests/generated_primitives/",
)


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def validate_write_target(path: Path) -> None:
    relative = repo_relative(path)
    if not any(relative.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"ADE-QRE-021 refuses write outside generated primitive surfaces: {relative}"
        )


__all__ = [
    "GENERATED_PRIMITIVE_CLOSEOUT_PATH",
    "GENERATED_PRIMITIVE_MANIFESTS_DIR",
    "GENERATED_PRIMITIVE_PACKAGE_DIR",
    "GENERATED_PRIMITIVE_REGISTRY_DIR",
    "GENERATED_PRIMITIVE_REGISTRY_PATH",
    "GENERATED_PRIMITIVE_REPORTS_DIR",
    "GENERATED_PRIMITIVE_SPECS_DIR",
    "GENERATED_PRIMITIVE_TEST_DIR",
    "GENERATED_PRIMITIVE_VALIDATION_DIR",
    "GENERATED_RESEARCH_ROOT",
    "REPO_ROOT",
    "repo_relative",
    "validate_write_target",
]
