from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Final

from research.discovery_sprint import BUILTIN_PROFILES, derive_plan
from research.presets import PRESETS

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_executable_hypothesis_selection"

DEFAULT_PROFILE_NAME: Final[str] = "crypto_exploratory_v1"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_executable_hypothesis_selection/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

NOTE_PROFILE_NOT_FOUND: Final[str] = "selection_profile_not_found"
NOTE_PLAN_DERIVATION_FAILED: Final[str] = "selection_plan_derivation_failed"
NOTE_PRESET_NOT_FOUND: Final[str] = "selection_preset_not_found"
NOTE_PRESET_BUNDLE_EMPTY: Final[str] = "selection_preset_bundle_empty"
NOTE_MALFORMED_PLAN_ENTRY: Final[str] = "selection_malformed_plan_entry"


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _bounded_list(values: Any, *, max_items: int = 25, max_len: int = 120) -> list[str]:
    if not isinstance(values, list | tuple | set | frozenset):
        return []
    out: list[str] = []
    for value in list(values)[:max_items]:
        text = _bounded_str(value, max_len=max_len)
        if text:
            out.append(text)
    return out


def _payload_from_entry(entry: Any) -> dict[str, Any]:
    if hasattr(entry, "to_payload") and callable(entry.to_payload):
        payload = entry.to_payload()
        return dict(payload) if isinstance(payload, dict) else {}
    if is_dataclass(entry):
        payload = asdict(entry)
        return dict(payload) if isinstance(payload, dict) else {}
    if isinstance(entry, dict):
        return dict(entry)
    return {}


