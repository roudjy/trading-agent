"""Static-guard invariants for the v3.15.15.29 VPS dashboard deploy.

These tests are pure source-text checks. They never run the
deploy script and never make a network call. The point is to
make every safety-critical decision in
``scripts/deploy_vps_dashboard.sh`` and
``.github/workflows/deploy-vps-dashboard.yml`` re-checkable on
every PR — a future regression that softens the dashboard-only
deploy contract trips a unit-test failure rather than waiting
for a runtime incident on the VPS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy_vps_dashboard.sh"
WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "deploy-vps-dashboard.yml"
)
DOC_PATH = REPO_ROOT / "docs" / "governance" / "vps_deploy.md"


# ---------------------------------------------------------------------------
# Files exist
# ---------------------------------------------------------------------------


def test_deploy_script_exists() -> None:
    assert SCRIPT_PATH.exists(), f"missing: {SCRIPT_PATH}"


def test_workflow_exists() -> None:
    assert WORKFLOW_PATH.exists(), f"missing: {WORKFLOW_PATH}"


def test_runbook_exists() -> None:
    assert DOC_PATH.exists(), f"missing: {DOC_PATH}"
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "v3.15.15.29" in text


# ---------------------------------------------------------------------------
# Deploy script invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_script_has_strict_bash_options(script_text: str) -> None:
    assert "set -euo pipefail" in script_text


def test_script_uses_compose_build_dashboard_only(script_text: str) -> None:
    """The safe build pattern: build the dashboard image WITHOUT
    forcing a recreate of any other service."""
    assert "docker compose build dashboard" in script_text or (
        "${COMPOSE} build dashboard" in script_text
        and 'COMPOSE="docker compose"' in script_text
    )


def test_script_uses_compose_up_no_deps_dashboard_nginx(script_text: str) -> None:
    """``--no-deps`` is the critical flag that prevents compose
    from touching the agent service via ``depends_on``
    resolution.

    v3.15.15.29.3: the canonical form is now
    ``up -d --no-deps --force-recreate dashboard nginx`` so
    nginx is rebuilt and re-resolves the dashboard upstream.
    The legacy form (no force-recreate) is still accepted by
    this test so the invariant remains "uses --no-deps for the
    up command, with both dashboard and nginx in the same
    invocation".
    """
    accepted = [
        "docker compose up -d --no-deps --force-recreate dashboard nginx",
        "${COMPOSE} up -d --no-deps --force-recreate dashboard nginx",
        "docker compose up -d --no-deps dashboard nginx",
        "${COMPOSE} up -d --no-deps dashboard nginx",
    ]
    assert any(p in script_text for p in accepted), (
        "script does not use any accepted '--no-deps dashboard nginx' "
        "compose-up form"
    )


def test_script_force_recreates_nginx_after_dashboard_rebuild(
    script_text: str,
) -> None:
    """v3.15.15.29.3 fix: when dashboard is rebuilt, the new
    container gets a new internal IP. nginx (already Running)
    is left alone by ``up -d --no-deps`` and keeps its stale
    upstream → every /agent-control request 502s.

    The deploy must explicitly refresh nginx. Three accepted
    patterns:

      A) ``up -d --no-deps --force-recreate dashboard nginx``
         (single command, recreates both — preferred)
      B) ``up -d --no-deps --force-recreate nginx`` after the
         dashboard up
      C) ``restart nginx`` after the dashboard up

    Anything else is a regression that lets the 502 mode return.
    """
    pattern_a = (
        "--no-deps --force-recreate dashboard nginx" in script_text
        or "--force-recreate --no-deps dashboard nginx" in script_text
    )
    pattern_b = (
        "--no-deps --force-recreate nginx" in script_text
        or "--force-recreate --no-deps nginx" in script_text
    )
    pattern_c = (
        "compose restart nginx" in script_text
        or "${COMPOSE} restart nginx" in script_text
    )
    assert pattern_a or pattern_b or pattern_c, (
        "deploy script does not explicitly refresh nginx after the "
        "dashboard rebuild; the v3.15.15.29.3 502 regression mode "
        "would re-emerge"
    )


def test_script_explicitly_stops_agent(script_text: str) -> None:
    """Defense-in-depth: even if a future compose reorganisation
    forgets ``--no-deps``, the agent must be stopped after deploy."""
    assert (
        "docker compose stop agent" in script_text
        or "${COMPOSE} stop agent" in script_text
    )


def test_script_does_not_use_forbidden_up_build_pattern(
    script_text: str,
) -> None:
    """The forbidden pattern that previously caused the agent
    service to be rebuilt/recreated/started: ``docker compose
    up -d --build dashboard nginx``. Any variant of
    ``up -d --build`` is rejected.

    The script's safety-policy COMMENT explains why this pattern
    is forbidden, so the literal phrase appears legitimately in
    a comment. We only scan executable (non-comment) lines.
    """
    forbidden_patterns = [
        "docker compose up -d --build dashboard nginx",
        "docker compose up -d --build dashboard",
        "docker compose up --build dashboard nginx",
        "${COMPOSE} up -d --build dashboard nginx",
    ]
    executable_lines = [
        ln for ln in script_text.splitlines() if not ln.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)
    for pat in forbidden_patterns:
        assert pat not in executable, (
            f"deploy script (executable lines only) contains "
            f"forbidden pattern: {pat!r}"
        )


def test_script_refuses_arguments(script_text: str) -> None:
    """Narrow-by-design: the script must refuse any positional
    argument so the workflow cannot accidentally pass arbitrary
    operator input."""
    assert '"$#"' in script_text or "$#" in script_text
    assert "exit 2" in script_text


def test_script_verifies_dashboard_running(script_text: str) -> None:
    """The script must fail loudly if dashboard did not reach
    running state."""
    assert "ps --status running --services" in script_text
    assert "grep -qx dashboard" in script_text


def test_script_healthcheck_captures_http_status_code(
    script_text: str,
) -> None:
    """v3.15.15.29.2: the dashboard healthcheck captures the HTTP
    status with ``%{http_code}`` instead of using ``curl --fail``.
    The previous form treated 401 as failure, but 401 is the
    expected response from /agent-control (auth-protected) and
    proves the Flask app + auth layer are alive."""
    assert "%{http_code}" in script_text


def test_script_healthcheck_does_not_use_curl_fail(
    script_text: str,
) -> None:
    """``curl --fail`` (or ``-f``) collapses 4xx/5xx into exit
    code 22, which prevents the script from distinguishing 401
    (auth-alive) from 5xx (server down). The auth-aware version
    must NOT use ``--fail``/``-f`` against /agent-control."""
    # The forbidden flags. We allow ``-sS`` (silent + show errors
    # on transport failure), ``-o``, ``-w``, and ``--max-time``.
    executable_lines = [
        ln for ln in script_text.splitlines() if not ln.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)
    forbidden = [
        "curl -sSf",
        "curl -fsS",
        "curl -f",
        "curl --fail",
    ]
    for f in forbidden:
        assert f not in executable, (
            f"deploy script (executable lines) uses forbidden curl flag: {f!r}"
        )


def test_script_healthcheck_accepts_200_302_401(script_text: str) -> None:
    """The auth-aware healthcheck must accept 200, 302, and 401
    as alive. Each must appear as an accepted status in the
    case statement that gates the retry loop."""
    # A robust check: each accepted status must appear, and they
    # must appear together as a case-pattern alternation
    # (``200|302|401)`` — no scattered references that may not be
    # in the case-arm.
    assert re.search(r"200\s*\|\s*302\s*\|\s*401\b", script_text), (
        "script does not declare 200|302|401 as the accepted "
        "alive case for /agent-control"
    )


def test_script_healthcheck_logs_accepted_status(script_text: str) -> None:
    """When the healthcheck accepts a status, the script must log
    which status it accepted so the operator can see (in the
    workflow log) that 401 was the expected response, not a
    silent skip."""
    # The script logs ``dashboard responded with HTTP <status>``.
    assert "dashboard responded with HTTP" in script_text


def test_script_verifies_agent_not_running(script_text: str) -> None:
    """The script must fail loudly if agent is still running."""
    assert "grep -qx agent" in script_text
    # The check for agent running must be a fatal exit.
    assert re.search(r"unexpectedly running.*\n.*exit\s+5", script_text, re.DOTALL) or (
        "exit 5" in script_text
    )


def test_script_does_not_embed_secrets_or_hosts(script_text: str) -> None:
    """The script must not contain literal IPs, tokens, or
    private-key headers. The VPS hostname only appears as a
    constant repo path; the deploy URL is localhost."""
    forbidden_substrings = [
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
        "BEGIN PRIVATE KEY",
        "ssh-rsa AAAA",
        "ssh-ed25519 AAAA",
        "ghp_",
        "github_pat_",
        "sk-ant-",
        "AKIA",
    ]
    for tok in forbidden_substrings:
        assert tok not in script_text, f"script contains forbidden token: {tok!r}"
    # No hard-coded VPS IP. The only IP literal allowed is loopback.
    # Lookbehind ``(?<![\w.])`` prevents matching a 4-octet
    # subsequence inside a longer dotted string like the version
    # tag ``v3.15.15.26.2`` (contains ``15.15.26.2``) or
    # ``v3.15.15.29`` (contains ``3.15.15.29``). Lookahead
    # ``(?![.\d])`` prevents matching a 4-octet prefix of a 5+
    # component string.
    ip_re = re.compile(
        r"(?<![\w.])(?!127\.0\.0\.1\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    matches = ip_re.findall(script_text)
    assert matches == [], (
        f"deploy script contains a non-loopback IP literal: {matches!r}"
    )


# ---------------------------------------------------------------------------
# Workflow invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_triggers_on_gate_success_or_dispatch(
    workflow_text: str,
) -> None:
    """v3.15.16.N5b1 — the trigger surface is exactly
    ``workflow_run`` after the "Fast pre-merge gate" completes on
    ``main``, plus an operator-only ``workflow_dispatch`` for
    manual deploys. The legacy ``push:`` trigger has been removed
    so a direct push to ``main`` (bypassing the gate) cannot
    auto-deploy. ``pull_request`` is still explicitly absent."""
    # workflow_run trigger:
    assert "workflow_run:" in workflow_text, (
        "workflow must use workflow_run as the auto-deploy trigger"
    )
    assert 'workflows: ["Fast pre-merge gate"]' in workflow_text, (
        "workflow_run must reference the exact 'Fast pre-merge gate' "
        "workflow name"
    )
    assert "types: [completed]" in workflow_text, (
        "workflow_run must subscribe to the 'completed' type "
        "(branch filter + if: guard further restrict to success-on-main)"
    )
    assert "branches: [main]" in workflow_text, (
        "workflow_run must restrict to the main branch only"
    )

    # workflow_dispatch trigger:
    assert "workflow_dispatch:" in workflow_text, (
        "workflow must expose a workflow_dispatch surface for "
        "operator-initiated manual deploys"
    )

    # Legacy push trigger explicitly removed:
    assert not re.search(
        r"^\s*push:\s*\n\s*branches:", workflow_text, re.MULTILINE
    ), (
        "legacy push-to-main trigger must be removed — the "
        "workflow_run trigger is the canonical auto-deploy path"
    )


def test_workflow_only_deploys_on_successful_gate_or_dispatch(
    workflow_text: str,
) -> None:
    """The deploy job must guard against running on a failed gate
    run. Without this guard, ``workflow_run`` would fire on every
    gate completion including failures."""
    # The if-guard must include the conclusion check.
    assert (
        "github.event.workflow_run.conclusion == 'success'"
        in workflow_text
    ), (
        "deploy job must guard on workflow_run.conclusion == 'success' "
        "so a failed gate run cannot trigger a deploy"
    )
    # The if-guard must also allow workflow_dispatch through.
    assert "workflow_dispatch" in workflow_text, (
        "deploy job must allow workflow_dispatch as the operator "
        "manual-deploy path through its if-guard"
    )


def test_workflow_does_not_trigger_on_pull_request(workflow_text: str) -> None:
    """A pull_request trigger would deploy unmerged code. Refuse
    any variant."""
    forbidden = ["pull_request:", "pull_request_target:"]
    for tok in forbidden:
        assert tok not in workflow_text, (
            f"workflow contains forbidden trigger: {tok!r}"
        )


def test_workflow_uses_required_secrets(workflow_text: str) -> None:
    """The three repository secrets the workflow consumes.

    v3.15.16.N5b1 renamed ``VPS_SSH_KEY`` → ``VPS_SSH_PRIVATE_KEY``
    so the secret name self-documents that it carries the *private*
    key material (and the operator does not confuse it with the
    deploy *public* key that lives on the VPS authorized_keys)."""
    assert "${{ secrets.VPS_HOST }}" in workflow_text
    assert "${{ secrets.VPS_USER }}" in workflow_text
    assert "${{ secrets.VPS_SSH_PRIVATE_KEY }}" in workflow_text
    # The legacy name must not linger anywhere in the workflow,
    # otherwise the operator could mis-set the GitHub secret and
    # get a confusing "missing secrets" failure later.
    assert "VPS_SSH_KEY" not in workflow_text, (
        "legacy secret name VPS_SSH_KEY must not appear in the "
        "workflow — it was renamed to VPS_SSH_PRIVATE_KEY"
    )


def test_workflow_has_concurrency_group(workflow_text: str) -> None:
    """Two deploys must not race; the in-flight deploy must not be
    cancelled mid-flight."""
    assert "concurrency:" in workflow_text
    assert "group: deploy-vps-dashboard" in workflow_text
    assert "cancel-in-progress: false" in workflow_text


def test_workflow_has_timeout_minutes(workflow_text: str) -> None:
    """A bounded timeout prevents a hung SSH from burning a
    runner-hour."""
    m = re.search(r"timeout-minutes:\s*(\d+)", workflow_text)
    assert m, "workflow does not declare timeout-minutes"
    minutes = int(m.group(1))
    assert 1 <= minutes <= 60, f"workflow timeout-minutes ({minutes}) out of sane range"


def test_workflow_does_not_embed_secrets_or_hosts(workflow_text: str) -> None:
    """No literal private-key material, tokens, IPs, or
    passwords."""
    forbidden_substrings = [
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
        "BEGIN PRIVATE KEY",
        "ssh-rsa AAAA",
        "ssh-ed25519 AAAA",
        "ghp_",
        "github_pat_",
        "sk-ant-",
        "AKIA",
        "password:",
        "PASSWORD=",
    ]
    for tok in forbidden_substrings:
        assert tok not in workflow_text, f"workflow contains forbidden token: {tok!r}"
    # No hard-coded IP literal. Same boundary tightening as the
    # script-level test: lookbehind+lookahead reject 4-octet
    # subsequences inside longer dotted strings like a release
    # tag (``v3.15.15.29.1`` contains ``15.15.29.1``).
    ip_re = re.compile(
        r"(?<![\w.])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    matches = ip_re.findall(workflow_text)
    assert matches == [], (
        f"workflow contains an IP literal (must come from secrets): {matches!r}"
    )


def test_workflow_invokes_safe_deploy_script(workflow_text: str) -> None:
    """The deploy work must run via the audited script, not
    inline."""
    assert "scripts/deploy_vps_dashboard.sh" in workflow_text


def test_workflow_bootstraps_repo_on_vps_before_running_script(
    workflow_text: str,
) -> None:
    """v3.15.15.29.1 first-run fix: the workflow's SSH command
    must perform ``git fetch origin main`` and
    ``git reset --hard origin/main`` BEFORE invoking
    ``bash scripts/deploy_vps_dashboard.sh``. Otherwise on a
    stale VPS checkout the script file does not exist yet and
    the deploy fails with exit code 127."""
    assert "git fetch origin main" in workflow_text
    assert "git reset --hard origin/main" in workflow_text


def test_workflow_bootstrap_runs_before_script_invocation(
    workflow_text: str,
) -> None:
    """The bootstrap commands must precede the script call in
    the workflow text. We allow them to live on the same SSH
    line (chained with ``&&``) or in separate prior steps; the
    invariant is just ordering."""
    fetch_idx = workflow_text.find("git fetch origin main")
    reset_idx = workflow_text.find("git reset --hard origin/main")
    script_idx = workflow_text.find("bash scripts/deploy_vps_dashboard.sh")
    assert fetch_idx >= 0, "workflow does not run git fetch origin main"
    assert reset_idx >= 0, "workflow does not run git reset --hard origin/main"
    assert script_idx >= 0, "workflow does not invoke bash scripts/deploy_vps_dashboard.sh"
    assert fetch_idx < script_idx, (
        "git fetch origin main must precede the script invocation"
    )
    assert reset_idx < script_idx, (
        "git reset --hard origin/main must precede the script invocation"
    )


def test_workflow_does_not_use_forbidden_compose_pattern(
    workflow_text: str,
) -> None:
    """The workflow itself must not paste the unsafe up-build
    pattern. The deploy script enforces this on the VPS, but
    the workflow is also a source of truth."""
    forbidden_patterns = [
        "docker compose up -d --build dashboard nginx",
        "docker compose up -d --build dashboard",
    ]
    for pat in forbidden_patterns:
        assert pat not in workflow_text, (
            f"workflow contains forbidden compose pattern: {pat!r}"
        )


def test_workflow_actions_are_sha_pinned(workflow_text: str) -> None:
    """Every ``uses:`` reference must be SHA-pinned (40 hex
    chars). This matches the repo-wide governance lint policy."""
    uses_re = re.compile(r"uses:\s*([^\s#]+)")
    for line_match in uses_re.finditer(workflow_text):
        ref = line_match.group(1)
        # The action ref must include a 40-char hex SHA, e.g.
        # ``actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11``.
        assert re.search(r"@[0-9a-f]{40}\b", ref), (
            f"workflow uses non-SHA-pinned action: {ref!r}"
        )


def test_workflow_wipes_ssh_artifacts(workflow_text: str) -> None:
    """Defense in depth even though the runner is ephemeral:
    the SSH key file must be removed at end-of-job."""
    assert "rm -f ~/.ssh/deploy_key" in workflow_text


def test_workflow_uses_strict_host_key_checking(workflow_text: str) -> None:
    """The SSH command must NOT disable host key checking."""
    assert "StrictHostKeyChecking=yes" in workflow_text
    assert "StrictHostKeyChecking=no" not in workflow_text


def test_workflow_uses_batch_mode_to_refuse_password_prompts(
    workflow_text: str,
) -> None:
    """``BatchMode=yes`` ensures the SSH client never falls back
    to interactive auth (which would hang a runner)."""
    assert "BatchMode=yes" in workflow_text


# ---------------------------------------------------------------------------
# Cross-file consistency
# ---------------------------------------------------------------------------


def test_runbook_references_required_secrets(workflow_text: str) -> None:
    """The operator runbook must enumerate the secrets the
    workflow consumes so the operator can't miss one during
    setup. The secret name is the v3.15.16.N5b1
    ``VPS_SSH_PRIVATE_KEY`` (legacy name ``VPS_SSH_KEY`` is no
    longer accepted)."""
    text = DOC_PATH.read_text(encoding="utf-8")
    for sec in ("VPS_HOST", "VPS_USER", "VPS_SSH_PRIVATE_KEY"):
        assert sec in text, f"runbook does not document required secret: {sec!r}"


def test_runbook_documents_safe_compose_pattern() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "docker compose build dashboard" in text
    assert "docker compose up -d --no-deps dashboard nginx" in text
    assert "docker compose stop agent" in text


def test_runbook_warns_against_forbidden_pattern() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    # The runbook's "Never use" section must call out the
    # forbidden pattern verbatim so reviewers spot a regression.
    assert "docker compose up -d --build dashboard nginx" in text


def test_no_other_file_references_a_full_vps_ip() -> None:
    """No file we ship in this release contains a non-loopback
    IPv4 literal."""
    # Lookbehind ``(?<![\w.])`` prevents matching a 4-octet
    # subsequence inside a longer dotted string like the version
    # tag ``v3.15.15.26.2`` (contains ``15.15.26.2``) or
    # ``v3.15.15.29`` (contains ``3.15.15.29``). Lookahead
    # ``(?![.\d])`` prevents matching a 4-octet prefix of a 5+
    # component string.
    ip_re = re.compile(
        r"(?<![\w.])(?!127\.0\.0\.1\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    for path in (SCRIPT_PATH, WORKFLOW_PATH, DOC_PATH):
        text = path.read_text(encoding="utf-8")
        matches = ip_re.findall(text)
        assert matches == [], (
            f"{path.name} contains a non-loopback IP literal: {matches!r}"
        )


# ---------------------------------------------------------------------------
# v3.15.15.29.4 — protocol-aware healthcheck invariants
# ---------------------------------------------------------------------------


def test_script_healthcheck_supports_https_with_self_signed_ca(
    script_text: str,
) -> None:
    """The healthcheck curl call must use ``-k`` (or ``--insecure``)
    so the VPS self-signed local CA on the HTTPS variant of port
    8050 does not cause a certificate-verification failure.

    We only scan executable (non-comment) lines so a comment
    explaining why ``-k`` is safe does not satisfy this test on
    its own — the flag must appear in an actual curl invocation.
    """
    executable_lines = [
        ln for ln in script_text.splitlines() if not ln.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)
    assert "curl -k" in executable or "curl --insecure" in executable, (
        "healthcheck curl call does not pass -k / --insecure; "
        "HTTPS with a self-signed local CA will fail"
    )


def test_script_healthcheck_lists_https_and_http_candidates(
    script_text: str,
) -> None:
    """Both the HTTPS and HTTP loopback candidates must appear
    literally in the script so the operator can audit the two
    probe addresses without having to reason about runtime
    string construction."""
    assert "https://127.0.0.1:8050/agent-control" in script_text, (
        "script does not contain HTTPS candidate "
        "https://127.0.0.1:8050/agent-control"
    )
    assert "http://127.0.0.1:8050/agent-control" in script_text, (
        "script does not contain HTTP candidate "
        "http://127.0.0.1:8050/agent-control"
    )


def test_script_healthcheck_honours_env_override(
    script_text: str,
) -> None:
    """The script must expose an operator-level env override so a
    non-standard setup (different port, different path) can be
    accommodated without editing the script.

    Accepted forms:
      * ``${DASHBOARD_HEALTH_URL:-}`` — explicit default-empty
        expansion used to detect whether the var is set.
      * ``${DASHBOARD_HEALTH_URL_OVERRIDE}`` — a local copy that
        the script derives from the env var.
    Either form proves the script reads DASHBOARD_HEALTH_URL from
    the environment.
    """
    assert (
        "${DASHBOARD_HEALTH_URL:-}" in script_text
        or "${DASHBOARD_HEALTH_URL_OVERRIDE}" in script_text
    ), (
        "script does not reference DASHBOARD_HEALTH_URL as an "
        "env-driven override (expected ${DASHBOARD_HEALTH_URL:-} "
        "or ${DASHBOARD_HEALTH_URL_OVERRIDE})"
    )


def test_script_healthcheck_iterates_candidates(
    script_text: str,
) -> None:
    """The healthcheck must iterate over a candidates array so
    both HTTPS and HTTP are tried per retry attempt — a healthy
    HTTP-only deploy must not be delayed by HTTPS timeouts on
    all five attempts before HTTP is even tried.

    Accepted pattern: ``for url in "${DASHBOARD_HEALTH_CANDIDATES[@]}"``
    (or a functionally equivalent iteration over the array).
    """
    assert (
        'for url in "${DASHBOARD_HEALTH_CANDIDATES[@]}"' in script_text
        or "DASHBOARD_HEALTH_CANDIDATES[@]" in script_text
    ), (
        "script does not iterate over DASHBOARD_HEALTH_CANDIDATES[@]; "
        "both HTTPS and HTTP candidates must be tried inside each "
        "retry attempt"
    )
