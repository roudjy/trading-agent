"""Passive read helpers for observability.

All artifact reads in ``research.observability`` go through these
functions. They:

* never raise: any IO/parse error is reported in the returned tuple;
* never mutate: open in read-only mode, no truncation, no tmp files
  on the read path;
* never trigger lazy fetches or recompute: pure ``Path`` + ``json``;
* are bounded: JSONL tail-reader caps both line count and bytes;
* defensively skip trailing partial lines that may be in flight from a
  concurrent appender.

Every aggregation module returns ``state`` and ``error_message`` to
the caller so observability output can mark the artifact as
``unavailable`` / ``invalid_json`` / ``empty`` rather than crashing
the build.

Imports: stdlib only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ReadState = Literal[
    "valid",
    "absent",
    "empty",
    "invalid_json",
    "unreadable",
]


@dataclass(frozen=True)
class JsonReadResult:
    """Outcome of a passive JSON read.

    ``payload`` is None unless ``state == "valid"``. ``error_message``
    is an empty string unless ``state in {"invalid_json", "unreadable"}``.
    """

    state: ReadState
    payload: Any | None
    error_message: str
    size_bytes: int | None
    modified_at_unix: float | None


@dataclass(frozen=True)
class JsonlTailResult:
    """Outcome of a bounded JSONL tail read.

    * ``lines_consumed`` — how many lines we successfully parsed.
    * ``parse_errors`` — count of lines that failed JSON parsing
      (not raised; just counted).
    * ``truncated`` — True when the bound was hit before reaching the
      head of the file (output is "within last N events").
    * ``partial_trailing_line_dropped`` — True when the very last line
      lacked a trailing newline; we drop it as a likely in-flight write
      from a concurrent appender.
    """

    state: ReadState
    events: list[dict[str, Any]]
    lines_consumed: int
    parse_errors: int
    truncated: bool
    partial_trailing_line_dropped: bool
    error_message: str
    size_bytes: int | None
    modified_at_unix: float | None


def _stat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def read_json_safe(path: Path) -> JsonReadResult:
    """Read a JSON artifact passively. Never raises.

    State transitions:

    * file missing       → ``absent``
    * file unreadable    → ``unreadable`` with error_message
    * file empty/whitespace → ``empty``
    * malformed JSON     → ``invalid_json`` with error_message
    * otherwise          → ``valid`` with payload populated
    """
    st = _stat_or_none(path)
    if st is None:
        return JsonReadResult(
            state="absent",
            payload=None,
            error_message="",
            size_bytes=None,
            modified_at_unix=None,
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return JsonReadResult(
            state="unreadable",
            payload=None,
            error_message=str(exc),
            size_bytes=int(st.st_size),
            modified_at_unix=float(st.st_mtime),
        )
    if raw.strip() == "":
        return JsonReadResult(
            state="empty",
            payload=None,
            error_message="",
            size_bytes=int(st.st_size),
            modified_at_unix=float(st.st_mtime),
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return JsonReadResult(
            state="invalid_json",
            payload=None,
            error_message=str(exc),
            size_bytes=int(st.st_size),
            modified_at_unix=float(st.st_mtime),
        )
    return JsonReadResult(
        state="valid",
        payload=payload,
        error_message="",
        size_bytes=int(st.st_size),
        modified_at_unix=float(st.st_mtime),
    )


def _tail_lines_bounded(
    path: Path,
    *,
    max_lines: int,
    max_tail_bytes: int,
) -> tuple[list[bytes], bool, bool]:
    """Read up to ``max_lines`` trailing lines, capped at ``max_tail_bytes``.

    Returns (lines_in_chronological_order, truncated, partial_trailing).

    Reads the file in fixed chunks from the end, walking backwards
    until the line count is satisfied or the byte budget is exhausted.
    Does NOT load the whole file into memory.

    The trailing partial line (no terminating ``\n``) is dropped to
    defend against in-flight writes from a concurrent appender; this
    is reported via ``partial_trailing``.
    """
    chunk_size = 65536
    file_size: int
    try:
        file_size = path.stat().st_size
    except OSError:
        return [], False, False

    if file_size == 0:
        return [], False, False

    consumed = bytearray()
    pos = file_size
    truncated = False
    bytes_budget = max_tail_bytes

    with path.open("rb") as fh:
        while pos > 0 and bytes_budget > 0:
            read_size = min(chunk_size, pos, bytes_budget)
            pos -= read_size
            bytes_budget -= read_size
            fh.seek(pos)
            consumed[0:0] = fh.read(read_size)  # prepend
            # Count line breaks in what we have so far. Stop when we
            # exceed max_lines + 1 (the "+1" leaves one whole boundary
            # line we can safely discard at the front).
            if consumed.count(b"\n") > max_lines:
                truncated = True
                break

    lines = consumed.split(b"\n")

    # If we did NOT reach the head AND the very first segment may be a
    # partial fragment of an earlier line, drop it.
    if pos > 0 and lines:
        lines = lines[1:]
        truncated = True

    # Detect a trailing partial line. A complete file ends with b"\n",
    # so split() yields an empty final element. If the final element
    # is non-empty, the last line was in flight (no newline yet) — drop
    # it for safety against concurrent appenders.
    partial_trailing = bool(lines) and lines[-1] != b""
    if partial_trailing:
        lines = lines[:-1]
    elif lines and lines[-1] == b"":
        lines = lines[:-1]

    # Cap to max_lines (in case the heuristic above kept slightly more).
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True

    return lines, truncated, partial_trailing


def read_jsonl_tail_safe(
    path: Path,
    *,
    max_lines: int,
    max_tail_bytes: int,
) -> JsonlTailResult:
    """Read the tail of a JSONL artifact passively. Never raises.

    Bounded: at most ``max_lines`` are returned, sourced from at most
    ``max_tail_bytes`` of trailing file content. Malformed lines are
    skipped and counted in ``parse_errors`` rather than raised.

    A trailing partial line (likely an in-flight append from a
    concurrent writer) is dropped and flagged via
    ``partial_trailing_line_dropped``.
    """
    st = _stat_or_none(path)
    if st is None:
        return JsonlTailResult(
            state="absent",
            events=[],
            lines_consumed=0,
            parse_errors=0,
            truncated=False,
            partial_trailing_line_dropped=False,
            error_message="",
            size_bytes=None,
            modified_at_unix=None,
        )

    try:
        raw_lines, truncated, partial_trailing = _tail_lines_bounded(
            path,
            max_lines=max_lines,
            max_tail_bytes=max_tail_bytes,
        )
    except OSError as exc:
        return JsonlTailResult(
            state="unreadable",
            events=[],
            lines_consumed=0,
            parse_errors=0,
            truncated=False,
            partial_trailing_line_dropped=False,
            error_message=str(exc),
            size_bytes=int(st.st_size),
            modified_at_unix=float(st.st_mtime),
        )

    events: list[dict[str, Any]] = []
    parse_errors = 0
    for line_bytes in raw_lines:
        if not line_bytes.strip():
            continue
        try:
            obj = json.loads(line_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            parse_errors += 1
            continue
        if isinstance(obj, dict):
            events.append(obj)
        else:
            parse_errors += 1

    if not events and not raw_lines:
        return JsonlTailResult(
            state="empty",
            events=[],
            lines_consumed=0,
            parse_errors=0,
            truncated=truncated,
            partial_trailing_line_dropped=partial_trailing,
            error_message="",
            size_bytes=int(st.st_size),
            modified_at_unix=float(st.st_mtime),
        )

    return JsonlTailResult(
        state="valid",
        events=events,
        lines_consumed=len(events),
        parse_errors=parse_errors,
        truncated=truncated,
        partial_trailing_line_dropped=partial_trailing,
        error_message="",
        size_bytes=int(st.st_size),
        modified_at_unix=float(st.st_mtime),
    )


__all__ = [
    "JsonReadResult",
    "JsonlTailResult",
    "ReadState",
    "read_json_safe",
    "read_jsonl_tail_safe",
]
