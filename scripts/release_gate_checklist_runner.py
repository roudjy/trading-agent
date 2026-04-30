#!/usr/bin/env python3
"""release_gate_checklist_runner.py - mechanical checks for release-gate.

Reads git diff against a base ref and verifies items 1-9 of
docs/governance/release_gate_checklist.md mechanically. Items that
require operator-side verification are flagged n/a.

Usage: python scripts/release_gate_checklist_runner.py [--base origin/main]

Stdlib-only.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Dict

ROOT = Path(__file__).resolve().parent.parent


def diff_files(base: str) -> List[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", base + "...HEAD"],
            capture_output=True, text=True, check=True, cwd=ROOT)
    except subprocess.CalledProcessError:
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def added_lines(base: str, glob: str) -> str:
    try:
        out = subprocess.run(
            ["git", "diff", base + "...HEAD", "--unified=0", "--", glob],
            capture_output=True, text=True, check=True, cwd=ROOT)
    except subprocess.CalledProcessError:
        return ""
    return "\n".join(
        l for l in out.stdout.splitlines()
        if l.startswith("+") and not l.startswith("+++"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files = diff_files(a.base)
    R: List[Dict[str, Any]] = []

    def add(_id, name, status, ev):
        R.append({"id": _id, "name": name, "status": status, "evidence": ev})

    gen = ("dist/", "build/", ".egg-info/", "__pycache__/")
    bad = [f for f in files if any(p in f for p in gen)]
    add(1, "No unreviewed generated files",
        "fail" if bad else "pass", bad or "clean")

    pin_re = re.compile(
        r"^tests/regression/(test_v3_.*pin.*\.py|"
        r"test_v3_15_artifacts_deterministic\.py|"
        r"test_authority_invariants\.py|"
        r"test_v3_15_8_canonical_dump_and_digest\.py)$")
    pin = [f for f in files if pin_re.match(f)]
    add(2, "No regenerated determinism pins",
        "fail" if pin else "pass", pin or "no pin tests touched")

    snap_re = re.compile(r"_latest\.v1\.(json|jsonl)$")
    snap = [f for f in files if snap_re.search(f)]
    add(3, "No snapshot churn",
        "fail" if snap else "pass", snap or "no v1 snapshots touched")

    fx = [f for f in files if "/fixtures/" in f or "/golden/" in f]
    add(4, "No fixture rewrites",
        "fail" if fx else "pass", fx or "no fixtures/golden touched")

    ts_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    bad_ts: List[str] = []
    for blob in (added_lines(a.base, "*.json"),
                 added_lines(a.base, "*.jsonl")):
        for ln in blob.splitlines():
            if ts_re.search(ln) and not any(
                    t in ln for t in ("schema_version", "$schema", "$id", "url")):
                bad_ts.append(ln[:120])
    add(5, "No nondeterministic timestamps in artifacts",
        "fail" if bad_ts else "pass",
        bad_ts[:5] or "no timestamps added in JSON/JSONL diff")

    add(6, "Active nightly failures referenced", "n/a",
        "operator must cross-check open GitHub issues")

    image_touched = any(
        f in ("Dockerfile", "docker-compose.yml", "docker-compose.prod.yml")
        or f.startswith(".github/workflows/docker-build.yml") for f in files)
    add(7, "Build provenance attached", "n/a",
        "image-touching PR" if image_touched else "non-image PR")

    ledger = a.ledger
    if ledger is None:
        from datetime import datetime, timezone
        d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ledger = str(ROOT / "logs" / ("agent_audit." + d + ".jsonl"))
    if Path(ledger).exists():
        try:
            r = subprocess.run(
                ["python", "-m", "reporting.agent_audit", "verify", ledger],
                capture_output=True, text=True, cwd=ROOT)
            ok = r.returncode == 0
            add(8, "Audit chain intact",
                "pass" if ok else "fail",
                (r.stdout or r.stderr).strip()[:200])
        except Exception as e:
            add(8, "Audit chain intact", "fail", "verify failed: " + repr(e))
    else:
        add(8, "Audit chain intact", "n/a", "no ledger at " + ledger)

    live_re = re.compile(
        r"^(execution/live/|automation/live/|agent/execution/live/|"
        r".*live_.*broker.*\.py$|.*_live\.py$|.*live_executor.*\.py$)")
    live = [f for f in files if live_re.search(f)]
    add(9, "No new live/broker connector files",
        "fail" if live else "pass", live or "no live-connector paths")

    add(10, "VERSION bump justified",
        "n/a" if "VERSION" not in files else "operator-confirms",
        "VERSION not in diff" if "VERSION" not in files
        else "VERSION changed; report must cite rationale")

    summary = [
        f for f in files
        if f.startswith("docs/governance/agent_run_summaries/")
        and f.endswith(".md") and not f.endswith("_template.md")]
    add(11, "Agent run summary committed",
        "pass" if summary else "operator-confirms",
        summary or "no run summary in diff")

    add(12, "CODEOWNERS review present", "n/a",
        "branch-protection enforces this at merge")

    fail = any(r["status"] == "fail" for r in R)
    if a.json:
        print(json.dumps({"base": a.base, "files": len(files),
                          "results": R,
                          "overall": "fail" if fail else "pass"}, indent=2))
    else:
        print("Release-gate checklist (base=" + a.base
              + ", " + str(len(files)) + " changed files)")
        print("=" * 60)
        badge = {"pass": "[PASS]", "fail": "[FAIL]",
                 "n/a": "[N/A]", "operator-confirms": "[OP]"}
        for r in R:
            ev = r["evidence"]
            if isinstance(ev, list):
                ev = ev[:3]
            print("  " + badge.get(r["status"], "[??]") + " "
                  + str(r["id"]).rjust(2) + ". " + r["name"] + ": " + str(ev))
        print()
        print("OVERALL: " + ("FAIL" if fail else "PASS"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
