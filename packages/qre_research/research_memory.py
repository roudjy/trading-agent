"""Deterministic read-only research memory over local artifacts."""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from packages.qre_artifacts.public_outputs import CSV_PATH, JSON_PATH

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_memory_v1"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_memory")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/qre_research_memory/"
DEFAULT_ARTIFACT_PATHS: Final[tuple[Path, ...]] = (
    Path(JSON_PATH),
    Path(CSV_PATH),
    Path("docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md"),
    Path("logs/qre_data_cache_manifest/latest.json"),
    Path("logs/qre_data_source_quality_readiness/latest.json"),
    Path("logs/qre_hypothesis_disposition_memory/latest.json"),
    Path("logs/qre_research_cycle_router/latest.json"),
    Path("logs/qre_evidence_breadth_framework/latest.json"),
    Path("logs/qre_research_memory_retrieval/latest.json"),
    Path("logs/qre_null_control_falsification_suite/latest.json"),
    Path("logs/qre_candidate_identity_lifecycle/latest.json"),
)
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9_./:-]+")
_PREVIEW_LIMIT: Final[int] = 280


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _tokenize(value: Any) -> list[str]:
    return _TOKEN_RE.findall(str(value).lower())


def _content_hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _flatten(value: Any) -> str:
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            parts.append(str(key))
            parts.append(_flatten(item))
        return " ".join(part for part in parts if part)
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _is_success(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _is_failure(value: Any) -> bool:
    return value is False or str(value).strip().lower() == "false"


def _has_error(value: Any) -> bool:
    return value is not None and str(value).strip().lower() not in {"", "none", "null"}


def _ontology_tags(text: str, metadata: Mapping[str, Any]) -> list[str]:
    haystack = f"{text} {_flatten(metadata)}".lower()
    tags: set[str] = set()
    if any(term in haystack for term in ("hypothesis", "hypothese", "doel")):
        tags.add("hypothesis")
    success = metadata.get("success")
    error = metadata.get("error")
    if (
        _is_failure(success)
        or _has_error(error)
        or (
            not _is_success(success)
            and any(term in haystack for term in ("failure", "failed", "unknown_"))
        )
    ):
        tags.add("failure")
    if any(term in haystack for term in ("campaign", "queue item", "queue id")):
        tags.add("campaign")
    if any(term in haystack for term in ("policy", "governance", "authority")):
        tags.add("policy")
    if any(term in haystack for term in ("action", "recommendation", "ready")):
        tags.add("policy_action")
    if any(term in haystack for term in ("source", "manifest", "data quality")):
        tags.add("data_readiness")
    if "strategy" in haystack:
        tags.add("strategy_context")
    return sorted(tags)


def _entry(
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_type: str,
    record_kind: str,
    title: str,
    text: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    clean_text = " ".join(text.split())
    keywords = sorted(set(_tokenize(f"{title} {clean_text} {_flatten(metadata)}")))
    tags = _ontology_tags(clean_text, metadata)
    return {
        "artifact_id": artifact_id,
        "artifact_path": artifact_path,
        "artifact_type": artifact_type,
        "record_kind": record_kind,
        "title": title,
        "ontology_tags": tags,
        "keywords": keywords,
        "metadata": dict(sorted(metadata.items())),
        "content_hash": _content_hash(clean_text),
        "text_preview": clean_text[:_PREVIEW_LIMIT],
    }


def _entries_from_research_latest(
    payload: Mapping[str, Any],
    *,
    artifact_path: str,
) -> list[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    entries: list[dict[str, Any]] = []
    for index, row in enumerate(results):
        if not isinstance(row, Mapping):
            continue
        strategy = str(row.get("strategy_name") or "unknown_strategy")
        hypothesis = str(row.get("hypothesis") or "")
        asset = str(row.get("asset") or "")
        interval = str(row.get("interval") or "")
        success = bool(row.get("success"))
        title = " ".join(part for part in (strategy, asset, interval) if part)
        text = _flatten(row)
        metadata = {
            "strategy_name": strategy,
            "hypothesis": hypothesis,
            "asset": asset,
            "interval": interval,
            "success": success,
            "error": row.get("error"),
            "source": "research_latest",
        }
        entries.append(
            _entry(
                artifact_id=f"{artifact_path}#results[{index}]",
                artifact_path=artifact_path,
                artifact_type="json",
                record_kind="research_result",
                title=title,
                text=text,
                metadata=metadata,
            )
        )
    return entries


def _entries_from_json(path: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    rel_path = _rel(path, root=repo_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, Mapping) and rel_path == JSON_PATH:
        entries = _entries_from_research_latest(payload, artifact_path=rel_path)
        if entries:
            return entries
    text = _flatten(payload)
    metadata = {
        "source": "json_artifact",
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
        "report_kind": payload.get("report_kind") if isinstance(payload, Mapping) else None,
    }
    return [
        _entry(
            artifact_id=rel_path,
            artifact_path=rel_path,
            artifact_type="json",
            record_kind="artifact",
            title=rel_path,
            text=text,
            metadata=metadata,
        )
    ]


def _entries_from_csv(path: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    rel_path = _rel(path, root=repo_root)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        title = " ".join(
            str(row.get(key) or "")
            for key in ("strategy_name", "asset", "interval")
            if row.get(key)
        )
        metadata = {
            "strategy_name": row.get("strategy_name"),
            "hypothesis": row.get("hypothesis"),
            "asset": row.get("asset"),
            "interval": row.get("interval"),
            "success": row.get("success"),
            "error": row.get("error"),
            "source": "strategy_matrix",
        }
        entries.append(
            _entry(
                artifact_id=f"{rel_path}#row[{index}]",
                artifact_path=rel_path,
                artifact_type="csv",
                record_kind="research_result",
                title=title or f"{rel_path} row {index}",
                text=_flatten(row),
                metadata=metadata,
            )
        )
    return entries


def _entries_from_text(path: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    rel_path = _rel(path, root=repo_root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    title = rel_path
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip() or rel_path
            break
    return [
        _entry(
            artifact_id=rel_path,
            artifact_path=rel_path,
            artifact_type=path.suffix.lstrip(".") or "text",
            record_kind="artifact",
            title=title,
            text=text,
            metadata={"source": "text_artifact"},
        )
    ]


def _load_artifact_entries(path: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _entries_from_json(path, repo_root=repo_root)
    if suffix == ".csv":
        return _entries_from_csv(path, repo_root=repo_root)
    if suffix in {".md", ".txt"}:
        return _entries_from_text(path, repo_root=repo_root)
    return []


def _resolve_artifact_paths(
    artifact_paths: Iterable[Path] | None,
    *,
    repo_root: Path,
) -> tuple[list[Path], list[str]]:
    paths = [Path(path) for path in (artifact_paths or DEFAULT_ARTIFACT_PATHS)]
    existing: list[Path] = []
    missing: list[str] = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        full_path = repo_root / path
        if full_path.is_file():
            existing.append(full_path)
        else:
            missing.append(_rel(full_path, root=repo_root))
    return existing, missing


def retrieve(memory: Mapping[str, Any], query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []
    matches: list[dict[str, Any]] = []
    for entry in memory.get("entries", []):
        if not isinstance(entry, Mapping):
            continue
        keywords = {str(keyword) for keyword in entry.get("keywords", [])}
        tags = {str(tag) for tag in entry.get("ontology_tags", [])}
        text_tokens = set(_tokenize(entry.get("text_preview", "")))
        score = (
            3 * len(query_tokens & tags)
            + 2 * len(query_tokens & keywords)
            + len(query_tokens & text_tokens)
        )
        if score <= 0:
            continue
        matches.append(
            {
                "artifact_id": entry["artifact_id"],
                "artifact_path": entry["artifact_path"],
                "record_kind": entry["record_kind"],
                "title": entry["title"],
                "ontology_tags": entry["ontology_tags"],
                "score": score,
                "text_preview": entry["text_preview"],
            }
        )
    matches.sort(key=lambda row: (-int(row["score"]), str(row["artifact_id"])))
    return matches[:limit]


def find_related_failures(
    memory: Mapping[str, Any],
    failure_query: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    candidates = retrieve(memory, failure_query, limit=max(limit * 4, limit))
    failures = [
        row
        for row in candidates
        if "failure" in row.get("ontology_tags", [])
        or "error" in _tokenize(row.get("text_preview", ""))
    ]
    return failures[:limit]


def build_research_memory(
    *,
    artifact_paths: Iterable[Path] | None = None,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    query: str | None = None,
    related_failure: str | None = None,
) -> dict[str, Any]:
    when = generated_at_utc or _utcnow()
    existing, missing = _resolve_artifact_paths(artifact_paths, repo_root=repo_root)
    entries: list[dict[str, Any]] = []
    for path in existing:
        entries.extend(_load_artifact_entries(path, repo_root=repo_root))
    entries.sort(key=lambda row: str(row["artifact_id"]))

    tag_counts = Counter(tag for row in entries for tag in row["ontology_tags"])
    kind_counts = Counter(str(row["record_kind"]) for row in entries)
    artifact_hash = hashlib.sha256(
        "|".join(str(row["content_hash"]) for row in entries).encode("utf-8")
    ).hexdigest()
    memory: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": when,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": {
            "status": "ready" if entries else "not_ready",
            "research_memory_ready": bool(entries),
            "fail_closed": not bool(entries),
            "artifact_count": len(existing),
            "entry_count": len(entries),
            "missing_artifact_count": len(missing),
            "record_kind_counts": dict(sorted(kind_counts.items())),
            "ontology_tag_counts": dict(sorted(tag_counts.items())),
            "memory_content_hash": f"sha256:{artifact_hash}",
        },
        "artifact_paths": [_rel(path, root=repo_root) for path in existing],
        "missing_artifacts": missing,
        "entries": entries,
        "retrieval": {
            "query": query,
            "matches": [],
        },
        "related_failures": {
            "query": related_failure,
            "matches": [],
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_embeddings": False,
            "uses_llm_authority": False,
            "uses_network": False,
            "uses_subprocess": False,
            "mutates_campaigns": False,
            "mutates_research_outputs": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    if query:
        memory["retrieval"]["matches"] = retrieve(memory, query)
    if related_failure:
        memory["related_failures"]["matches"] = find_related_failures(memory, related_failure)
    return memory


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(f"qre_research_memory: refusing write outside allowlist: {path!r}")


def write_research_memory_outputs(
    memory: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(memory["generated_at_utc"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    payload = json.dumps(memory, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(memory, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest, root=repo_root),
        "timestamped": _rel(timestamped, root=repo_root),
        "history": _rel(history, root=repo_root),
    }


def read_research_memory_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_research_memory",
            "research_memory_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_research_memory",
            "research_memory_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, dict) else None
    ready = bool(summary.get("research_memory_ready")) if isinstance(summary, dict) else False
    return {
        "status": "ready" if ready else "not_ready",
        "research_memory_ready": ready,
        "path": _rel(latest, root=repo_root),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packages.qre_research.research_memory",
        description="Build a deterministic read-only research memory over local artifacts.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--related-failure", type=str, default=None)
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_research_memory_status(), sort_keys=True, indent=2))
        return 0

    memory = build_research_memory(
        generated_at_utc=args.frozen_utc,
        query=args.query,
        related_failure=args.related_failure,
    )
    if not args.no_write:
        memory["_artifact_paths"] = write_research_memory_outputs(memory)
    print(json.dumps(memory, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_ARTIFACT_PATHS",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_research_memory",
    "find_related_failures",
    "read_research_memory_status",
    "retrieve",
    "write_research_memory_outputs",
]
