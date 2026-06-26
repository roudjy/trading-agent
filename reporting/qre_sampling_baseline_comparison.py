from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_sampling_baseline_comparison"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017q-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_sampling_baseline_comparison")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_sampling_baseline_comparison.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_sampling_baseline_comparison/",
    "docs/governance/qre_sampling_baseline_comparison.md",
)
DEFAULT_SAMPLING_PATH: Final[Path] = Path("logs/qre_sampling_readiness_from_basket/latest.json")
DEFAULT_JOINED_PATH: Final[Path] = Path("logs/qre_routing_sampling_readiness/latest.json")
BASELINE_IDS: Final[tuple[str, ...]] = (
    "current_sampling_score",
    "fifo_artifact_order",
    "routing_score_order",
    "lexical_candidate_id",
    "lexical_behavior_family",
)
STATE_VALUES: Final[frozenset[str]] = frozenset({"ready", "blocked", "deferred", "fail_closed"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_sampling_baseline_comparison: refusing write outside allowlist: {path!r}"
        )


def _source_status(payload: dict[str, Any] | None, *, required_field: str) -> dict[str, Any]:
    if payload is None:
        return {"status": "missing", "required_field": required_field, "fails_closed": True}
    if not isinstance(payload.get(required_field), list):
        return {"status": "invalid", "required_field": required_field, "fails_closed": True}
    return {"status": "ready", "required_field": required_field, "fails_closed": False}


def _max_oos_trades(counts: dict[str, Any]) -> int:
    if int(counts.get("sufficient_oos_evidence") or 0) > 0:
        return 12
    if int(counts.get("insufficient_oos_trades") or 0) > 0:
        return 5
    return 0


def _candidate_record(
    row: dict[str, Any],
    *,
    index: int,
    joined_by_candidate: dict[str, dict[str, Any]],
    max_timeframe_count: int,
) -> dict[str, Any]:
    candidate_id = _text(row.get("candidate_id"))
    joined = joined_by_candidate.get(candidate_id, {})
    validation_counts = dict(row.get("validation_evidence_status_counts") or {})
    timeframe_count = len(list(row.get("timeframes") or []))
    signal_density_proxy = min(1.0, _max_oos_trades(validation_counts) / 12.0)
    sample_adequacy_proxy = min(1.0, float(row.get("sampling_readiness_score_pct") or 0) / 100.0)
    regime_coverage_proxy = min(1.0, timeframe_count / max(1, max_timeframe_count))
    oos_readiness_proxy = (
        1.0
        if int(validation_counts.get("sufficient_oos_evidence") or 0) > 0
        else 0.5
        if bool((row.get("evidence_presence") or {}).get("oos_evidence_known"))
        else 0.0
    )
    failure_discovery_proxy = (
        1.0
        if _text(row.get("sampling_readiness_state")) in {"blocked", "deferred"}
        and bool(joined.get("sampling_reason_record_present"))
        else 0.0
    )
    compute_efficiency_proxy = (
        1.0
        if bool(joined.get("shared_ready"))
        else 0.6
        if _text(row.get("sampling_readiness_state")) == "ready"
        else 0.25
    )
    usefulness = max(
        0.0,
        min(
            1.0,
            0.25 * sample_adequacy_proxy
            + 0.20 * (float(joined.get("routing_score_pct") or 0) / 100.0)
            + 0.20 * signal_density_proxy
            + 0.15 * oos_readiness_proxy
            + 0.10 * regime_coverage_proxy
            + 0.05 * failure_discovery_proxy
            + 0.05 * compute_efficiency_proxy,
        ),
    )
    return {
        "candidate_id": candidate_id,
        "behavior_family": _text(row.get("behavior_family")),
        "sampling_state": _text(row.get("sampling_readiness_state")),
        "sampling_score_pct": int(row.get("sampling_readiness_score_pct") or 0),
        "routing_score_pct": int(joined.get("routing_score_pct") or row.get("routing_readiness_score_pct") or 0),
        "artifact_index": index,
        "timeframe_count": timeframe_count,
        "signal_density_proxy": round(signal_density_proxy, 6),
        "sample_adequacy_proxy": round(sample_adequacy_proxy, 6),
        "regime_coverage_proxy": round(regime_coverage_proxy, 6),
        "oos_readiness_proxy": round(oos_readiness_proxy, 6),
        "failure_discovery_proxy": round(failure_discovery_proxy, 6),
        "compute_efficiency_proxy": round(compute_efficiency_proxy, 6),
        "decision_usefulness_proxy": round(usefulness, 6),
        "shared_ready": bool(joined.get("shared_ready")),
        "sampling_reason_record_present": bool(joined.get("sampling_reason_record_present")),
        "provenance_refs": [
            f"{DEFAULT_SAMPLING_PATH.as_posix()}#rows[{index}]",
            *(
                [f"{DEFAULT_JOINED_PATH.as_posix()}#candidate_examples_top[{joined.get('_row_index')}]"]
                if "_row_index" in joined
                else []
            ),
        ],
    }


def _ranked(rows: list[dict[str, Any]], baseline_id: str) -> list[dict[str, Any]]:
    if baseline_id == "current_sampling_score":
        return sorted(rows, key=lambda row: (-row["sampling_score_pct"], row["candidate_id"]))
    if baseline_id == "fifo_artifact_order":
        return sorted(rows, key=lambda row: row["artifact_index"])
    if baseline_id == "routing_score_order":
        return sorted(rows, key=lambda row: (-row["routing_score_pct"], row["candidate_id"]))
    if baseline_id == "lexical_candidate_id":
        return sorted(rows, key=lambda row: row["candidate_id"])
    if baseline_id == "lexical_behavior_family":
        return sorted(rows, key=lambda row: (row["behavior_family"], row["candidate_id"]))
    raise KeyError(baseline_id)


def _dcg(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for index, row in enumerate(rows, start=1):
        total += float(row["decision_usefulness_proxy"]) / math.log2(index + 1)
    return round(total, 6)


def _baseline_summary(baseline_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = _ranked(rows, baseline_id)
    top3 = ranked[:3]
    return {
        "baseline_id": baseline_id,
        "ranking": [row["candidate_id"] for row in ranked],
        "decision_usefulness_score": _dcg(ranked),
        "top3_signal_density_capture": round(sum(float(row["signal_density_proxy"]) for row in top3), 6),
        "top3_sample_adequacy_capture": round(sum(float(row["sample_adequacy_proxy"]) for row in top3), 6),
        "top3_oos_ready_count": sum(float(row["oos_readiness_proxy"]) >= 1.0 for row in top3),
        "top3_blocker_discovery_count": sum(float(row["failure_discovery_proxy"]) > 0.0 for row in top3),
        "top3_mean_compute_efficiency": round(
            sum(float(row["compute_efficiency_proxy"]) for row in top3) / max(1, len(top3)),
            6,
        ),
        "comparison_scope": "context_only_not_execution_authority",
    }


def build_sampling_baseline_comparison(
    *,
    repo_root: Path | None = None,
    sampling_report: dict[str, Any] | None = None,
    joined_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    sampling_report = sampling_report or _read_json(root / DEFAULT_SAMPLING_PATH)
    joined_report = joined_report or _read_json(root / DEFAULT_JOINED_PATH)
    source_status = {
        "sampling_readiness_from_basket": _source_status(sampling_report, required_field="rows"),
        "routing_sampling_readiness": _source_status(joined_report, required_field="candidate_examples_top"),
    }
    joined_rows = _read_rows(joined_report, "candidate_examples_top")
    joined_by_candidate = {
        _text(row.get("candidate_id")): {**row, "_row_index": index}
        for index, row in enumerate(joined_rows)
        if _text(row.get("candidate_id"))
    }
    sampling_rows = _read_rows(sampling_report, "rows")
    max_timeframe_count = max((len(list(row.get("timeframes") or [])) for row in sampling_rows), default=1)
    candidate_rows = [
        _candidate_record(
            row,
            index=index,
            joined_by_candidate=joined_by_candidate,
            max_timeframe_count=max_timeframe_count,
        )
        for index, row in enumerate(sampling_rows)
    ]
    candidate_rows.sort(key=lambda row: row["candidate_id"])
    baselines = [_baseline_summary(baseline_id, candidate_rows) for baseline_id in BASELINE_IDS]
    baselines.sort(key=lambda row: (-float(row["decision_usefulness_score"]), row["baseline_id"]))
    current = next(row for row in baselines if row["baseline_id"] == "current_sampling_score")
    routing = next(row for row in baselines if row["baseline_id"] == "routing_score_order")
    best = baselines[0]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "source_status": source_status,
        "artifact_references": {
            "sampling_readiness_from_basket": DEFAULT_SAMPLING_PATH.as_posix(),
            "routing_sampling_readiness": DEFAULT_JOINED_PATH.as_posix(),
        },
        "candidate_rows": candidate_rows,
        "baselines": baselines,
        "summary": {
            "candidate_count": len(candidate_rows),
            "baseline_count": len(baselines),
            "current_sampling_score": current["decision_usefulness_score"],
            "best_baseline_id": best["baseline_id"],
            "best_baseline_score": best["decision_usefulness_score"],
            "current_minus_routing_order": round(
                current["decision_usefulness_score"] - routing["decision_usefulness_score"],
                6,
            ),
            "final_recommendation": "sampling_baseline_comparison_ready",
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_sampling": False,
            "can_launch_campaign": False,
            "can_register_strategy": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "context_only_not_authority": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Sampling Baseline Comparison",
        "",
        "This surface compares the current read-only sampling ordering against simple deterministic baselines.",
        "",
        "| baseline_id | usefulness | signal_density_capture | oos_ready_count |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("baselines", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("baseline_id")),
                    f"{float(row.get('decision_usefulness_score') or 0.0):.3f}",
                    f"{float(row.get('top3_signal_density_capture') or 0.0):.3f}",
                    str(int(row.get("top3_oos_ready_count") or 0)),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            f"- source sampling status: `{_text(((report.get('source_status') or {}).get('sampling_readiness_from_basket') or {}).get('status'))}`",
            f"- source joined status: `{_text(((report.get('source_status') or {}).get('routing_sampling_readiness') or {}).get('status'))}`",
            "",
            "Current sampling remains context only and does not authorize campaign execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path.cwd()
    latest = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    doc = root / DOC_PATH
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    for path in (latest, doc):
        _validate_write_target(path)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, latest)
    doc.write_text(render_doc(report), encoding="utf-8")
    return {"latest": latest.relative_to(root).as_posix(), "doc": doc.relative_to(root).as_posix()}


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {"status": "missing", "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(), "fails_closed": True}
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_status(), indent=2, sort_keys=True))
        return 0
    report = build_sampling_baseline_comparison()
    if args.write:
        print(json.dumps(write_outputs(report), indent=2, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
