"""Artifact Health observability module.

Inspects the known input artifacts listed in
``research.observability.paths.INPUT_ARTIFACTS`` and produces a
descriptive snapshot. Read-only:

* every artifact is opened via ``read_json_safe`` (or stat-only for
  CSV / JSONL);
* writes only to ``research/observability/artifact_health_latest.v1.json``
  via ``write_sidecar_atomic``;
* never imports from runtime/decision modules — verified by the
  static import-surface test.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic

from .clock import default_now_utc, to_iso_z
from .io import read_json_safe
from .paths import (
    ARTIFACT_HEALTH_PATH,
    INPUT_ARTIFACTS,
    OBSERVABILITY_SCHEMA_VERSION,
    stale_threshold_for,
)

# Linked-id field aliases we look for in artifact payloads. Kept
# deterministic and explicit — no reflection, no heuristics beyond
# this list.
LINKED_ID_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("run_id", ("run_id",)),
    ("campaign_id", ("campaign_id",)),
    ("sprint_id", ("sprint_id",)),
    ("worker_id", ("worker_id",)),
    ("preset_id", ("preset_id", "preset", "preset_name")),
    ("hypothesis_id", ("hypothesis_id",)),
)


def _linked_ids_from_payload(payload: Any) -> dict[str, str | None]:
    """Best-effort extraction of linked IDs from a payload dict.

    Looks at the top level, ``last_attempted_run``, ``last_public_artifact_write``,
    ``run_state.artifact``, and the first element of the ``campaigns`` /
    ``events`` lists. Always returns a fully-populated dict (with None
    placeholders) so the output schema is stable.
    """
    out: dict[str, str | None] = {key: None for key, _ in LINKED_ID_KEYS}
    if not isinstance(payload, dict):
        return out

    candidates: list[dict[str, Any]] = [payload]

    for nested_key in (
        "last_attempted_run",
        "last_public_artifact_write",
    ):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            candidates.append(nested)

    run_state = payload.get("run_state")
    if isinstance(run_state, dict):
        candidates.append(run_state)
        artifact = run_state.get("artifact")
        if isinstance(artifact, dict):
            candidates.append(artifact)

    for list_key in ("campaigns", "events", "queue"):
        listed = payload.get(list_key)
        if isinstance(listed, list) and listed:
            first = listed[0]
            if isinstance(first, dict):
                candidates.append(first)

    for output_key, source_keys in LINKED_ID_KEYS:
        if out[output_key] is not None:
            continue
        for cand in candidates:
            for src_key in source_keys:
                value = cand.get(src_key)
                if isinstance(value, str) and value:
                    out[output_key] = value
                    break
            if out[output_key] is not None:
                break
    return out


def _empty_linked_ids() -> dict[str, str | None]:
    return {key: None for key, _ in LINKED_ID_KEYS}


def _classify_health(
    state: str,
    *,
    contract_class: str,
    age_seconds: float | None,
) -> tuple[bool, str | None]:
    """Return (stale, stale_reason) for an artifact.

    Pure rule: age vs threshold for the contract class. Missing /
    invalid artifacts are not stale by themselves; they are reported
    separately via ``exists`` / ``parse_ok``.
    """
    if state != "valid":
        return False, None
    if age_seconds is None:
        return False, None
    threshold = stale_threshold_for(contract_class)
    if age_seconds > threshold:
        return True, f"age_seconds={int(age_seconds)} > threshold={threshold}"
    return False, None


def _inspect_one(
    canonical_name: str,
    contract_class: str,
    path: Path,
    *,
    now_utc: datetime,
) -> dict[str, Any]:
    """Inspect a single artifact. Returns one row of the report."""
    suffix = path.suffix.lower()
    is_json = suffix in {".json"}
    is_jsonl = suffix in {".jsonl"}

    if is_json:
        result = read_json_safe(path)
        state = result.state
        size_bytes = result.size_bytes
        modified_at_unix = result.modified_at_unix
        error_message = result.error_message
        payload = result.payload
        parse_ok = state == "valid"
    else:
        # CSV / JSONL — stat-only inspection. We never parse the body
        # of a CSV (frozen contract) or load a JSONL into memory here.
        from os import stat
        try:
            st = stat(path)
            state = "valid"
            size_bytes = int(st.st_size)
            modified_at_unix = float(st.st_mtime)
            error_message = ""
            payload = None
            parse_ok = True
        except OSError as exc:
            state = "absent" if not path.exists() else "unreadable"
            size_bytes = None
            modified_at_unix = None
            error_message = "" if state == "absent" else str(exc)
            payload = None
            parse_ok = False

    age_seconds: float | None = None
    if modified_at_unix is not None:
        delta = now_utc.timestamp() - modified_at_unix
        age_seconds = max(0.0, delta)

    stale, stale_reason = _classify_health(
        state,
        contract_class=contract_class,
        age_seconds=age_seconds,
    )

    schema_version: str | None = None
    generated_at_utc: str | None = None
    if isinstance(payload, dict):
        sv = payload.get("schema_version")
        if isinstance(sv, str):
            schema_version = sv
        gen = payload.get("generated_at_utc")
        if isinstance(gen, str):
            generated_at_utc = gen

    linked_ids = (
        _linked_ids_from_payload(payload) if isinstance(payload, dict) else _empty_linked_ids()
    )

    parse_error_type: str | None = None
    parse_error_message = error_message or ""
    if state == "invalid_json":
        parse_error_type = "JSONDecodeError"
    elif state == "unreadable":
        parse_error_type = "OSError"

    empty = state == "empty" or (
        is_json and isinstance(payload, (list, dict)) and len(payload) == 0
    )

    return {
        "artifact_name": canonical_name,
        "path": str(path).replace("\\", "/"),
        "exists": state != "absent",
        "parse_ok": parse_ok,
        "schema_version": schema_version,
        "generated_at_utc": generated_at_utc,
        "modified_at_unix": modified_at_unix,
        "age_seconds": age_seconds,
        "stale": stale,
        "stale_reason": stale_reason,
        "size_bytes": size_bytes,
        "empty": empty,
        "linked_ids": linked_ids,
        "parse_error_type": parse_error_type,
        "parse_error_message": parse_error_message,
        "contract_class": contract_class,
    }


def inspect_artifact_health(
    *,
    now_utc: datetime | None = None,
    artifacts: tuple[tuple[str, str, Path], ...] | None = None,
) -> dict[str, Any]:
    """Inspect known artifacts and return a stable report payload.

    Pure function — no IO except read_json_safe / stat. Deterministic
    given (artifacts list, file contents, now_utc).
    """
    when = now_utc or default_now_utc()
    sources = artifacts if artifacts is not None else INPUT_ARTIFACTS

    rows: list[dict[str, Any]] = []
    for canonical_name, contract_class, path in sources:
        rows.append(
            _inspect_one(
                canonical_name,
                contract_class,
                path,
                now_utc=when,
            )
        )
    # Stable ordering: by canonical_name (filename). The input tuple
    # already happens to be ordered, but we sort defensively so future
    # additions don't change byte-output for unrelated entries.
    rows.sort(key=lambda r: r["artifact_name"])

    summary = {
        "total": len(rows),
        "missing": sum(1 for r in rows if not r["exists"]),
        "corrupt": sum(1 for r in rows if r["exists"] and not r["parse_ok"]),
        "stale": sum(1 for r in rows if r["stale"]),
        "fresh": sum(
            1 for r in rows if r["exists"] and r["parse_ok"] and not r["stale"]
        ),
        "empty": sum(1 for r in rows if r["empty"]),
        "by_contract_class": _counts_by(rows, "contract_class"),
    }

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "summary": summary,
        "artifacts": rows,
    }


def _counts_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if not isinstance(v, str):
            continue
        out[v] = out.get(v, 0) + 1
    # Stable ordering: sorted by key.
    return dict(sorted(out.items()))


def write_artifact_health(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    """Persist the artifact-health snapshot. Refuses to write outside
    ``research/observability/`` (defense-in-depth).

    ``path=None`` resolves to the module-level ``ARTIFACT_HEALTH_PATH``
    AT CALL TIME, not at function definition time, so tests can
    monkeypatch the constant.
    """
    target = path if path is not None else ARTIFACT_HEALTH_PATH
    if "observability" not in str(target).replace("\\", "/").split("/"):
        raise RuntimeError(
            "write_artifact_health refuses to write outside research/observability/"
        )
    write_sidecar_atomic(target, payload)


__all__ = [
    "inspect_artifact_health",
    "write_artifact_health",
]
