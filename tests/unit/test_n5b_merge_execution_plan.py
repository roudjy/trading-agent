"""Doc pin-tests + repo-wide source scans for the N5b plan-only slice.

Locks the new ``docs/governance/n5b_merge_execution_plan.md`` doc
against drift away from the doctrine, and asserts the
documentation-only PR did not smuggle in any runtime merge
execution code.

The N5b plan is **documentation only**. It must not introduce a
Flask blueprint, a route, a CLI, a subprocess call, a GitHub
mutation call, or any executable merge / approve / deploy
adapter. These tests fail-closed if a future commit tries to
sneak a runtime implementation in under the doc-only banner.

Defense-in-depth note: the forbidden marker strings the tests
search for are NEVER embedded as literals in this file (a
literal ``BEGIN PRIVATE KEY`` block in the test source itself
would trip gitleaks' private-key rule). Markers are assembled at
runtime from constituent parts so the test source stays
inert to scanners.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "governance" / "n5b_merge_execution_plan.md"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Doc existence + size
# ---------------------------------------------------------------------------


def test_doc_file_exists() -> None:
    assert DOC_PATH.is_file(), (
        f"N5b merge execution plan missing: {DOC_PATH}"
    )


def test_doc_is_non_trivial_in_size() -> None:
    text = _doc_text()
    # A meaningful plan-doc is at least ~6 KiB. Anything smaller
    # means the operator does not have enough governance material
    # to enforce the safety boundaries.
    assert len(text) > 6000, (
        f"N5b plan-doc is too short ({len(text)} bytes); the doc "
        "must document the full §1-§12 governance surface."
    )


# ---------------------------------------------------------------------------
# Positive phrase pins — required doctrine language
# ---------------------------------------------------------------------------


def test_doc_states_plan_only_status() -> None:
    text = _doc_text().lower()
    assert "plan only" in text, (
        "doc must declare 'Plan only' status at the top"
    )


def test_doc_states_not_implemented_status() -> None:
    text = _doc_text().lower()
    assert "not implemented" in text, (
        "doc must declare 'Not implemented' status"
    )


def test_doc_forbids_autonomous_merge() -> None:
    text = _doc_text().lower()
    # The exact phrase from §11. We accept either the canonical
    # 'no autonomous merge' or the longer 'autonomous merge' deny
    # nearby.
    assert "no autonomous merge" in text, (
        "doc must declare 'No autonomous merge' as a permanent denial"
    )


def test_doc_pins_step5_implementation_allowed_false() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text, (
        "doc must reference step5_implementation_allowed invariant"
    )
    # The literal 'false' must appear nearby (within 200 chars of
    # the first mention).
    idx = text.find("step5_implementation_allowed")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "step5_implementation_allowed must be stated as false in the doc"
    )


def test_doc_pins_step5_enabled_substage_none() -> None:
    text = _doc_text()
    assert (
        "STEP5_ENABLED_SUBSTAGE" in text
        or "step5_enabled_substage" in text
    ), "doc must reference STEP5_ENABLED_SUBSTAGE invariant"
    assert '"none"' in text or " none" in text.lower(), (
        "STEP5_ENABLED_SUBSTAGE must be stated as 'none' in the doc"
    )


def test_doc_states_level_6_permanently_disabled() -> None:
    text = _doc_text().lower()
    assert "level 6" in text, "doc must reference Level 6 doctrine"
    assert "permanently disabled" in text or "no level 6" in text, (
        "doc must state Level 6 is permanently disabled / denied"
    )


def test_doc_states_n4b_phase_b_is_operator_go_only() -> None:
    """The doc must reference N4b Phase B AND somewhere in the
    doc qualify it as operator-go-only. We do not require the
    two phrases within strict proximity — N4b Phase B is named
    in §3 as a precondition and in §12 as an open carry-forward
    item; the operator-go qualifier may land in either §3 / §10
    / §12 depending on how the doc evolves."""
    text = _doc_text().lower()
    assert "n4b phase b" in text, (
        "doc must reference N4b Phase B activation"
    )
    assert "operator-go" in text or "operator go" in text, (
        "doc must qualify N4b Phase B as operator-go-only somewhere"
    )


def test_doc_states_n4c_is_future_slice() -> None:
    """The doc must reference N4c AND somewhere qualify it as a
    future slice. Same relaxed-proximity reasoning as the N4b
    pin above."""
    text = _doc_text().lower()
    assert "n4c" in text, "doc must reference N4c"
    assert "future slice" in text, (
        "doc must qualify N4c as a future slice somewhere"
    )


def test_doc_pins_a18b_exact_go_phrase() -> None:
    text = _doc_text()
    # Build the required phrase at runtime so the test source
    # itself is inert to grep/scanning tools.
    a18b_phrase = "GO " + "A18b " + "generated_seed " + "writer"
    assert a18b_phrase in text, (
        f"doc must pin the exact A18b activation phrase: {a18b_phrase!r}"
    )


def test_doc_requires_merge_state_status_clean() -> None:
    text = _doc_text()
    assert "mergeStateStatus" in text or "mergeStateStatus = CLEAN" in text, (
        "doc must require mergeStateStatus = CLEAN as a precondition"
    )
    # CLEAN must appear close to the mergeStateStatus mention.
    idx = text.find("mergeStateStatus")
    nearby = text[idx : idx + 200]
    assert "CLEAN" in nearby, (
        "mergeStateStatus must be qualified as required = CLEAN"
    )


def test_doc_requires_exact_head_sha_binding() -> None:
    text = _doc_text().lower()
    # The doc binds head SHA both at mint time and at execution
    # time. Either phrasing satisfies the pin.
    assert "head sha" in text or "head_sha" in text, (
        "doc must require head SHA binding"
    )
    assert "head sha at execution" in text or (
        "head_sha at execution" in text
    ) or "equals token-bound head sha" in text, (
        "doc must require head SHA equality at execution time"
    )


def test_doc_requires_pr_number_binding() -> None:
    text = _doc_text().lower()
    assert "pr number" in text or "pr_number" in text, (
        "doc must require PR-number binding"
    )
    # The 'bound to PR number' phrasing or equivalent must appear.
    assert (
        "bound to pr number" in text
        or "bound to pr_number" in text
        or "token's `pr_number`" in text
        or "token's pr_number" in text
    ), "doc must explicitly bind the token to the PR number"


def test_doc_requires_replay_and_nonce_protection() -> None:
    text = _doc_text().lower()
    assert "replay" in text and "nonce" in text, (
        "doc must require both replay protection and nonce handling"
    )
    # Replay-detected as a stop condition must appear.
    assert "replay_detected" in text or "replay detected" in text, (
        "doc must declare replay_detected as a stop-condition"
    )


def test_doc_forbids_deploy_coupling() -> None:
    text = _doc_text().lower()
    assert "deploy coupling" in text or "no deploy coupling" in text, (
        "doc must forbid deploy coupling"
    )
    # The qualifier 'must not' / 'forbidden' / 'no' should be
    # near the deploy-coupling mention.
    idx = text.find("deploy coupling")
    if idx < 0:
        idx = text.find("no deploy coupling")
    nearby = text[max(0, idx - 100) : idx + 200]
    assert any(
        marker in nearby
        for marker in ("forbidden", "must not", "no ", "deny")
    ), "doc must state deploy coupling is forbidden, not just mention it"


def test_doc_requires_dry_run_default() -> None:
    text = _doc_text().lower()
    assert "dry-run" in text or "dry run" in text, (
        "doc must mention dry-run"
    )
    # The 'default to dry-run' qualifier must appear.
    assert (
        "default to dry-run" in text
        or "dry-run default" in text
        or "dry run default" in text
        or "default to dry run" in text
    ), "doc must require dry-run as the default for the future adapter"


def test_doc_requires_no_branch_protection_bypass() -> None:
    """The doc must reference branch protection AND somewhere
    forbid bypassing it (either via the explicit 'no branch
    protection bypass' phrase, the '--admin' negative
    instruction, or the 'no admin merge' / 'no admin token'
    qualifiers). We do not require strict proximity — the
    bypass-prohibition naturally lives in §8 'Security
    boundaries', not adjacent to the first mention in §3 / §7."""
    text = _doc_text().lower()
    assert "branch protection" in text, (
        "doc must reference branch protection"
    )
    qualifiers = (
        "must not be bypassed",
        "no branch protection bypass",
        "without the `--admin`",
        "without the --admin",
        "no admin merge",
        "no admin token",
        "no `--admin`",
        "no --admin",
    )
    assert any(q in text for q in qualifiers), (
        "doc must forbid bypassing branch protection / admin merge "
        "somewhere in the doc"
    )


