from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common

REPORT_KIND: Final[str] = "qre_automated_generation_closeout"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-019m-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_automated_generation_closeout")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_automated_generation_closeout.md")
DEFAULT_CLOSEOUT_PATH: Final[Path] = Path("generated_research/reports/automated_generation_closeout.v1.json")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("generated_research/registry/generated_strategy_registry.v1.json")
DEFAULT_PRESETS_PATH: Final[Path] = Path("generated_research/presets/generated_research_presets.v1.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("generated_research/lineage/generated_campaign_lineage.v1.json")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_automated_generation_closeout/",
    "docs/governance/qre_automated_generation_closeout.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    closeout_path: Path | None = None,
    registry_path: Path | None = None,
    presets_path: Path | None = None,
    lineage_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    closeout = common.read_json(root / (closeout_path or DEFAULT_CLOSEOUT_PATH)) or {}
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    presets = common.read_json(root / (presets_path or DEFAULT_PRESETS_PATH)) or {}
    lineage = common.read_json(root / (lineage_path or DEFAULT_LINEAGE_PATH)) or {}

    closeout_rows = common.rows(closeout, "rows")
    registry_rows = common.rows(registry, "rows")
    preset_rows = common.rows(presets, "rows")
    lineage_rows = common.rows(lineage, "rows")

    registry_by_hypothesis = common.index_by(registry_rows, "source_hypothesis_id")
    presets_by_hypothesis = common.index_by(preset_rows, "source_hypothesis_id")
    lineage_by_hypothesis = common.index_by(lineage_rows, "source_hypothesis_id")

    rows_out: list[dict[str, Any]] = []
    for row in sorted(closeout_rows, key=lambda item: common.text(item.get("source_hypothesis_id"))):
        source_hypothesis_id = common.text(row.get("source_hypothesis_id"))
        registry_row = registry_by_hypothesis.get(source_hypothesis_id, {})
        preset_row = presets_by_hypothesis.get(source_hypothesis_id, {})
        lineage_row = lineage_by_hypothesis.get(source_hypothesis_id, {})
        rows_out.append(
            {
                "source_hypothesis_id": source_hypothesis_id,
                "final_generation_outcome": common.text(row.get("final_generation_outcome")),
                "generated_strategy_id": common.text(row.get("generated_strategy_id")) or common.text(registry_row.get("generated_strategy_id")),
                "generated_registration_id": common.text(registry_row.get("generated_registration_id")),
                "preset_id": common.text(preset_row.get("preset_id")),
                "preset_name": common.text(preset_row.get("preset_name")),
                "lineage_id": common.text(lineage_row.get("generated_lineage_id")),
                "campaign_readiness_state": common.text(lineage_row.get("campaign_readiness_state")) or common.text(row.get("campaign_readiness_state")),
                "blockers": common.normalize_list(row.get("blockers")),
                "reason": common.text(row.get("reason")),
                "provenance_refs": common.dedupe(
                    common.normalize_list(registry_row.get("provenance"))
                    + common.normalize_list(preset_row.get("provenance_refs"))
                    + common.normalize_list(lineage_row.get("provenance_refs"))
                    + [
                        common.rel(root / (closeout_path or DEFAULT_CLOSEOUT_PATH), root),
                        common.rel(root / (registry_path or DEFAULT_REGISTRY_PATH), root),
                        common.rel(root / (presets_path or DEFAULT_PRESETS_PATH), root),
                        common.rel(root / (lineage_path or DEFAULT_LINEAGE_PATH), root),
                    ]
                ),
            }
        )
    status_counts: dict[str, int] = {}
    for row in rows_out:
        outcome = row["final_generation_outcome"]
        status_counts[outcome] = status_counts.get(outcome, 0) + 1
    snapshot_identity = f"qag_{common.stable_digest(rows_out)[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "automated_generation_identity": snapshot_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "registered_count": status_counts.get("RESEARCH_REGISTERED_AUTOMATED", 0),
            "status_counts": dict(sorted(status_counts.items())),
            "exact_next_action": (
                "continue_generated_lineage_and_evidence_remediation"
                if status_counts.get("RESEARCH_REGISTERED_AUTOMATED", 0) == 0
                else "rebuild_campaign_portfolio_from_generated_outputs"
            ),
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE Automated Generation Closeout",
        "",
        f"- automated_generation_identity: `{common.text(snapshot.get('automated_generation_identity'))}`",
        f"- thesis_count: `{snapshot.get('summary', {}).get('thesis_count', 0)}`",
        f"- registered_count: `{snapshot.get('summary', {}).get('registered_count', 0)}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('final_generation_outcome'))}` -> `{common.text(row.get('campaign_readiness_state')) or common.text(row.get('reason'))}`"
        )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_019m.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_automated_generation_closeout")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
