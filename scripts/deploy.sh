#!/usr/bin/env bash
# =================================================================
# scripts/deploy.sh — v3.10 controllable VPS deploy.
# =================================================================
# Pulls the main branch, pulls the images from GHCR pinned via
# ${IMAGE_TAG:-latest}, brings the stack up, prunes dangling images,
# and health-checks /api/health. NO watchtower; deploys are explicit.
#
# Usage on VPS:
#   cd /root/trading-agent && bash scripts/deploy.sh
#   IMAGE_TAG=3.9.5 bash scripts/deploy.sh   # rollback
#
# First-time setup (once per host) — enable the daily systemd-timer:
#   sudo cp ops/systemd/trading-agent-daily-research.{service,timer} \
#       /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now trading-agent-daily-research.timer
#

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BRANCH="${BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8050/api/health}"

echo ">> deploying ${REPO_ROOT} @ tag=${IMAGE_TAG} branch=${BRANCH}"

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker not on PATH" >&2
    exit 1
fi

echo ">> [1/5] git fetch + checkout ${BRANCH}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo ">> [2/5] docker compose pull (tag=${IMAGE_TAG})"
IMAGE_TAG="${IMAGE_TAG}" docker compose \
    -f docker-compose.yml -f docker-compose.prod.yml pull

echo ">> [3/5] docker compose up -d"
IMAGE_TAG="${IMAGE_TAG}" docker compose \
    -f docker-compose.yml -f docker-compose.prod.yml up -d

echo ">> [4/5] docker image prune -f"
docker image prune -f

echo ">> [5/5] health check on ${HEALTH_URL}"
sleep 5
for attempt in 1 2 3 4 5; do
    if curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/tmp/jvr-health.$$ ; then
        cat /tmp/jvr-health.$$
        echo
        echo ">> deploy OK"
        rm -f /tmp/jvr-health.$$
        break
    fi
    echo "   attempt ${attempt} failed; retrying in 5s..."
    sleep 5
done

if [ ! -f /tmp/jvr-health.$$ ] && ! curl --fail --silent --max-time 5 "${HEALTH_URL}" >/dev/null; then
    echo "error: health endpoint never responded OK. Roll back with:" >&2
    echo "  IMAGE_TAG=<previous> bash scripts/deploy.sh" >&2
    exit 2
fi
rm -f /tmp/jvr-health.$$

# Advisory systemd-timer status report (non-fatal).
# Unit name kept as trading-agent-daily-research.timer for stable
# install paths; the underlying behaviour is now an hourly COL tick.
if command -v systemctl >/dev/null 2>&1; then
    TIMER_STATUS=$(systemctl is-active trading-agent-daily-research.timer 2>/dev/null || true)
    echo ">> campaign operating layer timer: ${TIMER_STATUS:-not-installed}"
    if [ "${TIMER_STATUS}" != "active" ]; then
        echo "   (enable once with: sudo systemctl enable --now trading-agent-daily-research.timer)"
        echo "   after every change to the unit files: sudo systemctl daemon-reload"
    fi
fi