def test_doc_requires_rollback_and_failure_handling() -> None:
    text = _doc_text().lower()
    # The §7 stop conditions cover failure modes; §10 / §6.5 cover
    # rollback. We assert both concepts appear.
    assert "stop condition" in text, (
        "doc must enumerate stop conditions"
    )
    assert "failure" in text, (
        "doc must address failure handling"
    )
    assert "rollback" in text or "abort" in text, (
        "doc must address rollback / abort behaviour for failure modes"
    )


def test_doc_requires_audit_trail_artifacts() -> None:
    text = _doc_text().lower()
    for kind in ("preflight", "dry-run artefact", "decision", "failure"):
        # Accept either 'dry-run artefact' or 'dry-run' near 'artefact'.
        if kind == "dry-run artefact":
            assert "dry-run" in text and "artefact" in text, (
                "doc must define dry-run artefact"
            )
            continue
        assert kind in text, (
            f"doc must define audit artefact kind: {kind!r}"
        )


def test_doc_lists_operator_confirmation_moments() -> None:
    text = _doc_text().lower()
    assert "operator confirmation" in text or (
        "operator-confirmed" in text
    ), "doc must require explicit operator confirmation moment(s)"


def test_doc_states_no_runtime_authority() -> None:
    text = _doc_text().lower()
    assert "no runtime authority" in text, (
        "doc must declare 'No runtime authority'"
    )


