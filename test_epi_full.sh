#!/usr/bin/env bash
# Full EPI smoke test script — runs locally and against live epilabs.org
# Usage: bash test_epi_full.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

pass() { echo -e "${GREEN}✓${NC} $1"; ((PASS++)); }
fail() { echo -e "${RED}✗${NC} $1"; ((FAIL++)); }

echo "========================================"
echo "  EPI Full Smoke Test Suite"
echo "========================================"
echo ""

# ── 1. Local Python Tests ───────────────────────────────────────────
echo "▶ Phase 1: Local Python Tests"

if python -m pytest tests/test_verify_portal.py -q --tb=line 2>/dev/null; then
    pass "Portal tests (13 tests)"
else
    fail "Portal tests"
fi

if python -m pytest tests/test_aiuc1_mapping.py -q --tb=line 2>/dev/null; then
    pass "AIUC-1 tests (26 tests)"
else
    fail "AIUC-1 tests"
fi

if python -m pytest tests/test_scitt.py -q --tb=line 2>/dev/null; then
    pass "SCITT tests (18 tests)"
else
    fail "SCITT tests"
fi

# ── 2. Live Website Tests (epilabs.org) ─────────────────────────────
echo ""
echo "▶ Phase 2: Live Website Tests (epilabs.org)"

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/ | grep -q "200"; then
    pass "Landing page (/)"
else
    fail "Landing page (/)"
fi

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/pricing.html | grep -q "200"; then
    pass "Pricing page"
else
    fail "Pricing page"
fi

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/technology.html | grep -q "200"; then
    pass "Technology page"
else
    fail "Technology page"
fi

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/css/style.css | grep -q "200"; then
    pass "CSS assets"
else
    fail "CSS assets"
fi

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/assets/logo.png | grep -q "200"; then
    pass "Image assets"
else
    fail "Image assets"
fi

# ── 3. API Endpoint Tests ───────────────────────────────────────────
echo ""
echo "▶ Phase 3: API Endpoint Tests"

if curl -s https://epilabs.org/health | grep -q '"status":"ok"'; then
    pass "Health endpoint"
else
    fail "Health endpoint"
fi

if curl -s https://epilabs.org/.well-known/did.json | grep -q 'did:web:epilabs.org'; then
    pass "DID document"
else
    fail "DID document"
fi

if curl -s https://epilabs.org/.well-known/epi-trust-registry.json | grep -q '"scitt_services"'; then
    pass "Trust registry"
else
    fail "Trust registry"
fi

if curl -s -o /dev/null -w "%{http_code}" https://epilabs.org/portal | grep -q "200"; then
    pass "Server portal (/portal)"
else
    fail "Server portal (/portal)"
fi

# ── 4. SCITT Service Tests ──────────────────────────────────────────
echo ""
echo "▶ Phase 4: SCITT Transparency Service"

SCITT_KEYS=$(curl -s https://epilabs.org/scitt/keys)
if echo "$SCITT_KEYS" | grep -q '"public_key"'; then
    pass "SCITT /keys returns public key"
else
    fail "SCITT /keys"
fi

# Test SCITT register with a dummy payload (should get 400, not 503)
SCITT_REG=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/cose" \
    -d "not-valid-cose" \
    https://epilabs.org/scitt/register)
if [ "$SCITT_REG" = "400" ]; then
    pass "SCITT /register rejects invalid COSE (400)"
else
    fail "SCITT /register (got $SCITT_REG, expected 400)"
fi

# ── 5. CLI Smoke Tests ──────────────────────────────────────────────
echo ""
echo "▶ Phase 5: CLI Smoke Tests"

if epi --version >/dev/null 2>&1; then
    pass "epi CLI is installed"
else
    fail "epi CLI not found"
fi

GOLDEN="epi-recordings/aiuc1_golden_submission.epi"
if [ -f "$GOLDEN" ]; then
    if epi verify "$GOLDEN" --json >/dev/null 2>&1; then
        pass "Golden artifact verifies (epi verify)"
    else
        fail "Golden artifact verification"
    fi
else
    fail "Golden artifact not found at $GOLDEN"
fi

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
