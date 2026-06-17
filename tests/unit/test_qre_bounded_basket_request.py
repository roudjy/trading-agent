from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_bounded_basket_request as request


def _valid_payload() -> dict[str, object]:
    return {
        "request_id": "req-001",
        "symbols": ["NVDA", "AAPL"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "pr-558#approval-manifest",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": [
            "logs/qre_bounded_basket_request/",
            "artifacts/qre_bounded_basket_request/",
        ],
        "forbidden_capabilities": [
            "campaign_launch",
            "strategy_synthesis",
            "provider_activation",
        ],
        "created_at_utc": "2026-06-17T16:00:00Z",
        "source": "operator_approval_manifest",
    }


def test_bounded_basket_request_snapshot_is_valid_and_deterministic() -> None:
    snap1 = request.build_bounded_basket_request_snapshot(_valid_payload())
    snap2 = request.build_bounded_basket_request_snapshot(_valid_payload())

    assert snap1 == snap2
    assert snap1["report_kind"] == "qre_bounded_basket_request"
    assert snap1["validation_status"] == "rejected"
    assert snap1["request"]["symbols"] == ["AAPL", "NVDA"]
    assert snap1["request"]["scope_hash"] == snap2["request"]["scope_hash"]
    assert len(snap1["request"]["scope_hash"]) == 64


def test_bounded_basket_request_from_payload_normalizes_and_hashes() -> None:
    payload = _valid_payload()
    payload["forbidden_capabilities"] = []
    snap = request.build_bounded_basket_request_snapshot(payload)

    assert snap["validation_status"] == "valid"
    assert snap["rejection_reasons"] == []
    assert snap["request"]["symbols"] == ["AAPL", "NVDA"]
    assert snap["request"]["scope_hash"] == request.BoundedBasketRequest.from_payload(payload).scope_hash


def test_bounded_basket_request_scope_hash_is_symbol_order_insensitive() -> None:
    payload_a = _valid_payload()
    payload_b = _valid_payload()
    payload_a["forbidden_capabilities"] = []
    payload_b["forbidden_capabilities"] = []
    payload_a["symbols"] = ["AAPL", "NVDA"]
    payload_b["symbols"] = ["NVDA", "AAPL"]

    hash_a = request.build_bounded_basket_request_snapshot(payload_a)["request"]["scope_hash"]
    hash_b = request.build_bounded_basket_request_snapshot(payload_b)["request"]["scope_hash"]

    assert hash_a == hash_b


@pytest.mark.parametrize(
    "field, value, expected_reason",
    [
        ("symbols", [], "missing_symbols"),
        ("preset_id", "", "missing_preset_id"),
        ("timeframe", "", "missing_timeframe"),
        ("approval_ref", "", "missing_approval_ref"),
    ],
)
def test_bounded_basket_request_fails_closed_on_missing_core_fields(
    field: str,
    value: object,
    expected_reason: str,
) -> None:
    payload = _valid_payload()
    payload["forbidden_capabilities"] = []
    payload[field] = value

    snap = request.build_bounded_basket_request_snapshot(payload)

    assert snap["validation_status"] == "rejected"
    assert expected_reason in snap["rejection_reasons"]


def test_bounded_basket_request_rejects_forbidden_capabilities() -> None:
    payload = _valid_payload()
    payload["forbidden_capabilities"] = ["campaign_queue_mutation"]

    snap = request.build_bounded_basket_request_snapshot(payload)

    assert snap["validation_status"] == "rejected"
    assert "forbidden_capabilities_present" in snap["rejection_reasons"]


def test_bounded_basket_request_rejects_path_violations() -> None:
    payload = _valid_payload()
    payload["forbidden_capabilities"] = []
    payload["allowed_output_paths"] = ["paper/output/"]

    snap = request.build_bounded_basket_request_snapshot(payload)

    assert snap["validation_status"] == "rejected"
    assert "path_violation" in snap["rejection_reasons"]


def test_bounded_basket_request_requires_request_file_for_cli(tmp_path: Path) -> None:
    p = tmp_path / "request.json"
    p.write_text(json.dumps(_valid_payload()), encoding="utf-8")

    exit_code = request.main(["--request-file", str(p)])

    assert exit_code == 0


def test_bounded_basket_request_write_outputs_is_allowlisted(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["forbidden_capabilities"] = []
    report = request.build_bounded_basket_request_snapshot(payload)

    paths = request.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_bounded_basket_request/latest.json"
    assert paths["operator_summary"] == "logs/qre_bounded_basket_request/operator_summary.md"
    assert (tmp_path / "logs" / "qre_bounded_basket_request" / "latest.json").is_file()

