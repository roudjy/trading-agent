from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_campaign_throughput_bottleneck_intelligence as throughput_bottlenecks
from research import qre_contradiction_staleness_intelligence as contradiction_staleness
from research import qre_read_only_artifact_continuity as artifact_continuity
from research import qre_research_state_sequential_retrieval as sequential_retrieval
from research import qre_trusted_loop_operational_controls as operational_controls


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_incomplete_artifact_remediation_planning"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_incomplete_artifact_remediation_planning")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_incomplete_artifact_remediation_planning/"
_PRIORITY_ORDER: Final[dict[str, int]] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _priority(value: str) -> str:
    normalized = _text(value).lower()
    return normalized if normalized in _PRIORITY_ORDER else "medium"


def _row(
    *,
    source_report: str,
    blocker_class: str,
    priority: str,
    reason: str,
    exact_next_action: str,
    artifact_ref: str,
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    payload = {
        "source_report": source_report,
        "blocker_class": blocker_class,
        "priority": _priority(priority),
        "reason": reason,
        "exact_next_action": exact_next_action,
        "artifact_ref": artifact_ref,
        "evidence_refs": list(evidence_refs),
    }
    payload["remediation_id"] = _digest(payload)[:23]
    return payload


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if canonical in seen:
            continue
        seen.add(canonical)
        deduped.append(dict(row))
    return deduped


def _continuity_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("targets") if isinstance(report.get("targets"), list) else []
    remediation_rows: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        state = _text(item.get("materialization_state"))
        projected_status = _text(item.get("projected_status"))
        if state == "current_artifact_matches_projected" and projected_status == "ready":
            continue
        priority = "high" if projected_status != "ready" else "medium"
        remediation_rows.append(
            _row(
                source_report="qre_read_only_artifact_continuity",
                blocker_class=state or "artifact_materialization_gap",
                priority=priority,
                reason=", ".join(str(code) for code in item.get("reason_codes") or []) or "artifact continuity requires remediation",
                exact_next_action=_text(item.get("exact_next_action")) or "review_artifact_materialization_gap",
                artifact_ref=_text(item.get("artifact_path")),
                evidence_refs=[str(ref) for ref in item.get("source_artifact_refs") or []],
            )
        )
    return remediation_rows


def _contradiction_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    stale_rows = report.get("stale_or_superseded") if isinstance(report.get("stale_or_superseded"), list) else []
    exact_next_action = _text((report.get("summary") or {}).get("exact_next_action"))
    return [
        _row(
            source_report="qre_contradiction_staleness_intelligence",
            blocker_class="stale_or_superseded_artifact",
            priority="medium",
            reason=_text(row.get("detail")) or "stale_or_superseded_artifact",
            exact_next_action=exact_next_action or "reconcile_stale_or_superseded_artifacts",
            artifact_ref=_text(row.get("artifact_path")) or _text(row.get("artifact_ref")),
            evidence_refs=[_text(row.get("artifact_ref"))],
        )
        for row in stale_rows
        if isinstance(row, Mapping)
    ]


def _throughput_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("bottlenecks") if isinstance(report.get("bottlenecks"), list) else []
    return [
        _row(
            source_report="qre_campaign_throughput_bottleneck_intelligence",
            blocker_class=_text(row.get("bottleneck_code")) or "campaign_throughput_bottleneck",
            priority=_text(row.get("severity")) or "medium",
            reason=_text(row.get("operator_explanation")) or _text(row.get("bottleneck_code")),
            exact_next_action=_text(row.get("exact_next_action")) or "review_campaign_throughput_bottleneck",
            artifact_ref="logs/qre_campaign_throughput_bottleneck_intelligence/latest.json",
            evidence_refs=[str(ref) for ref in row.get("evidence_refs") or []],
        )
        for row in rows
        if isinstance(row, Mapping)
    ]


def _sequential_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    exact_next_action = _text((report.get("summary") or {}).get("exact_next_action"))
    return [
        _row(
            source_report="qre_research_state_sequential_retrieval",
            blocker_class=_text(row.get("blocker_code")) or "sequential_state_gap",
            priority=_text(row.get("severity")) or "medium",
            reason=_text(row.get("reason")) or _text(row.get("blocker_code")),
            exact_next_action=exact_next_action or "restore_current_run_artifacts",
            artifact_ref=_text(row.get("evidence_ref")) or "logs/qre_research_state_sequential_retrieval/latest.json",
            evidence_refs=[_text(row.get("evidence_ref"))],
        )
        for row in blockers
        if isinstance(row, Mapping)
    ]


def _operational_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    if bool(summary.get("trusted_loop_operational_controls_ready")):
        return []
    current_run = report.get("current_run") if isinstance(report.get("current_run"), Mapping) else {}
    return [
        _row(
            source_report="qre_trusted_loop_operational_controls",
            blocker_class=_text(summary.get("status")) or "trusted_loop_operational_gap",
            priority="high",
            reason=_text(current_run.get("status_reason")) or _text(summary.get("status")) or "trusted_loop_operational_controls_not_ready",
            exact_next_action=_text(summary.get("exact_next_safe_action")) or "operator_review_required_before_retry",
            artifact_ref="logs/qre_trusted_loop_operational_controls/latest.json",
            evidence_refs=["logs/qre_trusted_loop_operational_controls/latest.json"],
        )
    ]


def build_incomplete_artifact_remediation_planning(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    continuity_report = artifact_continuity.build_read_only_artifact_continuity(repo_root=repo_root)
    contradiction_report = contradiction_staleness.build_contradiction_staleness_intelligence(
        repo_root=repo_root
    )
    throughput_report = throughput_bottlenecks.build_campaign_throughput_bottleneck_intelligence(
        repo_root=repo_root
    )
    sequential_report = sequential_retrieval.build_research_state_sequential_retrieval(repo_root=repo_root)
    operational_report = operational_controls.build_trusted_loop_operational_controls(repo_root=repo_root)

    remediation_rows = _dedupe_rows(
        [
            *_continuity_rows(continuity_report),
            *_contradiction_rows(contradiction_report),
            *_throughput_rows(throughput_report),
            *_sequential_rows(sequential_report),
            *_operational_rows(operational_report),
        ]
    )
    remediation_rows.sort(
        key=lambda row: (
            _PRIORITY_ORDER.get(_priority(_text(row.get("priority"))), 9),
            _text(row.get("source_report")),
            _text(row.get("artifact_ref")),
            _text(row.get("blocker_class")),
        )
    )
    counts = Counter(_priority(_text(row.get("priority"))) for row in remediation_rows)
    exact_next_action = (
        _text(remediation_rows[0].get("exact_next_action"))
        if remediation_rows
        else "preserve_current_read_only_artifact_visibility"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "remediation_planning_ready": True,
            "remediation_count": len(remediation_rows),
            "critical_count": int(counts.get("critical") or 0),
            "high_count": int(counts.get("high") or 0),
            "medium_count": int(counts.get("medium") or 0),
            "low_count": int(counts.get("low") or 0),
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Incomplete artifact remediation planning consolidates continuity gaps, stale or superseded "
                "artifacts, trusted-loop blockers, throughput bottlenecks, and sequential-state gaps into one "
                "read-only priority queue."
            ),
        },
        "remediation_rows": remediation_rows,
        "source_summaries": {
            "artifact_continuity": dict(continuity_report.get("summary") or {}),
            "contradiction_staleness": dict(contradiction_report.get("summary") or {}),
            "campaign_throughput_bottlenecks": dict(throughput_report.get("summary") or {}),
            "research_state_sequential_retrieval": dict(sequential_report.get("summary") or {}),
            "trusted_loop_operational_controls": dict(operational_report.get("summary") or {}),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
        },
        "safety_invariants": {
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "summary": report["summary"],
            "remediation_rows": report["remediation_rows"],
            "source_summaries": report["source_summaries"],
            "authority_boundary": report["authority_boundary"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("remediation_rows") if isinstance(report.get("remediation_rows"), list) else []
    lines = [
        "# QRE Incomplete Artifact Remediation Planning",
        "",
        f"- remediation_planning_ready: {summary.get('remediation_planning_ready', False)}",
        f"- remediation_count: {summary.get('remediation_count', 0)}",
        f"- critical_count: {summary.get('critical_count', 0)}",
        f"- high_count: {summary.get('high_count', 0)}",
        f"- medium_count: {summary.get('medium_count', 0)}",
        f"- exact_next_action: {summary.get('exact_next_action', '')}",
        "",
        "## Top Remediation Rows",
    ]
    for row in rows[:10]:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- [{row.get('priority')}] {row.get('blocker_class')} -> {row.get('exact_next_action')} ({row.get('artifact_ref')})"
        )
    if not rows:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    refreshed = build_incomplete_artifact_remediation_planning(repo_root=repo_root)
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(refreshed) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_incomplete_artifact_remediation_planning",
        description="Build a deterministic read-only QRE incomplete-artifact remediation plan.",
    )
    parser.add_argument("--write", action="store_true", help="Write allowlisted report outputs.")
    args = parser.parse_args()

    report = build_incomplete_artifact_remediation_planning()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
