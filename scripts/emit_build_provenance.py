#!/usr/bin/env python3
"""Emit a build_provenance JSON record and validate it against the schema.

Usage (called from .github/workflows/docker-build.yml):

    python scripts/emit_build_provenance.py \
        --commit <sha> \
        --image-digest <sha256:...> \
        --workflow-run-id <id> \
        --workflow-run-attempt <int> \
        --version <semver> \
        --actor <gh handle> \
        --actions-pinned true \
        --output artifacts/build_provenance-<version>.json

The script is intentionally stdlib-only (no jsonschema dependency in CI).
It performs a minimal in-process validation against the schema's
required keys and patterns; the schema file itself is the source of truth
and is checked into Git.

Exit codes:
    0 — provenance written and validated.
    2 — argument or pattern validation failed.
    3 — schema file missing or unreadable.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "artifacts" / "build_provenance.schema.json"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Emit build_provenance JSON.")
    p.add_argument("--commit", required=True)
    p.add_argument("--image-digest", required=True)
    p.add_argument("--image-digest-dashboard", default=None)
    p.add_argument("--workflow-run-id", required=True)
    p.add_argument("--workflow-run-attempt", required=True, type=int)
    p.add_argument("--version", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument(
        "--actions-pinned",
        required=True,
        type=lambda s: s.lower() in ("1", "true", "yes"),
    )
    p.add_argument("--output", required=True)
    return p.parse_args()


def _validate(record: dict, schema: dict) -> list[str]:
    """Minimal validation: required keys, types, regex patterns."""
    problems: list[str] = []
    required = schema.get("required", [])
    props = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)

    for k in required:
        if k not in record:
            problems.append(f"missing required field: {k}")

    if additional is False:
        for k in record:
            if k not in props:
                problems.append(f"unexpected field: {k}")

    if not _SHA_RE.fullmatch(record.get("commit", "")):
        problems.append("commit must match ^[0-9a-f]{40}$")
    if not _DIGEST_RE.fullmatch(record.get("image_digest", "")):
        problems.append("image_digest must match ^sha256:[0-9a-f]{64}$")
    if record.get("image_digest_dashboard") and not _DIGEST_RE.fullmatch(
        record["image_digest_dashboard"]
    ):
        problems.append("image_digest_dashboard must match ^sha256:[0-9a-f]{64}$")
    if record.get("schema_version") != 1:
        problems.append("schema_version must equal 1")
    if not isinstance(record.get("workflow_run_attempt"), int):
        problems.append("workflow_run_attempt must be int")

    return problems


def main() -> int:
    args = _parse_args()
    if not SCHEMA_PATH.is_file():
        print(f"schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 3

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    record = {
        "schema_version": 1,
        "commit": args.commit,
        "image_digest": args.image_digest,
        "image_digest_dashboard": args.image_digest_dashboard or None,
        "workflow_run_id": str(args.workflow_run_id),
        "workflow_run_attempt": int(args.workflow_run_attempt),
        "version": args.version,
        "built_at_utc": _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "actor": args.actor,
        "actions_pinned": bool(args.actions_pinned),
    }
    if record["image_digest_dashboard"] is None:
        del record["image_digest_dashboard"]

    problems = _validate(record, schema)
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"provenance written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
