from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_basket_request as basket_request


REPORT_KIND: Final[str] = "qre_structured_oos_artifacts"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_structured_oos_artifacts")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_structured_oos_artifacts/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _artifact_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return "qoo_" + digest[:16]


def _request_snapshot(request_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if request_payload is None:
        return {
            "schema_version": basket_request.SCHEMA_VERSION,
            "report_kind": basket_request.REPORT_KIND,
            "request": {},
            "validation_status": "rejected",
            "rejection_reasons": ["missing_request_payload"],
        }
    return basket_request.build_bounded_basket_request_snapshot(request_payload)


def _oos_row(request: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    request_id = str(request.get("request_id") or "")
    preset_id = str(request.get("preset_id") or "")
    timeframe = str(request.get("timeframe") or "")
    approval_ref = str(request.get("approval_ref") or "")
    source_paths = [
        "logs/qre_bounded_current_basket_generation_runner/latest.json",
        "logs/qre_bounded_current_basket_generation_discovery/latest.json",
        "logs/qre_bounded_basket_request/latest.json",
    ]
    reason_record_refs = [
        "logs/qre_bounded_current_basket_generation_runner/latest.json#reason_records",
    ]
    metric_fields = {
        "oos_trade_count": None,
        "oos_return_pct": None,
        "max_drawdown_pct": None,
        "slippage_cost_pct": None,
    }
    missing_fields = [
        "oos_window_start",
        "oos_window_end",
        "oos_metric_fields",
        "cost_slippage_assumption_refs",
    ]
    return {
        "artifact_id": _artifact_id("oos", request_id, symbol, preset_id, timeframe),
        "request_id": request_id,
        "symbol": symbol,
        "preset_id": preset_id,
        "timeframe": timeframe,
        "oos_window": {"start": "", "end": "", "label": "provisional_missing"},
        "oos_metric_fields": metric_fields,
        "cost_slippage_assumption_refs": [],
        "validation_status": "provisional",
        "approval_ref": approval_ref,
        "generation_manifest_ref": "logs/qre_bounded_current_basket_generation_runner/latest.json",
        "source_paths": source_paths,
        "reason_record_refs": reason_record_refs,
        "created_at_utc": str(request.get("created_at_utc") or ""),
        "accepted_for_oos_evidence": False,
        "missing_fields": missing_fields,
        "rejection_reasons": [
            "missing_oos_window",
            "missing_oos_metric_fields",
            "missing_cost_slippage_assumption_refs",
            "provisional_only_no_real_validation",
        ],
        "can_clear_no_oos_evidence": False,
    }


def build_structured_oos_artifacts(
    request_payload: Mapping[str, Any] | None = None,
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    request_report = _request_snapshot(request_payload)
    request = request_report.get("request") if isinstance(request_report.get("request"), Mapping) else {}
    rows = []
    if request_report.get("validation_status") == "valid":
        for symbol in request.get("symbols") or []:
            rows.append(_oos_row(request, str(symbol)))
    counts = {
        "provisional": sum(1 for row in rows if row["validation_status"] == "provisional"),
        "accepted": sum(1 for row in rows if row["accepted_for_oos_evidence"]),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "request_validation_status": request_report.get("validation_status"),
        "request_rejection_reasons": list(request_report.get("rejection_reasons") or []),
        "summary": {
            "request_id": str(request.get("request_id") or ""),
            "symbols": list(request.get("symbols") or []),
            "artifact_count": len(rows),
            "provisional_count": counts["provisional"],
            "accepted_count": counts["accepted"],
            "final_recommendation": (
                "structured_oos_artifacts_provisional_no_real_evidence"
                if rows
                else "request_invalid_fails_closed"
            ),
            "operator_summary": (
                "Structured OOS artifacts remain provisional until real OOS windows, metrics, and cost assumptions are present."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "no_fake_oos_evidence": True,
            "no_blocker_clearance_from_provisional_rows": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return "\n".join(
        [
            "# QRE Structured OOS Artifacts",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["request_id", str(summary.get("request_id") or "")],
                    ["artifact_count", str(summary.get("artifact_count") or 0)],
                    ["provisional_count", str(summary.get("provisional_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Symbol", "Validation", "Missing fields"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("validation_status") or ""),
                        ", ".join(str(v) for v in row.get("missing_fields") or []) or "none",
                    ]
                    for row in rows
                ]
                or [["none", "n/a", "n/a"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_structured_oos_artifacts: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_structured_oos_artifacts",
        description="Build the provisional structured OOS artifacts report.",
    )
    parser.add_argument("--request-file")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    request_payload = _read_json(Path(args.request_file)) if args.request_file else None
    report = build_structured_oos_artifacts(request_payload)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
