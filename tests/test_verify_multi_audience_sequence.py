"""Multi-audience files + --witness-log must print the real chain position.

A file sealed for two customers carries commitments, not a plaintext chain. The
verifier used to hash the witness report itself, which never matches a
commitment (the report renames seq to seal_seq and adds fields), so a valid log
read as "supply --witness-log to check" even though one was supplied.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.audience import entry_from_report
from epi_core.container import EPIContainer
from epi_core.keys import fingerprint_for_private_key
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest

REPO = Path(__file__).resolve().parents[1]


def _two_audience_file(tmp_path: Path) -> tuple[Path, dict]:
    work = tmp_path / "work"
    work.mkdir()
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {"n": 1}}) + "\n",
        encoding="utf-8",
    )
    key = Ed25519PrivateKey.generate()
    entries: dict = {}
    out = tmp_path / "two.epi"
    EPIContainer.pack(
        work,
        ManifestModel(goal="two audiences"),
        out,
        signer_function=lambda current: sign_manifest(current, key, "k"),
        seal_fingerprint=fingerprint_for_private_key(key),
        audiences=["customer:bank-a", "customer:bank-b"],
        seal_entries=entries,
        generate_analysis=False,
        embed_viewer=False,
        notarize=False,
    )
    return out, entries


def _report(entry: dict, seq: int | None = None) -> dict:
    """The shape a witness receiver stores: seq becomes seal_seq, plus detail."""
    payload = {
        "schema": "epi-witness/v1",
        "type": "epi.sealed",
        "workflow_id": "wf-test",
        "manifest_hash": "manifest-test",
        "file_sha256": "file-test",
        "steps": 1,
        "sealed_at": "2026-11-12T00:00:00Z",
        "seal_timestamp": {"status": "none", "gen_time": None},
    }
    for name in ("audience", "key_fingerprint", "ledger_id", "prev_seq", "prev_content_digest", "nonce"):
        if name in entry:
            payload[name] = entry[name]
    payload["seal_seq"] = entry.get("seq") if seq is None else seq
    return payload


def _verify(epi: Path, log: Path, tmp_path: Path) -> tuple[int, str]:
    home = tmp_path / "home"
    for name in ("keys", "trusted_keys", "trusted_approvers", "approver_keys"):
        (home / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "EPI_HOME": str(home),
            "EPI_KEYS_DIR": str(home / "keys"),
            "EPI_TRUSTED_KEYS_DIR": str(home / "trusted_keys"),
            "EPI_TRUSTED_APPROVERS_DIR": str(home / "trusted_approvers"),
            "EPI_APPROVER_KEYS_DIR": str(home / "approver_keys"),
            "EPI_TELEMETRY": "0",
            "EPI_NOTARIZE": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "epi_cli", "verify", str(epi), "--witness-log", str(log)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    return result.returncode, result.stdout + result.stderr


def test_report_rebuilds_the_committed_entry():
    entry = {
        "audience": "customer:bank-a",
        "key_fingerprint": "abcd",
        "ledger_id": "ledger-1",
        "seq": 4,
        "prev_seq": 3,
        "prev_content_digest": "digest-3",
        "nonce": "deadbeef",
    }
    payload = {**_report(entry), "workflow_id": "wf", "steps": 7}
    assert entry_from_report(payload) == entry
    # A log that stores the entry directly still works.
    assert entry_from_report(entry) == entry


def test_matching_log_prints_the_chain_position(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    epi, entries = _two_audience_file(tmp_path)
    log = tmp_path / "witness.jsonl"
    log.write_text(
        "\n".join(json.dumps(_report(e)) for e in entries.values()) + "\n",
        encoding="utf-8",
    )
    _, output = _verify(epi, log, tmp_path)
    assert "#1 of chain" in output, output[-3000:]
    assert "log contiguous 1..1" in output, output[-3000:]
    assert "supply --witness-log to check" not in output


def test_gap_in_the_customers_chain_reads_as_gaps(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    epi, entries = _two_audience_file(tmp_path)
    entry = entries["customer:bank-a"]
    gap = _report({**entry, "prev_seq": 2, "nonce": "different-nonce"}, seq=3)
    log = tmp_path / "witness.jsonl"
    log.write_text(
        json.dumps(_report(entry)) + "\n" + json.dumps(gap) + "\n",
        encoding="utf-8",
    )
    _, output = _verify(epi, log, tmp_path)
    assert "#1" in output, output[-3000:]
    assert "log has gaps" in output, output[-3000:]
    assert "log contiguous 1..3" not in output


def test_a_log_with_no_matching_commitment_does_not_blame_the_missing_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    epi, entries = _two_audience_file(tmp_path)
    # A report that matches none of this file's commitments.
    stranger = _report(
        {**entries["customer:bank-a"], "nonce": "not-one-of-this-files", "ledger_id": "other-ledger"},
        seq=1,
    )
    log = tmp_path / "other.jsonl"
    log.write_text(json.dumps(stranger) + "\n", encoding="utf-8")
    _, output = _verify(epi, log, tmp_path)
    assert "not in this witness log" in output, output[-3000:]
    assert "supply --witness-log to check" not in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # Right audience, key, ledger and nonce — only the number differs.
        ("seq", 99),
        # Right everything except the per-seal salt.
        ("nonce", "different-nonce"),
        # Right everything except the link to the previous seal.
        ("prev_content_digest", "different-previous-digest"),
    ],
)
def test_a_near_miss_entry_does_not_match_the_file(tmp_path, monkeypatch, field, value):
    """A commitment is exact: one changed field must not match.

    This is the other half of the positive test. Matching on audience (or
    audience plus ledger) alone would let a different seal of the same
    customer be reported as this file's position.
    """
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(tmp_path / "ledger"))
    epi, entries = _two_audience_file(tmp_path)
    near_miss = dict(entries["customer:bank-a"])
    near_miss[field] = value

    log = tmp_path / "near-miss.jsonl"
    log.write_text(json.dumps(_report(near_miss)) + "\n", encoding="utf-8")
    _, output = _verify(epi, log, tmp_path)
    assert "not in this witness log" in output, output[-3000:]
    assert "log contiguous" not in output, output[-3000:]
    assert "supply --witness-log to check" not in output
