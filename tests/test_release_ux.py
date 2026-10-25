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
from tests.test_seal_witness import SECRET, CaptureHandler, _hermetic, _serve
from tests.test_seal_witness import _seal as _seal_llm_request  # noqa: F401


def _seal(monkeypatch, tmp_path: Path, out: Path, **kwargs) -> Path:
    """A complete record (no dangling request), so a clean file can PASS."""
    from epi_recorder import record

    with record(str(out), **kwargs) as epi:
        epi.log_step("agent.decision", {"content": "hello", "decision": "approve"})
    return out

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
    trust = runner.invoke(
        cli_app, ["keys", "trust", str(out), "--name", "vendor", "--fingerprint", fp]
    )
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
    out = capsys.readouterr().err
    assert "demo-2.epi" in out and "EPI_OVERWRITE=1" in out, out
    assert "already exists" not in out

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


# ------------------------------------------------------------- round 2


def _tampered(src: Path, dst: Path) -> Path:
    import zipfile

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "steps.jsonl":
                data = data.replace(b"hello", b"HELLO")
            zout.writestr(item, data)
    return dst


def test_audit_on_tampered_file_fails_every_domain_and_exits_1(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    good = _seal(monkeypatch, tmp_path, tmp_path / "good.epi")
    bad = _tampered(good, tmp_path / "bad.epi")

    res = runner.invoke(cli_app, ["audit", str(bad), "-f", "json"])
    assert res.exit_code == 1
    report = json.loads(res.output[: res.output.rindex("}") + 1])
    for dom in report["pipeline"]["aiuc1"]["domains"].values():
        assert dom["status"] == "FAIL"
        assert "chain_ok" not in dom["evidence"]
    assert report["compliance_score"]["rating"] == "altered"

    ok = runner.invoke(cli_app, ["audit", str(good)])
    assert ok.exit_code == 0, ok.output
    assert ok.output.count("Compliance Report") == 1  # printed once


def test_verify_never_suggests_pinning_from_the_file(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    # Verifier's machine: no local signing key, nothing pinned.
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "verifier-keys"))
    text = runner.invoke(cli_app, ["verify", str(out)]).output
    assert f'epi keys trust "{out}"' not in text
    assert "keys trust <file.epi>" not in text
    assert "never from this file" in text.replace("\n", " ")


def test_revoke_applies_to_the_key_and_can_be_undone(monkeypatch, tmp_path: Path) -> None:
    import os
    import re

    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    trusted = Path(os.environ["EPI_TRUSTED_KEYS_DIR"])
    pk = __import__("epi_core.container", fromlist=["EPIContainer"]).EPIContainer.read_manifest(out).public_key
    trusted.mkdir(parents=True, exist_ok=True)
    (trusted / "vendor.pub").write_text(pk + "\n")
    (trusted / "vendor-did.pub").write_text(pk + "\n")

    assert runner.invoke(cli_app, ["keys", "revoke", "vendor-did"]).exit_code == 0
    listing = re.sub(r"\s+", " ", runner.invoke(cli_app, ["keys", "list"]).output)
    assert "vendor │" in listing and "trusted" not in listing.split("Trusted Keys")[1]
    assert runner.invoke(cli_app, ["verify", str(out)]).exit_code == 1

    res = runner.invoke(cli_app, ["keys", "unrevoke", "vendor-did"])
    assert res.exit_code == 0, res.output
    assert not list(trusted.glob("*.revoked"))
    assert runner.invoke(cli_app, ["verify", str(out)]).exit_code == 0


def test_incomplete_evidence_is_warn_not_pass_under_standard(monkeypatch, tmp_path: Path) -> None:
    from epi_core.trust import VerificationPolicy, apply_policy

    report = {
        "facts": {"integrity_ok": True, "sequence_ok": True, "signature_valid": True,
                  "completeness_ok": False},
        "identity": {"status": "KNOWN", "pinned_names": ["vendor"]},
    }
    assert apply_policy(report, VerificationPolicy.STANDARD)["decision"]["status"] == "WARN"
    assert apply_policy(report, VerificationPolicy.STRICT)["decision"]["status"] == "FAIL"
    report["facts"]["completeness_ok"] = True
    assert apply_policy(report, VerificationPolicy.STANDARD)["decision"]["status"] == "PASS"


# ------------------------------------------------------------- round 3


