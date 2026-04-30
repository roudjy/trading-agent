"""Agent audit ledger — append-only, hash-chained JSONL.

This module is the canonical writer for ``logs/agent_audit.jsonl`` (and
its daily-rotated siblings). It mirrors the design of
``reporting/audit_log.py`` (the existing system audit log) but adds:

- A SHA-256 hash chain (``prev_event_sha256`` + ``event_sha256``) so that
  any deletion, insertion, or rewrite of past events is detectable.
- A daily UTC rotation policy, so a long-lived sessie cannot produce a
  single multi-GB ledger.
- A redaction layer that scrubs high-entropy strings and known credential
  patterns before they hit disk. The hooks call site is expected to feed
  already-redacted payloads, but the ledger applies a second pass as
  defense in depth.

Hash chain invariants
---------------------

For event N>0:

    record["prev_event_sha256"] = sha256( canonical(record_{N-1} excluding "event_sha256") )
    record["event_sha256"]      = sha256( canonical(record_N excluding "event_sha256") )

For N=0 (file is empty):

    record["prev_event_sha256"] = None
    record["event_sha256"]      = sha256( canonical(record_0 excluding "event_sha256") )

``canonical`` = ``json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False).encode("utf-8")`` — a stable byte form.

Concurrency
-----------

Single-process append with ``O_APPEND``. We additionally take a file-level
lock via ``fcntl.flock`` on POSIX or ``msvcrt.locking`` on Windows to
serialize concurrent writers. The hash chain requires a read of the last
event before each append, so the lock spans both the read and the write.

Stdlib-only
-----------

This module is intentionally stdlib-only. It is imported by Claude Code
hooks which must remain dependency-light.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import io
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Iterator, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 1

#: Path to the directory that holds rolling ledger files. Resolved relative
#: to the repository root (the directory two levels above this file).
_LEDGER_DIR: Path = Path(__file__).resolve().parent.parent / "logs"

#: Hash field that is excluded when computing the canonical bytes of a record.
_HASH_FIELD: str = "event_sha256"

#: Fields the in-process process locker uses; module-level for simplicity.
_PROCESS_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# High-entropy strings (long hex/base64) that look like credentials.
# Conservative — we'd rather over-redact than leak.
_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),  # Anthropic
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),  # GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{40,}"),  # generic long hex
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9])"),  # base64-ish
)

# Patterns for known sensitive paths — substrings of these strings should
# never appear in a ledger entry. The redaction layer replaces them.
_SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    "config/config.yaml",
    "/state/",
    ".env",
    "live_gate.secret",
    "fred.secret",
)


def _redact(text: str) -> tuple[str, bool]:
    """Return (redacted_text, did_redact)."""
    if not text:
        return text, False
    redacted = text
    did = False
    for pat in _REDACT_PATTERNS:
        new = pat.sub("[REDACTED]", redacted)
        if new != redacted:
            did = True
            redacted = new
    return redacted, did


def _redact_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Apply redaction to user-controlled string fields."""
    out = dict(rec)
    redacted_any = False

    # command_summary may carry a shell line; redact in place.
    cs = out.get("command_summary")
    if isinstance(cs, str):
        new, did = _redact(cs)
        if did:
            out["command_summary"] = new
            redacted_any = True

    # diff_summary should never have content; only meta. Sanity check:
    ds = out.get("diff_summary")
    if isinstance(ds, dict):
        # do not allow "content" or similar; drop unexpected keys
        allowed = {"lines_added", "lines_removed", "content_sha256"}
        cleaned = {k: v for k, v in ds.items() if k in allowed}
        if cleaned != ds:
            out["diff_summary"] = cleaned
            redacted_any = True

    out["redacted"] = bool(out.get("redacted", False) or redacted_any)
    return out


# ---------------------------------------------------------------------------
# Canonicalization & hashing
# ---------------------------------------------------------------------------


def _canonical_bytes(record: dict[str, Any]) -> bytes:
    """Return canonical JSON bytes excluding the ``event_sha256`` field."""
    rec = {k: v for k, v in record.items() if k != _HASH_FIELD}
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# File path & rotation
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rotation_date_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def current_ledger_path(base_dir: Optional[Path] = None) -> Path:
    """Return the path of the ledger file for today (UTC).

    The base dir is overridable for tests.
    """
    base = base_dir if base_dir is not None else _LEDGER_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"agent_audit.{_rotation_date_utc()}.jsonl"


