"""Tests for AGT artifact type detection."""

import json
from pathlib import Path

import pytest

from epi_recorder.integrations.agt_adapter.detect import (
    detect_artifact_type,
    detect_file_format,
    detect_agt_version,
    AGTArtifactType,
)
from epi_recorder.integrations.agt_adapter.errors import AGTArtifactError


class TestDetectArtifactType:
    def test_export_bundle(self, fixture_agt_current):
        result = detect_artifact_type(fixture_agt_current)
        assert result == AGTArtifactType.EXPORT_BUNDLE

    def test_single_entry(self):
        data = {"entry_id": "x", "event_type": "tool_invocation"}
        result = detect_artifact_type(data)
        assert result == AGTArtifactType.SINGLE_ENTRY

    def test_cloudevents(self):
        data = {"specversion": "1.0", "type": "ai.agentmesh.tool.invoked", "id": "x"}
        result = detect_artifact_type(data)
        assert result == AGTArtifactType.CLOUDEVENTS

    def test_unknown(self):
        data = {"foo": "bar"}
        result = detect_artifact_type(data)
        assert result == AGTArtifactType.UNKNOWN


class TestDetectFileFormat:
    def test_json_file(self, tmp_path, fixture_agt_current):
        f = tmp_path / "audit.json"
        f.write_text(json.dumps(fixture_agt_current))
        atype, entries = detect_file_format(f)
        assert atype == AGTArtifactType.EXPORT_BUNDLE
        assert len(entries) == 6

    def test_jsonl_file(self, tmp_path, fixture_agt_fileaudit):
        f = tmp_path / "audit.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in fixture_agt_fileaudit))
        atype, entries = detect_file_format(f)
        assert atype == AGTArtifactType.FILE_AUDIT_SINK
        assert len(entries) == 2

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("")
        with pytest.raises(AGTArtifactError):
            detect_file_format(f)

    def test_missing_file(self, tmp_path):
        with pytest.raises(AGTArtifactError):
            detect_file_format(tmp_path / "nonexistent.json")


class TestDetectVersion:
    def test_current(self, fixture_agt_current):
        v = detect_agt_version(fixture_agt_current["entries"])
        assert v == "4.1+"

    def test_old(self, fixture_agt_old):
        v = detect_agt_version(fixture_agt_old["entries"])
        assert v == "4.0"

    def test_unknown(self):
        v = detect_agt_version([{"foo": "bar"}])
        assert v == "unknown"

    def test_empty(self):
        v = detect_agt_version([])
        assert v == "unknown"
