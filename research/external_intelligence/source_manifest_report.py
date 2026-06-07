"""Operator-readable report for source manifests and license policy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


OUTPUT_DIR: Final[Path] = Path("artifacts/external_intelligence")
OUTPUT_NAME: Final[str] = "source_manifest_operator_report_latest.md"
WRITE_PREFIX: Final[str] = "artifacts/external_intelligence/"


def collect_snapshot() -> dict[str, object]:
    registry = build_source_manifest_registry()
    return {
        "report_kind": "source_manifest_operator_report",
        "schema_version": registry["schema_version"],
        "summary": registry["summary"],
        "rows": [
            {
                "source_id": row["source_id"],
                "provider_id": row["provider_id"],
                "source_type": row["source_type"],
                "source_category": row["source_category"],
                "manifest_status": row["manifest_status"],
                "license_policy_status": registry["policy_by_source"][str(row["source_id"])]["license_policy_status"],
                "manifest_block_reasons": row["manifest_block_reasons"],
            }
            for row in registry["rows"]
        ],
        "safety_invariants": registry["safety_invariants"],
    }


def render_markdown(snapshot: dict[str, object]) -> str:
    summary = snapshot["summary"]
    lines = [
        "# QRE Source Manifest Schema and License Policy",
        "",
        "- No data fetched",
        "- No provider activated",
        "- No recipe, hypothesis seed, or controlled evaluation readiness is unlocked unless all gates pass",
        "",
        "## Manifest Summary",
        f"- total manifests: {summary['total_manifests']}",
    ]
    for key, value in summary["manifest_status_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## License Policy Summary"])
    for key, value in summary["license_policy_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Source Categories",
        ]
    )
    for key, value in summary["source_category_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Key Constraints"])
    lines.append(f"- quality_gated eligible providers: {', '.join(summary['quality_gated_eligible_providers']) or 'none'}")
    lines.append(f"- active_read_only eligible providers: {', '.join(summary['active_read_only_eligible_providers']) or 'none'}")
    lines.append(f"- providers blocked by license policy: {', '.join(summary['providers_blocked_by_license_policy']) or 'none'}")
    lines.append(f"- providers blocked by policy gaps: {', '.join(summary['providers_blocked_by_policy_gaps']) or 'none'}")
    lines.extend(["", "## Source Rows"])
    for row in snapshot["rows"]:
        lines.append(
            f"- {row['source_id']}: status={row['manifest_status']}, license_policy={row['license_policy_status']}, "
            f"type={row['source_type']}, category={row['source_category']}, blockers={', '.join(row['manifest_block_reasons']) or 'none'}"
        )
    return "\n".join(lines) + "\n"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"source_manifest_report: refusing write outside allowlist: {path!r}")


def _write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    path = base / OUTPUT_NAME
    _validate_write_target(path)
    _write_text(path, render_markdown(collect_snapshot()))
    return {"markdown": path.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.external_intelligence.source_manifest_report",
        description="Write operator-readable source manifest report.",
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
