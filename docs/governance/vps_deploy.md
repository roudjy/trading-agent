# VPS dashboard deploy — operator runbook

Module: `scripts/deploy_vps_dashboard.sh` + `.github/workflows/deploy-vps-dashboard.yml`
Release: v3.15.15.29
Sibling docs: `mobile_agent_control_pwa.md`,
`high_risk_approval_policy.md`, `recurring_maintenance.md`,
`no_touch_paths.md`.

## TL;DR

Every push to `main` automatically deploys the latest dashboard
and nginx surface to the VPS. **The agent / discovery worker is
NOT deployed and is NOT started by this workflow.** Live trading
remains operator-gated.

## What this deploys

| service | role | deployed by this workflow? |
| --- | --- | :---: |
| `dashboard` | Flask app + Agent Control PWA | yes (rebuilt + restarted) |
| `nginx` | reverse proxy | yes (recreated) |
| `agent` | autonomous trading worker | **NO — explicitly stopped after deploy** |
| any other compose service the dashboard `depends_on` | — | **NO — `--no-deps` prevents touch** |

## Hard guarantees encoded in the script

* `set -euo pipefail` — any failed step halts the deploy.
* `docker compose build dashboard` (NOT `up -d --build`) — only
  the dashboard image is rebuilt; the agent image is untouched.
* `docker compose up -d --no-deps dashboard nginx` — the
  `--no-deps` flag tells compose to NOT touch any service the
  named services depend on. Combined with the explicit
  service list, this means the agent is never recreated.
* `docker compose stop agent || true` — defense in depth: even
  if a future compose reorganisation forgets `--no-deps`, the
  agent is explicitly stopped after deploy.
* The script then asserts:
  * `dashboard` is in the running set.
  * `agent` is NOT in the running set.
  * `http://127.0.0.1:8050/agent-control` responds with HTTP 2xx
    within 5 retry attempts (3 s sleep between attempts).
* The script accepts no arguments. There is no free-form
  command surface.

## The forbidden compose pattern

**Never use:**

```
docker compose up -d --build dashboard nginx
```

This previously caused the `agent` service to be rebuilt /
recreated / started via compose's `depends_on` resolution. The
deploy script and the workflow are explicit about NOT using this
pattern, and a static test in `tests/unit/` enforces it.

## Auth-aware healthcheck (v3.15.15.29.2)

The deploy script's final step verifies that the dashboard is
responding on `http://127.0.0.1:8050/agent-control`. That route
is **auth-protected** (wrapped in `<RequireAuth>` on the SPA
side; Flask requires a session cookie), so an anonymous request
from the deploy job receives one of:

| status | meaning | accepted? |
| :---: | --- | :---: |
| 200 | fully served (only when host cookies are present, e.g. manual run from a logged-in shell) | ✅ |
| 302 | auth redirect or trailing-slash redirect | ✅ |
| 401 | authenticated endpoint rejects the anonymous request | ✅ |
| 000 / no response | dashboard not listening / connection refused | ❌ retry |
| 4xx (other) | misrouted | ❌ retry |
| 5xx | dashboard crashed | ❌ retry |
| anything else | unexpected | ❌ retry |

All three accepted statuses prove the Flask app is alive AND the
auth layer is active. The script captures the status code with
`curl ... -w '%{http_code}'` (NOT `curl --fail`) so a 401 does
not collapse to exit 22 and trip the script. The accepted status
is logged so the operator sees in the workflow log that, e.g.,
`HTTP 401` was treated as alive and not as a silent skip.

The script never embeds credentials and never bypasses auth.

## First-run bootstrap (v3.15.15.29.1)

The workflow's SSH command runs:

```
cd /root/trading-agent
git fetch origin main
git reset --hard origin/main
bash scripts/deploy_vps_dashboard.sh
```

The explicit `git fetch` + `git reset --hard` BEFORE the script
invocation is intentional. On the very first deploy the VPS
checkout may be on an older `main` commit that does not yet
contain `scripts/deploy_vps_dashboard.sh`. Without the bootstrap
the SSH command fails with `bash: scripts/deploy_vps_dashboard.sh:
No such file or directory` and exit code 127 (this is exactly
what happened the first time the workflow ran after v3.15.15.29
merged).

The bootstrap is idempotent: the script itself ALSO does
`git fetch` + `git reset --hard origin/main` as its first two
steps. Subsequent deploys do the same work twice (cheap)
rather than skipping the bootstrap.

## Required GitHub secrets

The workflow consumes exactly three repository secrets:

| secret | purpose | where to set |
| --- | --- | --- |
| `VPS_HOST` | hostname or IP of the VPS (the operator already knows it; do NOT paste it into any committed file) | `Repo → Settings → Secrets and variables → Actions → New repository secret` |
| `VPS_USER` | SSH user (typically `root`) | same place |
| `VPS_SSH_KEY` | full private-key contents (PEM) of a dedicated deploy key | same place |

The workflow:

* references each secret via `${{ secrets.* }}` only;
* never echoes secret values;
* writes the private key to `~/.ssh/deploy_key` with `chmod 600`
  on the ephemeral GitHub-hosted runner;
* wipes `~/.ssh/deploy_key` and `~/.ssh/known_hosts` in an
  `if: always()` final step.

## One-time setup: dedicated deploy SSH key

Generate a **new** SSH key dedicated to the deploy workflow.
Do NOT reuse personal keys.

On a workstation (NOT the VPS):

