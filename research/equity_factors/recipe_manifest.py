"""Artifact writer for research-only equity factor recipes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.equity_factors.recipe_catalog import build_equity_factor_recipe_catalog


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/equity_factors")
WRITE_PREFIX: Final[str] = "artifacts/equity_factors/"
RECIPES_NAME: Final[str] = "equity_factor_recipes_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"recipe_manifest: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    recipes_path = base / RECIPES_NAME
    _validate_write_target(recipes_path)
    _write_json(recipes_path, build_equity_factor_recipe_catalog())
    return {"recipes": recipes_path.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.equity_factors.recipe_manifest",
        description="Write deterministic read-only equity factor recipe artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = {"recipes": build_equity_factor_recipe_catalog()}
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
