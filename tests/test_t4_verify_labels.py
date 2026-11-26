"""T4 regression tests: weak results must not look stronger than they are.

Each state has two tests:
  - label present when the state applies
  - label absent when the state doesn't apply

States:
  S1 - signer not confirmed (key not pinned / UNKNOWN / LOCAL)
  S2 - SCITT self-issued receipt
  S3 - timestamp present but not validated (CLI "not evaluated" path)
  S4 - contents-only timestamp (older seal format, key not bound)
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.helpers.artifacts import make_decision_epi

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke_verify(artifact: Path, extra_args: list[str] | None = None) -> str:
    """Run epi verify on artifact and return combined output."""
    args = ["verify", str(artifact)] + (extra_args or [])
    result = runner.invoke(cli_app, args)
    return result.output


def _invoke_verify_json(artifact: Path) -> dict:
    result = runner.invoke(cli_app, ["verify", str(artifact), "--json"])
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# S1: Signer not confirmed
# ---------------------------------------------------------------------------

def test_s1_signer_not_confirmed_shown_for_unpinned_key(tmp_path: Path) -> None:
    """An unpinned signed artifact must show the signer-not-confirmed caveat."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    # No keys pinned in tmp_path -> identity will be UNKNOWN / NOT_PINNED
    with patch("epi_core.trust.TrustRegistry.pinned_names", return_value=[]):
        output = _invoke_verify(artifact)
    assert "Signer not confirmed" in output, (
        f"Expected 'Signer not confirmed' in output but got:\n{output}"
    )
    assert "epi keys trust" in output


def test_s1_signer_not_confirmed_absent_for_pinned_key(tmp_path: Path) -> None:
    """A properly pinned key must NOT show the signer-not-confirmed caveat."""
    artifact, key = make_decision_epi(tmp_path, signed=True)
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    pub_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    # Patch the registry to report this key as KNOWN / local_pin
    with patch(
        "epi_core.trust.TrustRegistry.verify_key_trust_with_source",
        return_value=(True, "test-key", "Verified via local trusted registry", "local_pin"),
    ):
        output = _invoke_verify(artifact)
    assert "Signer not confirmed" not in output, (
        f"'Signer not confirmed' must be absent for pinned key but got:\n{output}"
    )


def test_s1_signer_not_confirmed_json_field(tmp_path: Path) -> None:
    """facts.signer_not_confirmed must be True for an unpinned signed artifact."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    with patch("epi_core.trust.TrustRegistry.pinned_names", return_value=[]):
        report = _invoke_verify_json(artifact)
    assert report["facts"]["signer_not_confirmed"] is True


def test_s1_signer_not_confirmed_json_false_for_pinned(tmp_path: Path) -> None:
    """facts.signer_not_confirmed must be False for a pinned key."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    with patch(
        "epi_core.trust.TrustRegistry.verify_key_trust_with_source",
        return_value=(True, "test-key", "Verified via local trusted registry", "local_pin"),
    ):
        report = _invoke_verify_json(artifact)
    assert report["facts"]["signer_not_confirmed"] is False


# ---------------------------------------------------------------------------
# S2: SCITT self-issued receipt
# ---------------------------------------------------------------------------

def _make_scitt_local_artifact(tmp_path: Path) -> Path:
    """Return an artifact whose governance.scitt.service_url == 'local'."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    # Rewrite manifest.json to add governance.scitt.service_url = "local"
    with zipfile.ZipFile(artifact, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    manifest_data = json.loads(members["manifest.json"])
    # governance may be null in the JSON — always replace with our dict
    manifest_data["governance"] = {"scitt": {
        "service_url": "local",
        "entry_id": "test-entry",
    }}
    # Clear the signature so integrity re-signs don't fail (unsigned = no sig check on scitt path)
    manifest_data.pop("signature", None)
    members["manifest.json"] = json.dumps(manifest_data).encode()
    out = tmp_path / "scitt_local.epi"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            ct = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, ct)
    return out


def test_s2_scitt_self_issued_label_shown(tmp_path: Path) -> None:
    """A local SCITT receipt must show the self-issued label."""
    artifact = _make_scitt_local_artifact(tmp_path)
    output = _invoke_verify(artifact)
    assert "self-issued" in output.lower(), (
        f"Expected 'self-issued' in output but got:\n{output}"
    )
    assert "not from an independent" in output.lower() or "independent" in output.lower()


def test_s2_scitt_self_issued_absent_without_local_scitt(tmp_path: Path) -> None:
    """A file with no local SCITT receipt must NOT show the self-issued label."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    output = _invoke_verify(artifact)
    assert "Receipt is self-issued" not in output, (
        f"'Receipt is self-issued' must be absent for a non-SCITT file but got:\n{output}"
    )


def test_s2_scitt_self_issued_json_field(tmp_path: Path) -> None:
    """facts.scitt_self_issued must be True for a local-service artifact."""
    artifact = _make_scitt_local_artifact(tmp_path)
    report = _invoke_verify_json(artifact)
    assert report["facts"]["scitt_self_issued"] is True


