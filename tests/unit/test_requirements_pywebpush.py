"""Pin test for the N2b-3b runtime dependency on ``pywebpush``.

Pins:

* ``requirements.txt`` contains exactly one ``pywebpush`` declaration;
* the declaration is exactly ``pywebpush>=1.14.0`` (the version
  bound matched by :mod:`reporting.web_push_real_transport`'s lazy
  import contract);
* no VAPID-private-key env name or PEM marker appears on the
  ``pywebpush`` line (defense-in-depth — ``requirements.txt`` is
  not the place to ever stash secrets);
* the line is well-formed (no leading whitespace, no trailing
  comment, single token).

This is a declarative pin: it does NOT import ``pywebpush`` and
therefore passes in dev environments where the optional runtime
dependency has not been pip-installed locally. The Dockerfile is
the install boundary (``pip install -r requirements.txt``).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"

_EXPECTED_LINE = "pywebpush>=1.14.0"

# Defense-in-depth — patterns that must never appear on the
# pywebpush declaration line in requirements.txt.
_FORBIDDEN_ON_DEP_LINE = (
    "WEB_PUSH_VAPID_PRIVATE_KEY",
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
)


def _requirements_lines() -> list[str]:
    return REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()


def _pywebpush_lines() -> list[str]:
    return [
        ln for ln in _requirements_lines()
        if re.match(r"^\s*pywebpush\b", ln, re.IGNORECASE)
    ]


def test_requirements_file_exists() -> None:
    assert REQUIREMENTS_PATH.is_file()


def test_exactly_one_pywebpush_line() -> None:
    matches = _pywebpush_lines()
    assert len(matches) == 1, (
        f"requirements.txt must contain exactly one pywebpush line; "
        f"found {len(matches)}: {matches}"
    )


def test_pywebpush_line_is_pinned_exactly() -> None:
    matches = _pywebpush_lines()
    assert matches == [_EXPECTED_LINE], (
        f"requirements.txt pywebpush pin must be {_EXPECTED_LINE!r}; "
        f"got {matches!r}"
    )


def test_pywebpush_line_carries_no_secret_marker() -> None:
    matches = _pywebpush_lines()
    assert matches, "pywebpush line missing"
    line = matches[0]
    for needle in _FORBIDDEN_ON_DEP_LINE:
        assert needle not in line, (
            f"requirements.txt pywebpush line must not contain {needle!r}"
        )
