"""Artifact writer for controlled factor evaluation readiness."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.equity_factors.controlled_factor_evaluation import (
    build_controlled_factor_evaluation_readiness,
)


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/equity_factors")
WRITE_PREFIX: Final[str] = "artifacts/equity_factors/"
LATEST_NAME: Final[str] = "controlled_factor_evaluation_readiness_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"controlled_factor_evaluation_manifest: refusing write outside allowlist: {path!r}"
        )


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    _validate_write_target(latest)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(
        json.dumps(build_controlled_factor_evaluation_readiness(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_latest, latest)
    return {"latest": latest.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.equity_factors.controlled_factor_evaluation_manifest",
        description="Write deterministic controlled factor evaluation readiness artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = build_controlled_factor_evaluation_readiness()
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
