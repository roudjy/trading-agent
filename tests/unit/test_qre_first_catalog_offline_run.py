from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools import qre_first_catalog_offline_run as first_run

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = REPO_ROOT / "docs/research/qre_offline_dataset_catalog.v1.example.json"
FROZEN_OUTPUTS = ("research/research_latest.json", "research/strategy_matrix.csv")


def test_first_run_command_works_with_admitted_catalog_entry(tmp_path: Path) -> None:
    payload = first_run.run_first_catalog_offline_run(
        catalog_path=CATALOG,
        dataset_id="qre_fixture_dataset",
        hypothesis_id="qre_fixture_hypothesis",
        output_dir=tmp_path,
        run_id="first-admitted",
    )

    assert payload["report_kind"] == "qre_first_catalog_admitted_offline_run"
    assert payload["hypothesis_id"] == "qre_fixture_hypothesis"
    assert payload["dataset_id"] == "qre_fixture_dataset"
    assert payload["dataset_admission"]["decision"] == "admitted"
    assert Path(str(payload["artifact_path"])).parent == tmp_path
    assert Path(str(payload["latest_path"])) == tmp_path / "latest.json"
    assert payload["operator_review"]["offline_eligibility_decision"] == "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH"


def test_first_run_command_works_with_blocked_catalog_entry(tmp_path: Path) -> None:
    payload = first_run.run_first_catalog_offline_run(
        catalog_path=CATALOG,
        dataset_id="qre_blocked_dataset",
        hypothesis_id="qre_fixture_hypothesis",
        output_dir=tmp_path,
        run_id="first-blocked",
    )

    assert payload["dataset_admission"]["decision"] == "blocked"
    assert payload["operator_review"]["offline_eligibility_decision"] in {
        "BLOCKED_DATA_NOT_ADMITTED",
        "BLOCKED_SOURCE_NOT_APPROVED",
    }


def test_first_run_summary_includes_disposition_review_and_authority(tmp_path: Path) -> None:
    payload = first_run.run_first_catalog_offline_run(
        catalog_path=CATALOG,
        dataset_id="qre_fixture_dataset",
        hypothesis_id="qre_fixture_hypothesis",
        output_dir=tmp_path,
        run_id="first-summary",
    )

    assert payload["disposition"]
    assert payload["operator_review"]
    assert payload["authority"]["offline_only"] is True
    assert all(value is False for key, value in payload["authority"].items() if key != "offline_only")


def test_first_run_never_mutates_frozen_outputs(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    first_run.run_first_catalog_offline_run(
        catalog_path=CATALOG,
        dataset_id="qre_fixture_dataset",
        hypothesis_id="qre_fixture_hypothesis",
        output_dir=tmp_path,
        run_id="first-frozen",
    )

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_first_run_cli_emits_json(tmp_path: Path) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "tools/qre_first_catalog_offline_run.py",
            "--catalog",
            str(CATALOG),
            "--dataset-id",
            "qre_fixture_dataset",
            "--hypothesis-id",
            "qre_fixture_hypothesis",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "first-cli",
            "--json",
        ),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)

    assert payload["report_kind"] == "qre_first_catalog_admitted_offline_run"
    assert payload["run_id"] == "first-cli"
    assert payload["dataset_admission"]["decision"] == "admitted"
