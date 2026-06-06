from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import production_discovery_catalog as discovery_catalog
from research import qre_failure_action_from_basket as failure_action
from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_routing_readiness_from_basket as routing_readiness
from research import qre_sampling_readiness_from_basket as sampling_readiness
from research.hypothesis_discovery import behavior_hypotheses


REPORT_KIND: Final[str] = "qre_hypothesis_seed_feasibility"
BEHAVIOR_REPORT_KIND: Final[str] = "qre_behavior_family_coverage"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_hypothesis_seed_feasibility")
BEHAVIOR_OUTPUT_DIR: Final[Path] = Path("logs/qre_behavior_family_coverage")
LATEST_NAME: Final[str] = "latest.json"
_WRITE_PREFIX: Final[str] = "logs/qre_hypothesis_seed_feasibility/"
_BEHAVIOR_WRITE_PREFIX: Final[str] = "logs/qre_behavior_family_coverage/"


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:160])
    return out


def _top_counts(values: Sequence[str], *, limit: int = 5) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    return [
        {"value": key, "count": counts[key]}
        for key in sorted(counts, key=lambda item: (-counts[item], item))[:limit]
    ]


def _reasoned_follow_up(actions: Sequence[str]) -> str:
    priority = (
        "eligible_for_readonly_routing",
        "require_identity_resolution",
        "require_source_readiness",
        "collect_more_evidence",
        "expand_basket_coverage",
        "route_to_manual_review",
        "suppress_until_new_evidence",
        "defer_as_duplicate",
        "keep_blocked",
    )
    available = {action for action in actions if action}
    for action in priority:
        if action in available:
            return action
    return "keep_blocked"


def _feasibility_state(
    *,
    maps_to_basket_count: int,
    source_ready_count: int,
    data_ready_count: int,
    screening_visible_count: int,
    oos_visible_count: int,
    routing_ready_count: int,
    sampling_ready_count: int,
    source_identity_blocked_count: int,
    prior_failure_count: int,
) -> tuple[str, str]:
    if maps_to_basket_count == 0:
        return (
            "blocked_missing_basket_mapping",
            "No bounded discovery basket currently maps this hypothesis seed to a real read-only basket.",
        )
    if sampling_ready_count > 0 or routing_ready_count > 0:
        return (
            "feasible_for_readonly_research",
            "At least one mapped basket is routing/sampling-ready, so the seed is feasible for read-only research only.",
        )
    if source_identity_blocked_count >= maps_to_basket_count and source_identity_blocked_count > 0:
        return (
            "blocked_source_identity",
            "All mapped baskets are blocked by source identity, so feasibility stays blocked until provider identity is resolved.",
        )
    if data_ready_count == 0:
        return (
            "blocked_source_or_cache",
            "Mapped baskets exist, but none has source-plus-cache readiness yet.",
        )
    if screening_visible_count == 0 or oos_visible_count == 0:
        return (
            "blocked_missing_evidence_path",
            "Mapped baskets lack screening or OOS visibility, so there is no sufficient evidence path yet.",
        )
    if source_ready_count == 0:
        return (
            "blocked_source_readiness",
            "Mapped baskets have some data signals but no fully source-ready basket.",
        )
    if prior_failure_count > 0:
        return (
            "blocked_by_observed_failures",
            "Observed bounded failures exist, so the seed remains blocked until new evidence changes the read-only picture.",
        )
    return (
        "blocked_insufficient_readiness_signal",
        "The seed maps to real baskets, but current evidence is still too thin for read-only feasibility.",
    )


