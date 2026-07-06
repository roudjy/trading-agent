from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.qre_data.dataset_catalog import materialize_data_truth

from .contracts import (
    DatasetSnapshot,
    SnapshotRevision,
    canonical_payload,
    content_id,
    stable_digest,
)

SNAPSHOT_LINEAGE_PATH = Path("generated_research/data_catalog/snapshot_lineage/latest.json")
REVISIONS_PATH = Path("generated_research/data_catalog/revisions/latest.json")

_CACHE_PATTERN = re.compile(
    r"^(?P<source>[^_]+(?:_[^_]+)*)__(?P<instrument>.+?)__(?P<timeframe>\d+[dh])__(?P<start>\d{8})__(?P<end>\d{8})__(?P<hash>[0-9a-f]{16,64})\.parquet$",
    re.IGNORECASE,
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _parse_cache_identity(path_text: str) -> dict[str, str]:
    name = Path(path_text).name
    match = _CACHE_PATTERN.match(name)
    if not match:
        return {
            "source": "unknown",
            "instrument": "unknown",
            "timeframe": "unknown",
            "start": "",
            "end": "",
            "hash": "",
        }
    return {key: str(value) for key, value in match.groupdict().items()}


def _query_timestamp(value: str) -> str:
    if len(value) != 8:
        return ""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}T00:00:00Z"


def _normalize_partition_refs(partition_refs: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not partition_refs:
        return ()
    normalized = {Path(str(value)).name for value in partition_refs if str(value).strip()}
    return tuple(sorted(normalized))


def _snapshot_semantic_identity(snapshot: DatasetSnapshot | dict[str, Any]) -> dict[str, Any]:
    row = asdict(snapshot) if isinstance(snapshot, DatasetSnapshot) else dict(snapshot)
    return canonical_payload(
        {
            "logical_dataset_family_id": row.get("logical_dataset_family_id") or "",
            "acquisition_batch_ids": tuple(sorted(str(value) for value in row.get("acquisition_batch_ids") or () if str(value).strip())),
            "parent_snapshot_id": row.get("parent_snapshot_id"),
            "instrument_ids": tuple(sorted(str(value) for value in row.get("instrument_ids") or () if str(value).strip())),
            "timeframe": row.get("timeframe") or "",
            "start": row.get("start") or "",
            "end": row.get("end") or "",
            "unique_bar_count": int(row.get("unique_bar_count") or 0),
            "raw_row_count": int(row.get("raw_row_count") or 0),
            "exact_duplicate_row_count": int(row.get("exact_duplicate_row_count") or 0),
            "overlapping_row_count": int(row.get("overlapping_row_count") or 0),
            "conflicting_row_count": int(row.get("conflicting_row_count") or 0),
            "invalid_row_count": int(row.get("invalid_row_count") or 0),
            "expected_bar_count": row.get("expected_bar_count"),
            "coverage_ratio": row.get("coverage_ratio"),
            "fingerprint": row.get("fingerprint") or "",
            "source_id": row.get("source_id") or "",
            "source_policy_version": row.get("source_policy_version") or "",
            "qualification_status": row.get("qualification_status") or "",
            "immutable": bool(row.get("immutable")),
            "compatibility_status": row.get("compatibility_status") or "",
            "lineage_depth": int(row.get("lineage_depth") or 0),
        }
    )


def _row_sort_key(row: dict[str, Any]) -> tuple[str, int, str, str, str]:
    return (
        str(row.get("logical_dataset_family_id") or ""),
        int(row.get("lineage_depth") or 0),
        str(row.get("start") or ""),
        str(row.get("end") or ""),
        str(row.get("dataset_snapshot_id") or ""),
    )


def _canonicalize_snapshot_row(row: DatasetSnapshot | dict[str, Any]) -> dict[str, Any]:
    payload = asdict(row) if isinstance(row, DatasetSnapshot) else dict(row)
    semantic_identity = _snapshot_semantic_identity(payload)
    dataset_snapshot_id = str(payload.get("dataset_snapshot_id") or "")
    if not dataset_snapshot_id or dataset_snapshot_id == "pending":
        dataset_snapshot_id = content_id("qdsnap", semantic_identity)
    normalized = {
        **payload,
        "dataset_snapshot_id": dataset_snapshot_id,
        "acquisition_batch_ids": tuple(sorted(str(value) for value in payload.get("acquisition_batch_ids") or () if str(value).strip())),
        "instrument_ids": tuple(sorted(str(value) for value in payload.get("instrument_ids") or () if str(value).strip())),
        "partition_refs": _normalize_partition_refs(payload.get("partition_refs")),
        "created_at_utc": str(payload.get("created_at_utc") or payload.get("end") or ""),
        "content_identity": str(payload.get("content_identity") or "") or content_id("qdsnaprow", semantic_identity),
    }
    if normalized["content_identity"] == "pending":
        normalized["content_identity"] = content_id("qdsnaprow", semantic_identity)
    return canonical_payload(normalized)


def _snapshot_set_identity(rows: list[dict[str, Any]]) -> str:
    canonical_rows = sorted((_canonicalize_snapshot_row(row) for row in rows), key=_row_sort_key)
    identity_rows = [_snapshot_semantic_identity(row) for row in canonical_rows]
    return content_id("qdsnapset", identity_rows)


def _canonicalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in payload.get("rows", []) if isinstance(row, dict)]
    normalized_rows = sorted((_canonicalize_snapshot_row(row) for row in rows), key=_row_sort_key)
    summary = {
        "families": len({str(row.get("logical_dataset_family_id") or "") for row in normalized_rows}),
        "snapshots": len(normalized_rows),
        "revisions": int((payload.get("summary") or {}).get("revisions") or 0),
        "coherent_snapshots": sum(1 for row in normalized_rows if str(row.get("qualification_status") or "") == "COHERENT"),
    }
    return {
        "schema_version": str(payload.get("schema_version") or "1.0"),
        "report_kind": str(payload.get("report_kind") or "qre_dataset_snapshot_lineage"),
        "rows": normalized_rows,
        "summary": summary,
        "content_identity": _snapshot_set_identity(normalized_rows),
    }


