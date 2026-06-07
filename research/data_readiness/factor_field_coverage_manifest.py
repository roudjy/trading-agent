"""Artifact writer for deterministic factor field coverage sidecars."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.data_readiness.factor_field_coverage import build_factor_field_coverage


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/data_readiness")
WRITE_PREFIX: Final[str] = "artifacts/data_readiness/"
OUTPUT_NAME: Final[str] = "factor_field_coverage_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"factor_field_coverage_manifest: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    output_path = base / OUTPUT_NAME
    _validate_write_target(output_path)
    _write_json(output_path, build_factor_field_coverage())
    return {"factor_field_coverage": output_path.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.data_readiness.factor_field_coverage_manifest",
        description="Write deterministic factor field coverage artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = {"factor_field_coverage": build_factor_field_coverage()}
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
