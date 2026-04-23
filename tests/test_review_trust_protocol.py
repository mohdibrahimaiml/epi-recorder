import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import typer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_cli.verify import verify_command
from epi_core.case_store import CaseStore
from epi_core.container import EPIContainer
from epi_core.review import (
    ReviewRecord,
    add_review_to_artifact,
    make_review_entry,
    read_review,
    verify_review_trust,
)
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now


def _make_epi(tmp_path: Path, name: str = "case.epi") -> Path:
    source_dir = tmp_path / f"{name}.src"
    source_dir.mkdir()
    (source_dir / "steps.jsonl").write_text(
        '{"index":0,"kind":"agent.decision","content":{"result":"approved"}}\n',
        encoding="utf-8",
    )
    (source_dir / "analysis.json").write_text(
        json.dumps(
            {
                "fault_detected": True,
                "primary_fault": {
                    "step_number": 1,
                    "rule_id": "R001",
                    "fault_type": "POLICY_VIOLATION",
                },
            }
        ),
        encoding="utf-8",
    )
    epi_path = tmp_path / name
    EPIContainer.pack(
        source_dir,
        ManifestModel(
            workflow_id=uuid4(),
            created_at=utc_now(),
            cli_command="pytest",
        ),
        epi_path,
        preserve_generated=True,
        generate_analysis=False,
    )
    return epi_path


def _review_record(reviewer: str = "alice@example.com", notes: str = "Confirmed") -> ReviewRecord:
    return ReviewRecord(
        reviewed_by=reviewer,
        reviews=[
            make_review_entry(
                fault={"step_number": 1, "rule_id": "R001", "fault_type": "POLICY_VIOLATION"},
                outcome="confirmed_fault",
                notes=notes,
                reviewer=reviewer,
            )
        ],
    )


def _signed_review(epi_path: Path, reviewer: str = "alice@example.com") -> ReviewRecord:
    record = _review_record(reviewer=reviewer)
    add_review_to_artifact(epi_path, record, private_key=Ed25519PrivateKey.generate())
    return record


def _replace_members(epi_path: Path, replacements: dict[str, str | bytes]) -> None:
    container_format = EPIContainer.detect_container_format(epi_path)
    temp_dir = EPIContainer._make_temp_dir("test_review_trust_")
    payload_path = temp_dir / "payload.zip"
    next_payload = temp_dir / "next.zip"
    try:
        EPIContainer.extract_inner_payload(epi_path, payload_path)
        with zipfile.ZipFile(payload_path, "r") as src, zipfile.ZipFile(next_payload, "w") as dst:
            for item in src.infolist():
                if item.filename in replacements:
                    continue
                dst.writestr(item, src.read(item.filename))
            for name, value in replacements.items():
                data = value.encode("utf-8") if isinstance(value, str) else value
                dst.writestr(name, data)
        EPIContainer.write_from_payload(next_payload, epi_path, container_format=container_format)
    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


def _copy_review_members(source: Path, dest: Path) -> None:
    replacements: dict[str, bytes] = {}
    for name in EPIContainer.list_members(source):
        if name == "review.json" or name == "review_index.json" or name.startswith("reviews/"):
            replacements[name] = EPIContainer.read_member_bytes(source, name)
    _replace_members(dest, replacements)


def _ledger_member(epi_path: Path) -> str:
    names = [
        name for name in EPIContainer.list_members(epi_path)
        if name.startswith("reviews/") and name.endswith(".json")
    ]
    assert names
    return sorted(names)[-1]


def test_signed_artifact_bound_review_verifies_strict(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)

    latest = read_review(epi_path)
    report = verify_review_trust(epi_path, strict=True)

    assert latest is not None
    assert latest.review_version == "1.1.0"
    assert latest.artifact_binding
    assert latest.review_hash
    assert latest.review_signature
    assert report["status"] == "verified"
    assert report["binding_valid"] is True
    assert report["signature_valid"] is True
    assert report["chain_valid"] is True


