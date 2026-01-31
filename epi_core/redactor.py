"""
EPI Core Redactor - Automatic secret redaction for security.

Provides regex-based pattern matching to automatically remove sensitive
information like API keys, tokens, and credentials from captured data.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
import json


# Default redaction patterns (security-first)
DEFAULT_REDACTION_PATTERNS = [
    # OpenAI API keys
    (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API key'),
    (r'sk-proj-[a-zA-Z0-9_-]{48,}', 'OpenAI Project API key'),
    
    # Anthropic API keys
    (r'sk-ant-[a-zA-Z0-9_-]{95,}', 'Anthropic API key'),
    
    # Google/Gemini API keys
    (r'AIza[a-zA-Z0-9_-]{35}', 'Google API key'),
    
    # Generic Bearer tokens
    (r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', 'Bearer token'),
    
    # AWS credentials
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key'),
    (r'aws_secret_access_key\s*=\s*[a-zA-Z0-9/+=]{40}', 'AWS Secret Key'),
    
    # GitHub tokens
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token'),
    (r'gho_[a-zA-Z0-9]{36}', 'GitHub OAuth Token'),
    
    # Generic API keys (common patterns)
    (r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{32,})', 'Generic API key'),
    (r'apikey["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{32,})', 'Generic API key'),
    
    # JWT tokens
    (r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}', 'JWT token'),
    
    # Database connection strings
    (r'postgres://[^:]+:[^@]+@[^/]+', 'PostgreSQL connection string'),
    (r'mysql://[^:]+:[^@]+@[^/]+', 'MySQL connection string'),
    (r'mongodb://[^:]+:[^@]+@[^/]+', 'MongoDB connection string'),
    
    # Private keys (PEM format)
    (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]+?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----', 'Private key'),
]

# Environment variable names to redact
REDACT_ENV_VARS = {
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'GOOGLE_API_KEY',
    'GEMINI_API_KEY',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'GITHUB_TOKEN',
    'API_KEY',
    'SECRET_KEY',
    'DATABASE_URL',
    'DB_PASSWORD',
    'PASSWORD',
    'SECRET',
}

REDACTION_PLACEHOLDER = "***REDACTED***"


class Redactor:
    """
    Redacts sensitive information using configurable regex patterns.
    
    Automatically removes API keys, tokens, credentials, and other secrets
    from captured workflow data.
    """
    
    def __init__(self, config_path: Path | None = None, enabled: bool = True, allowlist: List[str] = None):
        """
        Initialize redactor with optional custom configuration.
        
        Args:
            config_path: Optional path to config.toml with custom patterns
            enabled: Whether redaction is enabled (default: True)
            allowlist: Optional list of strings to NEVER redact
        """
        self.enabled = enabled
        self.patterns: List[Tuple[re.Pattern, str]] = []
        self.env_vars_to_redact = REDACT_ENV_VARS.copy()
        self.allowlist = set(allowlist) if allowlist else set()
        
        # Compile default patterns
        for pattern_str, description in DEFAULT_REDACTION_PATTERNS:
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                self.patterns.append((compiled, description))
            except re.error as e:
                # Skip invalid patterns (should not happen with defaults)
                print(f"Warning: Invalid pattern '{pattern_str}': {e}")
        
        # Load custom config if provided
        if config_path and config_path.exists():
            self._load_config(config_path)
    
    def _load_config(self, config_path: Path):
        """
        Load custom redaction patterns from TOML config.
        
        Args:
            config_path: Path to config.toml
        """
        try:
            import tomllib  # Python 3.11+
            
            with open(config_path, 'rb') as f:
                config = tomllib.load(f)
            
            # Load custom patterns
            if 'redaction' in config and 'patterns' in config['redaction']:
                for pattern_dict in config['redaction']['patterns']:
                    pattern_str = pattern_dict.get('pattern')
                    description = pattern_dict.get('description', 'Custom pattern')
                    
                    if pattern_str:
                        try:
                            compiled = re.compile(pattern_str, re.IGNORECASE)
                            self.patterns.append((compiled, description))
                        except re.error as e:
                            print(f"Warning: Invalid custom pattern '{pattern_str}': {e}")
            
            # Load custom env vars
            if 'redaction' in config and 'env_vars' in config['redaction']:
                self.env_vars_to_redact.update(config['redaction']['env_vars'])
                
            # Load allowlist
            if 'redaction' in config and 'allowlist' in config['redaction']:
                self.allowlist.update(config['redaction']['allowlist'])
        
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
    
    def redact(self, data: Any) -> Tuple[Any, int]:
        """
        Redact sensitive information from data.
        
        Recursively processes dicts, lists, and strings to find and replace
        sensitive patterns with REDACTION_PLACEHOLDER.
        
        Args:
            data: Data to redact (dict, list, str, or primitive)
            
        Returns:
            tuple: (redacted_data, redaction_count)
        """
        if not self.enabled:
            return data, 0
        
        redaction_count = 0
        
        if isinstance(data, dict):
            redacted_dict = {}
            for key, value in data.items():
                # Check if key is a sensitive env var
                if key.upper() in self.env_vars_to_redact:
                    redacted_dict[key] = REDACTION_PLACEHOLDER
                    redaction_count += 1
                else:
                    redacted_value, count = self.redact(value)
                    redacted_dict[key] = redacted_value
                    redaction_count += count
            return redacted_dict, redaction_count
        
        elif isinstance(data, list):
            redacted_list = []
            for item in data:
                redacted_item, count = self.redact(item)
                redacted_list.append(redacted_item)
                redaction_count += count
            return redacted_list, redaction_count
        
        elif isinstance(data, str):
            # Check allowlist first
            if data in self.allowlist:
                return data, 0
                
            redacted_str = data
            for pattern, description in self.patterns:
                matches = pattern.findall(redacted_str)
                if matches:
                    redacted_str = pattern.sub(REDACTION_PLACEHOLDER, redacted_str)
                    redaction_count += len(matches) if isinstance(matches, list) else 1
            
            return redacted_str, redaction_count
        
        else:
            # Primitive types (int, float, bool, None)
            return data, 0
    
    def redact_dict_keys(self, data: Dict[str, Any], sensitive_keys: set[str]) -> Tuple[Dict[str, Any], int]:
        """
        Redact specific dictionary keys by name.
        
        Args:
            data: Dictionary to redact
            sensitive_keys: Set of key names to redact (case-insensitive)
            
        Returns:
            tuple: (redacted_dict, redaction_count)
        """
        if not self.enabled:
            return data, 0
        
        redacted_dict = {}
        redaction_count = 0
        sensitive_keys_lower = {k.lower() for k in sensitive_keys}
        
        for key, value in data.items():
            if key.lower() in sensitive_keys_lower:
                redacted_dict[key] = REDACTION_PLACEHOLDER
                redaction_count += 1
            else:
                redacted_dict[key] = value
        
        return redacted_dict, redaction_count


def create_default_config(config_path: Path) -> None:
    """
    Create default configuration file with redaction patterns.
    
    Args:
        config_path: Path where config should be created
    """
    config_content = """# EPI Configuration
# Redaction patterns for automatic secret removal

[redaction]
# Whether redaction is enabled (true by default)
enabled = true

# Additional custom patterns (regex)
# Example:
# [[redaction.patterns]]
# pattern = "my_secret_[a-zA-Z0-9]{20}"
# description = "My custom secret"

# Additional environment variable names to redact
# env_vars = ["MY_SECRET_VAR", "CUSTOM_TOKEN"]

# Allowlist: Strings that should NEVER be redacted (exact match)
# allowlist = ["sk-not-actually-a-key", "my-public-token"]
"""
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_content)


def get_default_redactor() -> Redactor:
    """
    Get a redactor with default configuration.
    
    Attempts to load ~/.epi/config.toml if it exists.
    
    Returns:
        Redactor: Configured redactor instance
    """
    config_path = Path.home() / ".epi" / "config.toml"
    
    # Create default config if it doesn't exist
    if not config_path.exists():
        try:
            create_default_config(config_path)
        except Exception:
            pass  # Fail silently, use defaults
    
    return Redactor(config_path=config_path if config_path.exists() else None)


