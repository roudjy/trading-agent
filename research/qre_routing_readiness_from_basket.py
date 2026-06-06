from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_evidence_coverage as coverage


REPORT_KIND: Final[str] = "qre_routing_readiness_from_basket"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_routing_readiness_from_basket")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_routing_readiness_from_basket/"
_STATE_ORDER: Final[tuple[str, ...]] = ("ready", "blocked", "deferred", "fail_closed")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _score_row(row: Mapping[str, Any]) -> int:
    flags = row.get("evidence_presence")
    if not isinstance(flags, Mapping):
        flags = {}
    score = 0
    if str(row.get("diagnosis_class") or "") == "diagnosable":
        score += 25
    if bool(flags.get("source_identity_ready")):
        score += 15
    if bool(flags.get("source_quality_ready")):
        score += 20
    if bool(flags.get("cache_ready")):
        score += 20
    if bool(flags.get("screening_evidence_present")):
        score += 10
    if bool(flags.get("oos_evidence_known")):
        score += 5
    if bool(flags.get("campaign_lineage_present")):
        score += 3
    if bool(flags.get("candidate_lineage_present")):
        score += 2
    return min(score, 100)


def _classify_readiness(row: Mapping[str, Any]) -> tuple[str, str, list[str], bool]:
    missing = [str(value) for value in row.get("missing_evidence_taxonomy") or []]
    diagnosis_class = str(row.get("diagnosis_class") or "unknown_fail_closed")
    if diagnosis_class == "unknown_fail_closed" or "supporting_artifacts_missing" in missing:
        return ("fail_closed", "supporting_artifacts_missing", missing, False)
    if "source_identity_blocked" in missing:
        return ("blocked", "source_identity_blocked", missing, False)
    if "source_quality_not_ready" in missing or "cache_coverage_not_ready" in missing:
        return ("blocked", "source_or_cache_not_ready", missing, False)
    if "source_quality_rows_missing" in missing or "cache_coverage_missing" in missing:
        return ("deferred", "source_or_cache_coverage_missing", missing, False)
    if "screening_evidence_missing" in missing:
        return ("deferred", "screening_evidence_missing", missing, False)
    if "oos_evidence_missing" in missing or "oos_evidence_unknown" in missing:
        return ("deferred", "oos_evidence_missing", missing, False)
    if "campaign_lineage_missing" in missing and "candidate_lineage_missing" in missing:
        return ("deferred", "lineage_missing", missing, False)
    return ("ready", "evidence_ready_for_readonly_routing", missing, True)


def build_routing_readiness_from_basket(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    base = coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    source_rows = base.get("rows")
    if not isinstance(source_rows, list):
        source_rows = []

    rows: list[dict[str, Any]] = []
    for row in source_rows:
        if not isinstance(row, Mapping):
            continue
        state, primary_reason, supporting_reasons, routing_ready = _classify_readiness(row)
        score = _score_row(row)
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "symbol": row.get("symbol"),
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "behavior_family": row.get("behavior_family"),
                "timeframes": list(row.get("timeframes") or []),
                "diagnosis_class": row.get("diagnosis_class"),
                "evidence_completeness_score_pct": int(
                    row.get("evidence_completeness_score_pct") or 0
                ),
                "routing_readiness_state": state,
                "routing_readiness_score_pct": score,
                "routing_ready": routing_ready,
                "primary_reason_code": primary_reason,
                "supporting_reason_codes": supporting_reasons,
                "follow_up": (
                    "eligible_for_readonly_routing"
                    if routing_ready
                    else row.get("follow_up") or "keep_fail_closed"
                ),
                "source_identity_status": row.get("source_identity_status"),
                "provider_symbol_status": row.get("provider_symbol_status"),
                "evidence_presence": dict(row.get("evidence_presence") or {}),
                "validation_evidence_status_counts": dict(
                    row.get("validation_evidence_status_counts") or {}
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            _STATE_ORDER.index(str(row["routing_readiness_state"])),
            -int(row["routing_readiness_score_pct"]),
            str(row["symbol"]),
            str(row["preset_id"]),
        )
    )
    state_counts = Counter(str(row["routing_readiness_state"]) for row in rows)
    ready_count = state_counts.get("ready", 0)
    deferred_count = state_counts.get("deferred", 0)
    blocked_count = state_counts.get("blocked", 0)
    fail_closed_count = state_counts.get("fail_closed", 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "basket_source": base.get("basket_source"),
        "max_candidates": max_candidates,
        "summary": {
            "basket_inventory_count": len(rows),
            "routing_readiness_state_counts": {
                key: state_counts.get(key, 0) for key in _STATE_ORDER
            },
            "routing_ready_count": ready_count,
            "routing_blocked_count": blocked_count,
            "routing_deferred_count": deferred_count,
            "routing_fail_closed_count": fail_closed_count,
            "evidence_backed_zero_ready": ready_count == 0
            and (deferred_count > 0 or blocked_count > 0 or fail_closed_count > 0),
            "final_recommendation": (
                "nothing_ready_evidence_backed"
                if ready_count == 0
                else "read_only_routing_ready_items_present"
            ),
            "operator_summary": (
                "Routing readiness is a read-only projection from real basket evidence. "
                "Baskets are only routing-ready when source identity, source/cache "
                "readiness, and screening/OOS evidence are all explicitly present."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "queue_integration": False,
            "campaign_enqueue": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    counts = summary.get("routing_readiness_state_counts") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket inventory", str(summary.get("basket_inventory_count") or 0)],
            ["ready", str(counts.get("ready") or 0)],
            ["blocked", str(counts.get("blocked") or 0)],
            ["deferred", str(counts.get("deferred") or 0)],
            ["fail closed", str(counts.get("fail_closed") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "State",
            "Score",
            "Primary reason",
            "Diagnosis",
            "Follow-up",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("routing_readiness_state") or ""),
                str(row.get("routing_readiness_score_pct") or 0),
                str(row.get("primary_reason_code") or ""),
                str(row.get("diagnosis_class") or ""),
                str(row.get("follow_up") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Routing Readiness From Basket Evidence",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Routing readiness counts",
            count_table,
            "",
            "## 3. Routing readiness by basket",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_routing_readiness_from_basket: refusing write outside allowlist: {path!r}"
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
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_routing_readiness_from_basket",
        description="Build read-only routing readiness from real basket evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_routing_readiness_from_basket(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
