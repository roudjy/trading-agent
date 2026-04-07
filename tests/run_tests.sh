#!/bin/bash
# ============================================================
# Run alle tests voor de trading agent herarchitectuur
# Gebruik: ./tests/run_tests.sh
# ============================================================

set -e
cd "$(dirname "$0")/.."

echo "================================================"
echo " TRADING AGENT TEST SUITE"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

PASS=0
FAIL=0
ERRORS=()

run_suite() {
    local naam="$1"
    local pad="$2"

    echo ""
    echo "── $naam ──────────────────────────────────────"
    if python3 -m pytest "$pad" -v --tb=short --no-header -q 2>&1; then
        echo "✓ $naam: GESLAAGD"
        ((PASS++)) || true
    else
        echo "✗ $naam: GEFAALD"
        ((FAIL++)) || true
        ERRORS+=("$naam")
    fi
}

# 1. Smoke tests eerst (snelste feedback)
run_suite "SMOKE" "tests/smoke/"

# 2. Unit tests
run_suite "UNIT" "tests/unit/"

# 3. Regressie tests (bugs mogen niet terugkomen)
run_suite "REGRESSIE" "tests/regression/"

# 4. Integratie tests
run_suite "INTEGRATIE" "tests/integration/"

# 5. Resilience tests
run_suite "RESILIENCE" "tests/resilience/"

# ── Samenvatting ─────────────────────────────────────────────
echo ""
echo "================================================"
echo " SAMENVATTING"
echo "================================================"
echo " Suites geslaagd : $PASS"
echo " Suites gefaald  : $FAIL"

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo " Gefaalde suites  : ${ERRORS[*]}"
fi

if [ $FAIL -eq 0 ]; then
    echo ""
    echo " ✓ ALLE TESTS GESLAAGD"
    exit 0
else
    echo ""
    echo " ✗ $FAIL SUITE(S) GEFAALD — zie output hierboven"
    exit 1
fi
