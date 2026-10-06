"""Optional sign-in: verified identity flows from the approve page into the sealed file."""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient  # noqa: E402

REDIRECT = "https://chat.example/cb"
VERIFIER = "test-verifier-1234567890"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


def _events():
    return [
        {"kind": "user.message", "content": {"text": "Approve the refund"}, "fidelity": "verbatim"},
        {"kind": "assistant.message", "content": {"text": "Approved."}, "fidelity": "verbatim"},
    ]


@pytest.fixture
def idp(monkeypatch, tmp_path):
    from epi_mcp import idp as idp_mod

    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.example")
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_IDP_ISSUER", "https://idp.example")
    monkeypatch.setenv("EPI_IDP_CLIENT_ID", "cid")
    monkeypatch.setenv("EPI_IDP_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("EPI_IDP_NAME", "Example SSO")
    idp_mod._DISCOVERY_CACHE.clear()
    state = {"claims": {"iss": "https://idp.example", "sub": "user-123", "email": "alice@corp.example",
                        "email_verified": True}}

    def fake_get(url):
        assert url.endswith("/.well-known/openid-configuration")
        return {"issuer": "https://idp.example", "authorization_endpoint": "https://idp.example/auth",
                "token_endpoint": "https://idp.example/token", "jwks_uri": "https://idp.example/jwks"}

    def fake_post(url, data):
        assert data["client_secret"] == "csecret" and data["code"] == "idp-code"
        return {"id_token": "fake"}

    def fake_decode(id_token, jwks_uri, issuer, audience, nonce):
        claims = dict(state["claims"])
        if state.get("bad_nonce"):
            raise idp_mod.IdpError("Sign-in could not be confirmed (nonce mismatch). Please start again.")
        return claims

    monkeypatch.setattr(idp_mod, "_http_get_json", fake_get)
    monkeypatch.setattr(idp_mod, "_http_post_form", fake_post)
    monkeypatch.setattr(idp_mod, "_decode_id_token", fake_decode)
    return state


def _client():
    from epi_mcp.http import build_app

    return TestClient(build_app(), raise_server_exceptions=False)


def _register(client):
    return client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()


def _authorize_params(reg):
    return {"client_id": reg["client_id"], "redirect_uri": REDIRECT, "state": "s1",
            "code_challenge": CHALLENGE, "code_challenge_method": "S256"}


def _sign_in(client, reg, include_email=True):
    params = _authorize_params(reg)
    if include_email:
        params["include_email"] = "1"
    start = client.get("/oauth/idp/start", params=params, follow_redirects=False)
    assert start.status_code == 303 and start.headers["location"].startswith("https://idp.example/auth?")
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = client.get("/oauth/idp/callback", params={"code": "idp-code", "state": state}, follow_redirects=False)
    return cb, state


def _token(client, reg, cb):
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(cb.headers["location"]).query)["code"][0]
    return client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "client_id": reg["client_id"],
        "redirect_uri": REDIRECT, "code_verifier": VERIFIER}).json()


def _identity_of(epi_path):
    with zipfile.ZipFile(epi_path) as zf:
        return json.loads(zf.read("environment.json"))["sealer_identity"]


def _seal_with(access_token, tmp_path):
    from epi_mcp.auth import verify_bearer_token
    from epi_mcp.oauth import verify_own_claims
    from epi_mcp.tools import _current_identity, _current_subject, epi_seal_record_tool

    subject = verify_bearer_token(access_token)
    ident = verify_own_claims(access_token)[1]
    t1, t2 = _current_subject.set(subject), _current_identity.set(ident)
    try:
        return subject, epi_seal_record_tool(_events(), goal="identity", output_path=str(tmp_path / "i.epi"))
    finally:
        _current_subject.reset(t1)
        _current_identity.reset(t2)


def test_sign_in_button_only_when_configured(idp, monkeypatch):
    client = _client()
    reg = _register(client)
    page = client.get("/oauth/authorize", params=_authorize_params(reg))
    assert "Sign in with Example SSO" in page.text and "/oauth/idp/start" in page.text
    monkeypatch.delenv("EPI_IDP_ISSUER")
    page2 = client.get("/oauth/authorize", params=_authorize_params(reg))
    assert "Sign in with" not in page2.text and "Approve" in page2.text


