#!/usr/bin/env python3
"""Backward-compatibility gate: HEAD-sealed files must verify on the last release.

The 4.10.0 launch blocker was a format change that only the new verifier
understood. This gate installs the last released ``epi-recorder`` from PyPI and
the current tree side by side, seals plain / witness / release / pre-action
files with HEAD, then:

* runs the **last release's CLI** ``epi verify`` on every file;
* runs the **last release's browser preimage** (``website/js/``) in Node on the
  same manifests.

Any failure blocks the gate. Run locally with:

    python scripts/check_backward_compatibility.py

In CI the workflow passes ``--last-website`` from the last release tag.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _latest_release_version() -> str:
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/epi-recorder/json", timeout=30) as resp:
            data = json.load(resp)
        return str(data["info"]["version"])
    except Exception:
        return "4.9.0"


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )


def _make_venv(venv: Path) -> Path:
    if not _venv_python(venv).exists():
        result = _run([sys.executable, "-m", "venv", str(venv)], timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"venv failed: {result.stderr[-2000:]}")
    return _venv_python(venv)


def _pip_install(python: Path, *args: str) -> None:
    result = _run(
        [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *args],
        timeout=1200,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pip install {' '.join(args)} failed:\n{result.stderr[-4000:]}")


def _plain_seal(head_python: Path, work: Path) -> Path:
    home = work / "plain-home"
    (home / "keys").mkdir(parents=True)
    out = work / "plain.epi"
    code = f"""
from pathlib import Path
from epi_recorder import record
with record(r"{out}", goal="compat plain", with_viewer=False) as epi:
    epi.log_step("custom.test", {{"n": 1}})
"""
    env = os.environ.copy()
    env.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(home / "keys"),
            "EPI_NOTARIZE": "0",
            "EPI_QUIET": "1",
            "EPI_WITNESS_URL": "",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    result = _run([str(head_python), "-c", code], env=env, timeout=600)
    if result.returncode != 0 or not out.exists():
        raise RuntimeError(f"plain seal failed:\n{result.stdout[-2000:]}\n{result.stderr[-3000:]}")
    return out


def _demo_seals(head_python: Path, work: Path) -> list[Path]:
    """Run the shipped demo generator in a temp skeleton (no repo writes)."""
    skeleton = work / "demo-repo"
    (skeleton / "scripts").mkdir(parents=True)
    (skeleton / "website" / "assets" / "demo").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "scripts" / "make_decision_example.py",
        skeleton / "scripts" / "make_decision_example.py",
    )
    env = os.environ.copy()
    env.update(
        {
            "EPI_NOTARIZE": "0",
            "EPI_QUIET": "1",
            "EPI_OVERWRITE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    result = _run(
        [str(head_python), str(skeleton / "scripts" / "make_decision_example.py")],
        cwd=skeleton,
        env=env,
        timeout=1200,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "demo generator failed:\n" + (result.stdout[-4000:] + result.stderr[-4000:])
        )
    return sorted((skeleton / "website" / "assets" / "demo").glob("*.epi"))


def _last_cli_verify(last_python: Path, files: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in files:
        result = _run(
            [str(last_python), "-m", "epi_cli", "verify", str(path), "--json"],
            timeout=300,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode not in (0, 1):
            failures.append(f"{path.name}: last-release CLI exited {result.returncode}\n{output[-1500:]}")
            continue
        try:
            payload = json.loads(output[output.index("{") :])
        except Exception:
            failures.append(f"{path.name}: last-release CLI did not emit JSON\n{output[-1500:]}")
            continue
        facts = payload.get("facts") or {}
        if facts.get("signature_valid") is not True:
            failures.append(f"{path.name}: signature_valid={facts.get('signature_valid')!r}")
        if facts.get("integrity_ok") is not True:
            failures.append(f"{path.name}: integrity_ok={facts.get('integrity_ok')!r}")
        if "SEAL FAIL" in output or "SIGNATURE INVALID" in output:
            failures.append(f"{path.name}: last-release CLI reported a seal failure")
    return failures


# Node harness: load the last release's browser preimage from website/js/.
_NODE_HARNESS = r"""
const fs = require('fs');
require(process.argv[2]);
const raw = fs.readFileSync(process.argv[3], 'utf8');
const manifest = JSON.parse(raw);
(async () => {
  const hash = await globalThis.epiComputeManifestHash(raw);
  const r = await globalThis.epiVerifyEd25519(manifest.signature, manifest.public_key, hash);
  process.stdout.write(JSON.stringify({hash: hash, valid: r.valid, msg: r.msg}));
})().catch((e) => { process.stdout.write(JSON.stringify({error: String(e)})); });
"""


def _browser_preimage_checks(
    files: list[Path], last_website: Path, node: str, work: Path
) -> list[str]:
    preimage = last_website / "website" / "js" / "epi-manifest-preimage.js"
    if not preimage.exists():
        preimage = last_website / "js" / "epi-manifest-preimage.js"
    if not preimage.exists():
        return [f"last release browser preimage not found under {last_website}"]
    harness = work / "verify-preimage.js"
    harness.write_text(_NODE_HARNESS, encoding="utf-8")
    failures: list[str] = []
    for path in files:
        with zipfile.ZipFile(path) as zf:
            raw = zf.read("manifest.json")
        manifest_path = work / f"{path.stem}-manifest.json"
        manifest_path.write_bytes(raw)
        result = _run(
            [node, str(harness), str(preimage), str(manifest_path)],
            timeout=120,
        )
        output = (result.stdout or "") + (result.stderr or "")
        try:
            payload = json.loads(output[output.index("{") :])
        except Exception:
            failures.append(f"{path.name}: browser preimage harness failed\n{output[-1500:]}")
            continue
        if payload.get("valid") is not True:
            failures.append(
                f"{path.name}: last-release browser preimage says {payload.get('valid')!r} "
                f"({payload.get('msg') or payload.get('error')})"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-version", default=None)
    parser.add_argument("--last-website", default=None, help="Checkout of the last release tag")
    parser.add_argument("--node", default=os.environ.get("NODE", "node"))
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    work = Path(args.workdir).resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="epi_compat_"))
    work.mkdir(parents=True, exist_ok=True)
    last_version = args.last_version or _latest_release_version()
    print(f"backward-compatibility gate: HEAD vs epi-recorder {last_version}")

    head_venv = work / "head-venv"
    last_venv = work / "last-venv"
    head_python = _make_venv(head_venv)
    last_python = _make_venv(last_venv)
    if not args.skip_install:
        _pip_install(head_python, "--upgrade", "pip")
        _pip_install(last_python, "--upgrade", "pip")
        _pip_install(head_python, str(ROOT))
        _pip_install(last_python, f"epi-recorder=={last_version}")

    failures: list[str] = []
    try:
        plain = _plain_seal(head_python, work)
        print(f"sealed plain: {plain.name}")
        demo = _demo_seals(head_python, work)
        print(f"sealed demo: {', '.join(p.name for p in demo)}")
    except Exception as exc:
        print(f"FAIL: could not seal with HEAD: {exc}")
        return 1

    files = [plain, *demo]
    failures.extend(_last_cli_verify(last_python, files))

    if args.last_website:
        failures.extend(
            _browser_preimage_checks(files, Path(args.last_website).resolve(), args.node, work)
        )
    else:
        print("WARN: --last-website not supplied; skipped the browser preimage check")

    if failures:
        print("FAIL: backward compatibility")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: {len(files)} HEAD-sealed file(s) verify on epi-recorder {last_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