def _snapshot_status(*, quality_status: str, conflicting_row_count: int, raw_row_count: int, unique_bar_count: int, expected_bar_count: int | None) -> str:
    if quality_status == "blocked":
        return "BLOCKED_INTEGRITY"
    if conflicting_row_count:
        return "BLOCKED_CONFLICT"
    if expected_bar_count is not None and unique_bar_count > expected_bar_count:
        return "BLOCKED_IMPOSSIBLE_DENSITY"
    if raw_row_count < unique_bar_count:
        return "BLOCKED_INTEGRITY"
    return "COHERENT"


def _dataset_snapshot_from_logical(row: dict[str, Any]) -> DatasetSnapshot:
    integrity = dict(row.get("integrity_summary") or {})
    quality = dict(row.get("quality_summary") or {})
    instrument_ids = tuple(str(value) for value in row.get("instrument_ids") or () if str(value))
    dataset_id = str(row.get("dataset_id") or "|".join((str(row.get("source_id") or ""), ",".join(instrument_ids), str(row.get("timeframe") or ""))))
    unique_bar_count = int(integrity.get("unique_bar_count") or row.get("row_count") or 0)
    raw_row_count = int(integrity.get("raw_row_count") or row.get("raw_row_count") or unique_bar_count)
    expected_bar_count = integrity.get("expected_bar_count")
    if expected_bar_count is not None:
        expected_bar_count = int(expected_bar_count)
    coverage_ratio = integrity.get("coverage_ratio")
    if coverage_ratio is not None:
        coverage_ratio = round(float(coverage_ratio), 6)
    conflicting_row_count = int(integrity.get("conflicting_row_count") or 0)
    invalid_row_count = int(integrity.get("invalid_row_count") or 0)
    exact_duplicate_row_count = int(integrity.get("exact_duplicate_row_count") or 0)
    overlapping_row_count = int(integrity.get("overlapping_row_count") or 0)
    row_integrity_status = str(quality.get("row_integrity_status") or "blocked").lower()
    qualification_status = _snapshot_status(
        quality_status="ready" if row_integrity_status == "ready" else "blocked",
        conflicting_row_count=conflicting_row_count,
        raw_row_count=raw_row_count,
        unique_bar_count=unique_bar_count,
        expected_bar_count=expected_bar_count,
    )
    semantic = {
        "dataset_id": dataset_id,
        "fingerprint": row.get("dataset_fingerprint"),
        "source_id": row.get("source_id"),
        "instrument_ids": instrument_ids,
        "timeframe": row.get("timeframe"),
        "start": row.get("start"),
        "end": row.get("end"),
        "unique_bar_count": unique_bar_count,
        "expected_bar_count": expected_bar_count,
    }
    snapshot = DatasetSnapshot(
        dataset_snapshot_id=str(row.get("dataset_snapshot_id") or "") or content_id("qdsnap", semantic),
        logical_dataset_family_id=dataset_id,
        acquisition_batch_ids=tuple(sorted(str(value) for value in row.get("acquisition_batch_ids") or row.get("partition_refs") or () if str(value))),
        parent_snapshot_id=None,
        instrument_ids=instrument_ids,
        timeframe=str(row.get("timeframe") or ""),
        start=str(row.get("start") or ""),
        end=str(row.get("end") or ""),
        unique_bar_count=unique_bar_count,
        raw_row_count=raw_row_count,
        exact_duplicate_row_count=exact_duplicate_row_count,
        overlapping_row_count=overlapping_row_count,
        conflicting_row_count=conflicting_row_count,
        invalid_row_count=invalid_row_count,
        expected_bar_count=expected_bar_count,
        coverage_ratio=coverage_ratio,
        fingerprint=str(row.get("dataset_fingerprint") or stable_digest(semantic)),
        source_id=str(row.get("source_id") or ""),
        source_policy_version=str(row.get("source_policy_version") or row.get("source_manifest_id") or "data_catalog_logical_v1"),
        qualification_status=qualification_status,
        immutable=True,
        created_at_utc=str((row.get("provenance") or {}).get("generated_at_utc") or row.get("complete_bar_end") or row.get("end") or ""),
        partition_refs=tuple(sorted(str(value) for value in row.get("partition_refs") or () if str(value))),
        compatibility_status="ROOT",
        lineage_depth=0,
        content_identity="pending",
    )
    return DatasetSnapshot(**_canonicalize_snapshot_row(snapshot))


