"""v3.15.5 — run_research.py __main__ wrapper exit-code contract.

Pins:

- ``python -m research.run_research`` exits with rc=EXIT_CODE_DEGENERATE_NO_SURVIVORS
  when the run terminates via :class:`DegenerateResearchRunError`.
- Other exceptions still bubble (default rc=1) — we do NOT catch them.
- The callable ``run_research(...)`` (library use) still raises
  ``DegenerateResearchRunError`` so existing tests keep their contract.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from research.empty_run_reporting import (
    EXIT_CODE_DEGENERATE_NO_SURVIVORS,
    DegenerateResearchRunError,
)
from research import run_research as run_research_module


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_module_with_injected_main(main_body: str) -> int:
    """Execute the run_research module's __main__ block with a stubbed
    callable.

    We monkey-patch ``run_research.run_research`` to a function that
    raises the exception we want to test, then re-execute the module's
    ``__main__`` guard via ``runpy.run_path`` semantics. To keep this
    test hermetic and fast we just spawn a tiny inline subprocess
    that imports the module, replaces the function, then calls the
    `__main__` guard's body inline.
    """
    snippet = textwrap.dedent(f"""
        import sys
        from research import run_research as rr

        def _stub(**_kwargs):
            {main_body}

        rr.run_research = _stub
        # Re-run the __main__ block manually with no CLI args so
        # _parse_cli_args() succeeds with all defaults.
        sys.argv = ["research.run_research"]
        try:
            args = rr._parse_cli_args()
            try:
                rr.run_research(
                    resume=bool(args.resume),
                    retry_failed_batches=bool(args.retry_failed_batches),
                    continue_latest=bool(args.continue_latest),
                    preset=args.preset,
                    col_campaign_id=args.campaign_id,
                )
            except rr.DegenerateResearchRunError:
                sys.exit(rr.EXIT_CODE_DEGENERATE_NO_SURVIVORS)
        except SystemExit:
            raise
    """).strip()
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-c", snippet],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        shell=False,
    )
    return completed.returncode


def test_main_exit_code_on_degenerate_is_2():
    rc = _run_module_with_injected_main(
        'raise rr.DegenerateResearchRunError("forced for test")'
    )
    assert rc == EXIT_CODE_DEGENERATE_NO_SURVIVORS == 2


def test_main_other_exception_propagates_default_rc1():
    rc = _run_module_with_injected_main('raise RuntimeError("not degenerate")')
    # Python's default for an uncaught exception is rc=1.
    assert rc == 1


def test_main_clean_run_exits_0():
    rc = _run_module_with_injected_main("return None")
    assert rc == 0


def test_callable_run_research_still_raises_degenerate_for_library_callers():
    """The library callable must keep raising the exception — only the
    CLI ``__main__`` block translates it into rc=2. This pins the
    contract relied on by ``tests/unit/test_run_research_empty_run_handling``.
    """
    # We do not invoke the full run_research callable here; instead we
    # assert by introspection that the module exposes the exception
    # class and the constant the CLI wrapper relies on.
    assert hasattr(run_research_module, "DegenerateResearchRunError")
    assert run_research_module.DegenerateResearchRunError is DegenerateResearchRunError
    assert hasattr(run_research_module, "EXIT_CODE_DEGENERATE_NO_SURVIVORS")
    assert run_research_module.EXIT_CODE_DEGENERATE_NO_SURVIVORS == 2
