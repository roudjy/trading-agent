from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from packages.qre_research.alpha_discovery.contracts import (
    DatasetSnapshot,
    canonical_payload,
    content_id,
    stable_digest,
)
from packages.qre_research.alpha_discovery.snapshot_lineage import append_snapshot_row
from packages.qre_research.alpha_discovery.source_qualification import (
    SOURCE_POLICY_VERSION,
    qualify_datasets,
)

ONBOARDING_DIR = Path("generated_research/data_catalog/onboarding")
SOURCE_CERTIFICATION_PATH = Path("generated_research/data_catalog/source_certification/latest.json")
SOURCE_QUALIFICATIONS_PATH = Path("generated_research/alpha_discovery/source_qualifications/latest.json")
SOURCE_RESOLUTION_PATH = Path("generated_research/alpha_discovery/source_resolution/latest.json")
SCHEMA_VERSION = "qre_source_onboarding_v1"
MANIFEST_SCHEMA_VERSION = "qre_source_manifest_v1"

SECRET_ENV_VARS = (
    "QRE_DATABENTO_API_KEY",
    "QRE_TIINGO_API_KEY",
    "QRE_NASDAQ_DATA_LINK_API_KEY",
    "QRE_ALPHA_VANTAGE_API_KEY",
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8-sig") == text:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a YAML mapping")
    return payload


def _manifest_hash(manifest: dict[str, Any]) -> str:
    return "sha256:" + stable_digest(canonical_payload(manifest))