def _build_base_snapshots(census: dict[str, Any]) -> list[DatasetSnapshot]:
    snapshots: list[DatasetSnapshot] = []
    logical_rows = [dict(row) for row in census.get("logical_datasets") or [] if isinstance(row, dict)]
    if logical_rows:
        snapshots = [_dataset_snapshot_from_logical(row) for row in logical_rows]
        snapshots.sort(key=lambda item: (item.logical_dataset_family_id, item.start, item.end, item.dataset_snapshot_id))
        return snapshots
    seen_paths: set[str] = set()
    for row in census.get("physical_files", []):
        path_text = str(row.get("portable_relative_path") or row.get("physical_path") or "")
        if not path_text or path_text in seen_paths:
            continue
        seen_paths.add(path_text)
        parsed = _parse_cache_identity(path_text)
        batch_seed = {
            "source": parsed["source"],
            "instrument": parsed["instrument"],
            "timeframe": parsed["timeframe"],
            "start": parsed["start"],
            "end": parsed["end"],
            "fingerprint": row.get("dataset_fingerprint") or parsed["hash"],
            "row_count": int(row.get("row_count") or 0),
        }
        batch_id = content_id("qdbatch", batch_seed)
        batch_identity = {
            **batch_seed,
            "batch_id": batch_id,
        }
        raw_row_count = int(row.get("row_count") or 0)
        expected_bar_count = raw_row_count if parsed["timeframe"] == "unknown" else None
        snapshot = DatasetSnapshot(
            dataset_snapshot_id="pending",
            logical_dataset_family_id="|".join((parsed["source"], parsed["instrument"], parsed["timeframe"])),
            acquisition_batch_ids=(batch_id,),
            parent_snapshot_id=None,
            instrument_ids=(parsed["instrument"],),
            timeframe=parsed["timeframe"],
            start=_query_timestamp(parsed["start"]),
            end=_query_timestamp(parsed["end"]),
            unique_bar_count=raw_row_count,
            raw_row_count=raw_row_count,
            exact_duplicate_row_count=0,
            overlapping_row_count=0,
            conflicting_row_count=0,
            invalid_row_count=0,
            expected_bar_count=expected_bar_count,
            coverage_ratio=1.0,
            fingerprint=str(row.get("dataset_fingerprint") or parsed["hash"] or stable_digest(batch_identity)),
            source_id=parsed["source"],
            source_policy_version="cache_file_v1",
            qualification_status=_snapshot_status(
                quality_status=str(row.get("effective_research_quality_status") or "blocked"),
                conflicting_row_count=0,
                raw_row_count=raw_row_count,
                unique_bar_count=raw_row_count,
                expected_bar_count=expected_bar_count,
            ),
            immutable=True,
            created_at_utc=str(row.get("complete_bar_end") or _query_timestamp(parsed["end"]) or ""),
            partition_refs=(path_text,),
            compatibility_status="ROOT",
            lineage_depth=0,
            content_identity="pending",
        )
        snapshots.append(DatasetSnapshot(**_canonicalize_snapshot_row(snapshot)))
    snapshots.sort(key=lambda item: (item.logical_dataset_family_id, item.start, item.end, item.dataset_snapshot_id))
    return snapshots


