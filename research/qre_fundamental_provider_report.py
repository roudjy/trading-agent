"""Read-only operator report for the fundamental provider candidate registry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.external_intelligence.fundamental_provider_registry import (
    build_fundamental_provider_registry,
)


REPO_ROOT: Final[Path] = Path(".")
OUTPUT_DIR: Final[Path] = Path("artifacts/external_intelligence")
MD_NAME: Final[str] = "fundamental_provider_operator_report_latest.md"
WRITE_PREFIX: Final[str] = "artifacts/external_intelligence/"
DISCLAIMER: Final[str] = (
    "Research-only provider registry. No data has been fetched, no API integration was activated, "
    "and no provider is trusted or active by default."
)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_fundamental_provider_report: refusing write outside allowlist: {path!r}")


def _write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def collect_snapshot() -> dict[str, object]:
    registry = build_fundamental_provider_registry()
    rows = registry["rows"]
    by_status: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_status.setdefault(str(row["source_status"]), []).append(row)
    for items in by_status.values():
        items.sort(key=lambda item: (int(item["implementation_priority"]), str(item["provider_id"])))
    return {
        "report_kind": "qre_fundamental_provider_report",
        "schema_version": "1.0",
        "disclaimer": DISCLAIMER,
        "summary": registry["summary"],
        "providers_by_status": {
            key: [
                {
                    "provider_id": row["provider_id"],
                    "provider_name": row["provider_name"],
                    "provider_category": row["provider_category"],
                    "implementation_priority": row["implementation_priority"],
                    "risk_level": row["risk_level"],
                    "license_terms_status": row["license_terms_status"],
                }
                for row in items
            ]
            for key, items in sorted(by_status.items())
        },
        "highest_priority_candidates": registry["summary"]["highest_priority_candidates"],
        "all_provider_ids": [str(row["provider_id"]) for row in rows],
        "safety_invariants": registry["safety_invariants"],
    }


def render_markdown(snapshot: dict[str, object]) -> str:
    summary = snapshot["summary"]
    lines = [
        "# QRE Fundamental Provider Candidate Registry",
        "",
        DISCLAIMER,
        "",
        "## Status Counts",
        f"- total providers: {summary['total_providers']}",
        f"- candidate: {summary['candidate_count']}",
        f"- manual_research_only: {summary['manual_research_only_count']}",
        f"- staging: {summary['staging_count']}",
        f"- quality_gated: {summary['quality_gated_count']}",
        f"- active_read_only: {summary['active_read_only_count']}",
        f"- deprecated: {summary['deprecated_count']}",
        f"- blocked: {summary['blocked_count']}",
        "",
        "## Highest Priority Candidates",
    ]
    for row in snapshot["highest_priority_candidates"]:
        lines.append(
            f"- {row['provider_id']}: priority {row['implementation_priority']} [{row['source_status']}] - {row['reason']}"
        )
    lines.extend(["", "## Providers By Status"])
    for status, rows in snapshot["providers_by_status"].items():
        lines.append(f"### {status}")
        for row in rows:
            lines.append(
                f"- {row['provider_id']}: {row['provider_name']} ({row['provider_category']}, license={row['license_terms_status']}, risk={row['risk_level']})"
            )
    lines.extend(
        [
            "",
            "## Safety",
            "- No buy/sell recommendations",
            "- No trade signals",
            "- No strategy registration",
            "- No paper/shadow/live activation",
            "- No broker/risk/execution authority",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(*, repo_root: Path = REPO_ROOT, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    md_path = base / MD_NAME
    _validate_write_target(md_path)
    _write_text(md_path, render_markdown(collect_snapshot()))
    return {"markdown": md_path.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_fundamental_provider_report",
        description="Write read-only fundamental provider registry operator report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    snapshot = collect_snapshot()
    payload = {"report": snapshot, "markdown": render_markdown(snapshot)}
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
