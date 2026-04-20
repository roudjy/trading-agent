"""Integration test for the v3.5 integrity + falsification sidecars.

Exercises the payload-builders against a realistic candidate shape
and pins:

(a) the v1 schema surface of `integrity_report_latest.v1.json` and
    `falsification_gates_latest.v1.json`;

(b) the D4 boundary — neither sidecar emits a `status` field anywhere
    alongside a candidate record (promotion remains the sole decision
    authority);

(c) the `feature_version` / `evaluation_version` fields exposed on
    the run manifest, confirming the manifest is additive v3.5-aware
    without touching the frozen `research_latest.json` surface.

End-to-end byte-equality of `research_latest.json` against a pre-v3.5
snapshot is out of scope here because no existing fixture captures
that state. The public output contract regression
(tests/regression/test_public_output_contract.py) pins the frozen
row / JSON schemas instead; together with the bytewise Tier 1 pins
they provide the same numerical guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent.backtesting.features import FEATURE_VERSION
from research.falsification import (
    check_corrected_significance,
    check_fee_drag_ratio,
    check_low_trade_count,
    check_oos_collapse,
)
from research.falsification_reporting import (
    SIDECAR_VERSION as FALSIFICATION_SIDECAR_VERSION,
    build_candidate_gate_record,
    build_falsification_payload,
)
from research.integrity import (
    FEATURE_INCOMPLETE,
    IntegrityCheck,
    IntegrityReport,
    STRATEGY_NOT_APPLICABLE,
)
from research.integrity_reporting import (
    SIDECAR_VERSION as INTEGRITY_SIDECAR_VERSION,
    build_integrity_report_payload,
)


AS_OF = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)


def _integrity_payload() -> dict:
    report = IntegrityReport()
    report.record(
        IntegrityCheck(
            name="eligibility[pairs_zscore|BTC/EUR|1h]",
            passed=False,
            reason_code=STRATEGY_NOT_APPLICABLE,
            details={"strategy_name": "pairs_zscore", "asset": "BTC/EUR", "interval": "1h"},
        )
    )
    report.record(
        IntegrityCheck(
            name="eligibility[sma_crossover|ETH/EUR|1h]",
            passed=False,
            reason_code=FEATURE_INCOMPLETE,
            details={"strategy_name": "sma_crossover", "asset": "ETH/EUR", "interval": "1h"},
        )
    )
    report.record(
        IntegrityCheck(
            name="eligibility[sma_crossover|BTC/EUR|1h]",
            passed=True,
            details={"strategy_name": "sma_crossover", "asset": "BTC/EUR", "interval": "1h"},
        )
    )
    return build_integrity_report_payload(
        run_id="run-int-test",
        as_of_utc=AS_OF,
        config_hash="cfg-abc",
        git_revision="deadbeef",
        feature_version=FEATURE_VERSION,
        evaluation_version="1.0",
        report=report,
    )


def _falsification_payload() -> dict:
    oos_summary = {"totaal_trades": 45, "sharpe": 0.6, "gross_return": 0.12}
    is_summary = {"sharpe": 1.0}
    verdicts = [
        check_low_trade_count(oos_summary, threshold=30),
        check_oos_collapse(is_summary, oos_summary),
        check_fee_drag_ratio(oos_summary, cost_per_side=0.0035),
        check_corrected_significance({"psr": 0.92, "dsr_canonical": 0.1}),
    ]
    record = build_candidate_gate_record(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        selected_params={"fast_window": 10, "slow_window": 50},
        sizing_regime="fixed_unit",
        verdicts=verdicts,
    )
    return build_falsification_payload(
        run_id="run-int-test",
        as_of_utc=AS_OF,
        candidate_records=[record],
    )


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)


def test_integrity_sidecar_carries_expected_top_level_schema():
    payload = _integrity_payload()

    assert payload["version"] == INTEGRITY_SIDECAR_VERSION
    assert payload["run_id"] == "run-int-test"
    assert payload["feature_version"] == FEATURE_VERSION
    assert payload["evaluation_version"] == "1.0"
    assert payload["config_hash"] == "cfg-abc"
    assert payload["git_revision"] == "deadbeef"
    assert "checks" in payload
    assert "rejection_counts_by_reason" in payload
    assert "summary" in payload
    assert "generated_at_utc" in payload


def test_integrity_sidecar_aggregates_rejection_counts_by_reason_code():
    payload = _integrity_payload()

    counts = payload["rejection_counts_by_reason"]
    assert counts[STRATEGY_NOT_APPLICABLE] == 1
    assert counts[FEATURE_INCOMPLETE] == 1


def test_integrity_sidecar_summary_matches_checks_length():
    payload = _integrity_payload()

    assert payload["summary"]["total_checks"] == len(payload["checks"])
    assert payload["summary"]["failed_checks"] + payload["summary"]["passed_checks"] == len(payload["checks"])


def test_falsification_sidecar_carries_expected_top_level_schema():
    payload = _falsification_payload()

    assert payload["version"] == FALSIFICATION_SIDECAR_VERSION
    assert payload["run_id"] == "run-int-test"
    assert "note" in payload and "promotion" in payload["note"].lower()
    assert "candidates" in payload
    assert "summary" in payload
    assert "generated_at_utc" in payload


def test_falsification_sidecar_records_gate_kind_for_every_gate():
    payload = _falsification_payload()

    for record in payload["candidates"]:
        for gate in record["gates"]:
            assert gate["gate_kind"] in {"heuristic", "statistical", "structural"}


def test_falsification_sidecar_reports_sizing_regime_fixed_unit_for_v35_tier1():
    """v3.5 scaffolding: every Tier 1 candidate reports 'fixed_unit'."""
    payload = _falsification_payload()

    for record in payload["candidates"]:
        assert record["sizing_regime"] == "fixed_unit"


def test_fee_drag_gate_in_sidecar_is_labeled_heuristic_not_sensitivity():
    """D3 pin through the full sidecar pipeline."""
    payload = _falsification_payload()

    fee_gates = [
        gate
        for record in payload["candidates"]
        for gate in record["gates"]
        if gate["gate"] == "fee_drag_ratio"
    ]
    assert fee_gates, "fee_drag_ratio gate must appear in the sidecar"
    assert fee_gates[0]["gate_kind"] == "heuristic"


def test_integrity_and_falsification_sidecars_carry_no_status_field_anywhere():
    """D4 boundary: no 'status' key escapes into the new sidecars.

    The sole decision layer is research/promotion.py; integrity and
    falsification emit evidence only.
    """
    integrity_offenders = [
        node for node in _walk(_integrity_payload()) if "status" in node
    ]
    falsification_offenders = [
        node for node in _walk(_falsification_payload()) if "status" in node
    ]
    assert not integrity_offenders, (
        "integrity sidecar leaked a 'status' field; D4 boundary broken"
    )
    assert not falsification_offenders, (
        "falsification sidecar leaked a 'status' field; D4 boundary broken"
    )


def test_manifest_payload_exposes_feature_version_and_evaluation_version():
    """The manifest is the sidecar that carries version provenance; it
    must expose the v3.5 feature / evaluation version fields so the
    integrity sidecar can cross-reference them.
    """
    from research.run_research import EVALUATION_VERSION, _build_run_manifest_payload

    class _Asset:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

    manifest = _build_run_manifest_payload(
        run_id="run-int-test",
        started_at_utc=AS_OF,
        research_config={},
        assets=[_Asset("BTC-EUR")],
        intervals=["1h"],
        total_candidate_count=1,
        strategies=[{"name": "sma_crossover"}],
        universe_snapshot_path=__import__("pathlib").Path("universe.v1.json"),
        screening_candidate_budget_seconds=60,
        execution_settings={"execution_mode": "inline", "max_workers": 1},
        lifecycle_mode="fresh",
        resumed_from_run_id=None,
        continuation_summary={"resumed_batches": 0, "retried_batches": 0},
        recovery_policy={},
        retry_failed_batches=False,
    )

    assert manifest["feature_version"] == FEATURE_VERSION
    assert manifest["evaluation_version"] == EVALUATION_VERSION
