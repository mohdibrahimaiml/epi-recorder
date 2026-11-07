"""Signed release records tied to decisions (docs/RELEASES.md)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core import release as release_core

runner = CliRunner()

POLICY = {"policy_version": "1.0", "policy_format_version": "2.0", "policy_id": "credit"}


def _env(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(home / "approver_keys"))
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(home / "trusted_approvers"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    monkeypatch.setenv("EPI_KEY_PASSWORD", "test-password")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "sys.txt").write_text("You are careful.\n", encoding="utf-8")
    (tmp_path / "epi_policy.json").write_text(json.dumps(POLICY), encoding="utf-8")
    return home


def _default_key():
    from epi_core.keys import KeyManager

    km = KeyManager()
    if not km.has_key("default"):
        km.generate_keypair("default")
    return km, km.load_private_key("default")


def _document(
    tmp_path: Path,
    *,
    version: str = "3.2",
    required: int = 1,
    models: list[str] | None = None,
    prompt_path: Path | None = None,
    code_dirty: bool = False,
) -> dict:
    components = release_core.parse_component_specs(["credit=epi_policy.json"], "policy")
    prompt = prompt_path or (tmp_path / "prompts" / "sys.txt")
    components += release_core.parse_component_specs([f"system={prompt}"], "prompt")
    components += release_core.model_components(models or ["anthropic:claude-x"])
    if code_dirty:
        components.append(
            {
                "type": "code",
                "name": "git",
                "identifier": "deadbeef",
                "dirty": True,
            }
        )
    return release_core.build_release_document(
        name="credit-policy",
        version=version,
        required_approvals=required,
        components=components,
    )


def _seal_release(tmp_path: Path, document: dict, name: str = "release.epi") -> Path:
    from epi_core.container import EPIContainer
    from epi_core.schemas import ManifestModel, ReleaseModel
    from epi_core.trust import sign_manifest

    km, private_key = _default_key()
    workspace = tmp_path / f"ws-{name}"
    workspace.mkdir()
    (workspace / "release.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    out = tmp_path / name
    EPIContainer.pack(
        workspace,
        ManifestModel(
            record_kind="release",
            release=ReleaseModel(**document),
            goal=f"release {document['name']} {document['version']}",
        ),
        out,
        signer_function=lambda current: sign_manifest(
            current, private_key, "default"
        ),
        generate_analysis=False,
        embed_viewer=False,
    )
    return out


def _pin_approver(name: str = "alice") -> str:
    from epi_core.approvers import ApproverRegistry
    from epi_core.keys import KeyManager, key_fingerprint

    keys_dir = Path(os.environ["EPI_APPROVER_KEYS_DIR"])
    km = KeyManager(keys_dir=keys_dir)
    if not km.has_key(name):
        km.generate_keypair(name)
    public_hex = km.load_public_key(name).hex()
    ApproverRegistry().add(name, public_hex)
    return key_fingerprint(public_hex, grouped=False)


def _approve(release_path: Path, *, name: str = "alice") -> None:
    _pin_approver(name)
    result = runner.invoke(
        cli_app,
        ["release", "approve", str(release_path), "--as", name, "--yes", "--no-timestamp"],
    )
    assert result.exit_code == 0, result.output


def _decision(
    tmp_path: Path,
    release: Path,
    *,
    models: list[str] | None = None,
    prompt_path: Path | None = None,
    release_strict: bool = False,
    name: str = "decision.epi",
    on_run=None,
) -> Path:
    from epi_recorder import record

    path = tmp_path / name
    prompts = None
    if prompt_path is not None:
        prompts = {"system": str(prompt_path)}
    else:
        prompts = {"system": str(tmp_path / "prompts" / "sys.txt")}
    with record(
        str(path),
        release=str(release),
        prompts=prompts,
        release_strict=release_strict,
        goal="adjudicate claim",
    ) as epi:
        for model in models or ["anthropic:claude-x"]:
            provider, _, served = model.partition(":")
            epi.log_step(
                "llm.request",
                {"model": served or model, "provider": provider or None},
            )
        if on_run:
            on_run()
    return path


def _verify(decision: Path, release: Path | None = None, *extra: str) -> tuple[dict, int]:
    args = ["verify", str(decision), "--json"]
    if release is not None:
        args += ["--release", str(release)]
    result = runner.invoke(cli_app, args + list(extra))
    return json.loads(result.output), result.exit_code


# ---------------------------------------------------------------------------


def test_release_approve_and_decision_matches(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path))
    _approve(release)
    decision = _decision(tmp_path, release)

    report, code = _verify(decision, release)
    assert report["release"]["status"] == "match", report["release"]
    assert report["release"]["approvals"] == {
        "have": 1,
        "required": 1,
        "vendor_required": 1,
        "verifier_minimum": 0,
        "approvers": report["release"]["approvals"]["approvers"],
    }
    assert code == 0

    human = runner.invoke(cli_app, ["verify", str(decision), "--release", str(release)])
    assert "MATCHES" in human.output
    assert "Release:" in human.output


def test_approval_after_the_decision_is_not_matches(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path))
    decision = _decision(tmp_path, release)  # sealed before the approval
    _approve(release)

    report, _code = _verify(decision, release)
    assert report["release"]["status"] == "approved_after_use", report["release"]
    assert report["release"]["approvals_before_decision"] == 0

    strict = runner.invoke(
        cli_app,
        ["verify", str(decision), "--release", str(release), "--require-release"],
    )
    assert strict.exit_code == 1
    assert "APPROVED AFTER USE" in strict.output


def test_second_unpinned_model_is_undeclared(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path, models=["anthropic:claude-x"]))
    _approve(release)
    decision = _decision(
        tmp_path, release, models=["anthropic:claude-x", "openai:gpt-x"]
    )

    report, _code = _verify(decision, release)
    assert report["release"]["status"] == "undeclared", report["release"]
    assert any(
        item["name"] == "openai:gpt-x" for item in report["release"]["undeclared"]
    )

    human = runner.invoke(cli_app, ["verify", str(decision), "--release", str(release)])
    assert "UNDECLARED" in human.output


def test_two_releases_with_the_same_id_are_ambiguous(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    document = _document(tmp_path)
    first = _seal_release(tmp_path, document, name="one.epi")
    second = tmp_path / "two.epi"
    shutil.copyfile(first, second)
    _approve(first)
    decision = _decision(tmp_path, first)

    report, _code = _verify(decision)
    # Without an explicit path the resolver scans the cwd; two copies with the
    # same id are ambiguous, never a silent pick.
    assert report["release"]["status"] == "ambiguous", report["release"]

    result = runner.invoke(
        cli_app,
        [
            "verify",
            str(decision),
            "--json",
            "--release-dir",
            str(tmp_path),
        ],
    )
    parsed = json.loads(result.output)
    assert parsed["release"]["status"] in ("ambiguous", "not_found")
    # The two files share the id, so a directory scan must report ambiguity.
    assert parsed["release"]["status"] == "ambiguous", parsed["release"]

    human = runner.invoke(
        cli_app, ["verify", str(decision), "--release-dir", str(tmp_path)]
    )
    assert "AMBIGUOUS RELEASE" in human.output


def test_required_approvals_is_inside_the_digest(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    two = _document(tmp_path, required=2)
    one = _document(tmp_path, required=1)
    assert two["release_digest"] != one["release_digest"]
    assert two["release_id"] != one["release_id"]

    # A 1-approval artifact cannot satisfy a reference to the 2-approval id.
    release_one = _seal_release(tmp_path, one, name="one.epi")
    _approve(release_one)
    decision = _decision(tmp_path, release_one)
    # Point the decision at the 2-approval id by editing the signed ref is not
    # possible; instead verify against a directory holding only the 1-approval
    # release while the decision references the 2-approval one.
    from epi_core.container import EPIContainer

    manifest = EPIContainer.read_manifest(decision)
    assert manifest.release_ref.release_id == one["release_id"]

    # Build the 2-approval release and ask the verifier to use it explicitly.
    release_two = _seal_release(tmp_path, two, name="two.epi")
    report, _code = _verify(decision, release_two)
    assert report["release"]["status"] == "not_found", report["release"]


def test_verifier_min_approvals_wins(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path, required=1))
    _approve(release)
    decision = _decision(tmp_path, release)

    report, _code = _verify(decision, release, "--min-approvals", "2")
    assert report["release"]["status"] == "unapproved", report["release"]
    assert report["release"]["approvals"]["required"] == 2
    assert report["release"]["approvals"]["have"] == 1


def test_dirty_release_never_matches(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path, code_dirty=True))
    _approve(release)
    decision = _decision(tmp_path, release)

    report, _code = _verify(decision, release)
    assert report["release"]["status"] == "dirty", report["release"]
    assert "uncommitted" in report["release"]["detail"]
    assert _code == 0  # warning by default
    strict, code = _verify(decision, release, "--require-release")
    assert strict["release"]["status"] == "dirty"
    assert code == 1  # one consistent exit-code rule


def test_prompt_change_mid_run_is_drift_not_a_failure(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path))
    _approve(release)

    prompt = tmp_path / "prompts" / "sys.txt"

    def _edit() -> None:
        prompt.write_text("You are a changed prompt.\n", encoding="utf-8")

    decision = _decision(tmp_path, release, on_run=_edit)

    from epi_core.container import EPIContainer

    manifest = EPIContainer.read_manifest(decision)
    prompt_component = next(
        item for item in (manifest.runtime_components or []) if item["type"] == "prompt"
    )
    assert prompt_component["observed"] is True
    assert prompt_component["drift"] is True
    assert prompt_component["sha256_at_start"] != prompt_component["sha256_at_seal"]

    report, _code = _verify(decision, release)
    assert report["release"]["status"] == "drift", report["release"]
    assert "changed during the run" in report["release"]["detail"]

    # Opt-in strictness: only then does the run refuse to seal.
    prompt.write_text("You are careful.\n", encoding="utf-8")
    with pytest.raises(Exception):
        _decision(
            tmp_path,
            release,
            release_strict=True,
            name="strict.epi",
            on_run=_edit,
        )


def test_same_file_at_different_paths_matches(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    release_prompt = tmp_path / "release-prompts" / "v1.txt"
    release_prompt.parent.mkdir()
    release_prompt.write_text("same bytes\n", encoding="utf-8")
    document = _document(tmp_path, prompt_path=release_prompt)
    release = _seal_release(tmp_path, document)
    _approve(release)

    other = tmp_path / "another" / "machine" / "copy.txt"
    other.parent.mkdir(parents=True)
    other.write_text("same bytes\n", encoding="utf-8")
    decision = _decision(tmp_path, release, prompt_path=other)

    report, _code = _verify(decision, release)
    prompt = next(
        item for item in report["release"]["components"] if item["type"] == "prompt"
    )
    assert prompt["status"] == "match", report["release"]


def test_duplicate_logical_names_are_rejected(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate prompt logical name"):
        release_core.parse_component_specs(
            ["system=a.txt", "system=b.txt"], "prompt", base_dir=tmp_path
        )

    result = runner.invoke(
        cli_app,
        [
            "release",
            "create",
            "--name",
            "x",
            "--version",
            "1",
            "--prompt",
            "system=a.txt",
            "--prompt",
            "system=b.txt",
            "--out",
            str(tmp_path / "x.epi"),
        ],
    )
    assert result.exit_code == 2
    assert "duplicate" in result.output


def test_release_approval_cannot_be_replayed_onto_another_version(
    monkeypatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    document_a = _document(tmp_path, version="1.0")
    document_b = _document(tmp_path, version="2.0")
    release_a = _seal_release(tmp_path, document_a, name="a.epi")
    release_b = _seal_release(tmp_path, document_b, name="b.epi")
    _approve(release_a)

    approvals_a = release_core.release_approvals(
        release_a, document_a["release_digest"]
    )
    approvals_b = release_core.release_approvals(
        release_b, document_b["release_digest"]
    )
    assert len(approvals_a) == 1
    assert approvals_b == []  # A's approval names A's digest; B does not count it.


def test_record_resolves_a_release_by_id(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    document = _document(tmp_path)
    release = _seal_release(tmp_path, document)
    _approve(release)

    from epi_recorder import record
    from epi_core.container import EPIContainer

    path = tmp_path / "by-id.epi"
    with record(
        str(path),
        release=document["release_id"],
        release_dir=str(tmp_path),
        prompts={"system": "prompts/sys.txt"},
    ) as epi:
        epi.log_step("llm.request", {"model": "claude-x", "provider": "anthropic"})

    manifest = EPIContainer.read_manifest(path)
    assert manifest.release_ref is not None
    assert manifest.release_ref.release_id == document["release_id"]


def test_approval_witness_time_beats_a_backdated_signed_at(
    monkeypatch, tmp_path: Path
) -> None:
    """An approval's own report dates it; a decision report never does."""
    _env(monkeypatch, tmp_path)
    release = _seal_release(tmp_path, _document(tmp_path))
    decision = _decision(tmp_path, release)  # sealed now

    from cryptography.hazmat.primitives import serialization

    from epi_core.keys import KeyManager, key_fingerprint
    from epi_core.review import (
        ReviewRecord,
        add_review_to_artifact,
        make_release_approval_entry,
    )

    _pin_approver("alice")
    approver_key = KeyManager(
        keys_dir=Path(os.environ["EPI_APPROVER_KEYS_DIR"])
    ).load_private_key("alice")
    approver_hex = approver_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    from epi_core.container import EPIContainer

    document = EPIContainer.read_manifest(release).release.model_dump()
    entry = make_release_approval_entry(
        release_id=document["release_id"],
        release_digest=document["release_digest"],
        decision="approve",
        approver_name="alice",
        key_fingerprint_hex=key_fingerprint(approver_hex, grouped=False),
        signed_at="2020-01-01T00:00:00+00:00",  # backdated on purpose
    )
    record = ReviewRecord(reviewed_by="alice", reviews=[entry])
    add_review_to_artifact(release, record, private_key=approver_key)

    # Without the approval's own witness report, the backdated clock looks
    # early enough and the decision would match.
    before, _code = _verify(decision, release)
    assert before["release"]["status"] == "match", before["release"]

    # The approval was actually received after the decision: that is the time
    # verification must use, never a decision/release report.
    log = tmp_path / "received.jsonl"
    log.write_text(
        json.dumps(
            {
                "schema": "epi-witness/v1",
                "type": "epi.release_approval",
                "release_id": document["release_id"],
                "release_digest": document["release_digest"],
                "approval_hash": record.review_hash,
                "approver": "alice",
                "approver_key_fingerprint": key_fingerprint(
                    approver_hex, grouped=False
                ),
                "signed_at": "2020-01-01T00:00:00+00:00",
                "received_at": "2030-01-01T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report, _code = _verify(decision, release, "--witness-log", str(log))
    assert report["release"]["status"] == "approved_after_use", report["release"]


def test_release_history_lists_versions(monkeypatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    _seal_release(tmp_path, _document(tmp_path, version="1.0"), name="v1.epi")
    second = _seal_release(tmp_path, _document(tmp_path, version="2.0"), name="v2.epi")
    _approve(second)

    result = runner.invoke(cli_app, ["release", "history", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    versions = {row["version"] for row in payload["releases"]}
    assert versions == {"1.0", "2.0"}
    approved = [row for row in payload["releases"] if row["status"] == "approved"]
    assert len(approved) == 1
