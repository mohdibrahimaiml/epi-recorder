import os
import sys
import shutil
import time
import subprocess
import json
import logging
from pathlib import Path

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("EPI-MASTER-TEST")

def run_step(name, func):
    logger.info(f"--- STARTING: {name} ---")
    try:
        func()
        logger.info(f"--- PASSED: {name} ---\n")
        return True
    except Exception as e:
        logger.error(f"--- FAILED: {name} ---")
        logger.error(str(e))
        return False

def test_web_verifier_assets():
    """
    Verifies that the crucial Web Verifier file exists and has content.
    """
    verifier_path = Path("epi_web_verifier/verify.html")
    if not verifier_path.exists():
        raise Exception("verify.html is MISSING!")
        
    size = verifier_path.stat().st_size
    if size < 1000:
        raise Exception(f"verify.html seems too small ({size} bytes). Suspicious.")
        
    logger.info(f"verify.html exists ({size} bytes) and looks ready.")

def test_invisible_hook_logic():
    """
    Simulates the GitHub Action: Wraps a command with `epi record`.
    """
    output_file = "action_sim_evidence.epi"
    
    # Clean up previous run
    if os.path.exists(output_file):
        os.remove(output_file)
        
    logger.info(f"Simulating Action: Command -> 'echo Hello Enterprise' | Output -> {output_file}")
    
    # The Action performs: epi record --out <file> -- <command>
    # Use python -c print instead of echo because echo is not an executable on Windows (shell builtin)
    cmd = [sys.executable, "-m", "epi_cli", "record", "--out", output_file, "--", sys.executable, "-c", "print('Hello Enterprise')"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Action simulation failed: {result.stderr}")
        
    if not os.path.exists(output_file):
        raise Exception("Action output file was not created!")
        
    logger.info("Evidence file created successfully.")
    
    # Verify the produced file (What the Web Verifier would do)
    verify_cmd = [sys.executable, "-m", "epi_cli", "verify", output_file]
    v_result = subprocess.run(verify_cmd, capture_output=True, text=True)
    
    if v_result.returncode != 0:
        raise Exception(f"Verification of Action artifact failed: {v_result.stderr}")
        
    logger.info("Artifact verified significantly.")

def test_enterprise_gateway():
    """
    Tests the Async Sidecar (FastAPI + Worker).
    Requires 'requests' or 'httpx' (we will use subprocess to run the existing test script to avoid dependency duplication)
    """
    logger.info("Launching Gateway Integration Test (epi_gateway.test_gateway_local)...")
    
    # We re-use the specific test we wrote, running it as a subprocess to keep environment clean
    cmd = [sys.executable, "-m", "epi_gateway.test_gateway_local"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Gateway Test Failed:\n{result.stdout}\n{result.stderr}")
        
    logger.info(f"Gateway Output:\n{result.stdout}")
    logger.info("Gateway verified successfully.")

def test_pwa_readiness():
    """
    Verifies Phase 4: PWA Assets (manifest, sw.js, logo).
    """
    required_files = ["epi_web_verifier/manifest.json", "epi_web_verifier/sw.js", "epi_web_verifier/logo.svg"]
    
    for f in required_files:
        path = Path(f)
        if not path.exists():
            raise Exception(f"PWA Asset Missing: {f}")
        if path.stat().st_size == 0:
            raise Exception(f"PWA Asset Empty: {f}")
            
    # Check if verify.html has the manifest link (simple string check)
    with open("epi_web_verifier/verify.html", "r", encoding="utf-8") as html:
        content = html.read()
        if 'href="manifest.json"' not in content:
            raise Exception("verify.html does not link to manifest.json!")
            
    logger.info("PWA Assets and Links verified.")

def main():
    logger.info("STARTING TOTAL SYSTEM VERIFICATION")
    
    tests = [
        ("Phase 1: Web Verifier Assets", test_web_verifier_assets),
        ("Phase 2: Invisible Hook (Action Simulation)", test_invisible_hook_logic),
        ("Phase 3: Enterprise Gateway (Async Sidecar)", test_enterprise_gateway),
        ("Phase 4: One-Click PWA Upgrade", test_pwa_readiness)
    ]
    
    passed = 0
    total = len(tests)
    
    for name, func in tests:
        if run_step(name, func):
            passed += 1
        else:
            logger.error("HALTING SUITE DUE TO FAILURE")
            sys.exit(1)
            
    logger.info(f"SUITE COMPLETE: {passed}/{total} Tests Passed. The Platform is Solid.")

if __name__ == "__main__":
    main()
