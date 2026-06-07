"""Artifact writer for fail-closed fundamental readiness sidecars."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.data_readiness.factor_field_coverage import build_factor_field_coverage
from research.data_readiness.fundamental_readiness import build_fundamental_readiness


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/data_readiness")
WRITE_PREFIX: Final[str] = "artifacts/data_readiness/"
READINESS_NAME: Final[str] = "fundamental_readiness_latest.v1.json"
COVERAGE_NAME: Final[str] = "factor_field_coverage_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"fundamental_readiness_manifest: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    readiness_path = base / READINESS_NAME
    coverage_path = base / COVERAGE_NAME
    for path in (readiness_path, coverage_path):
        _validate_write_target(path)
    _write_json(readiness_path, build_fundamental_readiness())
    _write_json(coverage_path, build_factor_field_coverage())
    return {
        "fundamental_readiness": readiness_path.relative_to(repo_root).as_posix(),
        "factor_field_coverage": coverage_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.data_readiness.fundamental_readiness_manifest",
        description="Write deterministic fail-closed fundamental readiness artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = {
        "fundamental_readiness": build_fundamental_readiness(),
        "factor_field_coverage": build_factor_field_coverage(),
    }
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
