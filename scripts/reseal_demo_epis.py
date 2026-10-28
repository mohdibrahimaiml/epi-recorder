#!/usr/bin/env python3
"""Re-seal the shipped demo `.epi` samples for the current release.

`tests/test_demo_assets.py` requires every `.epi` under `website/` to carry the
current `spec_version`, so the site never advertises one version while its
samples say another. The samples' *content* is curated (and some was produced
with a live model), so this re-signs the existing artifacts rather than
regenerating their steps: `EPIContainer.refresh_viewer` re-packs the same
payload, restores the container format, refreshes the embedded viewer and
re-signs through the hook below.

The demo key is generated per run and never committed — it signs public sample
files only. Run:

    python scripts/reseal_demo_epis.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from epi_core._version import get_version  # noqa: E402
from epi_core.container import EPIContainer  # noqa: E402
from epi_core.keys import key_fingerprint  # noqa: E402
from epi_core.trust import sign_manifest  # noqa: E402

SAMPLE_DIR = ROOT / "website"


def _stamps(path: Path) -> tuple[object, object]:
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    return manifest.get("spec_version"), manifest.get("producer_version")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report which samples are stale; write nothing",
    )
    args = parser.parse_args()

    version = get_version()
    samples = sorted(SAMPLE_DIR.rglob("*.epi"))
    if not samples:
        print("no .epi samples found under website/", file=sys.stderr)
        return 1

    stale = [path for path in samples if _stamps(path)[0] != version]
    for path in samples:
        spec, producer = _stamps(path)
        flag = "stale" if spec != version else "ok"
        print(f"{path.relative_to(ROOT)}: spec={spec} producer={producer} [{flag}]")

    if args.check:
        print(f"\n{len(stale)} of {len(samples)} sample(s) not at {version}")
        return 1 if stale else 0
    if not stale:
        print(f"\nall {len(samples)} sample(s) already at {version}")
        return 0

    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes_raw().hex()
    print(f"\nre-sealing with a new demo key (fp {key_fingerprint(public_hex)})")

    def signer(manifest):
        # spec_version is "the EPI version that sealed the file"; producer_version
        # says the same thing about the same seal, so they move together.
        manifest.spec_version = version
        manifest.producer_version = version
        return sign_manifest(manifest, key, "epi-demo")

    for path in stale:
        staged = path.with_suffix(".epi.resealed")
        EPIContainer.refresh_viewer(
            path, staged, signer_function=signer, with_viewer=None
        )
        staged.replace(path)
        print(f"  re-sealed {path.relative_to(ROOT)}: {_stamps(path)[0]}")

    print(f"\nre-sealed {len(stale)} sample(s) at {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
