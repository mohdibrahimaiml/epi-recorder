"""Cross-audience invariants for every reporting stage.

The leak that reached review was structural: one function built per-URL
payloads, another posted a single payload to every URL. These tests pin the
contract at the boundary (the outbox entry) and at the preimage mirror, so the
same class of bug fails here first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.audience import derive_audiences
from epi_core.container import EPIContainer
from epi_core.keys import fingerprint_for_private_key
from epi_core.release import document_digest
from epi_core.schemas import ManifestModel, ReleaseModel
from epi_core.trust import sign_manifest
from epi_core.webhook import stage_release_report, stage_seal_report

REPO = Path(__file__).resolve().parents[1]


def _keys(tmp_path: Path, manifest: ManifestModel, audiences, entries) -> Path:
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {}}) + "\n",
        encoding="utf-8",
    )
    key = Ed25519PrivateKey.generate()
    out = tmp_path / "artifact.epi"
    EPIContainer.pack(
        work,
        manifest,
        out,
        signer_function=lambda current: sign_manifest(current, key, "k"),
        seal_fingerprint=fingerprint_for_private_key(key),
        audiences=audiences,
        seal_entries=entries,
        generate_analysis=False,
        embed_viewer=False,
        notarize=False,
    )
    return out


def _release_manifest() -> ManifestModel:
    document = {
        "release_id": "rel_inv",
        "name": "inv",
        "version": "1.0",
        "created_at": "2026-11-09T00:00:00Z",
        "required_approvals": 1,
        "components": [],
        "release_digest": "",
    }
    document["release_digest"] = document_digest(document)
    return ManifestModel(goal="inv", record_kind="release", release=ReleaseModel(**document))


def _assert_entry_is_per_audience(entry: dict, urls: list[str]) -> None:
    pending = list(entry.get("pending") or [])
    payloads = entry.get("payloads") or {}
    headers = entry.get("headers_by_url") or {}
    assert pending == urls
    assert set(payloads) == set(urls), (set(payloads), set(urls))
    if headers:
        assert set(headers) == set(urls)
    for url, payload in payloads.items():
        # Each payload carries exactly the audience that URL reports to.
        assert payload["audience"] == derive_audiences(None, [url])[0]
        assert "nonce" in payload


def test_seal_and_release_entries_are_per_url(tmp_path):
    urls = ["https://bank-a.test/w", "https://bank-b.test/w"]
    audiences = derive_audiences(None, urls)

    entries: dict = {}
    seal = _keys(tmp_path / "seal", ManifestModel(goal="seal"), audiences, entries)
    entry = stage_seal_report(seal, urls=urls, audience_entries=entries, path=tmp_path / "o1.jsonl")
    assert entry is not None
    _assert_entry_is_per_audience(entry, urls)
    assert {p["type"] for p in entry["payloads"].values()} == {"epi.sealed"}

    entries2: dict = {}
    rel = _keys(tmp_path / "rel", _release_manifest(), audiences, entries2)
    rel_entry = stage_release_report(rel, urls=urls, audience_entries=entries2, path=tmp_path / "o2.jsonl")
    assert rel_entry is not None
    _assert_entry_is_per_audience(rel_entry, urls)
    assert {p["type"] for p in rel_entry["payloads"].values()} == {"epi.release"}


def test_delivery_never_posts_one_payload_to_every_url():
    source = (REPO / "epi_core" / "webhook.py").read_text(encoding="utf-8")
    # The URL loop must look up that URL's payload, never the entry default.
    assert "payload_for_url = (entry.get(\"payloads\") or {}).get(url)" in source
    assert "_post_once(\n                url,\n                payload_for_url" in source


def test_preimage_mirrors_drop_every_member_field():
    # Each mirror drops the member-backed fields it is responsible for. A new
    # field must be added here and to the JS at the same time, or this fails.
    expected = {
        "website/js/epi-manifest-preimage.js": {
            "case_id",
            "seal_chains",
            "record_kind",
            "release",
            "release_ref",
            "runtime_components",
        },
        "epi_viewer_static/crypto.js": {"seal_chain", "seal_chains"},
    }
    for name, fields in expected.items():
        path = REPO / name
        text = path.read_text(encoding="utf-8")
        dropped = set(re.findall(r"delete\s+(?:copy|parsed|manifest)\.(\w+)", text))
        for field in fields:
            assert field in dropped, f"{path.name} does not drop {field} from the preimage"
