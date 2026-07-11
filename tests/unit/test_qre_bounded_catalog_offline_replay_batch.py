from __future__ import annotations

from pathlib import Path

from packages.qre_research import bounded_catalog_offline_replay_batch as batch

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = REPO_ROOT / "docs/research/qre_offline_dataset_catalog.v1.example.json"
FROZEN_OUTPUTS = ("research/research_latest.json", "research/strategy_matrix.csv")


def _budget(**updates: int) -> batch.BatchBudget:
    values = {
        "max_runs": 4,
        "max_admitted_runs": 3,
        "max_blocked_runs": 2,
        "per_dataset": 2,
        "per_hypothesis": 2,
    }
    values.update(updates)
    return batch.BatchBudget(**values)


def _item(run_id: str, dataset_id: str = "qre_fixture_dataset", hypothesis_id: str = "hypothesis") -> batch.BatchPlanItem:
    return batch.BatchPlanItem(run_id, hypothesis_id, dataset_id)


def test_batch_respects_max_runs(tmp_path: Path) -> None:
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-max",
        catalog_path=CATALOG,
        plan=(_item("run-1"), _item("run-2", hypothesis_id="hypothesis-2")),
        budget=_budget(max_runs=1),
        output_dir=tmp_path,
    ).as_dict()

    assert len(result["admitted_runs"]) == 1
    assert result["skipped_runs"][0]["reason_codes"] == ["campaign_budget_exceeded"]


def test_batch_respects_dataset_and_hypothesis_budgets(tmp_path: Path) -> None:
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-budget",
        catalog_path=CATALOG,
        plan=(_item("run-1"), _item("run-2"), _item("run-3", hypothesis_id="hypothesis-3")),
        budget=_budget(per_dataset=1, per_hypothesis=1),
        output_dir=tmp_path,
    ).as_dict()

    assert result["operator_summary"]["admitted_count"] == 1
    assert {run["reason_codes"][0] for run in result["skipped_runs"]} >= {"per_dataset_budget_exceeded"}


def test_blocked_catalog_entries_produce_blocked_runs(tmp_path: Path) -> None:
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-blocked",
        catalog_path=CATALOG,
        plan=(_item("run-blocked", dataset_id="qre_blocked_dataset"),),
        budget=_budget(),
        output_dir=tmp_path,
    ).as_dict()

    assert result["operator_summary"]["blocked_count"] == 1
    assert result["blocked_runs"][0]["operator_review_decision"] in {
        "BLOCKED_DATA_NOT_ADMITTED",
        "BLOCKED_SOURCE_NOT_APPROVED",
    }


def test_duplicate_and_do_not_retest_are_skipped(tmp_path: Path) -> None:
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-skip",
        catalog_path=CATALOG,
        plan=(_item("run-1"), _item("run-1"), _item("run-2", hypothesis_id="do-not")),
        budget=_budget(),
        output_dir=tmp_path,
        do_not_retest=("do-not",),
    ).as_dict()

    assert [run["reason_codes"][0] for run in result["skipped_runs"]] == [
        "duplicate_active_research_path",
        "do_not_retest",
    ]


def test_batch_indexes_artifacts_and_writes_only_to_output_dir(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-index",
        catalog_path=CATALOG,
        plan=(_item("run-1"), _item("run-blocked", dataset_id="qre_blocked_dataset")),
        budget=_budget(),
        output_dir=tmp_path,
    ).as_dict()

    assert len(result["artifact_references"]) == 2
    assert Path(str(result["run_registry_path"])).parent == tmp_path / "registry"
    assert result["run_registry"]["entries"]
    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_batch_denies_execution_authority_and_produces_operator_summary(tmp_path: Path) -> None:
    result = batch.run_bounded_catalog_replay_batch(
        batch_id="batch-authority",
        catalog_path=CATALOG,
        plan=(_item("run-1"),),
        budget=_budget(),
        output_dir=tmp_path,
    ).as_dict()

    assert result["operator_summary"]["admitted_count"] == 1
    assert "next_action_queue" in result
    assert result["authority"]["offline_only"] is True
    assert all(value is False for key, value in result["authority"].items() if key != "offline_only")
