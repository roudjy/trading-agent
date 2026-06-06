from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_diagnosis as diagnosis


REPORT_KIND: Final[str] = "qre_real_basket_evidence_coverage"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_real_basket_evidence_coverage")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_real_basket_evidence_coverage/"
_COMPLETENESS_FIELDS: Final[tuple[str, ...]] = (
    "source_identity_ready",
    "source_quality_ready",
    "cache_ready",
    "screening_evidence_present",
    "oos_evidence_known",
    "campaign_lineage_present",
    "candidate_lineage_present",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _validation_statuses(screening_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for row in screening_rows:
        payload = row.get("validation_evidence")
        if not isinstance(payload, Mapping):
            statuses.append("unknown")
            continue
        status = str(payload.get("status") or "unknown")
        statuses.append(status)
    return statuses


def _oos_trade_count(screening_rows: Sequence[Mapping[str, Any]]) -> int:
    best = 0
    for row in screening_rows:
        payload = row.get("validation_evidence")
        if not isinstance(payload, Mapping):
            continue
        value = payload.get("oos_trade_count")
        if isinstance(value, int | float):
            best = max(best, int(value))
    return best


def _missing_evidence_taxonomy(
    *,
    diagnosis_class: str,
    reason_code: str,
    provider_symbol_status: str,
    source_quality_rows: int,
    source_quality_ready: bool,
    cache_rows: int,
    cache_ready: bool,
    screening_rows: int,
    validation_statuses: Sequence[str],
    campaign_rows: int,
    candidate_rows: int,
) -> list[str]:
    missing: list[str] = []
    if diagnosis_class == "unknown_fail_closed":
        missing.append("supporting_artifacts_missing")
    if provider_symbol_status == "candidate_alias_requires_verification" or reason_code.startswith(
        "source_identity"
    ):
        missing.append("source_identity_blocked")
    if source_quality_rows == 0:
        missing.append("source_quality_rows_missing")
    elif not source_quality_ready:
        missing.append("source_quality_not_ready")
    if cache_rows == 0:
        missing.append("cache_coverage_missing")
    elif not cache_ready:
        missing.append("cache_coverage_not_ready")
    if screening_rows == 0:
        missing.append("screening_evidence_missing")
    if not validation_statuses:
        missing.append("oos_evidence_missing")
    elif all(status in {"unknown", "None", ""} for status in validation_statuses):
        missing.append("oos_evidence_unknown")
    elif all(status == "no_oos_trades" for status in validation_statuses):
        missing.append("no_oos_evidence")
    elif all(status == "insufficient_oos_trades" for status in validation_statuses):
        missing.append("insufficient_oos_evidence")
    if campaign_rows == 0:
        missing.append("campaign_lineage_missing")
    if candidate_rows == 0:
        missing.append("candidate_lineage_missing")
    return missing


def _completeness_flags(
    *,
    row: Mapping[str, Any],
    validation_statuses: Sequence[str],
) -> dict[str, bool]:
    evidence = row.get("current_evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    source_status_counts = evidence.get("source_quality_status_counts")
    if not isinstance(source_status_counts, Mapping):
        source_status_counts = {}
    return {
        "source_identity_ready": str(row.get("provider_symbol_status") or "") == "verified",
        "source_quality_ready": bool(evidence.get("source_quality_rows"))
        and "blocked" not in {str(key) for key in source_status_counts.keys()},
        "cache_ready": bool(evidence.get("cache_coverage_rows"))
        and int(evidence.get("cache_ready_count") or 0)
        >= int(evidence.get("cache_coverage_rows") or 0),
        "screening_evidence_present": int(evidence.get("screening_rows") or 0) > 0,
        "oos_evidence_known": bool(validation_statuses)
        and any(status not in {"unknown", "None", ""} for status in validation_statuses),
        "campaign_lineage_present": int(evidence.get("campaign_rows") or 0) > 0,
        "candidate_lineage_present": int(evidence.get("candidate_rows") or 0) > 0,
    }


def _completeness_status(score_pct: int) -> str:
    if score_pct >= 85:
        return "complete"
    if score_pct >= 55:
        return "partial"
    if score_pct > 0:
        return "thin"
    return "missing"


def build_real_basket_evidence_coverage(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    supporting_artifacts = diagnosis._load_supporting_artifacts(repo_root=repo_root)  # type: ignore[attr-defined]
    base = diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = base.get("rows")
    if not isinstance(rows, list):
        rows = []

    coverage_rows: list[dict[str, Any]] = []
    taxonomy_counter: Counter[str] = Counter()
    completeness_counter: Counter[str] = Counter()
    evidence_backed_zero = True

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        evidence = row.get("current_evidence")
        if not isinstance(evidence, Mapping):
            evidence = {}
        screening_rows = diagnosis._matching_screening_rows(  # type: ignore[attr-defined]
            supporting_artifacts.get("screening_evidence"),
            symbol=str(row.get("symbol") or ""),
            hypothesis_id=str(row.get("hypothesis_id") or ""),
        )
        validation_statuses = _validation_statuses(screening_rows)
        flags = _completeness_flags(row=row, validation_statuses=validation_statuses)
        score = round(100 * sum(flags.values()) / len(_COMPLETENESS_FIELDS))
        status = _completeness_status(score)
        missing = _missing_evidence_taxonomy(
            diagnosis_class=str(row.get("diagnosis_class") or "unknown_fail_closed"),
            reason_code=str(row.get("reason_code") or "unknown"),
            provider_symbol_status=str(row.get("provider_symbol_status") or "unknown"),
            source_quality_rows=int(evidence.get("source_quality_rows") or 0),
            source_quality_ready=flags["source_quality_ready"],
            cache_rows=int(evidence.get("cache_coverage_rows") or 0),
            cache_ready=flags["cache_ready"],
            screening_rows=int(evidence.get("screening_rows") or 0),
            validation_statuses=validation_statuses,
            campaign_rows=int(evidence.get("campaign_rows") or 0),
            candidate_rows=int(evidence.get("candidate_rows") or 0),
        )
        if flags["screening_evidence_present"] or flags["oos_evidence_known"]:
            evidence_backed_zero = False
        taxonomy_counter.update(missing)
        completeness_counter.update([status])
        coverage_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "symbol": row.get("symbol"),
                "provider_symbol": row.get("provider_symbol"),
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "behavior_family": row.get("behavior_family"),
                "timeframes": list(row.get("timeframes") or []),
                "diagnosis_class": row.get("diagnosis_class"),
                "diagnosis_reason_code": row.get("reason_code"),
                "source_identity_status": row.get("source_identity_status"),
                "provider_symbol_status": row.get("provider_symbol_status"),
                "evidence_counts": {
                    "campaign_lineage_rows": int(evidence.get("campaign_rows") or 0),
                    "candidate_lineage_rows": int(evidence.get("candidate_rows") or 0),
                    "screening_rows": int(evidence.get("screening_rows") or 0),
                    "source_quality_rows": int(evidence.get("source_quality_rows") or 0),
                    "cache_coverage_rows": int(evidence.get("cache_coverage_rows") or 0),
                    "cache_ready_rows": int(evidence.get("cache_ready_count") or 0),
                    "oos_trade_count_max": _oos_trade_count(screening_rows),
                },
                "screening_stage_result_counts": dict(
                    evidence.get("screening_stage_result_counts") or {}
                ),
                "validation_evidence_status_counts": dict(
                    Counter(validation_statuses)
                ),
                "evidence_presence": flags,
                "evidence_completeness_score_pct": score,
                "evidence_completeness_status": status,
                "missing_evidence_taxonomy": missing,
                "follow_up": (
                    "eligible_for_readonly_routing"
                    if score >= 85
                    and str(row.get("diagnosis_class")) == "diagnosable"
                    and not missing
                    else "require_identity_resolution"
                    if "source_identity_blocked" in missing
                    else "collect_more_evidence"
                    if "screening_evidence_missing" in missing
                    or "oos_evidence_missing" in missing
                    or "oos_evidence_unknown" in missing
                    else "require_source_readiness"
                    if "source_quality_rows_missing" in missing
                    or "source_quality_not_ready" in missing
                    or "cache_coverage_missing" in missing
                    or "cache_coverage_not_ready" in missing
                    else "keep_fail_closed"
                ),
            }
        )

    coverage_rows.sort(
        key=lambda row: (
            -int(row["evidence_completeness_score_pct"]),
            str(row["symbol"]),
            str(row["preset_id"]),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "basket_source": base.get("basket_source"),
        "max_candidates": max_candidates,
        "summary": {
            "basket_inventory_count": len(coverage_rows),
            "diagnosis_class_counts": dict(
                Counter(str(row["diagnosis_class"]) for row in coverage_rows)
            ),
            "evidence_completeness_status_counts": dict(completeness_counter),
            "missing_evidence_taxonomy_counts": dict(sorted(taxonomy_counter.items())),
            "screening_evidence_rows_total": sum(
                int(row["evidence_counts"]["screening_rows"]) for row in coverage_rows
            ),
            "sufficient_oos_evidence_rows_total": sum(
                int(row["validation_evidence_status_counts"].get("sufficient_oos_evidence") or 0)
                for row in coverage_rows
            ),
            "evidence_backed_zero_screening": evidence_backed_zero,
            "operator_summary": (
                "Real basket evidence coverage maps each production discovery basket to "
                "lineage, screening, OOS, source, and cache readiness without mutating "
                "campaigns or promotion state."
            ),
        },
        "rows": coverage_rows,
        "safety_invariants": dict(base.get("safety_invariants") or {}),
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    counts = summary.get("evidence_completeness_status_counts") or {}
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket inventory", str(summary.get("basket_inventory_count") or 0)],
            ["complete", str(counts.get("complete") or 0)],
            ["partial", str(counts.get("partial") or 0)],
            ["thin", str(counts.get("thin") or 0)],
            ["missing", str(counts.get("missing") or 0)],
            [
                "sufficient OOS rows",
                str(summary.get("sufficient_oos_evidence_rows_total") or 0),
            ],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Diagnosis",
            "Coverage",
            "Score",
            "OOS",
            "Source",
            "Cache",
            "Missing",
            "Follow-up",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("diagnosis_class") or ""),
                str(row.get("evidence_completeness_status") or ""),
                str(row.get("evidence_completeness_score_pct") or 0),
                ",".join(
                    sorted(
                        str(key)
                        for key, value in (row.get("validation_evidence_status_counts") or {}).items()
                        if int(value or 0) > 0
                    )
                )
                or "none",
                "ready" if (row.get("evidence_presence") or {}).get("source_quality_ready") else "blocked",
                "ready" if (row.get("evidence_presence") or {}).get("cache_ready") else "blocked",
                ",".join(str(value) for value in row.get("missing_evidence_taxonomy") or [])
                or "none",
                str(row.get("follow_up") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Real Basket Evidence Coverage",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Evidence completeness counts",
            count_table,
            "",
            "## 3. Basket evidence coverage",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_real_basket_evidence_coverage: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_real_basket_evidence_coverage",
        description="Build read-only basket evidence coverage over the discovery seed.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_real_basket_evidence_coverage(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
