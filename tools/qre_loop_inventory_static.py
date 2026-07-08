"""Read-only static inventory for the QRE research loop.

The scanner intentionally uses filesystem text and AST parsing only. It does
not import repository research modules, run campaign code, or execute any QRE
runtime path.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOTS: Final[tuple[str, ...]] = ("research", "packages", "reporting", "tools")
REFERENCE_ROOTS: Final[tuple[str, ...]] = ("tests", "docs")
WRITE_PATH: Final[Path] = Path("logs/qre_loop_architecture_inventory/latest.json")
REPORT_KIND: Final[str] = "qre_loop_architecture_inventory_static"
CONFIDENCE_LEVELS: Final[tuple[str, ...]] = ("verified", "inferred", "unknown")
AUTHORITY_TERMS: Final[tuple[str, ...]] = (
    "validation",
    "promotion",
    "shadow",
    "paper",
    "live",
    "trading_authority",
)
SEARCH_PATTERNS: Final[tuple[str, ...]] = (
    "report_kind",
    "REPORT_KIND",
    "DEFAULT_*PATH",
    "*_PATH",
    "latest.json",
    "write_outputs",
    "read_*status",
    "build_*",
    "main(",
    "argparse",
    "candidate",
    "hypothesis",
    "screening",
    "evidence",
    "feedback",
    "memory",
    "router",
    "sampling",
    "campaign",
    "validation",
    "promotion",
    "shadow",
    "paper",
    "live",
    "trading_authority",
    "strategy_matrix.csv",
    "research_latest.json",
)


PATH_NAME_RE: Final[re.Pattern[str]] = re.compile(r"(^DEFAULT_.*PATH$|.*_PATH$|.*PATHS$)")
LOCAL_IMPORT_PREFIXES: Final[tuple[str, ...]] = ("research", "packages", "reporting", "tools")


@dataclass(frozen=True)
class Finding:
    kind: str
    file: str
    line: int
    name: str
    value: str
    confidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "name": self.name,
            "value": self.value,
            "confidence": self.confidence,
        }


def _rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _module_name(path: Path, repo_root: Path) -> str:
    rel = path.resolve().relative_to(repo_root.resolve()).with_suffix("")
    return ".".join(rel.parts)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _safe_literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Path"
            and node.args
        ):
            return _safe_literal(node.args[0])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = _safe_literal(node.left)
            right = _safe_literal(node.right)
            if left is not None and right is not None:
                return f"{left}/{right}"
        return None


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        names: list[str] = []
        for item in target.elts:
            names.extend(_target_names(item))
        return names
    return []


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _add(
    findings: list[Finding],
    *,
    kind: str,
    file: str,
    line: int,
    name: str,
    value: Any,
    confidence: str,
) -> None:
    findings.append(
        Finding(
            kind=kind,
            file=file,
            line=max(1, int(line or 1)),
            name=name,
            value=_stringify(value),
            confidence=confidence,
        )
    )


def _extract_assignment_findings(
    tree: ast.AST,
    file: str,
    findings: list[Finding],
) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = _safe_literal(node.value)
        for target in targets:
            for name in _target_names(target):
                if name == "REPORT_KIND":
                    _add(
                        findings,
                        kind="report_kind",
                        file=file,
                        line=node.lineno,
                        name=name,
                        value=value,
                        confidence="verified",
                    )
                if PATH_NAME_RE.match(name):
                    _add(
                        findings,
                        kind="artifact_path_constant",
                        file=file,
                        line=node.lineno,
                        name=name,
                        value=value,
                        confidence="verified",
                    )


def _extract_function_findings(tree: ast.AST, file: str, findings: list[Finding]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name == "write_outputs":
            _add(
                findings,
                kind="write_outputs_function",
                file=file,
                line=node.lineno,
                name=node.name,
                value=node.name,
                confidence="verified",
            )
        if node.name == "main":
            _add(
                findings,
                kind="main_entrypoint",
                file=file,
                line=node.lineno,
                name=node.name,
                value=node.name,
                confidence="verified",
            )
        if node.name.startswith("read_") or node.name.endswith("_status") or "status" in node.name:
            _add(
                findings,
                kind="read_status_function",
                file=file,
                line=node.lineno,
                name=node.name,
                value=node.name,
                confidence="verified",
            )
        if node.name.startswith("build_"):
            _add(
                findings,
                kind="build_function",
                file=file,
                line=node.lineno,
                name=node.name,
                value=node.name,
                confidence="verified",
            )


def _extract_import_findings(
    tree: ast.AST,
    file: str,
    module: str,
    findings: list[Finding],
) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in LOCAL_IMPORT_PREFIXES:
                    _add(
                        findings,
                        kind="local_import",
                        file=file,
                        line=node.lineno,
                        name=module,
                        value=alias.name,
                        confidence="verified",
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in LOCAL_IMPORT_PREFIXES:
                _add(
                    findings,
                    kind="local_import",
                    file=file,
                    line=node.lineno,
                    name=module,
                    value=node.module,
                    confidence="verified",
                )


def _extract_dict_report_kind(tree: ast.AST, file: str, findings: list[Finding]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if isinstance(key, ast.Constant) and key.value == "report_kind":
                literal = _safe_literal(value)
                _add(
                    findings,
                    kind="report_kind",
                    file=file,
                    line=getattr(key, "lineno", getattr(node, "lineno", 1)),
                    name="report_kind",
                    value=literal,
                    confidence="verified" if isinstance(literal, str) else "inferred",
                )


def _line_findings(path: Path, repo_root: Path, text: str, findings: list[Finding]) -> None:
    rel = _rel(path, repo_root)
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "argparse" in line:
            _add(
                findings,
                kind="argparse_entrypoint_reference",
                file=rel,
                line=line_no,
                name="argparse",
                value=line.strip(),
                confidence="verified",
            )
        if "frozen" in line.lower() and "contract" in line.lower():
            _add(
                findings,
                kind="frozen_contract_reference",
                file=rel,
                line=line_no,
                name="frozen_contract",
                value=line.strip(),
                confidence="verified",
            )
        for term in AUTHORITY_TERMS:
            if term in line.lower():
                _add(
                    findings,
                    kind="authority_risk_reference",
                    file=rel,
                    line=line_no,
                    name=term,
                    value=line.strip(),
                    confidence="verified",
                )
        if any(marker in line for marker in ("latest.json", "research_latest.json", "strategy_matrix.csv")):
            _add(
                findings,
                kind="artifact_path_reference",
                file=rel,
                line=line_no,
                name="artifact_reference",
                value=line.strip(),
                confidence="verified",
            )
        if "write_text" in line or "replace(" in line or ".open(" in line and '"w"' in line:
            _add(
                findings,
                kind="likely_producer",
                file=rel,
                line=line_no,
                name="static_write_reference",
                value=line.strip(),
                confidence="inferred",
            )
        if "read_text" in line or "json.loads" in line or ".open(" in line and '"r"' in line:
            _add(
                findings,
                kind="likely_consumer",
                file=rel,
                line=line_no,
                name="static_read_reference",
                value=line.strip(),
                confidence="inferred",
            )


def _scan_python(path: Path, repo_root: Path, findings: list[Finding]) -> None:
    text = _read_text(path)
    rel = _rel(path, repo_root)
    _line_findings(path, repo_root, text, findings)
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        _add(
            findings,
            kind="parse_status",
            file=rel,
            line=exc.lineno or 1,
            name="syntax_error",
            value=str(exc),
            confidence="unknown",
        )
        return
    module = _module_name(path, repo_root)
    _extract_assignment_findings(tree, rel, findings)
    _extract_function_findings(tree, rel, findings)
    _extract_import_findings(tree, rel, module, findings)
    _extract_dict_report_kind(tree, rel, findings)


def _python_files(repo_root: Path, roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = repo_root / root_name
        if root.exists():
            files.extend(path for path in root.rglob("*.py") if "history" not in path.parts)
    return sorted(files)


def _reference_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in REFERENCE_ROOTS:
        root = repo_root / root_name
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".py", ".md", ".json", ".jsonl"}
            )
    return sorted(files)


def _module_references(repo_root: Path, modules: list[str]) -> dict[str, dict[str, list[str]]]:
    references = {module: {"tests": [], "docs": []} for module in modules}
    module_needles = {module: (module, module.replace(".", "/") + ".py") for module in modules}
    for path in _reference_files(repo_root):
        text = _read_text(path)
        rel = _rel(path, repo_root)
        bucket = "tests" if rel.startswith("tests/") else "docs"
        for module, needles in module_needles.items():
            if any(needle in text for needle in needles):
                references[module][bucket].append(rel)
    return references


def _artifact_references(repo_root: Path, artifacts: list[str]) -> dict[str, dict[str, list[str]]]:
    references = {artifact: {"tests": [], "docs": []} for artifact in artifacts}
    for path in _reference_files(repo_root):
        text = _read_text(path)
        rel = _rel(path, repo_root)
        bucket = "tests" if rel.startswith("tests/") else "docs"
        for artifact in artifacts:
            if artifact and artifact in text:
                references[artifact][bucket].append(rel)
    return references


def _summarize_modules(
    repo_root: Path,
    py_files: list[Path],
    findings: list[Finding],
) -> list[dict[str, Any]]:
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.file, []).append(finding)
    module_names = [_module_name(path, repo_root) for path in py_files]
    refs = _module_references(repo_root, module_names)
    modules: list[dict[str, Any]] = []
    for path in py_files:
        rel = _rel(path, repo_root)
        module = _module_name(path, repo_root)
        kinds = sorted({finding.kind for finding in by_file.get(rel, [])})
        modules.append(
            {
                "module": module,
                "path": rel,
                "finding_kinds": kinds,
                "likely_producer": "write_outputs_function" in kinds or "likely_producer" in kinds,
                "likely_consumer": "likely_consumer" in kinds,
                "tests": sorted(refs[module]["tests"]),
                "docs": sorted(refs[module]["docs"]),
                "confidence": "inferred" if {"likely_producer", "likely_consumer"} & set(kinds) else "verified",
            }
        )
    return modules


def build_inventory(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    findings: list[Finding] = []
    py_files = _python_files(repo_root, DEFAULT_SCAN_ROOTS)
    for path in py_files:
        _scan_python(path, repo_root, findings)

    artifacts = sorted(
        {
            finding.value
            for finding in findings
            if finding.kind in {"artifact_path_constant", "artifact_path_reference"}
            and finding.value
            and finding.value != "null"
        }
    )
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            item.file,
            item.line,
            item.kind,
            item.name,
            item.value,
            item.confidence,
        ),
    )
    return {
        "report_kind": REPORT_KIND,
        "schema_version": "1.0",
        "scan_roots": list(DEFAULT_SCAN_ROOTS),
        "reference_roots": list(REFERENCE_ROOTS),
        "search_patterns": list(SEARCH_PATTERNS),
        "confidence_levels": list(CONFIDENCE_LEVELS),
        "modules": _summarize_modules(repo_root, py_files, findings),
        "findings": [finding.as_dict() for finding in sorted_findings],
        "artifact_references": _artifact_references(repo_root, artifacts),
        "safety": {
            "read_only_static_scan": True,
            "runtime_modules_imported": False,
            "research_runtime_called": False,
            "trading_authority": False,
        },
    }


def _write_inventory(repo_root: Path, payload: dict[str, Any]) -> Path:
    path = repo_root / WRITE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static QRE loop architecture inventory.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    payload = build_inventory(repo_root)
    if args.write:
        _write_inventory(repo_root, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
