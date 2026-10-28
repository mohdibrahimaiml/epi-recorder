#!/usr/bin/env python3
"""The pilot demo, end to end, in three separate EPI_HOME directories.

Vendor → approver → bank. Nothing from the vendor's or approver's home is
visible to the bank, and the bank's home never holds a private key.

Every step prints one plain-English line and the script exits non-zero if an
expectation is not met. Linux/macOS: run_pilot_demo.sh calls this; Windows:
`python run_pilot_demo.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
PY = sys.executable
# Kept identical to the URI in docs/PILOT-GUIDE.md step 3 (a test enforces it).
VAULT_URI = "pkcs11:token=epi-pilot;object=epi-sealer;module-path=/usr/lib/softhsm/libsofthsm2.so"
FAILURES: list[str] = []

try:  # Windows consoles are cp1252; the verifier prints box drawing
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def line(text: str) -> None:
    print(text, flush=True)


def run(args: list[str], *, env: dict[str, str], expect: int = 0, quiet: bool = True) -> str:
    result = subprocess.run(
        args, cwd=str(HERE), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    out = (result.stdout or "") + (result.stderr or "")
    if quiet:
        for candidate in out.splitlines():
            if any(k in candidate for k in ("Human approval", "DECISION:", "Integrity", "Signature", "[X]", "[FAIL]", "[OK]", "WARNING")):
                line("    " + candidate.strip())
    else:
        line(out.rstrip())
    if result.returncode != expect:
        raise RuntimeError(
            f"expected exit {expect}, got {result.returncode}: {' '.join(args)}\n{out}"
        )
    return out


def check(condition: bool, message: str) -> None:
    if condition:
        line(f"  PASS  {message}")
    else:
        FAILURES.append(message)
        line(f"  FAIL  {message}")


def epi_home(root: Path, name: str) -> dict[str, str]:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(home / "keys"),
            "EPI_TRUSTED_KEYS_DIR": str(home / "trusted_keys"),
            "EPI_TRUSTED_APPROVERS_DIR": str(home / "trusted_approvers"),
            "EPI_APPROVER_KEYS_DIR": str(home / "approver_keys"),
            "EPI_NOTARIZE": "0",
            "EPI_TELEMETRY": "0",
            "PYTHONPATH": str(REPO),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def epi(env: dict[str, str], *args: str, expect: int = 0, quiet: bool = True) -> str:
    return run([PY, "-m", "epi_cli", *args], env=env, expect=expect, quiet=quiet)


def softhsm_available() -> bool:
    return shutil.which("softhsm2-util") is not None and any(
        Path(p).exists() for p in ("/usr/lib/softhsm/libsofthsm2.so", "/usr/local/lib/softhsm/libsofthsm2.so")
    )


def public_hex(path: Path) -> str:
    """Raw Ed25519 public key hex from a PEM or 64-hex `.pub` file."""
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
    root = Path(tempfile.mkdtemp(prefix="epi-pilot-"))
    vendor, approver, bank = (epi_home(root, n) for n in ("vendor", "approver", "bank"))
    # The demo sets a password so `approvers keygen` does not prompt. A real
    # approver types their own (docs/HUMAN-APPROVAL.md).
    approver["EPI_KEY_PASSWORD"] = "pilot-demo-password"
    # Re-running the demo must replace the sample run, not create run-2.epi.
    vendor["EPI_OVERWRITE"] = "1"
    run_file = HERE / "run.epi"
    for stale in HERE.glob("run*.epi"):
        stale.unlink()
    line(f"work dir: {root}")

    # ── a. VENDOR: vault-backed key, then record ────────────────────────────
    line("\na. VENDOR — sealing key, then run the agent")
    if softhsm_available():
        # Link only — never `epi keys generate` first. A key file is exactly what
        # the vault path exists to avoid, and `link` refuses when one exists.
        epi(vendor, "keys", "link", "--name", "default", "--uri", VAULT_URI, expect=1, quiet=False)
        line("  SoftHSM is installed; see docs/KEY-CUSTODY.md to create the token, then re-run.")
    else:
        line("  WARNING: SoftHSM not available — falling back to a key file.")
        line("           This is NOT vault-backed; install softhsm2 for the real path.")
    # Only because no vault exists on this machine. On a real one the key is
    # created inside the vault and `link` is the last step, not this one.
    epi(vendor, "keys", "generate", expect=0)
    vendor["EPI_REQUIRE_EXTERNAL_KEY"] = "0"
    run([PY, "agent.py", "--out", str(run_file)], env=vendor)
    check(run_file.is_file(), "the vendor sealed run.epi")

    # ── b. APPROVER: own key, approve both requests ─────────────────────────
    line("\nb. APPROVER — own key, approve both requests")
    epi(approver, "approvers", "keygen", "--name", "alice@bank.com")
    approver_pub_path = Path(approver["EPI_APPROVER_KEYS_DIR"]) / "alice@bank.com.pub"
    approver_pub = approver_pub_path.read_text(encoding="utf-8").strip()
    approver_fp = fingerprint(approver_pub_path)
    line(f"  alice reads this fingerprint aloud: {approver_fp}")
    epi(approver, "approvers", "add", str(Path(approver["EPI_APPROVER_KEYS_DIR"]) / "alice@bank.com.pub"),
        "--name", "alice@bank.com", "--fingerprint", approver_fp)

    before_second = root / "run-after-first-approval.epi"
    epi(approver, "review", str(run_file), "approve", "--approval-id", "refund-7",
        "--decision", "approve", "--as", "alice@bank.com", "--yes")
    shutil.copyfile(run_file, before_second)
    epi(approver, "review", str(run_file), "approve", "--approval-id", "refund-8",
        "--decision", "approve", "--as", "alice@bank.com", "--yes")

    # ── c. BANK: pin by fingerprint, verify ─────────────────────────────────
    line("\nc. BANK — pin the vendor and the approver, then verify")
    vendor_pub_path = root / "vendor.pub"
    shutil.copyfile(Path(vendor["EPI_KEYS_DIR"]) / "default.pub", vendor_pub_path)
    # The bank learns this fingerprint out of band (the vendor reads it aloud).
    vendor_fp = fingerprint(vendor_pub_path)
    epi(bank, "keys", "trust", str(vendor_pub_path), "--name", "vendor", "--fingerprint", vendor_fp)
    bank_pub = root / "approver.pub"
    bank_pub.write_text(approver_pub + "\n", encoding="utf-8")
    epi(bank, "approvers", "add", str(bank_pub), "--name", "alice@bank.com", "--fingerprint", approver_fp)
    out = epi(bank, "verify", str(run_file), "--policy", "strict", "--require-human-approval")
    check("Human approval: VERIFIED" in out, "the bank's strict + require-human-approval verify passes")

    # ── d. tamper one byte ──────────────────────────────────────────────────
    line("\nd. TAMPER — one byte changes the file")
    tampered = root / "tampered.epi"
    blob = bytearray(run_file.read_bytes())
    blob[len(blob) // 2] ^= 0x01
    tampered.write_bytes(bytes(blob))
    out = epi(bank, "verify", str(tampered), expect=1)
    check("FAILED" in out or "FAIL" in out, "the bank rejects the tampered file")

    # ── e. one approval missing ─────────────────────────────────────────────
    line("\ne. INCOMPLETE — only one of the two requests approved")
    out = epi(bank, "verify", str(before_second), "--require-human-approval", expect=1)
    check("INCOMPLETE" in out, "the bank sees INCOMPLETE for the half-approved run")

    # ── the bank home must hold no private key ──────────────────────────────
    line("\nf. BANK home holds no private key")
    keys = list(Path(bank["EPI_KEYS_DIR"]).glob("*.key")) if Path(bank["EPI_KEYS_DIR"]).exists() else []
    approver_dir = Path(bank["EPI_APPROVER_KEYS_DIR"])
    check(keys == [], "no *.key in the bank's EPI_HOME")
    check(not approver_dir.exists() or not any(approver_dir.iterdir()),
          "no approver key material in the bank's EPI_HOME")

    line("")
    if FAILURES:
        line(f"DEMO FAILED ({len(FAILURES)}):")
        for item in FAILURES:
            line(f"  - {item}")
        return 1
    line("DEMO PASSED — record → sign-off → verify → tamper → incomplete, all as expected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