def test_s2_scitt_self_issued_json_false_normally(tmp_path: Path) -> None:
    """facts.scitt_self_issued must be False for a normal (no-SCITT) artifact."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    report = _invoke_verify_json(artifact)
    assert report["facts"]["scitt_self_issued"] is False


# ---------------------------------------------------------------------------
# S3: Timestamp present but not validated in CLI "not evaluated" path
# ---------------------------------------------------------------------------

def _make_notarized_artifact(tmp_path: Path) -> Path:
    """Return an artifact that carries a notarization.json (tsa_token_available=True)."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    notar = {
        "tsa_token_available": True,
        "notarized_at": {"provider": "test-tsa", "url": "http://timestamp.example.com"},
        "tsa_genTime": "2026-11-01T00:00:00Z",
    }
    with zipfile.ZipFile(artifact, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    members["artifacts/notarization/notarization.json"] = json.dumps(notar).encode()
    out = tmp_path / "notarized.epi"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            ct = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, ct)
    return out


def test_s3_timestamp_not_checked_label_shown_in_not_evaluated_path(tmp_path: Path) -> None:
    """When _build_timestamps_block raises, the 'Timestamp not checked here' note appears."""
    artifact = _make_notarized_artifact(tmp_path)
    # Force the timestamps block to raise so we hit the "not evaluated" path
    with patch(
        "epi_cli.verify._build_timestamps_block",
        side_effect=Exception("forced skip"),
    ):
        output = _invoke_verify(artifact)
    assert "Timestamp not checked here" in output, (
        f"Expected 'Timestamp not checked here' but got:\n{output}"
    )
    assert "epi verify" in output


