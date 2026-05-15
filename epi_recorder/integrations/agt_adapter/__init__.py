"""AGT ↔ EPI Integration Layer.

Zero AGT runtime dependencies. Only consumes exported AGT evidence artifacts.

Usage:
    # Import AGT evidence → EPI artifact
    from epi_recorder.integrations.agt_adapter import import_agt
    epi_path, report = import_agt("audit_export.json")

    # Export EPI evidence → signed receipt for AGT
    from epi_recorder.integrations.agt_adapter import export_evidence_receipt, build_agt_log_data
    receipt = export_evidence_receipt("trace.epi")
    log_data = build_agt_log_data(receipt, "trace.epi")
    audit.log(event_type="external_evidence", ..., data=log_data)
"""

from .importer import import_agt
from .exporter import export_evidence_receipt, verify_evidence_receipt, build_agt_log_data
from .detect import detect_file_format, detect_artifact_type, detect_agt_version
from .schemas import MappingReport, EEOAPStatement, AGTExportBundle
from .errors import AGTIntegrationError, AGTArtifactError, AGTVersionError

__all__ = [
    # Importer
    "import_agt",
    # Exporter
    "export_evidence_receipt",
    "verify_evidence_receipt",
    "build_agt_log_data",
    # Detection
    "detect_file_format",
    "detect_artifact_type",
    "detect_agt_version",
    # Schemas
    "MappingReport",
    "EEOAPStatement",
    "AGTExportBundle",
    # Errors
    "AGTIntegrationError",
    "AGTArtifactError",
    "AGTVersionError",
]
