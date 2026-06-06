"""Read-only identity diagnostics for the static equity universe catalog."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.equity_universe_catalog import list_equity_instruments


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "instrument_identity"
STATUS_VALUES: Final[tuple[str, ...]] = ("OK", "WARN", "FAIL", "UNKNOWN")


def _status_for_row(
    *,
    provider_symbol: str,
    candidate_provider_symbols: tuple[str, ...],
    identity_confidence: str,
    duplicate_canonical: bool,
    duplicate_symbol: bool,
    duplicate_provider_symbol: bool,
    missing_required: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if missing_required:
        reasons.append("missing_required_identity_fields")
    if duplicate_canonical:
        reasons.append("duplicate_canonical_id")
    if duplicate_provider_symbol:
        reasons.append("duplicate_provider_symbol")
    if duplicate_symbol:
        reasons.append("duplicate_symbol")
    if not provider_symbol and candidate_provider_symbols:
        reasons.append("provider_symbol_unverified")
    elif not provider_symbol:
        reasons.append("provider_symbol_missing")
    if identity_confidence not in {"high", "medium", "low"}:
        reasons.append("identity_confidence_unknown")
    elif identity_confidence != "high":
        reasons.append("identity_confidence_not_high")

    if "missing_required_identity_fields" in reasons or "duplicate_canonical_id" in reasons:
        return "FAIL", reasons
    if reasons:
        return "WARN", reasons
    return "OK", reasons


def build_instrument_identity_report() -> dict[str, object]:
    instruments = list_equity_instruments()
    canonical_counts = Counter(item.canonical_id for item in instruments)
    symbol_counts = Counter(item.symbol for item in instruments)
    provider_symbol_counts = Counter(item.provider_symbol for item in instruments if item.provider_symbol)
    rows: list[dict[str, object]] = []
    for item in instruments:
        missing_required = not all(
            (
                item.canonical_id,
                item.symbol,
                item.display_name,
                item.country,
                item.exchange,
                item.currency,
            )
        )
        status, reasons = _status_for_row(
            provider_symbol=item.provider_symbol,
            candidate_provider_symbols=item.candidate_provider_symbols,
            identity_confidence=item.identity_confidence,
            duplicate_canonical=canonical_counts[item.canonical_id] > 1,
            duplicate_symbol=symbol_counts[item.symbol] > 1,
            duplicate_provider_symbol=bool(item.provider_symbol)
            and provider_symbol_counts[item.provider_symbol] > 1,
            missing_required=missing_required,
        )
        rows.append(
            {
                "canonical_id": item.canonical_id,
                "symbol": item.symbol,
                "provider_symbol": item.provider_symbol,
                "candidate_provider_symbols": list(item.candidate_provider_symbols),
                "country": item.country,
                "exchange": item.exchange,
                "currency": item.currency,
                "identity_confidence": item.identity_confidence,
                "identity_status": status,
                "identity_reasons": reasons,
                "ambiguous_mapping_warning": item.ambiguous_mapping_warning,
                "eligible_for_hypothesis_seed": status == "OK",
                "eligible_for_trading": False,
            }
        )
    rows.sort(key=lambda row: (str(row["country"]), str(row["exchange"]), str(row["symbol"])))
    status_counts = Counter(str(row["identity_status"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "status_vocabulary": list(STATUS_VALUES),
        "summary": {
            "instrument_count": len(rows),
            "ok_instruments": status_counts.get("OK", 0),
            "warn_instruments": status_counts.get("WARN", 0),
            "fail_instruments": status_counts.get("FAIL", 0),
            "unknown_instruments": status_counts.get("UNKNOWN", 0),
            "ambiguous_mappings": sum(bool(row["ambiguous_mapping_warning"]) for row in rows),
            "duplicate_canonical_ids": sum("duplicate_canonical_id" in row["identity_reasons"] for row in rows),
            "duplicate_symbols": sum("duplicate_symbol" in row["identity_reasons"] for row in rows),
            "duplicate_provider_symbols": sum(
                "duplicate_provider_symbol" in row["identity_reasons"] for row in rows
            ),
            "eligible_for_hypothesis_seed": sum(bool(row["eligible_for_hypothesis_seed"]) for row in rows),
            "blocked_for_hypothesis_seed": sum(not bool(row["eligible_for_hypothesis_seed"]) for row in rows),
            "operator_summary": (
                "Instrument identity is deterministic metadata only. Ambiguity, missing mappings, "
                "and duplicate identifiers remain visible and block escalation to hypothesis seeds."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
