from __future__ import annotations

from pathlib import Path

from research import qre_bounded_validation_approval_gate as gate


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "request_id": "req-approval-001",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "allowed_output_paths": ["logs/qre_controlled_validation_adapter_results/"],
        "forbidden_capabilities": [],
    }
    payload.update(overrides)
    return payload


def _approval(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_id": "approval-001",
        "approved_by": "operator-001",
        "approved_at_utc": "2026-06-18T18:00:00Z",
        "expires_at_utc": "2026-06-19T18:00:00Z",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "allowed_command_class": "bounded_validation",
        "allowed_output_paths": ["logs/qre_controlled_validation_adapter_results/"],
        "forbidden_capabilities": [],
        "dry_run_allowed": True,
        "real_run_allowed": True,
        "external_fetch_allowed": False,
        "evidence_acceptance_allowed": True,
    }
    payload.update(overrides)
    return payload


def test_missing_approval_blocks() -> None:
    report = gate.build_bounded_validation_approval_gate(None, _request(), evaluated_at_utc="2026-06-18T18:30:00Z")
    assert report["approval_gate_status"] == "blocked_missing_approval"


def test_expired_approval_blocks() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(expires_at_utc="2026-06-18T17:00:00Z"),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    assert report["approval_gate_status"] == "blocked_expired_approval"


def test_scope_mismatch_blocks() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(symbols=["AAPL"]),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    assert report["approval_gate_status"] == "blocked_scope_mismatch"


def test_forbidden_capability_blocks() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(forbidden_capabilities=["strategy_synthesis"]),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    assert report["approval_gate_status"] == "blocked_forbidden_capability"


def test_real_run_blocked_by_default() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(real_run_allowed=False),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    assert report["approval_gate_status"] == "blocked_real_run_not_allowed"


def test_external_fetch_blocked_by_default() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(external_fetch_allowed=False),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
        requested_external_fetch=True,
    )
    assert report["approval_gate_status"] == "blocked_external_fetch_not_allowed"


def test_exact_approval_can_pass() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    validation = gate.validate_approval_gate_result(report)

    assert report["approval_gate_status"] == "approval_valid_for_bounded_validation"
    assert report["can_execute"] is True
    assert validation["valid"] is True


def test_no_shadow_paper_live_or_broker_risk_execution_authority() -> None:
    report = gate.build_bounded_validation_approval_gate(
        _approval(),
        _request(),
        evaluated_at_utc="2026-06-18T18:30:00Z",
    )
    assert report["can_authorize_shadow"] is False
    assert report["can_authorize_paper"] is False
    assert report["can_authorize_live"] is False
    assert report["can_authorize_broker_risk_execution"] is False


def test_output_is_deterministic() -> None:
    first = gate.build_bounded_validation_approval_gate(_approval(), _request(), evaluated_at_utc="2026-06-18T18:30:00Z")
    second = gate.build_bounded_validation_approval_gate(_approval(), _request(), evaluated_at_utc="2026-06-18T18:30:00Z")
    assert first == second
    assert first["hash"] == gate.compute_approval_gate_hash(first)


def test_core_gate_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_bounded_validation_approval_gate.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
