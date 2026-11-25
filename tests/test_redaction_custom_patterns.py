"""T5: user-supplied redaction patterns (config file and env var).

Built-in patterns must always stay on. Custom patterns are additive only.
Redaction is best-effort and pattern-based: these tests prove the plumbing,
not that every secret format is caught.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from epi_core.redactor import (
    REDACT_PATTERNS_ENV_VAR,
    Redactor,
    load_custom_patterns_from_env,
)


@pytest.fixture(autouse=True)
def _fixed_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read or write ~/.epi/.redaction_secret during tests."""
    monkeypatch.setenv("EPI_REDACTION_SECRET", "test-only-redaction-secret")
    monkeypatch.delenv(REDACT_PATTERNS_ENV_VAR, raising=False)


def _redact(value: str, **kwargs) -> tuple[str, int]:
    redactor = Redactor(**kwargs)
    return redactor.redact(value)


# ---------------------------------------------------------------------------
# Built-ins always stay on
# ---------------------------------------------------------------------------

def test_builtin_pattern_redacts_with_no_config() -> None:
    out, count = _redact("key=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert count == 1
    assert "HMAC-SHA256" in out
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out


def test_builtin_pattern_still_redacts_when_custom_pattern_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, '["acme_[a-z]{12}"]')
    out, count = _redact(
        "custom=acme_abcdefghijkl and key=sk-abcdefghijklmnopqrstuvwxyz123456"
    )
    assert count == 2
    assert "acme_abcdefghijkl" not in out
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out


# ---------------------------------------------------------------------------
# Config file (existing style: ~/.epi/config.toml)
# ---------------------------------------------------------------------------

def test_config_file_custom_pattern_redacts(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[redaction]\n"
        "[[redaction.patterns]]\n"
        'pattern = "acme_[a-z]{12}"\n'
        'description = "Acme key"\n',
        encoding="utf-8",
    )
    out, count = _redact("token acme_abcdefghijkl here", config_path=config)
    assert count == 1
    assert "Acme key" in out
    assert "acme_abcdefghijkl" not in out


def test_config_file_does_not_remove_builtins(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[redaction]\nenabled = true\n", encoding="utf-8")
    out, _ = _redact("key=sk-abcdefghijklmnopqrstuvwxyz123456", config_path=config)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out


# ---------------------------------------------------------------------------
# Env var (matches the existing EPI_REDACT_SECRETS style)
# ---------------------------------------------------------------------------

def test_env_pattern_list_of_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, '["acme_[a-z]{12}"]')
    out, count = _redact("token acme_abcdefghijkl here")
    assert count == 1
    assert "acme_abcdefghijkl" not in out


def test_env_pattern_object_carries_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        REDACT_PATTERNS_ENV_VAR,
        '[{"pattern": "acme_[a-z]{12}", "description": "Acme key"}]',
    )
    out, count = _redact("token acme_abcdefghijkl here")
    assert count == 1
    assert "Acme key" in out


def test_env_bare_single_pattern_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, "acme_[a-z]{12}")
    out, count = _redact("token acme_abcdefghijkl here")
    assert count == 1
    assert "acme_abcdefghijkl" not in out


def test_env_invalid_regex_is_skipped_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, '["(unclosed"]')
    with pytest.warns(UserWarning, match="invalid"):
        patterns = load_custom_patterns_from_env()
    assert patterns == []
    # Built-ins still work after the bad entry is skipped.
    out, _ = _redact("key=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out


def test_env_malformed_json_warns_and_loads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, "[not json")
    with pytest.warns(UserWarning, match="does not"):
        assert load_custom_patterns_from_env() == []


def test_env_empty_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, "   ")
    assert load_custom_patterns_from_env() == []


def test_env_patterns_are_applied_inside_nested_structures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REDACT_PATTERNS_ENV_VAR, '["acme_[a-z]{12}"]')
    redactor = Redactor()
    payload = {"messages": [{"content": "token acme_abcdefghijkl"}]}
    out, count = redactor.redact(payload)
    assert count == 1
    assert "acme_abcdefghijkl" not in str(out)
    assert "HMAC-SHA256" in out["messages"][0]["content"]
