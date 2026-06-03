import ast
from pathlib import Path

from reporting.qre_executable_hypothesis_identity_bridge_contract import (
    build_bridge_index,
    validate_bridge_row,
)


def _authority() -> dict:
    return {
        "available": True,
        "by_hypothesis_id": {
            "qre-hyp-fixture": {
                "status": "linked_exact_ids",
                "hypothesis_id": "qre-hyp-fixture",
                "validation_plan_id": "qre-plan-fixture",
                "run_manifest_id": "qre-run-fixture",
                "warnings": [],
            }
        },
    }


def _row(**overrides: str | None) -> dict:
    row = {
        "executable_hypothesis_id": "trend_pullback_v1",
        "qre_hypothesis_id": "qre-hyp-fixture",
        "source_hypothesis_id": "source-fixture",
        "strategy_family": "trend",
        "strategy_template_id": "trend_pullback",
        "preset_name": "trend_pullback_v1",
        "validation_plan_id": "qre-plan-fixture",
        "run_manifest_id": "qre-run-fixture",
    }
    row.update(overrides)
    return row


def test_exact_bridge_row_validates_safe() -> None:
    result = validate_bridge_row(_row(), qre_authority=_authority())

    assert result["safe_to_bridge"] is True
    assert result["bridge_status"] == "bridge_exact"
    assert result["bridge_warnings"] == []


def test_missing_executable_hypothesis_id_fails_closed() -> None:
    result = validate_bridge_row(
        _row(executable_hypothesis_id=""),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_missing_executable_hypothesis_id"


def test_missing_qre_hypothesis_id_fails_closed() -> None:
    result = validate_bridge_row(
        _row(qre_hypothesis_id=None),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_missing_qre_hypothesis_id"


def test_missing_validation_plan_id_fails_closed() -> None:
    result = validate_bridge_row(
        _row(validation_plan_id=""),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_missing_validation_plan_id"


def test_missing_run_manifest_id_fails_closed() -> None:
    result = validate_bridge_row(
        _row(run_manifest_id=""),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_missing_run_manifest_id"


def test_qre_hypothesis_id_not_in_authority_fails_closed() -> None:
    result = validate_bridge_row(
        _row(qre_hypothesis_id="qre-hyp-missing"),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_qre_hypothesis_id_not_in_authority"


def test_validation_plan_id_mismatch_fails_closed() -> None:
    result = validate_bridge_row(
        _row(validation_plan_id="qre-plan-other"),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_validation_plan_mismatch"


def test_run_manifest_id_mismatch_fails_closed() -> None:
    result = validate_bridge_row(
        _row(run_manifest_id="qre-run-other"),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is False
    assert result["bridge_status"] == "bridge_run_manifest_mismatch"


def test_duplicate_executable_hypothesis_id_with_same_qre_id_is_deterministic() -> None:
    index = build_bridge_index(
        [
            _row(preset_name="a"),
            _row(preset_name="b"),
        ],
        qre_authority=_authority(),
    )

    bridge = index["by_executable_hypothesis_id"]["trend_pullback_v1"]
    assert bridge["safe_to_bridge"] is True
    assert bridge["bridge_status"] == "bridge_exact"
    assert bridge["qre_hypothesis_id"] == "qre-hyp-fixture"
    assert index["bridge_summary"] == {
        "exact_bridge_count": 1,
        "ambiguous_bridge_count": 0,
        "unsafe_bridge_count": 0,
    }


def test_duplicate_executable_hypothesis_id_with_different_qre_id_is_ambiguous() -> None:
    authority = _authority()
    authority["by_hypothesis_id"]["qre-hyp-other"] = {
        "status": "linked_exact_ids",
        "hypothesis_id": "qre-hyp-other",
        "validation_plan_id": "qre-plan-other",
        "run_manifest_id": "qre-run-other",
        "warnings": [],
    }

    index = build_bridge_index(
        [
            _row(),
            _row(
                qre_hypothesis_id="qre-hyp-other",
                validation_plan_id="qre-plan-other",
                run_manifest_id="qre-run-other",
            ),
        ],
        qre_authority=authority,
    )

    bridge = index["by_executable_hypothesis_id"]["trend_pullback_v1"]
    assert bridge["safe_to_bridge"] is False
    assert bridge["bridge_status"] == "bridge_ambiguous_executable_hypothesis_id"
    assert bridge["conflicting_qre_hypothesis_ids"] == [
        "qre-hyp-fixture",
        "qre-hyp-other",
    ]
    assert index["bridge_summary"]["ambiguous_bridge_count"] == 1
    assert index["bridge_summary"]["unsafe_bridge_count"] == 1


def test_contract_output_is_bounded() -> None:
    result = validate_bridge_row(
        _row(source_hypothesis_id="x" * 500),
        qre_authority=_authority(),
    )

    assert result["safe_to_bridge"] is True
    assert len(result["source_hypothesis_id"]) <= 160
    assert set(result) <= {
        "executable_hypothesis_id",
        "qre_hypothesis_id",
        "source_hypothesis_id",
        "strategy_family",
        "strategy_template_id",
        "preset_name",
        "validation_plan_id",
        "run_manifest_id",
        "safe_to_bridge",
        "bridge_status",
        "bridge_warnings",
    }


def test_contract_has_no_forbidden_calls_or_writes() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "reporting"
        / "qre_executable_hypothesis_identity_bridge_contract.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_names = {"open", "exec", "eval", "__import__"}
    forbidden_attrs = {"write", "replace", "unlink", "mkdir", "run", "Popen"}

    assert "subprocess" not in source
    assert "research.run_research" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_names
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attrs
