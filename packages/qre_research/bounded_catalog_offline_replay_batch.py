"""Bounded catalog-based governed offline replay batch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.qre_research import governed_offline_research_runner as runner
from packages.qre_research import governed_offline_run_registry as run_registry
from packages.qre_research import offline_dataset_catalog as catalog


@dataclass(frozen=True, slots=True)
class BatchBudget:
    max_runs: int
    max_admitted_runs: int
    max_blocked_runs: int
    per_dataset: int
    per_hypothesis: int


@dataclass(frozen=True, slots=True)
class BatchPlanItem:
    run_id: str
    hypothesis_id: str
    dataset_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "hypothesis_id": self.hypothesis_id,
            "dataset_id": self.dataset_id,
        }


@dataclass(frozen=True, slots=True)
class BoundedCatalogReplayBatch:
    payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return dict(self.payload)


def _authority() -> dict[str, bool]:
    return {
        "offline_only": True,
        "strategy_synthesis_authority": False,
        "shadow_authority": False,
        "paper_authority": False,
        "live_authority": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
    }


def run_bounded_catalog_replay_batch(
    *,
    batch_id: str,
    catalog_path: Path,
    plan: tuple[BatchPlanItem, ...],
    budget: BatchBudget,
    output_dir: Path,
    do_not_retest: tuple[str, ...] = (),
) -> BoundedCatalogReplayBatch:
    loaded_catalog = catalog.load_catalog(catalog_path)
    seen_runs: set[str] = set()
    per_dataset: dict[str, int] = {}
    per_hypothesis: dict[str, int] = {}
    admitted_count = 0
    blocked_count = 0
    admitted_runs: list[dict[str, object]] = []
    blocked_runs: list[dict[str, object]] = []
    skipped_runs: list[dict[str, object]] = []
    artifact_paths: list[Path] = []

    for item in plan:
        if item.run_id in seen_runs:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["duplicate_active_research_path"]})
            continue
        if item.hypothesis_id in do_not_retest:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["do_not_retest"]})
            continue
        if len(admitted_runs) + len(blocked_runs) >= budget.max_runs:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["campaign_budget_exceeded"]})
            continue
        if per_dataset.get(item.dataset_id, 0) >= budget.per_dataset:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["per_dataset_budget_exceeded"]})
            continue
        if per_hypothesis.get(item.hypothesis_id, 0) >= budget.per_hypothesis:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["per_hypothesis_budget_exceeded"]})
            continue

        entry = loaded_catalog.lookup(item.dataset_id)
        decision = entry.admission_decision()
        would_admit = decision["decision"] == "admitted"
        if would_admit and admitted_count >= budget.max_admitted_runs:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["admitted_run_budget_exceeded"]})
            continue
        if not would_admit and blocked_count >= budget.max_blocked_runs:
            skipped_runs.append({"run_id": item.run_id, "reason_codes": ["blocked_run_budget_exceeded"]})
            continue

        result = runner.run_governed_offline_research(
            hypothesis_id=item.hypothesis_id,
            dataset_id=item.dataset_id,
            dataset_catalog_path=catalog_path,
            output_dir=output_dir,
            run_id=item.run_id,
        ).as_dict()
        artifact_paths.append(Path(str(result["artifact_path"])))
        row = {
            "run_id": item.run_id,
            "hypothesis_id": item.hypothesis_id,
            "dataset_id": item.dataset_id,
            "artifact_path": result["artifact_path"],
            "operator_review_decision": result["operator_review"]["offline_eligibility_decision"],
            "reason_codes": [
                reason["code"] for reason in result["rejection_reasons"] if isinstance(reason, dict)
            ],
        }
        if would_admit:
            admitted_count += 1
            admitted_runs.append(row)
        else:
            blocked_count += 1
            blocked_runs.append(row)
        seen_runs.add(item.run_id)
        per_dataset[item.dataset_id] = per_dataset.get(item.dataset_id, 0) + 1
        per_hypothesis[item.hypothesis_id] = per_hypothesis.get(item.hypothesis_id, 0) + 1

    index = run_registry.build_run_registry(tuple(artifact_paths)) if artifact_paths else run_registry.OfflineRunRegistry(())
    registry_path = run_registry.write_run_registry(index, output_dir / "registry")
    next_action_queue = [
        run["operator_review_decision"]
        for run in [*admitted_runs, *blocked_runs]
        if run["operator_review_decision"] != "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH"
    ]
    payload = {
        "schema_version": 1,
        "report_kind": "qre_bounded_catalog_offline_replay_batch",
        "batch_id": batch_id,
        "batch_plan": [item.as_dict() for item in plan],
        "admitted_runs": admitted_runs,
        "blocked_runs": blocked_runs,
        "skipped_runs": skipped_runs,
        "reason_codes": sorted(
            {code for run in [*admitted_runs, *blocked_runs, *skipped_runs] for code in run["reason_codes"]}
        ),
        "artifact_references": [path.as_posix() for path in artifact_paths],
        "run_registry": index.as_dict(),
        "run_registry_path": registry_path.as_posix(),
        "operator_summary": {
            "admitted_count": len(admitted_runs),
            "blocked_count": len(blocked_runs),
            "skipped_count": len(skipped_runs),
        },
        "next_action_queue": next_action_queue,
        "do_not_retest": list(do_not_retest),
        "eligible_for_more_offline_research_count": sum(
            1 for entry in index.entries if entry.as_dict()["eligible_for_more_offline_research"]
        ),
        "authority": _authority(),
    }
    return BoundedCatalogReplayBatch(payload)


__all__ = [
    "BatchBudget",
    "BatchPlanItem",
    "BoundedCatalogReplayBatch",
    "run_bounded_catalog_replay_batch",
]
