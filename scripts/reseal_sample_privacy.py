"""Re-seal a sample artifact with a scrubbed environment and a current VERIFY.txt.

A sealed sample is handed to a counterparty, so ``environment.json`` must not
name the builder's machine, and the ``VERIFY.txt`` inside it must state the
version that actually sealed the file. Both are inside the sealed payload, so
the only honest fix is to re-seal: replace the member, recompute the payload
hashes and sign again.

This is the generic path behind ``scripts/check_artifact_privacy.py``: the
triage tool and the remedy live together.

Usage:
    python scripts/reseal_sample_privacy.py --check
    python scripts/reseal_sample_privacy.py
    python scripts/reseal_sample_privacy.py --path docs/assets/readme-demo.epi
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from epi_core._version import get_version  # noqa: E402
from epi_core.container import EPIContainer  # noqa: E402
from epi_core.keys import key_fingerprint  # noqa: E402
from epi_core.trust import sign_manifest  # noqa: E402
from epi_recorder.environment import capture_full_environment  # noqa: E402
from scripts.check_artifact_privacy import SKIP_DIRS, committed_epi_files, findings  # noqa: E402


def _fresh_environment() -> bytes:
    """A snapshot from the current, scrubbed capture path (no host detail)."""
    snapshot = capture_full_environment(include_all_env_vars=False, redact_env_vars=True)
    return json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8")


def _unpack(epi_path: Path, dest: Path) -> bool:
    """Extract the payload to ``dest``; return True when it carried a viewer."""
    payload = dest.parent / "payload.zip"
    EPIContainer.extract_inner_payload(epi_path, payload)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload) as zf:
        zf.extractall(dest)
    return "viewer.html" in {name for name in zipfile.ZipFile(payload).namelist()}


def reseal(path: Path, *, signer, version: str) -> dict:
    """Re-seal one artifact in place. Returns what changed."""
    work = Path(tempfile.mkdtemp(prefix="epi_reseal_"))
    try:
        source = work / "payload"
        had_viewer = _unpack(path, source)
        container_format = EPIContainer.detect_container_format(path)
        manifest = EPIContainer.read_manifest(path)

        changed: list[str] = []
        env_path = source / "environment.json"
        if env_path.exists():
            env_path.write_bytes(_fresh_environment())
            changed.append("environment.json")

        # VERIFY.txt and viewer.html are rewritten by pack(); removing them
        # guarantees the copy inside the file is current instead of preserved.
        for generated in ("VERIFY.txt", "viewer.html"):
            generated_path = source / generated
            if generated_path.exists():
                generated_path.unlink()
                changed.append(generated)

        # Post-seal proof members describe the OLD bytes. Keeping them while
        # re-signing produces a file whose TSA imprint no longer matches, which
        # `epi verify` correctly rejects ("modified and re-signed after
        # sealing"). Drop them and let pack() stamp the new bytes.
        for stale in ("artifacts/notarization", "artifacts/scitt", "artifacts/transparency"):
            stale_dir = source / stale
            if stale_dir.exists():
                shutil.rmtree(stale_dir, ignore_errors=True)
                changed.append(stale)

        manifest.spec_version = version
        manifest.producer_version = version

        staged = work / path.name
        EPIContainer.pack(
            source,
            manifest,
            staged,
            signer_function=signer,
            preserve_generated=True,
            container_format=container_format,
            generate_analysis=False,
            notarize=None,
            embed_viewer=had_viewer,
        )
        shutil.copyfile(staged, path)
        return {"changed": changed, "viewer": had_viewer}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--path", action="append", default=[], help="re-seal this file instead of every leaking one"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="re-seal every committed sample, leaking or not (refreshes VERIFY.txt)",
    )
    args = parser.parse_args(argv)

    version = get_version()
    if args.path:
        targets = [Path(p) for p in args.path]
    else:
        candidates = committed_epi_files()
        targets = list(candidates) if args.all else [p for p in candidates if findings(p)]

    if not targets:
        print("nothing to re-seal")
        return 0

    print(f"re-sealing {len(targets)} artifact(s) at {version}")
    if args.check:
        for path in targets:
            print(f"  would re-seal {path}")
        return 0

    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    print(f"  demo signing key: {key_fingerprint(public_hex)}")

    def signer(manifest):
        return sign_manifest(manifest, key, "epi-sample")

    failures = 0
    for path in targets:
        try:
            info = reseal(path, signer=signer, version=version)
        except Exception as exc:  # noqa: BLE001 - one bad sample must not stop the rest
            print(f"  FAILED {path}: {type(exc).__name__}: {exc}")
            failures += 1
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        remaining = findings(path)
        verdict = "CLEAN" if not remaining else f"STILL LEAKING {remaining}"
        print(
            f"  {path}: spec={version} sha256={digest} "
            f"changed={','.join(info['changed']) or 'signature only'} {verdict}"
        )
        if remaining:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