def _required_manifest_actions(manifest: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    required_paths = {
        "source_id": ("source_id",),
        "provider_id": ("provider_id",),
        "allowed_use": ("allowed_use",),
        "calendar": ("calendar",),
        "timeframe": ("timeframe",),
        "schema_mapping": ("data",),
        "universe": ("universe",),
    }
    for action, path in required_paths.items():
        value: Any = manifest
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value in (None, "", [], {}):
            actions.append(f"missing_{action}")
    data = manifest.get("data") if isinstance(manifest.get("data"), dict) else {}
    for key in ("timestamp_column", "symbol_column", "open_column", "high_column", "low_column", "close_column", "volume_column"):
        if not data.get(key):
            actions.append(f"missing_{key}")
    allowed_use = {str(value) for value in manifest.get("allowed_use") or []}
    license_status = str(manifest.get("license_policy_status") or "").upper()
    attestation = manifest.get("operator_license_attestation") if isinstance(manifest.get("operator_license_attestation"), dict) else {}
    if "research_screening" in allowed_use and (license_status != "PASS" or not attestation):
        actions.append("missing_license_attestation")
        actions.append("provide_screening_license_attestation")
    if "research_screening" not in allowed_use:
        actions.append("missing_license_attestation")
        actions.append("provide_screening_license_attestation")
    return sorted(dict.fromkeys(actions))


def validate_manifest_file(path: Path) -> dict[str, Any]:
    manifest = _load_manifest(path)
    actions = _required_manifest_actions(manifest)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_onboarding_manifest_validation",
        "manifest_path": path.name,
        "source_id": manifest.get("source_id"),
        "provider_id": manifest.get("provider_id"),
        "manifest_hash": _manifest_hash(manifest),
        "valid": not actions,
        "operator_actions": actions,
        "secret_boundary": {
            "accepted_env_vars": SECRET_ENV_VARS,
            "secrets_written_to_artifacts": False,
        },
    }
    return canonical_payload(payload)


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _format_ts(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timeframe_delta(timeframe: str) -> timedelta | None:
    text = str(timeframe or "").lower()
    if text.endswith("h") and text[:-1].isdigit():
        return timedelta(hours=int(text[:-1]))
    if text.endswith("d") and text[:-1].isdigit():
        return timedelta(days=int(text[:-1]))
    return None


def _expected_bar_count(*, calendar: dict[str, Any], timeframe: str, start: datetime | None, end: datetime | None, symbol_count: int) -> int | None:
    if start is None or end is None or end < start or symbol_count <= 0:
        return None
    calendar_type = str(calendar.get("type") or "")
    delta = _timeframe_delta(timeframe)
    if delta is None:
        return None
    if calendar_type == "crypto_24_7":
        return int(((end - start).total_seconds() // delta.total_seconds()) + 1) * symbol_count
    if calendar_type == "weekday_daily" and timeframe == "1d":
        count = 0
        current = start.date()
        final = end.date()
        while current <= final:
            if current.weekday() < 5:
                count += 1
            current += timedelta(days=1)
        return count * symbol_count
    return None


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_rows(*, bars_path: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = dict(manifest.get("data") or {})
    columns = {
        "timestamp": str(data.get("timestamp_column") or "timestamp"),
        "symbol": str(data.get("symbol_column") or "symbol"),
        "open": str(data.get("open_column") or "open"),
        "high": str(data.get("high_column") or "high"),
        "low": str(data.get("low_column") or "low"),
        "close": str(data.get("close_column") or "close"),
        "volume": str(data.get("volume_column") or "volume"),
    }
    rows: list[dict[str, Any]] = []
    missing_columns: list[str] = []
    with bars_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = [value for value in columns.values() if value not in fieldnames]
        if missing_columns:
            return [], {"missing_required_columns": tuple(sorted(missing_columns)), "raw_row_count": 0}
        for raw in reader:
            ts = _parse_timestamp(raw.get(columns["timestamp"]))
            open_ = _to_float(raw.get(columns["open"]))
            high = _to_float(raw.get(columns["high"]))
            low = _to_float(raw.get(columns["low"]))
            close = _to_float(raw.get(columns["close"]))
            volume = _to_float(raw.get(columns["volume"]))
            invalid = ts is None or open_ is None or high is None or low is None or close is None or volume is None
            if not invalid:
                invalid = high < max(open_, close) or low > min(open_, close) or volume < 0
            rows.append(
                {
                    "timestamp_utc": _format_ts(ts) if ts else None,
                    "symbol": str(raw.get(columns["symbol"]) or "").strip(),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "invalid": bool(invalid),
                }
            )
    return rows, {"missing_required_columns": (), "raw_row_count": len(rows)}


def _quality_metrics(*, rows: list[dict[str, Any]], manifest: dict[str, Any], requested_end: str | None) -> dict[str, Any]:
    valid_rows = [row for row in rows if not row["invalid"] and row["timestamp_utc"] and row["symbol"]]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in valid_rows:
        grouped[(str(row["symbol"]), str(row["timestamp_utc"]))].append(row)

    canonical_rows: list[dict[str, Any]] = []
    exact_duplicates = 0
    conflicts = 0
    overlaps = 0
    for _key, key_rows in sorted(grouped.items()):
        values = [tuple(item[column] for column in ("open", "high", "low", "close", "volume")) for item in key_rows]
        unique_values = list(dict.fromkeys(values))
        if len(key_rows) > 1:
            overlaps += len(key_rows) - 1
        if len(unique_values) == 1:
            exact_duplicates += max(len(key_rows) - 1, 0)
            canonical_rows.append({key_name: key_value for key_name, key_value in key_rows[0].items() if key_name != "invalid"})
        else:
            conflicts += 1

    canonical_rows.sort(key=lambda row: (str(row["symbol"]), str(row["timestamp_utc"])))
    timestamps = [_parse_timestamp(row["timestamp_utc"]) for row in canonical_rows]
    timestamps = [value for value in timestamps if value is not None]
    start = min(timestamps) if timestamps else None
    end = _parse_timestamp(requested_end) if requested_end else (max(timestamps) if timestamps else None)
    symbols = tuple(sorted({str(row["symbol"]) for row in canonical_rows if str(row["symbol"])}))
    manifest_symbols = tuple(str(value) for value in (manifest.get("universe") or {}).get("symbols") or () if str(value))
    symbol_count = len(manifest_symbols or symbols)
    expected = _expected_bar_count(
        calendar=dict(manifest.get("calendar") or {}),
        timeframe=str(manifest.get("timeframe") or (manifest.get("timeframes") or [""])[0]),
        start=start,
        end=end,
        symbol_count=symbol_count,
    )
    unique_count = len(canonical_rows)
    coverage = None if expected in (None, 0) else round(unique_count / expected, 6)
    fingerprint_payload = canonical_payload(canonical_rows)
    return {
        "canonical_rows": canonical_rows,
        "raw_row_count": len(rows),
        "unique_bar_count": unique_count,
        "exact_duplicate_row_count": exact_duplicates,
        "overlapping_row_count": overlaps,
        "conflicting_row_count": conflicts,
        "invalid_row_count": sum(1 for row in rows if row["invalid"]),
        "expected_bar_count": expected,
        "coverage_ratio": coverage,
        "missing_bar_count": max(expected - unique_count, 0) if expected is not None else None,
        "start": _format_ts(start) if start else None,
        "end": _format_ts(end) if end else None,
        "instrument_ids": symbols,
        "data_fingerprint": "sha256:" + stable_digest(fingerprint_payload),
    }


def _manifest_registry_row(manifest: dict[str, Any], manifest_hash: str) -> dict[str, Any]:
    return canonical_payload(
        {
            "source_id": manifest.get("source_id"),
            "provider_id": manifest.get("provider_id"),
            "source_name": manifest.get("source_name") or manifest.get("source_id"),
            "source_type": "market_price_data",
            "source_category": "operator_onboarded_local_file",
            "source_status": manifest.get("source_status") or "manual_review_required",
            "access_method": "local_file_import",
            "authentication_required": False,
            "cost_model": "operator_supplied",
            "license_terms_status": "reviewed" if str(manifest.get("license_policy_status") or "").upper() == "PASS" else "review_required",
            "license_policy_status": manifest.get("license_policy_status"),
            "license_terms_reference": (manifest.get("operator_license_attestation") or {}).get("evidence_ref") or "operator_license_attestation_required",
            "allowed_use": tuple(manifest.get("allowed_use") or ()),
            "forbidden_use": (
                "broker_execution",
                "buy_list",
                "candidate_promotion",
                "capital_allocation",
                "live_activation",
                "paper_activation",
                "sell_list",
                "shadow_activation",
                "strategy_registration",
                "trade_signal",
            ),
            "asset_coverage": (manifest.get("asset_class"),),
            "exchange_coverage": (manifest.get("venue"),),
            "calendar_model": (manifest.get("calendar") or {}).get("type"),
            "schema_version": manifest.get("schema_version"),
            "manifest_status": "PASS" if not _required_manifest_actions(manifest) else "WARN",
            "manifest_block_reasons": tuple(_required_manifest_actions(manifest)),
            "reproducibility_method": "operator_local_file_import",
            "operator_notes": "Onboarded local OHLCV source. Manifest presence never grants trading authority.",
            "manifest_hash": manifest_hash,
        }
    )


def _catalog_dataset(*, manifest: dict[str, Any], snapshot_id: str, metrics: dict[str, Any], manifest_hash: str) -> dict[str, Any]:
    source_id = str(manifest["source_id"])
    timeframe = str(manifest.get("timeframe") or (manifest.get("timeframes") or [""])[0])
    dataset_id = "|".join((source_id, ",".join(metrics["instrument_ids"]), timeframe))
    return canonical_payload(
        {
            "dataset_id": dataset_id,
            "dataset_snapshot_id": snapshot_id,
            "dataset_fingerprint": metrics["data_fingerprint"],
            "source_id": source_id,
            "source_manifest_id": manifest_hash,
            "instrument_ids": metrics["instrument_ids"],
            "timeframe": timeframe,
            "start": metrics["start"],
            "end": metrics["end"],
            "row_count": metrics["unique_bar_count"],
            "quality_summary": {
                "effective_research_quality_status": "ready",
                "row_integrity_status": "ready",
                "minimum_required_history": "derived",
                "minimum_required_rows": 48,
            },
            "identity_summary": {"instrument_identity_status": "ready", "instrument_ids": metrics["instrument_ids"]},
            "integrity_summary": {
                "raw_row_count": metrics["raw_row_count"],
                "unique_bar_count": metrics["unique_bar_count"],
                "expected_bar_count": metrics["expected_bar_count"],
                "coverage_ratio": metrics["coverage_ratio"],
                "exact_duplicate_row_count": metrics["exact_duplicate_row_count"],
                "overlapping_row_count": metrics["overlapping_row_count"],
                "conflicting_row_count": metrics["conflicting_row_count"],
                "invalid_row_count": metrics["invalid_row_count"],
                "activity_estimate": metrics["unique_bar_count"],
                "validation_capacity": 0,
            },
            "adjustment_policy": "explicit_unadjusted" if not (manifest.get("data") or {}).get("adjusted") else "explicit_adjusted",
            "timezone_policy": "UTC_NORMALIZED",
            "session_policy": (manifest.get("calendar") or {}).get("type"),
            "history_span": "derived",
            "validation_capacity": 0,
            "activity_estimate": metrics["unique_bar_count"],
            "source_policy_version": SOURCE_POLICY_VERSION,
            "qualification_policy_version": SOURCE_POLICY_VERSION,
            "provenance": {"generated_at_utc": metrics["end"]},
        }
    )


def import_local_source(
    *,
    repo_root: Path,
    manifest_path: Path,
    bars_path: Path,
    out_dir: Path,
    snapshot_id: str | None = None,
    requested_end: str | None = None,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    if not bars_path.is_file():
        raise FileNotFoundError(f"missing_bars_file: {bars_path}")
    snapshot_id = snapshot_id or content_id("qdsnap", {"manifest": manifest, "bars": bars_path.name})
    rows, column_metrics = _normalize_rows(bars_path=bars_path, manifest=manifest)
    metrics = _quality_metrics(rows=rows, manifest=manifest, requested_end=requested_end)
    metrics = {**column_metrics, **metrics}
    manifest_hash = _manifest_hash(manifest)
    registry_row = _manifest_registry_row(manifest, manifest_hash)
    dataset = _catalog_dataset(manifest=manifest, snapshot_id=snapshot_id, metrics=metrics, manifest_hash=manifest_hash)
    source_id = str(manifest["source_id"])
    timeframe = str(manifest.get("timeframe") or (manifest.get("timeframes") or [""])[0])
    snapshot = DatasetSnapshot(
        dataset_snapshot_id=snapshot_id,
        logical_dataset_family_id=str(dataset["dataset_id"]),
        acquisition_batch_ids=(content_id("qdbatch", {"source": source_id, "snapshot": snapshot_id, "fingerprint": metrics["data_fingerprint"]}),),
        parent_snapshot_id=None,
        instrument_ids=tuple(metrics["instrument_ids"]),
        timeframe=timeframe,
        start=str(metrics["start"] or ""),
        end=str(metrics["end"] or ""),
        unique_bar_count=int(metrics["unique_bar_count"]),
        raw_row_count=int(metrics["raw_row_count"]),
        exact_duplicate_row_count=int(metrics["exact_duplicate_row_count"]),
        overlapping_row_count=int(metrics["overlapping_row_count"]),
        conflicting_row_count=int(metrics["conflicting_row_count"]),
        invalid_row_count=int(metrics["invalid_row_count"]),
        expected_bar_count=metrics["expected_bar_count"],
        coverage_ratio=metrics["coverage_ratio"],
        fingerprint=str(metrics["data_fingerprint"]),
        source_id=source_id,
        source_policy_version=SOURCE_POLICY_VERSION,
        qualification_status="COHERENT" if not metrics["conflicting_row_count"] and not metrics["invalid_row_count"] else "BLOCKED_CONFLICT",
        immutable=True,
        created_at_utc=str(metrics["end"] or ""),
        partition_refs=(out_dir.relative_to(repo_root).as_posix() + "/bars_normalized.csv",),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity=content_id("qdsnaprow", {"snapshot": snapshot_id, "fingerprint": metrics["data_fingerprint"], "metrics": metrics}),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = out_dir / "bars_normalized.csv"
    with normalized_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp_utc", "symbol", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(metrics["canonical_rows"])
    append_snapshot_row(repo_root, snapshot)

    source_manifest = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_onboarding_manifest",
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "provider_id": manifest.get("provider_id"),
        "manifest_hash": manifest_hash,
        "manifest": canonical_payload(manifest),
        "registry_row": registry_row,
        "operator_actions": _required_manifest_actions(manifest),
        "generated_at_utc": _utcnow(),
    }
    import_audit = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_onboarding_import_audit",
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "provider_id": manifest.get("provider_id"),
        "manifest_hash": manifest_hash,
        "data_fingerprint": metrics["data_fingerprint"],
        "imported_row_count": metrics["raw_row_count"],
        "unique_bar_count": metrics["unique_bar_count"],
        "expected_bar_count": metrics["expected_bar_count"],
        "coverage_ratio": metrics["coverage_ratio"],
        "duplicate_row_count": metrics["exact_duplicate_row_count"],
        "conflicting_duplicate_count": metrics["conflicting_row_count"],
        "invalid_row_count": metrics["invalid_row_count"],
        "missing_required_columns": metrics["missing_required_columns"],
        "source_tier": "SOURCE_BLOCKED",
        "qualification_status": "PENDING_SOURCE_QUALIFICATION",
        "policy_version": SOURCE_POLICY_VERSION,
        "generated_at_utc": _utcnow(),
    }
    current_onboarding = _read_json(repo_root / ONBOARDING_DIR / "latest.json") or {"rows": []}
    prior_rows = [
        dict(row)
        for row in current_onboarding.get("rows") or []
        if not (str(row.get("source_id") or "") == source_id and str(row.get("snapshot_id") or "") == snapshot_id)
    ]
    onboarding_row = {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "provider_id": manifest.get("provider_id"),
        "manifest_hash": manifest_hash,
        "data_fingerprint": metrics["data_fingerprint"],
        "operator_actions": _required_manifest_actions(manifest),
    }
    onboarding = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_onboarding",
        "operator_actions": _required_manifest_actions(manifest),
        "rows": sorted([*prior_rows, onboarding_row], key=lambda row: (str(row.get("source_id") or ""), str(row.get("snapshot_id") or ""))),
        "content_identity": content_id("qreonboard", {"manifest": manifest_hash, "fingerprint": metrics["data_fingerprint"], "snapshot": snapshot_id}),
    }
    payload = canonical_payload(
        {
            "source_manifest": source_manifest,
            "import_audit": import_audit,
            "onboarding": onboarding,
            "snapshot": snapshot.__dict__ if hasattr(snapshot, "__dict__") else {
                key: getattr(snapshot, key) for key in DatasetSnapshot.__dataclass_fields__
            },
            "dataset_catalog": {"datasets": [dataset]},
        }
    )
    _write_json(repo_root / ONBOARDING_DIR / "source_manifest_latest.json", source_manifest)
    _write_json(repo_root / ONBOARDING_DIR / f"{source_id}_{snapshot_id}_source_manifest.json", source_manifest)
    _write_json(repo_root / ONBOARDING_DIR / "import_audit_latest.json", import_audit)
    _write_json(repo_root / ONBOARDING_DIR / f"{source_id}_{snapshot_id}_import_audit.json", import_audit)
    _write_json(repo_root / ONBOARDING_DIR / "latest.json", onboarding)
    _write_json(repo_root / ONBOARDING_DIR / f"{source_id}_{snapshot_id}_catalog.json", {"schema_version": SCHEMA_VERSION, "datasets": [dataset]})
    return payload


def _load_onboarded_manifest(repo_root: Path, source_id: str | None = None) -> dict[str, Any] | None:
    payload = _read_json(repo_root / ONBOARDING_DIR / "source_manifest_latest.json")
    if payload is not None and (source_id is None or str(payload.get("source_id") or "") == source_id):
        return payload
    if source_id is None:
        return None
    matches = sorted((repo_root / ONBOARDING_DIR).glob(f"{source_id}_*_source_manifest.json"))
    for match in matches:
        payload = _read_json(match)
        if payload is not None and str(payload.get("source_id") or "") == source_id:
            return payload
    return None


def qualify_onboarded_source(*, repo_root: Path, source_id: str, snapshot_id: str | None = None) -> dict[str, Any]:
    manifest_payload = _load_onboarded_manifest(repo_root, source_id)
    if manifest_payload is None:
        raise FileNotFoundError(f"missing_source_manifest: {source_id}")
    catalog_path = repo_root / ONBOARDING_DIR / f"{source_id}_{snapshot_id or manifest_payload.get('snapshot_id')}_catalog.json"
    catalog = _read_json(catalog_path)
    if catalog is None:
        raise FileNotFoundError(f"missing_onboarding_catalog: {catalog_path}")
    registry_row = dict(manifest_payload.get("registry_row") or {})
    policy = {
        "current_yfinance_status": "manual_research_only",
        "content_identity": content_id("qsp", {"onboarded_source": source_id, "manifest": manifest_payload.get("manifest_hash")}),
        "policy_version": SOURCE_POLICY_VERSION,
    }
    qualification = qualify_datasets(
        repo_root=repo_root,
        dataset_catalog=catalog,
        policy_reconciliation=policy,
        extra_manifest_rows=[registry_row],
    )
    rows = qualification.get("rows") or []
    row = dict(rows[0]) if rows else {}
    source_certification = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_certification",
        "source_id": source_id,
        "snapshot_id": snapshot_id or manifest_payload.get("snapshot_id"),
        "qualification_status": row.get("qualification_status"),
        "source_tier": row.get("allowed_evidence_tier"),
        "blocked_reasons": row.get("reason_codes") or [],
        "operator_actions": _operator_actions_for_reasons(row.get("reason_codes") or []),
        "policy_version": SOURCE_POLICY_VERSION,
        "content_identity": content_id("qresourcecert", row),
        "generated_at_utc": _utcnow(),
    }
    blockers = list(row.get("reason_codes") or [])
    resolution_row = {
        "resolution_id": content_id("qsr", {"source": source_id, "snapshot": snapshot_id or manifest_payload.get("snapshot_id"), "blockers": blockers}),
        "requirement_id": "qre_source_onboarding",
        "candidate_sources": [source_id],
        "selected_source": source_id,
        "selected_snapshot": snapshot_id or manifest_payload.get("snapshot_id"),
        "current_source_tier": row.get("allowed_evidence_tier"),
        "target_source_tier": "SOURCE_SCREENING_ELIGIBLE",
        "qualification_actions": ["use_onboarded_local_snapshot"],
        "credential_requirements": [],
        "license_requirements": ["operator_license_attestation"] if "source_license_not_screening_eligible" in blockers else [],
        "cross_source_requirements": [],
        "unresolved_blockers": blockers,
        "operator_action_required": bool(source_certification["operator_actions"]),
        "automatic_actions_allowed": not bool(source_certification["operator_actions"]),
        "trading_authority": False,
    }
    resolution_row["content_identity"] = content_id("qsrc", resolution_row)
    resolution = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_alpha_source_resolution",
        "rows": [resolution_row],
        "content_identity": content_id("qsrset", resolution_row),
    }
    onboarding = _read_json(repo_root / ONBOARDING_DIR / "latest.json") or {"rows": []}
    for onboarding_row in onboarding.get("rows") or []:
        if str(onboarding_row.get("source_id") or "") != source_id:
            continue
        if snapshot_id is not None and str(onboarding_row.get("snapshot_id") or "") != snapshot_id:
            continue
        onboarding_row["qualification_status"] = row.get("qualification_status")
        onboarding_row["source_tier"] = row.get("allowed_evidence_tier")
        onboarding_row["blocked_reasons"] = row.get("reason_codes") or []
        onboarding_row["operator_actions"] = source_certification["operator_actions"]
        onboarding["operator_actions"] = source_certification["operator_actions"]
    if onboarding.get("rows"):
        onboarding["content_identity"] = content_id("qreonboard", onboarding["rows"])
    _write_json(repo_root / SOURCE_QUALIFICATIONS_PATH, qualification)
    _write_json(repo_root / SOURCE_CERTIFICATION_PATH, source_certification)
    _write_json(repo_root / SOURCE_RESOLUTION_PATH, resolution)
    _write_json(repo_root / ONBOARDING_DIR / "latest.json", onboarding)
    return canonical_payload(
        {
            "source_qualification": qualification,
            "source_certification": source_certification,
            "source_resolution": resolution,
            "onboarding": onboarding,
        }
    )


def _operator_actions_for_reasons(reasons: list[str] | tuple[str, ...]) -> list[str]:
    actions = []
    mapping = {
        "source_license_not_screening_eligible": "provide_screening_license_attestation",
        "missing_calendar": "provide_supported_calendar",
        "missing_expected_bar_count": "provide_supported_calendar",
        "insufficient_coverage": "provide_more_complete_bars",
        "conflicting_rows_present": "repair_conflicting_duplicate_bars",
        "duplicate_bar_ratio_too_high": "deduplicate_source_export",
    }
    for reason in reasons:
        action = mapping.get(str(reason))
        if action:
            actions.append(action)
    return sorted(dict.fromkeys(actions))


def summarize_onboarding(*, repo_root: Path) -> dict[str, Any]:
    onboarding = _read_json(repo_root / ONBOARDING_DIR / "latest.json") or {"rows": []}
    qualifications = _read_json(repo_root / SOURCE_QUALIFICATIONS_PATH) or {"rows": []}
    rows = [dict(row) for row in qualifications.get("rows") or [] if isinstance(row, dict)]
    reason_counts = Counter(reason for row in rows for reason in row.get("reason_codes") or [])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_source_onboarding_summary",
        "summary": {
            "source_count": len({str(row.get("source_id") or "") for row in onboarding.get("rows") or [] if str(row.get("source_id") or "")}),
            "snapshot_count": len(rows),
            "screening_eligible_count": sum(1 for row in rows if row.get("allowed_evidence_tier") == "SOURCE_SCREENING_ELIGIBLE"),
            "validation_eligible_count": sum(1 for row in rows if row.get("allowed_evidence_tier") == "SOURCE_VALIDATION_ELIGIBLE"),
            "blocked_count": sum(1 for row in rows if row.get("allowed_evidence_tier") == "SOURCE_BLOCKED"),
            "blocked_reasons": dict(sorted(reason_counts.items())),
        },
        "rows": onboarding.get("rows") or [],
        "content_identity": content_id("qreonboardsummary", {"rows": onboarding.get("rows") or [], "qualifications": rows}),
    }
    return canonical_payload(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.qre_source_onboarding")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-manifest")
    validate.add_argument("--manifest", required=True)
    local = sub.add_parser("import-local")
    local.add_argument("--manifest", required=True)
    local.add_argument("--bars", required=True)
    local.add_argument("--out", required=True)
    local.add_argument("--snapshot-id")
    local.add_argument("--repo-root", default=".")
    qualify = sub.add_parser("qualify")
    qualify.add_argument("--source-id", required=True)
    qualify.add_argument("--snapshot-id")
    qualify.add_argument("--repo-root", default=".")
    audit = sub.add_parser("audit")
    audit.add_argument("--source-id", required=True)
    audit.add_argument("--repo-root", default=".")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    if args.command == "validate-manifest":
        payload = validate_manifest_file(Path(args.manifest))
    elif args.command == "import-local":
        payload = import_local_source(
            repo_root=Path(args.repo_root),
            manifest_path=Path(args.manifest),
            bars_path=Path(args.bars),
            out_dir=Path(args.out),
            snapshot_id=args.snapshot_id,
        )
    elif args.command == "qualify":
        payload = qualify_onboarded_source(repo_root=Path(args.repo_root), source_id=args.source_id, snapshot_id=args.snapshot_id)
    elif args.command == "audit":
        payload = _read_json(Path(args.repo_root) / SOURCE_CERTIFICATION_PATH) or {}
    else:
        payload = summarize_onboarding(repo_root=Path(args.repo_root))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "import_local_source",
    "main",
    "qualify_onboarded_source",
    "summarize_onboarding",
    "validate_manifest_file",
]