def _stable_id(*parts: Any, prefix: str) -> str:
    joined = "|".join(_bounded_str(part, max_len=240) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _preset_by_name(presets: Any) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for preset in presets or ():
        name = _bounded_str(getattr(preset, "name", None), max_len=120)
        if name:
            index[name] = preset
    return index


def _profile_by_name(profile_name: str) -> Any | None:
    profiles = BUILTIN_PROFILES
    if isinstance(profiles, dict):
        return profiles.get(profile_name)
    return None


def _selection_status(*, row: dict[str, Any], preset: Any | None, strategy_template_id: str) -> str:
    if not row:
        return NOTE_MALFORMED_PLAN_ENTRY
    if preset is None:
        return NOTE_PRESET_NOT_FOUND
    if not strategy_template_id:
        return NOTE_PRESET_BUNDLE_EMPTY
    required = (
        "preset_name",
        "hypothesis_id",
        "strategy_family",
        "timeframe",
        "asset_class",
        "universe",
    )
    if any(not row.get(key) for key in required):
        return NOTE_MALFORMED_PLAN_ENTRY
    return "selected"


def _build_selection_row(
    *,
    row: dict[str, Any],
    preset: Any | None,
    profile_name: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    preset_name = _bounded_str(row.get("preset_name"), max_len=120)
    executable_hypothesis_id = _bounded_str(row.get("hypothesis_id"), max_len=120)
    strategy_family = _bounded_str(row.get("strategy_family"), max_len=120)
    timeframe = _bounded_str(row.get("timeframe"), max_len=40)
    asset_class = _bounded_str(row.get("asset_class"), max_len=40)
    universe = _bounded_list(row.get("universe"), max_items=50, max_len=80)
    asset = universe[0] if universe else ""

    preset_bundle = _bounded_list(getattr(preset, "bundle", ()), max_items=25, max_len=120)
    strategy_template_id = preset_bundle[0] if preset_bundle else ""

    status = _selection_status(
        row=row,
        preset=preset,
        strategy_template_id=strategy_template_id,
    )

    selection_id = _stable_id(
        profile_name,
        preset_name,
        executable_hypothesis_id,
        strategy_template_id,
        timeframe,
        asset,
        prefix="qre-exec-sel",
    )

    reason_codes: list[str] = []
    if status == "selected":
        reason_codes.append("catalog_profile_plan_entry")
        reason_codes.append("preset_bundle_strategy_template_resolved")
        reason_codes.append("operator_review_required")
    else:
        reason_codes.append(status)

    return {
        "selection_id": selection_id,
        "selection_status": status,
        "selection_profile_name": profile_name,
        "selection_source": "research.discovery_sprint.derive_plan",
        "selection_reason": "catalog_derive_plan_entry",
        "generated_at_utc": generated_at_utc,
        "preset_name": preset_name or None,
        "executable_hypothesis_id": executable_hypothesis_id or None,
        "source_hypothesis_id": executable_hypothesis_id or None,
        "strategy_family": strategy_family or None,
        "strategy_template_id": strategy_template_id or None,
        "asset_class": asset_class or None,
        "asset": asset or None,
        "symbol": asset or None,
        "timeframe": timeframe or None,
        "interval": timeframe or None,
        "universe": universe,
        "preset_bundle": preset_bundle,
        "supporting_evidence_refs": [
            f"discovery_sprint:{profile_name}#{preset_name}",
            f"strategy_hypothesis_catalog#{executable_hypothesis_id}",
            f"research.presets#{preset_name}",
        ],
        "requires_operator_approval": True,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "reason_codes": reason_codes,
    }


def _counts(selection_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for row in selection_rows:
        status = _bounded_str(row.get("selection_status"), max_len=80) or "unknown"
        by_status[status] = by_status.get(status, 0) + 1

    selected = by_status.get("selected", 0)
    blocked = max(0, len(selection_rows) - selected)
    return {
        "total": len(selection_rows),
        "selected": selected,
        "blocked": blocked,
        "by_selection_status": dict(sorted(by_status.items())),
    }


def _base_snapshot(
    *,
    generated_at_utc: str,
    profile_name: str,
    selection_rows: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    counts = _counts(selection_rows)
    final_recommendation = (
        "executable_hypothesis_selections_ready_for_operator_review"
        if counts["selected"] > 0 and counts["blocked"] == 0
        else "executable_hypothesis_selection_blocked"
    )
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "selection_profile_name": profile_name,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "read_only": True,
        "launches_subprocess": False,
        "launches_codex": False,
        "mutates_research_artifacts": False,
        "mutates_strategy_or_preset": False,
        "mutates_campaign_queue": False,
        "mutates_paper_shadow_live_runtime": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "writes_development_work_queue": False,
        "counts": counts,
        "selection_rows": selection_rows,
        "validation_warnings": validation_warnings,
        "final_recommendation": final_recommendation,
    }


def collect_snapshot(
    *,
    profile_name: str = DEFAULT_PROFILE_NAME,
    generated_at_utc: str | None = None,
    presets: Any = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    warnings: list[str] = []
    profile = _profile_by_name(profile_name)
    if profile is None:
        warnings.append(NOTE_PROFILE_NOT_FOUND)
        return _base_snapshot(
            generated_at_utc=generated,
            profile_name=profile_name,
            selection_rows=[],
            validation_warnings=warnings,
        )

    active_presets = presets if presets is not None else PRESETS
    preset_index = _preset_by_name(active_presets)

    try:
        plan = derive_plan(profile, presets=active_presets)
    except Exception:
        warnings.append(NOTE_PLAN_DERIVATION_FAILED)
        return _base_snapshot(
            generated_at_utc=generated,
            profile_name=profile_name,
            selection_rows=[],
            validation_warnings=warnings,
        )

    selection_rows: list[dict[str, Any]] = []
    for entry in plan:
        row = _payload_from_entry(entry)
        preset_name = _bounded_str(row.get("preset_name"), max_len=120)
        preset = preset_index.get(preset_name)
        selection_rows.append(
            _build_selection_row(
                row=row,
                preset=preset,
                profile_name=profile_name,
                generated_at_utc=generated,
            )
        )

    selection_rows.sort(key=lambda item: item.get("selection_id", ""))
    return _base_snapshot(
        generated_at_utc=generated,
        profile_name=profile_name,
        selection_rows=selection_rows,
        validation_warnings=warnings,
    )


def write_outputs(snapshot: dict[str, Any], *, path: Path | None = None) -> Path:
    target = path or ARTIFACT_LATEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