def _ranges_overlap(left: DatasetSnapshot, right: DatasetSnapshot) -> bool:
    if not left.start or not left.end or not right.start or not right.end:
        return False
    left_start = left.start
    left_end = left.end
    right_start = right.start
    right_end = right.end
    return not (left_end < right_start or right_end < left_start)


def _build_lineage_rows(base_snapshots: list[DatasetSnapshot]) -> tuple[list[DatasetSnapshot], list[SnapshotRevision]]:
    final_rows: list[DatasetSnapshot] = []
    revisions: list[SnapshotRevision] = []
    by_family: dict[str, list[DatasetSnapshot]] = defaultdict(list)
    for row in base_snapshots:
        by_family[row.logical_dataset_family_id].append(row)
    for family, items in sorted(by_family.items()):
        lineage_heads: list[DatasetSnapshot] = []
        for item in items:
            attached = False
            for head in list(lineage_heads):
                if not _ranges_overlap(head, item):
                    child = DatasetSnapshot(
                        dataset_snapshot_id="pending",
                        logical_dataset_family_id=family,
                        acquisition_batch_ids=head.acquisition_batch_ids + item.acquisition_batch_ids,
                        parent_snapshot_id=head.dataset_snapshot_id,
                        instrument_ids=head.instrument_ids,
                        timeframe=head.timeframe,
                        start=min(filter(None, (head.start, item.start)), default=head.start),
                        end=max(filter(None, (head.end, item.end)), default=item.end),
                        unique_bar_count=head.unique_bar_count + item.unique_bar_count,
                        raw_row_count=head.raw_row_count + item.raw_row_count,
                        exact_duplicate_row_count=head.exact_duplicate_row_count + item.exact_duplicate_row_count,
                        overlapping_row_count=head.overlapping_row_count + item.overlapping_row_count,
                        conflicting_row_count=head.conflicting_row_count + item.conflicting_row_count,
                        invalid_row_count=head.invalid_row_count + item.invalid_row_count,
                        expected_bar_count=(head.expected_bar_count or 0) + (item.expected_bar_count or 0) or None,
                        coverage_ratio=None,
                        fingerprint=content_id("qdsnapfp", (head.fingerprint, item.fingerprint)),
                        source_id=head.source_id,
                        source_policy_version=head.source_policy_version,
                        qualification_status="COHERENT",
                        immutable=True,
                        created_at_utc=item.end or head.end or "",
                        partition_refs=head.partition_refs + item.partition_refs,
                        compatibility_status="COMPATIBLE_APPEND",
                        lineage_depth=head.lineage_depth + 1,
                        content_identity="pending",
                    )
                    child = DatasetSnapshot(**_canonicalize_snapshot_row(child))
                    lineage_heads.remove(head)
                    lineage_heads.append(child)
                    final_rows.append(child)
                    attached = True
                    break
                overlap_count = min(head.unique_bar_count, item.unique_bar_count)
                conflict_count = overlap_count if head.fingerprint != item.fingerprint else 0
                revision_seed = {
                    "family": family,
                    "baseline": head.dataset_snapshot_id,
                    "candidate": item.dataset_snapshot_id,
                    "overlap_count": overlap_count,
                    "conflict_count": conflict_count,
                }
                revisions.append(
                    SnapshotRevision(
                        revision_id=content_id("qdrev", revision_seed),
                        logical_dataset_family_id=family,
                        baseline_snapshot_id=head.dataset_snapshot_id,
                        candidate_snapshot_id=item.dataset_snapshot_id,
                        overlapping_bar_count=overlap_count,
                        conflicting_bar_count=conflict_count,
                        status="INCOMPATIBLE_REVISION",
                        reason_codes=("cross_snapshot_conflict",),
                        content_identity=content_id("qdrevc", revision_seed),
                    )
                )
            if not attached:
                lineage_heads.append(item)
                final_rows.append(item)
    deduped = {row.dataset_snapshot_id: row for row in final_rows}
    return sorted(deduped.values(), key=lambda item: (item.logical_dataset_family_id, item.lineage_depth, item.start, item.end)), revisions


