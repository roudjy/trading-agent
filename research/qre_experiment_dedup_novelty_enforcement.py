from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_experiment_dedup_novelty_enforcement"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_experiment_dedup_novelty_enforcement")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_experiment_dedup_novelty_enforcement/"

ROUTER_PATH: Final[Path] = Path("logs/qre_research_cycle_router/latest.json")
DISPOSITION_PATH: Final[Path] = Path("logs/qre_hypothesis_disposition_memory/latest.json")
REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
THROUGHPUT_PATH: Final[Path] = Path("logs/qre_campaign_throughput_bottleneck_intelligence/latest.json")


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


def _campaign_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    campaigns = payload.get("campaigns") if isinstance(payload, Mapping) else None
    if not isinstance(campaigns, Mapping):
        return []
    rows = [dict(row) for row in campaigns.values() if isinstance(row, Mapping)]
    rows.sort(key=lambda row: (_text(row.get("campaign_id")), _text(row.get("preset_name"))))
    return rows


def _fingerprint(row: Mapping[str, Any]) -> str:
    parts = {
        "campaign_type": _text(row.get("campaign_type")),
        "preset_name": _text(row.get("preset_name")),
        "parent_campaign_id": _text(row.get("parent_campaign_id")),
        "lineage_root_campaign_id": _text(row.get("lineage_root_campaign_id")),
        "input_artifact_fingerprint": _text(row.get("input_artifact_fingerprint")),
    }
    return _digest(parts)


def _scope_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _text(row.get("hypothesis_id")),
            _text(row.get("strategy_family")),
            _text(row.get("preset_name")),
            _text(row.get("asset_class")),
        ]
    )


def _build_duplicate_rows(
    *,
    campaigns: list[dict[str, Any]],
    suppressed_scopes: list[dict[str, Any]],
    throughput: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    active_rows = [
        row for row in campaigns if _text(row.get("state")) in {"pending", "leased", "running"}
    ]
    by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for row in active_rows:
        by_fingerprint.setdefault(_fingerprint(row), []).append(row)
        by_scope.setdefault(_scope_key(row), []).append(row)

    for fingerprint, items in sorted(by_fingerprint.items()):
        if len(items) <= 1:
            continue
        rows.append(
            {
                "duplicate_class": "active_duplicate_fingerprint",
                "duplicate_key": fingerprint,
                "status": "blocked_duplicate",
                "campaign_ids": [_text(item.get("campaign_id")) for item in items],
                "exact_next_action": "deduplicate_active_campaign_scope",
                "evidence_refs": ["research/campaign_registry_latest.v1.json"],
            }
        )

    for scope_key, items in sorted(by_scope.items()):
        if len(items) <= 1 or not scope_key.strip("|"):
            continue
        rows.append(
            {
                "duplicate_class": "active_scope_conflict",
                "duplicate_key": scope_key,
                "status": "blocked_scope_conflict",
                "campaign_ids": [_text(item.get("campaign_id")) for item in items],
                "exact_next_action": "review_scope_collision_before_new_research",
                "evidence_refs": ["research/campaign_registry_latest.v1.json"],
            }
        )

    for scope in suppressed_scopes:
        if not isinstance(scope, Mapping):
            continue
        rows.append(
            {
                "duplicate_class": _text(scope.get("scope_kind")) or "suppressed_scope",
                "duplicate_key": _digest(scope),
                "status": "suppressed",
                "campaign_ids": [],
                "exact_next_action": "preserve_suppressed_scope_boundary",
                "evidence_refs": ["logs/qre_research_cycle_router/latest.json", "logs/qre_hypothesis_disposition_memory/latest.json"],
            }
        )

    throughput_rows = throughput.get("bottlenecks") if isinstance(throughput, Mapping) and isinstance(throughput.get("bottlenecks"), list) else []
    for row in throughput_rows:
        if not isinstance(row, Mapping):
            continue
        if _text(row.get("bottleneck_code")) != "duplicate_low_value_run_pressure":
            continue
        rows.append(
            {
                "duplicate_class": "duplicate_low_value_run_pressure",
                "duplicate_key": "duplicate_low_value_run_pressure",
                "status": "context_only_duplicate_pressure",
                "campaign_ids": [],
                "exact_next_action": _text(row.get("exact_next_action")) or "increase_duplicate_avoidance_review",
                "evidence_refs": list(row.get("evidence_refs") or []),
            }
        )
    rows.sort(key=lambda row: (_text(row.get("duplicate_class")), _text(row.get("duplicate_key"))))
    return rows


def _build_novelty_rows(router: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    eligible = router.get("eligible_directions") if isinstance(router, Mapping) and isinstance(router.get("eligible_directions"), list) else []
    rows: list[dict[str, Any]] = []
    for row in eligible:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "direction_id": _text(row.get("direction_id")),
                "direction_type": _text(row.get("direction_type")),
                "status": "eligible_novel_direction",
                "route_status": _text(row.get("route_status")),
                "eligibility_reasons": list(row.get("eligibility_reasons") or []),
            }
        )
    rows.sort(key=lambda row: row["direction_id"])
    return rows


