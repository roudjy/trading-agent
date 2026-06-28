from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_broad_campaign_funnel_diagnosis"
MODULE_VERSION: Final[str] = "ade-qre-017z-2026-06-28"

DEFAULT_EXECUTION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_execution" / "latest.json"
DEFAULT_PORTFOLIO_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_campaign_portfolio_plan" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_funnel_diagnosis"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_broad_campaign_funnel_diagnosis.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_broad_campaign_funnel_diagnosis/",
    "docs/governance/qre_broad_campaign_funnel_diagnosis.md",
)
ALLOWED_RECOMMENDATIONS: Final[tuple[str, ...]] = (
    "keep",
    "stratify",
    "move_to_later_stage",
    "replace",
    "remove_as_redundant",
    "insufficient_evidence_to_change",
)
CRITERIA: Final[tuple[str, ...]] = (
    "data_breadth",
    "data_quality",
    "source_authority",
    "identity_ambiguity",
    "hypothesis_diversity",
    "signal_density",
    "sample_adequacy",
    "window_design",
    "screening",
    "validation",
    "oos_acceptance",
    "null_controls",
    "evidence_completeness",
    "repeated_dead_zones",
    "genuine_absence_of_edge",
)
PRIMARY_ORDER: Final[tuple[str, ...]] = (
    "evidence_completeness",
    "oos_acceptance",
    "null_controls",
    "identity_ambiguity",
    "source_authority",
    "repeated_dead_zones",
    "genuine_absence_of_edge",
    "signal_density",
    "sample_adequacy",
    "window_design",
    "data_breadth",
    "data_quality",
    "hypothesis_diversity",
    "screening",
    "validation",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _stable_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_write_target(path: Path) -> None:
    normalized = _rel(path)
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _criterion_for_reason(reason: str) -> str | None:
    lowered = reason.lower()
    if "dead_zone" in lowered:
        return "repeated_dead_zones"
    if "null_control" in lowered or "controls_incomplete" in lowered:
        return "null_controls"
    if "accepted_oos" in lowered or "no_oos" in lowered or "oos_trades" in lowered:
        return "oos_acceptance"
    if "source_identity" in lowered or "source_readiness" in lowered:
        return "source_authority"
    if "data_snapshot_identity" in lowered or "identity_readiness" in lowered or "identity" in lowered:
        return "identity_ambiguity"
    if "signal_density" in lowered:
        return "signal_density"
    if "minimum_sample" in lowered or "trades" in lowered:
        return "sample_adequacy"
    if "window" in lowered:
        return "window_design"
    if "data_readiness" in lowered or "data_unavailable" in lowered:
        return "data_breadth"
    if "quality" in lowered:
        return "data_quality"
    if "no_executable_preset_mapping" in lowered or "campaign_scope_not_materialized" in lowered:
        return "evidence_completeness"
    if any(token in lowered for token in ("campaign_identity", "funnel_result", "policy_decision", "next_action_bridge", "lineage")):
        return "evidence_completeness"
    if "thesis_status_not_executable" in lowered:
        return "hypothesis_diversity"
    if "fail_closed_rejected" in lowered or "absence_of_edge" in lowered:
        return "genuine_absence_of_edge"
    return None


def _recommendation(criterion_id: str, count: int, *, primary: str, secondary: set[str]) -> str:
    if count == 0:
        return "insufficient_evidence_to_change"
    if criterion_id in {"evidence_completeness", "oos_acceptance", "null_controls", "repeated_dead_zones"}:
        return "keep"
    if criterion_id in secondary and criterion_id == "identity_ambiguity":
        return "stratify"
    if criterion_id == primary:
        return "keep"
    return "insufficient_evidence_to_change"


def _group_counts(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        label = _text(row.get(field)) or "not_visible"
        counts[label][_text(row.get("execution_status")) or "unknown"] += 1
    out = []
    for label in sorted(counts):
        status_counts = {status: int(counts[label][status]) for status in sorted(counts[label])}
        out.append({"label": label, "status_counts": status_counts, "count": int(sum(status_counts.values()))})
    return out


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    lines = [
        "# QRE Broad Campaign Funnel Diagnosis",
        "",
        f"- diagnosis_identity: `{_text(snapshot.get('diagnosis_identity')) or 'not_materialized'}`",
        f"- source_execution_identity: `{_text(snapshot.get('source_execution_identity')) or 'not_visible'}`",
        f"- primary_bottleneck: `{_text(summary.get('primary_bottleneck')) or 'not_visible'}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        "",
        "## Funnel Counts",
        "",
    ]
    for key, value in _mapping(snapshot.get("funnel_counts")).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Criterion Recommendations", ""])
    for row in _list_of_mappings(snapshot.get("criterion_rows")):
        lines.append(
            f"- `{_text(row.get('criterion_id'))}`: `{_text(row.get('recommendation'))}` ({int(row.get('affected_cell_count') or 0)} cells)"
        )
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    execution_path: Path | None = None,
    portfolio_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    execution_source = execution_path or DEFAULT_EXECUTION_PATH
    portfolio_source = portfolio_path or DEFAULT_PORTFOLIO_PATH
    generated = generated_at_utc or _utcnow()
    execution = _read_json(execution_source) or {}
    portfolio = _read_json(portfolio_source) or {}

    execution_rows = _list_of_mappings(execution.get("rows"))
    portfolio_rows = {_text(row.get("cell_id")): row for row in _list_of_mappings(portfolio.get("rows"))}
    enriched_rows: list[dict[str, Any]] = []
    criterion_cells: dict[str, set[str]] = {criterion: set() for criterion in CRITERIA}
    failure_taxonomy = Counter()

    for row in execution_rows:
        cell_id = _text(row.get("cell_id"))
        joined = dict(row)
        joined.update(
            {
                "behavior_family": _text(_mapping(portfolio_rows.get(cell_id)).get("behavior_family")),
                "mechanism": _text(_mapping(portfolio_rows.get(cell_id)).get("mechanism")),
                "proposed_universe": _mapping(portfolio_rows.get(cell_id)).get("proposed_universe")
                if isinstance(_mapping(portfolio_rows.get(cell_id)).get("proposed_universe"), dict)
                else _text(_mapping(portfolio_rows.get(cell_id)).get("proposed_universe")),
                "proposed_timeframe": _text(_mapping(portfolio_rows.get(cell_id)).get("proposed_timeframe")),
                "proposed_regime_coverage": _text(_mapping(portfolio_rows.get(cell_id)).get("proposed_regime_coverage")),
                "signal_density_bucket": _text(_mapping(_mapping(portfolio_rows.get(cell_id)).get("expected_signal_density")).get("value")),
            }
        )
        reasons = _normalize_str_list(row.get("status_reasons"))
        for reason in reasons:
            failure_taxonomy[reason] += 1
            criterion = _criterion_for_reason(reason)
            if criterion:
                criterion_cells[criterion].add(cell_id)
        if _text(row.get("execution_status")) == "rejected" and "all_windows_no_oos_trades" in _text(_mapping(_mapping(row.get("stage_outcomes")).get("oos")).get("status")):
            criterion_cells["genuine_absence_of_edge"].add(cell_id)
        enriched_rows.append(joined)

    criterion_counts = {criterion: len(criterion_cells[criterion]) for criterion in CRITERIA}
    ordered = sorted(
        CRITERIA,
        key=lambda criterion: (-criterion_counts[criterion], PRIMARY_ORDER.index(criterion)),
    )
    primary_bottleneck = ordered[0] if ordered and criterion_counts[ordered[0]] > 0 else "evidence_completeness"
    secondary_bottlenecks = [criterion for criterion in ordered[1:] if criterion_counts[criterion] > 0][:2]

    criterion_rows = []
    for criterion in CRITERIA:
        count = criterion_counts[criterion]
        criterion_rows.append(
            {
                "criterion_id": criterion,
                "affected_cell_count": count,
                "affected_cell_ids": sorted(criterion_cells[criterion]),
                "recommendation": _recommendation(
                    criterion,
                    count,
                    primary=primary_bottleneck,
                    secondary=set(secondary_bottlenecks),
                ),
            }
        )

    criterion_rows.sort(key=lambda item: item["criterion_id"])
    funnel_counts = {
        "raw_scope_count": len(portfolio_rows),
        "eligibility_ready_count": int(_mapping(portfolio.get("summary")).get("ready_cell_count") or 0),
        "screening_entered_count": int(_mapping(execution.get("summary")).get("executable_cell_count") or 0),
        "validation_completed_count": 0,
        "oos_accepted_count": 0,
        "null_control_complete_count": sum(
            1
            for row in execution_rows
            if _text(_mapping(_mapping(_mapping(row.get("stage_outcomes")).get("null_controls")).get("status"))) == "controls_complete"
        ),
        "evidence_complete_count": sum(1 for row in execution_rows if _text(row.get("execution_status")) == "completed"),
    }
    funnel_counts["raw_to_eligibility_conversion_rate"] = round(
        funnel_counts["eligibility_ready_count"] / funnel_counts["raw_scope_count"], 6
    ) if funnel_counts["raw_scope_count"] else 0.0

    diagnosis_payload = {
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "criterion_rows": criterion_rows,
        "funnel_counts": funnel_counts,
        "primary_bottleneck": primary_bottleneck,
        "secondary_bottlenecks": secondary_bottlenecks,
    }
    diagnosis_identity = "qcz_" + _stable_digest(diagnosis_payload)[:16]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "source_portfolio_identity": _text(portfolio.get("portfolio_identity")),
        "diagnosis_identity": diagnosis_identity,
        "artifact_references": {
            "qre_broad_campaign_execution": _rel(execution_source),
            "qre_campaign_portfolio_plan": _rel(portfolio_source),
            "governance_doc": _rel(DOC_PATH),
        },
        "funnel_counts": funnel_counts,
        "criterion_rows": criterion_rows,
        "stratifications": {
            "by_thesis": _group_counts(enriched_rows, "title"),
            "by_behavior_family": _group_counts(enriched_rows, "behavior_family"),
            "by_strategy": _group_counts(enriched_rows, "source_hypothesis_id"),
            "by_preset": _group_counts(enriched_rows, "preset_name"),
            "by_timeframe": _group_counts(enriched_rows, "proposed_timeframe"),
            "by_regime": _group_counts(enriched_rows, "proposed_regime_coverage"),
            "by_signal_density_bucket": _group_counts(enriched_rows, "signal_density_bucket"),
        },
        "failure_taxonomy": [
            {"reason": reason, "count": int(count)}
            for reason, count in sorted(failure_taxonomy.items())
        ],
        "summary": {
            "primary_bottleneck": primary_bottleneck,
            "secondary_bottlenecks": secondary_bottlenecks,
            "all_criteria_have_exactly_one_recommendation": all(
                _text(row.get("recommendation")) in ALLOWED_RECOMMENDATIONS for row in criterion_rows
            ),
            "final_recommendation": "broad_campaign_funnel_diagnosis_ready",
        },
        "safety_invariants": {
            "read_only": True,
            "context_only": True,
            "mutates_campaign_queue": False,
            "mutates_strategy_or_preset": False,
            "mutates_frozen_contracts": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _atomic_write(path: Path, text: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_broad_campaign_funnel_diagnosis.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
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
    json_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, str]:
    target_json = json_path or ARTIFACT_LATEST
    target_markdown = markdown_path or ARTIFACT_MARKDOWN
    _atomic_write(target_json, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _atomic_write(target_markdown, _render_markdown(snapshot))
    return {
        "latest": _rel(target_json),
        "operator_summary": _rel(target_markdown),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_broad_campaign_funnel_diagnosis",
        description="Build deterministic broad campaign funnel diagnosis from 017Y execution accounting.",
    )
    parser.add_argument("--execution", default=_rel(DEFAULT_EXECUTION_PATH))
    parser.add_argument("--portfolio", default=_rel(DEFAULT_PORTFOLIO_PATH))
    parser.add_argument("--frozen-utc", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot(
        execution_path=REPO_ROOT / args.execution,
        portfolio_path=REPO_ROOT / args.portfolio,
        generated_at_utc=_text(args.frozen_utc) or None,
    )
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