def test_doc_states_exactly_one_merge_execution_route_exists() -> None:
    """B2.8e replaces the prior "no merge execution route exists"
    pin with a positive pin per implementation plan §6.4:
    "exactly one merge-execution route [module] exists, and it
    is the dry-run route".

    The doc must:
    * declare exactly one merge-execution route module exists
      (either as "route exists" or — more precisely after B2.8e —
      as "route module exists", reflecting that the blueprint is
      not yet wired into ``dashboard/dashboard.py``);
    * identify the dry-run route URL literally;
    * preserve the doctrine that the blueprint remains UNWIRED in
      ``dashboard/dashboard.py`` until the operator applies the
      wiring patch separately.

    No other doc-doctrine pin is weakened by B2.8e."""
    text = _doc_text()
    text_lc = text.lower()
    assert (
        "exactly one merge-execution route exists" in text_lc
        or "exactly one merge-execution route module exists" in text_lc
    ), (
        "doc must declare 'Exactly one merge-execution route [module] exists' "
        "(B2.8e positive pin replacement)"
    )
    # The dry-run route URL must be literally present.
    assert "/api/agent-control/merge-execution/dry-run" in text, (
        "doc must identify the dry-run route URL literally"
    )
    # UNWIRED-until-operator-applies doctrine must be preserved.
    assert "unwired" in text_lc, (
        "doc must preserve the UNWIRED-until-operator-applies doctrine"
    )


def test_doc_carries_forward_n4b_n4c_n5b_a18b() -> None:
    """The §12 carry-forward block must explicitly enumerate the
    four open items so a future reviewer can see at a glance what
    is and is not authorised."""
    text = _doc_text()
    for item in ("N4b Phase B", "N4c", "N5b", "A18b"):
        assert item in text, (
            f"carry-forward section missing required item: {item!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins on the doc itself — no secrets, no escalation
# instructions, no copy-paste runtime command for merging
# ---------------------------------------------------------------------------


def test_doc_contains_no_pem_secret_block() -> None:
    """Defense-in-depth: the doc must not embed a real PEM block.
    The forbidden markers are assembled at runtime so the test
    source itself is inert to gitleaks' private-key rule."""
    text = _doc_text()
    dashes = "-" * 5
    pem_kinds = (
        "PRIVATE KEY",
        "EC PRIVATE KEY",
        "RSA PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
    )
    for kind in pem_kinds:
        marker = f"{dashes}BEGIN {kind}{dashes}"
        assert marker not in text, (
            f"doc embeds a PEM secret block marker: {marker!r}"
        )


def test_doc_contains_no_literal_hex_secret_in_backticks() -> None:
    """A 64-char hex run inside backticks looks like a sample
    ``openssl rand -hex 32`` output. The doc must show how to
    *think* about secrets, not embed one."""
    text = _doc_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"doc embeds a hex-64 literal that looks like a secret: {matches!r}"
    )


def test_doc_contains_no_pat_or_bearer_token_shapes() -> None:
    """The doc must not embed a GitHub PAT prefix, an
    Anthropic-shaped key, or a long-form Bearer header value."""
    text = _doc_text()
    # PAT prefix shapes built at runtime.
    forbidden_prefixes = (
        "g" + "h" + "p_",
        "g" + "i" + "thub_pat_",
        "s" + "k-" + "ant-",
    )
    for prefix in forbidden_prefixes:
        # Allow the prefix to appear inside an inline-code block
        # labelled as 'forbidden' — but only inside the body of a
        # negative-example sentence, not as a literal followed by
        # 36+ alphanum chars (a real token).
        rx = re.compile(re.escape(prefix) + r"[A-Za-z0-9_]{20,}")
        assert not rx.search(text), (
            f"doc embeds a token-shaped literal with prefix {prefix!r}"
        )


