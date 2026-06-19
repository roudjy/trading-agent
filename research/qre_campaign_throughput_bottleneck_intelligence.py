from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_cache_throughput_manifest as cache_throughput
from research import qre_trusted_loop_operational_controls as operational_controls


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_campaign_throughput_bottleneck_intelligence"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_campaign_throughput_bottleneck_intelligence")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_campaign_throughput_bottleneck_intelligence/"

REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
QUEUE_PATH: Final[Path] = Path("research/campaign_queue_latest.v1.json")
DIGEST_PATH: Final[Path] = Path("research/campaign_digest_latest.v1.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _registry_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    campaigns = payload.get("campaigns") if isinstance(payload, Mapping) else None
    if not isinstance(campaigns, Mapping):
        return []
    rows = [dict(row) for row in campaigns.values() if isinstance(row, Mapping)]
    rows.sort(key=lambda row: (_text(row.get("campaign_id")), _text(row.get("preset_name"))))
    return rows


def _queue_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    queue = payload.get("queue") if isinstance(payload, Mapping) else None
    if not isinstance(queue, list):
        return []
    rows = [dict(row) for row in queue if isinstance(row, Mapping)]
    rows.sort(key=lambda row: (_text(row.get("campaign_id")), _text(row.get("state"))))
    return rows


def _active_registry_ids(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        _text(row.get("campaign_id"))
        for row in rows
        if _text(row.get("state")) in {"pending", "leased", "running"} and _text(row.get("campaign_id"))
    )


def _active_queue_ids(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        _text(row.get("campaign_id"))
        for row in rows
        if _text(row.get("state")) in {"pending", "leased", "running"} and _text(row.get("campaign_id"))
    )


def _bottleneck(
    *,
    code: str,
    severity: str,
    reason_codes: list[str],
    exact_next_action: str,
    operator_explanation: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "bottleneck_code": code,
        "severity": severity,
        "reason_codes": reason_codes,
        "exact_next_action": exact_next_action,
        "operator_explanation": operator_explanation,
        "evidence_refs": evidence_refs,
    }


def _build_bottlenecks(
    *,
    repo_root: Path,
    registry_payload: Mapping[str, Any] | None,
    queue_payload: Mapping[str, Any] | None,
    digest_payload: Mapping[str, Any] | None,
    throughput_status: Mapping[str, Any],
    controls: Mapping[str, Any],
    registry_rows: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if registry_payload is None:
        rows.append(
            _bottleneck(
                code="missing_campaign_registry",
                severity="critical",
                reason_codes=["campaign_registry_missing"],
                exact_next_action="restore_campaign_registry_artifact",
                operator_explanation="Campaign throughput intelligence cannot reconcile current scope without the registry snapshot.",
                evidence_refs=[_rel(repo_root / REGISTRY_PATH, root=repo_root)],
            )
        )
    if queue_payload is None:
        rows.append(
            _bottleneck(
                code="missing_campaign_queue",
                severity="critical",
                reason_codes=["campaign_queue_missing"],
                exact_next_action="restore_campaign_queue_artifact",
                operator_explanation="Campaign throughput intelligence cannot verify queue projection without the queue artifact.",
                evidence_refs=[_rel(repo_root / QUEUE_PATH, root=repo_root)],
            )
        )
    if digest_payload is None:
        rows.append(
            _bottleneck(
                code="missing_campaign_digest",
                severity="high",
                reason_codes=["campaign_digest_missing"],
                exact_next_action="restore_campaign_digest_artifact",
                operator_explanation="Digest context is missing, so throughput trends remain fail-closed and incomplete.",
                evidence_refs=[_rel(repo_root / DIGEST_PATH, root=repo_root)],
            )
        )

    active_registry = set(_active_registry_ids(registry_rows))
    active_queue = set(_active_queue_ids(queue_rows))
    missing_in_queue = sorted(active_registry - active_queue)
    orphaned_queue = sorted(active_queue - active_registry)
    if missing_in_queue or orphaned_queue:
        rows.append(
            _bottleneck(
                code="queue_registry_divergence",
                severity="critical",
                reason_codes=["active_registry_queue_mismatch"],
                exact_next_action="reconcile_campaign_queue_from_registry",
                operator_explanation="The queue view diverges from the registry source of truth for active campaigns.",
                evidence_refs=[
                    _rel(repo_root / REGISTRY_PATH, root=repo_root),
                    _rel(repo_root / QUEUE_PATH, root=repo_root),
                ],
            )
        )

    if not bool(throughput_status.get("research_ready")):
        rows.append(
            _bottleneck(
                code="cache_throughput_not_ready",
                severity="high",
                reason_codes=["cache_throughput_manifest_not_ready"],
                exact_next_action="stabilize_cache_throughput_manifest",
                operator_explanation="Local cache throughput context is not research-ready, so throughput analysis stays incomplete.",
                evidence_refs=[_text(throughput_status.get("path")) or "logs/qre_cache_throughput_manifest/latest.json"],
            )
        )

    controls_summary = controls.get("summary") if isinstance(controls.get("summary"), Mapping) else {}
    if _text(controls_summary.get("artifact_freshness_status")) == "stale_or_missing":
        rows.append(
            _bottleneck(
                code="stale_run_artifact_pressure",
                severity="high",
                reason_codes=["trusted_loop_artifacts_stale_or_missing"],
                exact_next_action=_text(controls_summary.get("exact_next_safe_action")) or "reconcile_stale_or_mismatched_run_artifacts",
                operator_explanation="Trusted-loop artifacts are stale or missing, which weakens campaign throughput comparability across runs.",
                evidence_refs=["logs/qre_trusted_loop_operational_controls/latest.json"],
            )
        )

    digest_meaningful = (
        (digest_payload or {}).get("meaningful_by_classification")
        if isinstance((digest_payload or {}).get("meaningful_by_classification"), Mapping)
        else {}
    )
    queue_depth = int((digest_payload or {}).get("queue_depth") or len(active_queue))
    campaigns_completed = int((digest_payload or {}).get("campaigns_completed") or 0)
    campaigns_failed = int((digest_payload or {}).get("campaigns_failed") or 0)
    duplicate_low_value = int(digest_meaningful.get("duplicate_low_value_run") or 0)
    if queue_depth > 0 and campaigns_completed == 0:
        rows.append(
            _bottleneck(
                code="queue_backpressure_without_completion",
                severity="medium",
                reason_codes=["queue_depth_positive_with_zero_completed_campaigns"],
                exact_next_action="inspect_active_campaign_queue_progress",
                operator_explanation="Campaigns remain active or queued without any completed campaigns in the current digest window.",
                evidence_refs=[_rel(repo_root / DIGEST_PATH, root=repo_root)],
            )
        )
    if campaigns_failed > 0:
        rows.append(
            _bottleneck(
                code="technical_or_failed_campaign_pressure",
                severity="medium",
                reason_codes=["campaign_failures_visible_in_digest"],
                exact_next_action="inspect_top_failure_reasons",
                operator_explanation="Failed campaigns are visible in the current digest window and may be reducing meaningful research throughput.",
                evidence_refs=[_rel(repo_root / DIGEST_PATH, root=repo_root)],
            )
        )
    if duplicate_low_value > 0:
        rows.append(
            _bottleneck(
                code="duplicate_low_value_run_pressure",
                severity="medium",
                reason_codes=["duplicate_low_value_runs_visible"],
                exact_next_action="increase_duplicate_avoidance_review",
                operator_explanation="Duplicate low-value runs are consuming throughput without adding meaningful evidence breadth.",
                evidence_refs=[_rel(repo_root / DIGEST_PATH, root=repo_root)],
            )
        )
    return sorted(rows, key=lambda row: (row["severity"], row["bottleneck_code"]))


def _next_action(bottlenecks: list[dict[str, Any]]) -> str:
    if not bottlenecks:
        return "preserve_campaign_throughput_context"
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    highest = min(
        bottlenecks,
        key=lambda row: (severity_order.get(_text(row.get("severity")), 99), _text(row.get("bottleneck_code"))),
    )
    return _text(highest.get("exact_next_action")) or "operator_review_campaign_throughput_context"


def build_campaign_throughput_bottleneck_intelligence(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    registry_payload = _read_json(repo_root / REGISTRY_PATH)
    queue_payload = _read_json(repo_root / QUEUE_PATH)
    digest_payload = _read_json(repo_root / DIGEST_PATH)
    throughput_status = cache_throughput.read_throughput_status(repo_root=repo_root)
    controls = operational_controls.build_trusted_loop_operational_controls(repo_root=repo_root)

    registry_rows = _registry_rows(registry_payload)
    queue_rows = _queue_rows(queue_payload)
    active_registry_ids = _active_registry_ids(registry_rows)
    active_queue_ids = _active_queue_ids(queue_rows)
    state_counts = Counter(_text(row.get("state")) or "unknown" for row in registry_rows)
    outcome_counts = Counter(_text(row.get("outcome")) or "none" for row in registry_rows)
    digest_meaningful = (
        (digest_payload or {}).get("meaningful_by_classification")
        if isinstance((digest_payload or {}).get("meaningful_by_classification"), Mapping)
        else {}
    )
    bottlenecks = _build_bottlenecks(
        repo_root=repo_root,
        registry_payload=registry_payload,
        queue_payload=queue_payload,
        digest_payload=digest_payload,
        throughput_status=throughput_status,
        controls=controls,
        registry_rows=registry_rows,
        queue_rows=queue_rows,
    )
    exact_next_action = _next_action(bottlenecks)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "campaign_throughput_bottleneck_intelligence_ready": bool(
                registry_payload is not None and queue_payload is not None and digest_payload is not None
            ),
            "registry_campaign_count": len(registry_rows),
            "active_registry_campaign_count": len(active_registry_ids),
            "active_queue_campaign_count": len(active_queue_ids),
            "queue_registry_divergence_count": abs(len(active_registry_ids) - len(active_queue_ids))
            + len(set(active_registry_ids) ^ set(active_queue_ids)),
            "queue_depth": int((digest_payload or {}).get("queue_depth") or len(active_queue_ids)),
            "campaigns_completed_today": int((digest_payload or {}).get("campaigns_completed") or 0),
            "campaigns_failed_today": int((digest_payload or {}).get("campaigns_failed") or 0),
            "meaningful_campaigns_total": int((digest_payload or {}).get("meaningful_campaigns_total") or 0),
            "duplicate_low_value_run_count": int(digest_meaningful.get("duplicate_low_value_run") or 0),
            "cache_throughput_ready": bool(throughput_status.get("research_ready")),
            "trusted_loop_artifact_freshness_status": _text(
                ((controls.get("summary") or {}).get("artifact_freshness_status"))
            )
            or "unknown",
            "bottleneck_count": len(bottlenecks),
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Campaign throughput bottleneck intelligence normalizes registry, queue, digest, cache-throughput, "
                "and trusted-loop signals into read-only operator context. It never mutates campaign state or lowers evidence standards."
            ),
        },
        "throughput_context": {
            "registry_state_counts": dict(sorted(state_counts.items())),
            "registry_outcome_counts": dict(sorted(outcome_counts.items())),
            "active_registry_campaign_ids": active_registry_ids,
            "active_queue_campaign_ids": active_queue_ids,
            "meaningful_by_classification": dict(sorted(digest_meaningful.items())),
            "queue_efficiency_pct": (digest_payload or {}).get("queue_efficiency_pct"),
            "worker_utilization_pct": (digest_payload or {}).get("worker_utilization_pct"),
            "top_failure_reasons": list((digest_payload or {}).get("top_failure_reasons") or []),
        },
        "bottlenecks": bottlenecks,
        "upstream_status": {
            "campaign_registry_path": _rel(repo_root / REGISTRY_PATH, root=repo_root),
            "campaign_queue_path": _rel(repo_root / QUEUE_PATH, root=repo_root),
            "campaign_digest_path": _rel(repo_root / DIGEST_PATH, root=repo_root),
            "cache_throughput_status": dict(throughput_status),
            "trusted_loop_operational_summary": dict((controls.get("summary") or {})),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_mutate_campaign_queue": False,
            "can_spawn_campaigns": False,
            "can_promote_candidates": False,
            "can_activate_shadow_or_live": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "mutates_campaigns": False,
            "mutates_queue": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "throughput_cannot_lower_evidence_standards": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Campaign Throughput Bottleneck Intelligence",
            "",
            f"- campaign_throughput_bottleneck_intelligence_ready: {summary.get('campaign_throughput_bottleneck_intelligence_ready')}",
            f"- registry_campaign_count: {summary.get('registry_campaign_count')}",
            f"- active_registry_campaign_count: {summary.get('active_registry_campaign_count')}",
            f"- active_queue_campaign_count: {summary.get('active_queue_campaign_count')}",
            f"- queue_registry_divergence_count: {summary.get('queue_registry_divergence_count')}",
            f"- queue_depth: {summary.get('queue_depth')}",
            f"- campaigns_completed_today: {summary.get('campaigns_completed_today')}",
            f"- campaigns_failed_today: {summary.get('campaigns_failed_today')}",
            f"- meaningful_campaigns_total: {summary.get('meaningful_campaigns_total')}",
            f"- duplicate_low_value_run_count: {summary.get('duplicate_low_value_run_count')}",
            f"- cache_throughput_ready: {summary.get('cache_throughput_ready')}",
            f"- trusted_loop_artifact_freshness_status: {summary.get('trusted_loop_artifact_freshness_status')}",
            f"- bottleneck_count: {summary.get('bottleneck_count')}",
            f"- exact_next_action: {summary.get('exact_next_action')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary.with_suffix(summary.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary)
    return {
        "latest": _rel(latest, root=repo_root),
        "operator_summary": _rel(summary, root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_campaign_throughput_bottleneck_intelligence",
        description="Build read-only campaign throughput bottleneck intelligence.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_campaign_throughput_bottleneck_intelligence()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
