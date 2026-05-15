"""Pin tests for the v3.15.16.A15.B2.0e push-notification body
safety lint (``scripts/push_body_safety_lint.py``).

Pins:

* Closed cardinalities (6 push surfaces, 6 operator-go-phrase
  literals).
* Closed-set values for both constants.
* Pinned violation message format.
* Regression: zero violations on the real repo push surfaces — the
  lint must pass on day one.
* Synthetic-file tests for each forbidden literal.
* Missing files are silently skipped.
* Deterministic violation ordering (file then line then token).
* AST guard: the scanner module imports only stdlib + ``pathlib`` +
  ``typing``. No subprocess / socket / urllib / requests / httpx /
  aiohttp imports anywhere.

These tests are stdlib + pytest only. No subprocess. No network.
No mutation of any file outside ``tmp_path``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Add scripts/ to sys.path so the scanner module is importable. This
# matches the integration pattern used by scripts/governance_lint.py
# section 6.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import push_body_safety_lint as pbs  # noqa: E402


# ---------------------------------------------------------------------------
# Closed-set cardinalities
# ---------------------------------------------------------------------------


def test_push_publisher_files_constant_cardinality() -> None:
    assert len(pbs.PUSH_PUBLISHER_FILES) == 6


def test_push_publisher_files_constant_values() -> None:
    """Exact closed set. Adding or removing a surface requires updating
    both the lint and this test."""
    assert set(pbs.PUSH_PUBLISHER_FILES) == {
        "reporting/web_push_dispatch_adapter.py",
        "reporting/web_push_real_transport.py",
        "reporting/push_subscription_store.py",
        "dashboard/api_push_subscribe.py",
        "dashboard/api_push_dispatch.py",
        "frontend/public/sw-push.js",
    }


def test_forbidden_body_tokens_constant_cardinality() -> None:
    assert len(pbs.FORBIDDEN_BODY_TOKENS) == 6


def test_forbidden_body_tokens_constant_values() -> None:
    """Exact closed set. Adding or removing a literal requires updating
    both the lint and this test."""
    assert set(pbs.FORBIDDEN_BODY_TOKENS) == {
        "required_phrase",
        "operator_go_phrase",
        "OPERATOR-GO",
        "GO Batch",
        "GO A18",
        "GO enable",
    }


def test_violation_format_pin() -> None:
    """Pinned format string — downstream consumers may match against
    this verbatim."""
    assert (
        pbs.VIOLATION_FORMAT
        == "push_body_safety_violation: token={token!r} file={file} line={line}"
    )


# ---------------------------------------------------------------------------
# Regression pin: existing push surfaces produce zero violations
# ---------------------------------------------------------------------------


def test_existing_push_surfaces_have_zero_violations() -> None:
    """The lint must pass on the current repo state. If a future PR
    introduces an operator-go-phrase literal in any push surface, this
    test fails before CI catches it."""
    violations = pbs.find_push_body_safety_violations(REPO_ROOT)
    assert violations == [], (
        f"existing push surfaces produced {len(violations)} unexpected "
        f"violation(s):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Synthetic-file tests — one per forbidden token
# ---------------------------------------------------------------------------


def _synth_root(tmp_path: Path, rel_file: str, content: str) -> Path:
    """Write a synthetic file at ``tmp_path / rel_file`` and return
    ``tmp_path`` for use as the scanner's ``repo_root``."""
    target = tmp_path / rel_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "token",
    [
        "required_phrase",
        "operator_go_phrase",
        "OPERATOR-GO",
        "GO Batch",
        "GO A18",
        "GO enable",
    ],
)
def test_synthetic_violation_for_each_forbidden_token(
    token: str, tmp_path: Path
) -> None:
    """For each of the 6 closed forbidden literals, a single synthetic
    push surface containing the literal produces exactly one violation,
    in the closed format, with the correct file + line + token fields."""
    rel_file = "reporting/web_push_dispatch_adapter.py"
    content = f'body = "hello world"\nphrase = "{token}"\n'
    root = _synth_root(tmp_path, rel_file, content)
    violations = pbs.find_push_body_safety_violations(root)
    assert len(violations) == 1, (
        f"expected exactly 1 violation for token {token!r}, got "
        f"{len(violations)}: {violations}"
    )
    expected = pbs.VIOLATION_FORMAT.format(
        token=token, file=rel_file, line=2
    )
    assert violations[0] == expected


