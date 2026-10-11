"""TRACE origin.producer is the exporter package version, not artifact spec_version."""

import pytest
from pathlib import Path

from epi_core._version import get_version
from epi_recorder.integrations.trace_exporter import epi_to_trace_record

pytestmark = pytest.mark.experimental

def test_origin_producer_uses_package_version_not_artifact_spec() -> None:
    path = Path(__file__).resolve().parent / "goldens" / "legacy-spec-4.3.0.epi"
    rec = epi_to_trace_record(path)
    assert rec["origin"]["producer"] == f"epi-recorder/{get_version()}"
    assert rec["origin"]["producer"] != "epi-recorder/4.3.0"
