#!/usr/bin/env python3
"""
EPI Verify — GitHub Action verification script.

Scans a path for .epi files, verifies integrity and signatures,
and outputs results for the GitHub Actions runner.
"""

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


def find_epi_files(path: str) -> list:
    """Find all .epi files in path."""
    p = Path(path)
    if p.is_file() and p.suffix == '.epi':
        return [p]
    if p.is_dir():
        return sorted(p.rglob("*.epi"))
    return []


def verify_single(epi_path: Path) -> dict:
    """Verify a single .epi file."""
    result = {
        "file": str(epi_path),
        "name": epi_path.name,
        "valid_archive": False,
        "has_manifest": False,
        "has_steps": False,
        "signed": False,
        "signature_valid": None,
        "tampered": False,
        "error": None,
    }

    try:
        if not zipfile.is_zipfile(epi_path):
            result["error"] = "Not a valid ZIP archive"
            result["tampered"] = True
            return result

        result["valid_archive"] = True

        with zipfile.ZipFile(epi_path, 'r') as zf:
            names = zf.namelist()

            # Check manifest
            if 'manifest.json' in names:
                result["has_manifest"] = True
                manifest = json.loads(zf.read('manifest.json').decode('utf-8'))

                # Check signature
                if manifest.get("signature"):
                    result["signed"] = True

                    # Verify signature using epi_core
                    try:
                        from epi_core.trust import verify_signature
                        from epi_core.schemas import ManifestModel

                        manifest_model = ManifestModel(**manifest)

                        # Extract public key from manifest (stored as hex)
                        public_key_hex = manifest.get("public_key")
                        if public_key_hex:
                            public_key_bytes = bytes.fromhex(public_key_hex)
                            is_valid, msg = verify_signature(manifest_model, public_key_bytes)
                            result["signature_valid"] = is_valid
                            if not is_valid:
                                result["tampered"] = True
                                result["error"] = msg
                        else:
                            # Signed but no public key embedded — can't verify
                            result["signature_valid"] = None
                            result["error"] = "Signed but no public key in manifest"
                    except Exception as e:
                        result["signature_valid"] = False
                        result["error"] = f"Signature verification failed: {e}"
                        result["tampered"] = True

                # Check file hashes
                file_hashes = manifest.get("file_hashes", {})
                if file_hashes:
                    import hashlib
                    for filename, expected_hash in file_hashes.items():
                        if filename in names:
                            actual = hashlib.sha256(zf.read(filename)).hexdigest()
                            if actual != expected_hash:
                                result["tampered"] = True
                                result["error"] = f"Hash mismatch: {filename}"
                                break
            else:
                result["error"] = "Missing manifest.json"
                result["tampered"] = True

            # Check steps
            if 'steps.jsonl' in names:
                result["has_steps"] = True

    except Exception as e:
        result["error"] = str(e)
        result["tampered"] = True

    return result


def generate_github_summary(results: list, total: int, verified: int, tampered: int, unsigned: int):
    """Generate GitHub Step Summary markdown."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    lines = [
        "## 🔒 EPI Verification Results\n",
        f"| Metric | Count |",
        f"|:-------|------:|",
        f"| Total .epi files | {total} |",
        f"| ✅ Verified | {verified} |",
        f"| ❌ Tampered | {tampered} |",
        f"| ⚠️ Unsigned | {unsigned} |",
        "",
    ]

    if results:
        lines.append("### Details\n")
        lines.append("| File | Signed | Valid | Status |")
        lines.append("|:-----|:------:|:-----:|:------:|")

        for r in results:
            signed = "✅" if r["signed"] else "⚠️"
            valid = "✅" if r["signature_valid"] else ("❌" if r["tampered"] else "—")
            status = "❌ TAMPERED" if r["tampered"] else "✅ OK"
            lines.append(f"| `{r['name']}` | {signed} | {valid} | {status} |")

    lines.append("")
    lines.append(f"*Verified by [EPI Recorder](https://github.com/mohdibrahimaiml/epi-recorder)*")

    with open(summary_file, "a") as f:
        f.write("\n".join(lines) + "\n")


def set_output(name: str, value: str):
    """Set a GitHub Actions output variable."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        # Fallback for local testing
        print(f"::set-output name={name}::{value}")


def main():
    parser = argparse.ArgumentParser(description="Verify EPI recordings")
    parser.add_argument("--path", required=True, help="Path to .epi files")
    parser.add_argument("--fail-on-tampered", default="true")
    parser.add_argument("--fail-on-unsigned", default="false")
    parser.add_argument("--generate-summary", default="true")
    args = parser.parse_args()

    fail_tampered = args.fail_on_tampered.lower() == "true"
    fail_unsigned = args.fail_on_unsigned.lower() == "true"
    gen_summary = args.generate_summary.lower() == "true"

    # Find files
    epi_files = find_epi_files(args.path)

    if not epi_files:
        print("⚠️  No .epi files found")
        set_output("total", "0")
        set_output("verified", "0")
        set_output("tampered", "0")
        set_output("unsigned", "0")
        set_output("result", "pass")
        return

    # Verify each file
    results = []
    for epi_file in epi_files:
        print(f"Verifying: {epi_file.name} ... ", end="")
        result = verify_single(epi_file)
        results.append(result)

        if result["tampered"]:
            print(f"❌ TAMPERED ({result.get('error', 'unknown')})")
        elif not result["signed"]:
            print("⚠️  UNSIGNED (valid archive)")
        else:
            print("✅ VERIFIED")

    # Count results
    total = len(results)
    tampered = sum(1 for r in results if r["tampered"])
    unsigned = sum(1 for r in results if not r["signed"] and not r["tampered"])
    verified = total - tampered - unsigned

    # Set outputs
    set_output("total", str(total))
    set_output("verified", str(verified))
    set_output("tampered", str(tampered))
    set_output("unsigned", str(unsigned))

    # Generate summary
    if gen_summary:
        generate_github_summary(results, total, verified, tampered, unsigned)

    # Determine pass/fail
    failed = False
    if fail_tampered and tampered > 0:
        print(f"\n❌ FAIL: {tampered} tampered file(s) found")
        failed = True
    if fail_unsigned and unsigned > 0:
        print(f"\n❌ FAIL: {unsigned} unsigned file(s) found")
        failed = True

    if failed:
        set_output("result", "fail")
        sys.exit(1)
    else:
        print(f"\n✅ PASS: {verified}/{total} verified, {unsigned} unsigned")
        set_output("result", "pass")


if __name__ == "__main__":
    main()
