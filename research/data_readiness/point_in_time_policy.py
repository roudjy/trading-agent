"""Deterministic fail-closed point-in-time policy projection."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.external_intelligence.source_manifest_registry import build_source_manifest_registry
from research.external_intelligence.source_manifest_schema import FUNDAMENTAL_SOURCE_TYPES


SCHEMA_VERSION: Final[str] = "1.0"
SUPPORT_VOCABULARY: Final[tuple[str, ...]] = (
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "UNKNOWN",
)
REQUIREMENT_VOCABULARY: Final[tuple[str, ...]] = ("REQUIRED", "NOT_REQUIRED")
POLICY_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "UNKNOWN",
    "REQUIRED",
    "NOT_REQUIRED",
    "POLICY_MISSING",
    "REVIEW_REQUIRED",
    "FAIL_CLOSED",
)
BLOCK_REASON_VOCABULARY: Final[tuple[str, ...]] = (
    "MISSING_POINT_IN_TIME_POLICY",
    "POINT_IN_TIME_UNKNOWN",
    "POINT_IN_TIME_UNSUPPORTED",
)


def _policy_row(row: dict[str, object], policy_row: dict[str, object]) -> dict[str, object]:
    source_type = str(row.get("source_type") or "unknown")
    support_status = str(row.get("point_in_time_support") or "unknown").upper()
    requirement_status = "REQUIRED" if source_type in FUNDAMENTAL_SOURCE_TYPES else "NOT_REQUIRED"
    license_policy_status = str(policy_row.get("license_policy_status") or "UNKNOWN")
    block_reasons: list[str] = []

    if requirement_status == "NOT_REQUIRED":
        policy_status = "NOT_REQUIRED"
    elif license_policy_status in {"UNKNOWN", "FAIL"}:
        policy_status = "FAIL_CLOSED"
        block_reasons.append("MISSING_POINT_IN_TIME_POLICY")
    elif support_status == "UNKNOWN":
        policy_status = "POLICY_MISSING"
        block_reasons.extend(["MISSING_POINT_IN_TIME_POLICY", "POINT_IN_TIME_UNKNOWN"])
    elif support_status == "UNSUPPORTED":
        policy_status = "UNSUPPORTED"
        block_reasons.extend(["MISSING_POINT_IN_TIME_POLICY", "POINT_IN_TIME_UNSUPPORTED"])
    elif license_policy_status == "WARN":
        policy_status = "REVIEW_REQUIRED"
        block_reasons.append("MISSING_POINT_IN_TIME_POLICY")
    elif support_status == "PARTIALLY_SUPPORTED":
        policy_status = "PARTIALLY_SUPPORTED"
    elif support_status == "SUPPORTED":
        policy_status = "SUPPORTED"
    else:
        policy_status = "UNKNOWN"
        block_reasons.extend(["MISSING_POINT_IN_TIME_POLICY", "POINT_IN_TIME_UNKNOWN"])

    return {
        "source_id": row["source_id"],
        "provider_id": row["provider_id"],
        "source_type": source_type,
        "requirement_status": requirement_status,
        "support_status": support_status,
        "license_policy_status": license_policy_status,
        "policy_status": policy_status,
        "block_reasons": sorted(set(block_reasons)),
        "operator_explanation": (
            "Point-in-time policy remains fail-closed until source semantics and review status are explicit."
        ),
    }


def build_point_in_time_policy() -> dict[str, object]:
    snapshot = build_source_manifest_registry()
    rows = [_policy_row(row, snapshot["policy_by_source"][str(row["source_id"])]) for row in snapshot["rows"]]
    rows.sort(key=lambda item: str(item["source_id"]))
    counts = Counter(str(row["policy_status"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "point_in_time_policy",
        "support_vocabulary": list(SUPPORT_VOCABULARY),
        "requirement_vocabulary": list(REQUIREMENT_VOCABULARY),
        "policy_status_vocabulary": list(POLICY_STATUS_VOCABULARY),
        "block_reason_vocabulary": list(BLOCK_REASON_VOCABULARY),
        "summary": {
            "source_count": len(rows),
            "required_count": sum(row["requirement_status"] == "REQUIRED" for row in rows),
            "not_required_count": sum(row["requirement_status"] == "NOT_REQUIRED" for row in rows),
            "policy_status_counts": dict(sorted(counts.items())),
            "operator_summary": (
                "Point-in-time policy is deterministic and fail-closed. "
                "Manifest presence does not imply usable PIT semantics."
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
            "no_data_fetch": True,
        },
    }