def test_unreported_reexport_with_same_workflow_is_not_called_altered(
    monkeypatch, tmp_path: Path
) -> None:
    """A reported workflow id with a different (genuine) copy: DIFFERENT VERSION, never FILE ALTERED."""
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = _seal(monkeypatch, tmp_path, tmp_path / "case.epi", witness_url=url, witness_secret=SECRET)
    finally:
        server.shutdown()
    entry = json.loads(CaptureHandler.received[-1]["body"].decode())
    entry["manifest_hash"] = "0" * 64  # the reported version was a different export
    entry["file_sha256"] = "1" * 64
    entry["content_digest"] = "2" * 64
    entry["received_at"] = "2026-10-12T00:00:00+00:00"
    log = tmp_path / "received.jsonl"
    log.write_text(json.dumps(entry) + "\n")

    res = runner.invoke(cli_app, ["verify", str(out), "--json", "--witness-log", str(log)])
    report = json.loads(res.output)
    assert report["witness"]["status"] == "MISMATCH"
    assert report["decision"]["status"] == "FAIL"
    assert report["facts"]["integrity_ok"] is True  # the file itself is intact
    assert "Not the version reported to you" in report["decision"]["reason"]

    text = runner.invoke(cli_app, ["verify", str(out), "--witness-log", str(log)]).output
    assert "NOT THE VERSION REPORTED TO YOU" in text
    assert "FILE ALTERED" not in text


def test_witness_flush_without_secret_says_no_secret(monkeypatch, tmp_path: Path) -> None:
    import threading

    from epi_core.witness_receiver import make_server

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.delenv("EPI_WITNESS_SECRET", raising=False)
    server = make_server("127.0.0.1", 0, out=tmp_path / "rx.jsonl", secret="bank-secret",
                         log=lambda _m: None)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        _seal(monkeypatch, tmp_path, tmp_path / "run.epi", witness_url=url)  # no secret
        res = runner.invoke(cli_app, ["witness", "flush"])
    finally:
        server.shutdown()
    assert res.exit_code == 1
    assert "No secret set" in res.output


def test_gateway_export_reuses_serve_settings(tmp_path: Path) -> None:
    from epi_cli.gateway import _load_serve_settings, _save_serve_settings

    _save_serve_settings(tmp_path, "did:web:vendor.example", "http://127.0.0.1:1/")
    assert _load_serve_settings(tmp_path) == {
        "did": "did:web:vendor.example", "witness_url": "http://127.0.0.1:1/"
    }
    assert "secret" not in (tmp_path / "gateway-settings.json").read_text()


def test_witness_payload_carries_case_id() -> None:
    from epi_core.webhook import build_witness_payload

    p = build_witness_payload(
        workflow_id="w", manifest_hash="m", file_sha256="f", public_key=None,
        key_fingerprint=None, steps=1, sealed_at="t", seal_timestamp={}, case_id="trace::t-1",
    )
    assert p["case_id"] == "trace::t-1"


# ------------------------------------------------------------- round 4


