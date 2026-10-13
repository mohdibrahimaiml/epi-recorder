"""WP-SEC-4: the remote trust registry must never grant trust.

The public registry at epilabs.org/.well-known/epi-trust-registry.json is
unsigned static JSON. Anyone who controls that file must not be able to make
every verifier in the world accept their key as a trusted identity.

Rules pinned here:
  1. A key listed ONLY in the remote registry: WARN under standard (never
     PASS), FAIL under strict (exit 1). Status stays UNKNOWN; the listing is
     shown as information ("not a pin").
  2. A locally pinned key still PASSes (local pins win over listings).
  3. Under --policy strict the remote registry is never fetched at all
     (strict is local-only, no network).
  4. A remote revocation still downgrades (safe to honour) — including when
     the same key is also listed.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.test_seal_witness import _hermetic

runner = CliRunner()


def _seal(monkeypatch, tmp_path: Path) -> Path:
    from epi_recorder import record

    out = tmp_path / "run.epi"
    with record(str(out)) as epi:
        epi.log_step("agent.decision", {"content": "hello", "decision": "approve"})
    return out


def _sealing_key(out: Path) -> str:
    from epi_core.container import EPIContainer

    manifest = EPIContainer.read_manifest(out)
    assert manifest.public_key, "sealed file must carry a public key"
    return manifest.public_key


class _FakeRegistryResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _fake_registry(monkeypatch, payload: dict, calls: list | None = None):
    import requests

    def _get(url, timeout=5):  # noqa: ANN001, ANN202
        if calls is not None:
            calls.append(url)
        return _FakeRegistryResponse(payload)

    monkeypatch.setattr(requests, "get", _get)


def _pin_locally(key_hex: str, trust_dir: Path, name: str = "vendor") -> None:
    (trust_dir / f"{name}.pub").write_text(key_hex, encoding="utf-8")


def _as_auditor(monkeypatch, tmp_path: Path) -> None:
    """Become the bank's machine: no local signing keys, empty trust dir kept.

    The hermetic seal uses the local 'default' key, which the sealer's own
    machine recognizes (LOCAL status). A real verifier never holds the
    sealer's private key, so point key storage at fresh dirs after sealing.
    """
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "auditor-home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "auditor-home" / "keys"))


def test_remote_listing_is_warn_not_pass_under_standard(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _as_auditor(monkeypatch, tmp_path)
    calls: list = []
    _fake_registry(monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": []}, calls)

    res = runner.invoke(cli_app, ["verify", str(out), "--json"])
    assert res.exit_code == 0, res.output
    report = json.loads(res.output)
    assert calls, "standard policy must consult the registry (then distrust it)"
    assert report["identity"]["status"] == "UNKNOWN", report["identity"]
    assert report["decision"]["status"] == "WARN", report["decision"]
    assert "LISTED" in report["identity"]["detail"]
    assert "not a pin" in report["identity"]["detail"]


def test_remote_listing_fails_under_strict(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _as_auditor(monkeypatch, tmp_path)
    _fake_registry(monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": []})

    res = runner.invoke(cli_app, ["verify", str(out), "--policy", "strict", "--json"])
    assert res.exit_code == 1, res.output
    report = json.loads(res.output)
    assert report["decision"]["status"] == "FAIL", report["decision"]
    assert report["identity"]["status"] == "UNKNOWN", report["identity"]


def test_strict_makes_no_registry_request(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _as_auditor(monkeypatch, tmp_path)
    calls: list = []
    _fake_registry(monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": []}, calls)

    res = runner.invoke(cli_app, ["verify", str(out), "--policy", "strict", "--json"])
    assert res.exit_code == 1, res.output  # FAIL on identity, with zero network
    assert calls == [], f"strict fetched the registry: {calls}"


def test_local_pin_still_passes_despite_listing(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    trust_dir = tmp_path / "trusted"
    trust_dir.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trust_dir))
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _fake_registry(monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": []})
    _pin_locally(key, trust_dir, "vendor")

    res = runner.invoke(cli_app, ["verify", str(out), "--json"])
    assert res.exit_code == 0, res.output
    report = json.loads(res.output)
    assert report["identity"]["status"] == "KNOWN", report["identity"]
    assert report["decision"]["status"] == "PASS", report["decision"]


def test_remote_revocation_still_downgrades(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _as_auditor(monkeypatch, tmp_path)
    # Listed AND revoked remotely: revocation must win (safe direction).
    _fake_registry(
        monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": [key]}
    )

    res = runner.invoke(cli_app, ["verify", str(out), "--json"])
    report = json.loads(res.output)
    assert report["identity"]["status"] == "REVOKED", report["identity"]
    assert report["decision"]["status"] in ("FAIL", "WARN"), report["decision"]


def test_registry_line_in_human_output(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(tmp_path / "trusted"))
    (tmp_path / "trusted").mkdir()
    out = _seal(monkeypatch, tmp_path)
    key = _sealing_key(out)
    _as_auditor(monkeypatch, tmp_path)
    _fake_registry(monkeypatch, {"trusted_keys": {key: "Mallory"}, "revoked_keys": []})

    res = runner.invoke(cli_app, ["verify", str(out)])
    assert res.exit_code == 0, res.output
    import re

    text = re.sub(r"[│\s]+", " ", res.output)
    assert 'Registry: listed as "Mallory" by epilabs.org (not a pin)' in text, res.output