def test_verify_review_json_output_includes_review_trust(tmp_path, capsys):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)

    verify_command(
        ctx=MagicMock(),
        epi_file=epi_path,
        json_output=True,
        review=True,
        strict=False,
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["review_trust"]["status"] == "verified"
    assert payload["review_trust"]["review_count"] == 1


def test_copying_review_to_another_artifact_fails_binding(tmp_path):
    reviewed = _make_epi(tmp_path, "reviewed.epi")
    target = _make_epi(tmp_path, "target.epi")
    _signed_review(reviewed)
    _copy_review_members(reviewed, target)

    report = verify_review_trust(target, strict=True)

    assert report["status"] == "failed"
    assert any("artifact binding" in failure for failure in report["failures"])


def test_tampering_review_ledger_fails(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)
    ledger_name = _ledger_member(epi_path)
    payload = EPIContainer.read_member_json(epi_path, ledger_name)
    payload["reviews"][0]["notes"] = "Changed after signature"

    _replace_members(epi_path, {ledger_name: json.dumps(payload)})

    report = verify_review_trust(epi_path, strict=True)
    assert report["status"] == "failed"
    assert any("review_hash" in failure or "signature" in failure for failure in report["failures"])


def test_tampering_review_index_is_ignored(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)

    _replace_members(epi_path, {"review_index.json": '{"not": "trusted"}'})

    report = verify_review_trust(epi_path, strict=True)
    assert report["status"] == "verified"


def test_breaking_previous_review_hash_fails_chain(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path, reviewer="alice@example.com")
    _signed_review(epi_path, reviewer="bob@example.com")
    ledger_name = _ledger_member(epi_path)
    payload = EPIContainer.read_member_json(epi_path, ledger_name)
    payload["previous_review_hash"] = "0" * 64

    _replace_members(epi_path, {ledger_name: json.dumps(payload)})

    report = verify_review_trust(epi_path, strict=True)
    assert report["status"] == "failed"
    assert any("Review chain break" in failure for failure in report["failures"])


def test_review_chain_does_not_trust_self_declared_timestamps(tmp_path):
    epi_path = _make_epi(tmp_path)
    first = _review_record(reviewer="future@example.com")
    first.reviewed_at = "2030-01-01T00:00:00Z"
    second = _review_record(reviewer="past@example.com")
    second.reviewed_at = "2020-01-01T00:00:00Z"

    add_review_to_artifact(epi_path, first, private_key=Ed25519PrivateKey.generate())
    add_review_to_artifact(epi_path, second, private_key=Ed25519PrivateKey.generate())

    report = verify_review_trust(epi_path, strict=True)
    latest = read_review(epi_path)

    assert report["status"] == "verified"
    assert report["chain_valid"] is True
    assert latest is not None
    assert latest.reviewed_by == "past@example.com"


def test_tampering_manifest_protected_evidence_fails_review_binding(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)

    _replace_members(epi_path, {"steps.jsonl": '{"index":0,"kind":"agent.decision","content":{"result":"tampered"}}\n'})

    report = verify_review_trust(epi_path, strict=True)
    assert report["status"] == "failed"
    assert any("artifact binding" in failure for failure in report["failures"])


def test_altering_review_signature_fails(tmp_path):
    epi_path = _make_epi(tmp_path)
    _signed_review(epi_path)
    ledger_name = _ledger_member(epi_path)
    payload = EPIContainer.read_member_json(epi_path, ledger_name)
    replacement_tail = "00" if not payload["review_signature"].endswith("00") else "ff"
    payload["review_signature"] = payload["review_signature"][:-2] + replacement_tail

    _replace_members(epi_path, {ledger_name: json.dumps(payload)})

    report = verify_review_trust(epi_path, strict=True)
    assert report["status"] == "failed"
    assert any("signature" in failure.lower() for failure in report["failures"])


def test_legacy_unbound_review_warns_and_strict_fails(tmp_path):
    epi_path = _make_epi(tmp_path)
    legacy_review = {
        "review_version": "1.0.0",
        "reviewed_by": "legacy@example.com",
        "reviewed_at": "2026-04-01T12:00:00Z",
        "reviews": [{"outcome": "dismissed", "reviewer": "legacy@example.com"}],
    }
    _replace_members(epi_path, {"review.json": json.dumps(legacy_review)})

    relaxed = verify_review_trust(epi_path, strict=False)
    strict = verify_review_trust(epi_path, strict=True)

    assert relaxed["status"] == "warnings"
    assert strict["status"] == "failed"
    assert any("not artifact-bound" in item for item in relaxed["warnings"])


def test_verify_without_review_flag_remains_success_for_legacy_review(tmp_path):
    epi_path = _make_epi(tmp_path)
    _replace_members(
        epi_path,
        {
            "review.json": json.dumps(
                {
                    "review_version": "1.0.0",
                    "reviewed_by": "legacy@example.com",
                    "reviewed_at": "2026-04-01T12:00:00Z",
                    "reviews": [{"outcome": "dismissed", "reviewer": "legacy@example.com"}],
                }
            )
        },
    )

    verify_command(ctx=MagicMock(), epi_file=epi_path)

    with pytest.raises(typer.Exit):
        verify_command(ctx=MagicMock(), epi_file=epi_path, review=True, strict=True)


def test_gateway_export_preserves_case_level_reviews_as_unbound(tmp_path):
    store = CaseStore(tmp_path / "cases.sqlite3")
    case = store.upsert_case_payload(
        {
            "id": "case-1",
            "source_name": "case-1.epi",
            "manifest": {"workflow_name": "Gateway export"},
            "steps": [{"index": 0, "kind": "agent.decision", "content": {"result": "approved"}}],
            "analysis": {"review_required": True},
        }
    )
    review_payload = {
        "review_version": "1.0.0",
        "reviewed_by": "qa@example.com",
        "reviewed_at": "2026-04-01T12:00:00Z",
        "reviews": [{"outcome": "confirmed_fault", "reviewer": "qa@example.com"}],
    }
    store.save_review(case["id"], review_payload, rebuild=False)

    export_path = tmp_path / "exported.epi"
    store.export_case_to_artifact(case["id"], export_path)

    names = set(EPIContainer.list_members(export_path))
    manifest = EPIContainer.read_manifest(export_path)
    relaxed = verify_review_trust(export_path, strict=False)
    strict = verify_review_trust(export_path, strict=True)

    assert "review.json" in names
    assert "review_index.json" in names
    assert any(name.startswith("reviews/") for name in names)
    assert "review.json" not in manifest.file_manifest
    assert "review_index.json" not in manifest.file_manifest
    assert relaxed["status"] == "warnings"
    assert strict["status"] == "failed"

    add_review_to_artifact(
        export_path,
        _review_record(reviewer="qa@example.com", notes="Bound on export"),
        private_key=Ed25519PrivateKey.generate(),
    )
    rebound = verify_review_trust(export_path, strict=True)
    review_index = EPIContainer.read_member_json(export_path, "review_index.json")
    ledger_payloads = [
        EPIContainer.read_member_json(export_path, name)
        for name in EPIContainer.list_members(export_path)
        if name.startswith("reviews/") and name.endswith(".json")
    ]

    assert rebound["status"] == "warnings"
    assert rebound["failures"] == []
    assert any(review["binding_valid"] is True for review in rebound["reviews"])
    assert any(review["artifact_bound"] is False for review in rebound["reviews"])
    assert len(review_index["reviews"]) == 2
    assert any(entry.get("case_level_review") is True for entry in review_index["reviews"])
    assert any(payload.get("case_level_review") is True for payload in ledger_payloads)
