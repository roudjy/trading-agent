"""Pure QRE preset/strategy eligibility contract for validation requests."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 1
REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
PRESETS_SOURCE_PATH: Final[Path] = REPO_ROOT / "research" / "presets.py"

STATUS_ELIGIBLE: Final[str] = "eligible"
STATUS_MISSING_PRESET_NAME: Final[str] = "missing_preset_name"
STATUS_PRESET_NOT_FOUND: Final[str] = "preset_not_found"
STATUS_PRESET_DISABLED: Final[str] = "preset_disabled"
STATUS_PRESET_DIAGNOSTIC_ONLY: Final[str] = "preset_diagnostic_only"
STATUS_PRESET_EXCLUDED_FROM_PROMOTION: Final[str] = "preset_excluded_from_promotion"
STATUS_EXECUTABLE_HYPOTHESIS_ID_MISMATCH: Final[str] = "executable_hypothesis_id_mismatch"
STATUS_TIMEFRAME_MISMATCH: Final[str] = "timeframe_mismatch"
STATUS_ASSET_NOT_IN_UNIVERSE: Final[str] = "asset_not_in_universe"
STATUS_STRATEGY_TEMPLATE_NOT_IN_BUNDLE: Final[str] = "strategy_template_not_in_bundle"
STATUS_MALFORMED_REQUEST: Final[str] = "malformed_request"
STATUS_AMBIGUOUS_REQUEST: Final[str] = "ambiguous_request"

ELIGIBILITY_STATUSES: Final[tuple[str, ...]] = (
    STATUS_ELIGIBLE,
    STATUS_MISSING_PRESET_NAME,
    STATUS_PRESET_NOT_FOUND,
    STATUS_PRESET_DISABLED,
    STATUS_PRESET_DIAGNOSTIC_ONLY,
    STATUS_PRESET_EXCLUDED_FROM_PROMOTION,
    STATUS_EXECUTABLE_HYPOTHESIS_ID_MISMATCH,
    STATUS_TIMEFRAME_MISMATCH,
    STATUS_ASSET_NOT_IN_UNIVERSE,
    STATUS_STRATEGY_TEMPLATE_NOT_IN_BUNDLE,
    STATUS_MALFORMED_REQUEST,
    STATUS_AMBIGUOUS_REQUEST,
)

REQUEST_FIELD_LIMITS: Final[dict[str, int]] = {
    "preset_name": 160,
    "executable_hypothesis_id": 160,
    "timeframe": 40,
    "interval": 40,
    "asset": 80,
    "symbol": 80,
    "strategy_template_id": 160,
}


def _bounded_str(value: Any, *, max_len: int = 160) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _get_field(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError):
        return None


def _research_preset_from_call(node: ast.Call) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "enabled": True,
        "diagnostic_only": False,
        "excluded_from_candidate_promotion": False,
        "hypothesis_id": None,
        "timeframe": "",
        "universe": (),
        "bundle": (),
        "name": "",
    }
    for keyword in node.keywords:
        if keyword.arg in fields:
            fields[str(keyword.arg)] = _literal(keyword.value)
    return fields


def _presets_from_source(path: Path = PRESETS_SOURCE_PATH) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    for node in tree.body:
        is_presets_assign = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PRESETS" for target in node.targets
        )
        is_presets_ann_assign = isinstance(node, ast.AnnAssign) and (
            isinstance(node.target, ast.Name) and node.target.id == "PRESETS"
        )
        if not is_presets_assign and not is_presets_ann_assign:
            continue
        if not isinstance(node.value, ast.Tuple):
            return []
        presets: list[dict[str, Any]] = []
        for item in node.value.elts:
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "ResearchPreset"
            ):
                presets.append(_research_preset_from_call(item))
        return presets
    return []


def _bool_field(obj: Any, field: str) -> bool:
    return bool(_get_field(obj, field, False))


def _tuple_field(obj: Any, field: str) -> tuple[str, ...]:
    raw = _get_field(obj, field, ())
    if not isinstance(raw, tuple | list):
        return ()
    return tuple(_bounded_str(item, max_len=160) for item in raw if _bounded_str(item))


def _request_summary(row: dict[str, Any]) -> dict[str, str]:
    return {
        field: text
        for field, limit in REQUEST_FIELD_LIMITS.items()
        if (text := _bounded_str(row.get(field), max_len=limit))
    }


def _preset_summary(preset: Any) -> dict[str, Any]:
    return {
        "preset_name": _bounded_str(_get_field(preset, "name"), max_len=160),
        "enabled": _bool_field(preset, "enabled"),
        "diagnostic_only": _bool_field(preset, "diagnostic_only"),
        "excluded_from_candidate_promotion": _bool_field(
            preset,
            "excluded_from_candidate_promotion",
        ),
        "hypothesis_id": _bounded_str(_get_field(preset, "hypothesis_id"), max_len=160),
        "timeframe": _bounded_str(_get_field(preset, "timeframe"), max_len=40),
        "universe": list(_tuple_field(preset, "universe"))[:50],
        "bundle": list(_tuple_field(preset, "bundle"))[:50],
    }


def _coerce_presets(presets: Any | None) -> list[Any]:
    if presets is None:
        return list(_presets_from_source())
    if isinstance(presets, str) or not hasattr(presets, "__iter__"):
        return []
    return list(presets)


def _preset_matches(presets: list[Any], preset_name: str) -> list[Any]:
    return [
        preset
        for preset in presets
        if _bounded_str(_get_field(preset, "name"), max_len=160) == preset_name
    ]


def _requested_timeframe(row: dict[str, Any]) -> str:
    return _bounded_str(row.get("timeframe"), max_len=40) or _bounded_str(
        row.get("interval"),
        max_len=40,
    )


def _requested_asset(row: dict[str, Any]) -> str:
    return _bounded_str(row.get("asset"), max_len=80) or _bounded_str(
        row.get("symbol"),
        max_len=80,
    )


def _requested_promotion(row: dict[str, Any]) -> bool:
    return row.get("promotion_path_requested") is True


def _first_status(reason_codes: list[str]) -> str:
    if not reason_codes:
        return STATUS_ELIGIBLE
    for status in ELIGIBILITY_STATUSES:
        if status in reason_codes:
            return status
    return STATUS_MALFORMED_REQUEST


def validate_request(
    row: Any,
    *,
    presets: Any | None = None,
    allow_diagnostic_only: bool = False,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {
            "safe_to_request": False,
            "eligibility_status": STATUS_MALFORMED_REQUEST,
            "reason_codes": [STATUS_MALFORMED_REQUEST],
            "request": {},
            "matched_preset": None,
        }

    request = _request_summary(row)
    preset_name = _bounded_str(row.get("preset_name"), max_len=160)
    if not preset_name:
        return {
            "safe_to_request": False,
            "eligibility_status": STATUS_MISSING_PRESET_NAME,
            "reason_codes": [STATUS_MISSING_PRESET_NAME],
            "request": request,
            "matched_preset": None,
        }

    preset_items = _coerce_presets(presets)
    matches = _preset_matches(preset_items, preset_name)
    if not matches:
        return {
            "safe_to_request": False,
            "eligibility_status": STATUS_PRESET_NOT_FOUND,
            "reason_codes": [STATUS_PRESET_NOT_FOUND],
            "request": request,
            "matched_preset": None,
        }
    if len(matches) != 1:
        return {
            "safe_to_request": False,
            "eligibility_status": STATUS_AMBIGUOUS_REQUEST,
            "reason_codes": [STATUS_AMBIGUOUS_REQUEST],
            "request": request,
            "matched_preset": None,
        }

    preset = matches[0]
    reason_codes: list[str] = []
    if not _bool_field(preset, "enabled"):
        reason_codes.append(STATUS_PRESET_DISABLED)
    if _bool_field(preset, "diagnostic_only") and not allow_diagnostic_only:
        reason_codes.append(STATUS_PRESET_DIAGNOSTIC_ONLY)
    if _requested_promotion(row) and _bool_field(preset, "excluded_from_candidate_promotion"):
        reason_codes.append(STATUS_PRESET_EXCLUDED_FROM_PROMOTION)

    requested_hypothesis_id = _bounded_str(row.get("executable_hypothesis_id"), max_len=160)
    preset_hypothesis_id = _bounded_str(_get_field(preset, "hypothesis_id"), max_len=160)
    if (
        requested_hypothesis_id
        and preset_hypothesis_id
        and requested_hypothesis_id != preset_hypothesis_id
    ):
        reason_codes.append(STATUS_EXECUTABLE_HYPOTHESIS_ID_MISMATCH)

    requested_timeframe = _requested_timeframe(row)
    preset_timeframe = _bounded_str(_get_field(preset, "timeframe"), max_len=40)
    if requested_timeframe and preset_timeframe and requested_timeframe != preset_timeframe:
        reason_codes.append(STATUS_TIMEFRAME_MISMATCH)

    requested_asset = _requested_asset(row)
    preset_universe = set(_tuple_field(preset, "universe"))
    if requested_asset and preset_universe and requested_asset not in preset_universe:
        reason_codes.append(STATUS_ASSET_NOT_IN_UNIVERSE)

    requested_strategy = _bounded_str(row.get("strategy_template_id"), max_len=160)
    preset_bundle = set(_tuple_field(preset, "bundle"))
    if requested_strategy and preset_bundle and requested_strategy not in preset_bundle:
        reason_codes.append(STATUS_STRATEGY_TEMPLATE_NOT_IN_BUNDLE)

    status = _first_status(reason_codes)
    return {
        "safe_to_request": status == STATUS_ELIGIBLE,
        "eligibility_status": status,
        "reason_codes": reason_codes,
        "request": request,
        "matched_preset": _preset_summary(preset),
    }


def summarize_eligibility(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(row.get("eligibility_status") for row in rows)
    return {status: counter.get(status, 0) for status in ELIGIBILITY_STATUSES}


__all__ = [
    "ELIGIBILITY_STATUSES",
    "SCHEMA_VERSION",
    "STATUS_AMBIGUOUS_REQUEST",
    "STATUS_ASSET_NOT_IN_UNIVERSE",
    "STATUS_ELIGIBLE",
    "STATUS_EXECUTABLE_HYPOTHESIS_ID_MISMATCH",
    "STATUS_MALFORMED_REQUEST",
    "STATUS_MISSING_PRESET_NAME",
    "STATUS_PRESET_DIAGNOSTIC_ONLY",
    "STATUS_PRESET_DISABLED",
    "STATUS_PRESET_EXCLUDED_FROM_PROMOTION",
    "STATUS_PRESET_NOT_FOUND",
    "STATUS_STRATEGY_TEMPLATE_NOT_IN_BUNDLE",
    "STATUS_TIMEFRAME_MISMATCH",
    "summarize_eligibility",
    "validate_request",
]
