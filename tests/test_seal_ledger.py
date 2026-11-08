"""Seal sequence numbers: allocation, links, cross-process safety, burns, audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from epi_core import seal_ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY = "0123456789abcdef"


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "seal_ledger"
    monkeypatch.setenv("EPI_SEAL_LEDGER_DIR", str(target))
    monkeypatch.delenv("EPI_HOME", raising=False)
    return target


def _report(chain: dict, digest: str, *, workflow: str = "wf", **extra) -> dict:
    entry = {
        "schema": "epi-witness/v1",
        "type": "epi.sealed",
        "seal_seq": chain["seq"],
        "ledger_id": chain["ledger_id"],
        "key_fingerprint": chain["key_fingerprint"],
        "prev_seq": chain["prev_seq"],
        "prev_content_digest": chain["prev_content_digest"],
        "content_digest": digest,
        "manifest_hash": "m-" + digest,
        "file_sha256": "f-" + digest,
        "workflow_id": workflow,
    }
    entry.update(extra)
    return entry


def test_sequential_seals_number_and_link(ledger: Path) -> None:
    first = seal_ledger.allocate(KEY)
    assert first["seq"] == 1
    assert first["prev_seq"] == 0
    assert first["prev_content_digest"] == "genesis"
    assert seal_ledger.commit(first, "digest-1")

    second = seal_ledger.allocate(KEY)
    assert second["seq"] == 2
    assert second["prev_seq"] == 1
    assert second["prev_content_digest"] == "digest-1"
    assert seal_ledger.commit(second, "digest-2")

    third = seal_ledger.allocate(KEY)
    assert third["seq"] == 3
    assert third["prev_seq"] == 2
    assert third["prev_content_digest"] == "digest-2"
    assert seal_ledger.commit(third, "digest-3")

    assert first["ledger_id"] == second["ledger_id"] == third["ledger_id"]
    state = seal_ledger.load(KEY)
    assert state is not None
    assert state["last_committed_seq"] == 3
    assert state["last_content_digest"] == "digest-3"
    assert state["pending"] == {}
    assert state["burns"] == []


def test_overlapping_reservations_both_commit_and_audit_clean(ledger: Path) -> None:
    """Fix #1: seq 6 links to the last COMMITTED seal, not necessarily seq-1."""
    first = seal_ledger.allocate(KEY)
    second = seal_ledger.allocate(KEY)
    assert first["seq"] == 1 and second["seq"] == 2
    assert second["prev_seq"] == 0  # first was not committed yet
    assert second["prev_content_digest"] == "genesis"

    # Commit out of order, as two concurrent seals can.
    assert seal_ledger.commit(second, "digest-2")
    assert seal_ledger.commit(first, "digest-1")

    result = seal_ledger.analyze([_report(first, "digest-1"), _report(second, "digest-2")])
    assert result["ok"] is True
    assert result["problems"] == {
        "missing": 0,
        "forks": 0,
        "chain_breaks": 0,
        "tail_gaps": 0,
        "approval_reuse": 0,
    }


def test_concurrent_allocations_across_processes(ledger: Path) -> None:
    """20 separate processes: no duplicate and no skipped number."""
    script = (
        "import json\n"
        "from epi_core import seal_ledger\n"
        "chain = seal_ledger.allocate('" + KEY + "')\n"
        "ok = seal_ledger.commit(chain, 'digest-%s' % chain['seq'])\n"
        "print(json.dumps({'chain': chain, 'ok': ok}), flush=True)\n"
    )
    env = os.environ.copy()
    env["EPI_SEAL_LEDGER_DIR"] = str(ledger)
    env.pop("EPI_HOME", None)
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(20)
    ]
    results = []
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=180)
        assert proc.returncode == 0, stderr
        results.append(json.loads(stdout.strip().splitlines()[-1]))

    assert all(item["ok"] for item in results)
    seqs = sorted(item["chain"]["seq"] for item in results)
    assert seqs == list(range(1, 21))
    assert len({item["chain"]["ledger_id"] for item in results}) == 1

    state = seal_ledger.load(KEY)
    assert state is not None
    assert state["seq"] == 20
    assert state["last_committed_seq"] == 20
    assert state["pending"] == {}
    assert state["burns"] == []


def test_live_reservations_from_two_processes_are_not_burned(ledger: Path) -> None:
    """Fix #2: a live holder's reservation survives another process allocating."""
    script = (
        "import json, time\n"
        "from epi_core import seal_ledger\n"
        "chain = seal_ledger.allocate('" + KEY + "')\n"
        "print(json.dumps(chain), flush=True)\n"
        "time.sleep(60)\n"
    )
    env = os.environ.copy()
    env["EPI_SEAL_LEDGER_DIR"] = str(ledger)
    env.pop("EPI_HOME", None)
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        child_chain = json.loads(child.stdout.readline())
        mine = seal_ledger.allocate(KEY)
        state = seal_ledger.load(KEY)
        assert state is not None
        assert state["burns"] == []
        assert str(child_chain["seq"]) in state["pending"]
        assert str(mine["seq"]) in state["pending"]
    finally:
        child.kill()
        child.wait(timeout=30)

    # Only after the holder is gone may its reservation be recorded as burned.
    seal_ledger.allocate(KEY)
    state = seal_ledger.load(KEY)
    assert state is not None
    assert any(burn["seq"] == child_chain["seq"] for burn in state["burns"])


