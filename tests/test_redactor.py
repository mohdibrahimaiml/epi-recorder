"""
Tests for epi_core.redactor - Secret redaction functionality.

Tests regex-based pattern matching for API keys, tokens, and credentials.
"""

import pytest
import tempfile
from pathlib import Path

from epi_core.redactor import Redactor, REDACTION_PLACEHOLDER


class TestRedactor:
    """Test suite for Redactor class."""
    
    def test_redactor_enabled_by_default(self):
        """Test that redaction is enabled by default."""
        redactor = Redactor()
        assert redactor.enabled is True
    
    def test_redactor_can_be_disabled(self):
        """Test that redaction can be disabled."""
        redactor = Redactor(enabled=False)
        
        data = {"api_key": "sk-abc123def456"}
        redacted, count = redactor.redact(data)
        
        assert redacted == data
        assert count == 0
    
    def test_redact_openai_api_key(self):
        """Test redacting OpenAI API keys."""
        redactor = Redactor()
        
        data = {
            "key": "sk-" + "a" * 48,  # OpenAI format
            "message": "Using key sk-" + "b" * 48 + " for authentication"
        }
        
        redacted, count = redactor.redact(data)
        
        assert REDACTION_PLACEHOLDER in redacted["key"]
        assert REDACTION_PLACEHOLDER in redacted["message"]
        assert count >= 2
    
    def test_redact_anthropic_api_key(self):
        """Test redacting Anthropic API keys."""
        redactor = Redactor()
        
        key = "sk-ant-" + "a" * 95
        data = {"anthropic_key": key}
        
        redacted, count = redactor.redact(data)
        
        assert redacted["anthropic_key"] == REDACTION_PLACEHOLDER
        assert count == 1
    
    def test_redact_bearer_token(self):
        """Test redacting Bearer tokens."""
        redactor = Redactor()
        
        data = {"Authorization": "Bearer abc123def456ghi789jkl012"}
        
        redacted, count = redactor.redact(data)
        
        assert REDACTION_PLACEHOLDER in redacted["Authorization"]
        assert count == 1
    
    def test_redact_aws_credentials(self):
        """Test redacting AWS credentials."""
        redactor = Redactor()
        
        data = {
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret": "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        redacted, count = redactor.redact(data)
        
        assert REDACTION_PLACEHOLDER in redacted["access_key"]
        assert REDACTION_PLACEHOLDER in redacted["secret"]
        assert count >= 2
    
    def test_redact_jwt_token(self):
        """Test redacting JWT tokens."""
        redactor = Redactor()
        
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        data = {"token": jwt}
        
        redacted, count = redactor.redact(data)
        
        assert redacted["token"] == REDACTION_PLACEHOLDER
        assert count == 1
    
    def test_redact_environment_variables(self):
        """Test redacting sensitive environment variable names."""
        redactor = Redactor()
        
        data = {
            "OPENAI_API_KEY": "sk-abc123",
            "PATH": "/usr/bin:/usr/local/bin",
            "SECRET_KEY": "supersecret",
            "NORMAL_VAR": "safe_value"
        }
        
        redacted, count = redactor.redact(data)
        
        assert redacted["OPENAI_API_KEY"] == REDACTION_PLACEHOLDER
        assert redacted["SECRET_KEY"] == REDACTION_PLACEHOLDER
        assert redacted["PATH"] == "/usr/bin:/usr/local/bin"  # Not sensitive
        assert redacted["NORMAL_VAR"] == "safe_value"  # Not sensitive
        assert count == 2
    
    def test_redact_nested_dict(self):
        """Test redacting secrets in nested dictionaries."""
        redactor = Redactor()
        
        data = {
            "config": {
                "api": {
                    "key": "sk-" + "a" * 48,
                    "endpoint": "https://api.example.com"
                }
            }
        }
        
        redacted, count = redactor.redact(data)
        
        assert REDACTION_PLACEHOLDER in redacted["config"]["api"]["key"]
        assert redacted["config"]["api"]["endpoint"] == "https://api.example.com"
        assert count == 1
    
    def test_redact_list_of_dicts(self):
        """Test redacting secrets in list of dictionaries."""
        redactor = Redactor()
        
        data = {
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "My key is sk-" + "a" * 48}
            ]
        }
        
        redacted, count = redactor.redact(data)
        
        assert "You are helpful" in redacted["messages"][0]["content"]
        assert REDACTION_PLACEHOLDER in redacted["messages"][1]["content"]
        assert count == 1
    
    def test_redact_preserves_structure(self):
        """Test that redaction preserves data structure."""
        redactor = Redactor()
        
        data = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        redacted, count = redactor.redact(data)
        
        assert isinstance(redacted["string"], str)
        assert isinstance(redacted["number"], int)
        assert isinstance(redacted["boolean"], bool)
        assert redacted["null"] is None
        assert isinstance(redacted["list"], list)
        assert isinstance(redacted["nested"], dict)
        assert count == 0  # No secrets to redact
    
    def test_redact_dict_keys(self):
        """Test redacting specific dictionary keys by name."""
        redactor = Redactor()
        
        data = {
            "username": "alice",
            "password": "secret123",
            "api_key": "key456",
            "email": "alice@example.com"
        }
        
        sensitive_keys = {"password", "api_key"}
        redacted, count = redactor.redact_dict_keys(data, sensitive_keys)
        
        assert redacted["username"] == "alice"
        assert redacted["password"] == REDACTION_PLACEHOLDER
        assert redacted["api_key"] == REDACTION_PLACEHOLDER
        assert redacted["email"] == "alice@example.com"
        assert count == 2
    
    def test_redact_dict_keys_case_insensitive(self):
        """Test that dict key redaction is case-insensitive."""
        redactor = Redactor()
        
        data = {
            "API_KEY": "key123",
            "api_key": "key456",
            "Api_Key": "key789"
        }
        
        redacted, count = redactor.redact_dict_keys(data, {"api_key"})
        
        assert redacted["API_KEY"] == REDACTION_PLACEHOLDER
        assert redacted["api_key"] == REDACTION_PLACEHOLDER
        assert redacted["Api_Key"] == REDACTION_PLACEHOLDER
        assert count == 3
    
    def test_multiple_secrets_in_string(self):
        """Test redacting multiple secrets in a single string."""
        redactor = Redactor()
        
        text = f"Key 1: sk-{'a' * 48}, Key 2: sk-{'b' * 48}"
        data = {"text": text}
        
        redacted, count = redactor.redact(data)
        
        assert redacted["text"].count(REDACTION_PLACEHOLDER) == 2
        assert count == 2
    
    def test_no_false_positives(self):
        """Test that legitimate text is not redacted."""
        redactor = Redactor()
        
        data = {
            "message": "This is a normal message without secrets",
            "code": "def function(key, value): return key + value",
            "url": "https://api.example.com/v1/endpoint"
        }
        
        redacted, count = redactor.redact(data)
        
        assert redacted == data
        assert count == 0
    
    def test_redactor_disabled(self):
        """Test that redactor can be disabled."""
        redactor = Redactor(enabled=False)
        
        data = {
            "OPENAI_API_KEY": "sk-" + "a" * 48,
            "password": "secret123"
        }
        
        redacted, count = redactor.redact(data)
        
        # Should not redact anything
        assert redacted == data
        assert count == 0
    
    def test_redact_dict_keys_disabled(self):
        """Test that redact_dict_keys respects enabled flag."""
        redactor = Redactor(enabled=False)
        
        data = {"password": "secret123"}
        redacted, count = redactor.redact_dict_keys(data, {"password"})
        
        assert redacted == data
        assert count == 0
    
    def test_invalid_regex_pattern_handling(self):
        """Test that invalid regex patterns are skipped gracefully."""
        # This tests the error handling in __init__ (lines 98-100)
        import re
        from unittest.mock import patch
        
        with patch('epi_core.redactor.DEFAULT_REDACTION_PATTERNS', [(r'(?P<invalid', 'Bad pattern')]):
            # Should not crash, just skip invalid pattern
            redactor = Redactor()
            assert len(redactor.patterns) == 0
    
    def test_get_default_redactor(self):
        """Test get_default_redactor function."""
        from epi_core.redactor import get_default_redactor
        
        redactor = get_default_redactor()
        
        assert isinstance(redactor, Redactor)
        assert redactor.enabled is True
    
    def test_create_default_config(self):
        """Test create_default_config function."""
        import tempfile
        from epi_core.redactor import create_default_config
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.toml"
            
            create_default_config(config_path)
            
            assert config_path.exists()
            content = config_path.read_text()
            assert "[redaction]" in content
            assert "enabled" in content


