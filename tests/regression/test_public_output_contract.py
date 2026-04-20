"""Regression pin for the v3.5 public output contract + D4 boundary.

research/results.py `ROW_SCHEMA` and `JSON_TOP_LEVEL_SCHEMA` are the
v3.5 public surface. This test strengthens the existing schema-drift
guard by asserting:

1. the row and top-level JSON schemas expose exactly the v3.4 keys —
   no accidental v3.5 additions bleed into research_latest.json /
   strategy_matrix.csv (frozen surface);

2. the v3.5 additive sidecar payloads
   (`integrity_report_latest.v1.json`, `falsification_gates_latest.v1.json`)
   do NOT include a `status` field anywhere near a candidate record
   — that is the D4 boundary: integrity and falsification are
   diagnostic evidence only, promotion remains the sole decision
   authority. If either sidecar ever grows a `status` key under a
   candidate, the separation is broken and this test fires.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from research.falsification import (
    FalsificationVerdict,
    GATE_KIND_HEURISTIC,
    GATE_KIND_STATISTICAL,
    SEVERITY_INFO,
    SEVERITY_WARN,
)
from research.falsification_reporting import (
    build_candidate_gate_record,
    build_falsification_payload,
)
from research.integrity import FEATURE_INCOMPLETE, IntegrityCheck, IntegrityReport
from research.integrity_reporting import build_integrity_report_payload
from research.results import JSON_TOP_LEVEL_SCHEMA, ROW_SCHEMA


EXPECTED_ROW_SCHEMA = (
    "timestamp_utc",
    "strategy_name",
    "family",
    "hypothesis",
    "asset",
    "interval",
    "params_json",
    "success",
    "error",
    "win_rate",
    "sharpe",
    "deflated_sharpe",
    "max_drawdown",
    "trades_per_maand",
    "consistentie",
    "totaal_trades",
    "goedgekeurd",
    "criteria_checks_json",
    "reden",
)


EXPECTED_JSON_TOP_LEVEL_SCHEMA = (
    "generated_at_utc",
    "count",
    "summary",
    "results",
)


def test_row_schema_is_frozen_exactly():
    """V3.5 must not add fields to the CSV/JSON row schema."""
    assert tuple(ROW_SCHEMA) == EXPECTED_ROW_SCHEMA


def test_json_top_level_schema_is_frozen_exactly():
    """V3.5 must not add keys at the top of research_latest.json."""
    assert tuple(JSON_TOP_LEVEL_SCHEMA) == EXPECTED_JSON_TOP_LEVEL_SCHEMA


def _walk(node):
    """Yield every dict encountered in nested containers."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)


def test_integrity_sidecar_payload_carries_no_status_field():
    """D4 boundary: integrity emits diagnostic evidence, not a decision."""
    report = IntegrityReport()
    report.record(
        IntegrityCheck(
            name="eligibility[sma_crossover|BTC/EUR|1h]",
            passed=False,
            reason_code=FEATURE_INCOMPLETE,
            details={"strategy_name": "sma_crossover"},
        )
    )

    payload = build_integrity_report_payload(
        run_id="run-test",
        as_of_utc=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
        config_hash="abc",
        git_revision="deadbeef",
        feature_version="1.0",
        evaluation_version="1.0",
        report=report,
    )

    offenders = [
        node for node in _walk(payload) if "status" in node
    ]
    assert not offenders, (
        "integrity sidecar must not expose a 'status' field anywhere — "
        "it is evidence-only per D4 (promotion decides candidate status)"
    )


def test_falsification_sidecar_payload_carries_no_status_field():
    """D4 boundary: falsification emits diagnostic evidence, not a decision."""
    verdicts = [
        FalsificationVerdict(
            gate="low_trade_count",
            gate_kind=GATE_KIND_STATISTICAL,
            passed=False,
            severity=SEVERITY_WARN,
            evidence={"totaal_trades": 5},
        ),
        FalsificationVerdict(
            gate="fee_drag_ratio",
            gate_kind=GATE_KIND_HEURISTIC,
            passed=True,
            severity=SEVERITY_INFO,
            evidence={"ratio": 0.1, "threshold": 0.5},
        ),
    ]
    record = build_candidate_gate_record(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        selected_params={"fast_window": 10, "slow_window": 50},
        sizing_regime="fixed_unit",
        verdicts=verdicts,
    )
    payload = build_falsification_payload(
        run_id="run-test",
        as_of_utc=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
        candidate_records=[record],
    )

    offenders = [node for node in _walk(payload) if "status" in node]
    assert not offenders, (
        "falsification sidecar must not expose a 'status' field anywhere — "
        "it is evidence-only per D4 (promotion decides candidate status)"
    )


def test_falsification_verdict_dataclass_carries_no_status_field():
    verdict = FalsificationVerdict(
        gate="x",
        gate_kind=GATE_KIND_HEURISTIC,
        passed=True,
        severity=SEVERITY_INFO,
    )
    payload = asdict(verdict)

    assert "status" not in payload


def test_integrity_check_dataclass_carries_no_status_field():
    check = IntegrityCheck(name="x", passed=True)
    payload = asdict(check)

    assert "status" not in payload


def test_row_schema_has_no_reference_asset_key_with_pairs_in_registry():
    """Scope-lock pin for v3.6: enabling pairs_zscore in the registry
    MUST NOT introduce a `reference_asset` column into the public row
    schema. reference_asset is an internal identity field only -
    public `asset` carries the primary symbol and nothing else.
    """
    from research.registry import STRATEGIES

    pairs_entries = [s for s in STRATEGIES if s["name"] == "pairs_zscore"]
    assert len(pairs_entries) == 1, "pairs_zscore registry entry missing"
    assert pairs_entries[0].get("enabled") is True, (
        "pairs_zscore must be enabled for this v3.6 contract pin to be meaningful"
    )
    assert pairs_entries[0].get("reference_asset") == "ETH-EUR"

    assert "reference_asset" not in ROW_SCHEMA, (
        "Public CSV/JSON row schema must not expose reference_asset - "
        "it lives only on internal candidate surfaces"
    )
    assert "reference_asset" not in JSON_TOP_LEVEL_SCHEMA, (
        "Public research_latest.json top-level schema must not expose "
        "reference_asset - it lives only on internal candidate surfaces"
    )


def test_falsification_sidecar_preserves_heuristic_label_on_fee_gate():
    """D3 pin: the fee drag gate stays labelled 'heuristic', never
    drifts toward presenting itself as true sensitivity analysis.
    """
    verdict = FalsificationVerdict(
        gate="fee_drag_ratio",
        gate_kind=GATE_KIND_HEURISTIC,
        passed=True,
        severity=SEVERITY_INFO,
        evidence={"note": "heuristic proxy"},
    )
    record = build_candidate_gate_record(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        selected_params={"fast_window": 10, "slow_window": 50},
        sizing_regime="fixed_unit",
        verdicts=[verdict],
    )

    fee_gate = next(g for g in record["gates"] if g["gate"] == "fee_drag_ratio")
    assert fee_gate["gate_kind"] == GATE_KIND_HEURISTIC
