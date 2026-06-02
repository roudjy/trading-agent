"""Read-only QRE closed-loop materialization runner."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Final

from reporting import qre_closed_loop_operator_report
from reporting import qre_evidence_quality_gate
from reporting import qre_hypothesis_candidates
from reporting import qre_hypothesis_evidence_update
from reporting import qre_hypothesis_validation_plan
from reporting import qre_hypothesis_validation_results
from reporting import qre_market_observation_snapshot
from reporting import qre_observation_hypothesis_projector
from reporting import qre_research_run_manifest
from reporting import qre_trusted_loop_readiness
from reporting import qre_validated_hypothesis_promotion_intent
from reporting import qre_validation_research_action_candidates

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_closed_loop_materialization"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_closed_loop_materialization"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_closed_loop_materialization/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STEP_MODULES: Final[tuple[ModuleType, ...]] = (
    qre_market_observation_snapshot,
    qre_hypothesis_candidates,
    qre_observation_hypothesis_projector,
    qre_hypothesis_validation_plan,
    qre_validation_research_action_candidates,
    qre_research_run_manifest,
    qre_hypothesis_validation_results,
    qre_hypothesis_evidence_update,
    qre_closed_loop_operator_report,
    qre_trusted_loop_readiness,
    qre_evidence_quality_gate,
    qre_validated_hypothesis_promotion_intent,
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    if isinstance(counts, dict):
        return counts
    for key in (
        "observations",
        "hypotheses",
        "validation_plans",
        "action_candidates",
        "run_manifests",
        "validation_results",
        "evidence_updates",
        "evidence_quality_rows",
        "promotion_intents",
    ):
        rows = snapshot.get(key)
        if isinstance(rows, list):
            return {"total": len(rows)}
    density = snapshot.get("evidence_density")
    if isinstance(density, dict):
        return dict(density)
    return {}


def _step_record(
    *,
    module: ModuleType,
    snapshot: dict[str, Any],
    artifact_path: Path | None,
) -> dict[str, Any]:
    return {
        "module": module.__name__,
        "report_kind": str(snapshot.get("report_kind") or ""),
        "final_recommendation": str(snapshot.get("final_recommendation") or ""),
        "safe_to_execute": False,
        "counts": _counts(snapshot),
        "artifact_path": _rel(artifact_path) if artifact_path is not None else None,
    }


def collect_snapshot(
    *,
    no_write: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    steps: list[dict[str, Any]] = []
    validation_warnings: list[str] = []
    aggregate_counts: dict[str, Any] = {}

    for module in STEP_MODULES:
        snapshot = module.collect_snapshot(generated_at_utc=generated)
        artifact_path: Path | None = None
        if not no_write:
            artifact_path = module.write_outputs(snapshot)
        report_kind = str(snapshot.get("report_kind") or module.__name__.rsplit(".", 1)[-1])
        aggregate_counts[report_kind] = _counts(snapshot)
        warnings = snapshot.get("validation_warnings")
        if isinstance(warnings, list):
            validation_warnings.extend(str(item) for item in warnings if item)
        steps.append(
            _step_record(
                module=module,
                snapshot=snapshot,
                artifact_path=artifact_path,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "steps": steps,
        "counts": aggregate_counts,
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "operator_review_required_before_any_follow_up"
            if validation_warnings
            else "closed_loop_materialized_for_operator_review"
        ),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "eligible_for_direct_execution": False,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE materialization dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_closed_loop_materialization.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_closed_loop_materialization_runner",
        description="Materialize read-only QRE closed-loop reports in sequence.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        no_write=args.no_write,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STEP_MODULES",
    "collect_snapshot",
    "main",
    "write_outputs",
]
