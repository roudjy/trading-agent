"""Writer for the falsification sidecar `falsification_gates_latest.v1.json`.

Sidecar is additive, diagnostic evidence. **No `status` field**
(D4 boundary): promotion remains the sole decision layer. Gates carry
gate_kind / passed / severity / evidence only. Joined against
candidate ids used by candidate_registry_latest.v1.json.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from research.falsification import FalsificationVerdict
from research.promotion import build_strategy_id


SIDECAR_VERSION = "v1"


def build_candidate_gate_record(
    *,
    strategy_name: str,
    asset: str,
    interval: str,
    selected_params: dict[str, Any],
    sizing_regime: str,
    verdicts: list[FalsificationVerdict],
) -> dict[str, Any]:
    candidate_id = build_strategy_id(strategy_name, asset, interval, selected_params)
    return {
        "candidate_id": candidate_id,
        "strategy_name": strategy_name,
        "asset": asset,
        "interval": interval,
        "sizing_regime": sizing_regime,
        "gates": [asdict(verdict) for verdict in verdicts],
        "summary": {
            "total_gates": len(verdicts),
            "passed_gates": sum(1 for v in verdicts if v.passed),
            "failed_gates": sum(1 for v in verdicts if not v.passed),
        },
    }


def build_falsification_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    candidate_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": SIDECAR_VERSION,
        "run_id": run_id,
        "generated_at_utc": as_of_utc.isoformat(),
        "note": (
            "Diagnostic evidence only. Promotion remains the sole decision layer. "
            "No 'status' is emitted here; see candidate_registry_latest.v1.json."
        ),
        "candidates": candidate_records,
        "summary": {
            "candidate_count": len(candidate_records),
            "failed_gate_count": sum(
                item["summary"]["failed_gates"] for item in candidate_records
            ),
        },
    }


__all__ = [
    "SIDECAR_VERSION",
    "build_candidate_gate_record",
    "build_falsification_payload",
]
