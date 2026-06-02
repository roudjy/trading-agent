from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from reporting import qre_validation_source_linkage_contract as contract

FROZEN = "2026-06-01T12:00:00Z"


def _compliant_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "validation_plan_id": "qre-plan-fixture-001",
        "run_manifest_id": "qre-run-fixture-001",
        "source_artifact": "research/screening_evidence_latest.v1.json",
        "source_report_kind": "screening_evidence",
        "source_row_id": "candidate-001",
    }
    row.update(overrides)
    return row


def _assert_fails_with(row: object, reason: str, missing_field: str | None = None) -> dict:
    result = contract.validate_source_linkage_contract(row)  # type: ignore[arg-type]
    assert result["is_contract_compliant"] is False
    assert result["safe_to_link"] is False
    assert reason in result["reason_codes"]
    if missing_field is not None:
        assert missing_field in result["missing_required_fields"]
    return result


def test_compliant_row_with_all_required_exact_ids_is_safe_to_link() -> None:
    result = contract.validate_source_linkage_contract(_compliant_row(candidate_id="candidate-001"))

    assert result["contract_version"] == contract.CONTRACT_VERSION
    assert result["is_contract_compliant"] is True
    assert result["safe_to_link"] is True
    assert result["missing_required_fields"] == []
    assert result["present_required_fields"] == list(contract.REQUIRED_LINKAGE_FIELDS)
    assert result["present_context_fields"] == ["candidate_id"]
    assert result["primary_linkage_mode"] == "exact_ids"
    assert result["reason_codes"] == ["contract_compliant_exact_ids"]


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("hypothesis_id", "missing_hypothesis_id"),
        ("validation_plan_id", "missing_validation_plan_id"),
        ("run_manifest_id", "missing_run_manifest_id"),
        ("source_artifact", "missing_source_artifact"),
        ("source_report_kind", "missing_source_report_kind"),
        ("source_row_id", "missing_source_row_id"),
    ],
)
def test_missing_required_exact_fields_fail_closed(field: str, reason: str) -> None:
    row = _compliant_row()
    row.pop(field)

    result = _assert_fails_with(row, reason, field)

    assert "unsupported_primary_linkage_mode" in result["reason_codes"]
    assert result["primary_linkage_mode"] == "incomplete_exact_ids"


@pytest.mark.parametrize("field", contract.REQUIRED_LINKAGE_FIELDS)
def test_empty_required_fields_fail_closed(field: str) -> None:
    result = _assert_fails_with(
        _compliant_row(**{field: "   "}),
        "empty_required_field",
        field,
    )

    assert f"missing_{field}" in result["reason_codes"]


def test_malformed_non_dict_row_fails_closed() -> None:
    result = _assert_fails_with(["not", "a", "mapping"], "malformed_source_row")

    assert result["missing_required_fields"] == list(contract.REQUIRED_LINKAGE_FIELDS)
    assert result["primary_linkage_mode"] == "malformed_source_row"
    assert result["field_value_summaries"] == {}


def test_required_field_with_container_value_fails_closed() -> None:
    result = _assert_fails_with(
        _compliant_row(source_row_id={"nested": "not allowed"}),
        "malformed_source_row",
        "source_row_id",
    )

    assert result["field_value_summaries"]["source_row_id"] == "<malformed>"


def test_candidate_id_only_row_is_not_compliant() -> None:
    result = _assert_fails_with(
        {"candidate_id": "candidate-001"},
        "candidate_id_context_only_not_allowed",
    )

    assert result["present_context_fields"] == ["candidate_id"]
    assert result["primary_linkage_mode"] == "context_only"


def test_asset_timeframe_only_row_is_not_compliant() -> None:
    result = _assert_fails_with(
        {"asset": "BTC-USD", "timeframe": "1h"},
        "asset_timeframe_only_not_allowed",
    )

    assert result["forbidden_primary_only_fields"] == ["asset", "timeframe"]
    assert result["primary_linkage_mode"] == "forbidden_context_only"


def test_symbol_timeframe_only_row_is_not_compliant() -> None:
    result = _assert_fails_with(
        {"symbol": "BTC-USD", "timeframe": "1h"},
        "symbol_timeframe_only_not_allowed",
    )

    assert result["forbidden_primary_only_fields"] == ["symbol", "timeframe"]


def test_strategy_id_only_row_is_not_compliant() -> None:
    result = _assert_fails_with(
        {"strategy_id": "trend_pullback"},
        "strategy_context_only_not_allowed",
    )

    assert result["forbidden_primary_only_fields"] == ["strategy_id"]


