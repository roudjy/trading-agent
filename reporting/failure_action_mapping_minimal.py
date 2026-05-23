"""Minimal v3.15.20 Failure to Action Mapping slice.

This module implements the reactivated minimal v3.15.20 scope from
ADR-021. It is a deterministic, reporting-side advisory surface:

* explicit closed failure taxonomy;
* bounded next-action recommendations;
* one read-only reason record per input failure;
* atomic-write digest under ``logs/failure_action_mapping_minimal/``;
* no adaptive feedback loop, no strategy mutation, no executable
  strategy generation, and no paper / shadow / live behavior.

The module is stdlib-only and never imports execution-side surfaces.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.20-minimal-reactivated-2026-05-21"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "failure_action_mapping_minimal_digest"


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


FAILURE_CODES: Final[tuple[str, ...]] = (
    "insufficient_trades",
    "high_drawdown",
    "weak_stability",
    "low_win_rate",
    "negative_expectancy",
    "technical_failure",
    "no_oos_samples",
    "cost_gate_fail",
    "entropy_regime_incompatible",
    "tail_fragility_high",
    "unknown_failure",
)

NEXT_ACTIONS: Final[tuple[str, ...]] = (
    "increase_timeframe",
    "apply_volatility_filter",
    "segment_by_regime",
    "preserve_negative_result",
    "collect_more_evidence",
    "review_data_pipeline",
    "review_cost_assumptions",
    "hold_no_action",
)

SEVERITIES: Final[tuple[str, ...]] = ("low", "medium", "high")

REASON_CODES: Final[tuple[str, ...]] = (
    "taxonomy_match",
    "bounded_action",
    "technical_not_research",
    "evidence_insufficient",
    "negative_result_preserved",
)

INPUT_FAILURE_KEYS: Final[tuple[str, ...]] = (
    "subject_id",
    "failure_code",
    "severity",
    "evidence_count",
)

OUTPUT_ITEM_KEYS: Final[tuple[str, ...]] = (
    "subject_id",
    "failure_code",
    "severity",
    "evidence_count",
    "recommended_action",
    "rank",
    "reason_record",
)

REASON_RECORD_KEYS: Final[tuple[str, ...]] = (
    "record_id",
    "record_kind",
    "schema_version",
    "subject_id",
    "failure_code",
    "recommended_action",
    "reason_codes",
    "reason_text",
    "inputs_digest",
)

MAX_FAILURES: Final[int] = 256
MAX_SUBJECT_ID_LEN: Final[int] = 64
MIN_EVIDENCE_FOR_RESEARCH_ACTION: Final[int] = 3


ACTION_BY_FAILURE_CODE: Final[Mapping[str, str]] = {
    "insufficient_trades": "increase_timeframe",
    "high_drawdown": "apply_volatility_filter",
    "weak_stability": "segment_by_regime",
    "low_win_rate": "preserve_negative_result",
    "negative_expectancy": "preserve_negative_result",
    "technical_failure": "review_data_pipeline",
    "no_oos_samples": "collect_more_evidence",
    "cost_gate_fail": "review_cost_assumptions",
    "entropy_regime_incompatible": "segment_by_regime",
    "tail_fragility_high": "apply_volatility_filter",
    "unknown_failure": "hold_no_action",
}

SCREENING_CLASSIFICATION_TO_FAILURE_CODE: Final[Mapping[str, str]] = {
    "data_coverage_gap": "technical_failure",
    "data_coverage_unknown": "technical_failure",
    "identity_unresolved": "technical_failure",
    "incomplete_policy_trace": "technical_failure",
    "insufficient_oos_window": "no_oos_samples",
    "missing_diagnostics": "technical_failure",
    "missing_metric_field": "technical_failure",
    "missing_screening_evidence": "technical_failure",
    "no_candidate_after_policy_filter": "technical_failure",
    "no_oos_returns": "no_oos_samples",
    "no_survivor_after_eval": "technical_failure",
    "policy_trace_inconsistent": "technical_failure",
    "synthesis_gate_blocked": "technical_failure",
    "timeout": "technical_failure",
    "unsupported_failure_shape": "unknown_failure",
    "unknown_screening_failure": "unknown_failure",
}


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "failure_action_mapping_minimal"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/failure_action_mapping_minimal/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "failure_action_mapping_minimal: refusing write outside " f"allowlist: {path!r}"
        )


def _bounded_subject_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value[:MAX_SUBJECT_ID_LEN]


def _bounded_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def compute_inputs_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_record_id(
    subject_id: str,
    failure_code: str,
    recommended_action: str,
    inputs_digest: str,
) -> str:
    h = hashlib.sha256()
    h.update(subject_id.encode("utf-8"))
    h.update(b"\x1f")
    h.update(failure_code.encode("utf-8"))
    h.update(b"\x1f")
    h.update(recommended_action.encode("utf-8"))
    h.update(b"\x1f")
    h.update(inputs_digest.encode("utf-8"))
    return "fam_" + h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_failures(failures: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(failures, list | tuple):
        raise ValueError("failure_action_mapping_minimal: failures must be a list/tuple")
    if len(failures) > MAX_FAILURES:
        raise ValueError(
            "failure_action_mapping_minimal: too many failures "
            f"({len(failures)} > {MAX_FAILURES})"
        )
    seen: set[str] = set()
    for i, failure in enumerate(failures):
        if not isinstance(failure, Mapping):
            raise ValueError("failure_action_mapping_minimal: " f"failure[{i}] must be a mapping")
        missing = set(INPUT_FAILURE_KEYS) - set(failure.keys())
        if missing:
            raise ValueError(
                "failure_action_mapping_minimal: " f"failure[{i}] missing fields: {sorted(missing)}"
            )
        subject_id = failure["subject_id"]
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError(
                "failure_action_mapping_minimal: "
                f"failure[{i}].subject_id must be a non-empty str"
            )
        if subject_id in seen:
            raise ValueError(
                "failure_action_mapping_minimal: " f"duplicate subject_id {subject_id!r}"
            )
        seen.add(subject_id)
        if failure["failure_code"] not in FAILURE_CODES:
            raise ValueError(
                "failure_action_mapping_minimal: "
                f"failure[{i}].failure_code is not in closed taxonomy"
            )
        if failure["severity"] not in SEVERITIES:
            raise ValueError(
                "failure_action_mapping_minimal: "
                f"failure[{i}].severity is not in closed severity vocab"
            )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def _reason_for(
    *,
    failure_code: str,
    recommended_action: str,
    evidence_count: int,
) -> tuple[list[str], str]:
    reason_codes = ["taxonomy_match", "bounded_action"]
    if failure_code == "technical_failure":
        reason_codes.append("technical_not_research")
    if evidence_count < MIN_EVIDENCE_FOR_RESEARCH_ACTION:
        reason_codes.append("evidence_insufficient")
    if recommended_action == "preserve_negative_result":
        reason_codes.append("negative_result_preserved")

    if failure_code == "technical_failure":
        text = (
            "Technical failure is not research evidence; review the data "
            "or pipeline before any research action."
        )
    elif evidence_count < MIN_EVIDENCE_FOR_RESEARCH_ACTION:
        text = (
            f"Failure code {failure_code} has only {evidence_count} "
            "evidence records; recommendation is bounded and advisory."
        )
    else:
        text = f"Failure code {failure_code} maps deterministically to " f"{recommended_action}."
    return reason_codes, text


def _build_reason_record(
    *,
    subject_id: str,
    failure_code: str,
    severity: str,
    evidence_count: int,
    recommended_action: str,
) -> dict[str, Any]:
    inputs_payload = {
        "subject_id": subject_id,
        "failure_code": failure_code,
        "severity": severity,
        "evidence_count": evidence_count,
        "recommended_action": recommended_action,
        "min_evidence_for_research_action": MIN_EVIDENCE_FOR_RESEARCH_ACTION,
    }
    digest = compute_inputs_digest(inputs_payload)
    reason_codes, reason_text = _reason_for(
        failure_code=failure_code,
        recommended_action=recommended_action,
        evidence_count=evidence_count,
    )
    return {
        "record_id": compute_record_id(subject_id, failure_code, recommended_action, digest),
        "record_kind": "failure_action_mapping_reason",
        "schema_version": SCHEMA_VERSION,
        "subject_id": subject_id,
        "failure_code": failure_code,
        "recommended_action": recommended_action,
        "reason_codes": reason_codes,
        "reason_text": reason_text,
        "inputs_digest": digest,
    }


def collect_snapshot(
    failures: Sequence[Mapping[str, Any]] | None = None,
    *,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    items_in: Sequence[Mapping[str, Any]] = failures or []
    validate_failures(items_in)
    ts = frozen_utc or _utcnow()

    items: list[dict[str, Any]] = []
    for failure in items_in:
        subject_id = _bounded_subject_id(failure["subject_id"])
        failure_code = str(failure["failure_code"])
        severity = str(failure["severity"])
        evidence_count = _bounded_int(failure["evidence_count"])
        recommended_action = ACTION_BY_FAILURE_CODE[failure_code]
        record = _build_reason_record(
            subject_id=subject_id,
            failure_code=failure_code,
            severity=severity,
            evidence_count=evidence_count,
            recommended_action=recommended_action,
        )
        items.append(
            {
                "subject_id": subject_id,
                "failure_code": failure_code,
                "severity": severity,
                "evidence_count": evidence_count,
                "recommended_action": recommended_action,
                "rank": -1,
                "reason_record": record,
            }
        )

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(
        key=lambda item: (
            severity_rank[item["severity"]],
            item["failure_code"],
            item["subject_id"],
        )
    )
    for rank, item in enumerate(items):
        item["rank"] = rank

    counts_by_action = {action: 0 for action in NEXT_ACTIONS}
    counts_by_failure = {code: 0 for code in FAILURE_CODES}
    for item in items:
        counts_by_action[item["recommended_action"]] += 1
        counts_by_failure[item["failure_code"]] += 1

    actionable_count = sum(
        count
        for action, count in counts_by_action.items()
        if action not in {"hold_no_action", "preserve_negative_result"}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "counts": {
            "total": len(items),
            "by_failure_code": counts_by_failure,
            "by_recommended_action": counts_by_action,
            "actionable_recommendations": actionable_count,
        },
        "items": items,
        "final_recommendation": ("actions_available" if actionable_count else "nothing_actionable"),
        "note": (
            "Minimal v3.15.20 slice. Deterministic Failure to Action "
            "Mapping only; no adaptive feedback loop, no strategy mutation, "
            "no executable strategy generation, and no paper/shadow/live "
            "behavior."
        ),
    }


def screening_attribution_failures(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Convert observed non-strategy screening classes into mapper inputs.

    The adapter is intentionally lossy and read-only: strategy/performance
    screening classes stay in the attribution report, while non-strategy
    diagnostics get mapped into the existing minimal closed taxonomy.
    """

    failures: list[dict[str, Any]] = []
    classifications = payload.get("classifications")
    if not isinstance(classifications, Sequence) or isinstance(classifications, str | bytes):
        return failures
    for row in classifications:
        if not isinstance(row, Mapping):
            continue
        classification = str(row.get("classification") or "")
        failure_code = SCREENING_CLASSIFICATION_TO_FAILURE_CODE.get(classification)
        if failure_code is None:
            continue
        count = _bounded_int(row.get("count"))
        if count <= 0:
            continue
        severity = "high" if failure_code == "unknown_failure" else "medium"
        failures.append(
            {
                "subject_id": f"screening:{classification}",
                "failure_code": failure_code,
                "severity": severity,
                "evidence_count": count,
            }
        )
    return failures


