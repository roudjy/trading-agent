from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_evidence_density_materialization as density
from research import qre_basket_lineage_recovery_diagnostics as lineage_diag
from research import qre_discovery_source_identity_diagnostics as identity_diag
from research import qre_evidence_complete_basket_closure as closure
from research import qre_real_basket_evidence_coverage as coverage


REPORT_KIND: Final[str] = "qre_basket_evidence_recovery_plan"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_evidence_recovery_plan")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_evidence_recovery_plan/"

_BLOCKER_PRIORITY: Final[dict[str, int]] = {
    "source_identity_blocked": 0,
    "source_quality_rows_missing": 1,
    "source_quality_not_ready": 1,
    "cache_coverage_missing": 1,
    "cache_coverage_not_ready": 1,
    "campaign_lineage_missing": 2,
    "candidate_lineage_missing": 2,
    "screening_evidence_missing": 3,
    "oos_evidence_missing": 4,
    "oos_evidence_unknown": 4,
    "no_oos_evidence": 4,
    "insufficient_oos_evidence": 4,
}

_BLOCKER_FAMILY: Final[dict[str, str]] = {
    "source_identity_blocked": "identity",
    "source_quality_rows_missing": "source_cache",
    "source_quality_not_ready": "source_cache",
    "cache_coverage_missing": "source_cache",
    "cache_coverage_not_ready": "source_cache",
    "campaign_lineage_missing": "lineage",
    "candidate_lineage_missing": "lineage",
    "screening_evidence_missing": "screening",
    "oos_evidence_missing": "oos",
    "oos_evidence_unknown": "oos",
    "no_oos_evidence": "oos",
    "insufficient_oos_evidence": "oos",
}

_BLOCKER_ACTION: Final[dict[str, str]] = {
    "source_identity_blocked": "require_identity_resolution",
    "source_quality_rows_missing": "expand_basket_coverage",
    "source_quality_not_ready": "expand_basket_coverage",
    "cache_coverage_missing": "expand_basket_coverage",
    "cache_coverage_not_ready": "expand_basket_coverage",
    "campaign_lineage_missing": "materialize_lineage_from_existing_artifacts",
    "candidate_lineage_missing": "materialize_lineage_from_existing_artifacts",
    "screening_evidence_missing": "collect_screening_evidence",
    "oos_evidence_missing": "collect_oos_evidence",
    "oos_evidence_unknown": "collect_oos_evidence",
    "no_oos_evidence": "collect_oos_evidence",
    "insufficient_oos_evidence": "collect_oos_evidence",
}

