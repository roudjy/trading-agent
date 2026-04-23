"""Tests for research.execution_bridge.agent_definition (v3.12 advisory-only).

Includes an AST-based test that guarantees this module never imports
live execution, broker, or market data code.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from research._sidecar_io import serialize_canonical
from research.execution_bridge import (
    AGENT_DEFINITIONS_SCHEMA_VERSION,
    ALLOWED_PRESETS,
    BridgeScopeError,
    build_agent_definition_entry,
    build_agent_definitions_payload,
)


NOW = "2026-04-23T12:00:00+00:00"


def _entry(
    preset_origin: str = "trend_equities_4h_baseline",
    lifecycle_status: str = "candidate",
    strategy_name: str = "sma_crossover",
    candidate_id: str | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id or f"{strategy_name}|NVDA|4h|{{}}",
        "strategy_name": strategy_name,
        "parameter_set": {"fast": 20, "slow": 100},
        "asset_universe": ["NVDA", "AMD"],
        "interval": "4h",
        "experiment_family": "trend|equities",
        "preset_origin": preset_origin,
        "lifecycle_status": lifecycle_status,
    }


def test_allowed_presets_is_exactly_two() -> None:
    assert ALLOWED_PRESETS == frozenset({
        "trend_equities_4h_baseline",
        "regime_filter_equities_4h_experimental",
    })


def test_single_entry_carries_runnable_false_and_execution_scope() -> None:
    out = build_agent_definition_entry(_entry())
    assert out["runnable"] is False
    assert out["execution_scope"] == "future_paper_phase_only"


def test_entry_crypto_diagnostic_preset_raises_scope_error() -> None:
    with pytest.raises(BridgeScopeError) as exc:
        build_agent_definition_entry(_entry(preset_origin="crypto_diagnostic_1h"))
    assert "preset_origin_not_allowed" in str(exc.value)


def test_entry_rejected_lifecycle_status_raises_scope_error() -> None:
    with pytest.raises(BridgeScopeError) as exc:
        build_agent_definition_entry(_entry(lifecycle_status="rejected"))
    assert "lifecycle_status_not_active" in str(exc.value)


def test_entry_unregistered_strategy_raises_scope_error() -> None:
    with pytest.raises(BridgeScopeError) as exc:
        build_agent_definition_entry(_entry(strategy_name="nonsense_strategy_xyz"))
    assert "strategy_not_registered" in str(exc.value)


def test_payload_pins_schema_and_invariants() -> None:
    payload = build_agent_definitions_payload([_entry()], generated_at_utc=NOW)
    assert payload["schema_version"] == AGENT_DEFINITIONS_SCHEMA_VERSION == "1.0"
    assert payload["advisory_only"] is True
    assert payload["runnable_entries"] == 0
    assert payload["scope_allowed_presets"] == sorted(ALLOWED_PRESETS)


def test_payload_allow_partial_skips_out_of_scope_with_reason() -> None:
    entries = [
        _entry(strategy_name="sma_crossover", candidate_id="good|1"),
        _entry(preset_origin="crypto_diagnostic_1h", candidate_id="skip|1"),
    ]
    payload = build_agent_definitions_payload(entries, generated_at_utc=NOW, allow_partial=True)
    assert len(payload["entries"]) == 1
    assert len(payload["skipped"]) == 1
    assert payload["skipped"][0]["candidate_id"] == "skip|1"
    assert "preset_origin_not_allowed" in payload["skipped"][0]["reason"]


def test_payload_allow_partial_false_raises_on_first_skip() -> None:
    entries = [_entry(preset_origin="crypto_diagnostic_1h")]
    with pytest.raises(BridgeScopeError):
        build_agent_definitions_payload(entries, generated_at_utc=NOW, allow_partial=False)


def test_payload_entries_and_skipped_sorted_by_candidate_id() -> None:
    entries = [
        _entry(candidate_id="zzz|1"),
        _entry(candidate_id="aaa|1"),
        _entry(candidate_id="mmm|1", preset_origin="crypto_diagnostic_1h"),
    ]
    payload = build_agent_definitions_payload(entries, generated_at_utc=NOW, allow_partial=True)
    entry_ids = [e["candidate_id"] for e in payload["entries"]]
    assert entry_ids == sorted(entry_ids)


def test_payload_byte_equal_across_two_calls() -> None:
    entries = [_entry()]
    a = build_agent_definitions_payload(entries, generated_at_utc=NOW)
    b = build_agent_definitions_payload(entries, generated_at_utc=NOW)
    assert serialize_canonical(a) == serialize_canonical(b)


def test_regime_filtered_preset_is_allowed() -> None:
    out = build_agent_definition_entry(
        _entry(preset_origin="regime_filter_equities_4h_experimental")
    )
    assert out["runnable"] is False


def test_advisory_note_is_present() -> None:
    out = build_agent_definition_entry(_entry())
    assert "not intended for execution" in out["advisory_note"]
    assert "v3.15" in out["advisory_note"]


# -----------------------------------------------------------------------------
# AST-based import isolation check
# -----------------------------------------------------------------------------

_FORBIDDEN_IMPORT_PREFIXES = (
    "agent.execution",
    "execution.paper",
    "ccxt",
    "yfinance",
    "polymarket",
    "alchemy",
)


def _all_imports(source: str) -> list[str]:
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for relative imports like "from . import x"
            if node.module:
                imports.append(node.module)
    return imports


def _iter_bridge_sources() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "research" / "execution_bridge"
    return sorted(p for p in root.rglob("*.py"))


def test_bridge_modules_have_no_forbidden_imports() -> None:
    files = _iter_bridge_sources()
    assert files, "expected bridge modules to exist"
    for path in files:
        source = path.read_text(encoding="utf-8")
        imports = _all_imports(source)
        for imp in imports:
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                assert not imp.startswith(prefix), (
                    f"forbidden import {imp!r} in {path} "
                    f"(prefix {prefix!r} banned in research/execution_bridge/)"
                )
