from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Final

from reporting import qre_ade018_common as common
from reporting import qre_blocked_thesis_lineage_census as census

REPORT_KIND: Final[str] = "qre_identity_ambiguity_resolution"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018c-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_identity_ambiguity_resolution")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_identity_ambiguity_resolution.md")
DEFAULT_CENSUS_PATH: Final[Path] = Path("logs/qre_blocked_thesis_lineage_census/latest.json")
DEFAULT_IDENTITY_PATH: Final[Path] = Path("logs/qre_source_identity_authority_normalization/latest.json")
VALID_RESOLUTION_STATES: Final[tuple[str, ...]] = (
    "RESOLVED",
    "RESOLVED_WITH_LIMITATIONS",
    "AMBIGUOUS",
    "CONFLICTING",
    "MISSING",
    "BLOCKED",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_identity_ambiguity_resolution/",
    "docs/governance/qre_identity_ambiguity_resolution.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    census_path: Path | None = None,
    identity_path: Path | None = None,
) -> dict[str, object]:
    root = repo_root or Path.cwd()
    census_payload = common.read_json(root / (census_path or DEFAULT_CENSUS_PATH))
    if census_payload is None:
        census_payload = census.collect_snapshot(repo_root=root)
    identity = common.read_json(root / (identity_path or DEFAULT_IDENTITY_PATH)) or {}
    identity_rows = common.rows(identity, "rows")
    rows_out: list[dict[str, object]] = []
    for row in common.rows(census_payload, "rows"):
        behavior_family = common.text(row.get("behavior_family"))
        matching = sorted(
            [
                item
                for item in identity_rows
                if common.text(item.get("behavior_id")) in common.behavior_keys(behavior_family)
            ],
            key=lambda item: (
                common.text(item.get("authority_status")).startswith("blocked_") is False,
                common.text(item.get("symbol")),
                common.text(item.get("provider_symbol")),
            ),
        )
        representative = matching[0] if matching else {}
        resolution_status = common.text(representative.get("resolution_status"))
        authority_status = common.text(representative.get("authority_status"))
        if not matching:
            resolution_state = "MISSING"
            ambiguity_reason = "no_authoritative_identity_rows_for_behavior_family"
            next_action = "resolve_identity_ambiguity_for_thesis"
        elif resolution_status == "AMBIGUOUS_BLOCKED":
            resolution_state = "AMBIGUOUS"
            ambiguity_reason = authority_status or "authority_ambiguity_visible"
            next_action = "resolve_identity_ambiguity_for_thesis"
        elif authority_status.startswith("blocked_"):
            resolution_state = "BLOCKED"
            ambiguity_reason = authority_status
            next_action = "resolve_identity_ambiguity_for_thesis"
        elif resolution_status == "VERIFIED":
            resolution_state = "RESOLVED_WITH_LIMITATIONS" if common.text(representative.get("instrument_identity_status")) == "missing" else "RESOLVED"
            ambiguity_reason = "instrument_identity_row_missing" if resolution_state == "RESOLVED_WITH_LIMITATIONS" else "none"
            next_action = "preserve_identity_resolution"
        else:
            resolution_state = "CONFLICTING"
            ambiguity_reason = resolution_status or "unknown_resolution_state"
            next_action = "resolve_identity_ambiguity_for_thesis"
        if resolution_state not in VALID_RESOLUTION_STATES:
            raise ValueError(f"invalid resolution state: {resolution_state}")
        rows_out.append(
            {
                "stable_id": f"qria_{common.stable_digest({'hypothesis': row.get('source_hypothesis_id')})[:16]}",
                "source_hypothesis_id": common.text(row.get("source_hypothesis_id")),
                "behavior_family": behavior_family,
                "strategy_identity": common.text(row.get("strategy_implementation_identity")),
                "preset_identity": common.text(row.get("preset_identity")),
                "source_identity": common.text(representative.get("provider_symbol")),
                "instrument_identity": common.text(representative.get("symbol")),
                "dataset_identity": common.text(representative.get("source_quality_status")),
                "snapshot_identity": common.text(row.get("snapshot_identity")),
                "campaign_identity": common.text(row.get("campaign_identity")),
                "resolution_state": resolution_state,
                "authority_status": authority_status,
                "ambiguity_reason": ambiguity_reason,
                "next_action": next_action,
                "provenance_refs": common.dedupe(
                    common.normalize_list(row.get("provenance_refs"))
                    + common.normalize_list(representative.get("provenance"))
                    + [common.rel(root / DEFAULT_IDENTITY_PATH, root)]
                ),
            }
        )
    rows_out.sort(key=lambda item: common.text(item.get("source_hypothesis_id")))
    snapshot_core = {"rows": rows_out}
    resolution_identity = f"qria_{common.stable_digest(snapshot_core)[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "identity_resolution_identity": resolution_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "resolved_count": sum(1 for row in rows_out if row["resolution_state"] in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}),
            "blocked_count": sum(1 for row in rows_out if row["resolution_state"] == "BLOCKED"),
            "ambiguous_count": sum(1 for row in rows_out if row["resolution_state"] == "AMBIGUOUS"),
            "exact_next_action": "materialize_campaign_lineage_for_resolved_or_limited_theses",
        },
    }


def _render_markdown(snapshot: dict[str, object]) -> str:
    lines = [
        "# QRE Identity Ambiguity Resolution",
        "",
        f"- identity_resolution_identity: `{common.text(snapshot.get('identity_resolution_identity'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('resolution_state'))}` -> `{common.text(row.get('next_action'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018c.", suffix=".tmp", dir=str(path.parent))
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


def write_outputs(snapshot: dict[str, object]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_identity_ambiguity_resolution")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