def test_doc_does_not_instruct_disabling_step5_or_level6() -> None:
    text = _doc_text().lower()
    forbidden_imperatives = [
        "set step5_implementation_allowed to true",
        "step5_implementation_allowed = true",
        'step5_enabled_substage = "5.1"',
        'step5_enabled_substage = "5.2"',
        "enable level 6",
        "skip replay",
        "skip binding check",
        "skip token verification",
        "bypass branch protection",
        "with --admin",
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"doc contains a forbidden authority-escalation phrase: {phrase!r}"
        )


def test_doc_does_not_instruct_touching_no_touch_paths() -> None:
    """The doc must not instruct the reader to *edit* no-touch
    governance surfaces. Negative mentions ('must not touch
    .claude') are fine and required; imperative 'edit / modify'
    of those paths is forbidden."""
    text = _doc_text().lower()
    forbidden_imperatives = [
        "edit .claude",
        "modify .claude",
        "write to .claude",
        "edit .gitleaks.toml",
        "weaken .gitleaks.toml",
        "edit seed.jsonl",
        "modify seed.jsonl",
        "write to seed.jsonl",
        "edit generated_seed.jsonl",
        "modify generated_seed.jsonl",
        "write to generated_seed.jsonl",
        "edit delegation_seed.jsonl",
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"doc contains a forbidden imperative-edit phrase: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Source-scan guards — this PR is doc-only; no runtime adapter
# may be smuggled in alongside the plan-doc.
# ---------------------------------------------------------------------------


# Directories scanned for runtime code. Tests + docs are skipped
# because the plan-doc and its tests legitimately discuss the
# forbidden patterns. Everything else under these roots is
# production-or-CI surface that must remain free of new merge
# adapter code.
_RUNTIME_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "dashboard",
    REPO_ROOT / "reporting",
    REPO_ROOT / "scripts",
    REPO_ROOT / ".github" / "workflows",
)


def _runtime_source_paths() -> list[Path]:
    paths: list[Path] = []
    for root in _RUNTIME_DIRS:
        if not root.is_dir():
            continue
        for child in root.rglob("*"):
            if not child.is_file():
                continue
            # Skip pycache / build artefacts.
            if "__pycache__" in child.parts:
                continue
            # Only scan source-shaped files.
            if child.suffix not in (".py", ".sh", ".yml", ".yaml"):
                continue
            paths.append(child)
    return paths


def _excerpt_around(text: str, idx: int, span: int = 80) -> str:
    """Return a small bounded excerpt around an index for nicer
    failure messages — never the whole file content."""
    start = max(0, idx - span)
    end = min(len(text), idx + span)
    return text[start:end]


#: Allowlist of N5b-adapter module paths that are explicitly
#: permitted by the operator. The list grows one path at a time
#: per sub-unit, narrowing the "no module exists" pin without
#: weakening its closed semantics.
#:
#: * B2.8b added ``dashboard/api_merge_execution_dry_run.py`` (the
#:   skeleton blueprint).
#: * B2.8c added ``reporting/n5b_merge_execution_dry_run.py`` (the
#:   preflight-only audit projector the walker calls).
#:
#: Subsequent sub-units (B2.8d / B2.8e) may extend this allowlist
#: by appending one further operator-approved path per PR; they
#: must never widen the glob set or remove paths.
_ALLOWED_N5B_ADAPTER_MODULES: tuple[str, ...] = (
    "dashboard/api_merge_execution_dry_run.py",
    "reporting/n5b_merge_execution_dry_run.py",
    # B2.9c — Phase 3 recorded-fixture simulator route module.
    "dashboard/api_merge_execution_simulate.py",
    # B2.9b — Phase 3 recorded-fixture simulator projector.
    "reporting/n5b_merge_execution_simulate.py",
)


