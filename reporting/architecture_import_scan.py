"""Deterministic repo-local Python import scanner for architecture review.

The scanner is intentionally static: it enumerates tracked Python files with
``git ls-files`` and parses import statements with ``ast``. It never imports
the modules it inspects.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

DOMAIN_ADE = "ADE"
DOMAIN_QRE = "QRE"
DOMAIN_CONTROL_PLANE = "control-plane"
DOMAIN_EXECUTION = "execution"
DOMAIN_TESTS = "tests"
DOMAIN_GOVERNANCE_TOOLING = "governance tooling"
DOMAIN_UNKNOWN = "unknown"

EXECUTION_PATH_ROOTS = frozenset(
    {
        "agent.execution",
        "agent.risk",
        "automation.live_gate",
        "broker",
        "execution",
        "live",
        "paper",
        "risk",
        "shadow",
    }
)

# Existing mixed-domain imports observed by ARCH-000. These remain visible in
# legacy reports, but they do not block ARCH-001 while package boundaries are
# still being prepared.
KNOWN_LEGACY_EDGE_ALLOWLIST = frozenset(
    {
        ("dashboard.api_campaigns", "research.campaign_digest"),
        ("dashboard.api_campaigns", "research.campaign_budget"),
        ("dashboard.api_campaigns", "research.campaign_family_policy"),
        ("dashboard.api_campaigns", "research.campaign_followup"),
        ("dashboard.api_campaigns", "research.campaign_launcher"),
        ("dashboard.api_campaigns", "research.campaign_policy"),
        ("dashboard.api_campaigns", "research.campaign_preset_policy"),
        ("dashboard.api_campaigns", "research.campaign_queue"),
        ("dashboard.api_campaigns", "research.campaign_registry"),
        ("dashboard.api_campaigns", "research.campaign_templates"),
        ("dashboard.api_observability", "research.diagnostics.paths"),
        ("dashboard.api_research_intelligence", "research.dead_zone_detection"),
        ("dashboard.api_research_intelligence", "research.funnel_spawn_proposer"),
        ("dashboard.api_research_intelligence", "research.information_gain"),
        ("dashboard.api_research_intelligence", "research.research_evidence_ledger"),
        ("dashboard.api_research_intelligence", "research.stop_condition_engine"),
        ("dashboard.api_research_intelligence", "research.viability_metrics"),
        ("dashboard.dashboard", "data.contracts"),
        ("dashboard.dashboard", "data.repository"),
        ("dashboard.dashboard", "research.presets"),
        ("dashboard.research_runner", "research.run_state"),
        ("reporting.hypothesis_discovery_summary", "research.hypothesis_discovery"),
        (
            "reporting.hypothesis_discovery_summary",
            "research.hypothesis_discovery.campaign_seed_proposer",
        ),
        ("reporting.intelligent_routing", "research.presets"),
    }
)


@dataclass(frozen=True)
class ImportEdge:
    source_module: str
    target_module: str
    source_path: str
    source_domain: str
    target_domain: str
    target_root: str
    line: int
    import_kind: str
    target_path: str | None = None


@dataclass(frozen=True)
class BoundaryFinding:
    source_module: str
    target_module: str
    source_path: str
    source_domain: str
    target_domain: str
    target_root: str
    line: int
    rule: str


@dataclass(frozen=True)
class BoundaryReport:
    edges: tuple[ImportEdge, ...]
    forbidden_edges: tuple[BoundaryFinding, ...]
    legacy_edges: tuple[BoundaryFinding, ...]


def tracked_python_files(repo_root: Path) -> tuple[Path, ...]:
    """Return tracked Python files relative to ``repo_root`` in stable order."""
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    files = [
        Path(line.strip())
        for line in result.stdout.splitlines()
        if line.strip() and not _is_generated_or_cache_path(line.strip())
    ]
    return tuple(sorted(files, key=_path_sort_key))


def scan_repo(repo_root: Path) -> BoundaryReport:
    tracked_files = tracked_python_files(repo_root)
    return scan_files(repo_root, tracked_files)


def scan_files(repo_root: Path, relative_paths: Iterable[Path]) -> BoundaryReport:
    paths = tuple(sorted(relative_paths, key=_path_sort_key))
    module_index = _module_index(paths)
    edges: list[ImportEdge] = []
    for path in paths:
        edges.extend(_imports_in_file(repo_root, path, module_index))
    return evaluate_edges(tuple(sorted(edges, key=_edge_sort_key)))


def evaluate_edges(edges: Sequence[ImportEdge]) -> BoundaryReport:
    forbidden: list[BoundaryFinding] = []
    legacy: list[BoundaryFinding] = []

    for edge in sorted(edges, key=_edge_sort_key):
        rule = _closed_forbidden_rule(edge)
        legacy_rule = _legacy_rule(edge)
        if rule:
            finding = _finding(edge, rule)
            if _is_allowlisted_legacy(edge):
                legacy.append(finding)
            else:
                forbidden.append(finding)
            continue
        if legacy_rule:
            legacy.append(_finding(edge, legacy_rule))

    return BoundaryReport(
        edges=tuple(sorted(edges, key=_edge_sort_key)),
        forbidden_edges=tuple(sorted(forbidden, key=_finding_sort_key)),
        legacy_edges=tuple(sorted(legacy, key=_finding_sort_key)),
    )


def classify_path(path: Path | str) -> str:
    normalized = _normalize_path(path)
    first = normalized.split("/", 1)[0]

    if first == "tests":
        return DOMAIN_TESTS
    if normalized.startswith(".claude/hooks/") or first == "scripts":
        return DOMAIN_GOVERNANCE_TOOLING
    if first == "dashboard" or first == "frontend":
        return DOMAIN_CONTROL_PLANE
    if first == "reporting":
        return DOMAIN_ADE
    if normalized.startswith("agent/execution/") or normalized.startswith("agent/risk/"):
        return DOMAIN_EXECUTION
    if first in {"automation", "broker", "execution", "live", "paper", "risk", "shadow"}:
        return DOMAIN_EXECUTION
    if first in {"agent", "data", "research", "strategies"}:
        return DOMAIN_QRE
    if first in {"config", "ops", "orchestration", "state"}:
        return DOMAIN_UNKNOWN
    return DOMAIN_UNKNOWN


def classify_module(module_name: str, module_index: dict[str, Path] | None = None) -> str:
    if module_index and module_name in module_index:
        return classify_path(module_index[module_name])

    top = module_name.split(".", 1)[0]
    if top == "tests":
        return DOMAIN_TESTS
    if top == "dashboard":
        return DOMAIN_CONTROL_PLANE
    if top == "reporting":
        return DOMAIN_ADE
    if module_name.startswith(("agent.execution", "agent.risk")):
        return DOMAIN_EXECUTION
    if top in {"automation", "broker", "execution", "live", "paper", "risk", "shadow"}:
        return DOMAIN_EXECUTION
    if top in {"agent", "data", "research", "strategies"}:
        return DOMAIN_QRE
    if top == "scripts":
        return DOMAIN_GOVERNANCE_TOOLING
    return DOMAIN_UNKNOWN


def report_to_dict(report: BoundaryReport) -> dict[str, object]:
    return {
        "edge_count": len(report.edges),
        "forbidden_edge_count": len(report.forbidden_edges),
        "legacy_edge_count": len(report.legacy_edges),
        "forbidden_edges": [asdict(finding) for finding in report.forbidden_edges],
        "legacy_edges": [asdict(finding) for finding in report.legacy_edges],
        "edges": [asdict(edge) for edge in report.edges],
    }


def report_to_summary_dict(report: BoundaryReport) -> dict[str, object]:
    """Return compact deterministic counts for architecture baseline docs."""
    domain_edge_categories = Counter(
        (edge.source_domain, edge.target_domain) for edge in report.edges
    )
    legacy_finding_categories = Counter(
        (finding.rule, finding.source_domain, finding.target_domain)
        for finding in report.legacy_edges
    )
    legacy_source_target_roots = Counter(
        (
            finding.source_path.split("/", 1)[0],
            finding.target_root,
            finding.rule,
        )
        for finding in report.legacy_edges
    )

    return {
        "edge_count": len(report.edges),
        "forbidden_edge_count": len(report.forbidden_edges),
        "legacy_edge_count": len(report.legacy_edges),
        "domain_edge_categories": [
            {
                "source_domain": source_domain,
                "target_domain": target_domain,
                "edge_count": count,
            }
            for (source_domain, target_domain), count in sorted(
                domain_edge_categories.items()
            )
        ],
        "legacy_finding_categories": [
            {
                "rule": rule,
                "source_domain": source_domain,
                "target_domain": target_domain,
                "finding_count": count,
            }
            for (rule, source_domain, target_domain), count in sorted(
                legacy_finding_categories.items()
            )
        ],
        "legacy_source_target_roots": [
            {
                "source_root": source_root,
                "target_root": target_root,
                "rule": rule,
                "finding_count": count,
            }
            for (source_root, target_root, rule), count in sorted(
                legacy_source_target_roots.items()
            )
        ],
    }


def report_to_text(report: BoundaryReport) -> str:
    lines = [
        "ARCH-001 domain import scan",
        f"edges: {len(report.edges)}",
        f"forbidden_edges: {len(report.forbidden_edges)}",
        f"legacy_edges: {len(report.legacy_edges)}",
        "",
        "Forbidden edges:",
    ]
    lines.extend(_format_findings(report.forbidden_edges))
    lines.append("")
    lines.append("Legacy/report-only edges:")
    lines.extend(_format_findings(report.legacy_edges))
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root to scan.")
    parser.add_argument(
        "--format",
        choices=("json", "summary", "text"),
        default="json",
        help="Deterministic report format.",
    )
    args = parser.parse_args(argv)

    report = scan_repo(Path(args.repo_root).resolve())
    if args.format == "json":
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    elif args.format == "summary":
        print(json.dumps(report_to_summary_dict(report), indent=2, sort_keys=True))
    else:
        print(report_to_text(report), end="")
    return 1 if report.forbidden_edges else 0


def _imports_in_file(
    repo_root: Path,
    relative_path: Path,
    module_index: dict[str, Path],
) -> list[ImportEdge]:
    full_path = repo_root / relative_path
    tree = ast.parse(full_path.read_text(encoding="utf-8"), filename=str(full_path))
    source_module = _module_name_from_path(relative_path)
    source_domain = classify_path(relative_path)
    edges: list[ImportEdge] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in sorted(node.names, key=lambda item: item.name):
                edges.append(
                    _edge(
                        source_module=source_module,
                        source_path=relative_path,
                        source_domain=source_domain,
                        target_module=alias.name,
                        line=node.lineno,
                        import_kind="import",
                        module_index=module_index,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            for target in _targets_from_import_from(node, source_module, relative_path, module_index):
                edges.append(
                    _edge(
                        source_module=source_module,
                        source_path=relative_path,
                        source_domain=source_domain,
                        target_module=target,
                        line=node.lineno,
                        import_kind="from",
                        module_index=module_index,
                    )
                )
    return edges


def _targets_from_import_from(
    node: ast.ImportFrom,
    source_module: str,
    source_path: Path,
    module_index: dict[str, Path],
) -> tuple[str, ...]:
    if node.level:
        base = _resolve_relative_base(source_module, source_path, node.level)
        if base is None:
            return tuple()
        module_base = ".".join(part for part in (base, node.module or "") if part)
    else:
        module_base = node.module or ""

    if not module_base:
        return tuple()

    targets = {
        _resolve_import_from_target(module_base, alias.name, module_index)
        for alias in node.names
    }
    return tuple(sorted(targets))


def _edge(
    *,
    source_module: str,
    source_path: Path,
    source_domain: str,
    target_module: str,
    line: int,
    import_kind: str,
    module_index: dict[str, Path],
) -> ImportEdge:
    resolved_target = _resolve_known_module(target_module, module_index)
    target_path = module_index.get(resolved_target)
    target_root = _target_root(resolved_target, target_path)
    return ImportEdge(
        source_module=source_module,
        target_module=resolved_target,
        source_path=_normalize_path(source_path),
        source_domain=source_domain,
        target_domain=classify_module(resolved_target, module_index),
        target_root=target_root,
        target_path=_normalize_path(target_path) if target_path else None,
        line=line,
        import_kind=import_kind,
    )


def _resolve_import_from_target(
    module_base: str,
    imported_name: str,
    module_index: dict[str, Path],
) -> str:
    if imported_name == "*":
        return _resolve_known_module(module_base, module_index)
    candidate = f"{module_base}.{imported_name}"
    if candidate in module_index or _has_module_descendant(candidate, module_index):
        return _resolve_known_module(candidate, module_index)
    return _resolve_known_module(module_base, module_index)


def _resolve_known_module(module_name: str, module_index: dict[str, Path]) -> str:
    parts = module_name.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in module_index:
            return candidate
    return module_name


def _resolve_relative_base(
    source_module: str,
    source_path: Path,
    level: int,
) -> str | None:
    if source_path.name == "__init__.py":
        package = source_module
    elif "." in source_module:
        package = source_module.rsplit(".", 1)[0]
    else:
        package = ""
    package_parts = package.split(".") if package else []
    keep = len(package_parts) - level + 1
    if keep < 0:
        return None
    return ".".join(package_parts[:keep])


def _module_index(paths: Iterable[Path]) -> dict[str, Path]:
    return {_module_name_from_path(path): path for path in paths}


def _module_name_from_path(path: Path) -> str:
    normalized = _normalize_path(path)
    without_suffix = normalized.removesuffix(".py")
    parts = without_suffix.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(part for part in parts if part)


def _target_root(module_name: str, target_path: Path | None) -> str:
    if target_path is not None:
        return _normalize_path(target_path).split("/", 1)[0]
    return module_name.split(".", 1)[0]


def _closed_forbidden_rule(edge: ImportEdge) -> str | None:
    if edge.source_domain == DOMAIN_TESTS:
        return None
    if edge.source_domain == DOMAIN_CONTROL_PLANE and edge.target_domain == DOMAIN_QRE:
        return "control-plane-to-qre"
    if edge.source_domain == DOMAIN_ADE and edge.target_domain == DOMAIN_QRE:
        return "ade-to-qre"
    if edge.source_domain == DOMAIN_QRE and edge.source_path.startswith("research/") and (
        edge.target_domain == DOMAIN_EXECUTION or _matches_prefix(edge.target_module, EXECUTION_PATH_ROOTS)
    ):
        return "qre-to-execution"
    return None


def _legacy_rule(edge: ImportEdge) -> str | None:
    if edge.source_domain == DOMAIN_TESTS:
        return None
    if edge.source_domain == DOMAIN_UNKNOWN or edge.target_domain == DOMAIN_UNKNOWN:
        return None
    if edge.source_domain == edge.target_domain:
        return None
    return "mixed-domain"


def _is_allowlisted_legacy(edge: ImportEdge) -> bool:
    return (edge.source_module, edge.target_module) in KNOWN_LEGACY_EDGE_ALLOWLIST


def _finding(edge: ImportEdge, rule: str) -> BoundaryFinding:
    return BoundaryFinding(
        source_module=edge.source_module,
        target_module=edge.target_module,
        source_path=edge.source_path,
        source_domain=edge.source_domain,
        target_domain=edge.target_domain,
        target_root=edge.target_root,
        line=edge.line,
        rule=rule,
    )


def _format_findings(findings: Sequence[BoundaryFinding]) -> list[str]:
    if not findings:
        return ["- none"]
    return [
        (
            f"- {finding.rule}: {finding.source_module}:{finding.line} -> "
            f"{finding.target_module} ({finding.source_domain} -> {finding.target_domain})"
        )
        for finding in sorted(findings, key=_finding_sort_key)
    ]


def _finding_sort_key(finding: BoundaryFinding) -> tuple[str, int, str, str]:
    return (
        finding.source_path,
        finding.line,
        finding.source_module,
        finding.target_module,
    )


def _edge_sort_key(edge: ImportEdge) -> tuple[str, int, str, str, str]:
    return (
        edge.source_path,
        edge.line,
        edge.source_module,
        edge.target_module,
        edge.import_kind,
    )


def _path_sort_key(path: Path | str) -> str:
    return _normalize_path(path)


def _normalize_path(path: Path | str | None) -> str:
    if path is None:
        return ""
    return str(path).replace("\\", "/")


def _has_module_descendant(module_name: str, module_index: dict[str, Path]) -> bool:
    prefix = module_name + "."
    return any(name.startswith(prefix) for name in module_index)


def _matches_prefix(module_name: str, prefixes: Iterable[str]) -> bool:
    return any(module_name == prefix or module_name.startswith(prefix + ".") for prefix in prefixes)


def _is_generated_or_cache_path(path: str) -> bool:
    normalized = _normalize_path(path)
    parts = normalized.split("/")
    return "__pycache__" in parts or normalized.startswith((".tmp/", "tests_tmp/"))


if __name__ == "__main__":
    raise SystemExit(main())
