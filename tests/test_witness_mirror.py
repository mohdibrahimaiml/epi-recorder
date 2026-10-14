"""Mirror script: fetches checkpoints + key, writes only on change."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from scripts.mirror_witness_checkpoints import mirror


class _Resp:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _handle(url, timeout=None):
    u = url.full_url if hasattr(url, "full_url") else str(url)
    if u.endswith("/.well-known/epi-witness-key.json"):
        return _Resp(json.dumps({"witness_ed25519_pub_hex": "ab"}).encode())
    if u.endswith("/checkpoints"):
        inbox = u.rsplit("/w/", 1)[-1].rsplit("/", 1)[0]
        return _Resp(json.dumps({"inbox": inbox, "checkpoints": []}).encode())
    raise AssertionError(u)


def test_mirror_writes_and_skips_unchanged(tmp_path: Path):
    out = tmp_path / "mirror"
    with patch("urllib.request.urlopen", side_effect=_handle):
        assert mirror("https://cloud.epilabs.org", ["inb_a", "inb_b"], out) == [
            "witness-key.json",
            "inb_a.json",
            "inb_b.json",
        ]
        assert mirror("https://cloud.epilabs.org", ["inb_a", "inb_b"], out) == []
    assert json.loads((out / "inb_a.json").read_text())["inbox"] == "inb_a"