def test_wrong_or_empty_witness_log_is_not_checked_not_blame(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    for content in ("", "not json\n", '{"some": "other json"}\n'):
        log = tmp_path / "wrong.jsonl"
        log.write_text(content)
        report = json.loads(runner.invoke(
            cli_app, ["verify", str(out), "--json", "--witness-log", str(log)]
        ).output)
        assert report["witness"]["status"] == "UNREADABLE", content
        assert report["decision"]["status"] == "FAIL"
        assert "re-run" not in report["decision"]["reason"]


def test_refresh_viewer_keeps_witnessed(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = _seal(monkeypatch, tmp_path, tmp_path / "case.epi", witness_url=url, witness_secret=SECRET, with_viewer=True)
        log = _witness_log_for(tmp_path, out)
    finally:
        server.shutdown()
    res = runner.invoke(cli_app, ["refresh-viewer", str(out)])
    assert res.exit_code == 0, res.output
    report = json.loads(runner.invoke(
        cli_app, ["verify", str(out), "--json", "--witness-log", str(log)]
    ).output)
    assert report["witness"]["status"] == "WITNESSED", report["witness"]


def test_trust_from_epi_hint_does_not_prefill_and_overwrite_is_loud(monkeypatch, tmp_path: Path) -> None:
    import os

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint

    _hermetic(monkeypatch, tmp_path)
    out = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    fp = key_fingerprint(EPIContainer.read_manifest(out).public_key)

    refused = runner.invoke(cli_app, ["keys", "trust", str(out), "--name", "vendor"])
    assert refused.exit_code == 1
    assert f'--fingerprint "{fp}"' not in refused.output

    trusted = Path(os.environ["EPI_TRUSTED_KEYS_DIR"])
    trusted.mkdir(parents=True, exist_ok=True)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    (trusted / "vendor.pub").write_text(other + "\n")
    res = runner.invoke(
        cli_app, ["keys", "trust", str(out), "--name", "vendor", "--fingerprint", fp, "--overwrite"]
    )
    # A case file is never allowed to replace a pinned sender's key.
    assert res.exit_code == 1, res.output
    text = " ".join(res.output.split())
    assert "you already trust vendor" in text
    assert "Not replaced" in text
    assert (trusted / "vendor.pub").read_text().strip() == other

    # A real rotation from the sender's key file is allowed, and loud.
    keyfile = tmp_path / "vendor-new.pub"
    keyfile.write_text(EPIContainer.read_manifest(out).public_key + "\n")
    res = runner.invoke(cli_app, ["keys", "trust", str(keyfile), "--name", "vendor", "--overwrite"])
    assert res.exit_code == 0, res.output
    assert "Replaced the key pinned as 'vendor'" in " ".join(res.output.split())


def test_strict_reason_matches_not_a_key_you_trust_headline() -> None:
    from epi_core.trust import VerificationPolicy, apply_policy

    report = {
        "facts": {"integrity_ok": True, "sequence_ok": True, "signature_valid": True,
                  "completeness_ok": True},
        "identity": {"status": "UNKNOWN", "pinned_names": ["vendor"]},
    }
    reason = apply_policy(report, VerificationPolicy.STRICT)["decision"]["reason"]
    assert reason.startswith("Not a key you trust")


def test_gateway_restart_without_flags_keeps_saved_settings(tmp_path: Path, monkeypatch) -> None:
    import uvicorn

    from epi_cli.gateway import _load_serve_settings, _save_serve_settings
    from epi_cli.gateway import app as gw_app

    _save_serve_settings(tmp_path, "did:web:vendor.example", "http://127.0.0.1:1/")
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    for var in ("EPI_DID", "EPI_GATEWAY_DID", "EPI_WITNESS_URL", "EPI_GATEWAY_WITNESS_URL"):
        monkeypatch.delenv(var, raising=False)
    res = runner.invoke(gw_app, ["serve", "--storage-dir", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert _load_serve_settings(tmp_path)["did"] == "did:web:vendor.example"
    assert "kept from the previous run" in res.output


def test_rezipped_file_gives_clear_errors_and_report(monkeypatch, tmp_path: Path) -> None:
    import zipfile

    _hermetic(monkeypatch, tmp_path)
    good = _seal(monkeypatch, tmp_path, tmp_path / "good.epi")
    bad = tmp_path / "rezip.epi"
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(bad, "w") as zout:
        for item in sorted(zin.infolist(), key=lambda i: i.filename, reverse=True):
            zout.writestr(item.filename, zin.read(item.filename))  # mimetype not first
    rep = tmp_path / "report.txt"
    res = runner.invoke(cli_app, ["verify", str(bad), "--report", str(rep)])
    assert res.exit_code == 1
    assert rep.exists() and "DECISION:  FAIL" in rep.read_text()
    audit = runner.invoke(cli_app, ["audit", str(bad)])
    assert audit.exit_code == 1
    assert "Traceback" not in audit.output
    assert "re-packed" in audit.output


def test_refresh_viewer_refuses_altered_or_foreign_files(monkeypatch, tmp_path: Path) -> None:
    import zipfile

    _hermetic(monkeypatch, tmp_path)
    good = _seal(monkeypatch, tmp_path, tmp_path / "good.epi")
    bad = tmp_path / "bad.epi"
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "steps.jsonl":
                data = data.replace(b"approve", b"reject!")
            zout.writestr(item, data)
    before = bad.read_bytes()
    res = runner.invoke(cli_app, ["refresh-viewer", str(bad)])
    assert res.exit_code != 0, res.output
    assert bad.read_bytes() == before

    # A file sealed by someone else's key is not re-signed with ours.
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "other-keys"))
    from epi_core.keys import KeyManager

    KeyManager().generate_keypair("default")
    before = good.read_bytes()
    res = runner.invoke(cli_app, ["refresh-viewer", str(good)])
    assert res.exit_code != 0, res.output
    assert good.read_bytes() == before
