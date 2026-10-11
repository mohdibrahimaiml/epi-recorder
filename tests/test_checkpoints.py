"""Forward-Secure Checkpoint tests (Feature 2)."""

import base64
import json
import os
import tempfile
import time
from pathlib import Path

FAKE_TOKEN = b"\x30\x82\x01\x00" + b"\x00" * 100


def _patch_tsa(monkeypatch, token=FAKE_TOKEN):
    import epi_core.notarize as _nz

    monkeypatch.setattr(_nz, "_submit_rfc3161", lambda digest_hex, url="": token)


def test_heartbeat_fires_on_both_thresholds():
    from epi_core.checkpoints import should_checkpoint

    # Event-count threshold
    assert should_checkpoint(0, 5, time.time(), time.time(),
                             interval_events=5, interval_seconds=10000) is True
    assert should_checkpoint(0, 4, time.time(), time.time(),
                             interval_events=5, interval_seconds=10000) is False
    # Time threshold (independent of count)
    old = time.time() - 100
    assert should_checkpoint(0, 1, old, time.time(),
                             interval_events=10000, interval_seconds=60) is True
    now = time.time()
    assert should_checkpoint(0, 1, now, now,
                             interval_events=10000, interval_seconds=60) is False


def test_checkpoint_token_valid_for_hash(monkeypatch):
    _patch_tsa(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        from epi_core.checkpoints import create_checkpoint, recompute_chain_head

        # Build a tiny real chain via RecordingContext hashing
        from epi_core.schemas import StepModel
        from epi_core.serialize import get_canonical_hash

        steps = []
        prev = "CHAIN_START"
        for i in range(3):
            m = StepModel(index=i, kind="llm.request", content={"i": i}, prev_hash=prev)
            prev = get_canonical_hash(m, format="json")
            steps.append(m.model_dump(mode="json"))
        head = prev
        rec = create_checkpoint(ws, index=0, event_count=3, chain_head=head)
        assert rec["tsa_available"] is True
        token = base64.b64decode(rec["tsa_token_b64"])
        # Valid RFC 3161 response sanity (same as _submit_rfc3161): DER, len, magic
        assert len(token) > 10 and token[0] == 0x30
        assert token == FAKE_TOKEN
        assert rec["chain_head"] == head
        assert recompute_chain_head(steps, 3) == head


def _seal_with_checkpoints(monkeypatch, out: Path, n_steps: int = 6) -> Path:
    _patch_tsa(monkeypatch)
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    from epi_recorder import record

    with record(str(out)) as epi:
        for i in range(n_steps):
            epi.log_step("llm.request", {"provider": "openai", "n": i})
    return out


def test_trim_detection_reports_specific_message(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "a.epi"
        _seal_with_checkpoints(monkeypatch, out)
        from epi_core.container import EPIContainer
        from epi_core.checkpoints import verify_checkpoints

        steps = EPIContainer.read_steps(out)
        ok, msgs, recs = verify_checkpoints(out, steps)
        assert ok and len([r for r in recs if r.get("tsa_available")]) > 0

        # Trim: unpack, drop last 3 steps, repack preserving checkpoints
        tmp = Path(td) / "ws"
        EPIContainer.unpack(out, tmp)
        lines = (tmp / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        trimmed = [line for line in lines if line.strip()][:-3]
        (tmp / "steps.jsonl").write_text("\n".join(trimmed), encoding="utf-8")
        import copy

        manifest = EPIContainer.read_manifest(out)
        manifest2 = copy.deepcopy(manifest)
        out2 = Path(td) / "trimmed.epi"
        monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
        EPIContainer.pack(tmp, manifest2, out2, preserve_generated=True)
        steps2 = EPIContainer.read_steps(out2)
        ok2, msgs2, _ = verify_checkpoints(out2, steps2)
        assert ok2 is False
        blob = " | ".join(msgs2)
        assert ("TRIMMED" in blob) or ("CHECKPOINT MISMATCH" in blob)
        # Not a generic failure alone — specific index/count info present
        assert ("checkpoint" in blob.lower())


def test_repack_does_not_regenerate_checkpoints(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "b.epi"
        _seal_with_checkpoints(monkeypatch, out)
        from epi_core.container import EPIContainer

        before = {
            m: EPIContainer.read_member_bytes(out, m)
            for m in EPIContainer.list_members(out)
            if m.startswith("artifacts/checkpoints/")
        }
        assert before
        tmp = Path(td) / "ws"
        EPIContainer.unpack(out, tmp)
        import copy

        manifest = EPIContainer.read_manifest(out)
        out2 = Path(td) / "b2.epi"
        monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
        EPIContainer.pack(tmp, copy.deepcopy(manifest), out2, preserve_generated=True)
        after = {
            m: EPIContainer.read_member_bytes(out2, m)
            for m in EPIContainer.list_members(out2)
            if m.startswith("artifacts/checkpoints/")
        }
        assert set(after.keys()) == set(before.keys())
        for k in before:
            assert after[k] == before[k]


def test_checkpoint_suppressed_when_disabled(monkeypatch):
    """EPI_CHECKPOINTS_ENABLED=0 (repack mode) creates no new checkpoints."""
    _patch_tsa(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "d.epi"
        monkeypatch.setenv("EPI_NOTARIZE", "0")
        monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
        monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "1")
        monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "1")
        from epi_recorder import record

        with record(str(out)) as epi:
            for i in range(4):
                epi.log_step("llm.request", {"n": i})
        from epi_core.container import EPIContainer

        members = EPIContainer.list_members(out)
        assert not [m for m in members if m.startswith("artifacts/checkpoints/")]


def test_tsa_outage_does_not_fail_run_and_gaps_manifest(monkeypatch):
    import epi_core.notarize as _nz

    monkeypatch.setattr(_nz, "_submit_rfc3161", lambda digest_hex, url="": None)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "c.epi"
        monkeypatch.setenv("EPI_NOTARIZE", "0")
        monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")
        monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
        monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
        from epi_recorder import record

        with record(str(out)) as epi:  # must not raise
            for i in range(5):
                epi.log_step("llm.request", {"n": i})
        assert out.exists()
        from epi_core.container import EPIContainer

        data = EPIContainer.read_member_json(out, "artifacts/manifest.json")
        gaps = data.get("known_gaps", [])
        assert any("TSA unavailable" in g or "checkpoint" in g.lower() for g in gaps)


def test_add_step_does_not_block_on_slow_tsa(monkeypatch, tmp_path):
    """A 2 s TSA must not slow 100 add_step calls (would be ~200 s synchronous)."""
    import time

    import epi_core.notarize as _nz

    def slow_submit(digest_hex, url=""):
        time.sleep(2)
        return None

    monkeypatch.setattr(_nz, "_submit_rfc3161", slow_submit)
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    from epi_recorder.patcher import RecordingContext

    ctx = RecordingContext(tmp_path / "ws")
    started = time.monotonic()
    for i in range(100):
        ctx.add_step("llm.request", {"n": i})
    elapsed = time.monotonic() - started
    assert elapsed < 10, f"add_step blocked on TSA: {elapsed:.1f}s for 100 steps"
    ctx.finalize()
    # Drain (default 10 s) cannot finish 100 x 2 s submits: a gap is recorded
    # instead of failing or hanging the run.
    gaps_path = tmp_path / "ws" / "artifacts" / "capture_gaps.json"
    assert gaps_path.is_file()
    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    assert any("drain timed out" in g for g in gaps)


def test_finalize_drains_background_checkpoints(monkeypatch, tmp_path):
    """After finalize, every enqueued checkpoint file exists (or a gap)."""
    _patch_tsa(monkeypatch)
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "2")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    from epi_recorder.patcher import RecordingContext

    ctx = RecordingContext(tmp_path / "ws")
    for i in range(6):
        ctx.add_step("llm.request", {"n": i})
    ctx.finalize()
    cp_dir = tmp_path / "ws" / "artifacts" / "checkpoints"
    files = sorted(cp_dir.glob("*.json"))
    assert len(files) == 3
    for p in files:
        rec = json.loads(p.read_text(encoding="utf-8"))
        assert rec["tsa_available"] is True
        assert "tsa_token_b64" in rec
    gaps_path = tmp_path / "ws" / "artifacts" / "capture_gaps.json"
    if gaps_path.is_file():
        gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
        assert not any("drain timed out" in g for g in gaps)


def test_drain_timeout_records_gap(monkeypatch, tmp_path):
    """Unfinished checkpoints at drain deadline become a runtime gap."""
    import time

    import epi_core.notarize as _nz

    def slow_submit(digest_hex, url=""):
        time.sleep(2)
        return None

    monkeypatch.setattr(_nz, "_submit_rfc3161", slow_submit)
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_EVENTS", "1")
    monkeypatch.setenv("EPI_CHECKPOINT_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("EPI_CHECKPOINT_DRAIN_SECONDS", "1")
    from epi_core.checkpoints import CheckpointSubmitter

    submitter = CheckpointSubmitter(tmp_path / "ws")
    submitter.submit(0, 1, "a" * 64)
    leftover = submitter.drain()
    assert leftover >= 1
    # CheckpointSubmitter alone writes no gaps; finalize() does that wiring
    # (covered by test_add_step_does_not_block_on_slow_tsa).
