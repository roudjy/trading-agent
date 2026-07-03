from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from packages.qre_data import cache_manifest as cm
from packages.qre_data import source_quality_readiness as sqr
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "qre_alpha_data_truth_v1"
CENSUS_PATH = Path("generated_research/data_catalog/census/latest.json")
CATALOG_PATH = Path("generated_research/data_catalog/catalog/latest.json")
RECONCILIATION_PATH = Path("generated_research/data_catalog/reconciliation/latest.json")
STATUS_PATH = Path("generated_research/data_catalog/status/latest.json")
BASELINE_POLICY_PATH = Path("generated_research/data_catalog/baseline_corpus_policy/latest.json")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{_digest(value)[:16]}"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_absolute_portability_issue(value: str) -> bool:
    text = str(value or "")
    return bool(text) and (":/" in text or ":\\" in text or text.startswith("/root/") or text.startswith("/tmp/"))


def _portable_relative(value: str, *, repo_root: Path) -> str:
    text = str(value or "").replace("\\", "/")
    if not text:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(repo_root).as_posix()
        except Exception:
            if repo_root.as_posix() in text:
                return text.split(repo_root.as_posix(), 1)[1].lstrip("/")
            return candidate.name
    return text


def _load_manifest(repo_root: Path) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    if isinstance(latest, dict) and latest and (latest.get("files") or latest.get("coverage")):
        return latest
    return cm.build_cache_manifest(repo_root=repo_root)


