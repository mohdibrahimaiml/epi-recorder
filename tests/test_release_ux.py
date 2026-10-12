"""Regressions from the 4.6.0 walkthroughs (developer, vendor, bank analyst).

Each test pins one thing a real user hit: silent no-timestamp seals, a
re-sealed case passing a witness check, a mistyped witness log, three
fingerprint formats, evidence written somewhere unexpected or overwritten,
and a self-issued transparency receipt labelled VERIFIED.
"""

from __future__ import annotations

import base64
import json
import socket
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.test_seal_witness import SECRET, CaptureHandler, _hermetic, _seal, _serve

runner = CliRunner()


# ---------------------------------------------------------------- timestamps


def test_no_timestamp_is_announced_at_seal_time(monkeypatch, tmp_path: Path, capsys) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_NOTARIZE", "1")
    calls: list[str] = []

    def _unreachable(digest_hex, url):  # noqa: ANN001
        calls.append(url)
        return None

    monkeypatch.setattr("epi_core.notarize._submit_rfc3161", _unreachable)
    monkeypatch.setattr(
        "epi_core.notarize._submit_opentimestamps", lambda _d: (None, "")
    )
    _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    err = capsys.readouterr().err
    assert "No trusted timestamp" in err
    assert "freetsa.org" in err
    assert len(calls) >= 2  # every configured TSA was asked


def test_tsas_are_asked_in_parallel(monkeypatch) -> None:
    import threading
    import time

    from epi_core import notarize

    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def _slow(digest_hex, url):  # noqa: ANN001
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.2)
        with lock:
            active["now"] -= 1
        return None

    monkeypatch.setattr(notarize, "_submit_rfc3161", _slow)
    monkeypatch.setattr(notarize, "_submit_opentimestamps", lambda _d: (None, ""))
    monkeypatch.delenv("EPI_TSA_URLS", raising=False)
    monkeypatch.delenv("EPI_TSA_URL", raising=False)
    notarize.notarize_manifest("{}", "00" * 32)
    assert active["max"] >= 2


# ------------------------------------------------------------------- witness


