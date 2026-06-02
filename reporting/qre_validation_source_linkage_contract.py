"""Read-only contract for QRE validation source-row linkage."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
CONTRACT_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_validation_source_linkage_contract"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / REPORT_KIND
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = f"logs/{REPORT_KIND}/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

REQUIRED_LINKAGE_FIELDS: Final[tuple[str, ...]] = (
    "hypothesis_id",
    "validation_plan_id",
    "run_manifest_id",
    "source_artifact",
    "source_report_kind",
    "source_row_id",
)
CONTEXT_LINKAGE_FIELDS: Final[tuple[str, ...]] = (
    "candidate_id",
    "strategy_id",
    "asset",
    "symbol",
    "timeframe",
    "run_id",
    "plan_id",
)
FORBIDDEN_PRIMARY_LINKAGE_FIELDS: Final[tuple[str, ...]] = (
    "asset",
    "symbol",
    "timeframe",
    "strategy_id",
)
REASON_CODE_VOCABULARY: Final[tuple[str, ...]] = (
    "contract_compliant_exact_ids",
    "missing_hypothesis_id",
    "missing_validation_plan_id",
    "missing_run_manifest_id",
    "missing_source_artifact",
    "missing_source_report_kind",
    "missing_source_row_id",
    "malformed_source_row",
    "empty_required_field",
    "asset_timeframe_only_not_allowed",
    "symbol_timeframe_only_not_allowed",
    "strategy_context_only_not_allowed",
    "candidate_id_context_only_not_allowed",
    "unsupported_primary_linkage_mode",
)

_SCALAR_SUMMARY_MAX_CHARS: Final[int] = 96
_MAX_FIELD_SUMMARIES: Final[int] = len(REQUIRED_LINKAGE_FIELDS) + len(CONTEXT_LINKAGE_FIELDS)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_supported_scalar(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _scalar_text(value: object, *, max_len: int = _SCALAR_SUMMARY_MAX_CHARS) -> str:
    if not _is_supported_scalar(value):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _field_summaries(row: Mapping[str, object]) -> dict[str, str]:
    summaries: dict[str, str] = {}
    for field in (*REQUIRED_LINKAGE_FIELDS, *CONTEXT_LINKAGE_FIELDS):
        if field not in row:
            continue
        text = _scalar_text(row[field])
        if text:
            summaries[field] = text
        elif not _is_supported_scalar(row[field]):
            summaries[field] = "<malformed>"
    if len(summaries) > _MAX_FIELD_SUMMARIES:
        raise ValueError("internal error: field summaries exceeded bound")
    return summaries


def _missing_reason(field: str) -> str:
    return f"missing_{field}"


def _closed_reason_codes(reason_codes: list[str]) -> list[str]:
    allowed = set(REASON_CODE_VOCABULARY)
    ordered = [code for code in REASON_CODE_VOCABULARY if code in set(reason_codes)]
    if not set(ordered) <= allowed:
        raise ValueError("internal error: unsupported source linkage reason code")
    return ordered


def validate_source_linkage_contract(row: Mapping[str, object]) -> dict[str, object]:
    """Return the strict source-linkage contract assessment for one row.

    The contract fails closed. Context fields can help later producers explain
    a row, but they never substitute for the six exact source-linkage fields.
    """
    if not isinstance(row, Mapping):
        return {
            "contract_version": CONTRACT_VERSION,
            "is_contract_compliant": False,
            "safe_to_link": False,
            "missing_required_fields": list(REQUIRED_LINKAGE_FIELDS),
            "present_required_fields": [],
            "present_context_fields": [],
            "forbidden_primary_only_fields": [],
            "primary_linkage_mode": "malformed_source_row",
            "reason_codes": ["malformed_source_row"],
            "warnings": [],
            "field_value_summaries": {},
        }

    reason_codes: list[str] = []
    present_required_fields: list[str] = []
    missing_required_fields: list[str] = []
    malformed_required = False
    empty_required = False

    for field in REQUIRED_LINKAGE_FIELDS:
        value = row.get(field)
        if not _is_supported_scalar(value):
            missing_required_fields.append(field)
            if value is not None:
                malformed_required = True
            reason_codes.append(_missing_reason(field))
            continue
        if not _scalar_text(value):
            missing_required_fields.append(field)
            empty_required = True
            reason_codes.append(_missing_reason(field))
            continue
        present_required_fields.append(field)

    present_context_fields = [
        field for field in CONTEXT_LINKAGE_FIELDS if _scalar_text(row.get(field))
    ]
    forbidden_present_fields = [
        field for field in FORBIDDEN_PRIMARY_LINKAGE_FIELDS if _scalar_text(row.get(field))
    ]
    exact_complete = not missing_required_fields
    has_required_context = bool(present_required_fields)
    has_context = bool(present_context_fields)

    if exact_complete:
        reason_codes.append("contract_compliant_exact_ids")
        primary_linkage_mode = "exact_ids"
    else:
        if malformed_required:
            reason_codes.append("malformed_source_row")
        if empty_required:
            reason_codes.append("empty_required_field")
        if (
            not has_required_context
            and ("asset" in forbidden_present_fields)
            and ("timeframe" in forbidden_present_fields)
        ):
            reason_codes.append("asset_timeframe_only_not_allowed")
        if (
            not has_required_context
            and ("symbol" in forbidden_present_fields)
            and ("timeframe" in forbidden_present_fields)
        ):
            reason_codes.append("symbol_timeframe_only_not_allowed")
        if not has_required_context and "strategy_id" in forbidden_present_fields:
            reason_codes.append("strategy_context_only_not_allowed")
        if not has_required_context and "candidate_id" in present_context_fields:
            reason_codes.append("candidate_id_context_only_not_allowed")
        reason_codes.append("unsupported_primary_linkage_mode")

        if not has_required_context and forbidden_present_fields:
            primary_linkage_mode = "forbidden_context_only"
        elif not has_required_context and has_context:
            primary_linkage_mode = "context_only"
        elif present_required_fields:
            primary_linkage_mode = "incomplete_exact_ids"
        else:
            primary_linkage_mode = "unsupported"

    forbidden_primary_only_fields = (
        forbidden_present_fields if not exact_complete and not has_required_context else []
    )
    closed_codes = _closed_reason_codes(reason_codes)
    return {
        "contract_version": CONTRACT_VERSION,
        "is_contract_compliant": exact_complete,
        "safe_to_link": exact_complete,
        "missing_required_fields": missing_required_fields,
        "present_required_fields": present_required_fields,
        "present_context_fields": present_context_fields,
        "forbidden_primary_only_fields": forbidden_primary_only_fields,
        "primary_linkage_mode": primary_linkage_mode,
        "reason_codes": closed_codes,
        "warnings": [],
        "field_value_summaries": _field_summaries(row),
    }


def _examples() -> dict[str, dict[str, object]]:
    exact = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "validation_plan_id": "qre-plan-fixture-001",
        "run_manifest_id": "qre-run-fixture-001",
        "source_artifact": "research/screening_evidence_latest.v1.json",
        "source_report_kind": "screening_evidence",
        "source_row_id": "candidate-001",
    }
    return {
        "compliant_exact_ids": validate_source_linkage_contract(exact),
        "rejected_asset_timeframe_only": validate_source_linkage_contract(
            {"asset": "BTC-USD", "timeframe": "1h"}
        ),
        "rejected_candidate_id_only": validate_source_linkage_contract(
            {"candidate_id": "candidate-001"}
        ),
        "rejected_missing_run_manifest_id": validate_source_linkage_contract(
            {
                "hypothesis_id": "qre-hyp-fixture-001",
                "validation_plan_id": "qre-plan-fixture-001",
                "source_artifact": "research/screening_evidence_latest.v1.json",
                "source_report_kind": "screening_evidence",
                "source_row_id": "candidate-001",
            }
        ),
    }


def build_source_linkage_contract_report(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": generated_at_utc or _utcnow(),
        "output_artifact_path": OUTPUT_ARTIFACT_RELATIVE_PATH,
        "safe_to_execute": False,
        "read_only": True,
        "required_linkage_fields": list(REQUIRED_LINKAGE_FIELDS),
        "context_linkage_fields": list(CONTEXT_LINKAGE_FIELDS),
        "forbidden_primary_linkage_fields": list(FORBIDDEN_PRIMARY_LINKAGE_FIELDS),
        "reason_code_vocabulary": list(REASON_CODE_VOCABULARY),
        "examples": _examples(),
    }


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(
            f"refusing write outside QRE validation source linkage contract dir: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_validation_source_linkage_contract.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def write_source_linkage_contract_report(
    report: Mapping[str, object] | None = None,
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, report or build_source_linkage_contract_report())
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_validation_source_linkage_contract",
        description="Emit the read-only QRE validation source-linkage contract.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = build_source_linkage_contract_report(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        write_source_linkage_contract_report(report)
    print(json.dumps(report, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "CONTEXT_LINKAGE_FIELDS",
    "CONTRACT_VERSION",
    "FORBIDDEN_PRIMARY_LINKAGE_FIELDS",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REASON_CODE_VOCABULARY",
    "REPORT_KIND",
    "REQUIRED_LINKAGE_FIELDS",
    "SCHEMA_VERSION",
    "build_source_linkage_contract_report",
    "main",
    "validate_source_linkage_contract",
    "write_source_linkage_contract_report",
]