_BLOCKER_ARTIFACTS: Final[dict[str, tuple[str, ...]]] = {
    "source_identity_blocked": (
        "research/production_discovery_catalog.py",
        "logs/qre_discovery_source_identity_diagnostics/latest.json",
    ),
    "source_quality_rows_missing": (
        "logs/qre_data_source_quality_readiness/latest.json",
        "logs/qre_data_cache_manifest/latest.json",
    ),
    "source_quality_not_ready": (
        "logs/qre_data_source_quality_readiness/latest.json",
        "logs/qre_data_cache_manifest/latest.json",
    ),
    "cache_coverage_missing": (
        "logs/qre_data_cache_manifest/latest.json",
        "logs/qre_data_source_quality_readiness/latest.json",
    ),
    "cache_coverage_not_ready": (
        "logs/qre_data_cache_manifest/latest.json",
        "logs/qre_data_source_quality_readiness/latest.json",
    ),
    "campaign_lineage_missing": (
        "logs/qre_discovery_basket_grid_evidence_materialization/latest.json",
        "logs/qre_grid_candidate_campaign_lineage_bridge/latest.json",
    ),
    "candidate_lineage_missing": (
        "logs/qre_discovery_basket_grid_evidence_materialization/latest.json",
        "logs/qre_grid_candidate_campaign_lineage_bridge/latest.json",
    ),
    "screening_evidence_missing": (
        "research/screening_evidence_latest.v1.json",
        "logs/qre_real_basket_evidence_coverage/latest.json",
    ),
    "oos_evidence_missing": (
        "research/screening_evidence_latest.v1.json",
        "logs/qre_hypothesis_validation_results/latest.json",
        "logs/qre_real_basket_evidence_coverage/latest.json",
    ),
    "oos_evidence_unknown": (
        "research/screening_evidence_latest.v1.json",
        "logs/qre_hypothesis_validation_results/latest.json",
        "logs/qre_real_basket_evidence_coverage/latest.json",
    ),
    "no_oos_evidence": (
        "research/screening_evidence_latest.v1.json",
        "logs/qre_hypothesis_validation_results/latest.json",
        "logs/qre_real_basket_evidence_coverage/latest.json",
    ),
    "insufficient_oos_evidence": (
        "research/screening_evidence_latest.v1.json",
        "logs/qre_hypothesis_validation_results/latest.json",
        "logs/qre_real_basket_evidence_coverage/latest.json",
    ),
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _index_by_candidate(rows: Sequence[Mapping[str, Any]], *, key: str = "candidate_id") -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        subject_id = str(row.get(key) or "")
        if subject_id and subject_id not in indexed:
            indexed[subject_id] = dict(row)
    return indexed


def _dedupe_refs(*groups: Sequence[Any]) -> list[str]:
    refs: list[str] = []
    for group in groups:
        if not isinstance(group, Sequence) or isinstance(group, str | bytes):
            continue
        for value in group:
            text = str(value or "").strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _blocker_profile(
    *,
    blocker_code: str,
    candidate_row: Mapping[str, Any],
    coverage_row: Mapping[str, Any],
    density_row: Mapping[str, Any],
    lineage_row: Mapping[str, Any],
    identity_row: Mapping[str, Any],
) -> dict[str, Any]:
    family = _BLOCKER_FAMILY.get(blocker_code, "unknown")
    exact_next_action = _BLOCKER_ACTION.get(blocker_code, "operator_review")
    artifact_refs = list(_BLOCKER_ARTIFACTS.get(blocker_code, ("research/production_discovery_catalog.py",)))
    if blocker_code in {"source_quality_rows_missing", "source_quality_not_ready"}:
        artifact_refs = _dedupe_refs(
            density_row.get("source_quality_refs") or artifact_refs,
            artifact_refs,
        )
    elif blocker_code in {"cache_coverage_missing", "cache_coverage_not_ready"}:
        artifact_refs = _dedupe_refs(
            density_row.get("cache_coverage_refs") or artifact_refs,
            artifact_refs,
        )
    elif blocker_code == "screening_evidence_missing":
        artifact_refs = _dedupe_refs(
            density_row.get("screening_evidence_refs") or artifact_refs,
            artifact_refs,
        )
    elif blocker_code in {
        "oos_evidence_missing",
        "oos_evidence_unknown",
        "no_oos_evidence",
        "insufficient_oos_evidence",
    }:
        artifact_refs = _dedupe_refs(
            density_row.get("oos_evidence_refs") or artifact_refs,
            artifact_refs,
        )
    elif blocker_code in {"campaign_lineage_missing", "candidate_lineage_missing"}:
        artifact_refs = _dedupe_refs(
            density_row.get("candidate_lineage_refs") or [],
            density_row.get("campaign_lineage_refs") or [],
            lineage_row.get("proof_source_refs", {}).get("density") if isinstance(lineage_row.get("proof_source_refs"), Mapping) else [],
            artifact_refs,
        )
    elif blocker_code == "source_identity_blocked":
        artifact_refs = _dedupe_refs(
            artifact_refs,
        )
    recoverable = False
    if blocker_code == "source_identity_blocked":
        recoverable = bool(identity_row) and bool(identity_row.get("is_provider_symbol_verified"))
    elif blocker_code in {"source_quality_rows_missing", "source_quality_not_ready"}:
        recoverable = int(density_row.get("source_quality_rows") or 0) > 0 and int(
            density_row.get("cache_coverage_rows") or 0
        ) > 0
    elif blocker_code in {"cache_coverage_missing", "cache_coverage_not_ready"}:
        recoverable = int(density_row.get("cache_coverage_rows") or 0) > 0 and int(
            density_row.get("source_quality_rows") or 0
        ) > 0
    elif blocker_code in {"campaign_lineage_missing", "candidate_lineage_missing"}:
        recoverable = str(lineage_row.get("candidate_lineage_proof_status") or "") in {
            "lineage_visible",
            "candidate_proven_campaign_missing",
        }
        recoverable = recoverable or str(lineage_row.get("campaign_lineage_proof_status") or "") == "proven"
    elif blocker_code == "screening_evidence_missing":
        recoverable = int(density_row.get("screening_evidence_rows") or 0) > 0
    elif blocker_code in {
        "oos_evidence_missing",
        "oos_evidence_unknown",
        "no_oos_evidence",
        "insufficient_oos_evidence",
    }:
        recoverable = str(density_row.get("oos_evidence_status") or "") in {
            "sufficient_oos_evidence",
            "insufficient_oos_evidence",
        }
    return {
        "blocker_code": blocker_code,
        "blocker_family": family,
        "recovery_class": "reducible" if recoverable else "irreducible",
        "exact_next_action": exact_next_action,
        "required_artifact": "; ".join(artifact_refs),
        "potential_clear_refs": artifact_refs,
        "blocked_by_identity": family == "identity",
        "blocked_by_source_cache": family == "source_cache",
        "blocked_by_lineage": family == "lineage",
        "blocked_by_screening": family == "screening",
        "blocked_by_oos": family == "oos",
        "lineage_proof_status": str(lineage_row.get("candidate_lineage_proof_status") or "gap"),
        "campaign_lineage_proof_status": str(lineage_row.get("campaign_lineage_proof_status") or "gap"),
        "lineage_recovery_reason": str(lineage_row.get("lineage_recovery_reason") or ""),
        "current_status": str(coverage_row.get("evidence_completeness_status") or "missing"),
        "allowed_to_auto_run": False,
        "safe_action_type": "report_only",
        "operator_explanation": (
            f"{candidate_row.get('symbol')} remains blocked by {blocker_code}; "
            f"the bounded next action is {exact_next_action}."
        ),
    }


def _candidate_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_basket_evidence_recovery_plan(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    density_report = density.build_basket_evidence_density_materialization(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    lineage_report = lineage_diag.build_basket_lineage_recovery_diagnostics(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    coverage_report = coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    closure_report = closure.build_evidence_complete_basket_closure(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    identity_report = identity_diag.build_source_identity_diagnostics(max_candidates=max_candidates)

    density_rows = _index_by_candidate(_candidate_rows(density_report))
    lineage_rows = _index_by_candidate(_candidate_rows(lineage_report))
    coverage_rows = _index_by_candidate(_candidate_rows(coverage_report))
    closure_rows = _index_by_candidate(_candidate_rows(closure_report))
    identity_rows = {
        str(row.get("instrument_symbol") or ""): row
        for row in _candidate_rows(identity_report)
    }

    candidate_ids = sorted(
        {
            *density_rows.keys(),
            *coverage_rows.keys(),
            *closure_rows.keys(),
        }
    )

    rows: list[dict[str, Any]] = []
    blocker_rows: list[dict[str, Any]] = []
    blocker_counts: Counter[str] = Counter()
    recovery_class_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()

    for candidate_id in candidate_ids:
        density_row = density_rows.get(candidate_id, {})
        lineage_row = lineage_rows.get(candidate_id, {})
        coverage_row = coverage_rows.get(candidate_id, {})
        closure_row = closure_rows.get(candidate_id, {})
        symbol = str(
            closure_row.get("symbol")
            or coverage_row.get("symbol")
            or density_row.get("symbol")
            or ""
        )
        identity_row = identity_rows.get(symbol, {})
        blocker_codes = list(closure_row.get("exact_blockers") or [])
        if not blocker_codes:
            blocker_codes = list(coverage_row.get("missing_evidence_taxonomy") or [])
        blocker_codes = list(dict.fromkeys(blocker_codes))
        blocker_records: list[dict[str, Any]] = []
        reducible_count = 0
        irreducible_count = 0
        next_actions: list[str] = []
        for blocker_code in blocker_codes:
            record = _blocker_profile(
                blocker_code=blocker_code,
                candidate_row=closure_row or coverage_row or density_row,
                coverage_row=coverage_row,
                density_row=density_row,
                lineage_row=lineage_row,
                identity_row=identity_row,
            )
            blocker_records.append(record)
            blocker_rows.append(
                {
                    "candidate_id": candidate_id,
                    "symbol": symbol,
                    "preset_id": str(
                        closure_row.get("preset_id")
                        or coverage_row.get("preset_id")
                        or density_row.get("preset_id")
                        or ""
                    ),
                    "hypothesis_id": str(
                        closure_row.get("hypothesis_id")
                        or coverage_row.get("hypothesis_id")
                        or density_row.get("hypothesis_id")
                        or ""
                    ),
                    "behavior_family": str(
                        closure_row.get("behavior_family")
                        or coverage_row.get("behavior_family")
                        or density_row.get("behavior_family")
                        or ""
                    ),
                    "region": str(
                        closure_row.get("region")
                        or coverage_row.get("region")
                        or density_row.get("region")
                        or ""
                    ),
                    "asset_class": str(
                        closure_row.get("asset_class")
                        or coverage_row.get("asset_class")
                        or density_row.get("asset_class")
                        or ""
                    ),
                    "timeframes": list(
                        closure_row.get("timeframes")
                        or coverage_row.get("timeframes")
                        or density_row.get("timeframes")
                        or []
                    ),
                    **record,
                    "reason_record_refs": {
                        "record_ids": list(closure_row.get("reason_record_ids") or []),
                        "record_families": list(closure_row.get("reason_record_families") or []),
                        "evidence_refs": list(closure_row.get("reason_record_evidence_refs") or []),
                    },
                }
            )
            blocker_counts.update([blocker_code])
            action_counts.update([record["exact_next_action"]])
            recovery_class_counts.update([record["recovery_class"]])
            if record["recovery_class"] == "reducible":
                reducible_count += 1
            else:
                irreducible_count += 1
            if record["exact_next_action"] not in next_actions:
                next_actions.append(record["exact_next_action"])
        rows.append(
            {
                "candidate_id": candidate_id,
                "symbol": symbol,
                "preset_id": str(
                    closure_row.get("preset_id")
                    or coverage_row.get("preset_id")
                    or density_row.get("preset_id")
                    or ""
                ),
                "hypothesis_id": str(
                    closure_row.get("hypothesis_id")
                    or coverage_row.get("hypothesis_id")
                    or density_row.get("hypothesis_id")
                    or ""
                ),
                "behavior_family": str(
                    closure_row.get("behavior_family")
                    or coverage_row.get("behavior_family")
                    or density_row.get("behavior_family")
                    or ""
                ),
                "region": str(
                    closure_row.get("region")
                    or coverage_row.get("region")
                    or density_row.get("region")
                    or ""
                ),
                "asset_class": str(
                    closure_row.get("asset_class")
                    or coverage_row.get("asset_class")
                    or density_row.get("asset_class")
                    or ""
                ),
                "timeframes": list(
                    closure_row.get("timeframes")
                    or coverage_row.get("timeframes")
                    or density_row.get("timeframes")
                    or []
                ),
                "closure_status": str(closure_row.get("closure_status") or "blocked_not_evidence_complete"),
                "evidence_completeness_status": str(
                    coverage_row.get("evidence_completeness_status") or "missing"
                ),
                "evidence_completeness_score_pct": int(
                    coverage_row.get("evidence_completeness_score_pct") or 0
                ),
                "blocker_count": len(blocker_records),
                "reducible_blocker_count": reducible_count,
                "irreducible_blocker_count": irreducible_count,
                "blockers": blocker_records,
                "exact_next_actions": next_actions,
                "reason_record_count": int(closure_row.get("reason_record_count") or 0),
                "reason_record_ids": list(closure_row.get("reason_record_ids") or []),
                "reason_record_evidence_refs": list(
                    closure_row.get("reason_record_evidence_refs") or []
                ),
                "failure_action": dict(closure_row.get("failure_action") or {}),
                "density_evidence_refs": {
                    "source_quality": list(density_row.get("source_quality_refs") or []),
                    "cache_coverage": list(density_row.get("cache_coverage_refs") or []),
                    "screening": list(density_row.get("screening_evidence_refs") or []),
                    "oos": list(density_row.get("oos_evidence_refs") or []),
                    "candidate_lineage": list(density_row.get("candidate_lineage_refs") or []),
                    "campaign_lineage": list(density_row.get("campaign_lineage_refs") or []),
                },
                "lineage_diagnostic": dict(lineage_row),
                "operator_explanation": (
                    f"{symbol} remains blocked by {', '.join(blocker_codes) or 'no recorded blockers'}; "
                    f"recoverable actions are {', '.join(next_actions) or 'none'}."
                ),
            }
        )

    rows.sort(key=lambda row: (str(row["symbol"]), str(row["preset_id"])))
    blocker_rows.sort(
        key=lambda row: (
            _BLOCKER_PRIORITY.get(str(row.get("blocker_code") or ""), 99),
            str(row.get("symbol") or ""),
            str(row.get("preset_id") or ""),
            str(row.get("blocker_code") or ""),
        )
    )
    closure_summary = closure_report.get("summary") if isinstance(closure_report, Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(rows),
            "blocker_row_count": len(blocker_rows),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "reducible_blocker_count": sum(
                1 for row in blocker_rows if str(row.get("recovery_class") or "") == "reducible"
            ),
            "irreducible_blocker_count": sum(
                1 for row in blocker_rows if str(row.get("recovery_class") or "") != "reducible"
            ),
            "blocker_recovery_class_counts": dict(sorted(recovery_class_counts.items())),
            "exact_next_action_counts": dict(sorted(action_counts.items())),
            "evidence_complete_count": int(closure_summary.get("evidence_complete_count") or 0),
            "lineage_diagnostic_row_count": len(lineage_rows),
            "lineage_proven_candidate_count": sum(
                1
                for row in lineage_rows.values()
                if str(row.get("candidate_lineage_proof_status") or "") in {
                    "lineage_visible",
                    "candidate_proven_campaign_missing",
                }
            ),
            "lineage_proven_campaign_count": sum(
                1
                for row in lineage_rows.values()
                if str(row.get("campaign_lineage_proof_status") or "") == "proven"
            ),
            "final_recommendation": (
                "basket_evidence_recovery_plan_ready" if rows else "basket_evidence_recovery_plan_missing"
            ),
            "operator_summary": (
                "Read-only basket evidence recovery keeps missing evidence explicit, classifies "
                "remaining blockers, and records the bounded next action for each unresolved blocker."
            ),
        },
        "rows": rows,
        "blocker_rows": blocker_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_queues": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    blocker_rows = report.get("blocker_rows") if isinstance(report.get("blocker_rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket count", str(summary.get("basket_count") or 0)],
            ["blocker rows", str(summary.get("blocker_row_count") or 0)],
            ["reducible blockers", str(summary.get("reducible_blocker_count") or 0)],
            ["irreducible blockers", str(summary.get("irreducible_blocker_count") or 0)],
            ["evidence complete baskets", str(summary.get("evidence_complete_count") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Blockers",
            "Actions",
            "Reducible",
            "Irreducible",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                ", ".join(str(item.get("blocker_code") or "") for item in row.get("blockers") or []),
                ", ".join(str(value) for value in row.get("exact_next_actions") or []),
                str(row.get("reducible_blocker_count") or 0),
                str(row.get("irreducible_blocker_count") or 0),
            ]
            for row in rows
        ],
    )
    blocker_table = _table(
        ["Symbol", "Blocker", "Recovery", "Next action", "Artifact"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("blocker_code") or ""),
                str(row.get("recovery_class") or ""),
                str(row.get("exact_next_action") or ""),
                str(row.get("required_artifact") or ""),
            ]
            for row in blocker_rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Evidence Recovery Plan",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Blocker counts",
            count_table,
            "",
            "## 3. Basket recovery matrix",
            basket_table,
            "",
            "## 4. Blocker rows",
            blocker_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_basket_evidence_recovery_plan: refusing write outside allowlist: {path!r}"
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
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_basket_evidence_recovery_plan",
        description="Build a read-only basket evidence recovery plan.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_evidence_recovery_plan(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
