from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Final

import reporting.qre_executable_hypothesis_selection as selection

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_selection_route_materialization"

OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_selection_route_materialization/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

NOTE_SELECTION_INPUT_UNAVAILABLE: Final[str] = "selection_input_unavailable"
NOTE_SELECTION_ROW_NOT_SELECTED: Final[str] = "selection_row_not_selected"


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _str_list(values: Any, *, max_items: int = 50, max_len: int = 180) -> list[str]:
    if not isinstance(values, list | tuple | set | frozenset):
        return []
    out: list[str] = []
    for value in list(values)[:max_items]:
        text = _bounded_str(value, max_len=max_len)
        if text:
            out.append(text)
    return out


def _stable_id(prefix: str, *parts: Any) -> str:
    joined = "|".join(_bounded_str(part, max_len=240) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _selection_rows(selection_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = selection_snapshot.get("selection_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _build_route_rows(
    *,
    selection_snapshot: dict[str, Any],
    generated_at_utc: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    observations: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    validation_plans: list[dict[str, Any]] = []
    run_manifests: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in _selection_rows(selection_snapshot):
        selection_id = _bounded_str(row.get("selection_id"), max_len=160)
        status = _bounded_str(row.get("selection_status"), max_len=80)
        if status != "selected":
            warnings.append(f"{NOTE_SELECTION_ROW_NOT_SELECTED}:{selection_id or 'unknown'}")
            continue

        preset_name = _bounded_str(row.get("preset_name"), max_len=160)
        executable_hypothesis_id = _bounded_str(
            row.get("executable_hypothesis_id"),
            max_len=160,
        )
        strategy_family = _bounded_str(row.get("strategy_family"), max_len=160)
        strategy_template_id = _bounded_str(row.get("strategy_template_id"), max_len=160)
        asset = _bounded_str(row.get("asset"), max_len=80)
        symbol = _bounded_str(row.get("symbol"), max_len=80) or asset
        timeframe = _bounded_str(row.get("timeframe"), max_len=40)
        interval = _bounded_str(row.get("interval"), max_len=40) or timeframe
        summary = _bounded_str(row.get("summary"), max_len=360)
        source_hypothesis_id = (
            _bounded_str(
                row.get("source_hypothesis_id"),
                max_len=160,
            )
            or executable_hypothesis_id
        )
        evidence_refs = _str_list(
            row.get("supporting_evidence_refs"),
            max_items=24,
            max_len=180,
        )
        universe = _str_list(row.get("universe"), max_items=50, max_len=80)
        asset_class = _bounded_str(row.get("asset_class"), max_len=80)
        profile_name = _bounded_str(row.get("selection_profile_name"), max_len=120)

        observation_id = _stable_id("qre-obs-sel", selection_id, preset_name, asset, timeframe)
        qre_hypothesis_id = _stable_id(
            "qre-hyp-sel",
            selection_id,
            executable_hypothesis_id,
            preset_name,
            asset,
            timeframe,
        )
        validation_plan_id = _stable_id("qre-plan-sel", qre_hypothesis_id, preset_name)
        run_manifest_id = _stable_id("qre-run-sel", validation_plan_id, qre_hypothesis_id)

        source_artifact = OUTPUT_ARTIFACT_RELATIVE_PATH
        source_report_kind = REPORT_KIND
        source_row_id = selection_id

        observations.append(
            {
                "observation_id": observation_id,
                "observation_type": "executable_hypothesis_selection",
                "source_artifact": source_artifact,
                "source_report_kind": source_report_kind,
                "source_row_id": source_row_id,
                "supporting_evidence_refs": evidence_refs,
                "asset": asset,
                "symbol": symbol,
                "timeframe": timeframe,
                "interval": interval,
                "summary": summary,
                "preset_name": preset_name,
                "strategy_family": strategy_family,
                "strategy_template_id": strategy_template_id,
                "executable_hypothesis_id": executable_hypothesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "market_context": {
                    "asset_class": asset_class,
                    "universe": universe,
                    "selection_profile_name": profile_name,
                    "selection_source": _bounded_str(row.get("selection_source"), max_len=160),
                },
                "generated_at_utc": generated_at_utc,
            }
        )

        hypotheses.append(
            {
                "hypothesis_id": qre_hypothesis_id,
                "source_observation_id": observation_id,
                "source_artifact": source_artifact,
                "source_report_kind": source_report_kind,
                "source_row_id": source_row_id,
                "supporting_evidence_refs": evidence_refs,
                "asset": asset,
                "symbol": symbol,
                "timeframe": timeframe,
                "interval": interval,
                "summary": summary,
                "preset_name": preset_name,
                "strategy_family": strategy_family,
                "strategy_template_id": strategy_template_id,
                "executable_hypothesis_id": executable_hypothesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "status": "proposed",
                "generated_at_utc": generated_at_utc,
            }
        )

        validation_plans.append(
            {
                "validation_plan_id": validation_plan_id,
                "hypothesis_id": qre_hypothesis_id,
                "executable_hypothesis_id": executable_hypothesis_id,
                "preset_name": preset_name,
                "strategy_family": strategy_family,
                "strategy_template_id": strategy_template_id,
                "asset": asset,
                "symbol": symbol,
                "timeframe": timeframe,
                "interval": interval,
                "status": "planned",
                "generated_at_utc": generated_at_utc,
            }
        )

        run_manifests.append(
            {
                "run_manifest_id": run_manifest_id,
                "target_validation_plan_id": validation_plan_id,
                "hypothesis_id": qre_hypothesis_id,
                "executable_hypothesis_id": executable_hypothesis_id,
                "preset_name": preset_name,
                "asset": asset,
                "symbol": symbol,
                "timeframe": timeframe,
                "interval": interval,
                "status": "operator_review_required",
                "generated_at_utc": generated_at_utc,
            }
        )

    return observations, hypotheses, validation_plans, run_manifests, warnings


def _counts(
    *,
    observations: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    validation_plans: list[dict[str, Any]],
    run_manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "observations": len(observations),
        "hypotheses": len(hypotheses),
        "validation_plans": len(validation_plans),
        "run_manifests": len(run_manifests),
        "materialized_route_ready": min(
            len(observations),
            len(hypotheses),
            len(validation_plans),
            len(run_manifests),
        ),
    }


def _base_snapshot(
    *,
    generated_at_utc: str,
    selection_snapshot: dict[str, Any],
    observations: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    validation_plans: list[dict[str, Any]],
    run_manifests: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    counts = _counts(
        observations=observations,
        hypotheses=hypotheses,
        validation_plans=validation_plans,
        run_manifests=run_manifests,
    )
    ready = counts["materialized_route_ready"]
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
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
        "selection_summary": {
            "report_kind": selection_snapshot.get("report_kind"),
            "selected": (selection_snapshot.get("counts") or {}).get("selected", 0),
            "blocked": (selection_snapshot.get("counts") or {}).get("blocked", 0),
            "total": (selection_snapshot.get("counts") or {}).get("total", 0),
            "final_recommendation": selection_snapshot.get("final_recommendation"),
        },
        "counts": counts,
        "market_observation_payload": {
            "report_kind": "qre_market_observation_snapshot",
            "schema_version": "selection-route-v1",
            "generated_at_utc": generated_at_utc,
            "observations": observations,
        },
        "hypothesis_candidates_payload": {
            "report_kind": "qre_hypothesis_candidates",
            "schema_version": "selection-route-v1",
            "generated_at_utc": generated_at_utc,
            "hypotheses": hypotheses,
        },
        "validation_plans_payload": {
            "report_kind": "qre_hypothesis_validation_plan",
            "schema_version": "selection-route-v1",
            "generated_at_utc": generated_at_utc,
            "validation_plans": validation_plans,
        },
        "run_manifest_payload": {
            "report_kind": "qre_research_run_manifest",
            "schema_version": "selection-route-v1",
            "generated_at_utc": generated_at_utc,
            "run_manifests": run_manifests,
        },
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "selection_route_materialized_for_validation_request"
            if ready > 0 and not validation_warnings
            else "selection_route_materialization_blocked"
        ),
    }


def collect_snapshot(
    *,
    selection_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    warnings: list[str] = []
    active_selection_snapshot = selection_snapshot or selection.collect_snapshot(
        generated_at_utc=generated,
    )
    if not isinstance(active_selection_snapshot, dict):
        active_selection_snapshot = {}
        warnings.append(NOTE_SELECTION_INPUT_UNAVAILABLE)

    observations, hypotheses, validation_plans, run_manifests, row_warnings = _build_route_rows(
        selection_snapshot=active_selection_snapshot,
        generated_at_utc=generated,
    )
    warnings.extend(row_warnings)

    return _base_snapshot(
        generated_at_utc=generated,
        selection_snapshot=active_selection_snapshot,
        observations=observations,
        hypotheses=hypotheses,
        validation_plans=validation_plans,
        run_manifests=run_manifests,
        validation_warnings=warnings,
    )


def write_outputs(snapshot: dict[str, Any], *, output_path: Path | None = None) -> Path:
    target = output_path or ARTIFACT_LATEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
