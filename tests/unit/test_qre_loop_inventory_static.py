from __future__ import annotations

import json
from pathlib import Path

from tools import qre_loop_inventory_static as inventory


def _write_fixture_repo(root: Path) -> None:
    research = root / "research"
    tests = root / "tests" / "unit"
    docs = root / "docs"
    research.mkdir(parents=True)
    tests.mkdir(parents=True)
    docs.mkdir(parents=True)
    (root / "packages").mkdir()
    (root / "reporting").mkdir()
    (root / "tools").mkdir()
    (research / "__init__.py").write_text("", encoding="utf-8")
    (research / "producer.py").write_text(
        """
from pathlib import Path
import argparse
from research.consumer import read_candidate_status

REPORT_KIND = "qre_fixture_report"
DEFAULT_OUTPUT_PATH = Path("logs/qre_fixture/latest.json")
FROZEN_CONTRACT_PATH = "research/research_latest.json"
STRATEGY_MATRIX_PATH = "research/strategy_matrix.csv"

def build_payload():
    return {"report_kind": REPORT_KIND, "trading_authority": False}

def write_outputs(payload):
    DEFAULT_OUTPUT_PATH.write_text("{}", encoding="utf-8")

def main(argv=None):
    parser = argparse.ArgumentParser()
    return 0
""",
        encoding="utf-8",
    )
    (research / "consumer.py").write_text(
        """
from pathlib import Path

def read_candidate_status(path: Path):
    return path.read_text(encoding="utf-8")

def validation_shadow_paper_live_words():
    return "validation promotion shadow paper live trading_authority"
""",
        encoding="utf-8",
    )
    (research / "explode_on_import.py").write_text(
        "raise RuntimeError('imported runtime module')\nREPORT_KIND = 'bad'\n",
        encoding="utf-8",
    )
    (tests / "test_producer.py").write_text(
        "from research.producer import build_payload\n",
        encoding="utf-8",
    )
    (docs / "producer.md").write_text(
        "research.producer writes logs/qre_fixture/latest.json and references frozen contracts.\n",
        encoding="utf-8",
    )


def _find(payload: dict, kind: str) -> list[dict]:
    return [finding for finding in payload["findings"] if finding["kind"] == kind]


def test_extracts_report_kind_strings(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert any(finding["value"] == "qre_fixture_report" for finding in _find(payload, "report_kind"))


def test_extracts_artifact_path_constants(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    values = {finding["value"] for finding in _find(payload, "artifact_path_constant")}
    assert "logs/qre_fixture/latest.json" in values
    assert "research/research_latest.json" in values
    assert "research/strategy_matrix.csv" in values


def test_detects_write_outputs_functions(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert any(finding["name"] == "write_outputs" for finding in _find(payload, "write_outputs_function"))


def test_detects_argparse_and_main_entrypoints(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert any(finding["name"] == "main" for finding in _find(payload, "main_entrypoint"))
    assert _find(payload, "argparse_entrypoint_reference")


def test_detects_imports_between_local_modules(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    imports = _find(payload, "local_import")
    assert any(finding["name"] == "research.producer" for finding in imports)
    assert any(finding["value"] == "research.consumer" for finding in imports)


def test_detects_frozen_contract_references(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert _find(payload, "frozen_contract_reference")


def test_detects_authority_risk_references(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    names = {finding["name"] for finding in _find(payload, "authority_risk_reference")}
    assert {"trading_authority", "promotion", "validation", "paper", "shadow", "live"} <= names


def test_marks_findings_with_confidence_levels(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert set(payload["confidence_levels"]) == {"verified", "inferred", "unknown"}
    assert all(finding["confidence"] in payload["confidence_levels"] for finding in payload["findings"])
    assert any(finding["confidence"] == "inferred" for finding in payload["findings"])


def test_does_not_execute_imported_research_modules(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    payload = inventory.build_inventory(tmp_path)

    assert payload["safety"]["runtime_modules_imported"] is False
    assert any("explode_on_import.py" in module["path"] for module in payload["modules"])


def test_main_outputs_json_to_stdout(tmp_path: Path, capsys) -> None:
    _write_fixture_repo(tmp_path)

    status = inventory.main(["--repo-root", str(tmp_path)])

    assert status == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == "qre_loop_architecture_inventory_static"