# ---------------------------------------------------------------------------
# Missing-file behaviour
# ---------------------------------------------------------------------------


def test_missing_file_silently_skipped(tmp_path: Path) -> None:
    """When a configured push surface is missing on disk, the scanner
    skips it silently. Returns [] if no other violations."""
    violations = pbs.find_push_body_safety_violations(tmp_path)
    assert violations == []


def test_missing_file_does_not_mask_other_violations(
    tmp_path: Path,
) -> None:
    """If one configured file is missing but another has a violation,
    the violation is still reported."""
    _synth_root(
        tmp_path,
        "reporting/web_push_dispatch_adapter.py",
        'phrase = "required_phrase"\n',
    )
    # The other 5 push surfaces are intentionally absent under tmp_path.
    violations = pbs.find_push_body_safety_violations(tmp_path)
    assert len(violations) == 1
    assert "required_phrase" in violations[0]


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


def test_violations_ordered_by_file_then_line_then_token(
    tmp_path: Path,
) -> None:
    """Two violations in two different surfaces, with multiple lines
    and multiple tokens per file, appear in the deterministic order:
    file index (catalog order), then line number, then token order."""
    # File 1: reporting/web_push_dispatch_adapter.py (catalog index 0).
    _synth_root(
        tmp_path,
        "reporting/web_push_dispatch_adapter.py",
        "\n".join(
            [
                'a = "GO Batch 2 Unit foo"',  # line 1: "GO Batch"
                'b = "required_phrase here"',  # line 2: "required_phrase"
            ]
        )
        + "\n",
    )
    # File 4: dashboard/api_push_subscribe.py (catalog index 3).
    _synth_root(
        tmp_path,
        "dashboard/api_push_subscribe.py",
        'c = "OPERATOR-GO test"\n',
    )
    violations = pbs.find_push_body_safety_violations(tmp_path)
    assert len(violations) == 3
    # File 1 entries come before file 4 entries.
    assert "reporting/web_push_dispatch_adapter.py line=1" in violations[0]
    assert "reporting/web_push_dispatch_adapter.py line=2" in violations[1]
    assert "dashboard/api_push_subscribe.py line=1" in violations[2]


def test_two_tokens_on_same_line_both_reported(tmp_path: Path) -> None:
    """A single line that contains two distinct forbidden tokens
    produces two violations, ordered by token catalog index."""
    _synth_root(
        tmp_path,
        "reporting/web_push_dispatch_adapter.py",
        'x = "required_phrase plus GO Batch on one line"\n',
    )
    violations = pbs.find_push_body_safety_violations(tmp_path)
    assert len(violations) == 2
    # required_phrase (index 0) is reported before GO Batch (index 3).
    assert "required_phrase" in violations[0]
    assert "GO Batch" in violations[1]


# ---------------------------------------------------------------------------
# Module surface: AST guard against forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_TOPS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
)


def test_module_has_no_subprocess_or_network_imports() -> None:
    """The scanner is stdlib-only. AST scan rejects any subprocess /
    socket / urllib / requests / httpx / aiohttp import."""
    src = (SCRIPTS_DIR / "push_body_safety_lint.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                assert top not in _FORBIDDEN_IMPORT_TOPS, (
                    f"scanner imports forbidden module: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in _FORBIDDEN_IMPORT_TOPS, (
                f"scanner imports forbidden module: from {node.module!r}"
            )


# ---------------------------------------------------------------------------
# Caller-injected token override (tests-only API surface)
# ---------------------------------------------------------------------------


def test_caller_can_inject_custom_files_and_tokens(tmp_path: Path) -> None:
    """The scanner's ``files`` and ``tokens`` keyword arguments are a
    closed test-only API surface. Production calls omit them and pick
    up the module-level closed lists."""
    _synth_root(
        tmp_path,
        "custom/path.txt",
        'literal = "custom_violation_marker"\n',
    )
    violations = pbs.find_push_body_safety_violations(
        tmp_path,
        files=("custom/path.txt",),
        tokens=("custom_violation_marker",),
    )
    assert len(violations) == 1
    assert "custom/path.txt" in violations[0]
    assert "custom_violation_marker" in violations[0]
