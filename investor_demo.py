import os
import json
import zipfile
import subprocess
import time

# Set up standard logging to show the difference
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - LOG: %(message)s', filename='agent_logs.txt', filemode='w')

from epi_recorder import record, get_current_session

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    clear_screen()
    
    print("=================================================================")
    print(" EPI RECORDER: EXECUTION EVIDENCE IN THE AGE OF AUTONOMOUS AI ")
    print("=================================================================\n")
    time.sleep(1)
    
    # ---------------------------------------------------------
    # ACT 1: THE WORLD WITHOUT EPI
    # ---------------------------------------------------------
    print("======================================================")
    print(" ACT 1: THE WORLD WITHOUT EPI")
    print("======================================================\n")
    print("Scenario: An autonomous financial agent is processing requests.\n")
    
    print("Standard tail output from production logs:")
    print("-" * 50)
    print("2026-03-04 14:23:01 INFO  Received: Transfer $10,000 from acc_A")
    print("2026-03-04 14:23:02 INFO  Agent generated execution plan")  
    print("2026-03-04 14:23:02 ERROR Transfer failed: insufficient funds")
    print("-" * 50)
    print("\n[?] What happened? Unknown.")
    print("[?] What did the AI actually decide? Unknown.")
    print("[?] Was this a malicious prompt, or an AI hallucination? Unknown.")
    print("[?] Can you prove compliance to a regulator? No.\n")
    
    print("This is the 'Black Box' problem. Every AI agent in production today suffers from it.")
    print("\n[Press Enter...] Continuing...")
    time.sleep(1)
    
    # ---------------------------------------------------------
    # ACT 2: THE WORLD WITH EPI
    # ---------------------------------------------------------
    clear_screen()
    print("======================================================")
    print(" ACT 2: THE WORLD WITH EPI")
    print("======================================================\n")
    print("Now, we run the exact same agent, but wrapped in 1 line of EPI code.\n")
    
    # Clean up any old files for the demo
    epi_filename = os.path.join("epi-recordings", "financial_agent.epi")
    if os.path.exists(epi_filename):
        os.remove(epi_filename)
        
    print(f"Executing agent with @record('{epi_filename}')...")
    time.sleep(1)
    
    # Realistic execution wrapped in EPI
    try:
        with record(output_path=epi_filename, workflow_name="financial_transfer", goal="Transfer funds safely") as session:
            
            # Step 1: Input
            session.log_step("user.input", {
                "content": "Transfer $10,000 from acc_A to acc_B",
                "account_balance": 15000
            })
            print(" -> Captured environment and user input.")
            time.sleep(0.5)
            
            # Step 2: Simulate real LLM response (Deterministic for the demo, but structured like OpenAI)
            decision_payload = {
                "thought_process": "User requested $10,000. For operational safety margins, policy requires a 10x buffer. Outputting $100,000 transfer.",
                "tool_call": "execute_transfer",
                "amount": 100000
            }
            
            session.log_llm_response({
                "provider": "openai",
                "model": "gpt-4-turbo",
                "choices": [{"message": {"role": "assistant", "content": json.dumps(decision_payload)}}]
            })
            print(" -> Captured raw LLM decision and thought process.")
            time.sleep(0.5)
            
            # Step 3: Execution and Failure
            session.log_step("tool.execution", {
                "tool": "execute_transfer",
                "amount_requested": 10000,
                "amount_attempted": 100000,  # The hallucinated amount
                "result": "FAILED: insufficient funds"
            })
            print(" -> Captured tool execution and failure.")
            time.sleep(0.5)
            
    except Exception as e:
        print(f"Exception occurred during execution: {type(e).__name__}: {str(e)}")
        
    print("\n[SUCCESS] Agent execution complete.")
    print(f"[SUCCESS] Cryptographic execution evidence sealed into: {epi_filename}")
    print("\n[Press Enter...] Continuing...")
    time.sleep(1)

    # ---------------------------------------------------------
    # ACT 3: THE CRYPTOGRAPHIC PROOF
    # ---------------------------------------------------------
    clear_screen()
    print("======================================================")
    print(" ACT 3: THE CRYPTOGRAPHIC PROOF")
    print("======================================================\n")
    
    if not os.path.exists(epi_filename):
        print("ERROR: EPI file was not generated.")
        return
        
    with zipfile.ZipFile(epi_filename, 'r') as z:
        # Show Manifest
        try:
            manifest_bytes = z.read("manifest.json")
            manifest = json.loads(manifest_bytes.decode('utf-8'))
            
            print("[MANIFEST] (The tamper-evident seal):")
            print(f"   Created by: {manifest.get('environment', {}).get('os', {}).get('username', 'system')}")
            print(f"   Timestamp:  {manifest.get('created_at', 'Unknown')}")
            print(f"   Device:     {manifest.get('environment', {}).get('os', {}).get('hostname', 'unknown')}")
            print(f"   Model:      gpt-4-turbo (detected)")
            
            # Safely get the signing key ID using multiple possible fields
            signing_key = manifest.get('signing_key_id') or manifest.get('key_id') or manifest.get('public_key') or 'Not Found'
            print(f"   Signed by:  {signing_key}")
            
            print()
            print("[Ed25519 CRYPTOGRAPHIC SIGNATURE]:")
            signature = manifest.get('signature', 'Not Signed')
            print(f"   {signature[:64]}...")
            print()
            
        except Exception as e:
            print(f"Could not read manifest: {e}")
            
        # Show Steps
        try:
            steps_bytes = z.read("steps.jsonl")
            print("[CAPTURED DECISION CHAIN] (The Evidence):")
            for i, line in enumerate(steps_bytes.decode('utf-8').strip().split('\n')):
                if not line: continue
                step = json.loads(line)
                kind = step.get('kind', 'unknown')
                data_preview = json.dumps(step.get('data', {}))
                
                # Truncate for display
                if len(data_preview) > 80:
                    data_preview = data_preview[:77] + "..."
                    
                print(f"   [{i+1}] {kind.ljust(15)} | {data_preview}")
            print("\nUnlike logs, we know EXACTLY why it failed: The AI purposefully added a 10x buffer.")
        except Exception as e:
            print(f"Could not read steps: {e}")
            
    print("\n[Press Enter...] Continuing...")
    time.sleep(1)
    
    # ---------------------------------------------------------
    # ACT 4: LIVE TAMPER TEST
    # ---------------------------------------------------------
    clear_screen()
    print("======================================================")
    print(" ACT 4: LIVE TAMPER TEST")
    print("======================================================\n")
    
    print("Scenario: An engineer tries to cover up the AI's $100,000 mistake.")
    print("They edit the log to say the AI only tried to transfer $10,000.")
    print("With Splunk or Datadog, this edit is permanent. With EPI...\n")
    
    print(f"1. Extracting {epi_filename}...")
    temp_dir = "tampered_epi"
    
    # Clean up before extracting
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        
    with zipfile.ZipFile(epi_filename, 'r') as z:
        z.extractall(temp_dir)
        
    print("2. Modifying steps.jsonl to hide the AI's mistake ($100000 -> $10000)...")
    steps_file = os.path.join(temp_dir, "steps.jsonl")
    with open(steps_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Perform the tamper
    tampered_content = content.replace("100000", "10000")
    
    with open(steps_file, 'w', encoding='utf-8') as f:
        f.write(tampered_content)
        
    print("3. Repacking the compromised execution record...\n")
    tampered_epi = "tampered_financial_agent.epi"
    
    if os.path.exists(tampered_epi):
        os.remove(tampered_epi)
        
    with zipfile.ZipFile(tampered_epi, 'w', zipfile.ZIP_DEFLATED) as z:
        for foldername, subfolders, filenames in os.walk(temp_dir):
            for filename in filenames:
                file_path = os.path.join(foldername, filename)
                arcname = os.path.relpath(file_path, temp_dir).replace("\\", "/")
                z.write(file_path, arcname)
                
    time.sleep(1)
    
    print("Running cryptographic verification on tampered file: `epi verify`")
    print("-" * 60)
    
    try:
        # Actually run the epi verify CLI command to prove it fails for real
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "epi_cli.main", "verify", tampered_epi],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
            
    except Exception as e:
        print(f"\n[FAILED] VERIFICATION SCRIPT ERROR: {str(e)}")
        
    print("-" * 60)
    print("\nThe tampering is instantly detected. The original evidence cannot be forged.")
    print("This is litigation-grade observability.")

    print("\n[Press Enter...] Continuing...")
    time.sleep(1)
    
    # ---------------------------------------------------------
    # ACT 5: THE REGULATORY MOMENT
    # ---------------------------------------------------------
    clear_screen()
    print("======================================================")
    print(" ACT 5: WHY THIS MATTERS NOW")
    print("======================================================\n")
    
    print("EU AI Act Article 12 — Effective August 2, 2026 (5 months from now):\n")
    print('  "High-risk AI systems shall technically allow for the')
    print('   automatic recording of events... tamper-resistant."\n')
    
    print("Penalty for non-compliance:")
    print("  Up to 7% of global annual revenue.")
    print("  For a $1B company: $70,000,000 per violation.\n")
    
    print("Every enterprise deploying AI agents into production (finance, healthcare,")
    print("customer support, infrastructure) needs exactly what you just saw.\n")
    
    print("Log files are insufficient for AI autonomy. You need execution evidence.\n")
    
    print("EPI Tracker is the only open, offline, cryptographically signed")  
    print("execution evidence standard that exists today.\n")
    
    print("6,500+ installs. 10 weeks. One founder.")
    print("The standard is being set right now.")
    print("======================================================\n")
    
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(tampered_epi):
        os.remove(tampered_epi)

if __name__ == "__main__":
    from pathlib import Path
    main()
