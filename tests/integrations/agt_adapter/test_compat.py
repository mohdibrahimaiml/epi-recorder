"""Tests for version compatibility and malformed handling."""

import pytest

from epi_recorder.integrations.agt_adapter.compat import (
    check_version_support,
    get_known_fields,
    is_forward_compatible,
    MIN_SUPPORTED_VERSION,
)
from epi_recorder.integrations.agt_adapter.errors import AGTVersionError


class TestVersionSupport:
    def test_supported_version(self):
        # Should not raise
        check_version_support("4.1")
        check_version_support("3.5")
        check_version_support("unknown")

    def test_unsupported_version(self):
        with pytest.raises(AGTVersionError):
            check_version_support("2.0")

    def test_known_fields_current(self):
        fields = get_known_fields("4.1+")
        assert "signature" in fields
        assert "content_hash" in fields

    def test_known_fields_old(self):
        fields = get_known_fields("4.0")
        assert "policy_decision" in fields
        assert "signature" not in fields

    def test_forward_compatible(self):
        assert is_forward_compatible("4.1", "4.2")
        assert not is_forward_compatible("3.0", "4.0")
