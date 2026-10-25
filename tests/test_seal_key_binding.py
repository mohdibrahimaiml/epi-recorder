"""RFC 3161 seal timestamps bind the signing key (epi-tsa-imprint/v1).

`record()` defers the timestamp to the signed repack, so the imprint names the
key that actually sealed the file. Old seals (imprinted_public_key null) keep
verifying as contents-only. The TSA is mocked: no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_tsa_validation import MiniPKI, make_tsr

GEN_TIME = "2026-05-05T12:00:00Z"


@pytest.fixture()
def pki() -> MiniPKI:
    return MiniPKI()


def _mock_tsa(monkeypatch, tmp_path: Path, pki: MiniPKI) -> None:
    def fake_submit(digest_hex: str, url: str = "") -> bytes:
        return make_tsr(bytes.fromhex(digest_hex), pki)

    monkeypatch.setattr("epi_core.notarize._submit_rfc3161", fake_submit)
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_TSA_URLS", "https://tsa.example.test/tsr")
    monkeypatch.setenv("EPI_NOTARIZE", "1")


def _record(out: Path, **kwargs) -> Path:
    from epi_recorder import record

    with record(str(out), **kwargs) as epi:
        for i in range(3):
            epi.log_step("llm.request", {"provider": "openai", "n": i})
    return out


def _verify_json(out: Path, capsys, **kwargs) -> dict:
    import typer

    from epi_cli.verify import verify_command

    try:
        verify_command(None, out, True, False, None, **kwargs)
    except typer.Exit:
        pass
    return json.loads(capsys.readouterr().out)


def _resign_with(monkeypatch, source: Path, target: Path, key_name: str) -> None:
    """Repack `source` signed by `key_name`, keeping its timestamp record."""
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.trust import sign_manifest

    km = KeyManager()
    km.generate_keypair(key_name, overwrite=True)
    private_key = km.load_private_key(key_name)

    ws = source.parent / f"ws-{key_name}"
    EPIContainer.unpack(source, ws)
    manifest = EPIContainer.read_manifest(source)
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    EPIContainer.pack(
        ws,
        manifest,
        target,
        signer_function=lambda current: sign_manifest(current, private_key, key_name),
        preserve_generated=True,
        generate_analysis=False,
    )


def test_record_seal_binds_the_signing_key(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    out = tmp_path / "run.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint
    from epi_core.notarize import compute_seal_imprint, normalize_imprint_time

    manifest = EPIContainer.read_manifest(out)
    assert manifest.public_key
    notar = EPIContainer.read_member_json(
        out, "artifacts/notarization/notarization.json"
    )
    assert notar["imprinted_public_key"] == manifest.public_key
    recomputed = compute_seal_imprint(
        str(manifest.workflow_id),
        normalize_imprint_time(manifest.created_at),
        notar["imprinted_public_key"],
        dict(manifest.file_manifest or {}),
    )
    assert recomputed == notar["imprinted_digest"]

    report = _verify_json(out, capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert len(seal) == 1
    assert seal[0]["status"] == "valid"
    assert seal[0]["key_bound"] is True
    assert seal[0]["gen_time"] == GEN_TIME
    assert seal[0]["imprinted_key_fingerprint"] == key_fingerprint(
        manifest.public_key, grouped=False
    )
    assert report["timestamps"]["key_binding"] == "key-bound"
    statement = report["timestamps"]["statement"]
    assert "sealed by key" in statement
    assert key_fingerprint(manifest.public_key, grouped=False) in statement
    assert GEN_TIME in statement
    assert report["decision"]["status"] in ("PASS", "WARN")

    import typer

    from epi_cli.verify import verify_command

    try:
        verify_command(None, out, False, False, None, tsa_root=[root_pem])
    except typer.Exit:
        pass
    human = capsys.readouterr().out
    assert "sealed by key" in human
    assert key_fingerprint(manifest.public_key) in human
    assert GEN_TIME in human
    assert "CONTENTS-ONLY" not in human


def test_swapped_signing_key_fails_the_binding(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    out = tmp_path / "run.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint

    original = EPIContainer.read_manifest(out)
    _resign_with(monkeypatch, out, tmp_path / "swapped.epi", "swapped")

    swapped = EPIContainer.read_manifest(tmp_path / "swapped.epi")
    report = _verify_json(tmp_path / "swapped.epi", capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert report["decision"]["status"] == "FAIL"
    assert seal[0]["status"] == "imprint_mismatch"
    assert seal[0]["key_bound"] is False
    assert "signing key changed" in seal[0]["detail"]
    assert key_fingerprint(original.public_key, grouped=False) in seal[0]["detail"]
    assert key_fingerprint(swapped.public_key, grouped=False) in seal[0]["detail"]
    assert report["timestamps"]["key_binding"] == "none"


def test_legacy_null_imprinted_key_verifies_as_contents_only(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    """The pre-change record() shape: stamped unsigned, signed without stamping."""
    unsigned = tmp_path / "unsigned.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(unsigned, auto_sign=False)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    _resign_with(monkeypatch, unsigned, tmp_path / "legacy.epi", "default")

    from epi_core.container import EPIContainer

    notar = EPIContainer.read_member_json(
        tmp_path / "legacy.epi", "artifacts/notarization/notarization.json"
    )
    assert notar["imprinted_public_key"] is None

    report = _verify_json(tmp_path / "legacy.epi", capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert seal[0]["status"] == "valid"
    assert seal[0]["key_bound"] is False
    assert seal[0]["gen_time"] == GEN_TIME
    assert report["timestamps"]["key_binding"] == "contents-only"
    assert "contents-only" in report["timestamps"]["statement"]
    assert report["decision"]["status"] != "FAIL"


def test_scitt_reembed_keeps_key_bound_timestamp(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    """auto_scitt re-signs with the same key: the timestamp must still bind it."""
    import cbor2

    out = tmp_path / "run.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_recorder import auto_scitt as auto_scitt_mod

    km = KeyManager()
    private_key = km.load_private_key("default")
    manifest = EPIContainer.read_manifest(out)
    original_key = manifest.public_key
    assert original_key
    # The default record() shape that auto-SCITT used to crash on.
    assert manifest.governance is None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def register(self, statement: bytes):
            # COSE tag 18 shape: "unverified", never a false "invalid".
            receipt = cbor2.dumps(cbor2.CBORTag(18, b"test-receipt"))
            return receipt, SimpleNamespace(
                entry_id="e1",
                registered_at=GEN_TIME,
                service_url="local",
            )

    monkeypatch.setattr(auto_scitt_mod, "SCITTServiceClient", _Client)
    anchor = auto_scitt_mod.AutoSCITTAnchor(service_url="local", timeout=1)
    anchor._enabled = True
    assert anchor.anchor_if_configured(manifest, out, private_key, "default") is True

    assert EPIContainer.read_member_bytes(out, "artifacts/scitt/receipt.cbor")
    assert EPIContainer.read_manifest(out).public_key == original_key

    report = _verify_json(out, capsys, tsa_root=[root_pem], offline=True)
    seal = report["timestamps"]["seal"]
    assert seal[0]["status"] == "valid"
    assert seal[0]["key_bound"] is True
    assert report["timestamps"]["key_binding"] == "key-bound"
    assert "sealed by key" in report["timestamps"]["statement"]


def test_refresh_viewer_resign_same_key_keeps_key_bound(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    from typer.testing import CliRunner

    from epi_cli.main import app as cli_app

    out = tmp_path / "run.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    result = CliRunner().invoke(cli_app, ["refresh-viewer", str(out), "--resign"])
    assert result.exit_code == 0, result.output

    report = _verify_json(out, capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert seal[0]["status"] == "valid"
    assert seal[0]["key_bound"] is True
    assert report["timestamps"]["key_binding"] == "key-bound"


def test_refresh_viewer_resign_different_key_breaks_binding(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    from typer.testing import CliRunner

    from epi_cli.main import app as cli_app
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager, key_fingerprint

    out = tmp_path / "run.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")
    original_key = EPIContainer.read_manifest(out).public_key

    KeyManager().generate_keypair("other", overwrite=True)
    result = CliRunner().invoke(
        cli_app, ["refresh-viewer", str(out), "--resign", "--key", "other", "--force"]
    )
    assert result.exit_code == 0, result.output

    refreshed_key = EPIContainer.read_manifest(out).public_key
    assert refreshed_key and refreshed_key != original_key

    report = _verify_json(out, capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert seal[0]["status"] == "imprint_mismatch"
    assert seal[0]["key_bound"] is False
    assert "signing key changed" in seal[0]["detail"]
    assert key_fingerprint(original_key, grouped=False) in seal[0]["detail"]
    assert key_fingerprint(refreshed_key, grouped=False) in seal[0]["detail"]
    assert report["decision"]["status"] == "FAIL"
    assert report["timestamps"]["key_binding"] == "none"


def test_record_without_auto_sign_stamps_contents_only(
    monkeypatch, tmp_path: Path, capsys, pki: MiniPKI
) -> None:
    out = tmp_path / "unsigned.epi"
    _mock_tsa(monkeypatch, tmp_path, pki)
    _record(out, auto_sign=False)
    root_pem = pki.root_pem_file(tmp_path / "root.pem")

    from epi_core.container import EPIContainer

    manifest = EPIContainer.read_manifest(out)
    assert manifest.public_key is None
    notar = EPIContainer.read_member_json(
        out, "artifacts/notarization/notarization.json"
    )
    assert notar["imprinted_public_key"] is None

    report = _verify_json(out, capsys, tsa_root=[root_pem])
    seal = report["timestamps"]["seal"]
    assert seal[0]["status"] == "valid"
    assert seal[0]["key_bound"] is False
    assert seal[0]["gen_time"] == GEN_TIME
    assert report["timestamps"]["key_binding"] == "contents-only"
    assert "contents-only" in report["timestamps"]["statement"]
