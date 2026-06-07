"""Artifact writer for read-only equity-factor hypothesis seeds."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.hypothesis_discovery.equity_factor_hypothesis_adapter import (
    build_equity_factor_hypothesis_seeds,
)


OUTPUT_DIR: Final[Path] = Path("artifacts/hypothesis_discovery")
LATEST_NAME: Final[str] = "equity_factor_hypothesis_seeds_latest.v1.json"
ARTIFACT_PATH: Final[str] = (OUTPUT_DIR / LATEST_NAME).as_posix()


def _validate_write_target(path: Path) -> None:
    if "artifacts/hypothesis_discovery/" not in path.as_posix():
        raise ValueError(f"equity_factor_seed_manifest: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    output_dir = repo_root / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    latest = output_dir / LATEST_NAME
    _validate_write_target(latest)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    return {"latest": latest.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.hypothesis_discovery.equity_factor_seed_manifest",
        description="Write read-only equity-factor hypothesis seed artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_equity_factor_hypothesis_seeds()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