def test_verified_identity_reaches_the_sealed_file(idp, tmp_path):
    client = _client()
    reg = _register(client)
    cb, _ = _sign_in(client, reg)
    assert cb.status_code == 303 and cb.headers["location"].startswith(REDIRECT + "?code=")
    tok = _token(client, reg, cb)
    subject, sealed = _seal_with(tok["access_token"], tmp_path)
    assert subject.startswith("oidc-")
    ident = _identity_of(sealed["epi_path"])
    assert ident["verified"] is True and ident["method"] == "oidc"
    assert ident["verified_by"] == "https://idp.example"
    assert ident["email"] == "alice@corp.example"
    assert "does not prove who typed" in ident["statement"]
    assert sealed["seal_check"]["signature_valid"] and sealed["seal_check"]["integrity_ok"]


def test_same_person_keeps_the_same_signer(idp, tmp_path):
    client = _client()
    reg = _register(client)
    keys = []
    for n in range(2):
        cb, _ = _sign_in(client, reg)
        tok = _token(client, reg, cb)
        from epi_mcp.tools import _current_subject, epi_seal_record_tool

        subject = __import__("epi_mcp.auth", fromlist=["x"]).verify_bearer_token(tok["access_token"])
        t = _current_subject.set(subject)
        try:
            r = epi_seal_record_tool(_events(), output_path=str(tmp_path / f"s{n}.epi"))
        finally:
            _current_subject.reset(t)
        with zipfile.ZipFile(r["epi_path"]) as zf:
            keys.append(json.loads(zf.read("manifest.json"))["public_key"])
    assert keys[0] == keys[1]


def test_email_is_opt_in_and_survives_refresh(idp, tmp_path):
    client = _client()
    reg = _register(client)
    cb, _ = _sign_in(client, reg, include_email=False)
    tok = _token(client, reg, cb)
    _, sealed = _seal_with(tok["access_token"], tmp_path)
    ident = _identity_of(sealed["epi_path"])
    assert ident["verified"] is True and "email" not in ident and ident["account_id"]
    refreshed = client.post("/oauth/token", data={"grant_type": "refresh_token",
                                                  "refresh_token": tok["refresh_token"]}).json()
    _, sealed2 = _seal_with(refreshed["access_token"], tmp_path)
    assert _identity_of(sealed2["epi_path"])["verified"] is True


def test_unverified_email_is_never_written(idp, tmp_path):
    idp["claims"]["email_verified"] = False
    client = _client()
    reg = _register(client)
    cb, _ = _sign_in(client, reg)
    _, sealed = _seal_with(_token(client, reg, cb)["access_token"], tmp_path)
    ident = _identity_of(sealed["epi_path"])
    assert "email" not in ident and ident["email_verified"] is False


def test_failed_or_forged_sign_in_approves_nothing(idp):
    client = _client()
    reg = _register(client)
    idp["bad_nonce"] = True
    cb, _ = _sign_in(client, reg)
    assert cb.status_code == 403 and "code=" not in cb.headers.get("location", "")
    forged = client.get("/oauth/idp/callback", params={"code": "idp-code", "state": "not-a-real-state"},
                        follow_redirects=False)
    assert forged.status_code == 403
    cancelled = client.get("/oauth/idp/callback", params={"error": "access_denied", "state": "x"},
                           follow_redirects=False)
    assert cancelled.status_code == 400


def test_anonymous_approval_is_unchanged_and_labelled_pseudonymous(idp, tmp_path):
    client = _client()
    reg = _register(client)
    q = "&".join(f"{k}={v}" for k, v in _authorize_params(reg).items())
    redir = client.post("/oauth/approve?" + q, data={"decision": "approve"}, follow_redirects=False)
    assert redir.status_code == 303
    tok = _token(client, reg, redir)
    subject, sealed = _seal_with(tok["access_token"], tmp_path)
    assert subject.startswith("chatgpt-")
    ident = _identity_of(sealed["epi_path"])
    assert ident["verified"] is False and ident["method"] == "pseudonymous"


def _rsa_token(claims, key):
    import jwt as pyjwt

    return pyjwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def test_real_id_token_validation_rejects_forgeries(monkeypatch):
    import time

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from epi_mcp import idp as idp_mod

    good_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    evil_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _Key:
        key = good_key.public_key()

    monkeypatch.setattr(pyjwt.PyJWKClient, "get_signing_key_from_jwt", lambda self, tok: _Key())
    now = int(time.time())
    base = {"iss": "https://idp.example", "sub": "u1", "aud": "cid", "exp": now + 300, "nonce": "n1"}
    decode = lambda tok, nonce="n1", aud="cid": idp_mod._decode_id_token(  # noqa: E731
        tok, "https://idp.example/jwks", "https://idp.example", aud, nonce)

    assert decode(_rsa_token(base, good_key))["sub"] == "u1"
    for label, bad in {
        "wrong signer": _rsa_token(base, evil_key),
        "wrong audience": _rsa_token({**base, "aud": "someone-else"}, good_key),
        "wrong issuer": _rsa_token({**base, "iss": "https://evil.example"}, good_key),
        "expired": _rsa_token({**base, "exp": now - 10}, good_key),
    }.items():
        with pytest.raises(Exception):
            decode(bad)
        assert label
    with pytest.raises(idp_mod.IdpError):
        decode(_rsa_token(base, good_key), nonce="different")


