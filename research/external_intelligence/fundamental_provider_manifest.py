"""Artifact writer for the research-only fundamental provider candidate registry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.external_intelligence.fundamental_provider_registry import (
    build_fundamental_provider_registry,
)


DEFAULT_OUTPUT_DIR: Final[Path] = Path("artifacts/external_intelligence")
WRITE_PREFIX: Final[str] = "artifacts/external_intelligence/"
CANDIDATES_NAME: Final[str] = "fundamental_provider_candidates_latest.v1.json"
SUMMARY_NAME: Final[str] = "fundamental_provider_summary_latest.v1.json"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"fundamental_provider_manifest: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def build_fundamental_provider_summary(snapshot: dict[str, object]) -> dict[str, object]:
    summary = snapshot["summary"]
    return {
        "schema_version": snapshot["schema_version"],
        "report_kind": "fundamental_provider_summary",
        "summary": {
            "total_providers": summary["total_providers"],
            "candidate": summary["candidate_count"],
            "manual_research_only": summary["manual_research_only_count"],
            "staging": summary["staging_count"],
            "quality_gated": summary["quality_gated_count"],
            "active_read_only": summary["active_read_only_count"],
            "deprecated": summary["deprecated_count"],
            "blocked": summary["blocked_count"],
            "highest_priority_candidates": summary["highest_priority_candidates"],
            "operator_summary": summary["operator_summary"],
        },
        "safety_invariants": snapshot["safety_invariants"],
    }


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    candidates_path = base / CANDIDATES_NAME
    summary_path = base / SUMMARY_NAME
    for path in (candidates_path, summary_path):
        _validate_write_target(path)
    snapshot = build_fundamental_provider_registry()
    _write_json(candidates_path, snapshot)
    _write_json(summary_path, build_fundamental_provider_summary(snapshot))
    return {
        "candidates": candidates_path.relative_to(repo_root).as_posix(),
        "summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.external_intelligence.fundamental_provider_manifest",
        description="Write deterministic research-only fundamental provider registry artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    snapshot = build_fundamental_provider_registry()
    payload = {
        "registry": snapshot,
        "summary": build_fundamental_provider_summary(snapshot),
    }
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
