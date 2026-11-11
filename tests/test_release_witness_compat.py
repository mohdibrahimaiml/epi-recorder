"""An old witness receiver (only `epi.sealed`) must see no hole for a release.

A release is a numbered seal. Before this fix the release was reported only as
`epi.release`; a receiver that predates that type rejected it, so the customer's
log had a hole and `epi witness audit` falsely said `MISSING #N`. The client now
sends a normal `epi.sealed` report for every release, with the release detail
as an extra.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.keys import KeyManager, fingerprint_for_private_key
from epi_core.release import document_digest
from epi_core.schemas import ManifestModel, ReleaseModel
from epi_core.seal_ledger import analyze
from epi_core.trust import sign_manifest
from epi_core.webhook import report_release, report_seal


def _legacy_release(tmp: Path, key, *, release_id: str = "rel_compat") -> Path:
    document = {
        "release_id": release_id,
        "name": "compat-policy",
        "version": "1.0",
        "created_at": "2026-11-09T00:00:00Z",
        "required_approvals": 1,
        "components": [],
        "release_digest": "",
    }
    document["release_digest"] = document_digest(document)
    work = tmp / "release-work"
    work.mkdir()
    (work / "release.json").write_text(json.dumps(document), encoding="utf-8")
    out = tmp / "release.epi"
    EPIContainer.pack(
        work,
        ManifestModel(
            goal="release compat",
            record_kind="release",
            release=ReleaseModel(**document),
        ),
        out,
        signer_function=lambda current: sign_manifest(current, key, "default"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
    )
    return out


def _plain_seal(tmp: Path, key, name: str) -> Path:
    work = tmp / f"{name}-work"
    work.mkdir()
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {"n": 1}}) + "\n",
        encoding="utf-8",
    )
    out = tmp / f"{name}.epi"
    EPIContainer.pack(
        work,
        ManifestModel(goal=name),
        out,
        signer_function=lambda current: sign_manifest(current, key, "default"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
    )
    return out


class _OldReceiver(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def test_old_receiver_accepts_only_seals_and_audit_is_clean(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    keys = home / "keys"
    keys.mkdir(parents=True)
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(keys))
    key = KeyManager(keys_dir=keys)
    key.generate_keypair("default")
    private_key = key.load_private_key("default")

    received: list[dict] = []
    rejected: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: ANN002
            return

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except Exception:
                self.send_response(400)
                self.end_headers()
                return
            if payload.get("type") == "epi.sealed":
                received.append(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
            else:
                rejected.append(str(payload.get("type") or ""))
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unknown report type"}')

    server = _OldReceiver(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        release = _legacy_release(tmp_path, private_key)
        entry = report_release(
            release,
            urls=[url],
            secret="test-secret",
            key_name="default",
            signer=private_key,
            timeout_seconds=10,
        )
        assert entry is not None
        assert (entry.get("_seal_outcome") or {}).get("delivered"), entry
        assert "epi.release" in rejected

        for index in (2, 3):
            seal = _plain_seal(tmp_path, private_key, f"seal-{index}")
            reported = report_seal(
                seal,
                urls=[url],
                secret="test-secret",
                key_name="default",
                signer=private_key,
                timeout_seconds=10,
            )
            assert reported is not None
            assert (reported.get("_outcome") or {}).get("delivered"), reported
    finally:
        server.shutdown()

    assert [item.get("seal_seq") for item in received] == [1, 2, 3]
    result = analyze(received)
    assert result["ok"] is True, result
    assert result["problems"]["missing"] == 0, result
    assert result["chains"] and result["chains"][0]["contiguous"] is True, result
    assert result["chains"][0]["first_seq"] == 1
    assert result["chains"][0]["last_seq"] == 3

    from epi_core.webhook import witness_capabilities

    caps = witness_capabilities()
    assert caps["seals"] == "✓", caps
    assert caps["releases"] == "✗", caps
    assert caps["heartbeats"] == "?", caps
    assert caps["approvals"] == "?", caps


def test_release_extra_does_not_fork_the_seal_chain() -> None:
    """A receiver that accepts both reports must not see two seals at #1."""
    entries = [
        {
            "type": "epi.sealed",
            "seal_seq": 1,
            "key_fingerprint": "k",
            "ledger_id": "l",
            "prev_seq": 0,
            "prev_content_digest": "genesis",
            "content_digest": "d1",
            "manifest_hash": "m1",
            "file_sha256": "f1",
            "workflow_id": "w1",
        },
        {
            "type": "epi.release",
            "seal_seq": 1,
            "key_fingerprint": "k",
            "ledger_id": "l",
            "prev_seq": 0,
            "prev_content_digest": "genesis",
            "release_id": "rel_1",
        },
    ]
    result = analyze(entries)
    assert result["reports"] == 1, result
    assert result["problems"]["forks"] == 0, result
    assert result["chains"][0]["contiguous"] is True, result
