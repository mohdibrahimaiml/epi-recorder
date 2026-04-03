"""
EPI Starter Kit: Insurance Claim Denial — Live Approval Demo
-------------------------------------------------------------
Gateway-backed version of the insurance claim denial workflow.

Unlike agent.py (which simulates approval inline), this script:
  - sends every event to the gateway via /capture
  - pauses at agent.approval.request and prints real approve/deny URLs
  - waits for a human to click approve or deny
  - continues only after the gateway records agent.approval.response
  - exports the sealed .epi case file from the gateway
  - opens the Decision Record in the browser

Use this script when selling the human-in-the-loop story.
Use agent.py when demonstrating offline artifact generation.

Prerequisites:
  epi gateway serve                   # gateway running at localhost:8765
  export EPI_APPROVAL_WEBHOOK_URL=... # optional: fires when approval is needed
  export EPI_APPROVAL_BASE_URL=http://localhost:8765

Run:
  python agent_live_approval.py
  python agent_live_approval.py --gateway http://localhost:8765
  python agent_live_approval.py --claim-id CLM-99001 --no-open
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4


# ── defaults ────────────────────────────────────────────────────────────────

DEFAULT_GATEWAY = "http://localhost:8765"
DEFAULT_CLAIM_ID = "CLM-48219"
DEFAULT_REVIEWER_EMAIL = "claims.manager@carrier.com"
POLL_INTERVAL_SECONDS = 2
APPROVAL_TIMEOUT_SECONDS = 600  # 10 minutes


# ── gateway client ───────────────────────────────────────────────────────────

class GatewayClient:
    def __init__(self, base_url: str, *, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _get_bytes(self, path: str) -> bytes:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def health(self) -> bool:
        try:
            self._get("/health")
            return True
        except Exception:
            return False

    def send_event(self, workflow_id: str, kind: str, content: dict) -> dict:
        # case_id must equal workflow_id so all events group into one case.
        # derive_case_key() uses case_id first; without it every event gets
        # a different SHA-256 fingerprint and ends up in a separate case.
        return self._post("/capture", {
            "workflow_id": workflow_id,
            "case_id": workflow_id,
            "kind": kind,
            "content": content,
        })

    def find_case(self, workflow_id: str, *, retries: int = 10) -> dict | None:
        """
        Poll /api/cases until the case appears.
        Because we set case_id=workflow_id in every event, the case's id field
        will equal workflow_id directly — no fuzzy matching needed.
        """
        for _ in range(retries):
            try:
                cases = self._get("/api/cases").get("cases", [])
                for case in cases:
                    if case.get("id") == workflow_id:
                        return case
            except Exception:
                pass
            time.sleep(POLL_INTERVAL_SECONDS)
        return None

    def poll_for_approval_response(
        self,
        workflow_id: str,
        approval_id: str,
        *,
        timeout: int = APPROVAL_TIMEOUT_SECONDS,
    ) -> dict | None:
        """
        Poll until agent.approval.response appears in the case.
        Returns the response content dict, or None on timeout.
        """
        deadline = time.monotonic() + timeout
        # case_id == workflow_id because we set case_id=workflow_id in send_event()
        case_id = workflow_id

        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                # GET /api/cases/{id} returns {"ok": True, "case": {...}}
                wrapper = self._get(f"/api/cases/{urllib.parse.quote(case_id, safe='')}")
                steps = (wrapper.get("case") or {}).get("steps") or []
                for step in steps:
                    content = step.get("content") or {}
                    if (
                        step.get("kind") == "agent.approval.response"
                        and content.get("approval_id") == approval_id
                    ):
                        return content
            except Exception:
                pass

        return None

    def export_case(self, case_id: str, output_path: Path) -> Path:
        """Download the sealed .epi file for a case."""
        data = self._get_bytes(f"/api/cases/{urllib.parse.quote(case_id, safe='')}/export")
        output_path.write_bytes(data)
        return output_path


# ── demo workflow ────────────────────────────────────────────────────────────

def _step(label: str) -> None:
    print(f"\n  → {label}")


def _ok(label: str) -> None:
    print(f"    ✓ {label}")


def _warn(label: str) -> None:
    print(f"    ⚠ {label}", file=sys.stderr)


def run_live_approval_demo(
    *,
    gateway_url: str = DEFAULT_GATEWAY,
    claim_id: str = DEFAULT_CLAIM_ID,
    reviewer_email: str = DEFAULT_REVIEWER_EMAIL,
    output_file: str | None = None,
    token: str | None = None,
    open_browser: bool = True,
) -> dict:
    """
    Run the insurance claim denial workflow against a live gateway.
    Pauses at human approval and waits for a real decision.
    """
    client = GatewayClient(gateway_url, token=token)
    output_path = Path(output_file or f"live_insurance_{claim_id}.epi")

    print()
    print("  EPI Insurance Claim — Live Approval Demo")
    print("  " + "─" * 44)
    print(f"  Gateway : {gateway_url}")
    print(f"  Claim   : {claim_id}")
    print(f"  Reviewer: {reviewer_email}")
    print()

    # ── preflight ────────────────────────────────────────────────────────────
    _step("Checking gateway connection...")
    if not client.health():
        print(
            f"\n  [ERROR] Cannot reach gateway at {gateway_url}\n"
            "  Start it with:  epi gateway serve\n"
            "  Or set:         --gateway http://your-host:8765\n",
            file=sys.stderr,
        )
        sys.exit(1)
    _ok(f"Gateway reachable at {gateway_url}")

    workflow_id = f"claim-{claim_id}-{uuid4().hex[:8]}"
    approval_id = f"approval-{claim_id}"

    # ── step 1: start ─────────────────────────────────────────────────────────
    _step("Starting claim review workflow...")
    client.send_event(workflow_id, "agent.run.start", {
        "agent_name": "InsuranceClaimDenialAgent",
        "agent_version": "1.0",
        "workflow": "claim-denial",
        "user_input": f"Review claim {claim_id}",
        "goal": "Determine whether the claim should be paid or denied with defensible evidence.",
        "policy_file": "epi_policy.json",
    })
    _ok("Workflow started — evidence capture active")

    # ── step 2: load claim ────────────────────────────────────────────────────
    _step(f"Loading claim {claim_id}...")
    claim = {
        "claim_id": claim_id,
        "claim_amount": 1200,
        "policy_number": "POL-77192",
        "line_of_business": "homeowners",
        "loss_type": "water damage",
        "reported_cause": "groundwater seepage",
        "coverage_summary": "Groundwater seepage is excluded under section HO-7.2.",
    }
    client.send_event(workflow_id, "tool.call", {
        "tool": "load_claim", "input": {"claim_id": claim_id},
    })
    client.send_event(workflow_id, "tool.response", {
        "tool": "load_claim", "status": "success", "output": claim,
    })
    _ok(f"Claim loaded — amount ${claim['claim_amount']}, line: {claim['line_of_business']}")

    # ── step 3: fraud check ───────────────────────────────────────────────────
    _step("Running fraud check...")
    client.send_event(workflow_id, "tool.call", {
        "tool": "run_fraud_check", "input": {"claim_id": claim_id},
    })
    client.send_event(workflow_id, "tool.response", {
        "tool": "run_fraud_check",
        "status": "success",
        "output": {"risk_level": "low", "score": 0.08, "watchlist_match": False},
    })
    _ok("Fraud check passed — risk: low, score: 0.08")

    # ── step 4: coverage check ────────────────────────────────────────────────
    _step("Checking coverage...")
    client.send_event(workflow_id, "tool.call", {
        "tool": "check_coverage",
        "input": {"claim_id": claim_id, "policy_number": claim["policy_number"]},
    })
    client.send_event(workflow_id, "tool.response", {
        "tool": "check_coverage",
        "status": "success",
        "output": {
            "claim_amount": claim["claim_amount"],
            "coverage_status": "excluded",
            "policy_clause": "HO-7.2",
            "summary": "Groundwater seepage exclusion applies to this loss type.",
        },
    })
    _ok("Coverage check complete — status: excluded (HO-7.2)")

    # ── step 5: approval request ──────────────────────────────────────────────
    _step("Submitting human approval request...")
    approval_reason = (
        f"Claim amount ${claim['claim_amount']} exceeds the $500 review threshold "
        "and the decision is a denial that must be approved by a human reviewer."
    )
    client.send_event(workflow_id, "agent.approval.request", {
        "approval_id": approval_id,
        "action": "deny_claim",
        "reason": approval_reason,
        "requested_from": reviewer_email,
        "reviewer_role": "manager",
        "timeout_minutes": 120,
    })

    # Print the real approve/deny URLs — the gateway built these from EPI_APPROVAL_BASE_URL
    wf_token = urllib.parse.quote(workflow_id, safe="")
    ap_token = urllib.parse.quote(approval_id, safe="")
    approve_url = f"{gateway_url}/api/approve/{wf_token}/{ap_token}?decision=approve"
    deny_url    = f"{gateway_url}/api/approve/{wf_token}/{ap_token}?decision=deny"

    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  WAITING FOR HUMAN APPROVAL                                 │")
    print("  │                                                             │")
    print(f"  │  Claim : {claim_id:<50}│")
    print(f"  │  Action: deny_claim                                         │")
    print("  │                                                             │")
    print("  │  Open one of these URLs in your browser to respond:        │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()
    print(f"  APPROVE → {approve_url}")
    print(f"  DENY    → {deny_url}")
    print()
    print(f"  (If EPI_APPROVAL_WEBHOOK_URL is set, the reviewer was notified automatically)")
    print(f"  Waiting up to {APPROVAL_TIMEOUT_SECONDS // 60} minutes for a response...", flush=True)

    # ── poll for response ─────────────────────────────────────────────────────
    response = client.poll_for_approval_response(
        workflow_id, approval_id, timeout=APPROVAL_TIMEOUT_SECONDS
    )

    if response is None:
        _warn(f"No approval response received within {APPROVAL_TIMEOUT_SECONDS // 60} minutes.")
        _warn("Record the event manually or restart the demo after configuring EPI_APPROVAL_WEBHOOK_URL.")
        sys.exit(1)

    approved = bool(response.get("approved"))
    reviewer = response.get("reviewer", "approval-link")
    response_reason = response.get("reason", "")
    print()
    print(f"  ✓ Response received — {'APPROVED' if approved else 'DENIED'} by {reviewer}")
    if response_reason:
        print(f"    Reason: {response_reason}")

    # ── step 6: denial reason ─────────────────────────────────────────────────
    _step("Documenting denial reason...")
    denial_reason = (
        "Claim denied because the reported groundwater seepage is excluded "
        "under policy section HO-7.2."
    )
    client.send_event(workflow_id, "tool.call", {
        "tool": "record_denial_reason",
        "input": {"claim_id": claim_id, "reason_code": "coverage-exclusion"},
    })
    client.send_event(workflow_id, "tool.response", {
        "tool": "record_denial_reason",
        "status": "success",
        "output": {
            "claim_id": claim_id,
            "reason_code": "coverage-exclusion",
            "summary": denial_reason,
        },
    })
    _ok("Denial reason recorded")

    # ── step 7: AI consultation ───────────────────────────────────────────────
    _step("Consulting claims AI (mock — no API key needed)...")
    time.sleep(0.15)
    model_name = "mock-claims-model"
    ai_recommendation = (
        "DENY. The reported water damage falls under an excluded cause of loss "
        "for this policy and the documented evidence does not support an exception."
    )
    client.send_event(workflow_id, "llm.request", {
        "provider": "mock",
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You summarize insurer claim decisions in one paragraph."},
            {"role": "user", "content": f"Explain the recommended outcome for claim {claim_id}."},
        ],
    })
    client.send_event(workflow_id, "llm.response", {
        "provider": "mock",
        "model": model_name,
        "choices": [{"message": {"role": "assistant", "content": ai_recommendation}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 68, "completion_tokens": 32, "total_tokens": 100},
    })
    _ok(f"AI recommendation recorded")

    # ── step 8: decision ──────────────────────────────────────────────────────
    _step("Recording final decision...")
    decision = {
        "decision": "deny_claim",
        "claim_id": claim_id,
        "claim_amount": claim["claim_amount"],
        "coverage_status": "excluded",
        "policy_clause": "HO-7.2",
        "denial_reason": denial_reason,
        "human_approved": approved,
        "approved_by": reviewer,
        "confidence": 0.93,
    }
    client.send_event(workflow_id, "agent.decision", decision)
    _ok("Decision recorded — deny_claim (confidence 0.93)")

    # ── step 9: denial notice ─────────────────────────────────────────────────
    _step("Issuing denial notice...")
    client.send_event(workflow_id, "tool.call", {
        "tool": "issue_denial_notice",
        "input": {"claim_id": claim_id, "delivery_channel": "letter"},
    })
    client.send_event(workflow_id, "tool.response", {
        "tool": "issue_denial_notice",
        "status": "success",
        "output": {"notice_id": f"DEN-{claim_id}", "delivery_channel": "letter"},
    })
    _ok("Denial notice issued")

    # ── step 10: close ────────────────────────────────────────────────────────
    _step("Closing workflow...")
    client.send_event(workflow_id, "agent.run.end", {
        "agent_name": "InsuranceClaimDenialAgent",
        "success": True,
        "outcome": "DENY",
    })
    _ok("Workflow complete")

    # ── export .epi ───────────────────────────────────────────────────────────
    _step("Exporting sealed case file from gateway...")

    # Find the case id — give the worker a moment to project events
    time.sleep(3)
    case_data = client.find_case(workflow_id, retries=10)
    if case_data is None:
        _warn("Case not found in gateway after workflow completed.")
        _warn("Check gateway logs. The workflow events were accepted but not projected.")
        sys.exit(1)

    case_id = case_data.get("id") or case_data.get("case_id")
    if not case_id:
        _warn(f"Case found but has no id: {list(case_data.keys())}")
        sys.exit(1)

    try:
        client.export_case(case_id, output_path)
        _ok(f"Case sealed → {output_path.resolve()}")
    except Exception as exc:
        _warn(f"Export failed: {exc}")
        _warn("The case is still in the gateway — retry with:")
        _warn(f"  curl -o {output_path} {gateway_url}/api/cases/{urllib.parse.quote(case_id, safe='')}/export")
        sys.exit(1)

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  CASE SEALED                                                │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()
    print(f"  Case file : {output_path.resolve()}")
    print(f"  Case ID   : {case_id}")
    print(f"  Decision  : DENY (approved by {reviewer})")
    print()
    print(f"  epi verify {output_path}                   # tamper-evidence check")
    print(f"  epi view {output_path}                     # open Decision Summary")
    print(f"  epi export-summary summary {output_path}   # export Decision Record HTML")
    print(f"  epi share {output_path}                    # get a shareable link")
    print()

    if open_browser:
        try:
            import subprocess
            import webbrowser
            # Generate the Decision Record HTML
            subprocess.run(
                [sys.executable, "-m", "epi_cli", "export-summary", "summary", str(output_path)],
                check=False,
            )
            # Open the live viewer in the browser
            subprocess.run(
                [sys.executable, "-m", "epi_cli", "view", str(output_path)],
                check=False,
            )
        except Exception:
            pass

    return decision


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Insurance claim denial — live approval demo via EPI gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--gateway", default=DEFAULT_GATEWAY, help="Gateway base URL (default: %(default)s)")
    p.add_argument("--claim-id", default=DEFAULT_CLAIM_ID, help="Claim ID (default: %(default)s)")
    p.add_argument("--reviewer", default=DEFAULT_REVIEWER_EMAIL, help="Reviewer email shown in approval request")
    p.add_argument("--output", default=None, help="Output .epi file path")
    p.add_argument("--token", default=None, help="Gateway Bearer token (if auth is enabled)")
    p.add_argument("--no-open", dest="open_browser", action="store_false", help="Skip opening Decision Record")
    p.set_defaults(open_browser=True)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_live_approval_demo(
        gateway_url=args.gateway,
        claim_id=args.claim_id,
        reviewer_email=args.reviewer,
        output_file=args.output,
        token=args.token,
        open_browser=args.open_browser,
    )