def test_s3_timestamp_not_checked_absent_when_no_token(tmp_path: Path) -> None:
    """With no token at all the 'Timestamp not checked here' note must NOT appear."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    # Strip the notarization.json so there is no token to report
    with zipfile.ZipFile(artifact, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()
                   if "notarization" not in name}
    no_ts = tmp_path / "no_ts.epi"
    with zipfile.ZipFile(no_ts, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            ct = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, ct)
    # Force the timestamps block to raise so we hit the "not evaluated" path
    with patch(
        "epi_cli.verify._build_timestamps_block",
        side_effect=Exception("forced skip"),
    ):
        output = _invoke_verify(no_ts)
    assert "Timestamp not checked here" not in output, (
        f"'Timestamp not checked here' must be absent when no token but got:\n{output}"
    )


# ---------------------------------------------------------------------------
# S4: Contents-only timestamp (older seal format, key not bound)
# ---------------------------------------------------------------------------

def _make_contents_only_artifact(tmp_path: Path) -> Path:
    """Return an artifact with a notarization.json that has imprinted_public_key=null."""
    artifact, _key = make_decision_epi(tmp_path, signed=True)
    notar = {
        "tsa_token_available": True,
        "imprint_scheme": "epi-seal-v1",
        "imprinted_public_key": None,   # contents-only: no key binding
        "imprinted_digest": "aabbccdd" * 8,
        "notarized_at": {"provider": "test-tsa", "url": "http://timestamp.example.com"},
        "tsa_tokens": [],
    }
    with zipfile.ZipFile(artifact, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    members["artifacts/notarization/notarization.json"] = json.dumps(notar).encode()
    out = tmp_path / "contents_only.epi"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            ct = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, ct)
    return out


def _make_key_bound_artifact(tmp_path: Path) -> Path:
    """Return an artifact with a notarization.json that has imprinted_public_key set."""
    artifact, key = make_decision_epi(tmp_path, signed=True)
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    pub_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    notar = {
        "tsa_token_available": True,
        "imprint_scheme": "epi-seal-v1",
        "imprinted_public_key": pub_hex,
        "imprinted_digest": "aabbccdd" * 8,
        "notarized_at": {"provider": "test-tsa", "url": "http://timestamp.example.com"},
        "tsa_tokens": [],
    }
    with zipfile.ZipFile(artifact, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    members["artifacts/notarization/notarization.json"] = json.dumps(notar).encode()
    out = tmp_path / "key_bound.epi"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            ct = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, ct)
    return out


def test_s4_contents_only_label_shown(tmp_path: Path) -> None:
    """A validated contents-only timestamp must show the older-seal-format caveat."""
    artifact = _make_contents_only_artifact(tmp_path)
    # Patch _build_timestamps_block to return a contents-only validated block
    fake_block = {
        "seal": [{"status": "valid", "gen_time": "2024-01-01T00:00:00Z",
                  "key_bound": False, "tsa_root": "test-root",
                  "imprinted_key_fingerprint": None}],
        "checkpoints": [],
        "earliest_verified": "2024-01-01T00:00:00Z",
        "key_binding": "contents-only",
        "statement": "contents existed no later than 2024-01-01T00:00:00Z.",
        "clock_warning": None,
    }
    with patch("epi_cli.verify._build_timestamps_block", return_value=fake_block):
        output = _invoke_verify(artifact)
    assert "Older seal format" in output, (
        f"Expected 'Older seal format' in output but got:\n{output}"
    )
    assert "signing key" in output.lower()


def test_s4_contents_only_absent_for_key_bound(tmp_path: Path) -> None:
    """A key-bound timestamp must NOT show the contents-only caveat."""
    artifact = _make_key_bound_artifact(tmp_path)
    fake_block = {
        "seal": [{"status": "valid", "gen_time": "2024-01-01T00:00:00Z",
                  "key_bound": True, "tsa_root": "test-root",
                  "imprinted_key_fingerprint": "aabbccdd"}],
        "checkpoints": [],
        "earliest_verified": "2024-01-01T00:00:00Z",
        "key_binding": "key-bound",
        "statement": "sealed by key aabbccdd no later than 2024-01-01T00:00:00Z.",
        "clock_warning": None,
    }
    with patch("epi_cli.verify._build_timestamps_block", return_value=fake_block):
        output = _invoke_verify(artifact)
    assert "Older seal format" not in output, (
        f"'Older seal format' must be absent for key-bound timestamp but got:\n{output}"
    )


def test_s4_timestamp_key_bound_json_false_for_contents_only(tmp_path: Path) -> None:
    """facts.timestamp_key_bound must be False for a contents-only token."""
    artifact = _make_contents_only_artifact(tmp_path)
    fake_block = {
        "seal": [{"status": "valid", "gen_time": "2024-01-01T00:00:00Z",
                  "key_bound": False, "tsa_root": "test-root",
                  "imprinted_key_fingerprint": None}],
        "checkpoints": [],
        "earliest_verified": "2024-01-01T00:00:00Z",
        "key_binding": "contents-only",
        "statement": "contents existed no later than 2024-01-01T00:00:00Z.",
        "clock_warning": None,
    }
    with patch("epi_cli.verify._build_timestamps_block", return_value=fake_block):
        report = _invoke_verify_json(artifact)
    assert report["facts"]["timestamp_key_bound"] is False


def test_s4_timestamp_key_bound_json_true_for_key_bound(tmp_path: Path) -> None:
    """facts.timestamp_key_bound must be True for a key-bound token."""
    artifact = _make_key_bound_artifact(tmp_path)
    fake_block = {
        "seal": [{"status": "valid", "gen_time": "2024-01-01T00:00:00Z",
                  "key_bound": True, "tsa_root": "test-root",
                  "imprinted_key_fingerprint": "aabbccdd"}],
        "checkpoints": [],
        "earliest_verified": "2024-01-01T00:00:00Z",
        "key_binding": "key-bound",
        "statement": "sealed by key aabbccdd no later than 2024-01-01T00:00:00Z.",
        "clock_warning": None,
    }
    with patch("epi_cli.verify._build_timestamps_block", return_value=fake_block):
        report = _invoke_verify_json(artifact)
    assert report["facts"]["timestamp_key_bound"] is True


# ---------------------------------------------------------------------------
# S2 (failure order): a FAILED local receipt keeps its FAIL line, caveat second
# ---------------------------------------------------------------------------

def test_s2_failed_local_receipt_keeps_clear_fail_line(tmp_path: Path) -> None:
    """A local receipt that fails validation must show FAILED first, then the
    caveat, so the caveat never softens or replaces the failure."""
    artifact = _make_scitt_local_artifact(tmp_path)
    output = _invoke_verify(artifact)
    # The artifact declares a local receipt but carries no statement/receipt
    # members, so SCITT validation fails.
    assert "Transparency: FAILED" in output, (
        f"Expected a clear FAILED transparency line but got:\n{output}"
    )
    assert "Receipt is self-issued (local)" in output
    fail_pos = output.find("Transparency: FAILED")
    caveat_pos = output.find("Receipt is self-issued (local)")
    assert fail_pos < caveat_pos, (
        "The FAILED line must come before the self-issued caveat"
    )


# ---------------------------------------------------------------------------
# Viewer: the four caveat containers exist and are filled with textContent
# ---------------------------------------------------------------------------

VIEWER_HTML = Path(__file__).resolve().parent.parent / "web_viewer" / "index.html"
VIEWER_JS = Path(__file__).resolve().parent.parent / "web_viewer" / "app.js"


@pytest.mark.parametrize(
    "element_id",
    [
        "ind-signer-not-confirmed",
        "ind-signer-not-confirmed-text",
        "diag-ts-note",
        "diag-ts-note-text",
        "diag-ts-contents-only",
        "diag-ts-contents-only-text",
        "diag-scitt-self-issued",
        "diag-scitt-self-issued-text",
    ],
)
def test_viewer_has_caveat_container(element_id: str) -> None:
    html = VIEWER_HTML.read_text(encoding="utf-8")
    assert f'id="{element_id}"' in html, f"viewer index.html is missing #{element_id}"


@pytest.mark.parametrize(
    "expected_text",
    [
        "Signer not confirmed: this key isn",
        "Timestamp not checked here. Run epi verify to validate it.",
        "Older seal format: the timestamp covers the contents, not the signing key.",
        "Receipt is self-issued (local), not from an independent transparency service.",
    ],
)
def test_viewer_caveat_texts_are_present(expected_text: str) -> None:
    js = VIEWER_JS.read_text(encoding="utf-8")
    assert expected_text in js, f"viewer app.js is missing caveat text: {expected_text}"
