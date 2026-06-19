from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from packages.qre_data.symbology_resolver import resolve_symbology_row
from packages.qre_data.source_quality_readiness import (
    build_source_quality_report,
)
from research.equity_universe_identity import build_instrument_identity_report
from research.qre_discovery_source_identity_diagnostics import (
    build_source_identity_diagnostics,
)
from research.qre_evidence_breadth_framework import build_evidence_breadth_framework


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_source_identity_authority_normalization"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_identity_authority_normalization")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_source_identity_authority_normalization/"
DEFAULT_BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
DEFAULT_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
DEFAULT_DISCOVERY_IDENTITY_PATH: Final[Path] = Path("logs/qre_discovery_source_identity_diagnostics/latest.json")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _breadth_rows(breadth_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = breadth_report.get("coverage_matrix") if isinstance(breadth_report.get("coverage_matrix"), list) else []
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("dimension")) == "basket"
    ]


def _scope_components(scope_key: str) -> dict[str, str]:
    parts = [part for part in scope_key.split("::") if part]
    preset_id = parts[1] if len(parts) >= 2 else ""
    symbol = parts[2] if len(parts) >= 3 else ""
    timeframe = ""
    for candidate in ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "daily", "weekly"):
        needle = f"_{candidate}_"
        if needle in f"_{preset_id}_":
            timeframe = "1d" if candidate == "daily" else candidate
            break
    behavior_id = preset_id
    for suffix in ("_daily_v1", "_4h_v1", "_1d_v1", "_weekly_v1", "_v1"):
        if behavior_id.endswith(suffix):
            behavior_id = behavior_id[: -len(suffix)]
            break
    return {
        "preset_id": preset_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "behavior_id": behavior_id,
    }


def _discovery_index(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return {
        _text(row.get("instrument_symbol")): dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("instrument_symbol"))
    }


def _instrument_index(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return {
        _text(row.get("symbol")): dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("symbol"))
    }


