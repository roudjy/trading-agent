from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Final

from reporting import qre_ade018_common as common
from reporting import qre_blocked_thesis_lineage_census as census
from reporting import qre_identity_ambiguity_resolution as identity

REPORT_KIND: Final[str] = "qre_campaign_lineage_materialization"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018d-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_campaign_lineage_materialization")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_campaign_lineage_materialization.md")
DEFAULT_CENSUS_PATH: Final[Path] = Path("logs/qre_blocked_thesis_lineage_census/latest.json")
DEFAULT_IDENTITY_PATH: Final[Path] = Path("logs/qre_identity_ambiguity_resolution/latest.json")
DEFAULT_GENERATED_LINEAGE_PATH: Final[Path] = Path("generated_research/lineage/generated_campaign_lineage.v1.json")
VALID_STATES: Final[tuple[str, ...]] = (
    "COMPLETE",
    "INCOMPLETE",
    "IDENTITY_BLOCKED",
    "PRESET_MISSING",
    "IMPLEMENTATION_MISSING",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_campaign_lineage_materialization/",
    "docs/governance/qre_campaign_lineage_materialization.md",
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
    generated_lineage_path: Path | None = None,
) -> dict[str, object]:
    root = repo_root or Path.cwd()
    census_payload = common.read_json(root / (census_path or DEFAULT_CENSUS_PATH))
    if census_payload is None:
        census_payload = census.collect_snapshot(repo_root=root)
    identity_payload = common.read_json(root / (identity_path or DEFAULT_IDENTITY_PATH))
    if identity_payload is None:
        identity_payload = identity.collect_snapshot(repo_root=root)
    generated_lineage_payload = common.read_json(root / (generated_lineage_path or DEFAULT_GENERATED_LINEAGE_PATH)) or {}
    identity_by_hypothesis = common.index_by(common.rows(identity_payload, "rows"), "source_hypothesis_id")
    generated_lineage_by_hypothesis = common.index_by(common.rows(generated_lineage_payload, "rows"), "source_hypothesis_id")
    rows_out: list[dict[str, object]] = []
    for row in common.rows(census_payload, "rows"):
        source_hypothesis_id = common.text(row.get("source_hypothesis_id"))
        identity_row = identity_by_hypothesis.get(source_hypothesis_id, {})
        generated_lineage_row = generated_lineage_by_hypothesis.get(source_hypothesis_id, {})
        lineage_status = common.text(row.get("lineage_status"))
        resolution_state = common.text(identity_row.get("resolution_state"))
        generated_campaign_identity = common.text(
            generated_lineage_row.get("campaign_specification_identity")
        )
        generated_preset_identity = common.text(
            generated_lineage_row.get("preset_id")
        )
        if generated_campaign_identity and generated_preset_identity:
            materialization_state = "COMPLETE"
            exact_blocker = "none"
            next_action = (
                common.text(generated_lineage_row.get("next_action"))
                or "preserve_campaign_lineage_state"
            )
        elif generated_campaign_identity:
            materialization_state = "PRESET_MISSING"
            exact_blocker = "generated_strategy_registered_but_preset_missing"
            next_action = "generate_bounded_research_preset"
        elif lineage_status in {"IMPLEMENTATION_MISSING", "PRESET_MISSING"}:
            materialization_state = lineage_status
            exact_blocker = common.text(row.get("exact_blocker")) or "bounded_campaign_metadata_missing"
            next_action = "establish_campaign_lineage_for_thesis"
        elif resolution_state in {"AMBIGUOUS", "BLOCKED", "CONFLICTING"}:
            materialization_state = "IDENTITY_BLOCKED"
            exact_blocker = common.text(identity_row.get("ambiguity_reason")) or "identity_resolution_missing"
            next_action = "resolve_identity_ambiguity_for_thesis"
        elif common.text(row.get("campaign_identity")):
            materialization_state = "COMPLETE"
            exact_blocker = "none"
            next_action = "preserve_campaign_lineage_state"
        else:
            materialization_state = "INCOMPLETE"
            exact_blocker = common.text(row.get("exact_blocker")) or "campaign_lineage_not_materialized"
            next_action = "materialize_campaign_lineage_for_thesis"
        if materialization_state not in VALID_STATES:
            raise ValueError(f"invalid materialization state: {materialization_state}")
        rows_out.append(
            {
                "stable_id": f"qrcl_{common.stable_digest({'hypothesis': source_hypothesis_id})[:16]}",
                "source_hypothesis_id": source_hypothesis_id,
                "mechanism": common.text(row.get("mechanism")),
                "strategy_or_representation": common.text(row.get("strategy_implementation_identity")),
                "preset_identity": common.text(row.get("preset_identity")),
                "universe": common.text(row.get("universe")),
                "source_identity": common.text(identity_row.get("source_identity")) or common.text(row.get("source_identity")),
                "dataset_identity": common.text(identity_row.get("dataset_identity")) or common.text(row.get("dataset_identity")),
                "snapshot_identity": common.text(row.get("snapshot_identity")),
                "campaign_specification_identity": common.text(generated_lineage_row.get("campaign_specification_identity")) or common.text(row.get("campaign_identity")),
                "materialization_state": materialization_state,
                "exact_blocker": exact_blocker,
                "next_action": next_action,
                "provenance_refs": common.dedupe(
                    common.normalize_list(row.get("provenance_refs"))
                    + common.normalize_list(identity_row.get("provenance_refs"))
                    + common.normalize_list(generated_lineage_row.get("provenance_refs"))
                ),
            }
        )
    rows_out.sort(key=lambda item: common.text(item.get("source_hypothesis_id")))
    lineage_identity = f"qrcl_{common.stable_digest({'rows': rows_out})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "campaign_lineage_identity": lineage_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "complete_count": sum(1 for row in rows_out if row["materialization_state"] == "COMPLETE"),
            "incomplete_count": sum(1 for row in rows_out if row["materialization_state"] == "INCOMPLETE"),
            "identity_blocked_count": sum(1 for row in rows_out if row["materialization_state"] == "IDENTITY_BLOCKED"),
            "exact_next_action": "specify_null_controls_for_materialized_or_partially_materialized_theses",
        },
    }


def _render_markdown(snapshot: dict[str, object]) -> str:
    lines = [
        "# QRE Campaign Lineage Materialization",
        "",
        f"- campaign_lineage_identity: `{common.text(snapshot.get('campaign_lineage_identity'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('materialization_state'))}` -> `{common.text(row.get('next_action'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018d.", suffix=".tmp", dir=str(path.parent))
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
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_campaign_lineage_materialization")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