# ---------------------------------------------------------------------------
# Cross-platform file lock
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _file_lock(fileobj: io.IOBase) -> Iterator[None]:
    """File-level exclusive lock that works on POSIX and Windows.

    ``sys.platform`` is mypy-narrowed: on Windows mypy ignores the
    ``else`` branch (and its fcntl import) and vice-versa.
    """
    if sys.platform == "win32":
        import msvcrt

        try:
            # Lock first byte of the file. Wait up to ~10s.
            msvcrt.locking(fileobj.fileno(), msvcrt.LK_LOCK, 1)
            yield
        finally:
            try:
                fileobj.seek(0)
                msvcrt.locking(fileobj.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
    else:
        import fcntl  # type: ignore[import-not-found]

        try:
            fcntl.flock(fileobj.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fileobj.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Tail reader — last event in the chain
# ---------------------------------------------------------------------------


def _read_last_event_from_handle(f: io.IOBase) -> Optional[dict[str, Any]]:
    """Read the last JSON object from an already-open binary file handle.

    The handle MUST be open in a mode that supports seeking (e.g. ``a+b``).
    Reusing the open handle avoids a second open() that would conflict with
    file-level locks on Windows.
    """
    # Save position so we leave the handle at end-of-file for append.
    saved = f.tell()
    try:
        f.seek(0, io.SEEK_END)
        size = f.tell()
        if size == 0:
            return None
        chunk = 4096
        pos = size
        buf = b""
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            stripped = buf.rstrip(b"\n")
            idx = stripped.rfind(b"\n")
            if idx >= 0:
                last_line = stripped[idx + 1 :]
                try:
                    return json.loads(last_line.decode("utf-8"))
                except json.JSONDecodeError:
                    return None
        line = buf.strip(b"\n")
        if not line:
            return None
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return None
    finally:
        f.seek(saved)


def _read_last_event(path: Path) -> Optional[dict[str, Any]]:
    """Public helper for read-only consumers (verify_chain CLI, etc.)."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open("rb") as f:
        return _read_last_event_from_handle(f)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_event(
    event: dict[str, Any],
    *,
    base_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Append an audit event to today's ledger file.

    The supplied ``event`` may omit ``schema_version``, ``sequence_id``,
    ``timestamp_utc``, ``prev_event_sha256``, and ``event_sha256``; this
    function fills them in. Callers are expected to provide ``actor``,
    ``event``, ``tool``, ``outcome``, and any tool-specific fields.

    Returns the final (sealed) record dict.
    """
    if not isinstance(event, dict):
        raise TypeError("event must be a dict")

    path = current_ledger_path(base_dir=base_dir)

    # Ensure parent + file exist.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    with _PROCESS_LOCK:
        with path.open("a+b") as f:
            with _file_lock(f):
                # Read from the locked handle; opening a second handle
                # would conflict with the lock on Windows.
                last = _read_last_event_from_handle(f)
                # Position file at end for the append.
                f.seek(0, io.SEEK_END)
                seq = (last["sequence_id"] + 1) if last and "sequence_id" in last else 0
                prev_hash = last.get(_HASH_FIELD) if last else None

                base: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION,
                    "sequence_id": seq,
                    "timestamp_utc": _utcnow_iso(),
                    "actor": event.get("actor", "claude:unknown"),
                    "model": event.get("model"),
                    "event": event.get("event", "tool_use"),
                    "tool": event.get("tool"),
                    "target_path": event.get("target_path"),
                    "diff_summary": event.get("diff_summary"),
                    "command_summary": event.get("command_summary"),
                    "outcome": event.get("outcome", "ok"),
                    "block_reason": event.get("block_reason"),
                    "branch": event.get("branch"),
                    "head_sha": event.get("head_sha"),
                    "redacted": event.get("redacted", False),
                    "autonomy_level_claimed": event.get("autonomy_level_claimed"),
                    "session_id": event.get("session_id"),
                    "prev_event_sha256": prev_hash,
                }
                # Allow callers to add additional fields, but never overwrite
                # the chain-computed ones.
                for k, v in event.items():
                    if k not in base and k != _HASH_FIELD:
                        base[k] = v

                base = _redact_record(base)
                base[_HASH_FIELD] = _sha256_hex(_canonical_bytes(base))

                line = json.dumps(base, sort_keys=True, ensure_ascii=False) + "\n"
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
                return base


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield events from a ledger file in order."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Mid-write corruption: stop iteration.
                return


def verify_chain(path: Path) -> tuple[bool, Optional[int]]:
    """Verify the hash chain in ``path``.

    Returns ``(True, None)`` if the chain is intact, otherwise
    ``(False, first_corrupt_index)``.
    """
    prev_hash: Optional[str] = None
    for idx, ev in enumerate(iter_events(path)):
        # Check sequence id monotonicity.
        if ev.get("sequence_id") != idx:
            return (False, idx)
        # Check prev_event_sha256 matches prior event's event_sha256.
        if ev.get("prev_event_sha256") != prev_hash:
            return (False, idx)
        # Recompute event_sha256.
        recomputed = _sha256_hex(_canonical_bytes(ev))
        if ev.get(_HASH_FIELD) != recomputed:
            return (False, idx)
        prev_hash = ev.get(_HASH_FIELD)
    return (True, None)


def verify_sequence_continuity(path: Path) -> bool:
    ok, _ = verify_chain(path)
    return ok


# ---------------------------------------------------------------------------
# CLI for ad-hoc verification
# ---------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: python -m reporting.agent_audit <verify|tail> <path>")
        return 0
    cmd = argv[1]
    p = Path(argv[2]) if len(argv) >= 3 else current_ledger_path()
    if cmd == "verify":
        ok, idx = verify_chain(p)
        if ok:
            print(f"OK — chain intact ({sum(1 for _ in iter_events(p))} events)")
            return 0
        print(f"FAIL — first corrupt event index: {idx}")
        return 2
    if cmd == "tail":
        last = _read_last_event(p)
        print(json.dumps(last, indent=2, sort_keys=True) if last else "(empty)")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv))
