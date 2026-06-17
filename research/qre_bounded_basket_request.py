from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence


REPORT_KIND: Final[str] = "qre_bounded_basket_request"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_basket_request")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_basket_request/"

ALLOWED_OUTPUT_ROOTS: Final[tuple[str, ...]] = (
    "logs/",
    "artifacts/",
    "archived/",
    "backup/",
    "local_quarantine/",
)
FORBIDDEN_CAPABILITY_TOKENS: Final[tuple[str, ...]] = (
    "campaign_launch",
    "campaign_queue_mutation",
    "campaign_registry_mutation",
    "run_campaign_mutation",
    "strategy_synthesis",
    "strategy_registration",
    "candidate_promotion",
    "paper_shadow_live",
    "broker_risk_execution",
    "provider_activation",
    "external_data_fetch",
    "frozen_contract_mutation",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _as_str(value: Any) -> str:
    return str(value).strip()


def _normalize_symbols(values: Any) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    symbols = []
    seen: set[str] = set()
    for value in values:
        symbol = _as_str(value).upper()
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return tuple(sorted(symbols))


def _normalize_paths(values: Any) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    paths: list[str] = []
    seen: set[str] = set()
    for value in values:
        path = _as_str(value).replace("\\", "/")
        if not path:
            continue
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return tuple(sorted(paths))


def _normalize_strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _as_str(value)
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        items.append(item)
    return tuple(sorted(items))


def _is_allowed_output_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")) or ".." in path.split("/"):
        return False
    return any(path.startswith(root) for root in ALLOWED_OUTPUT_ROOTS)


def _scope_hash_payload(
    *,
    symbols: tuple[str, ...],
    preset_id: str,
    timeframe: str,
    approval_ref: str,
    required_artifact_types: tuple[str, ...],
    allowed_output_paths: tuple[str, ...],
    forbidden_capabilities: tuple[str, ...],
    source: str,
) -> str:
    payload = {
        "symbols": list(symbols),
        "preset_id": preset_id,
        "timeframe": timeframe,
        "approval_ref": approval_ref,
        "required_artifact_types": list(required_artifact_types),
        "allowed_output_paths": list(allowed_output_paths),
        "forbidden_capabilities": list(forbidden_capabilities),
        "source": source,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_request_payload(payload: Mapping[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    rejection_reasons: list[str] = []

    request_id = _as_str(payload.get("request_id"))
    if not request_id:
        rejection_reasons.append("missing_request_id")

    symbols = _normalize_symbols(payload.get("symbols"))
    if not symbols:
        rejection_reasons.append("missing_symbols")

    preset_id = _as_str(payload.get("preset_id"))
    if not preset_id:
        rejection_reasons.append("missing_preset_id")

    timeframe = _as_str(payload.get("timeframe"))
    if not timeframe:
        rejection_reasons.append("missing_timeframe")

    approval_ref = _as_str(payload.get("approval_ref"))
    if not approval_ref:
        rejection_reasons.append("missing_approval_ref")

    required_artifact_types = _normalize_strings(payload.get("required_artifact_types"))
    allowed_output_paths = _normalize_paths(payload.get("allowed_output_paths"))
    forbidden_capabilities = _normalize_strings(payload.get("forbidden_capabilities"))

    if not allowed_output_paths:
        rejection_reasons.append("missing_allowed_output_paths")
    else:
        invalid_paths = [path for path in allowed_output_paths if not _is_allowed_output_path(path)]
        if invalid_paths:
            rejection_reasons.append("path_violation")

    if not required_artifact_types:
        rejection_reasons.append("missing_required_artifact_types")

    forbidden_hits = [
        capability
        for capability in forbidden_capabilities
        if any(token in capability.lower() for token in FORBIDDEN_CAPABILITY_TOKENS)
    ]
    if forbidden_hits:
        rejection_reasons.append("forbidden_capabilities_present")

    created_at_utc = _as_str(payload.get("created_at_utc"))
    if not created_at_utc:
        rejection_reasons.append("missing_created_at_utc")

    source = _as_str(payload.get("source"))
    if not source:
        rejection_reasons.append("missing_source")

    scope_hash = _scope_hash_payload(
        symbols=symbols,
        preset_id=preset_id,
        timeframe=timeframe,
        approval_ref=approval_ref,
        required_artifact_types=required_artifact_types,
        allowed_output_paths=allowed_output_paths,
        forbidden_capabilities=forbidden_capabilities,
        source=source,
    )

    validation_status = "valid" if not rejection_reasons else "rejected"
    normalized = {
        "request_id": request_id,
        "symbols": list(symbols),
        "preset_id": preset_id,
        "timeframe": timeframe,
        "approval_ref": approval_ref,
        "required_artifact_types": list(required_artifact_types),
        "allowed_output_paths": list(allowed_output_paths),
        "forbidden_capabilities": list(forbidden_capabilities),
        "created_at_utc": created_at_utc,
        "source": source,
        "scope_hash": scope_hash,
        "validation_status": validation_status,
        "rejection_reasons": rejection_reasons,
    }
    return validation_status, rejection_reasons, normalized


@dataclass(frozen=True)
class BoundedBasketRequest:
    request_id: str
    symbols: tuple[str, ...]
    preset_id: str
    timeframe: str
    approval_ref: str
    required_artifact_types: tuple[str, ...]
    allowed_output_paths: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    created_at_utc: str
    source: str
    scope_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "BoundedBasketRequest":
        validation_status, rejection_reasons, normalized = _validate_request_payload(payload)
        if validation_status != "valid":
            raise ValueError(
                "bounded basket request is invalid: "
                + ", ".join(rejection_reasons)
            )
        return cls(
            request_id=normalized["request_id"],
            symbols=tuple(normalized["symbols"]),
            preset_id=normalized["preset_id"],
            timeframe=normalized["timeframe"],
            approval_ref=normalized["approval_ref"],
            required_artifact_types=tuple(normalized["required_artifact_types"]),
            allowed_output_paths=tuple(normalized["allowed_output_paths"]),
            forbidden_capabilities=tuple(normalized["forbidden_capabilities"]),
            created_at_utc=normalized["created_at_utc"],
            source=normalized["source"],
            scope_hash=normalized["scope_hash"],
        )

    def validate(self) -> dict[str, Any]:
        return {
            "validation_status": "valid",
            "rejection_reasons": [],
            "scope_hash": self.scope_hash,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "symbols": list(self.symbols),
            "preset_id": self.preset_id,
            "timeframe": self.timeframe,
            "approval_ref": self.approval_ref,
            "required_artifact_types": list(self.required_artifact_types),
            "allowed_output_paths": list(self.allowed_output_paths),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "created_at_utc": self.created_at_utc,
            "source": self.source,
            "scope_hash": self.scope_hash,
            "validation_status": "valid",
            "rejection_reasons": [],
        }


def build_bounded_basket_request_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    validation_status, rejection_reasons, normalized = _validate_request_payload(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "request": {
            "request_id": normalized["request_id"],
            "symbols": normalized["symbols"],
            "preset_id": normalized["preset_id"],
            "timeframe": normalized["timeframe"],
            "approval_ref": normalized["approval_ref"],
            "required_artifact_types": normalized["required_artifact_types"],
            "allowed_output_paths": normalized["allowed_output_paths"],
            "forbidden_capabilities": normalized["forbidden_capabilities"],
            "created_at_utc": normalized["created_at_utc"],
            "source": normalized["source"],
            "scope_hash": normalized["scope_hash"],
        },
        "validation_status": validation_status,
        "rejection_reasons": rejection_reasons,
        "safety_invariants": {
            "read_only": True,
            "symbols_are_input_data": True,
            "bounded_request_driven": True,
            "symbol_agnostic_core_paths": True,
            "no_trading_authority": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    request = report.get("request") if isinstance(report.get("request"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Bounded Basket Request",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["request_id", str(request.get("request_id") or "")],
                    ["validation_status", str(report.get("validation_status") or "")],
                    ["scope_hash", str(request.get("scope_hash") or "")],
                ],
            ),
            "",
            "## Request",
            _table(
                ["Field", "Value"],
                [
                    ["symbols", ", ".join(str(v) for v in request.get("symbols") or []) or "none"],
                    ["preset_id", str(request.get("preset_id") or "")],
                    ["timeframe", str(request.get("timeframe") or "")],
                    ["approval_ref", str(request.get("approval_ref") or "")],
                    ["source", str(request.get("source") or "")],
                ],
            ),
            "",
            "## Rejection Reasons",
            _table(
                ["Reason"],
                [[reason] for reason in (report.get("rejection_reasons") or [])] or [["none"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_basket_request: refusing write outside allowlist: {path!r}"
        )


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
        prog="python -m research.qre_bounded_basket_request",
        description="Validate a bounded basket request manifest.",
    )
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.request_file is None:
        raise SystemExit("--request-file is required")
    payload = json.loads(args.request_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("request file must contain a JSON object")
    report = build_bounded_basket_request_snapshot(payload)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
