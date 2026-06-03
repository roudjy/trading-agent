from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final

import reporting.qre_executable_validation_request as validation_request
import reporting.qre_market_observation_hypothesis_readiness as readiness
import reporting.qre_selection_route_materialization as materialization
import reporting.qre_validation_request_dry_run_runner as dry_run


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_selection_route_validation_flow"

OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_selection_route_validation_flow/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    return counts if isinstance(counts, dict) else {}


def _dry_run_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    return counts if isinstance(counts, dict) else {}


def _readiness_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    return counts if isinstance(counts, dict) else {}


def _base_snapshot(
    *,
    generated_at_utc: str,
    materialization_snapshot: dict[str, Any],
    readiness_snapshot: dict[str, Any],
    validation_request_snapshot: dict[str, Any],
    dry_run_snapshot: dict[str, Any],
) -> dict[str, Any]:
    mat_counts = materialization_snapshot.get("counts") or {}
    readiness_counts = _readiness_counts(readiness_snapshot)
    request_counts = _request_counts(validation_request_snapshot)
    dry_run_counts = _dry_run_counts(dry_run_snapshot)

    materialized_route_ready = int(mat_counts.get("materialized_route_ready", 0) or 0)
    hypothesis_ready = int(readiness_counts.get("hypothesis_ready", 0) or 0)
    request_ready = int(request_counts.get("ready", 0) or 0)
    dry_run_ready = int(dry_run_counts.get("ready", 0) or 0)

    flow_ready = min(
        materialized_route_ready,
        hypothesis_ready,
        request_ready,
        dry_run_ready,
    )

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
        "counts": {
            "materialized_route_ready": materialized_route_ready,
            "hypothesis_ready": hypothesis_ready,
            "request_ready_for_operator_review": request_ready,
            "dry_run_ready": dry_run_ready,
            "selection_validation_flow_ready": flow_ready,
        },
        "materialization": {
            "counts": mat_counts,
            "final_recommendation": materialization_snapshot.get("final_recommendation"),
        },
        "readiness": {
            "counts": readiness_counts,
            "by_readiness_class": readiness_snapshot.get("by_readiness_class", {}),
            "final_recommendation": readiness_snapshot.get("final_recommendation"),
        },
        "validation_request": {
            "counts": request_counts,
            "final_recommendation": validation_request_snapshot.get("final_recommendation"),
        },
        "dry_run": {
            "counts": dry_run_counts,
            "executed_anything": dry_run_snapshot.get("executed_anything", False),
            "final_recommendation": dry_run_snapshot.get("final_recommendation"),
        },
        "validation_warnings": [
            *list(materialization_snapshot.get("validation_warnings") or []),
            *list(readiness_snapshot.get("validation_warnings") or []),
            *list(validation_request_snapshot.get("validation_warnings") or []),
            *list(dry_run_snapshot.get("validation_warnings") or []),
        ],
        "final_recommendation": (
            "selection_route_validation_flow_ready_for_operator_review"
            if flow_ready > 0
            else "selection_route_validation_flow_blocked"
        ),
    }


def collect_snapshot(
    *,
    materialization_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_materialization = materialization_snapshot or materialization.collect_snapshot(
        generated_at_utc=generated,
    )

    with TemporaryDirectory(prefix="qre_selection_route_validation_flow_") as tmp_name:
        tmp = Path(tmp_name)

        market_path = tmp / "market_observations.json"
        hypotheses_path = tmp / "hypothesis_candidates.json"
        plans_path = tmp / "validation_plans.json"
        manifests_path = tmp / "run_manifest.json"
        readiness_path = tmp / "readiness.json"
        request_path = tmp / "validation_request.json"

        _write_json(
            market_path,
            active_materialization.get("market_observation_payload") or {},
        )
        _write_json(
            hypotheses_path,
            active_materialization.get("hypothesis_candidates_payload") or {},
        )
        _write_json(
            plans_path,
            active_materialization.get("validation_plans_payload") or {},
        )
        _write_json(
            manifests_path,
            active_materialization.get("run_manifest_payload") or {},
        )

        readiness_snapshot = readiness.collect_snapshot(
            input_artifact_path=market_path,
            generated_at_utc=generated,
        )
        _write_json(readiness_path, readiness_snapshot)

        request_snapshot = validation_request.collect_snapshot(
            input_artifact_path=hypotheses_path,
            readiness_artifact_path=readiness_path,
            market_observation_artifact_path=market_path,
            validation_plan_artifact_path=plans_path,
            run_manifest_artifact_path=manifests_path,
            generated_at_utc=generated,
        )
        _write_json(request_path, request_snapshot)

        dry_run_snapshot = dry_run.collect_snapshot(
            input_artifact_path=request_path,
            generated_at_utc=generated,
        )

    return _base_snapshot(
        generated_at_utc=generated,
        materialization_snapshot=active_materialization,
        readiness_snapshot=readiness_snapshot,
        validation_request_snapshot=request_snapshot,
        dry_run_snapshot=dry_run_snapshot,
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