def test_no_new_merge_execution_adapter_module_exists() -> None:
    """Originally a hard 'no module exists' pin; **narrowed by
    B2.8b** to allow exactly the operator-approved skeleton
    blueprint at
    ``dashboard/api_merge_execution_dry_run.py``. Any other
    file matching the forbidden globs in ``dashboard/`` or
    ``reporting/`` still fails the test.

    Subsequent sub-units (B2.8c / B2.8d / B2.8e) may extend
    ``_ALLOWED_N5B_ADAPTER_MODULES`` by appending one further
    operator-approved path per PR. They must never widen the
    glob set or remove paths."""
    dashboard_dir = REPO_ROOT / "dashboard"
    reporting_dir = REPO_ROOT / "reporting"
    forbidden_module_globs = [
        "api_n5b_*.py",
        "api_*merge_execution*.py",
        "api_*merge_adapter*.py",
        "n5b_*.py",
        "*merge_execution*.py",
        "*merge_adapter*.py",
    ]
    hits: list[str] = []
    for d in (dashboard_dir, reporting_dir):
        if not d.is_dir():
            continue
        for pat in forbidden_module_globs:
            for p in d.rglob(pat):
                rel = p.relative_to(REPO_ROOT).as_posix()
                if rel in _ALLOWED_N5B_ADAPTER_MODULES:
                    continue
                hits.append(rel)
    assert not hits, (
        "PR introduced a runtime N5b adapter module outside the "
        "operator-approved allowlist "
        f"{_ALLOWED_N5B_ADAPTER_MODULES!r}: {hits!r}. "
        "Adding a new path requires an explicit operator-go and "
        "an updated allowlist in the same PR."
    )


def test_no_gh_pr_merge_invocation_in_runtime_code() -> None:
    """No new ``gh pr merge`` shell-out in production surfaces.

    We only flag the literal when it co-occurs with a subprocess
    attribute name or an ``os.system`` shell-out on the SAME
    line. Existing reporting modules already carry the literal
    inside deny-lists / event vocabularies (e.g. an audit
    policy enumerating commands that must NOT be run). Those are
    legitimate one-per-line string entries, not invocations.

    Forbidden literals + invocation attribute names are
    assembled from constituent parts so this test file itself
    is inert to grep/scanners.
    """
    forbidden_literal = "g" + "h " + "pr " + "merge"
    invoker_attrs = (
        "s" + "u" + "bprocess.run",
        "s" + "u" + "bprocess.Popen",
        "s" + "u" + "bprocess.call",
        "s" + "u" + "bprocess.check_call",
        "s" + "u" + "bprocess.check_output",
        "o" + "s.system",
        "o" + "s.popen",
    )
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if forbidden_literal not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if forbidden_literal not in line:
                continue
            if any(attr in line for attr in invoker_attrs):
                hits.append(
                    (
                        str(path.relative_to(REPO_ROOT)),
                        f"L{lineno}: {line.strip()[:160]}",
                    )
                )
    assert not hits, (
        f"runtime source invokes '{forbidden_literal}' via subprocess / "
        f"os.system on a single line — N5b execution adapter must be a "
        f"separate authorised PR. Hits: {hits!r}"
    )


def test_no_git_merge_against_main_in_runtime_code() -> None:
    """No new ``git merge`` shell-out in production surfaces.
    Note the deploy script's ``git fetch + reset --hard origin/main``
    is a checkout refresh, not a merge — that pattern is allowed
    and lives elsewhere."""
    forbidden_literal = "g" + "it " + "merge"
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        idx = text.find(forbidden_literal)
        if idx >= 0:
            hits.append(
                (
                    str(path.relative_to(REPO_ROOT)),
                    _excerpt_around(text, idx),
                )
            )
    assert not hits, (
        f"runtime source contains '{forbidden_literal}' shell-out: {hits!r}"
    )


def test_no_subprocess_pr_mutation_in_runtime_code() -> None:
    """No subprocess invocation of a PR-mutation command in
    production code paths.

    We flag a line only when BOTH the subprocess attribute name
    AND a PR-merge token appear on the SAME line. The reporting
    modules already keep PR-merge event names (e.g.
    ``pr_merge_approved``) and forbidden-pattern strings in
    closed vocabularies — those are file-level co-occurrences but
    not line-level, and they are legitimate audit / event names.
    """
    subprocess_attr = "s" + "u" + "bprocess"
    pr_merge_tokens = (
        "p" + "r merge",
        "p" + "r_merge",
        "merge" + "Pull" + "Request",
    )
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if subprocess_attr not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if subprocess_attr not in line:
                continue
            for tok in pr_merge_tokens:
                if tok in line:
                    hits.append(
                        (
                            str(path.relative_to(REPO_ROOT)),
                            f"L{lineno}: {line.strip()[:160]}",
                        )
                    )
                    break
    assert not hits, (
        f"runtime source has a single-line subprocess+PR-merge "
        f"pairing: {hits!r}"
    )