def _resolver_input(
    *,
    symbol: str,
    discovery_row: Mapping[str, Any] | None,
    instrument_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    discovery_row = discovery_row or {}
    instrument_row = instrument_row or {}
    aliases = discovery_row.get("candidate_aliases")
    if not isinstance(aliases, list):
        aliases = instrument_row.get("candidate_provider_symbols")
    return {
        "canonical_instrument_id": _text(instrument_row.get("canonical_id")) or _text(discovery_row.get("canonical_symbol")),
        "symbol": symbol,
        "primary_data_provider_symbol": _text(discovery_row.get("selected_provider_symbol")) or _text(instrument_row.get("provider_symbol")),
        "provider_symbol_aliases": list(aliases or []),
        "provider_symbol_status": _text(discovery_row.get("provider_symbol_status")),
        "source_identity_status": (
            "provider_symbol_verified"
            if bool(discovery_row.get("is_provider_symbol_verified"))
            else _text(discovery_row.get("provider_symbol_status"))
        ),
    }


def _authority_status(
    *,
    resolution: Mapping[str, Any],
    discovery_row: Mapping[str, Any] | None,
    instrument_row: Mapping[str, Any] | None,
    source_quality_report: Mapping[str, Any] | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not isinstance(source_quality_report, Mapping):
        return "blocked_missing_source_quality_report", ["source_quality_report_missing"]
    source_summary = source_quality_report.get("summary") if isinstance(source_quality_report.get("summary"), Mapping) else {}
    if not bool(source_summary.get("research_ready")):
        reasons.append("source_quality_not_research_ready")
    if discovery_row is None:
        reasons.append("discovery_identity_row_missing")
    if instrument_row is None:
        reasons.append("instrument_identity_row_missing")
    if _text(resolution.get("resolution_status")) != "VERIFIED":
        reasons.extend(_text(value) for value in resolution.get("blocking_reasons", []) if _text(value))
    if instrument_row is not None and not bool(instrument_row.get("eligible_for_hypothesis_seed")):
        reasons.append("instrument_identity_not_seed_eligible")
    if reasons:
        primary = reasons[0]
        if primary == "source_quality_not_research_ready":
            return "blocked_source_quality_not_ready", reasons
        if primary in {"discovery_identity_row_missing", "instrument_identity_row_missing"}:
            return "blocked_identity_inventory_missing", reasons
        return "blocked_provider_symbol_ambiguity", reasons
    return "normalized_context_ready", []


def _next_action(rows: list[dict[str, Any]]) -> str:
    statuses = {_text(row.get("authority_status")) for row in rows}
    if "blocked_source_quality_not_ready" in statuses:
        return "stabilize_source_quality_manifest_and_readiness"
    if "blocked_identity_inventory_missing" in statuses:
        return "materialize_identity_inventory_for_bounded_scope"
    if "blocked_provider_symbol_ambiguity" in statuses:
        return "resolve_provider_symbol_ambiguity_for_bounded_scope"
    if "blocked_missing_source_quality_report" in statuses:
        return "materialize_source_quality_report"
    return "preserve_read_only_source_authority_context"


def build_source_identity_authority_normalization(
    *,
    breadth_report: Mapping[str, Any],
    source_quality_report: Mapping[str, Any] | None,
    discovery_identity_report: Mapping[str, Any],
    instrument_identity_report: Mapping[str, Any],
) -> dict[str, Any]:
    breadth_rows = _breadth_rows(breadth_report)
    discovery_by_symbol = _discovery_index(discovery_identity_report)
    instrument_by_symbol = _instrument_index(instrument_identity_report)
    rows: list[dict[str, Any]] = []
    for breadth_row in breadth_rows:
        scope_key = _text(breadth_row.get("scope_key"))
        scope_components = _scope_components(scope_key)
        symbol = _text(breadth_row.get("symbol")) or scope_components["symbol"]
        discovery_row = discovery_by_symbol.get(symbol)
        instrument_row = instrument_by_symbol.get(symbol)
        resolution = resolve_symbology_row(
            _resolver_input(
                symbol=symbol,
                discovery_row=discovery_row,
                instrument_row=instrument_row,
            )
        )
        authority_status, authority_reasons = _authority_status(
            resolution=resolution,
            discovery_row=discovery_row,
            instrument_row=instrument_row,
            source_quality_report=source_quality_report,
        )
        row = {
            "scope_key": scope_key,
            "symbol": symbol,
            "region": _text(breadth_row.get("region")),
            "behavior_id": _text(breadth_row.get("behavior_id")) or scope_components["behavior_id"],
            "timeframe": _text(breadth_row.get("timeframe")) or scope_components["timeframe"],
            "authority_status": authority_status,
            "authority_reasons": authority_reasons,
            "resolution_status": _text(resolution.get("resolution_status")),
            "provider_symbol": resolution.get("provider_symbol"),
            "provider_symbol_status": _text(resolution.get("provider_symbol_status")),
            "source_identity_status": _text(resolution.get("source_identity_status")),
            "instrument_identity_status": (
                _text(instrument_row.get("identity_status")) if instrument_row else "missing"
            ),
            "instrument_seed_eligible": bool(instrument_row.get("eligible_for_hypothesis_seed")) if instrument_row else False,
            "source_quality_ready": bool(
                ((source_quality_report or {}).get("summary") or {}).get("research_ready")
            ),
            "source_quality_status": _text(
                (((source_quality_report or {}).get("summary") or {}).get("status"))
                or ((source_quality_report or {}).get("status"))
            )
            or "missing",
            "operator_explanation": (
                "Source identity and source authority are normalized for read-only candidate evaluation."
                if authority_status == "normalized_context_ready"
                else "Source authority remains fail-closed until identity ambiguity and source-quality prerequisites are resolved."
            ),
            "provenance": [
                {"artifact_path": DEFAULT_BREADTH_PATH.as_posix(), "artifact_ref": f"{DEFAULT_BREADTH_PATH.as_posix()}#coverage_matrix::{scope_key}"},
                {"artifact_path": DEFAULT_SOURCE_QUALITY_PATH.as_posix(), "artifact_ref": DEFAULT_SOURCE_QUALITY_PATH.as_posix()},
                {"artifact_path": DEFAULT_DISCOVERY_IDENTITY_PATH.as_posix(), "artifact_ref": f"{DEFAULT_DISCOVERY_IDENTITY_PATH.as_posix()}#rows::{symbol}"},
                {"artifact_path": "research/equity_universe_identity.py", "artifact_ref": f"instrument_identity::{symbol}"},
            ],
            "authority": {
                "context_only": True,
                "can_authorize_execution": False,
                "can_promote_candidate": False,
                "can_activate_shadow": False,
            },
        }
        row["deterministic_hash"] = _digest(
            {
                "scope_key": row["scope_key"],
                "symbol": row["symbol"],
                "authority_status": row["authority_status"],
                "authority_reasons": row["authority_reasons"],
                "provider_symbol": row["provider_symbol"],
            }
        )
        rows.append(row)

    rows.sort(key=lambda row: (str(row["authority_status"]), str(row["scope_key"])))
    status_counts = Counter(str(row["authority_status"]) for row in rows)
    next_action = _next_action(rows)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": "ready" if rows else "not_ready",
            "scope_count": len(rows),
            "ready_scope_count": sum(1 for row in rows if row["authority_status"] == "normalized_context_ready"),
            "blocked_scope_count": sum(1 for row in rows if row["authority_status"] != "normalized_context_ready"),
            "authority_status_counts": dict(sorted(status_counts.items())),
            "exact_next_action": next_action,
            "operator_summary": (
                "Source identity and source-quality context are normalized into one read-only authority surface. "
                "Missing or ambiguous mappings remain explicit blockers and never become promotion or deployment authority."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "breadth_report_kind": breadth_report.get("report_kind"),
            "source_quality_report_kind": (source_quality_report or {}).get("report_kind"),
            "discovery_identity_report_kind": discovery_identity_report.get("report_kind"),
            "instrument_identity_report_kind": instrument_identity_report.get("report_kind"),
        },
        "authority_boundary": {
            "context_only_not_authority": True,
            "source_quality_not_alpha": True,
            "source_quality_not_promotion_authority": True,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
            "can_activate_live": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_or_static_repo_context_only": True,
            "uses_network": False,
            "candidate_promotion_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def _load_breadth_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_BREADTH_PATH) or build_evidence_breadth_framework(repo_root=repo_root)


def _load_source_quality_report(repo_root: Path) -> dict[str, Any] | None:
    persisted = _read_json(repo_root / DEFAULT_SOURCE_QUALITY_PATH)
    if persisted is not None:
        return persisted
    manifest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    if isinstance(manifest, Mapping):
        return build_source_quality_report(manifest)
    return None


def _load_discovery_identity_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_DISCOVERY_IDENTITY_PATH) or build_source_identity_diagnostics()


def build_source_identity_authority_report(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    return build_source_identity_authority_normalization(
        breadth_report=_load_breadth_report(repo_root),
        source_quality_report=_load_source_quality_report(repo_root),
        discovery_identity_report=_load_discovery_identity_report(repo_root),
        instrument_identity_report=build_instrument_identity_report(),
    )


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Source Identity Authority Normalization",
        "",
        f"- status: {summary.get('status') or 'unknown'}",
        f"- scope_count: {summary.get('scope_count') or 0}",
        f"- ready_scope_count: {summary.get('ready_scope_count') or 0}",
        f"- blocked_scope_count: {summary.get('blocked_scope_count') or 0}",
        f"- exact_next_action: {summary.get('exact_next_action') or 'unknown'}",
        "",
        "## Scope Rows",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('scope_key')} symbol={row.get('symbol')} authority_status={row.get('authority_status')} blockers={','.join(row.get('authority_reasons', [])) or 'none'}"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": _rel(latest, root=repo_root),
        "operator_summary": _rel(summary_path, root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_source_identity_authority_normalization",
        description="Build a read-only normalized source identity authority surface for QRE scopes.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_source_identity_authority_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
