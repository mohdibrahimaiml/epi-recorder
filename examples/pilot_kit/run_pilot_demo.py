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
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
PY = sys.executable
#: The URI from docs/PILOT-GUIDE.md step 3, with the module path filled in. It
#: must stay identical to the guide's (minus the path); a test enforces that.
VAULT_URI = "pkcs11:token=epi-pilot;object=epi-sealer?module-path={module}"
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


SOFTHSM_LIBS = (
    "/usr/lib/softhsm/libsofthsm2.so",
    "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
    "/usr/local/lib/softhsm/libsofthsm2.so",
    "/opt/homebrew/lib/softhsm/libsofthsm2.so",
)
VAULT_TOKEN_LABEL = "epi-pilot"
VAULT_PIN = "1234"


def softhsm_library() -> str | None:
    if shutil.which("softhsm2-util") is None:
        return None
    return next((p for p in SOFTHSM_LIBS if Path(p).is_file()), None)


def prepare_softhsm(root: Path) -> dict[str, str]:
    """Create a SoftHSM token with an Ed25519 key, as docs/KEY-CUSTODY.md says.

    Returns the env a sealing process needs (the token dir and the PIN — the PIN
    is an env var on purpose; a PIN never goes in the URI).
    """
    import pkcs11
    from pkcs11 import Attribute, KeyType, Mechanism
    from pkcs11.util.ec import encode_named_curve_parameters

    tokens = root / "softhsm-tokens"
    tokens.mkdir(parents=True, exist_ok=True)
    conf = root / "softhsm2.conf"
    conf.write_text(f"directories.tokendir = {tokens}\nobjectstore.backend = file\n")

    # The library reads SOFTHSM2_CONF once per process, so the token dir must be in
    # *this* process's environment too — not only the children's — or `pkcs11.lib`
    # below looks in the system token store and never sees the token we just made.
    os.environ["SOFTHSM2_CONF"] = str(conf)
    os.environ.setdefault("EPI_PKCS11_PIN", VAULT_PIN)
    env = dict(os.environ)
    subprocess.run(
        [
            "softhsm2-util", "--init-token", "--free",
            "--label", VAULT_TOKEN_LABEL, "--pin", VAULT_PIN, "--so-pin", "5678",
        ],
        check=True, capture_output=True, env=env,
    )
    lib = pkcs11.lib(softhsm_library())
    with lib.get_token(token_label=VAULT_TOKEN_LABEL).open(user_pin=VAULT_PIN, rw=True) as session:
        params = session.create_domain_parameters(
            KeyType.EC_EDWARDS,
            {Attribute.EC_PARAMS: encode_named_curve_parameters("1.3.101.112")},
            local=True,
        )
        params.generate_keypair(
            mechanism=Mechanism.EC_EDWARDS_KEY_PAIR_GEN, store=True, label="epi-sealer"
        )
    return {"SOFTHSM2_CONF": str(conf), "EPI_PKCS11_PIN": VAULT_PIN}


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
    line("\na. VENDOR — sealing key in the vault, then run the agent")
    vault_ready = False
    vault_lib = softhsm_library()
    if vault_lib:
        try:
            vendor.update(prepare_softhsm(root))
            uri = VAULT_URI.format(module=vault_lib)
            line(f"  SoftHSM token '{VAULT_TOKEN_LABEL}' ready ({vault_lib})")
            # Link only — never `epi keys generate` first. A key file is exactly
            # what the vault path exists to avoid, and `link` refuses if one
            # exists.
            epi(vendor, "keys", "link", "--name", "default", "--uri", uri, quiet=False)
            vendor["EPI_REQUIRE_EXTERNAL_KEY"] = "1"
            check(True, "the sealing key is in the vault (epi keys link succeeded)")
            vault_ready = True
        except Exception as exc:  # noqa: BLE001 - report, then fall back loudly
            # Name the type and print the traceback: several SoftHSM/`pkcs11`
            # errors stringify to nothing, which is not a diagnosis.
            line(
                f"  WARNING: SoftHSM is present but unusable: "
                f"{type(exc).__name__}: {exc}"
            )
            traceback.print_exc()
    if not vault_ready:
        line("  WARNING: SoftHSM not available — falling back to a key file.")
        line("           This is NOT vault-backed; install softhsm2 for the real path.")
        if os.environ.get("EPI_PILOT_REQUIRE_VAULT", "").strip() == "1":
            check(
                False,
                "EPI_PILOT_REQUIRE_VAULT=1 but the demo fell back to a key file "
                "(install softhsm2 + the [pkcs11] extra)",
            )
        vendor["EPI_REQUIRE_EXTERNAL_KEY"] = "0"
        # Only because no vault exists on this machine. On a real one the key is
        # created inside the vault and `link` is the last step, not this one.
        epi(vendor, "keys", "generate", expect=0)

    run([PY, "agent.py", "--out", str(run_file)], env=vendor)
    check(run_file.is_file(), "the vendor sealed run.epi")
    if vault_ready:
        keys_dir = Path(vendor["EPI_KEYS_DIR"])
        leftovers = sorted(p.name for p in keys_dir.glob("*.key")) if keys_dir.is_dir() else []
        check(not leftovers, f"the vendor home holds no key file (found {leftovers})")

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
