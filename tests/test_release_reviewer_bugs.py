"""Reviewer bugs found on the 4.10.0 candidate.

* A browser download duplicate ("name (1).epi") is byte-identical; it must not
  make the release AMBIGUOUS.
* A valid approval from an unpinned key is not "UNAPPROVED RELEASE".
* Auto-discovery searches the decision file's own folder, non-recursively.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from epi_core.approvers import ApproverRegistry
from epi_core.container import EPIContainer
from epi_core.keys import KeyManager, fingerprint_for_private_key
from epi_core.release import (
    check_decision_release,
    document_digest,
    resolve_release,
)
from epi_core.schemas import ManifestModel, ReleaseModel, ReleaseRefModel
from epi_core.trust import sign_manifest

REPO = Path(__file__).resolve().parents[1]


def _key(tmp_path: Path):
    km = KeyManager(keys_dir=tmp_path / "keys")
    km.generate_keypair("default")
    return km.load_private_key("default")


def _release(
    tmp_path: Path,
    key,
    *,
    release_id: str = "rel_dup",
    component: str = "a",
    filename: str = "claims-policy-1.4.epi",
) -> tuple[Path, dict]:
    document = {
        "release_id": release_id,
        "name": "claims-policy",
        "version": "1.4",
        "created_at": "2026-11-09T00:00:00Z",
        "required_approvals": 1,
        "components": [
            {"type": "policy", "name": component, "sha256": "a" * 64}
        ],
        "release_digest": "",
    }
    document["release_digest"] = document_digest(document)
    work = tmp_path / f"release-work-{component}"
    work.mkdir()
    (work / "release.json").write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / filename
    EPIContainer.pack(
        work,
        ManifestModel(
            goal="release compat",
            record_kind="release",
            release=ReleaseModel(**document),
        ),
        out,
        signer_function=lambda current: sign_manifest(current, key, "default"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
    )
    return out, document


def _decision(tmp_path: Path, key, release_doc: dict, filename: str = "decision.epi") -> Path:
    work = tmp_path / "decision-work"
    work.mkdir()
    (work / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "custom.test", "content": {"n": 1}}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / filename
    EPIContainer.pack(
        work,
        ManifestModel(
            goal="decision",
            release_ref=ReleaseRefModel(
                release_id=str(release_doc["release_id"]),
                release_digest=str(release_doc["release_digest"]),
            ),
        ),
        out,
        signer_function=lambda current: sign_manifest(current, key, "default"),
        container_format="legacy-zip",
        generate_analysis=False,
        embed_viewer=False,
        seal_fingerprint=fingerprint_for_private_key(key),
    )
    return out


def test_identical_release_copies_are_one(tmp_path: Path) -> None:
    key = _key(tmp_path)
    release, document = _release(tmp_path, key)
    shutil.copyfile(release, tmp_path / "claims-policy-1.4 (1).epi")

    resolved = resolve_release(
        {
            "release_id": document["release_id"],
            "release_digest": document["release_digest"],
        },
        release_dir=tmp_path,
    )
    assert resolved["status"] == "found", resolved
    assert resolved["duplicates_skipped"] == 1, resolved
    assert Path(resolved["path"]).name in {release.name, "claims-policy-1.4 (1).epi"}


def test_same_id_different_content_is_ambiguous(tmp_path: Path) -> None:
    key = _key(tmp_path)
    _release(tmp_path, key, component="a", filename="release-a.epi")
    _release(tmp_path, key, component="b", filename="release-b.epi")

    resolved = resolve_release(
        {"release_id": "rel_dup", "release_digest": ""},
        release_dir=tmp_path,
    )
    assert resolved["status"] == "ambiguous", resolved
    assert len(resolved["paths"]) == 2, resolved


def test_auto_discovery_is_next_to_the_decision_and_not_recursive(tmp_path: Path) -> None:
    key = _key(tmp_path)
    decision_dir = tmp_path / "decision-folder"
    decision_dir.mkdir()
    release, document = _release(decision_dir, key)
    nested = decision_dir / "nested"
    nested.mkdir()
    shutil.copyfile(release, nested / release.name)
    decision = _decision(decision_dir, key, document)

    resolved = resolve_release(
        {
            "release_id": document["release_id"],
            "release_digest": document["release_digest"],
        },
        decision_path=decision,
    )
    assert resolved["status"] == "found", resolved
    assert resolved["discovery"] == "next_to_decision", resolved
    assert resolved["recursive"] is False, resolved
    assert Path(resolved["search_dir"]) == decision_dir
    # The nested copy is not scanned, so it is not even counted as a duplicate.
    assert resolved["duplicates_skipped"] == 0, resolved


def test_release_with_valid_but_unpinned_approval_is_not_unapproved(
    tmp_path: Path, monkeypatch
) -> None:
    """The demo release has a valid DEMO KEY approval; with no pin it is not a failure."""
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "approvers"))
    decision = REPO / "website" / "assets" / "demo" / "decision-example.epi"
    release = REPO / "website" / "assets" / "demo" / "claims-policy-1.4.epi"
    manifest = EPIContainer.read_manifest(decision)
    registry = ApproverRegistry(approvers_dir=tmp_path / "approvers")

    report = check_decision_release(
        decision_manifest=manifest,
        release_path=release,
        decision_path=decision,
        registry=registry,
    )
    assert report["status"] == "approver_not_pinned", report
    assert report["approvals"]["have"] == 0, report["approvals"]
    assert report["approvals"]["valid"] >= 1, report["approvals"]
    assert "APPROVER NOT PINNED" in report["detail"]
    assert "epi approvers add" in report["detail"]
