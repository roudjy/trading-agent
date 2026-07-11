from __future__ import annotations

from pathlib import Path

from packages.qre_research import governed_offline_research_runner as runner
from packages.qre_research import governed_offline_run_registry as registry

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = ("research/research_latest.json", "research/strategy_matrix.csv")


def _run(tmp_path: Path, run_id: str, dataset_admitted: bool = True) -> Path:
    payload = runner.run_governed_offline_research(
        hypothesis_id=f"hypothesis-{run_id}",
        dataset_id=f"dataset-{run_id}",
        output_dir=tmp_path,
        run_id=run_id,
        dataset_admitted=dataset_admitted,
    ).as_dict()
    return Path(str(payload["artifact_path"]))


def test_registry_builds_from_one_artifact(tmp_path: Path) -> None:
    artifact = _run(tmp_path, "run-one")
    index = registry.build_run_registry((artifact,))
    entry = index.entries[0].as_dict()

    assert entry["run_id"] == "run-one-closure"
    assert entry["hypothesis_id"] == "hypothesis-run-one"
    assert entry["dataset_id"] == "dataset-run-one"
    assert entry["eligible_for_more_offline_research"] is True


def test_registry_builds_from_multiple_artifacts_and_deduplicates(tmp_path: Path) -> None:
    first = _run(tmp_path, "run-a")
    second = _run(tmp_path, "run-b", dataset_admitted=False)
    index = registry.build_run_registry((first, second, first))

    assert [entry.as_dict()["run_id"] for entry in index.entries] == ["run-a-closure", "run-b-closure"]


def test_registry_preserves_blocked_lineage_and_do_not_retest(tmp_path: Path) -> None:
    artifact = _run(tmp_path, "run-blocked", dataset_admitted=False)
    entry = registry.build_run_registry((artifact,)).entries[0].as_dict()

    assert entry["dataset_admission_status"] == "BLOCKED"
    assert entry["negative_evidence_count"] >= 1
    assert entry["rejection_reason_codes"]
    assert "do_not_retest" in entry


def test_fixture_and_sample_modes_are_not_production_evidence(tmp_path: Path) -> None:
    entry = registry.build_run_registry((_run(tmp_path, "run-fixture"),)).entries[0].as_dict()

    assert entry["source_mode"] == "offline_fixture"
    assert entry["fixture_or_sample_not_production_evidence"] is True
    assert entry["authority"]["production_empirical_evidence"] is False


def test_registry_writes_only_to_tmp_path_and_protects_frozen_outputs(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    index = registry.build_run_registry((_run(tmp_path, "run-write"),))
    path = registry.write_run_registry(index, tmp_path / "registry")

    assert path == tmp_path / "registry" / "governed_offline_run_registry.json"
    assert path.exists()
    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_registry_denies_all_execution_authority(tmp_path: Path) -> None:
    index = registry.build_run_registry((_run(tmp_path, "run-authority"),))

    assert registry.validate_registry(index) == []
    for key, value in index.as_dict()["authority"].items():
        if key != "offline_only":
            assert value is False
