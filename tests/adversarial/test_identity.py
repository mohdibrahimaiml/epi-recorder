import pytest
from pathlib import Path
from types import SimpleNamespace
from epi_core.keys import KeyManager
from epi_core.trust import TrustRegistry
from epi_guardrails.session import GuardrailsRecorderSession
from epi_cli.main import app
from typer.testing import CliRunner
import os
import json

runner = CliRunner()

@pytest.fixture
def registry_setup(tmp_path):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    return registry_dir

def test_revoked_key(tmp_path, registry_setup):
    """Test that a revoked key is flagged as INVALID."""
    km = KeyManager(tmp_path / "keys")
    km.generate_keypair("bad-actor", overwrite=True)
    pub_hex = km.load_public_key("bad-actor").hex()
    
    path = tmp_path / "revoked.epi"
    os.environ["EPI_KEYS_DIR"] = str(tmp_path / "keys")
    
    session = GuardrailsRecorderSession(
        output_path=path,
        default_key_name="bad-actor",
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
        session.begin_iteration(0, "i")
        session.emit_validator_result("v", "pass", iteration_id="i")
        session.end_iteration(0, "i", mock_iter)
        
    revocation_file = registry_setup / "bad-actor.revoked"
    revocation_file.write_text(pub_hex)
    
    os.environ["EPI_TRUSTED_KEYS_DIR"] = str(registry_setup)
    
    result = runner.invoke(app, ["verify", str(path), "--strict", "--json"])
    assert result.exit_code != 0
    report = json.loads(result.stdout)
    assert report.get("trust_level") == "INVALID"

def test_unknown_key(tmp_path):
    """Test that an unknown key is flagged as MEDIUM trust."""
    path = tmp_path / "unknown.epi"
    session = GuardrailsRecorderSession(output_path=path, auto_sign=True)
    
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
        session.emit_validator_result("v", "pass", iteration_id="i")
        session.end_iteration(0, "i", mock_iter)
        
    empty_reg = tmp_path / "empty_reg"
    empty_reg.mkdir()
    os.environ["EPI_TRUSTED_KEYS_DIR"] = str(empty_reg)
    
    result = runner.invoke(app, ["verify", str(path), "--strict", "--json"])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report.get("trust_level") == "MEDIUM"