def collect_from_screening_attribution(
    payload: Mapping[str, Any],
    *,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    failures = screening_attribution_failures(payload)
    snapshot = collect_snapshot(failures, frozen_utc=frozen_utc)
    snapshot["source_report_kind"] = "screening_failure_attribution"
    snapshot["source_primary_classification"] = (
        payload.get("summary", {}).get("primary_classification")
        if isinstance(payload.get("summary"), Mapping)
        else None
    )
    return snapshot


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    json_now = base / f"{ts}.json"
    json_latest = base / ARTIFACT_LATEST.name
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    _validate_write_target(json_now)
    _validate_write_target(json_latest)
    _validate_write_target(history)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot(*, artifact_dir: Path | None = None) -> dict[str, Any] | None:
    base = artifact_dir or ARTIFACT_DIR
    path = base / ARTIFACT_LATEST.name
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.failure_action_mapping_minimal",
        description=(
            "Minimal v3.15.20 Failure to Action Mapping. The CLI is "
            "dry-run/read-only unless writing the digest artifact."
        ),
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--mode", choices=("dry-run",), default="dry-run")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            snap = {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "final_recommendation": "not_available",
                "note": "no latest snapshot",
            }
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    snap = collect_snapshot([], frozen_utc=args.frozen_utc)
    if not args.no_write:
        snap["_artifact_paths"] = write_outputs(snap)
    print(json.dumps(snap, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
