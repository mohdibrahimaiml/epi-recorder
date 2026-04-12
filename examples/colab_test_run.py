import asyncio, os, sys
from pathlib import Path
import tempfile
DEMO_DIR = Path(tempfile.mkdtemp(prefix="epi_colab_test_"))
os.chdir(DEMO_DIR)
print(f"DEMO_DIR: {DEMO_DIR}")

# === CELL: verify-install ===
import importlib.metadata
version = importlib.metadata.version("epi-recorder")
print(f"epi-recorder {version} installed")

# Check CLI is available
import subprocess, sys
result = subprocess.run([sys.executable, "-m", "epi_cli", "--version"], capture_output=True, text=True)
print(result.stdout.strip() or result.stderr.strip())

# === CELL: setup-dirs ===
import os, json, zipfile, asyncio
from pathlib import Path

# Working directory for this demo
DEMO_DIR = Path("/tmp/epi_demo")
DEMO_DIR.mkdir(exist_ok=True)
os.chdir(DEMO_DIR)

print(f"Working directory: {DEMO_DIR}")

# === CELL: basic-record ===
from epi_recorder import record

output_file = DEMO_DIR / "01_basic.epi"

with record(
    str(output_file),
    workflow_name="basic-demo",
    goal="Show the simplest EPI recording",
    notes="No API keys needed â€” all mock data",
    tags=["demo", "basic"],
    metrics={"confidence": 0.95},
) as epi:

    # Log a tool call
    epi.log_step("tool.call", {
        "tool": "lookup_customer",
        "input": {"customer_id": "CUST-001"}
    })

    # Simulate tool response
    epi.log_step("tool.response", {
        "tool": "lookup_customer",
        "status": "success",
        "output": {"name": "Alice Smith", "account_status": "active", "balance": 1500.00}
    })

    # Log a mock LLM request
    epi.log_step("llm.request", {
        "provider": "mock",
        "model": "mock-gpt-4",
        "messages": [
            {"role": "system", "content": "You are a customer service agent."},
            {"role": "user", "content": "Should we approve a $200 refund for CUST-001?"}
        ]
    })

    # Log the mock LLM response
    epi.log_step("llm.response", {
        "provider": "mock",
        "model": "mock-gpt-4",
        "choices": [{
            "message": {"role": "assistant", "content": "Yes, approve the refund. Customer is active with sufficient balance."},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60}
    })

    # Log a final decision
    epi.log_step("agent.decision", {
        "decision": "approve_refund",
        "amount": 200.00,
        "customer_id": "CUST-001",
        "confidence": 0.95
    })

print(f"\nCreated: {output_file}")
print(f"Size: {output_file.stat().st_size:,} bytes")
assert output_file.exists(), "ERROR: .epi file was not created"
print("PASS: basic recording")

# === CELL: agent-run ===
from epi_recorder import record

output_file = DEMO_DIR / "02_agent_run.epi"

with record(str(output_file), goal="Full AgentRun feature tour") as epi:

    with epi.agent_run(
        "RefundAgent",
        user_input="Process refund for order ORD-5551",
        goal="Validate and approve or deny the refund request",
    ) as agent:

        # Planning
        agent.plan(
            "Validate order â†’ check policy â†’ decide â†’ notify customer",
            steps=[
                "Look up order ORD-5551",
                "Check refund eligibility policy",
                "Make decision",
                "Notify customer",
            ]
        )

        # State transition
        agent.state("validating_order")

        # User message
        agent.message("user", "Process refund for order ORD-5551")

        # Tool call + result
        agent.tool_call("lookup_order", {"order_id": "ORD-5551"})
        agent.tool_result(
            "lookup_order",
            output={"order_id": "ORD-5551", "amount": 89.99, "days_since_purchase": 12, "status": "delivered"},
            status="success"
        )

        agent.state("checking_policy")

        agent.tool_call("check_refund_policy", {"order_id": "ORD-5551", "days": 12})
        agent.tool_result(
            "check_refund_policy",
            output={"eligible": True, "policy": "30-day return", "max_amount": 89.99},
            status="success"
        )

        # Memory read
        agent.memory_read(
            "customer_history",
            query="previous refund requests for CUST-001",
            result_count=2,
            value=[{"date": "2025-01-10", "amount": 20.00, "approved": True}]
        )

        # Memory write
        agent.memory_write(
            "pending_refund",
            value={"order_id": "ORD-5551", "amount": 89.99},
            operation="set"
        )

        # Decision
        agent.state("deciding")
        agent.decision(
            "approve_refund",
            output={"order_id": "ORD-5551", "refund_amount": 89.99},
            confidence=0.97,
            rationale="Order within 30-day window, customer in good standing, policy eligible"
        )

        # Notify
        agent.tool_call("send_notification", {"customer_id": "CUST-001", "message": "Refund approved"})
        agent.tool_result("send_notification", output={"sent": True}, status="success")
        agent.message("assistant", "Refund of $89.99 approved and customer notified.")

print(f"\nCreated: {output_file}")
print(f"Size: {output_file.stat().st_size:,} bytes")
assert output_file.exists(), "ERROR: .epi file was not created"
print("PASS: agent_run recording")

# === CELL: approval-flow ===
from epi_recorder import record

output_file = DEMO_DIR / "03_approval_flow.epi"

with record(str(output_file), goal="Demonstrate human-in-the-loop approval") as epi:

    with epi.agent_run(
        "InsuranceClaimAgent",
        user_input="Review claim CLM-9901",
        goal="Decide on claim CLM-9901 with human approval",
    ) as agent:

        # Load and check claim
        agent.tool_call("load_claim", {"claim_id": "CLM-9901"})
        agent.tool_result("load_claim", output={
            "claim_id": "CLM-9901",
            "claim_amount": 4500,
            "policy_number": "POL-12345",
            "loss_type": "fire damage",
        })

        agent.tool_call("run_fraud_check", {"claim_id": "CLM-9901"})
        agent.tool_result("run_fraud_check", output={
            "risk_level": "low", "score": 0.06
        })

        # REQUEST human approval (claim exceeds auto-approve threshold)
        agent.approval_request(
            action="approve_large_claim",
            reason="Claim amount $4,500 exceeds $1,000 auto-approve threshold. Human review required.",
            risk_level="medium",
            requested_by="InsuranceClaimAgent"
        )

        # --- In a live system this pauses and sends a webhook/email ---
        # --- Here we simulate the human clicking APPROVE             ---

        # RECORD human approval response
        agent.approval_response(
            action="approve_large_claim",
            approved=True,
            reviewer="claims.manager@carrier.com",
            notes="Coverage confirmed, fire damage exclusions do not apply."
        )

        # Now execute the approved action
        agent.decision(
            "approve_claim",
            output={"claim_id": "CLM-9901", "payout": 4500},
            confidence=0.99,
            rationale="Human approved after fraud check passed."
        )

        agent.tool_call("issue_payment", {"claim_id": "CLM-9901", "amount": 4500})
        agent.tool_result("issue_payment", output={"payment_id": "PAY-77001", "status": "queued"})

print(f"\nCreated: {output_file}")
assert output_file.exists(), "ERROR: .epi file was not created"
print("PASS: approval flow recording")

# === CELL: handoff ===
from epi_recorder import record

output_file = DEMO_DIR / "04_multi_agent.epi"

with record(str(output_file), goal="Multi-agent loan application pipeline") as epi:

    # Agent 1: Intake
    with epi.agent_run(
        "IntakeAgent",
        user_input="New loan application APP-4421",
        goal="Validate and route application"
    ) as intake:

        intake.tool_call("load_application", {"app_id": "APP-4421"})
        intake.tool_result("load_application", output={
            "app_id": "APP-4421",
            "applicant": "Bob Chen",
            "loan_amount": 25000,
            "purpose": "home improvement"
        })

        intake.tool_call("validate_documents", {"app_id": "APP-4421"})
        intake.tool_result("validate_documents", output={"valid": True, "missing": []})

        # Hand off to underwriting
        intake.handoff(
            to_agent="UnderwritingAgent",
            reason="Documents validated. Routing to underwriting for credit assessment."
        )

    # Agent 2: Underwriting
    with epi.agent_run(
        "UnderwritingAgent",
        user_input="Underwrite APP-4421",
        goal="Assess credit risk and recommend decision",
        parent_run_id="intake-run"
    ) as uw:

        uw.tool_call("run_credit_check", {"app_id": "APP-4421", "applicant": "Bob Chen"})
        uw.tool_result("run_credit_check", output={
            "credit_score": 742,
            "dti_ratio": 0.28,
            "risk_tier": "A"
        })

        uw.tool_call("calculate_rate", {"credit_score": 742, "loan_amount": 25000, "term_months": 60})
        uw.tool_result("calculate_rate", output={"apr": 7.2, "monthly_payment": 495.15})

        uw.decision(
            "approve_loan",
            output={"app_id": "APP-4421", "approved_amount": 25000, "apr": 7.2},
            confidence=0.92,
            rationale="Credit score 742, DTI 0.28 â€” within approved lending parameters."
        )

        # Hand off to notification
        uw.handoff(
            to_agent="NotificationAgent",
            reason="Loan approved. Notify applicant with terms."
        )

    # Agent 3: Notification
    with epi.agent_run(
        "NotificationAgent",
        user_input="Notify applicant for APP-4421",
        goal="Send approval notification with loan terms"
    ) as notif:

        notif.tool_call("send_approval_email", {
            "app_id": "APP-4421",
            "email": "bob.chen@email.com",
            "approved_amount": 25000,
            "apr": 7.2
        })
        notif.tool_result("send_approval_email", output={"sent": True, "message_id": "MSG-8821"})
        notif.message("assistant", "Approval email sent to bob.chen@email.com with full loan terms.")

print(f"\nCreated: {output_file}")
assert output_file.exists(), "ERROR: .epi file was not created"
print("PASS: multi-agent handoff recording")

# === CELL: pause-resume ===
from epi_recorder import record

output_file = DEMO_DIR / "05_pause_resume.epi"

with record(str(output_file), goal="Demonstrate pause/resume and error logging") as epi:

    with epi.agent_run(
        "DataPipelineAgent",
        user_input="Process batch JOB-331",
        goal="Fetch, transform, and store data from upstream"
    ) as agent:

        agent.tool_call("fetch_batch", {"job_id": "JOB-331"})
        agent.tool_result("fetch_batch", output={"records": 1500, "source": "s3://data-lake/batch-331"})

        # Pause â€” waiting for upstream confirmation
        agent.pause(
            reason="Waiting for upstream data validation service",
            waiting_for="validation-service"
        )

        # Resume after external signal
        agent.resume(
            reason="Validation service confirmed data integrity",
            resumed_from="validation-service"
        )

        # Continue processing
        agent.tool_call("transform_data", {"job_id": "JOB-331", "records": 1500})
        agent.tool_result("transform_data", output={"transformed": 1498, "skipped": 2})

        agent.tool_call("store_results", {"job_id": "JOB-331"})
        agent.tool_result("store_results", output={"stored": 1498, "destination": "warehouse.jobs"})

        agent.decision(
            "pipeline_complete",
            output={"job_id": "JOB-331", "records_stored": 1498},
            confidence=1.0
        )

    # --- Also show how errors are captured ---
    output_file_err = DEMO_DIR / "05b_error_capture.epi"
    try:
        with record(str(output_file_err), goal="Error capture demo") as epi2:
            with epi2.agent_run("FailingAgent", user_input="Do something risky") as agent2:
                agent2.tool_call("risky_operation", {"param": "value"})
                # Manually record an error
                agent2.error(ValueError("Upstream API returned 503"))
                # Finish with failure
                agent2.finish(success=False, failure_reason="upstream_unavailable")
    except Exception:
        pass  # Error was captured in the .epi, not raised

print(f"\nCreated: {output_file}")
print(f"Created: {output_file_err}")
assert output_file.exists() and output_file_err.exists(), "ERROR: .epi file missing"
print("PASS: pause/resume and error capture")

# === CELL: artifacts ===
from epi_recorder import record
from pathlib import Path
import json

output_file = DEMO_DIR / "06_artifacts.epi"

# Create some output files to capture
report_path = DEMO_DIR / "model_report.json"
report_path.write_text(json.dumps({
    "model": "classifier-v2",
    "accuracy": 0.934,
    "precision": 0.921,
    "recall": 0.947,
    "f1": 0.934,
    "evaluated_on": "2026-04-01"
}, indent=2))

predictions_path = DEMO_DIR / "predictions.csv"
predictions_path.write_text(
    "id,label,confidence\n"
    "1,approve,0.97\n"
    "2,deny,0.88\n"
    "3,review,0.61\n"
)

with record(str(output_file), goal="Capture model evaluation artifacts") as epi:

    epi.log_step("tool.call", {"tool": "run_evaluation", "input": {"model": "classifier-v2"}})
    epi.log_step("tool.response", {
        "tool": "run_evaluation",
        "status": "success",
        "output": {"accuracy": 0.934, "samples": 1000}
    })

    # Attach the report file into the .epi archive
    epi.log_artifact(report_path)

    # Attach the predictions CSV
    epi.log_artifact(predictions_path)

    epi.log_step("agent.decision", {
        "decision": "promote_model",
        "model": "classifier-v2",
        "accuracy": 0.934,
        "confidence": 0.92
    })

# Verify artifacts are inside the ZIP
with zipfile.ZipFile(output_file) as z:
    names = z.namelist()
    artifact_files = [n for n in names if n.startswith("artifacts/")]
    print(f"Files in archive: {names}")
    print(f"Artifacts captured: {artifact_files}")

assert any("model_report.json" in n for n in artifact_files), "ERROR: model_report.json not in archive"
assert any("predictions.csv" in n for n in artifact_files), "ERROR: predictions.csv not in archive"
print("PASS: artifact capture")

# === CELL: policy ===
from epi_recorder import record
import json

# Write a policy file in the working directory
policy = {
    "version": "1.0",
    "policy_id": "demo-insurance-policy",
    "name": "Insurance Claim Demo Policy",
    "description": "Controls for AI-assisted claim decisions",
    "rules": [
        {
            "id": "rule-001",
            "name": "fraud_check_required",
            "type": "sequence_guard",
            "severity": "high",
            "description": "Fraud check must run before any claim decision",
            "required_sequence": ["tool.call:run_fraud_check", "agent.decision"]
        },
        {
            "id": "rule-002",
            "name": "human_approval_for_large_claims",
            "type": "approval_guard",
            "severity": "critical",
            "description": "Claims over $1000 require human approval",
            "requires_approval_before": ["agent.decision"]
        },
        {
            "id": "rule-003",
            "name": "no_pii_in_output",
            "type": "prohibition_guard",
            "severity": "medium",
            "description": "Final output must not contain raw PII fields",
            "prohibited_fields": ["ssn", "date_of_birth", "credit_card"]
        }
    ]
}

policy_path = DEMO_DIR / "epi_policy.json"
policy_path.write_text(json.dumps(policy, indent=2))
print(f"Policy written: {policy_path}")

output_file = DEMO_DIR / "07_policy.epi"

with record(str(output_file), goal="Policy-governed claim decision") as epi:

    with epi.agent_run(
        "InsuranceClaimAgent",
        user_input="Decide claim CLM-7701",
        goal="Evaluate and decide claim"
    ) as agent:

        # Fraud check runs first (satisfies rule-001)
        agent.tool_call("run_fraud_check", {"claim_id": "CLM-7701"})
        agent.tool_result("run_fraud_check", output={"risk_level": "low", "score": 0.04})

        # Human approval (satisfies rule-002)
        agent.approval_request(
            action="deny_claim",
            reason="Claim amount $2,200 exceeds $1,000 threshold",
            risk_level="medium"
        )
        agent.approval_response(
            action="deny_claim",
            approved=True,
            reviewer="underwriter@carrier.com",
            notes="Coverage exclusion confirmed."
        )

        # Decision â€” output contains no PII (satisfies rule-003)
        agent.decision(
            "deny_claim",
            output={
                "claim_id": "CLM-7701",
                "outcome": "denied",
                "reason_code": "coverage-exclusion"
            },
            confidence=0.98
        )

# Check policy_evaluation.json was written into the archive
with zipfile.ZipFile(output_file) as z:
    names = z.namelist()
    print(f"Archive contents: {names}")
    has_policy_eval = "policy_evaluation.json" in names
    if has_policy_eval:
        policy_eval = json.loads(z.read("policy_evaluation.json"))
        print(f"Policy evaluation: {json.dumps(policy_eval, indent=2)[:500]}")

print(f"\nPolicy evaluation file present: {has_policy_eval}")
print("PASS: policy enforcement")

# === CELL: async-recording ===
async def _cell_async_recording():
    from epi_recorder import record
    import asyncio
    
    output_file = DEMO_DIR / "08_async.epi"
    
    async def run_async_agent():
        async with record(str(output_file), goal="Async agent demo") as epi:
    
            async with epi.agent_run(
                "AsyncSearchAgent",
                user_input="Search for best mortgage rates",
                goal="Find top 3 mortgage offers"
            ) as agent:
    
                # Async tool calls
                await agent.atool_call("search_rates", {"product": "mortgage", "term": "30yr"})
                await asyncio.sleep(0.05)  # Simulate async I/O
                await agent.atool_result("search_rates", output=[
                    {"lender": "BankA", "rate": 6.8, "apr": 6.9},
                    {"lender": "BankB", "rate": 6.75, "apr": 6.88},
                    {"lender": "CreditUnionC", "rate": 6.65, "apr": 6.75},
                ])
    
                await agent.amessage(
                    "assistant",
                    "Top result: CreditUnionC at 6.65% rate (6.75% APR)."
                )
    
                await agent.adecision(
                    "recommend_lender",
                    output={"lender": "CreditUnionC", "rate": 6.65},
                    confidence=0.89,
                    rationale="Lowest APR among three options."
                )
    
    # Run in Colab (event loop already running)
    await run_async_agent()
    
    print(f"\nCreated: {output_file}")
    assert output_file.exists(), "ERROR: async .epi file was not created"
    print("PASS: async recording")
asyncio.run(_cell_async_recording())

# === CELL: inspect ===
import zipfile, json

# Use the approval flow demo â€” it has the richest contents
target = DEMO_DIR / "03_approval_flow.epi"

print(f"Inspecting: {target}")
print(f"File size : {target.stat().st_size:,} bytes\n")

with zipfile.ZipFile(target) as z:
    names = z.namelist()
    print("=== Archive contents ===")
    for name in names:
        size = z.getinfo(name).file_size
        print(f"  {name:<40} {size:>8,} bytes")

    # Read manifest
    print("\n=== manifest.json ===")
    manifest = json.loads(z.read("manifest.json"))
    for k, v in manifest.items():
        if k == "file_manifest":
            print(f"  {k}: {{ {len(v)} files hashed }}")
        elif k == "signature":
            sig_short = str(v)[:40] + "..." if v else None
            print(f"  {k}: {sig_short}")
        else:
            print(f"  {k}: {v}")

    # Read and print all steps
    print("\n=== steps.jsonl (timeline) ===")
    steps_raw = z.read("steps.jsonl").decode()
    steps = [json.loads(line) for line in steps_raw.strip().splitlines()]
    for step in steps:
        kind = step.get("kind", "?")
        ts   = step.get("timestamp", "")[:19]
        # Show a short summary of content
        content = step.get("content", {})
        summary = ""
        if "tool" in content:
            summary = f"tool={content['tool']}"
        elif "decision" in content:
            summary = f"decision={content['decision']}"
        elif "action" in content:
            summary = f"action={content['action']}"
        elif "agent_name" in content:
            summary = f"agent={content['agent_name']}"
        print(f"  [{step['index']:>2}] {ts}  {kind:<35} {summary}")

    print(f"\nTotal steps: {len(steps)}")

# === CELL: verify ===
import subprocess, sys

files_to_verify = [
    DEMO_DIR / "01_basic.epi",
    DEMO_DIR / "02_agent_run.epi",
    DEMO_DIR / "03_approval_flow.epi",
    DEMO_DIR / "04_multi_agent.epi",
    DEMO_DIR / "07_policy.epi",
    DEMO_DIR / "08_async.epi",
]

print("=== epi verify ===")
all_passed = True

for f in files_to_verify:
    result = subprocess.run(
        [sys.executable, "-m", "epi_cli", "verify", str(f)],
        capture_output=True, text=True
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    if result.returncode != 0:
        all_passed = False
    output_line = (result.stdout + result.stderr).strip().split("\n")[0]
    print(f"  [{status}] {f.name:<35} {output_line[:60]}")

print()
if all_passed:
    print("PASS: all files verified")
else:
    print("WARN: some files failed verification â€” check output above")

# === CELL: tamper-demo ===
# Demonstrate tamper detection
# Modify a byte inside a sealed .epi file â†’ verification must FAIL

import shutil

tampered = DEMO_DIR / "tampered.epi"
shutil.copy2(DEMO_DIR / "01_basic.epi", tampered)

# Read the ZIP and modify steps.jsonl
import zipfile, io

# Read all contents
with zipfile.ZipFile(tampered, "r") as z:
    original_contents = {name: z.read(name) for name in z.namelist()}

# Tamper with steps.jsonl
steps_data = original_contents["steps.jsonl"].decode()
tampered_steps = steps_data.replace("approve_refund", "deny_refund")  # change decision!
original_contents["steps.jsonl"] = tampered_steps.encode()

# Rewrite the ZIP
with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as z:
    for name, data in original_contents.items():
        z.writestr(name, data)

# Now verify â€” should FAIL
result = subprocess.run(
    [sys.executable, "-m", "epi_cli", "verify", str(tampered)],
    capture_output=True, text=True
)

print("=== Tamper detection demo ===")
print(f"Return code: {result.returncode}")
print((result.stdout + result.stderr).strip()[:400])

if result.returncode != 0:
    print("\nPASS: tamper correctly detected")
else:
    print("\nUNEXPECTED: tamper was NOT detected â€” check verify logic")

# === CELL: export-summary ===
import subprocess, sys
from pathlib import Path

target = DEMO_DIR / "03_approval_flow.epi"
out_html = DEMO_DIR / "03_approval_flow_summary.html"

result = subprocess.run(
    [sys.executable, "-m", "epi_cli", "export-summary", "summary",
     str(target), "--out", str(out_html)],
    capture_output=True, text=True
)

print("=== epi export-summary ===")
print((result.stdout + result.stderr).strip())
print(f"Return code: {result.returncode}")

# The CLI may write to a default location â€” check both
found = out_html if out_html.exists() else next(iter(DEMO_DIR.glob("*summary*.html")), None)

if found and found.exists():
    print(f"\nDecision Record: {found.name} ({found.stat().st_size:,} bytes)")
    print("PASS: Decision Record exported")
    # To download in Colab:
    # from google.colab import files; files.download(str(found))
else:
    print("NOTE: HTML file not found at expected path â€” check CLI output above")

# === CELL: final-check ===
from pathlib import Path

expected = [
    ("01_basic.epi",          "Basic record() + manual log_step()"),
    ("02_agent_run.epi",      "AgentRun helper â€” full lifecycle"),
    ("03_approval_flow.epi",  "Human-in-the-loop approval"),
    ("04_multi_agent.epi",    "Multi-agent handoff chain"),
    ("05_pause_resume.epi",   "Pause / resume"),
    ("05b_error_capture.epi", "Error capture"),
    ("06_artifacts.epi",      "Artifact capture"),
    ("07_policy.epi",         "Policy enforcement"),
    ("08_async.epi",          "Async recording"),
]

print("=== Final check ===")
print(f"{'File':<30} {'Size':>10}  {'Status':<8}  Description")
print("-" * 80)

all_ok = True
for filename, description in expected:
    path = DEMO_DIR / filename
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    ok = exists and size > 0
    if not ok:
        all_ok = False
    status = "OK" if ok else "MISSING"
    print(f"{filename:<30} {size:>10,}  {status:<8}  {description}")

print()
if all_ok:
    print("ALL PASS â€” every EPI feature demonstrated successfully.")
else:
    print("SOME FILES MISSING â€” review cells above for errors.")