def test_plan_id_does_not_substitute_for_validation_plan_id() -> None:
    row = _compliant_row()
    row.pop("validation_plan_id")
    row["plan_id"] = "qre-plan-fixture-001"

    result = _assert_fails_with(row, "missing_validation_plan_id", "validation_plan_id")

    assert "plan_id" in result["present_context_fields"]
    assert "validation_plan_id" not in result["present_required_fields"]


def test_run_id_does_not_substitute_for_run_manifest_id() -> None:
    row = _compliant_row()
    row.pop("run_manifest_id")
    row["run_id"] = "qre-run-fixture-001"

    result = _assert_fails_with(row, "missing_run_manifest_id", "run_manifest_id")

    assert "run_id" in result["present_context_fields"]
    assert "run_manifest_id" not in result["present_required_fields"]


def test_output_uses_closed_reason_codes() -> None:
    rows = [
        _compliant_row(),
        {},
        {"candidate_id": "candidate-001"},
        {"asset": "BTC-USD", "timeframe": "1h"},
        {"symbol": "BTC-USD", "timeframe": "1h"},
        {"strategy_id": "trend_pullback"},
        _compliant_row(source_row_id=[]),
    ]

    allowed = set(contract.REASON_CODE_VOCABULARY)
    for row in rows:
        result = contract.validate_source_linkage_contract(row)
        assert set(result["reason_codes"]) <= allowed


def test_output_remains_bounded_and_truncated() -> None:
    long_value = "x" * 1000
    result = contract.validate_source_linkage_contract(
        _compliant_row(
            hypothesis_id=long_value,
            candidate_id=long_value,
            asset=long_value,
        )
    )

    encoded = json.dumps(result, sort_keys=True)
    assert len(encoded) < 2500
    assert long_value not in encoded
    assert result["field_value_summaries"]["hypothesis_id"].endswith("...")
    assert len(result["field_value_summaries"]["hypothesis_id"]) <= 96


def test_report_schema_and_examples_are_bounded() -> None:
    report = contract.build_source_linkage_contract_report(generated_at_utc=FROZEN)

    assert report["report_kind"] == contract.REPORT_KIND
    assert report["schema_version"] == contract.SCHEMA_VERSION
    assert report["contract_version"] == contract.CONTRACT_VERSION
    assert report["safe_to_execute"] is False
    assert report["read_only"] is True
    assert report["required_linkage_fields"] == list(contract.REQUIRED_LINKAGE_FIELDS)
    assert report["context_linkage_fields"] == list(contract.CONTEXT_LINKAGE_FIELDS)
    assert report["forbidden_primary_linkage_fields"] == list(
        contract.FORBIDDEN_PRIMARY_LINKAGE_FIELDS
    )
    assert report["reason_code_vocabulary"] == list(contract.REASON_CODE_VOCABULARY)
    assert set(report["examples"]) == {
        "compliant_exact_ids",
        "rejected_asset_timeframe_only",
        "rejected_candidate_id_only",
        "rejected_missing_run_manifest_id",
    }
    assert len(json.dumps(report["examples"], sort_keys=True)) < 7000


def test_report_writer_writes_only_contract_latest_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_dir = tmp_path / "logs" / contract.REPORT_KIND
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(contract, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(contract, "ARTIFACT_LATEST", latest)
    report = contract.build_source_linkage_contract_report(generated_at_utc=FROZEN)

    written = contract.write_source_linkage_contract_report(report)

    assert written == latest
    assert latest.exists()
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json")] == [
        "logs/qre_validation_source_linkage_contract/latest.json"
    ]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["safe_to_execute"] is False
    assert payload["read_only"] is True
    assert "required_linkage_fields" in payload
    assert "context_linkage_fields" in payload
    assert "forbidden_primary_linkage_fields" in payload
    assert "reason_code_vocabulary" in payload
    with pytest.raises(ValueError):
        contract.write_source_linkage_contract_report(report, output_path=tmp_path / "outside.json")


def test_forbidden_calls_imports_and_mutating_paths_absent() -> None:
    src = Path(contract.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules: set[str] = set()
    forbidden_runtime_modules = (
        "broker",
        "live",
        "paper",
        "shadow",
        "risk",
        "trading",
        "execution",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                assert (func.value.id, func.attr) != ("os", "system")
                assert func.value.id != "subprocess"

    assert "subprocess" not in imported_modules
    for module in imported_modules:
        root = module.split(".")[0]
        assert root not in forbidden_runtime_modules
    for token in (
        "generated_seed.jsonl",
        "seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "agent/backtesting/strategies.py",
        "registry.py",
        "research/research_latest.json",
        "strategy_matrix.csv",
        "codex",
    ):
        assert token not in src
