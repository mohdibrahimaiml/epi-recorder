#!/usr/bin/env python3
"""Seal the example decision records shown on the homepage.

Three outcomes, three real artifacts: a denial, an approval and an escalation.
The provider responses are scripted (no API key), so each file says so in its
notes. Everything else is real: the tool calls are recorded by the OpenAI
wrapper, each decision carries its reasons and the rules it relied on, the
release is sealed and approved by a demo key, the denial runs through the
pre-action approval gate with a separate demo approver key, and each seal is a
normal Ed25519 seal.

The demo also writes ``witness.jsonl``, ``claims-policy-1.4.epi`` and the demo
public keys next to the artifacts, so a reviewer can reproduce:

    epi approvers add demo-key.pub --name "DEMO KEY"
    epi approvers add demo-approver.pub --name "DEMO APPROVER"
    epi verify decision-example.epi --release claims-policy-1.4.epi \
      --witness-log witness.jsonl --require-release --min-approvals 1 \
      --require-pre-action-approval

    python scripts/make_decision_example.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "website" / "assets" / "demo"

MODEL = "gpt-4o"
SERVED = "gpt-4o-2024-08-06"
APPROVER = "DEMO KEY - Claims Adjuster (not a real person)"
RELEASE_NAME = "claims-policy"
RELEASE_VERSION = "1.4"
RELEASE_FILE = OUT_DIR / f"{RELEASE_NAME}-{RELEASE_VERSION}.epi"
POLICY_FILE = OUT_DIR / "claims-policy.yaml"
TRUST_POLICY_FILE = OUT_DIR / "claims-approval-policy.json"
WITNESS_FILE = OUT_DIR / "witness.jsonl"
WITNESS_SECRET = "epi-demo-witness"
RELEASE_APPROVER = "DEMO KEY"
PRE_ACTION_APPROVER = "DEMO APPROVER"

# One entry per card on the homepage. The page is asserted against these files
# by tests/test_homepage_example.py, so the card cannot describe a record the
# site does not ship.
VARIANTS = [
    {
        "file": "decision-example.epi",
        "case": "CLM-1001",
        "goal": "Adjudicate claim CLM-1001",
        "user_input": "Claim CLM-1001: burst pipe, kitchen. Policy HO3-4.2.",
        "lookup": {"claim_id": "CLM-1001", "peril": "water damage",
                   "policy": "HO3-4.2", "amount_usd": 4820},
        "policy_result": {"covered": False, "clause": "HO3-4.2",
                          "text": "Water damage from plumbing is excluded."},
        "tool": "deny_claim",
        "tool_args": ('{"claim_id": "CLM-1001", "decision": "deny", "reason": '
                      '"Water damage exclusion HO3-4.2 applies to this peril."}'),
        "tool_description": "Deny a claim with the policy clause relied on",
        "decision_output": {"claim_id": "CLM-1001", "payable_usd": 0},
        "rationale": "Water damage exclusion HO3-4.2 applies to this peril.",
        "basis": {"policy": "HO3-4.2",
                  "data": ["claim:CLM-1001", "policy:HO3-4.2#exclusion", "peril:water damage"]},
        "approval_id": "denial-CLM-1001",
        "approval_action": "issue denial notice",
        "approval_reason": "Checked against policy HO3-4.2; the exclusion applies.",
    },
    {
        "file": "decision-example-approved.epi",
        "case": "CLM-1002",
        "goal": "Approve claim CLM-1002",
        "user_input": "Claim CLM-1002: sudden pipe failure, bathroom. Policy HO3-2.0.",
        "lookup": {"claim_id": "CLM-1002", "peril": "sudden pipe failure",
                   "policy": "HO3-2.0", "amount_usd": 4820},
        "policy_result": {"covered": True, "clause": "HO3-2.0",
                          "text": "Sudden and accidental discharge is covered up to the limit."},
        "tool": "approve_claim",
        "tool_args": ('{"claim_id": "CLM-1002", "decision": "approve", "amount_usd": 4820, '
                      '"reason": "Covered peril under HO3-2.0 and the invoice is inside the limit."}'),
        "tool_description": "Approve a claim with the amount and the clause relied on",
        "decision_output": {"claim_id": "CLM-1002", "payable_usd": 4820},
        "rationale": "Covered peril under HO3-2.0 and the invoice is inside the limit.",
        "basis": {"policy": "HO3-2.0",
                  "data": ["claim:CLM-1002", "policy:HO3-2.0#covered", "invoice:INV-8841"]},
        "approval_id": "payment-CLM-1002",
        "approval_action": "release payment",
        "approval_reason": "Coverage and amount checked against HO3-2.0 and the invoice.",
    },
    {
        "file": "decision-example-escalated.epi",
        "case": "CLM-1003",
        "goal": "Escalate claim CLM-1003",
        "user_input": "Claim CLM-1003: slow leak behind a wall, damage over months. Policy HO3-4.2.",
        "lookup": {"claim_id": "CLM-1003", "peril": "slow leak",
                   "policy": "HO3-4.2", "amount_usd": 11840},
        "policy_result": {"covered": None, "clause": "HO3-4.2 vs 3.1",
                          "text": "Seepage over weeks is excluded; sudden discharge is covered."},
        "tool": "escalate_claim",
        "tool_args": ('{"claim_id": "CLM-1003", "route": "senior adjuster", "reason": '
                      '"Coverage is ambiguous: the loss sits between the seepage exclusion '
                      'and the sudden-discharge wording."}'),
        "tool_description": "Escalate a claim to a human when the wording does not settle it",
        "decision_output": {"claim_id": "CLM-1003", "payable_usd": None,
                            "route": "senior adjuster"},
        "rationale": "Coverage is ambiguous: the loss sits between the seepage exclusion and the sudden-discharge wording.",
        "basis": {"policy": "HO3-4.2 / HO3-3.1",
                  "data": ["claim:CLM-1003", "policy:HO3-4.2#seepage",
                           "policy:HO3-3.1#sudden-discharge", "inspection:INS-2207"]},
        "approval_id": "escalation-CLM-1003",
        "approval_action": "assign to a senior adjuster",
        "approval_reason": "The wording does not settle coverage; a person decides.",
    },
]


def _scripted_response(variant: dict) -> SimpleNamespace:
    call = SimpleNamespace(
        id=f"call_{variant['case'].lower().replace('-', '')}",
        type="function",
        function=SimpleNamespace(name=variant["tool"], arguments=variant["tool_args"]),
    )
    return SimpleNamespace(
        id=f"chatcmpl-{variant['case'].lower()}",
        model=SERVED,
        created=1761900000,
        system_fingerprint="fp_demo",
        usage=SimpleNamespace(prompt_tokens=412, completion_tokens=38, total_tokens=450),
        choices=[
            SimpleNamespace(
                index=0,
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    role="assistant", content=None, tool_calls=[call], refusal=None
                ),
            )
        ],
    )


def _public_hex(private_key) -> str:
    from cryptography.hazmat.primitives import serialization

    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _write_public(path: Path, public_hex: str) -> None:
    path.write_text(public_hex + "\n", encoding="utf-8")


def _write_policy_files() -> None:
    POLICY_FILE.write_text(
        json.dumps(
            {
                "policy_format_version": "2.0",
                "policy_id": "claims-release",
                "system_name": "claims",
                "system_version": "1.0",
                "policy_version": RELEASE_VERSION,
                "rules": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    TRUST_POLICY_FILE.write_text(
        json.dumps(
            {
                "policy_format_version": "2.0",
                "policy_id": "claims-approval",
                "system_name": "claims",
                "system_version": "1.0",
                "policy_version": RELEASE_VERSION,
                "rules": [
                    {
                        "id": "R-DENY",
                        "name": "Denial needs a person",
                        "severity": "critical",
                        "description": "A denial needs a person to approve that exact action first.",
                        "type": "approval_guard",
                        "mode": "require_approval",
                        "approval_action": "deny_claim",
                        "approval_policy_ref": "deny-approval",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _start_witness(env: dict) -> tuple[subprocess.Popen, str]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    if WITNESS_FILE.exists():
        WITNESS_FILE.unlink()
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "epi_cli",
            "witness",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--out",
            str(WITNESS_FILE),
            "--secret",
            WITNESS_SECRET,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    for _ in range(150):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return server, url
        except OSError:
            if server.poll() is not None:
                raise RuntimeError("demo witness server failed to start")
            time.sleep(0.1)
    raise RuntimeError("demo witness server did not become ready")


def _cli(args: list[str], env: dict) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "epi_cli", *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"epi {' '.join(args)} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
        )


def _gated_deny(state: dict):
    from epi_recorder.trust import ApprovalGate, RuntimePolicyEngine, TrustInterceptor

    def deny_claim(claim_id: str, decision: str, reason: str) -> dict:
        return {"claim_id": claim_id, "decision": decision, "reason": reason}

    gate = ApprovalGate(
        default_timeout=60,
        workflow_id="claims-agent",
        witness_url=state["witness_url"],
        witness_secret=WITNESS_SECRET,
    )
    engine = RuntimePolicyEngine(str(TRUST_POLICY_FILE), enable_blocking=True)
    return TrustInterceptor(engine, gate=gate).wrap_tool(deny_claim, "deny_claim")


def _seal(variant: dict, state: dict) -> Path:
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    out = OUT_DIR / variant["file"]
    response = _scripted_response(variant)
    case = variant["case"]

    with record(
        str(out),
        workflow_name="claims-agent",
        goal=variant["goal"],
        case_id=case,
        notes=(
            "SIMULATED DEMO - the model response is scripted; the record format, "
            "hashes, signature, release and approvals are real."
        ),
        with_viewer=False,
        release=str(RELEASE_FILE),
        policy={"claims": str(POLICY_FILE)},
        witness_url=state["witness_url"],
        witness_secret=WITNESS_SECRET,
    ) as epi:
        with epi.agent_run("claims-agent", user_input=variant["user_input"]) as agent:
            agent.tool_call("lookup_claim", {"claim_id": case})
            agent.tool_result("lookup_claim", variant["lookup"])
            agent.tool_call("check_policy", {"policy": variant["lookup"]["policy"]})
            agent.tool_result("check_policy", variant["policy_result"])
            TracedCompletions(SimpleNamespace(create=lambda *a, **k: response)).create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You adjudicate insurance claims."},
                    {"role": "user", "content": variant["user_input"]},
                ],
                temperature=0.0,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": variant["tool"],
                            "description": variant["tool_description"],
                        },
                    }
                ],
            )
            agent.decision(
                variant["tool"],
                output=variant["decision_output"],
                confidence=0.93 if variant["tool"] == "deny_claim" else 0.88,
                rationale=variant["rationale"],
                basis=variant["basis"],
            )
            if case == "CLM-1001":
                safe_deny = _gated_deny(state)
                safe_deny(
                    claim_id=case,
                    decision="deny",
                    reason=variant["rationale"],
                )
            epi.log(
                "agent.approval.request",
                {"action": variant["approval_action"], "approval_id": variant["approval_id"]},
            )
        epi.log("agent.run.end", {"status": "completed", "claim_id": case})
    return out


def _sign_off(variant: dict, out: Path, demo_key) -> dict:
    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry

    public_hex = _public_hex(demo_key)
    record_obj = ReviewRecord(
        reviewed_by=APPROVER,
        reviews=[
            make_approval_entry(
                approval_id=variant["approval_id"],
                decision="approve",
                action=variant["approval_action"],
                reason=variant["approval_reason"],
                approver_name=APPROVER,
                key_fingerprint_hex=key_fingerprint(public_hex, grouped=False),
                demo_key=True,
            )
        ],
        reviewer_identity={
            "type": "name",
            "value": APPROVER,
            "role": "Approver",
            "org": "EPI demo (synthetic)",
            "verified": False,
        },
    )
    stamp = add_review_to_artifact(out, record_obj, private_key=demo_key, timestamp=True) or {}
    return {"fingerprint": key_fingerprint(public_hex), "stamp": stamp}


def _setup() -> dict:
    from epi_core.approvers import ApproverRegistry
    from epi_core.keys import KeyManager, key_fingerprint

    home = Path(tempfile.mkdtemp(prefix="epi_demo_home_"))
    for name in ("keys", "approver_keys", "trusted_approvers", "trusted_keys", "empty_approver", "inbox"):
        (home / name).mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(home / "keys"),
            "EPI_APPROVER_KEYS_DIR": str(home / "approver_keys"),
            "EPI_TRUSTED_APPROVERS_DIR": str(home / "trusted_approvers"),
            "EPI_TRUSTED_KEYS_DIR": str(home / "trusted_keys"),
            "EPI_APPROVAL_INBOX_DIR": str(home / "inbox"),
            "EPI_WITNESS_SECRET": WITNESS_SECRET,
            "EPI_NOTARIZE": "0",
            "EPI_QUIET": "1",
            "EPI_OVERWRITE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    km = KeyManager(keys_dir=home / "keys")
    km.generate_keypair("default")
    approver_keys = KeyManager(keys_dir=home / "approver_keys")
    approver_keys.generate_keypair(RELEASE_APPROVER)
    approver_keys.generate_keypair(PRE_ACTION_APPROVER)
    registry = ApproverRegistry(approvers_dir=home / "trusted_approvers")
    for name in (RELEASE_APPROVER, PRE_ACTION_APPROVER):
        registry.add(name, approver_keys.load_public_key(name).hex(), overwrite=True)

    _write_policy_files()
    (home / "trusted_keys" / "demo-sealer.pub").write_text(
        km.load_public_key("default").hex() + "\n", encoding="utf-8"
    )
    _write_public(OUT_DIR / "demo-sealer.pub", km.load_public_key("default").hex())
    _write_public(OUT_DIR / "demo-key.pub", approver_keys.load_public_key(RELEASE_APPROVER).hex())
    _write_public(OUT_DIR / "demo-approver.pub", approver_keys.load_public_key(PRE_ACTION_APPROVER).hex())
    (OUT_DIR / "demo-keys.txt").write_text(
        "DEMO KEY        " + key_fingerprint(approver_keys.load_public_key(RELEASE_APPROVER).hex()) + "\n"
        "DEMO APPROVER   " + key_fingerprint(approver_keys.load_public_key(PRE_ACTION_APPROVER).hex()) + "\n"
        "DEMO SEALER     " + key_fingerprint(km.load_public_key("default").hex()) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    server, witness_url = _start_witness(env)
    state = {
        "home": home,
        "km": km,
        "approver_keys": approver_keys,
        "demo_key": approver_keys.load_private_key(RELEASE_APPROVER),
        "witness_server": server,
        "witness_url": witness_url,
        "env": env,
    }
    env["EPI_WITNESS_URL"] = witness_url

    _cli(
        [
            "release",
            "create",
            "--name",
            RELEASE_NAME,
            "--version",
            RELEASE_VERSION,
            "--policy",
            f"claims={POLICY_FILE}",
            "--model",
            f"openai:{MODEL}",
            "--require-approvals",
            "1",
            "--out",
            str(RELEASE_FILE),
        ],
        env,
    )
    _cli(
        [
            "release",
            "approve",
            str(RELEASE_FILE),
            "--as",
            RELEASE_APPROVER,
            "--yes",
            "--no-timestamp",
        ],
        env,
    )
    return state


def _signer_thread(state: dict) -> threading.Event:
    from epi_core.pre_action import sign_response

    stop = threading.Event()
    key = state["approver_keys"].load_private_key(PRE_ACTION_APPROVER)
    public_hex = state["approver_keys"].load_public_key(PRE_ACTION_APPROVER).hex()
    inbox = state["home"] / "inbox"

    def _run() -> None:
        from epi_core.keys import key_fingerprint

        while not stop.is_set():
            for path in inbox.glob("*.request.json"):
                request_id = path.name.split(".")[0]
                response_path = inbox / f"{request_id}.response.json"
                if response_path.exists():
                    continue
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                    response = sign_response(
                        request,
                        decision="approve",
                        approver=PRE_ACTION_APPROVER,
                        key_fingerprint=key_fingerprint(public_hex, grouped=False),
                        public_key=public_hex,
                        private_key=key,
                        reason="Demo approver checked the denial.",
                    )
                    response_path.write_text(
                        json.dumps(response, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass
            time.sleep(0.05)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return stop


def _verify_demo(state: dict) -> str:
    env = state["env"].copy()
    env["EPI_APPROVER_KEYS_DIR"] = str(state["home"] / "approver_keys")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "epi_cli",
            "verify",
            str(OUT_DIR / "decision-example.epi"),
            "--release",
            str(RELEASE_FILE),
            "--witness-log",
            str(WITNESS_FILE),
            "--require-release",
            "--min-approvals",
            "1",
            "--require-pre-action-approval",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0 or "MATCHES" not in output or "APPROVED BEFORE ACTION" not in output:
        raise RuntimeError(
            "the generated demo did not verify as MATCHES + APPROVED BEFORE ACTION:\n"
            + output[-4000:]
        )
    return output


def _patch_summary() -> None:
    """Add the release and pre-action rows the generic summary does not know."""
    path = OUT_DIR / "decision-record-example.html"
    text = path.read_text(encoding="utf-8")
    approval_tile = re.search(
        r'(<article class="summary-tile">\s*<p class="eyebrow">Human approval</p>.*?</article>)',
        text,
        re.S,
    )
    if approval_tile:
        insert = approval_tile.group(1) + """
        <article class="summary-tile">
          <p class="eyebrow">Release</p>
          <strong>claims-policy 1.4 &middot; MATCHES</strong>
        </article>
        <article class="summary-tile">
          <p class="eyebrow">Pre-action approval</p>
          <strong>DEMO APPROVER &middot; before the action</strong>
        </article>"""
        text = text.replace(approval_tile.group(1), insert, 1)
    anchor = (
        '<div class="detail-row"><dt>Data and rules relied on</dt>'
        "<dd>policy=HO3-4.2; data=claim:CLM-1001, policy:HO3-4.2#exclusion, peril:water damage</dd></div>"
    )
    rows = anchor + """
        <div class="detail-row"><dt>Release</dt><dd>claims-policy 1.4 &middot; MATCHES</dd></div>
        <div class="detail-row"><dt>Pre-action approval</dt><dd>DEMO APPROVER &middot; approved before the action</dd></div>"""
    text = text.replace(anchor, rows, 1)
    text = text.replace(
        "epi verify decision-example.epi --require-human-approval",
        "epi verify decision-example.epi --release claims-policy-1.4.epi "
        "--witness-log witness.jsonl --require-release --min-approvals 1 "
        "--require-pre-action-approval",
        1,
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _setup()
    stop = _signer_thread(state)
    os.environ["EPI_APPROVER_KEYS_DIR"] = str(state["home"] / "empty_approver")
    try:
        for variant in VARIANTS:
            out = _seal(variant, state)
            signed = _sign_off(variant, out, state["demo_key"])
            stamp = signed["stamp"]
            print(f"sealed {out.relative_to(ROOT)}")
            print(f"  approver fingerprint: {signed['fingerprint']}")
            print(f"  independent time: {stamp.get('status')} {stamp.get('gen_time') or ''}")
    finally:
        stop.set()
        state["witness_server"].terminate()
        try:
            state["witness_server"].wait(timeout=5)
        except Exception:
            state["witness_server"].kill()

    _cli(
        [
            "export-summary",
            str(OUT_DIR / "decision-example.epi"),
            "--out",
            str(OUT_DIR / "decision-record-example.html"),
        ],
        state["env"],
    )
    _patch_summary()
    report = _verify_demo(state)
    print("demo verify:")
    for line in report.splitlines():
        if any(word in line for word in ("DECISION", "Release", "Pre-action", "basis")):
            print(line)
    print(f"wrote {WITNESS_FILE.relative_to(ROOT)}")
    print(f"wrote {RELEASE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
