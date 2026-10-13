"""WP-SEC-6: epi share uploads really expire, and anonymous uploads are capped.

The privacy page promises 7 days by default (max 30), then deletion. Today
nothing deletes the files and nothing checks expires_at on read, and the
endpoint takes unlimited anonymous 5 MB uploads.

Rules pinned here:
  1. POST /api/share defaults to 7 days; expires_days=31 is rejected (422).
  2. Any read (download or meta) past expires_at returns 410 Gone with
     "This link has expired", even if the purger has not run yet.
  3. purge_expired_shares() deletes the .epi and .json of expired shares.
  4. Anonymous uploads are capped at 10/hour per IP (11th -> 429).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shared_cases").mkdir(exist_ok=True)
    import verify_portal.main as portal_main

    portal_main._share_upload_hits.clear()
    from verify_portal.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_default_expiry_is_seven_days(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    res = client.post("/api/share", content=b"PK\x03\x04fake-epi-bytes")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["expires_in_days"] == 7, body
    meta = json.loads((tmp_path / "shared_cases" / f"{body['share_id']}.json").read_text())
    created = datetime.fromisoformat(meta["created_at"])
    expires = datetime.fromisoformat(meta["expires_at"])
    assert timedelta(days=6, hours=23) < expires - created < timedelta(days=7, hours=1)


def test_thirty_one_days_rejected(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    res = client.post("/api/share?expires_days=31", content=b"PK\x03\x04x")
    assert res.status_code == 422, res.text
    res = client.post("/api/share?expires_days=30", content=b"PK\x03\x04x")
    assert res.status_code == 200, res.text
    assert res.json()["expires_in_days"] == 30


def _plant_expired_share(tmp_path: Path, share_id: str = "expiredcase01") -> None:
    d = tmp_path / "shared_cases"
    (d / f"{share_id}.epi").write_bytes(b"PK\x03\x04old-bytes")
    (d / f"{share_id}.json").write_text(
        json.dumps(
            {
                "share_id": share_id,
                "filename": "old.epi",
                "size": 12,
                "created_at": (datetime.now(timezone.utc) - timedelta(days=9)).isoformat(),
                "expires_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "downloads": 0,
            }
        )
    )


def test_expired_reads_are_gone(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _plant_expired_share(tmp_path)
    dl = client.get("/api/share/expiredcase01")
    assert dl.status_code == 410, dl.status_code
    assert "expired" in dl.json()["detail"].lower(), dl.text
    meta = client.get("/api/share/expiredcase01/meta")
    assert meta.status_code == 410, meta.status_code


def test_purge_deletes_expired_files(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _plant_expired_share(tmp_path, "gone00000001")

    import verify_portal.main as portal_main

    # Direct purge removes the planted files but keeps fresh ones.
    fresh = client.post("/api/share", content=b"PK\x03\x04fresh").json()["share_id"]
    # The upload already purged the first planted share (purge runs first).
    assert not (tmp_path / "shared_cases" / "gone00000001.epi").exists()
    assert not (tmp_path / "shared_cases" / "gone00000001.json").exists()
    _plant_expired_share(tmp_path, "gone00000002")
    removed = portal_main.purge_expired_shares(tmp_path / "shared_cases")
    assert "gone00000002" in removed
    assert not (tmp_path / "shared_cases" / "gone00000002.epi").exists()
    assert not (tmp_path / "shared_cases" / "gone00000002.json").exists()
    assert (tmp_path / "shared_cases" / f"{fresh}.epi").exists()
    assert (tmp_path / "shared_cases" / f"{fresh}.json").exists()


def test_anonymous_uploads_capped_per_hour(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    codes = [
        client.post("/api/share", content=b"PK\x03\x04x").status_code for _ in range(11)
    ]
    assert codes[:10] == [200] * 10, codes
    assert codes[10] == 429, codes


def test_cli_default_matches_server() -> None:
    from typer.testing import CliRunner

    from epi_cli.main import app as cli_app

    res = CliRunner().invoke(cli_app, ["share", "--help"])
    assert res.exit_code == 0, res.output
    import re

    flat = re.sub(r"[│\s]+", " ", res.output)
    assert "[default: 7]" in flat, res.output
    assert "max 30" in flat, res.output
