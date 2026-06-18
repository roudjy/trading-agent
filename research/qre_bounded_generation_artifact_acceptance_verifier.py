from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_first_batch_generation_decision as decision
from research import qre_controlled_validation_adapter_result_materialization as adapter_materialization


REPORT_KIND: Final[str] = "qre_bounded_generation_artifact_acceptance_verifier"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_generation_artifact_acceptance_verifier")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_generation_artifact_acceptance_verifier/"
SCAN_ROOTS: Final[tuple[str, ...]] = ("logs", "artifacts", "archived", "backup", "local_quarantine")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> Any | None:
    if path.suffix.lower() not in {".json", ".jsonl"}:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _mapping_has_key(payload: Any, key: str) -> bool:
    return isinstance(payload, Mapping) and key in payload


def _iter_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        paths.extend(sorted(path for path in root.rglob("*.json") if path.is_file()))
    return paths


def classify_artifact(
    path: Path,
    *,
    repo_root: Path = Path("."),
    allowlisted_paths: Sequence[str],
) -> dict[str, Any]:
    payload = _read_json(path)
    relative_path = path.relative_to(repo_root).as_posix()
    text = json.dumps(payload, sort_keys=True, default=str).lower() if payload is not None else ""
    report_kind = str(payload.get("report_kind") or "") if isinstance(payload, Mapping) else ""
    if report_kind == adapter_materialization.REPORT_KIND:
        materialization_status = str(payload.get("materialization_status") or "")
        authority = payload.get("authority") if isinstance(payload.get("authority"), Mapping) else {}
        lineage_candidates = payload.get("lineage_candidates") if isinstance(payload.get("lineage_candidates"), list) else []
        oos_candidates = payload.get("oos_candidates") if isinstance(payload.get("oos_candidates"), list) else []
        accepted_lineage_count = int(payload.get("accepted_lineage_count") or 0)
        accepted_oos_count = int(payload.get("accepted_oos_count") or 0)
        lineage_accepted = any(
            isinstance(candidate, Mapping)
            and str(candidate.get("candidate_id") or "").strip()
            and (
                str(candidate.get("campaign_id") or "").strip()
                or str(candidate.get("generation_id") or "").strip()
                or str(candidate.get("controlled_generation_id") or "").strip()
                or str(candidate.get("grid_run_id") or "").strip()
            )
            and bool(candidate.get("accepted_by_adapter", False))
            for candidate in lineage_candidates
        )
        oos_accepted = any(
            isinstance(candidate, Mapping)
            and str(candidate.get("candidate_id") or "").strip()
            and bool(candidate.get("oos_metric_fields"))
            and bool(candidate.get("cost_slippage_assumption_refs"))
            and bool(candidate.get("accepted_by_adapter", False))
            for candidate in oos_candidates
        )
        has_authority = (
            bool(authority.get("non_authoritative")) is True
            and bool(authority.get("can_authorize_execution")) is False
            and bool(authority.get("can_promote_candidate")) is False
            and bool(authority.get("can_clear_blockers")) is False
        )
        if (
            materialization_status == "materialized_accepted_structured_evidence"
            and accepted_lineage_count > 0
            and accepted_oos_count > 0
            and lineage_accepted
            and oos_accepted
            and has_authority
        ):
            classification = "accepted_for_campaign_lineage"
        elif materialization_status == "materialized_no_safe_source":
            classification = "rejected_materialized_no_safe_source"
        elif materialization_status == "materialized_rejected_source":
            classification = "rejected_materialized_rejected_source"
        elif materialization_status == "materialized_provisional_only":
            classification = "rejected_materialized_provisional_only"
        elif materialization_status in {
            "blocked_invalid_runner_payload",
            "blocked_invalid_adapter_payload",
            "blocked_missing_required_fields",
        }:
            classification = "rejected_materialized_missing_required_fields"
        else:
            classification = "rejected_context_only"
        return {
            "path": str(path),
            "relative_path": relative_path,
            "classification": classification,
            "accepted_for_campaign_lineage": classification == "accepted_for_campaign_lineage",
            "accepted_for_oos_evidence": classification == "accepted_for_campaign_lineage",
            "accepted_for_screening_evidence": False,
            "materialization_status": materialization_status,
        }
    target_symbols = {"aapl", "nvda"}
    has_target_symbol = any(symbol in text for symbol in target_symbols)
    has_target_preset = "trend_pullback_continuation_daily_v1" in text
    has_target_timeframe = "daily_v1" in text
    has_candidate_id = _mapping_has_key(payload, "candidate_id")
    has_generation_identity = _mapping_has_key(payload, "campaign_id") or _mapping_has_key(payload, "generation_run_id")
    has_grid_run_identity = _mapping_has_key(payload, "grid_run_id") or _mapping_has_key(payload, "controlled_generation_id")
    has_oos_fields = _mapping_has_key(payload, "oos_metric_fields")
    has_screening_fields = _mapping_has_key(payload, "screening_evidence_fields")
    has_lineage_fields = _mapping_has_key(payload, "lineage_fields")
    has_validation_status = _mapping_has_key(payload, "validation_status")
    has_artifact_timestamp = _mapping_has_key(payload, "artifact_timestamp") or _mapping_has_key(payload, "generated_at")
    has_source_artifact_path = _mapping_has_key(payload, "source_artifact_path")
    has_reason_record_refs = _mapping_has_key(payload, "reason_record_refs")
    has_policy_version = _mapping_has_key(payload, "policy_version")
    has_operator_approval = _mapping_has_key(payload, "operator_approval_id") or _mapping_has_key(payload, "approval_manifest_ref")
    if report_kind.startswith("qre_"):
        classification = "rejected_context_only"
    elif relative_path.startswith(".tmp/") or "stdout_tail" in text:
        classification = "rejected_stdout_only"
    elif "trend_pullback_v1" in text and "trend_pullback_continuation_daily_v1" not in text:
        classification = "rejected_context_only"
    elif not has_target_symbol:
        classification = "rejected_preset_mismatch"
    elif "trend_pullback_continuation_daily_v1" not in text:
        classification = "rejected_preset_mismatch"
    elif not has_target_timeframe:
        classification = "rejected_timeframe_mismatch"
    elif not any(relative_path.startswith(prefix) for prefix in allowlisted_paths):
        classification = "rejected_path_not_allowlisted"
    elif not (has_candidate_id and has_generation_identity and has_grid_run_identity):
        classification = "rejected_missing_identity"
    elif not has_operator_approval:
        classification = "rejected_unapproved_run"
    elif not (
        has_oos_fields
        and has_screening_fields
        and has_lineage_fields
        and has_validation_status
        and has_artifact_timestamp
        and has_source_artifact_path
        and has_reason_record_refs
        and has_policy_version
    ):
        classification = "rejected_missing_identity"
    else:
        classification = "accepted_for_campaign_lineage"
    return {
        "path": str(path),
        "relative_path": relative_path,
        "classification": classification,
        "accepted_for_campaign_lineage": classification == "accepted_for_campaign_lineage",
        "accepted_for_oos_evidence": classification == "accepted_for_campaign_lineage" and has_oos_fields,
        "accepted_for_screening_evidence": classification == "accepted_for_campaign_lineage" and has_screening_fields,
    }