def _witness_log_for(tmp_path: Path, out: Path) -> Path:
    received = tmp_path / "received.jsonl"
    received.write_text(
        json.dumps({**json.loads(CaptureHandler.received[-1]["body"].decode()),
                    "received_at": "2026-10-12T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    return received


def _pin_own_key_as_vendor(tmp_path: Path) -> None:
    """Pin the sealing key under a vendor name, as a bank would."""
    from epi_core.keys import KeyManager

    km = KeyManager()
    km.trust_key("default", trusted_keys_dir=Path(__import__("os").environ["EPI_TRUSTED_KEYS_DIR"]),
                 trusted_name="vendor")


def test_reseal_not_in_witness_log_is_never_a_clean_pass(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        original = _seal(monkeypatch, tmp_path, tmp_path / "case.epi",
                         witness_url=url, witness_secret=SECRET)
        log = _witness_log_for(tmp_path, original)
        # Vendor re-runs the case and does NOT report it.
        resealed = _seal(monkeypatch, tmp_path, tmp_path / "case-rerun.epi")
    finally:
        server.shutdown()
    _pin_own_key_as_vendor(tmp_path)

    ok = runner.invoke(cli_app, ["verify", str(original), "--json", "--witness-log", str(log)])
    assert json.loads(ok.output)["decision"]["status"] == "PASS", ok.output

    res = runner.invoke(cli_app, ["verify", str(resealed), "--json", "--witness-log", str(log)])
    report = json.loads(res.output)
    assert report["witness"]["status"] == "NOT IN WITNESS LOG"
    assert report["decision"]["status"] == "WARN"
    assert "never reported" in report["decision"]["reason"]

    strict = runner.invoke(
        cli_app, ["verify", str(resealed), "--policy", "strict", "--witness-log", str(log)]
    )
    assert strict.exit_code == 1, strict.output

    human = runner.invoke(cli_app, ["verify", str(resealed), "--witness-log", str(log)])
    assert "NOT IN YOUR WITNESS LOG" in human.output.replace("\n", " ")


def test_mistyped_witness_log_path_fails_loudly(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    res = runner.invoke(
        cli_app, ["verify", str(out), "--witness-log", str(tmp_path / "recieved.jsonl")]
    )
    assert res.exit_code != 0
    assert "DECISION: FAIL" in res.output
    assert "NOT CHECKED" in res.output
    report = json.loads(runner.invoke(
        cli_app, ["verify", str(out), "--json", "--witness-log", str(tmp_path / "recieved.jsonl")]
    ).output)
    assert report["witness"]["status"] == "UNREADABLE"
    assert "could not be read" in report["decision"]["reason"]


def test_flush_exits_nonzero_while_undelivered(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead = f"http://127.0.0.1:{sock.getsockname()[1]}/w"
    sock.close()
    _seal(monkeypatch, tmp_path, tmp_path / "run.epi", witness_url=dead, witness_secret=SECRET)
    res = runner.invoke(cli_app, ["witness", "flush"])
    assert res.exit_code == 1, res.output


def test_seal_says_whether_witness_got_it(monkeypatch, tmp_path: Path, capsys) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        _seal(monkeypatch, tmp_path, tmp_path / "a.epi", witness_url=url, witness_secret=SECRET)
    finally:
        server.shutdown()
    assert "Witness: delivered to 127.0.0.1" in capsys.readouterr().err

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead = f"http://127.0.0.1:{sock.getsockname()[1]}/w"
    sock.close()
    _seal(monkeypatch, tmp_path, tmp_path / "b.epi", witness_url=dead, witness_secret=SECRET)
    err = capsys.readouterr().err
    assert "Witness: QUEUED" in err
    assert "epi witness flush" in err


# --------------------------------------------------------------- fingerprints


def test_one_fingerprint_everywhere(monkeypatch, tmp_path: Path) -> None:
    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi",
                    witness_url=url, witness_secret=SECRET)
        payload = json.loads(CaptureHandler.received[-1]["body"].decode())
    finally:
        server.shutdown()
    pk = EPIContainer.read_manifest(out).public_key
    fp = key_fingerprint(pk)
    assert len(fp) == 19 and fp.count(" ") == 3

    # Witness log carries the same value (ungrouped).
    assert payload["key_fingerprint"] == fp.replace(" ", "")
    # verify prints it.
    assert fp in runner.invoke(cli_app, ["verify", str(out)]).output
    # keys export prints it.
    assert fp in runner.invoke(cli_app, ["keys", "export"]).output
    # keys trust prints it, and keys list shows the pin with it.
    trust = runner.invoke(cli_app, ["keys", "trust", str(out), "--name", "vendor"])
    assert fp in trust.output, trust.output
    listing = runner.invoke(cli_app, ["keys", "list"]).output
    assert "vendor" in listing and fp in listing
    # VERIFY.txt inside the file too.
    import zipfile

    with zipfile.ZipFile(out) as zf:
        assert fp in zf.read("VERIFY.txt").decode()


def test_trust_accepts_exported_base64_and_did_json(monkeypatch, tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    _hermetic(monkeypatch, tmp_path)
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    b64 = tmp_path / "vendor.b64"
    b64.write_text(base64.b64encode(raw).decode() + "\n")
    res = runner.invoke(cli_app, ["keys", "trust", str(b64), "--name", "vendor-b64"])
    assert res.exit_code == 0, res.output

    # did.json as `epi keys did` writes it.
    did_doc = {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": "did:web:vendor.example",
        "verificationMethod": [{
            "id": "did:web:vendor.example#key-1",
            "type": "Ed25519VerificationKey2020",
            "controller": "did:web:vendor.example",
            "publicKeyHex": raw.hex(),
        }],
    }
    did_file = tmp_path / "did.json"
    did_file.write_text(json.dumps(did_doc))
    res = runner.invoke(cli_app, ["keys", "trust", str(did_file), "--name", "vendor-did"])
    assert res.exit_code == 0, res.output
    trusted = Path(__import__("os").environ["EPI_TRUSTED_KEYS_DIR"])
    assert (trusted / "vendor-did.pub").read_text().strip() == raw.hex()


# ---------------------------------------------------------------- file paths


def test_record_paths_and_no_silent_overwrite(monkeypatch, tmp_path: Path, capsys) -> None:
    from epi_recorder.api import _resolve_output_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EPI_RECORDINGS_DIR", raising=False)
    monkeypatch.delenv("EPI_OVERWRITE", raising=False)

    assert _resolve_output_path("demo.epi") == Path("epi-recordings") / "demo.epi"
    assert _resolve_output_path("./here.epi") == Path("here.epi")
    assert _resolve_output_path("out/x.epi") == Path("out") / "x.epi"
    assert (tmp_path / "out").is_dir()

    (tmp_path / "epi-recordings" / "demo.epi").write_text("earlier evidence")
    second = _resolve_output_path("demo.epi")
    assert second == Path("epi-recordings") / "demo-2.epi"
    assert "already exists" in capsys.readouterr().err

    monkeypatch.setenv("EPI_OVERWRITE", "1")
    assert _resolve_output_path("demo.epi") == Path("epi-recordings") / "demo.epi"


# ------------------------------------------------------------ local SCITT


def test_local_scitt_receipt_is_not_labelled_verified(monkeypatch, tmp_path: Path) -> None:
    from epi_cli.register import app as register_app

    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    res = runner.invoke(register_app, [str(out), "--local"])
    assert res.exit_code == 0, res.output
    assert "self-issued" in res.output

    import re

    text = re.sub(r"[│\s]+", " ", runner.invoke(cli_app, ["verify", str(out)]).output)
    assert "LOCAL (self-issued receipt" in text
    assert "VERIFIED (SCITT)" not in text


def test_local_scitt_receipt_on_another_machine_is_unknown_not_failed(
    monkeypatch, tmp_path: Path
) -> None:
    from epi_cli.register import app as register_app

    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    assert runner.invoke(register_app, [str(out), "--local"]).exit_code == 0

    # The auditor's machine: a different EPI_HOME, no local SCITT service key.
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "auditor"))
    import re

    text = re.sub(r"[│\s]+", " ", runner.invoke(cli_app, ["verify", str(out)]).output)
    assert "only checkable on the machine that issued it" in text
    assert "FAILED (SCITT)" not in text
    assert not (tmp_path / "auditor" / "local-scitt" / "service.pub").exists()