def _next_action(duplicate_rows: list[dict[str, Any]], novelty_rows: list[dict[str, Any]]) -> str:
    if any(_text(row.get("status")) == "blocked_duplicate" for row in duplicate_rows):
        return "deduplicate_active_campaign_scope"
    if any(_text(row.get("status")) == "suppressed" for row in duplicate_rows):
        return "preserve_suppressed_scope_boundary"
    if novelty_rows:
        return "route_only_to_eligible_novel_directions"
    return "operator_review_required_before_new_scope"


def build_experiment_dedup_novelty_enforcement(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    router = _read_json(repo_root / ROUTER_PATH)
    disposition = _read_json(repo_root / DISPOSITION_PATH)
    registry = _read_json(repo_root / REGISTRY_PATH)
    throughput = _read_json(repo_root / THROUGHPUT_PATH)

    campaigns = _campaign_rows(registry)
    suppressed_scopes = router.get("suppressed_scopes") if isinstance(router, Mapping) and isinstance(router.get("suppressed_scopes"), list) else []
    duplicate_rows = _build_duplicate_rows(
        campaigns=campaigns,
        suppressed_scopes=suppressed_scopes,
        throughput=throughput,
    )
    novelty_rows = _build_novelty_rows(router)
    duplicate_counts = Counter(_text(row.get("duplicate_class")) or "unknown" for row in duplicate_rows)
    exact_next_action = _next_action(duplicate_rows, novelty_rows)

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "experiment_dedup_novelty_enforcement_ready": bool(
                router is not None and disposition is not None and registry is not None
            ),
            "suppressed_scope_count": sum(1 for row in duplicate_rows if _text(row.get("status")) == "suppressed"),
            "active_duplicate_fingerprint_count": sum(
                1 for row in duplicate_rows if _text(row.get("duplicate_class")) == "active_duplicate_fingerprint"
            ),
            "active_scope_conflict_count": sum(
                1 for row in duplicate_rows if _text(row.get("duplicate_class")) == "active_scope_conflict"
            ),
            "duplicate_pressure_count": len(duplicate_rows),
            "eligible_novel_direction_count": len(novelty_rows),
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Experiment dedup and novelty enforcement consolidates exact suppression, active duplicate pressure, "
                "and eligible novel directions into one read-only contract. It never mutates campaigns or consumes queue authority."
            ),
        },
        "duplicate_rows": duplicate_rows,
        "novelty_rows": novelty_rows,
        "upstream_status": {
            "router_path": _rel(repo_root / ROUTER_PATH, root=repo_root),
            "disposition_path": _rel(repo_root / DISPOSITION_PATH, root=repo_root),
            "registry_path": _rel(repo_root / REGISTRY_PATH, root=repo_root),
            "throughput_path": _rel(repo_root / THROUGHPUT_PATH, root=repo_root),
            "duplicate_class_counts": dict(sorted(duplicate_counts.items())),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_spawn_campaigns": False,
            "can_mutate_queue": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "mutates_campaigns": False,
            "mutates_queue": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Experiment Dedup and Novelty Enforcement",
            "",
            f"- experiment_dedup_novelty_enforcement_ready: {summary.get('experiment_dedup_novelty_enforcement_ready')}",
            f"- suppressed_scope_count: {summary.get('suppressed_scope_count')}",
            f"- active_duplicate_fingerprint_count: {summary.get('active_duplicate_fingerprint_count')}",
            f"- active_scope_conflict_count: {summary.get('active_scope_conflict_count')}",
            f"- duplicate_pressure_count: {summary.get('duplicate_pressure_count')}",
            f"- eligible_novel_direction_count: {summary.get('eligible_novel_direction_count')}",
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
        prog="python -m research.qre_experiment_dedup_novelty_enforcement",
        description="Build read-only experiment dedup and novelty enforcement.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_experiment_dedup_novelty_enforcement()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
