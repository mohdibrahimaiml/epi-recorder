"""Custom exceptions for AGT ↔ EPI integration."""


class AGTIntegrationError(Exception):
    """Base exception for AGT integration failures."""


class AGTArtifactError(AGTIntegrationError):
    """Raised when an AGT artifact cannot be parsed or is malformed."""


class AGTVersionError(AGTIntegrationError):
    """Raised when an AGT artifact version is unsupported."""


class AGTTransformError(AGTIntegrationError):
    """Raised when a field transformation fails."""


class AGTMappingError(AGTIntegrationError):
    """Raised when the mapping report indicates unhandled data loss."""
