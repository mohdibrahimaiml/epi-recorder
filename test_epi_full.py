#!/usr/bin/env python3
"""
Full EPI smoke test — runs locally and against live epilabs.org.
No tokens, just shell commands and pytest.
Usage: python test_epi_full.py
"""

import subprocess
import sys
import urllib.request

PASS = 0
FAIL = 0


def check(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def run_pytest(path: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-q", "--tb=line"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def fetch_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.status
    except Exception:
        return 0


def fetch_text(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


print("=" * 50)
print("  EPI Full Smoke Test Suite")
print("=" * 50)

# ── Phase 1: Local Python Tests ─────────────────────────────────────
print("\n>> Phase 1: Local Python Tests")
check("Portal tests (13)", run_pytest("tests/test_verify_portal.py"))
check("AIUC-1 tests (26)", run_pytest("tests/test_aiuc1_mapping.py"))
check("SCITT tests (18)", run_pytest("tests/test_scitt.py"))

# ── Phase 2: Live Website ───────────────────────────────────────────
print("\n>> Phase 2: Live Website (epilabs.org)")
check("Landing page (/)", fetch_status("https://epilabs.org/") == 200)
check("Pricing page", fetch_status("https://epilabs.org/pricing.html") == 200)
check("Technology page", fetch_status("https://epilabs.org/technology.html") == 200)
check("CSS assets", fetch_status("https://epilabs.org/css/style.css") == 200)
check("Image assets", fetch_status("https://epilabs.org/assets/logo.png") == 200)

# ── Phase 3: API Endpoints ──────────────────────────────────────────
print("\n>> Phase 3: API Endpoints")
check("Health", '"status":"ok"' in fetch_text("https://epilabs.org/health"))
check("DID document", "did:web:epilabs.org" in fetch_text("https://epilabs.org/.well-known/did.json"))
check("Trust registry", '"scitt_services"' in fetch_text("https://epilabs.org/.well-known/epi-trust-registry.json"))
check("Server portal", fetch_status("https://epilabs.org/portal") == 200)

# ── Phase 4: SCITT Service ──────────────────────────────────────────
print("\n>> Phase 4: SCITT Transparency Service")
scitt_keys = fetch_text("https://epilabs.org/scitt/keys")
check("SCITT /keys", '"public_key"' in scitt_keys)

# Register with bad payload should return 400, not 503
try:
    req = urllib.request.Request(
        "https://epilabs.org/scitt/register",
        data=b"not-valid-cose",
        headers={"Content-Type": "application/cose"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        reg_status = resp.status
except urllib.error.HTTPError as e:
    reg_status = e.code

check("SCITT /register rejects bad COSE (400)", reg_status == 400)

# ── Phase 5: CLI Smoke ──────────────────────────────────────────────
print("\n>> Phase 5: CLI Smoke Tests")
epi_version = subprocess.run([sys.executable, "-m", "epi_cli", "--version"], capture_output=True)
check("epi CLI installed", epi_version.returncode == 0)

golden = "epi-recordings/aiuc1_golden_submission.epi"
golden_verify = subprocess.run(
    [sys.executable, "-m", "epi_cli", "verify", golden, "--json"],
    capture_output=True,
)
check("Golden artifact verifies", golden_verify.returncode == 0)

# ── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"  Results: {PASS} passed, {FAIL} failed")
print("=" * 50)

if FAIL == 0:
    print("  All tests passed!")
    sys.exit(0)
else:
    print("  Some tests failed.")
    sys.exit(1)
