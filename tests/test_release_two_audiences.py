"""A release sends a seal report and a release detail to each audience."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.keys import fingerprint_for_private_key
from epi_core.release import document_digest
from epi_core.schemas import ManifestModel, ReleaseModel
from epi_core.seal_ledger import analyze
from epi_core.trust import sign_manifest
from epi_core.audience import derive_audiences
from epi_core.webhook import report_release


class _Receiver:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                try:
                    receiver.payloads.append(json.loads(body))
                except Exception:
                    pass
                self.send_response(202)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):  # noqa: D401 - silence
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def types(self) -> list[str]:
        return [str(p.get("type") or "") for p in self.payloads]


def _release_with_audiences(tmp: Path, key, audiences: list[str], entries: dict) -> Path:
    document = {
        "release_id": "rel_two",
        "name": "two-customer-policy",
        "version": "1.0",
        "created_at": "2026-11-09T00:00:00Z",
        "required_approvals": 1,
        "components": [],
        "release_digest": "",
    }
    document["release_digest"] = document_digest(document)
    work = tmp / "release-two"
    work.mkdir()
    (work / "release.json").write_text(json.dumps(document), encoding="utf-8")
    out = tmp / "release-two.epi"
    EPIContainer.pack(
        work,
        ManifestModel(goal="release two audiences", record_kind="release", release=ReleaseModel(**document)),
        out,
        signer_function=lambda current: sign_manifest(current, key, "default"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
        audiences=audiences,
        seal_entries=entries,
    )
    return out


def test_each_audience_gets_a_seal_and_a_release_and_audits_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    key = Ed25519PrivateKey.generate()
    a, b = _Receiver(), _Receiver()
    try:
        audiences = [derive_audiences(None, [a.url])[0], derive_audiences(None, [b.url])[0]]
        assert audiences[0] != audiences[1]
        entries: dict[str, dict] = {}
        release = _release_with_audiences(tmp_path, key, audiences, entries)

        entry = report_release(
            release,
            urls=[a.url, b.url],
            key_name="default",
            signer=key,
            timeout_seconds=10,
            audience_entries=entries,
        )
        assert entry is not None

        for receiver, audience in ((a, audiences[0]), (b, audiences[1])):
            types = receiver.types()
            assert types.count("epi.sealed") == 1, types
            assert types.count("epi.release") == 1, types
            for payload in receiver.payloads:
                assert payload.get("audience") == audience
            # The receiver's own log is a complete one-seal chain.
            audit = analyze(receiver.payloads)
            assert audit["chains"], receiver.payloads
            assert all(not chain["missing"] for chain in audit["chains"]), audit
            # And it carries nothing about the other audience.
            assert all(payload.get("audience") != audiences[1 if audience == audiences[0] else 0] for payload in receiver.payloads)
    finally:
        a.server.shutdown()
        b.server.shutdown()