def build_bounded_generation_artifact_acceptance_verifier(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    allowlisted_paths = list(
        (
            decision.build_bounded_first_batch_generation_decision(repo_root=repo_root)
            .get("acceptance_contract", {})
            .get("allowlisted_paths", [])
        )
    )
    rows = [
        classify_artifact(path, repo_root=repo_root, allowlisted_paths=allowlisted_paths)
        for path in _iter_paths(repo_root)
    ]
    counts = Counter(str(row["classification"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "artifact_count": len(rows),
            "classification_counts": dict(sorted(counts.items())),
            "operator_summary": (
                "Post-generation acceptance verifier remains read-only and classifies future "
                "bounded artifacts against the explicit acceptance contract."
            ),
            "final_recommendation": "artifact_acceptance_verifier_ready",
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "does_not_generate_evidence": True,
            "does_not_accept_context_only_as_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Bounded Generation Artifact Acceptance Verifier",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["artifact_count", str(summary.get("artifact_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Path", "Classification"],
                [
                    [str(row.get("relative_path") or ""), str(row.get("classification") or "")]
                    for row in rows[:20]
                ]
                or [["none", "none"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_generation_artifact_acceptance_verifier: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_bounded_generation_artifact_acceptance_verifier",
        description="Build the bounded generation artifact acceptance verifier report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_bounded_generation_artifact_acceptance_verifier()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