def test_cli_verify_prints_signed_in_line_only_for_a_verified_file(idp, tmp_path):
    from typer.testing import CliRunner

    from epi_cli.main import app

    client = _client()
    reg = _register(client)
    cb, _ = _sign_in(client, reg)
    _, sealed = _seal_with(_token(client, reg, cb)["access_token"], tmp_path)
    assert sealed["sealer_identity"]["verified"] is True and sealed["sealer_identity"]["who"] == "alice@corp.example"
    out = CliRunner().invoke(app, ["verify", sealed["epi_path"]]).output
    assert "Signed in:" in out and "alice@corp.example" in out



@pytest.fixture
def github(monkeypatch, tmp_path):
    from epi_mcp import idp as idp_mod

    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.example")
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_IDP_ISSUER", "github")
    monkeypatch.setenv("EPI_IDP_CLIENT_ID", "gh-cid")
    monkeypatch.setenv("EPI_IDP_CLIENT_SECRET", "gh-secret")
    monkeypatch.delenv("EPI_IDP_NAME", raising=False)
    calls = {"get": [], "fail": False}

    def fake_post(url, data):
        assert url == idp_mod.GITHUB_TOKEN and data["client_secret"] == "gh-secret"
        return {} if calls["fail"] else {"access_token": "gho_x"}

    def fake_get(url, headers=None):
        calls["get"].append(url)
        assert headers and headers["Authorization"] == "Bearer gho_x"
        if url.endswith("/user"):
            return {"login": "octocat", "id": 583231}
        if url.endswith("/user/emails"):
            return [{"email": "old@x.example", "primary": False, "verified": True},
                    {"email": "octo@corp.example", "primary": True, "verified": True}]
        raise AssertionError(url)

    monkeypatch.setattr(idp_mod, "_http_post_form", fake_post)
    monkeypatch.setattr(idp_mod, "_http_get_json", fake_get)
    return calls


def test_github_sign_in_records_public_username_not_email(github, tmp_path):
    client = _client()
    reg = _register(client)
    page = client.get("/oauth/authorize", params=_authorize_params(reg))
    assert "Sign in with GitHub" in page.text and "public GitHub username" in page.text
    params = _authorize_params(reg)
    start = client.get("/oauth/idp/start", params=params, follow_redirects=False)
    loc = start.headers["location"]
    assert loc.startswith("https://github.com/login/oauth/authorize?") and "scope=read%3Auser&" in loc
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(loc).query)["state"][0]
    cb = client.get("/oauth/idp/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert cb.status_code == 303
    subject, sealed = _seal_with(_token(client, reg, cb)["access_token"], tmp_path)
    assert subject.startswith("gh-")
    ident = _identity_of(sealed["epi_path"])
    assert ident["verified"] is True and ident["username"] == "octocat"
    assert ident["profile_url"] == "https://github.com/octocat" and "email" not in ident
    assert not any(u.endswith("/user/emails") for u in github["get"])
    assert sealed["sealer_identity"]["who"] == "@octocat"
    from typer.testing import CliRunner

    from epi_cli.main import app

    out = CliRunner().invoke(app, ["verify", sealed["epi_path"]]).output
    assert "@octocat" in out and "github.com" in out


def test_github_email_is_opt_in_and_must_be_primary_and_verified(github, tmp_path):
    client = _client()
    reg = _register(client)
    params = {**_authorize_params(reg), "include_email": "1"}
    start = client.get("/oauth/idp/start", params=params, follow_redirects=False)
    assert "scope=read%3Auser+user%3Aemail" in start.headers["location"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = client.get("/oauth/idp/callback", params={"code": "c", "state": state}, follow_redirects=False)
    _, sealed = _seal_with(_token(client, reg, cb)["access_token"], tmp_path)
    assert _identity_of(sealed["epi_path"])["email"] == "octo@corp.example"


def test_github_failed_exchange_approves_nothing(github):
    github["fail"] = True
    client = _client()
    reg = _register(client)
    start = client.get("/oauth/idp/start", params=_authorize_params(reg), follow_redirects=False)
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = client.get("/oauth/idp/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert cb.status_code == 403 and "code=" not in cb.headers.get("location", "")
