from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from packages.qre_research.architecture_registry import (  # noqa: E402
    ALLOWED_MATURITY_LEVELS,
    AUTHORITY_FLAGS,
    BLOCKED_AUTHORITY_FLAGS,
    DEFAULT_REGISTRY_PATH,
    FROZEN_LEGACY_OUTPUTS,
    ArchitectureRegistryEntry,
    canonical_ownership_index,
    is_qre_impact_path,
    operator_decision_entries,
    protected_outputs,
    registered_entry_for_artifact,
    registered_entry_for_producer,
    registry_entries,
    registry_entries_for_paths,
)
from packages.qre_research.maturity_gate import EVIDENCE_REQUIREMENTS  # noqa: E402

REPORT_KIND: Final[str] = "qre_architecture_impact_report"
SCHEMA_VERSION: Final[int] = 1
TEXT_SUFFIXES: Final[tuple[str, ...]] = (
    ".csv",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
)
ARTIFACT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:logs|research|generated_research|data/imports)/"
    r"[A-Za-z0-9_\-./]*\.(?:csv|json|md|py|txt|yaml|yml)"
)
SAFETY: Final[dict[str, bool]] = {
    "read_only": True,
    "runtime_behavior_changed": False,
    "created_candidates": False,
    "created_strategies": False,
    "created_presets": False,
    "created_campaigns": False,
    "ran_screening": False,
    "mutated_frozen_outputs": False,
    "strategy_synthesis_authority": False,
    "shadow_authority": False,
    "paper_authority": False,
    "live_authority": False,
    "broker_authority": False,
    "risk_authority": False,
    "order_authority": False,
    "capital_allocation_authority": False,
}


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _run_git(args: tuple[str, ...], repo_root: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return ()
    return tuple(
        line.replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def changed_paths_from_git(
    *,
    repo_root: Path,
    base: str | None = None,
    head: str | None = None,
) -> tuple[str, ...]:
    if base and head:
        paths = _run_git(("diff", "--name-only", base, head), repo_root)
    else:
        paths = (
            *_run_git(("diff", "--name-only",), repo_root),
            *_run_git(("diff", "--name-only", "--cached"), repo_root),
            *_run_git(("ls-files", "--others", "--exclude-standard"), repo_root),
        )
    return tuple(sorted({path for path in paths if is_qre_impact_path(path)}))


def _read_existing_text(path: str, repo_root: Path) -> str:
    candidate = repo_root / path
    if not candidate.exists() or not candidate.is_file():
        return ""
    if candidate.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        return candidate.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return candidate.read_text(encoding="utf-8", errors="ignore")


def _artifact_paths(text_by_path: dict[str, str]) -> tuple[str, ...]:
    artifacts: set[str] = set()
    for path, text in text_by_path.items():
        if path.startswith(("logs/", "research/", "generated_research/", "data/imports/")):
            artifacts.add(path)
        if path.startswith(("docs/", "tests/")) or path == "packages/qre_research/architecture_registry.py":
            continue
        artifacts.update(match.group(0).rstrip("'\")`,") for match in ARTIFACT_PATTERN.finditer(text))
    return tuple(sorted(artifacts))


def _changed_python_modules(changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in changed_paths if path.endswith(".py") and not path.startswith("tests/"))


def _new_producer_modules(changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path
        for path in _changed_python_modules(changed_paths)
        if registered_entry_for_producer(path) is None
    )


def _new_consumer_modules(changed_paths: tuple[str, ...], text_by_path: dict[str, str]) -> tuple[str, ...]:
    consumers: set[str] = set()
    for path in _changed_python_modules(changed_paths):
        text = text_by_path.get(path, "")
        if (
            ("packages.qre_" in text or "research.qre_" in text or "tools.qre_" in text)
            and all(path not in entry.consumer_modules for entry in registry_entries())
        ):
            consumers.add(path)
    return tuple(sorted(consumers))


def _terms_in_text(
    terms: tuple[str, ...],
    text_by_path: dict[str, str],
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    haystack = "\n".join((*changed_paths, *text_by_path.values()))
    return tuple(sorted(term for term in terms if term in haystack))


def _enabled_blocked_authority_flags(text_by_path: dict[str, str]) -> tuple[str, ...]:
    enabled: set[str] = set()
    for path, text in text_by_path.items():
        if path.startswith(("docs/", "tests/")):
            continue
        for flag in BLOCKED_AUTHORITY_FLAGS:
            patterns = (
                rf'"{re.escape(flag)}"\s*:\s*true',
                rf"'{re.escape(flag)}'\s*:\s*True",
                rf"\b{re.escape(flag)}\s*=\s*True\b",
            )
            if any(re.search(pattern, text) for pattern in patterns):
                enabled.add(flag)
    return tuple(sorted(enabled))


def _registry_entries_touched(
    changed_paths: tuple[str, ...],
    text_by_path: dict[str, str],
    artifact_paths: tuple[str, ...],
) -> tuple[ArchitectureRegistryEntry, ...]:
    touched: dict[str, ArchitectureRegistryEntry] = {
        entry.id: entry
        for entry in registry_entries_for_paths((*changed_paths, *artifact_paths))
    }
    haystack = "\n".join((*changed_paths, *text_by_path.values()))
    for entry in registry_entries():
        if entry.id in haystack:
            touched[entry.id] = entry
    return tuple(touched[entry_id] for entry_id in sorted(touched))


def _operator_decisions(
    touched_entries: tuple[ArchitectureRegistryEntry, ...],
    new_producer_modules: tuple[str, ...],
    new_artifact_paths: tuple[str, ...],
    protected_outputs_touched: tuple[str, ...],
    blocked_flags_touched: tuple[str, ...],
) -> tuple[str, ...]:
    reasons = {
        entry.id
        for entry in touched_entries
        if entry.operator_decision_required
    }
    reasons.update(entry.id for entry in operator_decision_entries() if entry.id in reasons)
    if new_producer_modules:
        reasons.add("new_producer_modules")
    if new_artifact_paths:
        reasons.add("new_artifact_paths")
    if protected_outputs_touched:
        reasons.add("protected_outputs")
    if blocked_flags_touched:
        reasons.add("blocked_authority_flags")
    return tuple(sorted(reasons))


def _verdict(
    *,
    new_producer_modules: tuple[str, ...],
    new_artifact_paths: tuple[str, ...],
    protected_outputs_touched: tuple[str, ...],
    registry_entries_touched: tuple[ArchitectureRegistryEntry, ...],
    maturity_claims_touched: tuple[str, ...],
    authority_flags_touched: tuple[str, ...],
    blocked_authority_claims: tuple[str, ...],
    operator_decision_required: tuple[str, ...],
) -> tuple[str, str]:
    if protected_outputs_touched or blocked_authority_claims:
        return (
            "blocked",
            "Stop and request operator review before merging protected output or authority changes.",
        )
    if (
        new_producer_modules
        or new_artifact_paths
        or registry_entries_touched
        or maturity_claims_touched
        or authority_flags_touched
        or operator_decision_required
    ):
        return (
            "review_required",
            "Update registry or maturity coverage, then run the static QRE gates.",
        )
    return ("safe", "Proceed with standard review; no QRE architecture impact detected.")


def build_report(
    changed_paths: tuple[str, ...],
    *,
    repo_root: Path = REPO_ROOT_FOR_IMPORT,
) -> dict[str, object]:
    qre_paths = tuple(sorted({path.replace("\\", "/") for path in changed_paths if is_qre_impact_path(path)}))
    text_by_path = {path: _read_existing_text(path, repo_root) for path in qre_paths}
    artifact_paths = _artifact_paths(text_by_path)
    new_artifact_paths = tuple(
        path
        for path in artifact_paths
        if registered_entry_for_artifact(path) is None
    )
    canonical_objects = _terms_in_text(tuple(canonical_ownership_index()), text_by_path, qre_paths)
    maturity_claims = _terms_in_text(ALLOWED_MATURITY_LEVELS, text_by_path, qre_paths)
    evidence_claims = _terms_in_text(EVIDENCE_REQUIREMENTS, text_by_path, qre_paths)
    authority_flags = _terms_in_text(AUTHORITY_FLAGS, text_by_path, qre_paths)
    blocked_authority_claims = _enabled_blocked_authority_flags(text_by_path)
    protected = tuple(
        sorted(
            {
                path
                for path in (*qre_paths, *artifact_paths)
                if path in set(protected_outputs()) | set(FROZEN_LEGACY_OUTPUTS)
            }
        )
    )
    touched_entries = _registry_entries_touched(qre_paths, text_by_path, artifact_paths)
    new_producers = _new_producer_modules(qre_paths)
    new_consumers = _new_consumer_modules(qre_paths, text_by_path)
    operator_decisions = _operator_decisions(
        touched_entries,
        new_producers,
        new_artifact_paths,
        protected,
        blocked_authority_claims,
    )
    verdict, recommended_action = _verdict(
        new_producer_modules=new_producers,
        new_artifact_paths=new_artifact_paths,
        protected_outputs_touched=protected,
        registry_entries_touched=touched_entries,
        maturity_claims_touched=maturity_claims,
        authority_flags_touched=authority_flags,
        blocked_authority_claims=blocked_authority_claims,
        operator_decision_required=operator_decisions,
    )
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "registry_path": _relative_path(DEFAULT_REGISTRY_PATH, repo_root),
        "changed_qre_files": list(qre_paths),
        "new_producer_modules": list(new_producers),
        "new_consumer_modules": list(new_consumers),
        "new_artifact_paths": list(new_artifact_paths),
        "canonical_objects_touched": list(canonical_objects),
        "registry_entries_touched": [entry.id for entry in touched_entries],
        "maturity_claims_touched": [*maturity_claims, *evidence_claims],
        "authority_flags_touched": list(authority_flags),
        "blocked_authority_claims": list(blocked_authority_claims),
        "protected_outputs_touched": list(protected),
        "operator_decision_required": list(operator_decisions),
        "verdict": verdict,
        "recommended_next_action": recommended_action,
        "safety": dict(SAFETY),
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _json(report: dict[str, object]) -> str:
    return json.dumps(_stable(report), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _text(report: dict[str, object]) -> str:
    lines = [
        "# QRE Architecture Impact Report",
        "",
        f"- verdict: {report['verdict']}",
        f"- recommended_next_action: {report['recommended_next_action']}",
        f"- changed_qre_files: {len(report['changed_qre_files'])}",
        f"- registry_entries_touched: {', '.join(report['registry_entries_touched']) or 'none'}",
        f"- operator_decision_required: {', '.join(report['operator_decision_required']) or 'none'}",
        f"- protected_outputs_touched: {', '.join(report['protected_outputs_touched']) or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report static QRE architecture impact for a diff.")
    parser.add_argument("--base", help="Base git ref for diff mode.")
    parser.add_argument("--head", help="Head git ref for diff mode.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    if bool(args.base) != bool(args.head):
        parser.error("--base and --head must be provided together")

    repo_root = REPO_ROOT_FOR_IMPORT
    changed_paths = changed_paths_from_git(repo_root=repo_root, base=args.base, head=args.head)
    report = build_report(changed_paths, repo_root=repo_root)
    sys.stdout.write(_json(report) if args.json else _text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
