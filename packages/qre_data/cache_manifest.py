"""Read-only local research cache manifest and coverage reporter."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

try:  # pragma: no cover - exercised when dependency is absent.
    import pyarrow.parquet as _pq
except Exception:  # pragma: no cover
    _pq = None

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_data_cache_manifest"
DEFAULT_CACHE_DIRS: Final[dict[str, Path]] = {
    "market": Path("data/cache/market"),
    "macro": Path("data/cache/macro"),
}
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_data_cache_manifest")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/qre_data_cache_manifest/"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _hash_file(path: Path) -> str | None:
    h = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return None
    return f"sha256:{h.hexdigest()}"


def _parse_market_filename(path: Path) -> dict[str, Any]:
    parts = path.stem.split("__")
    if len(parts) != 6:
        return {
            "source": "unknown",
            "instrument": "unknown",
            "timeframe": "unknown",
            "requested_start": None,
            "requested_end": None,
            "cache_key": None,
        }
    source, instrument, timeframe, start, end, cache_key = parts
    return {
        "source": source,
        "instrument": instrument,
        "timeframe": timeframe,
        "requested_start": _date_key_to_iso(start),
        "requested_end": _date_key_to_iso(end),
        "cache_key": cache_key,
    }


def _parse_macro_filename(path: Path) -> dict[str, Any]:
    parts = path.stem.split("__")
    series_id = parts[0] if parts and parts[0] else "unknown"
    return {
        "source": "macro_cache",
        "instrument": series_id,
        "timeframe": "native",
        "requested_start": None,
        "requested_end": None,
        "cache_key": parts[1] if len(parts) > 1 else None,
    }


def _date_key_to_iso(value: str) -> str | None:
    if len(value) != 8 or not value.isdigit():
        return None
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _timestamp_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "as_py"):
        value = value.as_py()
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
        value = _dt.datetime(value.year, value.month, value.day, tzinfo=_dt.UTC)
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_dt.UTC)
        else:
            value = value.astimezone(_dt.UTC)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _parquet_stats(path: Path) -> tuple[int | None, str | None, str | None, str]:
    if _pq is None:
        return None, None, None, "unreadable"
    try:
        parquet_file = _pq.ParquetFile(path)
        row_count = int(parquet_file.metadata.num_rows)
        schema_names = set(parquet_file.schema_arrow.names)
        if row_count <= 0:
            return row_count, None, None, "empty"
        if "timestamp_utc" not in schema_names:
            return row_count, None, None, "missing_timestamp"
        table = _pq.read_table(path, columns=["timestamp_utc"])
        values = [value for value in table.column("timestamp_utc").to_pylist() if value is not None]
    except Exception:
        return None, None, None, "unreadable"
    if not values:
        return row_count, None, None, "missing_timestamp"
    try:
        return row_count, _timestamp_to_iso(min(values)), _timestamp_to_iso(max(values)), "ready"
    except TypeError:
        normalized = sorted(str(value) for value in values)
        return row_count, normalized[0], normalized[-1], "ready"


def _inspect_cache_file(
    path: Path,
    *,
    cache_kind: str,
    repo_root: Path,
) -> dict[str, Any]:
    parsed = _parse_market_filename(path) if cache_kind == "market" else _parse_macro_filename(path)
    row_count, min_ts, max_ts, status = _parquet_stats(path)
    content_hash = _hash_file(path)
    try:
        size_bytes = int(path.stat().st_size)
    except OSError:
        size_bytes = None
        status = "unreadable"
    if content_hash is None:
        status = "unreadable"
    return {
        "path": _rel(path, root=repo_root),
        "cache_kind": cache_kind,
        "source": parsed["source"],
        "instrument": parsed["instrument"],
        "timeframe": parsed["timeframe"],
        "requested_start": parsed["requested_start"],
        "requested_end": parsed["requested_end"],
        "cache_key": parsed["cache_key"],
        "status": status,
        "row_count": row_count,
        "min_timestamp_utc": min_ts,
        "max_timestamp_utc": max_ts,
        "size_bytes": size_bytes,
        "content_hash": content_hash,
    }


def _coverage_rows(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in files:
        key = (
            str(row["source"]),
            str(row["instrument"]),
            str(row["timeframe"]),
        )
        grouped.setdefault(key, []).append(row)

    coverage: list[dict[str, Any]] = []
    for (source, instrument, timeframe), rows in grouped.items():
        row_counts = [
            int(row["row_count"]) for row in rows if isinstance(row.get("row_count"), int)
        ]
        min_values = sorted(
            str(row["min_timestamp_utc"]) for row in rows if row.get("min_timestamp_utc")
        )
        max_values = sorted(
            str(row["max_timestamp_utc"]) for row in rows if row.get("max_timestamp_utc")
        )
        hashes = sorted(str(row["content_hash"]) for row in rows if row.get("content_hash"))
        status_counts = Counter(str(row["status"]) for row in rows)
        digest = hashlib.sha256("|".join(hashes).encode("utf-8")).hexdigest()
        coverage.append(
            {
                "source": source,
                "instrument": instrument,
                "timeframe": timeframe,
                "file_count": len(rows),
                "row_count": sum(row_counts),
                "min_timestamp_utc": min_values[0] if min_values else None,
                "max_timestamp_utc": max_values[-1] if max_values else None,
                "content_hash": f"sha256:{digest}",
                "status_counts": dict(sorted(status_counts.items())),
                "ready": bool(row_counts) and status_counts.get("unreadable", 0) == 0,
            }
        )
    coverage.sort(key=lambda row: (row["source"], row["instrument"], row["timeframe"]))
    return coverage


def build_cache_manifest(
    *,
    cache_dirs: Mapping[str, Path] | None = None,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    when = generated_at_utc or _utcnow()
    roots = dict(cache_dirs or DEFAULT_CACHE_DIRS)
    root_status: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    for cache_kind, cache_dir in sorted(roots.items()):
        path = repo_root / cache_dir
        exists = path.is_dir()
        root_status.append(
            {
                "cache_kind": cache_kind,
                "path": _rel(path, root=repo_root),
                "status": "present" if exists else "missing",
            }
        )
        if not exists:
            continue
        for file_path in sorted(path.glob("*.parquet")):
            files.append(
                _inspect_cache_file(
                    file_path,
                    cache_kind=cache_kind,
                    repo_root=repo_root,
                )
            )

    files.sort(key=lambda row: row["path"])
    coverage = _coverage_rows(files)
    status_counts = Counter(str(row["status"]) for row in files)
    total_rows = sum(
        int(row["row_count"]) for row in files if isinstance(row.get("row_count"), int)
    )
    manifest_hash = hashlib.sha256(
        "|".join(str(row.get("content_hash") or "") for row in files).encode("utf-8")
    ).hexdigest()
    research_ready = bool(files) and total_rows > 0 and status_counts.get("unreadable", 0) == 0

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": when,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": {
            "status": "ready" if research_ready else "not_ready",
            "research_ready": research_ready,
            "cache_file_count": len(files),
            "coverage_row_count": len(coverage),
            "total_rows": total_rows,
            "source_count": len({row["source"] for row in files}),
            "instrument_count": len({row["instrument"] for row in files}),
            "timeframe_count": len({row["timeframe"] for row in files}),
            "status_counts": dict(sorted(status_counts.items())),
            "missing_roots": sum(1 for row in root_status if row["status"] == "missing"),
            "manifest_content_hash": f"sha256:{manifest_hash}",
            "missing_manifest_fails_closed": True,
        },
        "cache_roots": root_status,
        "files": files,
        "coverage": coverage,
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError("qre_data_cache_manifest: refusing write outside allowlist: " f"{path!r}")


def write_manifest_outputs(
    manifest: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(manifest["generated_at_utc"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    payload = json.dumps(manifest, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest, root=repo_root),
        "timestamped": _rel(timestamped, root=repo_root),
        "history": _rel(history, root=repo_root),
    }


def read_manifest_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_manifest",
            "research_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_manifest",
            "research_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, dict) else None
    ready = bool(summary.get("research_ready")) if isinstance(summary, dict) else False
    return {
        "status": "ready" if ready else "not_ready",
        "research_ready": ready,
        "path": _rel(latest, root=repo_root),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packages.qre_data.cache_manifest",
        description="Build a read-only local QRE data cache manifest.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_manifest_status(), sort_keys=True, indent=2))
        return 0

    manifest = build_cache_manifest(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        manifest["_artifact_paths"] = write_manifest_outputs(manifest)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_CACHE_DIRS",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_cache_manifest",
    "read_manifest_status",
    "write_manifest_outputs",
]