def test_abandoned_reservation_burns_after_stale_timeout(
    ledger: Path, monkeypatch
) -> None:
    monkeypatch.setenv("EPI_SEAL_LEDGER_STALE_SECONDS", "0.01")
    abandoned = seal_ledger.allocate(KEY)
    time.sleep(0.05)
    fresh = seal_ledger.allocate(KEY)
    state = seal_ledger.load(KEY)
    assert state is not None
    assert any(burn["seq"] == abandoned["seq"] for burn in state["burns"])
    assert str(fresh["seq"]) in state["pending"]


def test_commit_is_idempotent_for_a_resigned_seal(ledger: Path) -> None:
    chain = seal_ledger.allocate(KEY)
    assert seal_ledger.commit(chain, "digest-1")
    assert seal_ledger.commit(chain, "digest-1") is False
    state = seal_ledger.load(KEY)
    assert state is not None
    assert state["last_committed_seq"] == 1
    assert state["last_content_digest"] == "digest-1"


def test_each_key_has_its_own_chain(ledger: Path) -> None:
    one = seal_ledger.allocate("key-one")
    two = seal_ledger.allocate("key-two")
    assert one["seq"] == 1 and two["seq"] == 1
    assert one["ledger_id"] != two["ledger_id"]
    seal_ledger.commit(one, "d1")
    seal_ledger.commit(two, "d2")
    assert len(seal_ledger.all_states()) == 2


def test_audit_finds_missing_fork_chain_break_tail_gap_and_new_chain(
    ledger: Path,
) -> None:
    chain = seal_ledger.allocate(KEY)
    entries = [
        _report(chain, "d1", workflow="w1"),
        _report(
            {**chain, "seq": 3, "prev_seq": 1, "prev_content_digest": "d1"},
            "d3",
            workflow="w3",
        ),
        _report(
            {**chain, "seq": 4, "prev_seq": 3, "prev_content_digest": "WRONG"},
            "d4",
            workflow="w4",
        ),
        _report(
            {**chain, "seq": 5, "prev_seq": 4, "prev_content_digest": "d4"},
            "d5",
            workflow="w5",
        ),
        _report(
            {**chain, "seq": 5, "prev_seq": 4, "prev_content_digest": "d4"},
            "d5-other",
            workflow="w5b",
        ),
        {
            "schema": "epi-witness/v1",
            "type": "epi.heartbeat",
            "ledger_id": chain["ledger_id"],
            "key_fingerprint": KEY,
            "last_seq": 10,
            "burned_seqs": [7],
        },
        # A second chain on the same key, starting at #1.
        _report(
            {**chain, "ledger_id": "other-ledger", "seq": 1, "prev_seq": 0},
            "d9",
            workflow="w9",
        ),
    ]
    result = seal_ledger.analyze(entries)
    chain_result = next(
        item for item in result["chains"] if item["ledger_id"] == chain["ledger_id"]
    )

    assert chain_result["missing"] == [2]
    assert [fork["seq"] for fork in chain_result["forks"]] == [5]
    assert [brk["seq"] for brk in chain_result["chain_breaks"]] == [4]
    assert chain_result["tail_gap"] == {
        "heartbeat_last_seq": 10,
        "received_last_seq": 5,
        "missing_count": 4,
        "declared_burns": [7],
    }
    assert chain_result["burned"] == [7]
    other = next(item for item in result["chains"] if item["ledger_id"] == "other-ledger")
    assert other["new_chain"] is True

    assert result["problems"]["missing"] == 1
    assert result["problems"]["forks"] == 1
    assert result["problems"]["chain_breaks"] == 1
    assert result["problems"]["tail_gaps"] == 1
    assert result["warnings"]["burned"] == 1
    assert result["ok"] is False


def test_vendor_declared_burn_is_reported_and_never_clean(ledger: Path) -> None:
    chain = seal_ledger.allocate(KEY)
    entries = [
        _report(chain, "d1"),
        _report(
            {**chain, "seq": 3, "prev_seq": 1, "prev_content_digest": "d1"}, "d3"
        ),
        {
            "schema": "epi-witness/v1",
            "type": "epi.heartbeat",
            "ledger_id": chain["ledger_id"],
            "key_fingerprint": KEY,
            "last_seq": 3,
            "burned_seqs": [2],
        },
    ]
    result = seal_ledger.analyze(entries)
    chain_result = result["chains"][0]
    assert chain_result["missing"] == []  # not silently treated as missing
    assert chain_result["burned"] == [2]  # ...but not silently clean either
    assert chain_result["burn_rate"] > 0
    assert result["warnings"]["burned"] == 1
    assert result["ok"] is True  # default is a warning; --strict fails it


def test_burn_that_was_actually_received_is_a_conflict(ledger: Path) -> None:
    chain = seal_ledger.allocate(KEY)
    seal_ledger.commit(chain, "d1")
    result = seal_ledger.analyze(
        [
            _report(chain, "d1"),
            {
                "type": "epi.heartbeat",
                "ledger_id": chain["ledger_id"],
                "key_fingerprint": KEY,
                "last_seq": 1,
                "burned_seqs": [1],
            },
        ]
    )
    assert result["chains"][0]["burn_conflicts"] == [1]
    assert result["warnings"]["burn_conflicts"] == 1


def test_old_unsequenced_reports_are_never_errors(ledger: Path) -> None:
    result = seal_ledger.analyze(
        [
            {"workflow_id": "old-1", "manifest_hash": "m", "file_sha256": "f"},
            {"workflow_id": "old-2", "manifest_hash": "m", "file_sha256": "f"},
        ]
    )
    assert result["ok"] is True
    assert result["unsequenced"] == 2
    assert result["chains"] == []
