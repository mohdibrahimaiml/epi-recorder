"""Gateway export hash chain + capture-time checkpoints (WP3, issue #26)."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

FAKE_TOKEN = b"\x30\x82\x01\x00" + b"\x00" * 100


@pytest.fixture(autouse=True)
def _checkpoints_enabled(monkeypatch):
    # test_capture_manifest leaks EPI_CHECKPOINTS_ENABLED=0 via os.environ;
    # capture-chain tests need the worker chain active (tests that want it
    # off set it explicitly, which wins over this fixture).
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")


def _events(n: int, case_id: str = "case-chain-1") -> list[dict]:
    return [
        {
            "case_id": case_id,
            "workflow_id": "wf-chain-1",
            "kind": "llm.request",
            "content": {"messages": [{"role": "user", "content": f"question {i}"}]},
        }
        for i in range(n)
    ]


def _store(worker, events: list[dict]) -> None:
    touched = worker.store_items(events)
    assert touched, "events did not land in any case"


def _wait_for_capture_checkpoints(worker, case_id: str, timeout: float = 10.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        records = worker.case_store.list_capture_checkpoints(case_id)
        if records:
            return records
        time.sleep(0.05)
    return worker.case_store.list_capture_checkpoints(case_id)


def _export(worker, case_id: str, out: Path) -> Path:
    result = worker.export_case(case_id, out, signer_function=None)
    assert Path(result.output_path).is_file()
    return Path(result.output_path)


def _verify_json(out: Path, capsys) -> dict:
    import typer

    from epi_cli.verify import verify_command

    try:
        verify_command(None, out, True, False, None)
    except typer.Exit:
        pass
    return json.loads(capsys.readouterr().out)


def _resign(out: Path, tmp_path: Path, name: str = "resigned.epi", ws: Path | None = None) -> Path:
    """Repack a workspace with a fresh key (integrity passes; history is what is tested).

    Analysis is disabled so pack does not recount total_steps: the count
    attestation under test must survive the repack byte-for-byte.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from epi_core.container import EPIContainer
    from epi_core.trust import sign_manifest

    if ws is None:
        ws = tmp_path / "ws-resign"
        if ws.exists():
            import shutil

            shutil.rmtree(ws, ignore_errors=True)
        EPIContainer.unpack(out, ws)
    manifest = EPIContainer.read_manifest(out)
    key = Ed25519PrivateKey.generate()
    out2 = tmp_path / name
    EPIContainer.pack(
        ws,
        copy.deepcopy(manifest),
        out2,
        signer_function=lambda current: sign_manifest(current, key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return out2


def test_export_steps_are_chained_and_verify(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=50)
    _store(worker, _events(5))
    out = _export(worker, "case-chain-1", tmp_path / "chained.epi")

    from epi_core.container import EPIContainer

    steps = EPIContainer.read_steps(out)
    assert len(steps) == 6  # 5 events + synthetic session.start
    assert steps[0]["prev_hash"] == "CHAIN_START"
    assert all(isinstance(s.get("prev_hash"), str) and len(s["prev_hash"]) == 64 for s in steps[1:])

    report = _verify_json(out, capsys)
    assert report["facts"]["chain_ok"] is True


def test_trimmed_export_breaks_step_chain(monkeypatch, tmp_path: Path, capsys) -> None:
    from epi_core.container import EPIContainer

    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=50)
    _store(worker, _events(5))
    out = _export(worker, "case-chain-1", tmp_path / "trimmed.epi")

    # Middle trim: remaining links contradict each other -> chain break.
    ws = tmp_path / "ws-trim-mid"
    EPIContainer.unpack(out, ws)
    lines = [line for line in (ws / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 6
    del lines[2]
    (ws / "steps.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_mid = _resign(out, tmp_path, "trimmed-mid.epi", ws=ws)
    report = _verify_json(out_mid, capsys)
    assert report["facts"]["chain_ok"] is False
    assert report["decision"]["status"] == "FAIL"

    # Tail trim: links stay intact, but the manifest step count no longer
    # matches -> integrity FAIL (capture checkpoints report TRIMMED; covered
    # by test_delete_event_from_case_trimmed).
    ws2 = tmp_path / "ws-trim-tail"
    EPIContainer.unpack(out, ws2)
    lines = [line for line in (ws2 / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    (ws2 / "steps.jsonl").write_text("\n".join(lines[:-2]) + "\n", encoding="utf-8")
    out_tail = _resign(out, tmp_path, "trimmed-tail.epi", ws=ws2)
    report = _verify_json(out_tail, capsys)
    assert report["decision"]["status"] == "FAIL"


def test_old_unchained_export_still_verifies(tmp_path: Path, capsys) -> None:
    """Pre-chain exports (no prev_hash anywhere) verify on the pre-chain path."""
    from epi_core.container import EPIContainer

    # Simulate an old export by stripping the chain, then re-signing.
    import shutil

    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=50)
    _store(worker, _events(3))
    out = _export(worker, "case-chain-1", tmp_path / "new.epi")
    ws = tmp_path / "ws-old"
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    EPIContainer.unpack(out, ws)
    stripped = []
    for line in (ws / "steps.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        step = json.loads(line)
        step.pop("prev_hash", None)
        stripped.append(step)
    (ws / "steps.jsonl").write_text(
        "\n".join(json.dumps(s) for s in stripped) + "\n", encoding="utf-8"
    )
    out2 = _resign(out, tmp_path, "oldstyle.epi", ws=ws)
    report = _verify_json(out2, capsys)
    assert report["facts"]["chain_ok"] is True  # vacuous pre-chain pass, warned
    assert report["decision"]["status"] in ("PASS", "WARN")


def test_delete_event_from_case_trimmed(monkeypatch, tmp_path: Path, capsys) -> None:
    """Issue #26 acceptance 1: deleting one event -> TRIMMED."""
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(
        storage_dir=tmp_path, batch_size=50, tsa_submit=lambda head: FAKE_TOKEN
    )
    _store(worker, _events(5))
    records = _wait_for_capture_checkpoints(worker, "case-chain-1")
    assert records, "no capture checkpoint recorded"
    assert records[0]["tsa_available"] == 1

    # Delete one event from the case and re-project, then export.
    with worker.case_store._connect() as connection:
        connection.execute(
            "DELETE FROM events WHERE case_id = ? AND event_json LIKE ?",
            ("case-chain-1", "%question 2%"),
        )
        connection.commit()
    worker.case_store.rebuild_case("case-chain-1")
    out = _export(worker, "case-chain-1", tmp_path / "deleted.epi")

    report = _verify_json(out, capsys)
    blob = " | ".join(report["capture_checkpoints"]["messages"])
    assert "TRIMMED" in blob, blob
    assert report["decision"]["status"] == "FAIL"


def test_reorder_events_checkpoint_mismatch(monkeypatch, tmp_path: Path, capsys) -> None:
    """Issue #26 acceptance 2: reordering two events -> checkpoint mismatch."""
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(
        storage_dir=tmp_path, batch_size=50, tsa_submit=lambda head: FAKE_TOKEN
    )
    _store(worker, _events(4))
    assert _wait_for_capture_checkpoints(worker, "case-chain-1")
    out = _export(worker, "case-chain-1", tmp_path / "reorder.epi")

    from epi_core.container import EPIContainer

    ws = tmp_path / "ws-reorder"
    EPIContainer.unpack(out, ws)
    lines = [
        line
        for line in (ws / "artifacts" / "capture" / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert len(lines) >= 3
    lines[1], lines[2] = lines[2], lines[1]
    (ws / "artifacts" / "capture" / "events.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    out2 = _resign(out, tmp_path, "reordered.epi", ws=ws)

    report = _verify_json(out2, capsys)
    blob = " | ".join(report["capture_checkpoints"]["messages"])
    assert "MISMATCH" in blob, blob
    assert report["decision"]["status"] == "FAIL"


def test_capture_checkpoint_head_mismatch_invalid(monkeypatch, tmp_path: Path, capsys) -> None:
    """A capture checkpoint attesting a different head -> MISMATCH + FAIL."""
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=50)
    _store(worker, _events(3))
    out = _export(worker, "case-chain-1", tmp_path / "cp.epi")

    from epi_core.container import EPIContainer

    ws = tmp_path / "ws-cptamper"
    EPIContainer.unpack(out, ws)
    cp_dir = ws / "artifacts" / "capture" / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    head = worker.case_store.get_capture_head("case-chain-1")
    assert head is not None
    count, _real_head = head
    assert count == 3
    (cp_dir / "000000.json").write_text(
        json.dumps(
            {
                "checkpoint_index": 0,
                "event_count": count,
                "head": "00" * 32,  # not the true chain head
                "tsa_url": "https://tsa.example.test/tsr",
                "tsa_available": 0,
                "created_at": "2026-10-11T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    out2 = _resign(out, tmp_path, "cptamper.epi", ws=ws)
    report = _verify_json(out2, capsys)
    blob = " | ".join(report["capture_checkpoints"]["messages"])
    assert "MISMATCH" in blob, blob
    assert report["decision"]["status"] == "FAIL"


def test_large_case_export_time(monkeypatch, tmp_path: Path, capsys) -> None:
    """Issue #26 acceptance 3: 10,000 events export in a reasonable time."""
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=500)
    _store(worker, _events(10_000, case_id="case-big"))
    started = time.monotonic()
    out = _export(worker, "case-big", tmp_path / "big.epi")
    elapsed = time.monotonic() - started
    assert elapsed < 120, f"10k export too slow: {elapsed:.1f}s"
    report = _verify_json(out, capsys)
    assert report["facts"]["chain_ok"] is True
    print(f"\n10k-event gateway export: {elapsed:.1f}s")


def test_capture_checkpoint_tsa_root_trusted_with_flag(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """R0.1: gateway capture checkpoint is UNVERIFIED by default, valid with --tsa-root."""
    import base64 as _b64

    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")

    from tests.test_tsa_validation import MiniPKI, make_tsr

    pki = MiniPKI()

    def _tsa_submit(head_hex: str) -> bytes:
        return make_tsr(bytes.fromhex(head_hex), pki)

    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(
        storage_dir=tmp_path, batch_size=50, tsa_submit=_tsa_submit
    )
    _store(worker, _events(5))
    records = _wait_for_capture_checkpoints(worker, "case-chain-1")
    assert records, "no capture checkpoint recorded"
    # Background TSA submit runs on a daemon thread: wait for the token row.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        rows = worker.case_store.list_capture_checkpoints("case-chain-1")
        if rows and all(r.get("tsa_token_b64") for r in rows):
            break
        time.sleep(0.05)
    out = _export(worker, "case-chain-1", tmp_path / "capture-tstaroot.epi")

    from epi_core.case_store import verify_capture_checkpoints

    ok, messages, _recs = verify_capture_checkpoints(out)
    assert ok is True
    assert any("CAPTURE TIMESTAMP UNVERIFIED" in m for m in messages), messages

    ok2, messages2, _recs2 = verify_capture_checkpoints(
        out, trust_roots=[pki.root_cert]
    )
    assert ok2 is True
    assert not any("CAPTURE TIMESTAMP UNVERIFIED" in m for m in messages2), messages2

    # CLI flag path: same export verifies UNVERIFIED without the root (WARN,
    # still PASS) and clean with it.
    import typer

    from epi_cli.verify import verify_command

    root_pem = tmp_path / "test-root.pem"
    from cryptography.hazmat.primitives import serialization as _ser

    root_pem.write_bytes(pki.root_cert.public_bytes(_ser.Encoding.PEM))
    try:
        verify_command(None, out, True, False, None)
    except typer.Exit:
        pass
    report = json.loads(capsys.readouterr().out)
    assert any(
        "CAPTURE TIMESTAMP UNVERIFIED" in m
        for m in report["capture_checkpoints"]["messages"]
    ), report["capture_checkpoints"]["messages"]

    try:
        verify_command(None, out, True, False, None, tsa_root=[root_pem])
    except typer.Exit:
        pass
    report2 = json.loads(capsys.readouterr().out)
    assert not any(
        "CAPTURE TIMESTAMP UNVERIFIED" in m
        for m in report2["capture_checkpoints"]["messages"]
    ), report2["capture_checkpoints"]["messages"]
    assert _b64 is not None  # keep import used when FAKE_TOKEN path changes
