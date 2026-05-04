#!/usr/bin/env bash
# scripts/deploy_vps_dashboard.sh
#
# Audited VPS deploy for the JvR Trading Agent dashboard surface.
# v3.15.15.29 — automatic deploy on main merge.
#
# WHAT THIS DEPLOYS:
#   * dashboard service (Flask app + Agent Control PWA)
#   * nginx service (reverse proxy)
#
# WHAT THIS DOES NOT DEPLOY / START:
#   * agent service (the autonomous trading worker)
#   * discovery / research worker
#
# Why the safe compose pattern:
#   ``docker compose up -d --build dashboard nginx`` previously
#   caused the ``agent`` service to be rebuilt/recreated/started
#   via compose's depends_on / dependency resolution. The pattern
#   below is the safe one:
#
#     docker compose build dashboard
#     docker compose up -d --no-deps dashboard nginx
#     docker compose stop agent || true
#
#   ``--no-deps`` prevents compose from touching the agent service
#   even if dashboard declares depends_on. The trailing ``stop
#   agent`` is a defense-in-depth guarantee that even if a future
#   compose reorganisation forgets ``--no-deps``, the agent does
#   not silently start.
#
# Hard guarantees:
#   * No live / paper / shadow / trading / risk action.
#   * No free-form command input. The script accepts no arguments.
#   * No secrets read or echoed.
#   * No api_execute_safe_controls wiring.
#   * No browser push.
#   * Idempotent: re-running is safe.

set -euo pipefail

REPO_ROOT="/root/trading-agent"
DASHBOARD_HEALTH_URL="http://127.0.0.1:8050/agent-control"
COMPOSE="docker compose"

log() {
    # Plain stdout; never echo secrets.
    printf '[deploy_vps_dashboard] %s\n' "$*"
}

# Refuse to run with arguments — keeps the surface intentionally
# narrow. The workflow invokes this script bare.
if [[ "$#" -gt 0 ]]; then
    log "refused: this script accepts no arguments (got $#)"
    exit 2
fi

if [[ ! -d "${REPO_ROOT}" ]]; then
    log "fatal: ${REPO_ROOT} does not exist on this host"
    exit 3
fi

cd "${REPO_ROOT}"

log "step 1/6: fetch latest origin/main"
git fetch origin main

log "step 2/6: hard-reset working tree to origin/main"
git reset --hard origin/main

log "step 3/6: build dashboard image (only)"
${COMPOSE} build dashboard

log "step 4/6: bring dashboard + nginx up with --no-deps"
# --no-deps is the critical flag. It tells compose to NOT touch
# any service the named services depend on. Combined with the
# explicit list (dashboard nginx), this means agent stays as it
# was — typically stopped.
${COMPOSE} up -d --no-deps dashboard nginx

log "step 5/6: explicit defense-in-depth stop of agent"
# This is intentional. We do NOT want the agent to be running on
# the VPS by default; live trading is operator-gated. The ``|| true``
# is defensive — if the service is already stopped or not in the
# compose file, this is not a fatal error.
${COMPOSE} stop agent || true

log "step 6/6: verify cluster state"
${COMPOSE} ps

# Verification: dashboard must be Up.
if ! ${COMPOSE} ps --status running --services | grep -qx dashboard; then
    log "fatal: dashboard service did not reach running state"
    ${COMPOSE} logs --tail=120 dashboard || true
    exit 4
fi

# Verification: agent must NOT be Up. We log + fail loudly so
# the workflow surfaces the regression in the deploy run.
if ${COMPOSE} ps --status running --services | grep -qx agent; then
    log "fatal: agent service is unexpectedly running after deploy"
    ${COMPOSE} logs --tail=120 agent || true
    exit 5
fi

log "verifying dashboard responds on ${DASHBOARD_HEALTH_URL}"
# A short retry loop covers the seconds while nginx / Flask warm
# up. We hit /agent-control because the standalone PWA route is
# the operator-facing surface and is guaranteed to be wired.
#
# v3.15.15.29.2: the healthcheck is auth-aware. /agent-control
# is wrapped in <RequireAuth> on the SPA side and the Flask
# layer requires a session cookie. An anonymous request from
# the deploy job therefore receives one of:
#
#   200  — fully served (only happens if the host's session
#          cookies are present, e.g. during a manual run from
#          a logged-in shell)
#   302  — redirected (auth redirect, or trailing-slash redirect)
#   401  — authenticated endpoint rejects the anonymous request
#
# All three prove the Flask app is alive AND the auth layer is
# active. Anything else (no response, 5xx, 404, unexpected
# status) is a real failure. We capture the status code with
# %{http_code} instead of using curl --fail so a 401 does not
# trip the script. We never embed credentials and never bypass
# auth.
http_ok=0
last_status=""
for attempt in 1 2 3 4 5; do
    # ``|| true`` so a transport-level failure (no response at
    # all) just yields an empty status; the if-block below
    # treats that as "not yet alive" and retries.
    last_status="$(curl -sS -o /dev/null -w '%{http_code}' \
        --max-time 5 "${DASHBOARD_HEALTH_URL}" || true)"
    case "${last_status}" in
        200|302|401)
            http_ok=1
            log "dashboard responded with HTTP ${last_status}; treating as alive (\
/agent-control is auth-protected)"
            break
            ;;
        *)
            log "attempt ${attempt}/5: dashboard not alive yet (status=\
${last_status:-no_response}), sleeping 3s"
            sleep 3
            ;;
    esac
done

if [[ "${http_ok}" -ne 1 ]]; then
    log "fatal: dashboard did not respond on ${DASHBOARD_HEALTH_URL} \
(last status=${last_status:-no_response})"
    ${COMPOSE} logs --tail=120 dashboard || true
    exit 6
fi

log "deploy ok: dashboard + nginx running, agent stopped"
exit 0
