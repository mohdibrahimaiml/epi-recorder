"""Free-text and shell-style secrets must be redacted; harmless text must not.

Agent recordings capture shell command lines and tool output verbatim into
signed, shareable files. The quoted-only credential rule missed
``password=hunter2``, ``export DB_PASSWORD=...``, ``curl -u user:pass``,
``--password x``, ``token=...`` and JSON ``secret_key`` forms.
"""

from __future__ import annotations

import pytest

from epi_core.redactor import Redactor

SECRET = "hunter2hunter2"
SECRET2 = "abcd1234efgh5678abcd"


@pytest.fixture()
def red():
    return Redactor()


@pytest.mark.parametrize(
    "text",
    [
        f"password={SECRET}",
        f"password: {SECRET}",
        f"passwd={SECRET}",
        f"PASSWORD={SECRET}",
        f"export DB_PASSWORD={SECRET}",
        f"curl -u admin:{SECRET} https://example.test",
        f"curl --user admin:{SECRET} https://example.test",
        f"--password {SECRET}",
        f"--password={SECRET}",
        f"my password is {SECRET}",
        f"secret={SECRET2}",
        f"client_secret={SECRET2}",
        f"secret_access_key={SECRET2}",
        f'{{"secret_key":"{SECRET2}"}}',
        f"token={SECRET2}",
        f"--token={SECRET2}",
        f"X-API-Key: {SECRET2}",
        f"password_hash={SECRET2}",
    ],
)
def test_secret_forms_are_redacted(red, text):
    out, n = red.redact({"text": text})
    assert n >= 1
    assert SECRET not in out["text"] and SECRET2 not in out["text"]


def test_the_key_stays_visible_so_a_reader_sees_what_was_redacted(red):
    out, _ = red.redact({"text": f"export DB_PASSWORD={SECRET}"})
    assert out["text"].startswith("export DB_PASSWORD=***REDACTED***")


@pytest.mark.parametrize(
    "text",
    [
        "max_tokens=4096",
        "token_count: 12",
        "tokenizer=gpt2-large-model-v2",
        "the password is required",
        "passwordless: true",
        "secret_santa: yes",
        "password_policy: strong",
        "password_min_length: 12",
        "secrets_manager: aws",
        "PWD=/home/user/project",
        "docker run -u 1000:1000 image",
        "page=2&sort=asc",
        "The token budget is large",
        "keyboard=us-intl-layout",
        "API key rotation is monthly",
    ],
)
def test_harmless_text_is_left_alone(red, text):
    out, n = red.redact({"text": text})
    assert out["text"] == text and n == 0


def test_redaction_is_idempotent(red):
    once, n1 = red.redact({"text": f"password={SECRET}"})
    twice, n2 = red.redact(once)
    assert n1 == 1 and n2 == 0 and once == twice


@pytest.mark.parametrize("description_word", ["secret", "password", "token", "credential"])
def test_patterns_never_re_match_inside_a_redaction_receipt(red, description_word):
    """A receipt like ***REDACTED***:Declared secret:HMAC-SHA256:... must not be
    redacted (or counted) again by the free-text credential rules."""
    receipt = f"***REDACTED***:Declared {description_word}:HMAC-SHA256:" + "ab12" * 16 + "***"
    out, n = red.redact({"text": f"token is {receipt} ok"})
    assert n == 0 and out["text"] == f"token is {receipt} ok"