def build_hypothesis_seed_feasibility(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    presets = discovery_catalog.list_presets()
    active_behavior_map = {
        row.behavior_family: row.to_payload()
        for row in behavior_hypotheses.build_behavior_hypotheses()
    }
    coverage_report = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    routing_report = routing_readiness.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling_report = sampling_readiness.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure_report = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    coverage_rows = coverage_report.get("rows")
    if not isinstance(coverage_rows, list):
        coverage_rows = []
    routing_rows = routing_report.get("rows")
    if not isinstance(routing_rows, list):
        routing_rows = []
    sampling_rows = sampling_report.get("rows")
    if not isinstance(sampling_rows, list):
        sampling_rows = []
    failure_rows = failure_report.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []

    routing_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in routing_rows
        if isinstance(row, Mapping)
    }
    sampling_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in sampling_rows
        if isinstance(row, Mapping)
    }
    failure_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in failure_rows
        if isinstance(row, Mapping)
    }

    presets_by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for preset in presets:
        payload = preset.to_payload()
        presets_by_hypothesis[str(payload["hypothesis_id"])].append(payload)

    rows: list[dict[str, Any]] = []
    for hypothesis_id, hypothesis_presets in sorted(presets_by_hypothesis.items()):
        behavior_family = str(hypothesis_presets[0].get("behavior_family") or "")
        mapped_coverage = [
            row
            for row in coverage_rows
            if isinstance(row, Mapping) and str(row.get("hypothesis_id") or "") == hypothesis_id
        ]
        mapped_subject_ids = [str(row.get("candidate_id") or "") for row in mapped_coverage]

        source_ready_count = 0
        data_ready_count = 0
        screening_visible_count = 0
        oos_visible_count = 0
        routing_ready_count = 0
        sampling_ready_count = 0
        diagnosable_basket_count = 0
        source_identity_blocked_count = 0
        blocker_codes: list[str] = []
        recommended_actions: list[str] = []

        for row in mapped_coverage:
            evidence = row.get("evidence_presence")
            if not isinstance(evidence, Mapping):
                evidence = {}
            if str(row.get("diagnosis_class") or "") == "diagnosable":
                diagnosable_basket_count += 1
            if bool(evidence.get("source_identity_ready")) and bool(evidence.get("source_quality_ready")):
                source_ready_count += 1
            if (
                bool(evidence.get("source_identity_ready"))
                and bool(evidence.get("source_quality_ready"))
                and bool(evidence.get("cache_ready"))
            ):
                data_ready_count += 1
            if bool(evidence.get("screening_evidence_present")):
                screening_visible_count += 1
            if bool(evidence.get("oos_evidence_known")):
                oos_visible_count += 1
            if str(row.get("source_identity_status") or "") == "candidate_alias_only":
                source_identity_blocked_count += 1
            subject_id = str(row.get("candidate_id") or "")
            routing_row = routing_by_subject.get(subject_id, {})
            sampling_row = sampling_by_subject.get(subject_id, {})
            failure_row = failure_by_subject.get(subject_id, {})
            if str(routing_row.get("routing_readiness_state") or "") == "ready":
                routing_ready_count += 1
            if str(sampling_row.get("sampling_readiness_state") or "") == "ready":
                sampling_ready_count += 1
            blocker = str(failure_row.get("blocker_code") or "")
            if blocker:
                blocker_codes.append(blocker)
            action = str(failure_row.get("recommended_action") or "")
            if action:
                recommended_actions.append(action)

        prior_failure_count = sum(
            1 for action in recommended_actions if action and action != "eligible_for_readonly_routing"
        )
        sufficient_evidence_path = sampling_ready_count > 0 or routing_ready_count > 0
        feasibility_state, explanation = _feasibility_state(
            maps_to_basket_count=len(mapped_coverage),
            source_ready_count=source_ready_count,
            data_ready_count=data_ready_count,
            screening_visible_count=screening_visible_count,
            oos_visible_count=oos_visible_count,
            routing_ready_count=routing_ready_count,
            sampling_ready_count=sampling_ready_count,
            source_identity_blocked_count=source_identity_blocked_count,
            prior_failure_count=prior_failure_count,
        )
        catalog_bridge = active_behavior_map.get(behavior_family)
        rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "behavior_family": behavior_family,
                "supported_preset_mapping": [str(row.get("preset_id") or "") for row in hypothesis_presets],
                "supported_preset_mapping_count": len(hypothesis_presets),
                "catalog_bridge_status": (
                    "linked_catalog_active_discovery"
                    if catalog_bridge
                    else "seed_only_no_executable_hypothesis"
                ),
                "catalog_hypothesis_id": (
                    str(catalog_bridge.get("hypothesis_id") or "") if catalog_bridge else ""
                ),
                "maps_to_basket": len(mapped_coverage) > 0,
                "maps_to_basket_count": len(mapped_coverage),
                "mapped_candidate_ids": mapped_subject_ids,
                "diagnosable_basket_count": diagnosable_basket_count,
                "source_ready": source_ready_count > 0,
                "source_ready_basket_count": source_ready_count,
                "data_ready": data_ready_count > 0,
                "data_ready_basket_count": data_ready_count,
                "screening_visible_basket_count": screening_visible_count,
                "oos_visible_basket_count": oos_visible_count,
                "routing_ready_basket_count": routing_ready_count,
                "sampling_ready_basket_count": sampling_ready_count,
                "prior_failure_count": prior_failure_count,
                "sufficient_evidence_path": sufficient_evidence_path,
                "feasibility_state": feasibility_state,
                "top_blockers": _top_counts(blocker_codes),
                "recommended_follow_up": _reasoned_follow_up(recommended_actions),
                "operator_explanation": explanation,
            }
        )

    feasible_count = sum(
        1 for row in rows if str(row.get("feasibility_state") or "") == "feasible_for_readonly_research"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "hypothesis_seed_count": len(rows),
            "feasible_seed_count": feasible_count,
            "blocked_seed_count": len(rows) - feasible_count,
            "catalog_active_discovery_link_count": sum(
                1
                for row in rows
                if str(row.get("catalog_bridge_status") or "") == "linked_catalog_active_discovery"
            ),
            "seed_only_count": sum(
                1
                for row in rows
                if str(row.get("catalog_bridge_status") or "") == "seed_only_no_executable_hypothesis"
            ),
            "feasibility_state_counts": dict(
                sorted(Counter(str(row["feasibility_state"]) for row in rows).items())
            ),
            "final_recommendation": (
                "hypothesis_seed_feasibility_ready" if rows else "hypothesis_seed_feasibility_missing"
            ),
            "operator_summary": (
                "Hypothesis seed feasibility maps discovery-seed hypotheses to real basket, "
                "source, evidence, routing, sampling, and failure-action state without "
                "unlocking executable strategy changes."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_registry": False,
            "mutates_presets": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def build_behavior_family_coverage(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        rows = []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, Mapping):
            grouped[str(row.get("behavior_family") or "unknown")].append(row)

    coverage_rows: list[dict[str, Any]] = []
    for behavior_family, members in sorted(grouped.items()):
        coverage_rows.append(
            {
                "behavior_family": behavior_family,
                "seed_count": len(members),
                "feasible_seed_count": sum(
                    1
                    for row in members
                    if str(row.get("feasibility_state") or "") == "feasible_for_readonly_research"
                ),
                "blocked_seed_count": sum(
                    1
                    for row in members
                    if str(row.get("feasibility_state") or "") != "feasible_for_readonly_research"
                ),
                "mapped_basket_count": sum(int(row.get("maps_to_basket_count") or 0) for row in members),
                "routing_ready_basket_count": sum(
                    int(row.get("routing_ready_basket_count") or 0) for row in members
                ),
                "sampling_ready_basket_count": sum(
                    int(row.get("sampling_ready_basket_count") or 0) for row in members
                ),
                "source_ready_basket_count": sum(
                    int(row.get("source_ready_basket_count") or 0) for row in members
                ),
                "catalog_active_discovery_link_count": sum(
                    1
                    for row in members
                    if str(row.get("catalog_bridge_status") or "") == "linked_catalog_active_discovery"
                ),
                "top_blockers": _top_counts(
                    [str(blocker.get("value") or "") for row in members for blocker in row.get("top_blockers") or []]
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": BEHAVIOR_REPORT_KIND,
        "summary": {
            "behavior_family_count": len(coverage_rows),
            "behavior_family_with_feasible_seed_count": sum(
                1 for row in coverage_rows if int(row.get("feasible_seed_count") or 0) > 0
            ),
            "behavior_family_with_only_blocked_seed_count": sum(
                1 for row in coverage_rows if int(row.get("feasible_seed_count") or 0) == 0
            ),
            "final_recommendation": (
                "behavior_family_coverage_ready" if coverage_rows else "behavior_family_coverage_missing"
            ),
            "operator_summary": (
                "Behavior family coverage summarizes which discovery-seed behavior families "
                "currently have feasible versus blocked read-only hypothesis paths."
            ),
        },
        "rows": coverage_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path, prefix: str, *, label: str) -> None:
    if prefix not in path.as_posix():
        raise ValueError(f"{label}: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    behavior_report = build_behavior_family_coverage(report)
    main_dir = repo_root / DEFAULT_OUTPUT_DIR
    behavior_dir = repo_root / BEHAVIOR_OUTPUT_DIR
    main_dir.mkdir(parents=True, exist_ok=True)
    behavior_dir.mkdir(parents=True, exist_ok=True)
    latest = main_dir / LATEST_NAME
    behavior_latest = behavior_dir / LATEST_NAME
    _validate_write_target(latest, _WRITE_PREFIX, label="qre_hypothesis_seed_feasibility")
    _validate_write_target(
        behavior_latest,
        _BEHAVIOR_WRITE_PREFIX,
        label="qre_behavior_family_coverage",
    )
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_behavior = behavior_latest.with_suffix(behavior_latest.suffix + ".tmp")
    tmp_behavior.write_text(
        json.dumps(behavior_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_behavior, behavior_latest)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "behavior_family_coverage": behavior_latest.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_hypothesis_seed_feasibility",
        description="Build read-only QRE hypothesis seed feasibility from real basket evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_hypothesis_seed_feasibility(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
