"""Writer for the integrity sidecar `integrity_report_latest.v1.json`.

The sidecar is diagnostic evidence per D4. It carries per-candidate
IntegrityCheck records and run-level rejection counts by reason code
but **no `status` field**: candidate promotion remains the sole
decision authority. Downstream reporting reads this sidecar for
observability only.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from research.integrity import IntegrityCheck, IntegrityReport


SIDECAR_VERSION = "v1"


def build_integrity_report_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    config_hash: str,
    git_revision: str,
    feature_version: str,
    evaluation_version: str,
    report: IntegrityReport,
) -> dict[str, Any]:
    checks_payload = [asdict(check) for check in report.checks]
    counts = report.rejection_counts_by_reason()
    return {
        "version": SIDECAR_VERSION,
        "run_id": run_id,
        "generated_at_utc": as_of_utc.isoformat(),
        "config_hash": config_hash,
        "git_revision": git_revision,
        "feature_version": feature_version,
        "evaluation_version": evaluation_version,
        "checks": checks_payload,
        "rejection_counts_by_reason": counts,
        "summary": {
            "total_checks": len(checks_payload),
            "passed_checks": sum(1 for c in checks_payload if c["passed"]),
            "failed_checks": sum(1 for c in checks_payload if not c["passed"]),
        },
    }


def make_eligibility_integrity_check(
    *,
    strategy_name: str,
    asset: str,
    interval: str,
    passed: bool,
    reason_code: str | None,
    extras: dict[str, Any] | None = None,
) -> IntegrityCheck:
    details: dict[str, Any] = {
        "strategy_name": strategy_name,
        "asset": asset,
        "interval": interval,
    }
    if extras:
        details.update(extras)
    return IntegrityCheck(
        name=f"eligibility[{strategy_name}|{asset}|{interval}]",
        passed=passed,
        reason_code=reason_code,
        details=details,
    )


__all__ = [
    "SIDECAR_VERSION",
    "build_integrity_report_payload",
    "make_eligibility_integrity_check",
]
