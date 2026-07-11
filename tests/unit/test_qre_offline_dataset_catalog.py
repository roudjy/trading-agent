from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from packages.qre_research import governed_offline_research_runner as runner
from packages.qre_research import offline_dataset_catalog as catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = ("research/research_latest.json", "research/strategy_matrix.csv")


def _entry(**updates: object) -> dict[str, object]:
    data: dict[str, object] = {
        "dataset_id": "dataset-admitted",
        "name": "fixture dataset",
        "source_mode": "offline_fixture",
        "provider_or_source": "fixture",
        "source_identity": "fixture-source",
        "symbol_scope": ["FIXTURE"],
        "timeframe": "1h",
        "date_range": {"start": "2026-01-01", "end": "2026-01-02"},
        "local_reference": "fixtures/qre/offline/dataset.json",
        "dataset_fingerprint": "offline_fixture:dataset-admitted:deterministic",
        "quality_status": "passed",
        "admission_status": "ADMITTED",
        "block_reasons": [],
        "operator_notes": "fixture only",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "authority": catalog.authority_denial(),
    }
    data.update(updates)
    return data


def _catalog_path(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps({"schema_version": 1, "report_kind": catalog.REPORT_KIND, "entries": list(entries)}),
        encoding="utf-8",
    )
    return path


def test_valid_admitted_dataset_loads(tmp_path: Path) -> None:
    loaded = catalog.load_catalog(_catalog_path(tmp_path, _entry()))
    entry = loaded.lookup("dataset-admitted")

    assert entry.admission_decision()["decision"] == "admitted"
    assert entry.admission_decision()["dataset_fingerprint"] == "offline_fixture:dataset-admitted:deterministic"


def test_blocked_dataset_loads_and_blocks_runner(tmp_path: Path) -> None:
    catalog_path = _catalog_path(
        tmp_path,
        _entry(
            dataset_id="dataset-blocked",
            admission_status="BLOCKED",
            quality_status="failed",
            dataset_fingerprint="",
            block_reasons=["BLOCKED_DATA_NOT_ADMITTED"],
        ),
    )
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis",
        dataset_id="dataset-blocked",
        dataset_catalog_path=catalog_path,
        output_dir=tmp_path / "out",
    ).as_dict()

    assert result["dataset_admission"]["decision"] == "blocked"
    assert result["dataset_admission"]["catalog_decision"]["decision_reason"] == "BLOCKED_DATA_NOT_ADMITTED"
    assert result["eligible_for_more_offline_research"] is False


def test_review_required_dataset_does_not_run_as_admitted(tmp_path: Path) -> None:
    loaded = catalog.load_catalog(
        _catalog_path(
            tmp_path,
            _entry(
                admission_status="REVIEW_REQUIRED",
                block_reasons=["operator_decision_required"],
            ),
        )
    )

    assert loaded.lookup("dataset-admitted").admission_decision()["decision"] == "blocked"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"dataset_fingerprint": ""}, "missing_dataset_fingerprint"),
        ({"source_identity": ""}, "missing_source_identity"),
        ({"source_mode": "live_provider"}, "unknown_source_mode"),
        ({"admission_status": "READY"}, "unknown_admission_status"),
    ],
)
def test_invalid_catalog_entries_fail_validation(
    tmp_path: Path,
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        catalog.load_catalog(_catalog_path(tmp_path, _entry(**updates)))


def test_runner_accepts_dataset_catalog_for_admitted_entry(tmp_path: Path) -> None:
    result = runner.run_governed_offline_research(
        hypothesis_id="hypothesis",
        dataset_id="dataset-admitted",
        dataset_catalog_path=_catalog_path(tmp_path, _entry()),
        output_dir=tmp_path / "out",
    ).as_dict()

    assert result["dataset_admission"]["decision"] == "admitted"
    assert result["dataset_fingerprint"] == "offline_fixture:dataset-admitted:deterministic"
    assert all(value is False for key, value in result["authority"].items() if key != "offline_only")


def test_cli_accepts_dataset_catalog(tmp_path: Path) -> None:
    catalog_path = _catalog_path(tmp_path, _entry())
    completed = subprocess.run(
        (
            sys.executable,
            "tools/qre_governed_offline_research_run.py",
            "--hypothesis-id",
            "hypothesis-cli",
            "--dataset-id",
            "dataset-admitted",
            "--dataset-catalog",
            str(catalog_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--json",
        ),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)

    assert payload["dataset_admission"]["decision"] == "admitted"
    assert payload["dataset_admission"]["catalog_decision"]["decision_reason"] == "ADMITTED"


def test_catalog_runner_does_not_mutate_frozen_outputs(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    runner.run_governed_offline_research(
        hypothesis_id="hypothesis",
        dataset_id="dataset-admitted",
        dataset_catalog_path=_catalog_path(tmp_path, _entry()),
        output_dir=tmp_path / "out",
    )

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before
