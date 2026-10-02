"""Capture Manifest tests (Feature 1)."""

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path


def _seal_simple(out: Path) -> Path:
    os.environ["EPI_NOTARIZE"] = "0"
    from epi_recorder import record

    with record(str(out)) as epi:
        epi.log_step("llm.request", {"provider": "openai", "model": "gpt-4", "messages": []})
        epi.log_step("llm.response", {"ok": True})
    return out


def test_sealed_artifact_has_manifest():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "a.epi"
        _seal_simple(out)
        from epi_core.container import EPIContainer

        members = EPIContainer.list_members(out)
        assert "artifacts/manifest.json" in members
        data = EPIContainer.read_member_json(out, "artifacts/manifest.json")
        assert data["schema_version"] == "1.0"
        assert data["recorder_version"]
        assert isinstance(data["instrumented_surfaces"], list) and data["instrumented_surfaces"]
        assert isinstance(data["known_gaps"], list) and len(data["known_gaps"]) > 0


def test_fail_open_warning_in_verifier_topline():
    """fail_open_events non-empty => verifier top-line includes downgrade warning."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "b.epi"
        _seal_simple(out)
        from epi_core.container import EPIContainer

        # Inject a fail-open event into the sealed manifest by unpacking,
        # editing, and repacking WITHOUT preserve (test-only re-seal).
        tmp = Path(td) / "ws"
        EPIContainer.unpack(out, tmp)
        mp = tmp / "artifacts" / "manifest.json"
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["fail_open_events"] = [
            {"event_id": "evt_1", "timestamp": "2026-01-01T00:00:00Z", "reason": "client_header_override"}
        ]
        data["gateway_enforcement"] = "mixed"
        mp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        from epi_core.schemas import ManifestModel

        manifest = EPIContainer.read_manifest(out)
        out2 = Path(td) / "b2.epi"
        EPIContainer.pack(tmp, manifest, out2, preserve_generated=True)

        # Build a minimal report and check print_trust_report top-line.
        from epi_cli.verify import print_trust_report

        report = {
            "facts": {
                "integrity_ok": True,
                "signature_valid": None,
                "sequence_ok": True,
                "completeness_ok": True,
                "chain_ok": True,
            },
            "identity": {"status": "UNKNOWN", "name": None, "detail": ""},
            "decision": {"status": "PASS", "policy": "standard", "reason": "ok"},
            "summary": {"integrity": "VALID"},
            "capture_manifest": data,
            "capture_manifest_present": True,
            "enforcement_downgrade_count": 1,
        }
        import contextlib
        buf = io.StringIO()
        # Rich console writes to stdout; capture via redirect
        import sys
        old = sys.stdout
        sys.stdout = buf
        try:
            print_trust_report(report, out2, False)
        finally:
            sys.stdout = old
        text = buf.getvalue()
        assert "enforcement downgraded for 1 events" in text


def test_streaming_implies_not_gateway():
    """Invariant: streaming=true implies capture_path is never gateway for that segment."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        (ws / "artifacts").mkdir(parents=True)
        # Synthetic steps: one streaming step tagged gateway (invalid input)
        steps = [
            {"index": 0, "kind": "llm.request",
             "content": {"stream": True, "_epi_capture": {
                 "capture_path": "gateway", "gateway_enforcement": "fail_closed",
                 "streaming": True, "event_id": "e0"}},
             "timestamp": "2026-01-01T00:00:00Z", "prev_hash": "CHAIN_START"},
        ]
        (ws / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")
        from epi_core.manifest import build_capture_manifest

        m = build_capture_manifest(ws)
        for seg in m.segments:
            if seg.streaming:
                assert seg.capture_path != "gateway"


def test_manifest_covered_by_integrity_chain():
    """Mutating manifest.json post-seal breaks verification."""
    import copy
    import zipfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "c.epi"
        _seal_simple(out)
        from epi_core.container import (
            EPIContainer,
            EPI_CONTAINER_FORMAT_LEGACY,
        )

        ok, _ = EPIContainer.verify_integrity(out)
        assert ok

        # artifacts/manifest.json must be hash-chained (in file_manifest).
        manifest = EPIContainer.read_manifest(out)
        assert "artifacts/manifest.json" in manifest.file_manifest

        # Genuine tamper proof on a legacy-zip artifact (the .epi IS the zip,
        # so a post-seal byte mutation is a faithful tamper simulation).
        tmp = Path(td) / "ws2"
        EPIContainer.unpack(out, tmp)
        legacy_out = Path(td) / "c_legacy.epi"
        EPIContainer.pack(
            tmp,
            copy.deepcopy(manifest),
            legacy_out,
            preserve_generated=True,
            container_format=EPI_CONTAINER_FORMAT_LEGACY,
        )
        ok_leg, _ = EPIContainer.verify_integrity(legacy_out)
        assert ok_leg
        with zipfile.ZipFile(legacy_out, "a") as zf:
            zf.writestr("artifacts/manifest.json", '{"tampered": true}')
        ok2, mism2 = EPIContainer.verify_integrity(legacy_out)
        assert ok2 is False
        assert "artifacts/manifest.json" in mism2


def test_old_artifact_without_manifest_handled_gracefully():
    """Verifier handles manifest.json absent: scope undeclared, no crash."""
    import io, sys
    from epi_cli.verify import print_trust_report

    report = {
        "facts": {
            "integrity_ok": True,
            "signature_valid": None,
            "sequence_ok": True,
            "completeness_ok": True,
            "chain_ok": True,
        },
        "identity": {"status": "UNKNOWN", "name": None, "detail": ""},
        "decision": {"status": "PASS", "policy": "standard", "reason": "ok"},
        "summary": {"integrity": "VALID"},
        "capture_manifest": None,
        "capture_manifest_present": False,
        "enforcement_downgrade_count": 0,
    }
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        print_trust_report(report, "legacy.epi", False)
    finally:
        sys.stdout = old
    text = buf.getvalue()
    assert "scope undeclared" in text


def test_active_surfaces_reflect_run_not_capabilities():
    """active_surfaces derives from sealed steps (did see), while
    instrumented_surfaces stays the capability list (can see)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "e.epi"
        _seal_simple(out)
        from epi_core.container import EPIContainer

        data = EPIContainer.read_member_json(out, "artifacts/manifest.json")
        assert "sdk_wrapper:openai.chat.completions" in data["active_surfaces"]
        # Capability list is global; active list is per-run evidence.
        assert len(data["instrumented_surfaces"]) > len(data["active_surfaces"])


def test_active_surfaces_gateway_and_empty_cases():
    import json as _json
    from epi_core.manifest import build_capture_manifest

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        (ws / "artifacts").mkdir(parents=True)
        steps = [
            {"index": 0, "kind": "llm.request",
             "content": {"provider": "anthropic",
                         "_epi_capture": {"capture_path": "gateway",
                                          "gateway_enforcement": "fail_closed",
                                          "streaming": False, "event_id": "g0"}},
             "timestamp": "2026-01-01T00:00:00Z", "prev_hash": "CHAIN_START"},
            {"index": 1, "kind": "langgraph.checkpoint.save",
             "content": {"_epi_capture": {"capture_path": "sdk_wrapper",
                                          "gateway_enforcement": "not_applicable",
                                          "streaming": False}},
             "timestamp": "2026-01-01T00:00:01Z", "prev_hash": "x"},
        ]
        (ws / "steps.jsonl").write_text("\n".join(_json.dumps(s) for s in steps), encoding="utf-8")
        m = build_capture_manifest(ws)
        assert "gateway:anthropic.messages" in m.active_surfaces
        assert "sdk_wrapper:integration.langgraph" in m.active_surfaces

    # Empty workspace: capabilities listed, nothing active — never guessed.
    with tempfile.TemporaryDirectory() as td2:
        ws2 = Path(td2) / "ws"
        ws2.mkdir(parents=True)
        m2 = build_capture_manifest(ws2)
        assert m2.active_surfaces == []
        assert len(m2.instrumented_surfaces) > 0


def test_manifest_build_failure_leaves_declared_marker(monkeypatch):
    """A builder failure seals scope-undeclared but declares the absence via
    a hash-chained marker file — never a silent gap."""
    os.environ["EPI_NOTARIZE"] = "0"
    os.environ["EPI_CHECKPOINTS_ENABLED"] = "0"

    def _boom(_source_dir):
        raise RuntimeError("simulated builder failure")

    monkeypatch.setattr("epi_core.manifest.build_capture_manifest", _boom)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "m.epi"
        _seal_simple(out)
        from epi_core.container import EPIContainer

        assert "artifacts/manifest_build_failed.txt" in EPIContainer.list_members(out)
        manifest = EPIContainer.read_manifest(out)
        assert "artifacts/manifest_build_failed.txt" in manifest.file_manifest
        ok, _ = EPIContainer.verify_integrity(out)
        assert ok