def _load_quality(repo_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_source_quality_readiness/latest.json")
    if isinstance(latest, dict) and latest:
        return latest
    return sqr.build_source_quality_report(manifest)


def _source_authority_rows() -> dict[str, dict[str, Any]]:
    registry = build_source_manifest_registry()
    rows = registry.get("rows") or []
    return {
        str(row.get("source_name") or "").lower(): dict(row)
        for row in rows
        if isinstance(row, dict)
    } | {
        str(row.get("provider_id") or "").lower(): dict(row)
        for row in rows
        if isinstance(row, dict)
    } | {
        str(row.get("source_id") or "").lower(): dict(row)
        for row in rows
        if isinstance(row, dict)
    }


def _source_authority_for(source: str, authority_rows: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = str(source or "").lower()
    aliases = (
        key,
        "yahoo_finance_yfinance_manifest" if key == "yfinance" else key,
        "yahoo_finance_yfinance" if key == "yfinance" else key,
    )
    for alias in aliases:
        row = authority_rows.get(alias)
        if row is not None:
            return row
    return None


def _effective_source_quality(source: str, authority_rows: Mapping[str, dict[str, Any]]) -> tuple[str, str]:
    authority = _source_authority_for(source, authority_rows)
    if authority is None:
        return "unknown", "source_manifest_missing"
    source_status = str(authority.get("source_status") or "").lower()
    policy_status = str(authority.get("license_policy_status") or "").upper()
    if source_status in {"manual_research_only", "candidate", "staging", "quarantined"}:
        return "blocked", f"source_status_{source_status}"
    if policy_status != "PASS":
        return "blocked", f"license_policy_{policy_status.lower()}"
    if not bool(authority.get("allowed_for_quality_gate")):
        return "blocked", "quality_gate_not_allowed"
    return "ready", "source_authority_ready"


def _collect_dataset_references(repo_root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)
    roots = (
        repo_root / "generated_research",
        repo_root / "logs",
        repo_root / "research",
    )
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            if "data/cache/" not in text and ".parquet" not in text:
                continue
            rel = _rel(path, root=repo_root)
            for token in text.replace("\\", "/").split('"'):
                if ".parquet" not in token:
                    continue
                if "data/cache/" not in token and "artifacts/cache/" not in token:
                    continue
                refs[_portable_relative(token, repo_root=repo_root)].append(rel)
    return {key: sorted(set(value)) for key, value in refs.items()}


def _history_references(repo_root: Path) -> set[str]:
    refs: set[str] = set()
    for payload in _read_jsonl(repo_root / "logs/qre_data_cache_manifest/history.jsonl"):
        for row in payload.get("files") or []:
            if isinstance(row, dict) and row.get("path"):
                refs.add(_portable_relative(str(row["path"]), repo_root=repo_root))
    return refs


def _window_policy_by_timeframe(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(repo_root / "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json") or {}
    rows = payload.get("rows") or []
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        timeframe = str(row.get("timeframe") or "")
        if not timeframe:
            continue
        current = best.get(timeframe)
        if current is None or int(row.get("minimum_train_days") or 0) > int(current.get("minimum_train_days") or 0):
            best[timeframe] = row
    return best


def build_data_census(repo_root: Path) -> dict[str, Any]:
    manifest = _load_manifest(repo_root)
    _load_quality(repo_root, manifest)
    authority_rows = _source_authority_rows()
    dataset_refs = _collect_dataset_references(repo_root)
    historical_refs = _history_references(repo_root)
    window_policies = _window_policy_by_timeframe(repo_root)

    file_rows = [dict(row) for row in manifest.get("files") or [] if isinstance(row, dict)]
    coverage_rows = [dict(row) for row in manifest.get("coverage") or [] if isinstance(row, dict)]
    file_index = {str(row.get("path") or ""): row for row in file_rows}
    duplicate_hashes = Counter(str(row.get("content_hash") or "") for row in file_rows if row.get("content_hash"))

    physical_rows: list[dict[str, Any]] = []
    grouped_paths: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for row in file_rows:
        rel_path = _portable_relative(str(row.get("path") or ""), repo_root=repo_root)
        path = repo_root / rel_path
        source = str(row.get("source") or "")
        key = (source, str(row.get("instrument") or ""), str(row.get("timeframe") or ""))
        grouped_paths[key].append(rel_path)
        source_quality, source_reason = _effective_source_quality(source, authority_rows)
        classification = "PHYSICAL_FILE_PRESENT_AND_MANIFESTED" if path.is_file() else "MANIFEST_REFERENCE_MISSING_FILE"
        if rel_path in historical_refs and not path.is_file():
            classification = "HISTORICAL_REFERENCE_ONLY"
        physical_rows.append(
            {
                "physical_path": rel_path,
                "portable_relative_path": rel_path,
                "exists": path.is_file(),
                "file_size": int(path.stat().st_size) if path.is_file() else None,
                "format": path.suffix.lstrip("."),
                "row_count": int(row.get("row_count") or 0),
                "asset_count": 1,
                "instrument_ids": [str(row.get("instrument") or "")],
                "timeframe": str(row.get("timeframe") or ""),
                "first_timestamp": row.get("min_timestamp_utc"),
                "last_timestamp": row.get("max_timestamp_utc"),
                "complete_bar_end": row.get("max_timestamp_utc"),
                "source_id": source,
                "source_manifest_id": str((_source_authority_for(source, authority_rows) or {}).get("source_id") or ""),
                "identity_status": "ready" if str(row.get("instrument") or "") not in {"", "unknown"} else "ambiguous",
                "quality_status": str(row.get("status") or "unknown"),
                "dataset_id": _content_id("qdpf", {"path": rel_path, "hash": row.get("content_hash")}),
                "dataset_fingerprint": str(row.get("content_hash") or ""),
                "referenced_by_manifests": rel_path in file_index or rel_path in historical_refs,
                "referenced_by_campaigns": dataset_refs.get(rel_path, []),
                "orphaned": False,
                "stale": False,
                "duplicate": duplicate_hashes.get(str(row.get("content_hash") or ""), 0) > 1,
                "superseded": False,
                "machine_specific_path": _is_absolute_portability_issue(str(row.get("path") or "")),
                "highest_possible_evidence_tier": "EXECUTOR_SMOKE" if source_quality != "ready" else "LOCKED_OOS_VALIDATION",
                "effective_research_quality_status": source_quality,
                "effective_research_quality_reason": source_reason,
                "reconciliation_status": classification,
                "content_identity": _content_id("qdcf", {"path": rel_path, "classification": classification}),
            }
        )

    logical_rows: list[dict[str, Any]] = []
    for coverage in coverage_rows:
        key = (str(coverage.get("source") or ""), str(coverage.get("instrument") or ""), str(coverage.get("timeframe") or ""))
        partitions = sorted(grouped_paths.get(key, []))
        source = key[0]
        source_quality, source_reason = _effective_source_quality(source, authority_rows)
        policy = window_policies.get(key[2], {})
        min_train_days = int(policy.get("minimum_train_days") or 0)
        min_validation_days = int(policy.get("minimum_validation_days") or 0)
        min_oos_days = int(policy.get("minimum_oos_days") or 0)
        span_days = 0
        start = str(coverage.get("min_timestamp_utc") or "")
        end = str(coverage.get("max_timestamp_utc") or "")
        if start and end:
            try:
                from datetime import datetime

                span_days = max((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).days, 0)
            except Exception:
                span_days = 0
        validation_ready = span_days >= (min_train_days + min_validation_days)
        oos_ready = span_days >= (min_train_days + min_validation_days + min_oos_days)
        highest_tier = "EXECUTOR_SMOKE"
        if source_quality == "ready" and validation_ready:
            highest_tier = "EMPIRICAL_SCREENING"
        if source_quality == "ready" and oos_ready:
            highest_tier = "LOCKED_OOS_VALIDATION"
        logical_rows.append(
            {
                "dataset_id": _content_id("qds", {"coverage_hash": coverage.get("content_hash"), "key": key}),
                "dataset_fingerprint": str(coverage.get("content_hash") or ""),
                "schema_version": SCHEMA_VERSION,
                "source_id": source,
                "source_manifest_id": str((_source_authority_for(source, authority_rows) or {}).get("source_id") or ""),
                "universe_id": f"{source}:{key[1]}",
                "membership_version": "static_single_instrument",
                "instrument_ids": [key[1]],
                "timeframe": key[2],
                "base_timeframe": key[2],
                "derived_timeframe": None,
                "fields": ["open", "high", "low", "close", "volume"],
                "start": coverage.get("min_timestamp_utc"),
                "end": coverage.get("max_timestamp_utc"),
                "complete_bar_end": coverage.get("max_timestamp_utc"),
                "row_count": int(coverage.get("row_count") or 0),
                "asset_count": 1,
                "partition_refs": partitions,
                "quality_summary": {
                    "row_integrity_status": "ready" if coverage.get("ready") else "blocked",
                    "source_quality_status": source_quality,
                    "campaign_scoped_quality_status": "ready" if coverage.get("ready") else "blocked",
                    "effective_research_quality_status": source_quality,
                    "effective_research_quality_reason": source_reason,
                },
                "identity_summary": {
                    "source_identity_status": "ready" if key[1] not in {"", "unknown"} else "ambiguous",
                    "instrument_identity_status": "ready" if key[1] not in {"", "unknown"} else "ambiguous",
                    "universe_identity_status": "ready",
                },
                "PIT_summary": {"status": "PIT_NOT_REQUIRED"},
                "corporate_action_summary": {"status": "UNKNOWN"},
                "session_calendar_summary": {"status": "UNKNOWN"},
                "coverage_summary": {
                    "file_count": int(coverage.get("file_count") or 0),
                    "span_days": span_days,
                    "status_counts": dict(coverage.get("status_counts") or {}),
                },
                "window_capacity": {
                    "policy_timeframe": key[2],
                    "span_days": span_days,
                    "minimum_train_days": min_train_days,
                    "minimum_validation_days": min_validation_days,
                    "minimum_oos_days": min_oos_days,
                    "validation_ready": validation_ready,
                    "locked_oos_ready": oos_ready,
                },
                "highest_admissible_tier": highest_tier,
                "provenance": {
                    "manifest_latest": "logs/qre_data_cache_manifest/latest.json",
                    "source_quality_latest": "logs/qre_data_source_quality_readiness/latest.json",
                },
                "referenced_by_campaigns": sorted({ref for part in partitions for ref in dataset_refs.get(part, [])}),
                "content_identity": _content_id("qdsl", {"coverage_hash": coverage.get("content_hash"), "key": key, "tier": highest_tier}),
            }
        )

    current_files = {row["portable_relative_path"] for row in physical_rows}
    historical_only = sorted(historical_refs - current_files)
    missing_refs = [row for row in physical_rows if row["reconciliation_status"] == "MANIFEST_REFERENCE_MISSING_FILE"]
    non_portable = [row for row in physical_rows if row["machine_specific_path"]]
    duplicate_content = [row for row in physical_rows if row["duplicate"]]

    root_cause = {
        "pr_722_inventory_path": "packages/qre_research/alpha_discovery/data_planner.py::_choose_rows",
        "selector_behavior": "manifest.files preferred over manifest.coverage when files are present",
        "selector_effect": "physical shard rows with 5 bars each were treated as standalone datasets",
        "broader_logical_datasets_present": bool(logical_rows),
        "example_physical_row_count": int(physical_rows[0]["row_count"]) if physical_rows else None,
        "example_logical_row_count": max((int(row["row_count"]) for row in logical_rows), default=0),
        "source_quality_layer_gap": "file-level quality rows existed, but canonical source-authority still blocks yfinance for empirical readiness",
        "causes": [
            "inventory_bug",
            "source_quality_exclusion",
        ],
        "evidence_refs": [
            "logs/qre_data_cache_manifest/latest.json",
            "logs/qre_data_source_quality_readiness/latest.json",
            "research/external_intelligence/source_manifest_registry.py",
        ],
        "content_identity": _content_id("qdrc", {"logical_count": len(logical_rows), "physical_count": len(physical_rows)}),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_data_census",
        "physical_files": physical_rows,
        "logical_datasets": logical_rows,
        "reconciliation_summary": {
            "files_scanned": len(physical_rows),
            "logical_datasets": len(logical_rows),
            "orphaned_files": 0,
            "missing_referenced_files": len(missing_refs),
            "stale_manifests": 0,
            "duplicate_content": len(duplicate_content),
            "non_portable_paths": len(non_portable),
            "historical_only_datasets": len(historical_only),
        },
        "historical_only_refs": historical_only,
        "root_cause": root_cause,
        "content_identity": _content_id("qdcensus", {"physical": len(physical_rows), "logical": len(logical_rows), "root_cause": root_cause["content_identity"]}),
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8-sig") == text:
                return
        except OSError:
            pass
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_data_catalog.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def materialize_data_truth(repo_root: Path) -> dict[str, Any]:
    census = build_data_census(repo_root)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_dataset_catalog",
        "datasets": census["logical_datasets"],
        "summary": census["reconciliation_summary"],
        "content_identity": _content_id("qdcatalog", census["logical_datasets"]),
    }
    reconciliation = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_data_reconciliation",
        "root_cause": census["root_cause"],
        "summary": census["reconciliation_summary"],
        "content_identity": _content_id("qdrecon", census["root_cause"]),
    }
    baseline_policy = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_baseline_corpus_policy",
        "allowed_asset_classes": ["equity", "crypto"],
        "allowed_markets": ["global"],
        "minimum_liquidity": "cache_discovered_liquid_only",
        "maximum_number_of_assets": 20,
        "base_timeframes": ["1d", "4h", "1h"],
        "history_targets": {"1d": "365d", "4h": "365d", "1h": "120d"},
        "refresh_cadence_metadata": "bounded_on_demand",
        "source_requirements": ["quality_gate_allowed", "research_lineage_required"],
        "identity_requirements": ["resolved_identity"],
        "quality_requirements": ["effective_research_quality_ready"],
        "content_identity": _content_id("qdbase", "baseline_corpus_policy_v1"),
    }
    status = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_data_catalog_status",
        "files_scanned": census["reconciliation_summary"]["files_scanned"],
        "logical_datasets": census["reconciliation_summary"]["logical_datasets"],
        "five_row_root_cause": census["root_cause"]["causes"],
        "content_identity": _content_id("qdstatus", census["reconciliation_summary"]),
    }
    write_json_atomic(repo_root / CENSUS_PATH, census)
    write_json_atomic(repo_root / CATALOG_PATH, catalog)
    write_json_atomic(repo_root / RECONCILIATION_PATH, reconciliation)
    write_json_atomic(repo_root / BASELINE_POLICY_PATH, baseline_policy)
    write_json_atomic(repo_root / STATUS_PATH, status)
    return {
        "census": census,
        "catalog": catalog,
        "reconciliation": reconciliation,
        "baseline_policy": baseline_policy,
        "status": status,
    }


def load_catalog(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / CATALOG_PATH)
    if isinstance(payload, dict) and payload.get("datasets"):
        return payload
    return materialize_data_truth(repo_root)["catalog"]


__all__ = [
    "BASELINE_POLICY_PATH",
    "CATALOG_PATH",
    "CENSUS_PATH",
    "POLICY_VERSION",
    "RECONCILIATION_PATH",
    "SCHEMA_VERSION",
    "STATUS_PATH",
    "build_data_census",
    "load_catalog",
    "materialize_data_truth",
]
