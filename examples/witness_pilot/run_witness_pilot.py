#!/usr/bin/env python3
"""Witnessed pilot: the customer holds the proof, and a forgery is caught.

Four roles, four separate homes, no shared secrets:

    vendor    seals a refund decision, reports a hash-only line to the customer
    approver  signs the payout with their own key
    customer  runs the witness receiver, keeps the log, pins both keys
    forger    the vendor's key, a changed decision, re-sealed afterwards

The point of the last step: a re-sealed forgery is a *valid* artifact. Integrity
passes, the signature verifies against the vendor's own pinned key. A signature
protects the file - only the customer's witness log protects the customer, and
it says MISMATCH because the bytes they were handed are not the bytes that were
reported.

Run:  python examples/witness_pilot/run_witness_pilot.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

# The CLI prints box-drawing characters; a cp1252 console would crash on them.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Roles (each runs in its own process so EPI_HOME isolation is real)
# ---------------------------------------------------------------------------

def role_vendor(args: argparse.Namespace) -> int:
    """The agent runs, decides, and reports a hash-only line to the customer."""
    from epi_recorder import record

    out = Path(args.out)
    with record(
        out,
        workflow_name="Refund agent · ORD-9001",
        goal="Decide refund ORD-9001 and request payout approval",
        witness_url=args.witness_url,
        witness_secret=args.witness_secret,
        witness_include_goal=True,
        # The customer's own identifier for the case. It travels in the
        # hash-only witness payload, so their report speaks claim numbers.
        case_id="CLM-9001",
    ) as epi:
        with epi.agent_run("refund-agent", user_input="Customer asks for a refund, ORD-9001") as agent:
            agent.tool_call("lookup_order", {"order_id": "ORD-9001"})
            agent.tool_result(
                "lookup_order",
                {"order_id": "ORD-9001", "status": "delivered", "days_since_delivery": 41},
            )
            agent.tool_call("check_policy", {"policy": "refund-window-v3"})
            agent.tool_result(
                "check_policy",
                {"window_days": 30, "outside_window": True, "exception": "defective item"},
            )
            agent.decision(
                "approve_refund",
                output={"amount_usd": 89.0, "order_id": "ORD-9001"},
                confidence=0.91,
                rationale="Defective item exception applies despite the 41-day gap.",
                basis={"policy": "refund-window-v3#exception", "order": "ORD-9001"},
            )
            epi.log(
                "agent.approval.request",
                {
                    "action": "refund ORD-9001",
                    "approval_id": "refund-7",
                    "amount_usd": 89.0,
                },
            )
        epi.log("agent.run.end", {"status": "completed", "order_id": "ORD-9001"})
    print(f"vendor sealed {out}")
    return 0


def role_forge(args: argparse.Namespace) -> int:
    """The attack: same workflow, changed decision, re-sealed with the same key.

    This is what a vendor can do to their own record. Every step is consistent
    - the chain is rebuilt, the manifest hashes are recomputed, the signature is
    the vendor's real key - because the forger holds that key.
    """
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.schemas import StepModel
    from epi_core.serialize import get_canonical_hash
    from epi_core.trust import sign_manifest

    from uuid import uuid4

    source_artifact = Path(args.infile)
    out = Path(args.out)
    manifest = EPIContainer.read_manifest(source_artifact)
    if getattr(args, "new_workflow", False):
        # A vendor re-running the agent: same case, new workflow id. The
        # customer's log still names the case, which is what the report uses.
        manifest.workflow_id = uuid4()
    steps = EPIContainer.read_steps(source_artifact)

    forged = 0
    for step in steps:
        if step.get("kind") != "agent.decision":
            continue
        content = dict(step.get("content") or {})
        content["decision"] = "DENY"
        content["output"] = {"amount_usd": 0, "order_id": "ORD-9001"}
        content["rationale"] = "Outside the 30-day refund window."
        step["content"] = content
        forged += 1
    if not forged:
        print("no agent.decision step to forge", file=sys.stderr)
        return 2

    # Rebuild prev_hash links so the rewritten timeline is internally valid.
    previous = "CHAIN_START"
    rebuilt: list[dict] = []
    for step in steps:
        model = StepModel(
            index=step["index"],
            timestamp=step["timestamp"],
            kind=step["kind"],
            content=step["content"],
            prev_hash=previous,
        )
        rebuilt.append(model.model_dump(mode="json"))
        previous = get_canonical_hash(model, format="json")

    work = Path(tempfile.mkdtemp(prefix="epi_forge_"))
    try:
        payload = work / "payload.zip"
        EPIContainer.extract_inner_payload(source_artifact, payload)
        source_dir = work / "payload"
        import zipfile

        with zipfile.ZipFile(payload) as zf:
            zf.extractall(source_dir)
        (source_dir / "steps.jsonl").write_text(
            "\n".join(json.dumps(step) for step in rebuilt) + "\n", encoding="utf-8"
        )
        # These are regenerated by pack(); the duplicate manifest would go stale.
        for generated in ("manifest.json", "VERIFY.txt", "viewer.html"):
            path = source_dir / generated
            if path.exists():
                path.unlink()
        inner = source_dir / "artifacts" / "manifest.json"
        if inner.exists():
            inner.unlink()
        # A forger cannot mint the approver's signature, so the old approval is
        # dropped rather than carried over with a broken binding. (If it is kept,
        # the approval's artifact binding catches the rewrite on its own - a
        # second, independent defence this demo does not rely on.)
        for review_member in ("review.json", "review_index.json"):
            stale = source_dir / review_member
            if stale.exists():
                stale.unlink()
        for review_dir in ("reviews", "review_timestamps"):
            shutil.rmtree(source_dir / review_dir, ignore_errors=True)

        key = KeyManager().load_private_key("default")

        def signer(model):
            return sign_manifest(model, key, "vendor")

        EPIContainer.pack(
            source_dir,
            manifest,
            out,
            signer_function=signer,
            preserve_generated=True,
            generate_analysis=False,
            notarize=False,
            embed_viewer=False,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"forged decision re-sealed as {out}")
    return 0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def home(root: Path, name: str) -> dict[str, str]:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "EPI_HOME": str(directory),
        "EPI_KEYS_DIR": str(directory / "keys"),
        "EPI_APPROVER_KEYS_DIR": str(directory / "approver_keys"),
        "EPI_TRUSTED_APPROVERS_DIR": str(directory / "trusted_approvers"),
        "EPI_TRUSTED_KEYS_DIR": str(directory / "trusted_keys"),
        "EPI_QUIET": "1",
        "PYTHONIOENCODING": "utf-8",
        "EPI_NOTARIZE": "0",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
    }


def line(text: str = "") -> None:
    print(text, flush=True)


def check(ok: bool, what: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}", flush=True)
    if not ok:
        raise SystemExit(1)


def epi(env: dict[str, str], *args: str, expect: int = 0) -> str:
    result = subprocess.run(
        [PY, "-m", "epi_cli.main", *args],
        cwd=HERE,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode != expect:
        print(text)
        raise SystemExit(
            f"command failed ({result.returncode}, expected {expect}): epi {' '.join(args)}"
        )
    return text


def public_hex(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
        return text.lower()
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_public_key(text.encode())
    return key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def fingerprint(path: Path) -> str:
    from epi_core.keys import key_fingerprint

    return key_fingerprint(public_hex(path))


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="epi-witness-pilot-"))
    vendor = home(root, "vendor")
    approver = home(root, "approver")
    bank = home(root, "bank")
    approver["EPI_KEY_PASSWORD"] = "witness-pilot-password"
    vendor["EPI_OVERWRITE"] = "1"

    witness_dir = root / "customer"
    witness_dir.mkdir(parents=True, exist_ok=True)
    witness_log = witness_dir / "received.jsonl"
    secret = os.urandom(16).hex()

    run_file = root / "run.epi"
    forged_file = root / "run-forged.epi"

    line(f"work dir: {root}")

    # ── a. CUSTOMER: the witness receiver ───────────────────────────────────
    line("\na. CUSTOMER — start the witness receiver (their own machine, their own log)")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from epi_core.witness_receiver import make_server

    server = make_server("127.0.0.1", 0, out=witness_log, secret=secret)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    line(f"  listening on 127.0.0.1:{port} -> {witness_log.name} (HMAC on)")

    try:
        # ── b. VENDOR: seal and report ──────────────────────────────────────
        line("\nb. VENDOR — run the agent, seal, report a hash-only line")
        epi(vendor, "keys", "generate", "--name", "default")

        subprocess.run(
            [
                PY,
                str(HERE / "run_witness_pilot.py"),
                "--role",
                "vendor",
                "--out",
                str(run_file),
                "--witness-url",
                f"http://127.0.0.1:{port}/",
                "--witness-secret",
                secret,
            ],
            cwd=HERE,
            env={**os.environ, **vendor},
            check=True,
        )
        # The key that actually sealed the run is the one the customer pins.
        # Read it from the artifact, not from a keystore path that a later
        # command could rewrite: the fingerprint must match the bytes.
        from epi_core.container import EPIContainer
        from epi_core.keys import key_fingerprint

        sealed_key = str(EPIContainer.read_manifest(run_file).public_key or "").strip().lower()
        if not sealed_key:
            raise SystemExit("the run is unsigned; the witness pilot needs a sealed key")
        vendor_fp = key_fingerprint(sealed_key)
        line(f"  the vendor reads its fingerprint aloud: {vendor_fp}")

        epi(vendor, "witness", "flush")
        for _ in range(50):
            if witness_log.exists() and witness_log.read_text(encoding="utf-8").strip():
                break
            time.sleep(0.1)
        reports = [
            json.loads(text)
            for text in witness_log.read_text(encoding="utf-8").splitlines()
            if text.strip()
        ] if witness_log.exists() else []
        check(len(reports) == 1, "the customer's log holds exactly one report for the run")
        check(
            reports[0].get("file_sha256") is not None and reports[0].get("steps", 0) > 0,
            "the report is hash-only (file hash + step count, no content)",
        )
        check(
            "steps" in reports[0] and "messages" not in reports[0] and "content" not in reports[0],
            "no prompt, decision text or case content is in the witness payload",
        )

        # ── c. APPROVER: signs with their own key ───────────────────────────
        line("\nc. APPROVER — sign the payout with their own key")
        epi(approver, "approvers", "keygen", "--name", "alice@bank.com")
        approver_pub_path = Path(approver["EPI_APPROVER_KEYS_DIR"]) / "alice@bank.com.pub"
        approver_fp = fingerprint(approver_pub_path)
        line(f"  alice reads this fingerprint aloud: {approver_fp}")
        out = epi(
            approver,
            "review",
            str(run_file),
            "approve",
            "--approval-id",
            "refund-7",
            "--decision",
            "approve",
            "--as",
            "alice@bank.com",
            "--yes",
        )
        check("Signed approval written" in out, "the approval is signed by the approver's key")
        check("Independent time:" in out, "the approval carries an independent RFC 3161 timestamp")

        # ── d. CUSTOMER: pin both keys, verify with the log ─────────────────
        line("\nd. CUSTOMER — pin both fingerprints, verify against their own log")
        bank_vendor_pub = root / "vendor.pub"
        bank_vendor_pub.write_text(sealed_key + "\n", encoding="utf-8")
        epi(bank, "keys", "trust", str(bank_vendor_pub), "--name", "vendor", "--fingerprint", vendor_fp)
        bank_approver_pub = root / "approver.pub"
        bank_approver_pub.write_text(approver_pub_path.read_text(encoding="utf-8"), encoding="utf-8")
        epi(
            bank,
            "approvers",
            "add",
            str(bank_approver_pub),
            "--name",
            "alice@bank.com",
            "--fingerprint",
            approver_fp,
        )
        verified = epi(
            bank,
            "verify",
            str(run_file),
            "--policy",
            "strict",
            "--require-human-approval",
            "--witness-log",
            str(witness_log),
        )
        check("Human approval: VERIFIED" in verified, "strict verify passes (approval + identity)")
        check("Witness" in verified, "the witness line is reported")

        # ── e. FORGERY: same workflow, changed decision, re-sealed ──────────
        line("\ne. FORGERY — the vendor re-seals a different decision with their own key")
        subprocess.run(
            [
                PY,
                str(HERE / "run_witness_pilot.py"),
                "--role",
                "forge",
                "--in",
                str(run_file),
                "--out",
                str(forged_file),
            ],
            cwd=HERE,
            env={**os.environ, **vendor},
            check=True,
        )
        forged_plain = epi(bank, "verify", str(forged_file))
        check("Signature:    Valid" in forged_plain, "the forgery's signature is VALID (same vendor key)")
        check("Integrity:    Verified" in forged_plain, "the forgery's integrity is VERIFIED")
        line("  -> without the witness log, this file looks like a real record of the same case")

        caught = epi(bank, "verify", str(forged_file), "--witness-log", str(witness_log), expect=1)
        check(
            "NOT THE VERSION REPORTED TO YOU" in caught
            or "NOT IN WITNESS LOG" in caught
            or "different version of this case" in caught,
            "with the log, the forgery is caught (headline: not the version reported to you)",
        )

        # ── e2. Same claim, NEW workflow id (the vendor "re-ran" it) ────────
        line("\ne2. FORGERY — same claim, new workflow id (re-run with a different outcome)")
        rerun_file = root / "run-rerun.epi"
        subprocess.run(
            [
                PY,
                str(HERE / "run_witness_pilot.py"),
                "--role",
                "forge",
                "--in",
                str(run_file),
                "--out",
                str(rerun_file),
                "--new-workflow",
            ],
            cwd=HERE,
            env={**os.environ, **vendor},
            check=True,
        )
        rerun_report = epi(
            bank,
            "witness",
            "report",
            "--log",
            str(witness_log),
            "--cases",
            str(rerun_file),
        )
        check(
            "a different version of" in rerun_report or "MISMATCH" in rerun_report,
            "the report ties the re-run to the claim it re-ran, not 'never reported'",
        )
        rerun_verify = epi(
            bank,
            "verify",
            str(rerun_file),
            "--witness-log",
            str(witness_log),
            expect=1,
        )
        check(
            "DIFFERENT VERSION" in rerun_verify,
            "epi verify uses the same stronger wording, not 'NOT IN WITNESS LOG'",
        )

        # ── f. The customer's case report ───────────────────────────────────
        line("\nf. CUSTOMER — one report over the whole case")
        report = epi(
            bank,
            "witness",
            "report",
            "--log",
            str(witness_log),
            "--cases",
            str(run_file),
            "--cases",
            str(forged_file),
        )
        check("CLM-9001" in report, "the report names the claim, not just a workflow id")
        check("WITNESSED" in report, "the run they were told about is WITNESSED")
        check("MISMATCH" in report, "the re-sealed copy is MISMATCH")

        cases_csv = root / "cases.csv"
        cases_csv.write_text("claim_id\nCLM-9001\nCLM-2002\n", encoding="utf-8")
        expected = epi(
            bank,
            "witness",
            "report",
            "--log",
            str(witness_log),
            "--expect",
            str(cases_csv),
        )
        check("CLM-9001" in expected and "FOUND" in expected, "the claim they know is FOUND")
        check("CLM-2002" in expected and "MISSING" in expected, "a claim with no record is MISSING")

        failing = epi(
            bank,
            "witness",
            "report",
            "--log",
            str(witness_log),
            "--cases",
            str(forged_file),
            "--fail-on-unwitnessed",
            expect=1,
        )
        check("MISMATCH" in failing, "--fail-on-unwitnessed exits 1 for the forged copy")
    finally:
        server.shutdown()
        server.server_close()

    line("\nWhat this proves")
    line("  - the witness payload is hash-only: the customer learns a seal happened, not its content")
    line("  - a signature protects the file from edits; it cannot stop the vendor rebuilding it")
    line("  - the customer's own log is what makes a rebuilt record detectable")
    line("\nWhat it does not prove")
    line("  - that the decision was right, or that the agent did what the log says it did")
    line("  - that a vendor who reports the forgery too would be caught: the witness records")
    line("    what was reported, not what happened")
    line(f"\nartifacts kept in {root}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("vendor", "forge"))
    parser.add_argument("--out")
    parser.add_argument("--infile", "--in", dest="infile")
    parser.add_argument("--new-workflow", action="store_true")
    parser.add_argument("--witness-url")
    parser.add_argument("--witness-secret")
    args = parser.parse_args()
    if args.role == "vendor":
        raise SystemExit(role_vendor(args))
    if args.role == "forge":
        raise SystemExit(role_forge(args))
    raise SystemExit(main())
