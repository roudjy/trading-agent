"""Pure contract for explicit executable-to-QRE hypothesis identity bridges."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Final

BRIDGE_STATUS_EXACT: Final[str] = "bridge_exact"
BRIDGE_STATUS_MISSING_EXECUTABLE_HYPOTHESIS_ID: Final[str] = (
    "bridge_missing_executable_hypothesis_id"
)
BRIDGE_STATUS_MISSING_QRE_HYPOTHESIS_ID: Final[str] = "bridge_missing_qre_hypothesis_id"
BRIDGE_STATUS_MISSING_VALIDATION_PLAN_ID: Final[str] = "bridge_missing_validation_plan_id"
BRIDGE_STATUS_MISSING_RUN_MANIFEST_ID: Final[str] = "bridge_missing_run_manifest_id"
BRIDGE_STATUS_AMBIGUOUS_EXECUTABLE_HYPOTHESIS_ID: Final[str] = (
    "bridge_ambiguous_executable_hypothesis_id"
)
BRIDGE_STATUS_QRE_HYPOTHESIS_ID_NOT_IN_AUTHORITY: Final[str] = (
    "bridge_qre_hypothesis_id_not_in_authority"
)
BRIDGE_STATUS_VALIDATION_PLAN_MISMATCH: Final[str] = "bridge_validation_plan_mismatch"
BRIDGE_STATUS_RUN_MANIFEST_MISMATCH: Final[str] = "bridge_run_manifest_mismatch"
BRIDGE_STATUS_MALFORMED: Final[str] = "bridge_malformed"

CANONICAL_BRIDGE_FIELDS: Final[tuple[str, ...]] = (
    "executable_hypothesis_id",
    "qre_hypothesis_id",
    "source_hypothesis_id",
    "strategy_family",
    "strategy_template_id",
    "preset_name",
    "validation_plan_id",
    "run_manifest_id",
)

MAX_FIELD_LEN: Final[int] = 160
MAX_WARNING_LEN: Final[int] = 160
MAX_WARNINGS: Final[int] = 8


def _bounded_str(value: Any, *, max_len: int = MAX_FIELD_LEN) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _bridge_fields(row: dict[str, Any]) -> dict[str, str | None]:
    return {
        field: _bounded_str(row.get(field), max_len=MAX_FIELD_LEN) or None
        for field in CANONICAL_BRIDGE_FIELDS
    }


def _warning(value: str) -> str:
    return _bounded_str(value, max_len=MAX_WARNING_LEN)


def _result(
    *,
    fields: dict[str, str | None],
    bridge_status: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warning_values = [_warning(item) for item in warnings or [] if _warning(item)]
    return {
        **fields,
        "safe_to_bridge": bridge_status == BRIDGE_STATUS_EXACT,
        "bridge_status": bridge_status,
        "bridge_warnings": warning_values[:MAX_WARNINGS],
    }


def _authority_entry(
    *,
    qre_hypothesis_id: str,
    qre_authority: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if qre_authority is None:
        return None
    if not isinstance(qre_authority, dict):
        return {}
    by_hypothesis = qre_authority.get("by_hypothesis_id")
    if not isinstance(by_hypothesis, dict):
        return {}
    entry = by_hypothesis.get(qre_hypothesis_id)
    return entry if isinstance(entry, dict) else {}


def validate_bridge_row(
    row: dict[str, Any],
    qre_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one explicit bridge row and fail closed on every uncertainty."""
    if not isinstance(row, dict):
        return _result(
            fields={field: None for field in CANONICAL_BRIDGE_FIELDS},
            bridge_status=BRIDGE_STATUS_MALFORMED,
            warnings=["bridge_row_malformed"],
        )

    fields = _bridge_fields(row)
    if not fields["executable_hypothesis_id"]:
        return _result(
            fields=fields,
            bridge_status=BRIDGE_STATUS_MISSING_EXECUTABLE_HYPOTHESIS_ID,
            warnings=["bridge_row_missing_executable_hypothesis_id"],
        )
    if not fields["qre_hypothesis_id"]:
        return _result(
            fields=fields,
            bridge_status=BRIDGE_STATUS_MISSING_QRE_HYPOTHESIS_ID,
            warnings=["bridge_row_missing_qre_hypothesis_id"],
        )
    if not fields["validation_plan_id"]:
        return _result(
            fields=fields,
            bridge_status=BRIDGE_STATUS_MISSING_VALIDATION_PLAN_ID,
            warnings=["bridge_row_missing_validation_plan_id"],
        )
    if not fields["run_manifest_id"]:
        return _result(
            fields=fields,
            bridge_status=BRIDGE_STATUS_MISSING_RUN_MANIFEST_ID,
            warnings=["bridge_row_missing_run_manifest_id"],
        )

    qre_hypothesis_id = fields["qre_hypothesis_id"]
    assert qre_hypothesis_id is not None
    entry = _authority_entry(qre_hypothesis_id=qre_hypothesis_id, qre_authority=qre_authority)
    if entry == {}:
        return _result(
            fields=fields,
            bridge_status=BRIDGE_STATUS_QRE_HYPOTHESIS_ID_NOT_IN_AUTHORITY,
            warnings=["bridge_qre_hypothesis_id_not_in_authority"],
        )
    if entry is not None:
        expected_validation_plan_id = _bounded_str(
            entry.get("validation_plan_id"), max_len=MAX_FIELD_LEN
        )
        if fields["validation_plan_id"] != expected_validation_plan_id:
            return _result(
                fields=fields,
                bridge_status=BRIDGE_STATUS_VALIDATION_PLAN_MISMATCH,
                warnings=["bridge_validation_plan_id_not_authoritative"],
            )
        expected_run_manifest_id = _bounded_str(entry.get("run_manifest_id"), max_len=MAX_FIELD_LEN)
        if fields["run_manifest_id"] != expected_run_manifest_id:
            return _result(
                fields=fields,
                bridge_status=BRIDGE_STATUS_RUN_MANIFEST_MISMATCH,
                warnings=["bridge_run_manifest_id_not_authoritative"],
            )

    return _result(fields=fields, bridge_status=BRIDGE_STATUS_EXACT)


