"""Canonical sidecar IO helper for v3.12 artifacts.

All v3.12 sidecars (candidate_registry_v2, candidate_status_history,
agent_definitions) write through this helper so that identical input
produces byte-identical output regardless of dict insertion order,
platform, or Python version.

Serialization contract:
- sort_keys=True           : deterministic key ordering
- ensure_ascii=False       : preserve unicode characters verbatim
- indent=2                 : human-readable, stable formatting
- separators=(",", ": ")   : stable separator whitespace
- LF line endings          : cross-platform byte-reproducibility
- trailing newline         : POSIX text file convention

Atomicity contract:
- write to tempfile, then os.replace() to target path
- replace is atomic on POSIX; best-effort on Windows (still much
  safer than direct overwrite against crash/concurrent-reader races)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CANONICAL_JSON_KWARGS: dict[str, Any] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "indent": 2,
    "separators": (",", ": "),
}


class SchemaContractError(RuntimeError):
    """Raised when a payload lacks or mismatches its required schema_version."""


def serialize_canonical(payload: dict) -> str:
    """Return the canonical string form of ``payload``.

    Pure function — no IO. Exposed so tests and callers can compute
    byte-for-byte equality without touching disk.
    """
    return json.dumps(payload, **CANONICAL_JSON_KWARGS) + "\n"


def write_sidecar_atomic(path: Path, payload: dict) -> None:
    """Deterministic canonical JSON write with atomic rename.

    Writes to ``<path>.tmp`` then renames onto the target. Crash
    during write leaves the previous sidecar untouched; a successful
    call always produces a complete, well-formed file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = serialize_canonical(payload)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialized, encoding="utf-8", newline="\n")
    tmp.replace(path)


def require_schema_version(payload: dict, expected: str) -> None:
    """Validate that ``payload`` carries the expected schema_version.

    Raises SchemaContractError if the field is missing or mismatched.
    Kept separate from write_sidecar_atomic so callers can validate
    payloads assembled in memory before committing to disk.
    """
    actual = payload.get("schema_version")
    if actual != expected:
        raise SchemaContractError(
            f"schema_version mismatch: expected {expected!r}, got {actual!r}"
        )