#: Allowlist of runtime source files that are explicitly
#: permitted to contain the ``/api/agent-control/merge-execution``
#: route prefix. The list grows one path at a time per sub-unit,
#: narrowing the "no endpoint in runtime code" pin without
#: weakening its closed semantics. As of B2.8b the only allowed
#: file is the Phase 2 dry-run skeleton blueprint.
_ALLOWED_MERGE_EXECUTION_ROUTE_FILES: tuple[str, ...] = (
    "dashboard/api_merge_execution_dry_run.py",
    # B2.9c — Phase 3 simulator route module (different route
    # URL, same /api/agent-control/merge-execution prefix).
    "dashboard/api_merge_execution_simulate.py",
)


def test_no_new_merge_execution_endpoint_in_runtime_code() -> None:
    """Originally a hard 'no route URL in runtime' pin;
    **narrowed by B2.8b** to allow exactly the operator-approved
    skeleton blueprint to carry the
    ``/api/agent-control/merge-execution`` route prefix. Any
    other runtime source file that mentions the prefix still
    fails the test.

    Subsequent sub-units may extend
    ``_ALLOWED_MERGE_EXECUTION_ROUTE_FILES`` by appending one
    further operator-approved file per PR. They must never
    widen the prefix scan or remove files."""
    forbidden_route_prefix = "/api/agent-control/merge-execution"
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _ALLOWED_MERGE_EXECUTION_ROUTE_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        idx = text.find(forbidden_route_prefix)
        if idx >= 0:
            hits.append((rel, _excerpt_around(text, idx)))
    assert not hits, (
        "runtime source registers a /merge-execution route outside "
        "the operator-approved allowlist "
        f"{_ALLOWED_MERGE_EXECUTION_ROUTE_FILES!r}: {hits!r}. "
        "Adding a new file requires an explicit operator-go and "
        "an updated allowlist in the same PR."
    )


# ---------------------------------------------------------------------------
# Cross-reference sanity — the cross-referenced governance docs exist
# ---------------------------------------------------------------------------


def test_cross_referenced_docs_exist() -> None:
    referenced = [
        REPO_ROOT / "docs" / "governance" / "development_merge_recommendation.md",
        REPO_ROOT / "docs" / "governance" / "approval_token_gate.md",
        REPO_ROOT / "docs" / "governance" / "n4b_runtime_activation.md",
        REPO_ROOT / "docs" / "governance" / "vps_deploy.md",
        REPO_ROOT / "docs" / "governance" / "no_touch_paths.md",
        REPO_ROOT / "docs" / "governance" / "execution_authority.md",
    ]
    missing = [p for p in referenced if not p.is_file()]
    assert not missing, (
        f"N5b plan-doc cross-references missing files: {missing!r}"
    )


# ---------------------------------------------------------------------------
# Phase 3 sub-plan back-pointer (added by B2.9a)
# ---------------------------------------------------------------------------


def test_parent_doc_has_phase3_sub_plan_back_pointer() -> None:
    """B2.9a adds a §14 cross-reference to the Phase 3
    sub-plan. This pin asserts the back-pointer survives any
    future doc edit."""
    text = _doc_text()
    assert "n5b_phase3_implementation_plan.md" in text, (
        "parent doc must include a back-pointer to "
        "n5b_phase3_implementation_plan.md (added by B2.9a)"
    )


def test_parent_doc_phase3_section_declares_recorded_fixture_path() -> None:
    """The §14 Phase 3 sub-plan reference must declare the
    recorded-fixture simulator as the selected path and the
    sacrificial-GitHub-repository path as rejected."""
    text = _doc_text().lower()
    assert "recorded-fixture simulator" in text, (
        "parent doc §14 must reference the recorded-fixture simulator"
    )
    # The rejection of the sacrificial repo path must appear.
    assert "rejected" in text, (
        "parent doc §14 must mark the sacrificial-GitHub-repository "
        "path as rejected"
    )


def test_parent_doc_phase3_section_declares_phase_4_denied_for_ade() -> None:
    """The §14 Phase 3 sub-plan reference must record the
    Phase 4 permanently-denied-for-ADE doctrine."""
    text = _doc_text().lower()
    assert "phase 4" in text
    assert "permanently denied" in text or "permanently-denied" in text, (
        "parent doc §14 must declare Phase 4 production-merge "
        "permanently denied for ADE"
    )
