import pytest
import zipfile
import json
from types import SimpleNamespace
from pathlib import Path
from epi_guardrails.session import GuardrailsRecorderSession
from epi_cli.main import app
from typer.testing import CliRunner
import os

runner = CliRunner()

@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Set up a clean environment for each test."""
    keys_dir = tmp_path / "keys"
    registry_dir = tmp_path / "registry"
    keys_dir.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPI_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(registry_dir))
    return {"keys": keys_dir, "registry": registry_dir}

@pytest.fixture
def valid_artifact(tmp_path):
    """Create a valid signed .epi artifact for testing."""
    path = tmp_path / "test.epi"
    session = GuardrailsRecorderSession(
        guard_name="test-guard",
        output_path=path,
        auto_sign=True
    )
    mock_iter = SimpleNamespace(
        outputs=SimpleNamespace(
            llm_response_info=SimpleNamespace(output="raw"),
            parsed_output="parsed",
            validation_response=SimpleNamespace(passed=True),
            guarded_output="parsed"
        )
    )
    with session:
        session.begin_iteration(0, "iter-1")
        session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id="iter-1")
        session.end_iteration(0, "iter-1", mock_iter)
    
    return path

# 1. Cryptographic Integrity
def test_byte_level_tampering_steps(valid_artifact):
    """Modify a single byte in steps.jsonl and expect failure."""
    with zipfile.ZipFile(valid_artifact, "r") as zf:
        zf.extractall(valid_artifact.parent / "extracted")
    
    steps_file = valid_artifact.parent / "extracted" / "steps.jsonl"
    content = steps_file.read_text()
    new_content = content.replace('"status": "pass"', '"status": "fail"')
    steps_file.write_text(new_content)
    
    tampered_epi = valid_artifact.parent / "tampered.epi"
    with zipfile.ZipFile(tampered_epi, "w") as zf:
        for f in (valid_artifact.parent / "extracted").glob("**/*"):
            if f.is_file():
                zf.write(f, f.relative_to(valid_artifact.parent / "extracted"))
    
    result = runner.invoke(app, ["verify", str(tampered_epi), "--strict"])
    assert result.exit_code != 0
    assert "FAILED" in result.stdout or "mismatch" in result.stdout

# 2. Identity & Trust Model
def test_revoked_key(tmp_path, clean_env):
    """Test that a revoked key is flagged as INVALID."""
    from epi_core.keys import KeyManager
    km = KeyManager(clean_env["keys"])
    km.generate_keypair("bad-actor", overwrite=True)
    pub_hex = km.load_public_key("bad-actor").hex()
    
    path = tmp_path / "revoked.epi"
    session = GuardrailsRecorderSession(output_path=path, default_key_name="bad-actor", auto_sign=True)
    mock_iter = SimpleNamespace(
        outputs=SimpleNamespace(
            llm_response_info=SimpleNamespace(output="raw"),
            parsed_output="parsed",
            validation_response=SimpleNamespace(passed=True),
            guarded_output="parsed"
        )
    )
    with session:
        session.begin_iteration(0, "i")
        session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id="i")
        session.end_iteration(0, "i", mock_iter)
        
    (clean_env["registry"] / "bad-actor.revoked").write_text(pub_hex)
    
    result = runner.invoke(app, ["verify", str(path), "--strict"])
    assert result.exit_code != 0
    assert "REVOKED" in result.stdout or "INVALID" in result.stdout

# 3. Completeness & Telemetry
def test_dropped_span_detection(tmp_path):
    """Manually remove a step and expect sequence failure."""
    path = tmp_path / "dropped.epi"
    session = GuardrailsRecorderSession(output_path=path)
    mock_iter = SimpleNamespace(
        outputs=SimpleNamespace(
            llm_response_info=SimpleNamespace(output="raw"),
            parsed_output="parsed",
            validation_response=SimpleNamespace(passed=True),
            guarded_output="parsed"
        )
    )
    with session:
        for i in range(3):
            session.begin_iteration(i, f"i{i}")
            session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id=f"i{i}")
            session.end_iteration(i, f"i{i}", mock_iter)
        
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(tmp_path / "ext")
        
    steps_file = tmp_path / "ext" / "steps.jsonl"
    lines = steps_file.read_text().splitlines()
    del lines[1] # Remove a middle step to create a gap
    steps_file.write_text("\n".join(lines) + "\n")
    
    corrupt_epi = tmp_path / "corrupt.epi"
    with zipfile.ZipFile(corrupt_epi, "w") as zf:
        for f in (tmp_path / "ext").glob("**/*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_path / "ext"))
                
    result = runner.invoke(app, ["verify", str(corrupt_epi), "--strict"])
    assert result.exit_code != 0
    assert "Forensic:     FAIL" in result.stdout
