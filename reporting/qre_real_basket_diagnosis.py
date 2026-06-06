from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import production_discovery_catalog as catalog


REPORT_KIND: Final[str] = "qre_real_basket_diagnosis"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_real_basket_diagnosis")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_real_basket_diagnosis/"
_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
_SCREENING_EVIDENCE_PATH: Final[Path] = Path("research/screening_evidence_latest.v1.json")
_CAMPAIGN_REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
_CANDIDATE_REGISTRY_PATH: Final[Path] = Path("research/candidate_registry_latest.v1.json")
_DIAGNOSIS_CLASSES: Final[tuple[str, ...]] = (
    "diagnosable",
    "blocked",
    "deferred",
    "unknown_fail_closed",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_supporting_artifacts(*, repo_root: Path) -> dict[str, Any]:
    return {
        "cache_manifest": _read_json(repo_root / _CACHE_MANIFEST_PATH),
        "source_quality": _read_json(repo_root / _SOURCE_QUALITY_PATH),
        "screening_evidence": _read_json(repo_root / _SCREENING_EVIDENCE_PATH),
        "campaign_registry": _read_json(repo_root / _CAMPAIGN_REGISTRY_PATH),
        "candidate_registry": _read_json(repo_root / _CANDIDATE_REGISTRY_PATH),
    }


def _matching_source_rows(
    source_quality: Mapping[str, Any] | None,
    *,
    symbol: str,
    provider_symbol: str | None,
    aliases: Sequence[str],
    timeframes: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(source_quality, Mapping):
        return []
    rows = source_quality.get("rows")
    if not isinstance(rows, list):
        return []
    instrument_keys = {symbol}
    if provider_symbol:
        instrument_keys.add(provider_symbol)
    instrument_keys.update(str(value) for value in aliases if str(value).strip())
    timeframe_keys = {str(value) for value in timeframes if str(value).strip()}
    matched: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        instrument = str(row.get("instrument") or "")
        timeframe = str(row.get("timeframe") or "")
        if instrument not in instrument_keys:
            continue
        if timeframe_keys and timeframe not in timeframe_keys:
            continue
        matched.append(row)
    return matched


def _matching_cache_rows(
    cache_manifest: Mapping[str, Any] | None,
    *,
    symbol: str,
    provider_symbol: str | None,
    aliases: Sequence[str],
    timeframes: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(cache_manifest, Mapping):
        return []
    rows = cache_manifest.get("coverage")
    if not isinstance(rows, list):
        return []
    instrument_keys = {symbol}
    if provider_symbol:
        instrument_keys.add(provider_symbol)
    instrument_keys.update(str(value) for value in aliases if str(value).strip())
    timeframe_keys = {str(value) for value in timeframes if str(value).strip()}
    matched: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        instrument = str(row.get("instrument") or "")
        timeframe = str(row.get("timeframe") or "")
        if instrument not in instrument_keys:
            continue
        if timeframe_keys and timeframe not in timeframe_keys:
            continue
        matched.append(row)
    return matched


def _matching_screening_rows(
    screening_evidence: Mapping[str, Any] | None,
    *,
    symbol: str,
    hypothesis_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(screening_evidence, Mapping):
        return []
    rows = screening_evidence.get("candidates")
    if not isinstance(rows, list):
        return []
    matched: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("asset") or "") != symbol:
            continue
        row_hypothesis_id = str(
            row.get("hypothesis_id") or row.get("executable_hypothesis_id") or ""
        )
        if row_hypothesis_id and row_hypothesis_id != hypothesis_id:
            continue
        matched.append(row)
    return matched


def _matching_campaigns(
    campaign_registry: Mapping[str, Any] | None,
    *,
    preset_id: str,
    hypothesis_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(campaign_registry, Mapping):
        return []
    campaigns = campaign_registry.get("campaigns")
    if not isinstance(campaigns, dict):
        return []
    matched: list[dict[str, Any]] = []
    for row in campaigns.values():
        if not isinstance(row, dict):
            continue
        if str(row.get("preset_name") or "") != preset_id:
            continue
        row_hypothesis_id = str(row.get("hypothesis_id") or "")
        if row_hypothesis_id and row_hypothesis_id != hypothesis_id:
            continue
        matched.append(row)
    return matched


def _matching_candidates(
    candidate_registry: Mapping[str, Any] | None,
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    if not isinstance(candidate_registry, Mapping):
        return []
    candidates = candidate_registry.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [
        row
        for row in candidates
        if isinstance(row, dict) and str(row.get("asset") or "") == symbol
    ]


def _evidence_counts(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(str(row.get(field) or "unknown") for row in rows)
    return dict(sorted(counter.items()))


def _diagnosis(
    *,
    provider_symbol_status: str,
    source_identity_status: str,
    source_rows: Sequence[Mapping[str, Any]],
    cache_rows: Sequence[Mapping[str, Any]],
    source_quality_payload: Mapping[str, Any] | None,
    cache_manifest_payload: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if provider_symbol_status == "candidate_alias_requires_verification":
        return ("blocked", "source_identity_candidate_alias_unverified")
    if source_identity_status == "missing_provider_symbol":
        return ("blocked", "source_identity_missing_provider_symbol")
    if not isinstance(source_quality_payload, Mapping) or not isinstance(
        cache_manifest_payload, Mapping
    ):
        return ("unknown_fail_closed", "supporting_artifacts_missing")

    if any(str(row.get("quality_status") or "") == "blocked" for row in source_rows):
        return ("blocked", "source_quality_blocked")
    if any(not bool(row.get("ready")) for row in cache_rows):
        return ("blocked", "cache_coverage_not_ready")
    if source_rows and cache_rows:
        return ("diagnosable", "source_and_cache_evidence_available")
    if source_rows and not cache_rows:
        return ("deferred", "cache_coverage_missing_for_basket")
    if cache_rows and not source_rows:
        return ("deferred", "source_quality_rows_missing_for_basket")
    return ("deferred", "no_matching_real_basket_evidence")


def build_real_basket_diagnosis(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    artifacts = _load_supporting_artifacts(repo_root=repo_root)
    source_identity_index = {
        str(row["instrument_symbol"]): row for row in catalog.source_identity_diagnostics()
    }
    rows: list[dict[str, Any]] = []
    for basket in catalog.build_bounded_candidate_basket(max_candidates=max_candidates):
        symbol = str(basket["symbol"])
        hypothesis_id = str(basket["hypothesis_id"])
        preset_id = str(basket["preset_id"])
        source_identity = source_identity_index.get(symbol, {})
        provider_symbol = source_identity.get("provider_symbol")
        aliases = list(source_identity.get("candidate_aliases") or [])
        timeframes = list(basket.get("timeframes") or [])
        source_rows = _matching_source_rows(
            artifacts["source_quality"],
            symbol=symbol,
            provider_symbol=str(provider_symbol) if provider_symbol else None,
            aliases=aliases,
            timeframes=timeframes,
        )
        cache_rows = _matching_cache_rows(
            artifacts["cache_manifest"],
            symbol=symbol,
            provider_symbol=str(provider_symbol) if provider_symbol else None,
            aliases=aliases,
            timeframes=timeframes,
        )
        screening_rows = _matching_screening_rows(
            artifacts["screening_evidence"],
            symbol=symbol,
            hypothesis_id=hypothesis_id,
        )
        campaign_rows = _matching_campaigns(
            artifacts["campaign_registry"],
            preset_id=preset_id,
            hypothesis_id=hypothesis_id,
        )
        candidate_rows = _matching_candidates(
            artifacts["candidate_registry"],
            symbol=symbol,
        )
        diagnosis_class, reason_code = _diagnosis(
            provider_symbol_status=str(basket.get("provider_symbol_status") or "unknown"),
            source_identity_status=str(basket.get("source_identity_status") or "unknown"),
            source_rows=source_rows,
            cache_rows=cache_rows,
            source_quality_payload=artifacts["source_quality"],
            cache_manifest_payload=artifacts["cache_manifest"],
        )
        rows.append(
            {
                "candidate_id": basket["candidate_id"],
                "symbol": symbol,
                "provider_symbol": provider_symbol,
                "provider_symbol_aliases": aliases,
                "region": basket["region"],
                "asset_class": basket["asset_class"],
                "preset_id": preset_id,
                "hypothesis_id": hypothesis_id,
                "behavior_family": basket["behavior_family"],
                "timeframes": timeframes,
                "diagnosis_class": diagnosis_class,
                "reason_code": reason_code,
                "source_identity_status": basket.get("source_identity_status"),
                "provider_symbol_status": basket.get("provider_symbol_status"),
                "current_evidence": {
                    "source_quality_rows": len(source_rows),
                    "source_quality_status_counts": _evidence_counts(
                        source_rows, "quality_status"
                    ),
                    "cache_coverage_rows": len(cache_rows),
                    "cache_ready_count": sum(bool(row.get("ready")) for row in cache_rows),
                    "screening_rows": len(screening_rows),
                    "screening_stage_result_counts": _evidence_counts(
                        screening_rows, "stage_result"
                    ),
                    "screening_validation_status_counts": _evidence_counts(
                        [
                            row.get("validation_evidence") or {}
                            for row in screening_rows
                            if isinstance(row.get("validation_evidence"), Mapping)
                        ],
                        "status",
                    ),
                    "campaign_rows": len(campaign_rows),
                    "campaign_state_counts": _evidence_counts(campaign_rows, "state"),
                    "candidate_rows": len(candidate_rows),
                    "candidate_status_counts": _evidence_counts(candidate_rows, "status"),
                },
                "follow_up": (
                    "resolve_source_identity"
                    if diagnosis_class == "blocked"
                    and reason_code.startswith("source_identity")
                    else "inspect_source_quality"
                    if diagnosis_class == "blocked"
                    else "collect_cache_or_screening_evidence"
                    if diagnosis_class == "deferred"
                    else "inspect_missing_supporting_artifacts"
                    if diagnosis_class == "unknown_fail_closed"
                    else "eligible_for_readonly_diagnosis"
                ),
            }
        )

    summary_counts = Counter(str(row["diagnosis_class"]) for row in rows)
    artifact_availability = {
        "cache_manifest": isinstance(artifacts["cache_manifest"], Mapping),
        "source_quality": isinstance(artifacts["source_quality"], Mapping),
        "screening_evidence": isinstance(artifacts["screening_evidence"], Mapping),
        "campaign_registry": isinstance(artifacts["campaign_registry"], Mapping),
        "candidate_registry": isinstance(artifacts["candidate_registry"], Mapping),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "basket_source": "production_discovery_catalog.build_bounded_candidate_basket",
        "max_candidates": max_candidates,
        "summary": {
            "basket_inventory_count": len(rows),
            "diagnosis_class_counts": {
                key: summary_counts.get(key, 0) for key in _DIAGNOSIS_CLASSES
            },
            "artifact_availability": artifact_availability,
            "fail_closed": not all(artifact_availability.values()),
            "operator_summary": (
                "Real basket diagnosis is available as a read-only inventory over the "
                "production discovery seed. Baskets with unresolved source identity "
                "or missing cache/source evidence remain blocked or deferred."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "runner_integration": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    counts = summary.get("diagnosis_class_counts") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket inventory", str(summary.get("basket_inventory_count") or 0)],
            ["diagnosable", str(counts.get("diagnosable") or 0)],
            ["blocked", str(counts.get("blocked") or 0)],
            ["deferred", str(counts.get("deferred") or 0)],
            ["unknown fail closed", str(counts.get("unknown_fail_closed") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Timeframe",
            "Diagnosis",
            "Reason",
            "Source rows",
            "Cache rows",
            "Screening rows",
            "Follow-up",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                ",".join(str(value) for value in row.get("timeframes") or []),
                str(row.get("diagnosis_class") or ""),
                str(row.get("reason_code") or ""),
                str((row.get("current_evidence") or {}).get("source_quality_rows") or 0),
                str((row.get("current_evidence") or {}).get("cache_coverage_rows") or 0),
                str((row.get("current_evidence") or {}).get("screening_rows") or 0),
                str(row.get("follow_up") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Real Basket Diagnosis",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Diagnosis counts",
            count_table,
            "",
            "## 3. Basket diagnosis",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_real_basket_diagnosis: refusing write outside allowlist: {path!r}"
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
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_real_basket_diagnosis",
        description="Build a read-only diagnosis over the production discovery seed basket.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_real_basket_diagnosis(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