def materialize_snapshot_lineage(repo_root: Path, *, write_outputs: bool = True, force_refresh: bool = False) -> dict[str, Any]:
    truth = materialize_data_truth(repo_root, force_refresh=force_refresh)
    base_snapshots = _build_base_snapshots(truth["census"])
    snapshots, revisions = _build_lineage_rows(base_snapshots)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_dataset_snapshot_lineage",
        "rows": [_canonicalize_snapshot_row(row) for row in snapshots],
        "summary": {
            "families": len({row.logical_dataset_family_id for row in snapshots}),
            "snapshots": len(snapshots),
            "revisions": len(revisions),
            "coherent_snapshots": sum(1 for row in snapshots if row.qualification_status == "COHERENT"),
        },
        "content_identity": _snapshot_set_identity([asdict(row) for row in snapshots]),
    }
    revisions_payload = {
        "schema_version": "1.0",
        "report_kind": "qre_dataset_snapshot_revisions",
        "rows": [asdict(row) for row in revisions],
        "content_identity": content_id("qdrevset", [asdict(row) for row in revisions]),
    }
    if write_outputs:
        _atomic_json(repo_root / SNAPSHOT_LINEAGE_PATH, payload)
        _atomic_json(repo_root / REVISIONS_PATH, revisions_payload)
    return {
        "snapshot_lineage": payload,
        "revisions": revisions_payload,
        "frames": {},
        "catalog_identity": truth["catalog"].get("content_identity"),
    }


def load_snapshot_lineage(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / SNAPSHOT_LINEAGE_PATH)
    revisions = _read_json(repo_root / REVISIONS_PATH)
    if payload is not None and revisions is not None:
        normalized = _canonicalize_snapshot_payload(payload)
        if normalized != payload:
            _atomic_json(repo_root / SNAPSHOT_LINEAGE_PATH, normalized)
        return {"snapshot_lineage": normalized, "revisions": revisions}
    return materialize_snapshot_lineage(repo_root, write_outputs=True, force_refresh=False)


def append_snapshot_row(repo_root: Path, snapshot: DatasetSnapshot) -> dict[str, Any]:
    current = load_snapshot_lineage(repo_root)
    rows = [dict(row) for row in current.get("snapshot_lineage", {}).get("rows", []) if isinstance(row, dict)]
    rows = [row for row in rows if str(row.get("dataset_snapshot_id") or "") != snapshot.dataset_snapshot_id]
    rows.append(asdict(snapshot))
    rows.sort(key=lambda row: (str(row.get("logical_dataset_family_id") or ""), int(row.get("lineage_depth") or 0), str(row.get("start") or "")))
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_dataset_snapshot_lineage",
        "rows": sorted((_canonicalize_snapshot_row(row) for row in rows), key=_row_sort_key),
        "summary": {
            "families": len({str(row.get("logical_dataset_family_id") or "") for row in rows}),
            "snapshots": len(rows),
            "revisions": len(current.get("revisions", {}).get("rows", []) or []),
            "coherent_snapshots": sum(1 for row in rows if str(row.get("qualification_status") or "") == "COHERENT"),
        },
        "content_identity": _snapshot_set_identity(rows),
    }
    _atomic_json(repo_root / SNAPSHOT_LINEAGE_PATH, payload)
    return {"snapshot_lineage": payload, "revisions": current.get("revisions", {"rows": []})}


def coherent_snapshots(payload: dict[str, Any], *, source_id: str | None = None) -> list[dict[str, Any]]:
    rows = [dict(row) for row in payload.get("snapshot_lineage", {}).get("rows", []) if isinstance(row, dict)]
    filtered = [
        row
        for row in rows
        if str(row.get("qualification_status") or "") == "COHERENT"
        and (source_id is None or str(row.get("source_id") or "") == source_id)
    ]
    return sorted(
        filtered,
        key=lambda row: (
            -int(row.get("unique_bar_count") or 0),
            -int(row.get("lineage_depth") or 0),
            str(row.get("dataset_snapshot_id") or ""),
        ),
    )


__all__ = [
    "REVISIONS_PATH",
    "SNAPSHOT_LINEAGE_PATH",
    "append_snapshot_row",
    "coherent_snapshots",
    "load_snapshot_lineage",
    "materialize_snapshot_lineage",
]