```bash
# Generate the deploy key. ed25519 is small + modern; rsa-4096 is fine too.
ssh-keygen -t ed25519 -f ./deploy_vps_dashboard_key -C "github-actions deploy" -N ""

# Files produced:
#   deploy_vps_dashboard_key       <- private key (goes into VPS_SSH_KEY)
#   deploy_vps_dashboard_key.pub   <- public key (goes onto the VPS)
```

On the VPS, append the public key to the deploy user's
`authorized_keys`:

```bash
# Run as root (or the deploy user) on the VPS:
mkdir -p /root/.ssh
chmod 700 /root/.ssh
cat >> /root/.ssh/authorized_keys <<'EOF'
<contents of deploy_vps_dashboard_key.pub>
EOF
chmod 600 /root/.ssh/authorized_keys
```

Back on the workstation, add the **private** key as a GitHub
secret:

1. Open `Repo → Settings → Secrets and variables → Actions`.
2. Add `VPS_SSH_KEY` with the full contents of
   `deploy_vps_dashboard_key` (including the
   `-----BEGIN OPENSSH PRIVATE KEY-----` header and the
   `-----END OPENSSH PRIVATE KEY-----` footer).
3. Add `VPS_HOST` (the deploy host the operator already knows; do not commit the value here).
4. Add `VPS_USER` (e.g. `root`).

Then **delete the local copy of the private key** from the
workstation:

```bash
rm -f ./deploy_vps_dashboard_key
```

The public key file (`deploy_vps_dashboard_key.pub`) is safe to
keep locally — it's already on the VPS.

## Manual deploy (operator-initiated)

Run the same script manually from the VPS at any time:

```bash
ssh root@<VPS_HOST>
cd /root/trading-agent
bash scripts/deploy_vps_dashboard.sh
```

Same script, same invariants. The workflow and the manual path
are byte-identical.

## Manual verification

After a deploy (manual or automatic):

```bash
# Cluster state.
docker compose ps

# Dashboard health.
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8050/agent-control
# Expected: 200 (or 302 if redirected to /login).

# Confirm agent is NOT running.
docker compose ps --status running --services | grep -q '^agent$' \
  && echo "FAIL: agent is running" \
  || echo "OK: agent is stopped"
```

The Agent Control PWA may need a service-worker / site-data
clear after a shell or asset cache release; see
`mobile_agent_control_pwa.md` for the v3.15.15.26.x SW versioning
runbook.

## Rollback

To roll back to a previous SHA:

```bash
ssh root@<VPS_HOST>
cd /root/trading-agent

# Inspect recent merge commits.
git log --oneline --first-parent -10 main

# Reset to a known-good SHA (replace with the actual SHA).
git fetch origin main
git reset --hard <SHA>

# Re-build + relaunch via the audited script.
# (The script always resets to origin/main; for a deliberate
#  rollback you must override that. The simplest pattern is to
#  push a revert commit through GitHub so the workflow picks it
#  up the same way as any other merge.)
```

The recommended rollback path is a `git revert` PR through
GitHub: it preserves the audit trail and re-uses the same
deploy workflow without manual SSH.

## Operator note: PWA cache

After this release ships, the Agent Control PWA standalone
shell from v3.15.15.26.2 already lives behind
`SW_VERSION=v3.15.15.26.2`. No additional cache action is
required for v3.15.15.29. Future releases that change the PWA
shell or assets must bump `SW_VERSION` in
`frontend/public/sw.js`; see `mobile_agent_control_pwa.md` for
the canonical procedure.

## Security notes

* **Do not reuse personal SSH keys.** Use the dedicated deploy
  key generated via the steps above.
* **Do not commit secrets.** A static test in `tests/unit/`
  enforces that the workflow file contains no literal IPs,
  private-key headers, or token-shaped values.
* **The deploy user need not be root.** If you create a
  dedicated `deploy` user on the VPS, grant it the minimum
  privileges needed to run `docker compose` and edit
  `/root/trading-agent` (or move the repo to that user's home).
  Then set `VPS_USER=deploy` accordingly.
* **The workflow runner is GitHub-ephemeral.** The private key
  file lives only for the duration of one job and is wiped in
  the final step.

## Static-test guarantees

`tests/unit/test_vps_deploy_invariants.py` enforces:

* the script exists, contains `set -euo pipefail`,
  `docker compose build dashboard`,
  `docker compose up -d --no-deps dashboard nginx`,
  `docker compose stop agent`, and does NOT contain
  `docker compose up -d --build dashboard nginx`;
* the workflow exists, triggers on `push:` to `main` only, has
  no `pull_request` trigger, references the three required
  secrets, declares a `concurrency` group + `timeout-minutes`
  cap, contains no literal private-key / token / password /
  hostname material, and invokes the safe deploy script.

These tests run as part of `pytest tests/unit` on every PR;
breaking any invariant fails the build.

## Cross-references

* `scripts/deploy_vps_dashboard.sh` — the audited deploy script.
* `.github/workflows/deploy-vps-dashboard.yml` — the GitHub
  Actions workflow.
* `tests/unit/test_vps_deploy_invariants.py` — invariant
  guards.
* `.claude/agents/deployment-implementation-agent.md` — the
  agent that authored these files (narrow file-level allowlist).
* `.claude/agents/deployment-safety-agent.md` — the read-only
  reviewer that gates production-posture diffs.
* `docs/governance/no_touch_paths.md` — the broader no-touch
  policy.
