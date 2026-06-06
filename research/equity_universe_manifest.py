"""Artifact writer for the read-only equity universe foundation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.equity_universe_catalog import (
    build_equity_universe_catalog,
    build_equity_universe_summary,
)
from research.equity_universe_identity import build_instrument_identity_report
from research.equity_universe_quality import build_equity_universe_quality


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/universe")
DEFAULT_IDENTITY_OUTPUT_DIR: Final[Path] = Path("artifacts/identity")
WRITE_PREFIX: Final[str] = "artifacts/universe/"
IDENTITY_WRITE_PREFIX: Final[str] = "artifacts/identity/"
CATALOG_NAME: Final[str] = "equity_universe_catalog_latest.v1.json"
SUMMARY_NAME: Final[str] = "equity_universe_summary_latest.v1.json"
QUALITY_NAME: Final[str] = "equity_universe_quality_latest.v1.json"
IDENTITY_NAME: Final[str] = "instrument_identity_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if WRITE_PREFIX not in normalized and IDENTITY_WRITE_PREFIX not in normalized:
        raise ValueError(f"equity_universe_manifest: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    identity_output_dir: Path = DEFAULT_IDENTITY_OUTPUT_DIR,
) -> dict[str, str]:
    base = repo_root / output_dir
    identity_base = repo_root / identity_output_dir
    base.mkdir(parents=True, exist_ok=True)
    identity_base.mkdir(parents=True, exist_ok=True)
    catalog_path = base / CATALOG_NAME
    summary_path = base / SUMMARY_NAME
    quality_path = base / QUALITY_NAME
    identity_path = identity_base / IDENTITY_NAME
    for path in (catalog_path, summary_path, quality_path, identity_path):
        _validate_write_target(path)
    _write_json(catalog_path, build_equity_universe_catalog())
    _write_json(summary_path, build_equity_universe_summary())
    _write_json(quality_path, build_equity_universe_quality())
    _write_json(identity_path, build_instrument_identity_report())
    return {
        "catalog": catalog_path.relative_to(repo_root).as_posix(),
        "summary": summary_path.relative_to(repo_root).as_posix(),
        "quality": quality_path.relative_to(repo_root).as_posix(),
        "identity": identity_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.equity_universe_manifest",
        description="Write deterministic read-only equity-universe artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = {
        "catalog": build_equity_universe_catalog(),
        "summary": build_equity_universe_summary(),
        "quality": build_equity_universe_quality(),
        "identity": build_instrument_identity_report(),
    }
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