def _ambiguous_entry(executable_hypothesis_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    qre_ids = sorted(
        {
            _bounded_str(row.get("qre_hypothesis_id"), max_len=MAX_FIELD_LEN)
            for row in rows
            if _bounded_str(row.get("qre_hypothesis_id"), max_len=MAX_FIELD_LEN)
        }
    )
    return {
        "executable_hypothesis_id": executable_hypothesis_id,
        "qre_hypothesis_id": None,
        "source_hypothesis_id": None,
        "strategy_family": None,
        "strategy_template_id": None,
        "preset_name": None,
        "validation_plan_id": None,
        "run_manifest_id": None,
        "safe_to_bridge": False,
        "bridge_status": BRIDGE_STATUS_AMBIGUOUS_EXECUTABLE_HYPOTHESIS_ID,
        "bridge_warnings": ["bridge_executable_hypothesis_id_maps_to_multiple_qre_ids"],
        "conflicting_qre_hypothesis_ids": qre_ids[:MAX_WARNINGS],
    }


def build_bridge_index(
    rows: list[dict[str, Any]],
    qre_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic executable-hypothesis bridge index."""
    if not isinstance(rows, list):
        return {
            "available": False,
            "warnings": ["bridge_rows_malformed"],
            "by_executable_hypothesis_id": {},
            "bridge_summary": {
                "exact_bridge_count": 0,
                "ambiguous_bridge_count": 0,
                "unsafe_bridge_count": 1,
            },
        }

    validated_rows = [
        validate_bridge_row(row, qre_authority=qre_authority)
        for row in rows
        if isinstance(row, dict)
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unsafe_without_executable = 0
    for row in validated_rows:
        executable_id = row.get("executable_hypothesis_id")
        if isinstance(executable_id, str) and executable_id:
            grouped[executable_id].append(row)
        elif row.get("bridge_status") != BRIDGE_STATUS_EXACT:
            unsafe_without_executable += 1

    by_executable: dict[str, dict[str, Any]] = {}
    exact_count = 0
    ambiguous_count = 0
    unsafe_count = unsafe_without_executable

    for executable_id in sorted(grouped):
        group = grouped[executable_id]
        qre_ids = {
            str(row.get("qre_hypothesis_id")) for row in group if row.get("qre_hypothesis_id")
        }
        if len(qre_ids) > 1:
            by_executable[executable_id] = _ambiguous_entry(executable_id, group)
            ambiguous_count += 1
            unsafe_count += 1
            continue

        exact_rows = [row for row in group if row.get("bridge_status") == BRIDGE_STATUS_EXACT]
        selected = exact_rows[0] if exact_rows else group[0]
        by_executable[executable_id] = dict(selected)
        if selected.get("bridge_status") == BRIDGE_STATUS_EXACT:
            exact_count += 1
        else:
            unsafe_count += 1

    return {
        "available": True,
        "warnings": [],
        "by_executable_hypothesis_id": by_executable,
        "bridge_summary": {
            "exact_bridge_count": exact_count,
            "ambiguous_bridge_count": ambiguous_count,
            "unsafe_bridge_count": unsafe_count,
        },
    }
