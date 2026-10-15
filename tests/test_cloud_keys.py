"""M5 key registry: public keys only, and registered is never pinned.

Proves the plan's rule end to end: a vendor key listed in EPI Cloud changes
nothing until the reviewer pins the exact fingerprint they confirmed with
the sender (`epi keys trust --from-cloud slug --fingerprint ...`).
"""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.cloud import app as cloud_app
from epi_cli.main import app as cli_app
from tests.test_registry_trust import _as_auditor, _sealing_key
from tests.test_seal_witness import _hermetic

runner = CliRunner()
PUB = "92dc7b40403f6383527773b35eb9305ddf01306889ad4e9987a098e6304bead0"
FP = "7004 fce0 a4a9 2327"

CREDS = ["--url", "https://cloud.test", "--org", "o1", "--api-key", "epik_x"]


class FakeResponse:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, *args, **kwargs):
        FakeClient.instances.append(self)
        self.calls: list[dict] = []
        self.routes: dict[tuple[str, str], FakeResponse] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _call(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for (m, suffix), res in self.routes.items():
            if m == method and url.endswith(suffix):
                return res
        return FakeResponse(404, {})

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("DELETE", url, **kwargs)


def _client_with(routes: dict):
    def patched_init(self, *args, **kwargs):
        FakeClient.instances.append(self)
        self.calls = []
        self.routes = routes

    return type("CannedClient", (FakeClient,), {"__init__": patched_init})


def _cloud_keys_doc(keys: list[dict]) -> dict:
    return {"org": "acme", "keys": keys}


class _UrlopenResp:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_cloud_keys(monkeypatch, doc: dict, calls: list | None = None):
    import urllib.request

    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if calls is not None:
            calls.append(url)
        return _UrlopenResp(json.dumps(doc).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _open)


def test_push_refuses_anything_but_pub(monkeypatch, tmp_path: Path) -> None:
    for name, content in [
        ("key.key", "00" * 32),
        ("note.txt", PUB),
        ("junk.pub", "not hex at all"),
        ("short.pub", "abcd"),
        ("pem.pub", "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"),
    ]:
        target = tmp_path / name
        target.write_text(content)
        res = runner.invoke(cloud_app, ["keys", "push", str(target), *CREDS])
        assert res.exit_code == 2, (name, res.output)
        assert "only *.pub" in res.output or "Refusing" in res.output


def test_push_list_revoke_roundtrip(monkeypatch) -> None:
    routes = {
        ("POST", "keys"): FakeResponse(201, {"id": "key_1", "fingerprint": "7004fce0a4a92327"}),
        ("GET", "keys"): FakeResponse(200, {"keys": [{
            "id": "key_1", "fingerprint": "7004fce0a4a92327", "label": "prod",
            "valid_from": "2026-10-16T00:00:00Z", "revoked_at": None,
        }]}),
    }
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(routes))
        with tempfile.TemporaryDirectory() as tmp:
            pub = Path(tmp) / "prod.pub"
            pub.write_text(PUB + "\n")
            res = runner.invoke(cloud_app, ["keys", "push", str(pub), "--label", "prod", *CREDS])
            assert res.exit_code == 0, res.output
            assert "7004fce0a4a92327" in res.output
            assert "informational only" in res.output
            res = runner.invoke(cloud_app, ["keys", "list", *CREDS])
            assert res.exit_code == 0 and "prod" in res.output
    revoke_routes = {
        ("GET", "keys"): FakeResponse(200, {"keys": [{
            "id": "key_1", "fingerprint": "7004fce0a4a92327", "revoked_at": None,
        }]}),
        ("POST", "revoke"): FakeResponse(200, {"ok": True}),
    }
    with pytest.MonkeyPatch().context() as mp:
        import httpx

        mp.setattr(httpx, "Client", _client_with(revoke_routes))
        res = runner.invoke(cloud_app, ["keys", "revoke", "7004fce0a4a92327", *CREDS])
        assert res.exit_code == 0, res.output


def test_trust_from_cloud_needs_fingerprint(monkeypatch, tmp_path: Path) -> None:
    trust_dir = tmp_path / "trusted"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))
    doc = _cloud_keys_doc([{
        "public_key": PUB, "fingerprint": "7004fce0a4a92327", "revoked_at": None,
    }])
    calls: list = []
    _fake_cloud_keys(monkeypatch, doc, calls)
    res = runner.invoke(cli_app, ["keys", "trust", "--from-cloud", "acme", "--name", "vendor"])
    assert res.exit_code == 1, res.output
    assert "Not pinned" in res.output
    assert list(trust_dir.glob("*.pub")) == [], "fetching must never pin"
    assert calls == [], "no fetch should happen before the fingerprint gate"


def test_trust_from_cloud_rejects_mismatch_and_revoked(monkeypatch, tmp_path: Path) -> None:
    trust_dir = tmp_path / "trusted"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))
    doc = _cloud_keys_doc([{
        "public_key": PUB, "fingerprint": "7004fce0a4a92327", "revoked_at": None,
    }])
    _fake_cloud_keys(monkeypatch, doc)
    res = runner.invoke(cli_app, ["keys", "trust", "--from-cloud", "acme",
                                  "--fingerprint", "ffff ffff ffff ffff", "--name", "vendor"])
    assert res.exit_code == 1, res.output
    assert list(trust_dir.glob("*.pub")) == []
    revoked = _cloud_keys_doc([{
        "public_key": PUB, "fingerprint": "7004fce0a4a92327",
        "revoked_at": "2026-10-16T00:00:00Z",
    }])
    _fake_cloud_keys(monkeypatch, revoked)
    res = runner.invoke(cli_app, ["keys", "trust", "--from-cloud", "acme",
                                  "--fingerprint", FP, "--name", "vendor"])
    assert res.exit_code == 1, res.output
    assert "revoked" in res.output.lower()
    assert list(trust_dir.glob("*.pub")) == []


def test_registered_is_not_pinned_until_fingerprint_confirmed(monkeypatch, tmp_path: Path) -> None:
    """The plan's rule, end to end: cloud listing changes nothing; the
    confirmed fingerprint pins; strict verify then passes."""
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    from epi_recorder import record

    out = tmp_path / "run.epi"
    with record(str(out)) as epi:
        epi.log_step("agent.decision", {"content": "hello", "decision": "approve"})
    key = _sealing_key(out)
    from epi_core.keys import key_fingerprint

    fp = key_fingerprint(key)
    doc = _cloud_keys_doc([{
        "public_key": key, "fingerprint": fp.replace(" ", ""), "revoked_at": None,
    }])
    calls: list = []
    _fake_cloud_keys(monkeypatch, doc, calls)
    _as_auditor(monkeypatch, tmp_path)

    # 1. Listed in the cloud, but nothing pinned: strict FAILs, no network.
    res = runner.invoke(cli_app, ["verify", str(out), "--policy", "strict", "--json"])
    assert res.exit_code == 1, res.output
    assert json.loads(res.output)["identity"]["status"] == "UNKNOWN"
    assert not any("/o/" in url for url in calls), "verify must never consult the cloud registry"

    # 2. Pinning with the confirmed fingerprint works.
    res = runner.invoke(cli_app, ["keys", "trust", "--from-cloud", "acme",
                                  "--fingerprint", fp, "--name", "vendor"])
    assert res.exit_code == 0, res.output
    assert any("/o/acme/keys.json" in url for url in calls)

    # 3. Now strict passes with a pinned identity.
    res = runner.invoke(cli_app, ["verify", str(out), "--policy", "strict", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["identity"]["status"] == "KNOWN"
