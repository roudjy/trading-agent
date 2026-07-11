from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from packages.qre_research import governed_offline_research_runner as runner

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def test_runner_orchestrates_admitted_dataset_path(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis-admitted",
        dataset_id="dataset-admitted",
        output_dir=tmp_path,
        run_id="run-admitted",
    ).as_dict()

    assert result["report_kind"] == runner.REPORT_KIND
    assert result["dataset_admission"]["decision"] == "admitted"
    assert result["artifact_path"] == (tmp_path / "run-admitted-closure.json").as_posix()
    assert result["latest_path"] == (tmp_path / "latest.json").as_posix()
    assert result["operator_review"]["offline_eligibility_decision"] == "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH"
    assert result["eligible_for_more_offline_research"] is True


def test_runner_handles_blocked_dataset_path(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis-blocked",
        dataset_id="dataset-blocked",
        output_dir=tmp_path,
        run_id="run-blocked",
        dataset_admitted=False,
        source_approved=False,
    ).as_dict()

    assert result["dataset_admission"]["decision"] == "blocked"
    assert result["operator_review"]["offline_eligibility_decision"] in {
        "BLOCKED_DATA_NOT_ADMITTED",
        "BLOCKED_SOURCE_NOT_APPROVED",
    }
    assert result["eligible_for_more_offline_research"] is False


def test_runner_preserves_fingerprint_provenance_windows_and_evidence(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis-evidence",
        dataset_id="dataset-evidence",
        output_dir=tmp_path,
        run_id="run-evidence",
        window_statuses={"out_of_sample": "missing", "null_model": "failed"},
    ).as_dict()

    assert result["dataset_fingerprint"] == "offline_fixture:dataset-evidence:deterministic"
    assert result["stage_records"]
    assert {window["name"] for window in result["evidence_windows"]} >= {"out_of_sample", "null_model"}
    assert "oos_not_available" in result["evidence_summary"]["missing_evidence"]
    assert "null_model_not_beaten" in result["evidence_summary"]["negative_evidence"]
    assert result["memory_feedback"]["records"]


def test_runner_writes_only_to_output_dir_and_latest_inside_output_dir(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis-output",
        dataset_id="dataset-output",
        output_dir=tmp_path,
        run_id="run-output",
    ).as_dict()

    artifact = Path(str(result["artifact_path"]))
    latest = Path(str(result["latest_path"]))
    assert artifact.parent == tmp_path
    assert latest == tmp_path / "latest.json"
    assert artifact.exists()
    assert latest.exists()


def test_runner_never_mutates_frozen_outputs(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    runner.run_governed_offline_research(
        hypothesis_id="hypothesis-frozen",
        dataset_id="dataset-frozen",
        output_dir=tmp_path,
        run_id="run-frozen",
    )

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_runner_denies_all_execution_authority(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis-authority",
        dataset_id="dataset-authority",
        output_dir=tmp_path,
        run_id="run-authority",
    ).as_dict()

    assert result["authority"]["offline_only"] is True
    for key, value in result["authority"].items():
        if key != "offline_only":
            assert value is False


def test_cli_emits_json_output(tmp_path: Path) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "tools/qre_governed_offline_research_run.py",
            "--hypothesis-id",
            "hypothesis-cli",
            "--dataset-id",
            "dataset-cli",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "run-cli",
            "--json",
        ),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == runner.REPORT_KIND
    assert payload["run_id"] == "run-cli"
    assert payload["operator_review"]
