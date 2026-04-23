import pytest
import zipfile
import json
import hashlib
from pathlib import Path
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_cli.verify import verify_command
from typer.testing import CliRunner
from epi_cli.main import app

runner = CliRunner()

from types import SimpleNamespace

@pytest.fixture
def valid_artifact(tmp_path):
    """Create a valid signed .epi artifact for testing."""
    from epi_guardrails.session import GuardrailsRecorderSession
    
    path = tmp_path / "test.epi"
    session = GuardrailsRecorderSession(
        guard_name="test-guard",
        output_path=path,
        auto_sign=True
    )
    # Mock iteration object
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
        session.end_iteration(0, "iter-1", mock_iter)
    
    return path

def test_byte_level_tampering_steps(valid_artifact):
    """Modify a single byte in steps.jsonl and expect failure."""
    with zipfile.ZipFile(valid_artifact, "r") as zf:
        zf.extractall(valid_artifact.parent / "extracted")
    
    steps_file = valid_artifact.parent / "extracted" / "steps.jsonl"
    content = steps_file.read_text()
    # Change 'pass' to 'fail' or similar
    new_content = content.replace('"status": "pass"', '"status": "fail"')
    steps_file.write_text(new_content)
    
    # Re-pack
    tampered_epi = valid_artifact.parent / "tampered.epi"
    # We need to re-pack manually or use EPIContainer (but that might fix the hashes!)
    # We'll use zipfile directly to simulate an attacker.
    with zipfile.ZipFile(tampered_epi, "w") as zf:
        for f in (valid_artifact.parent / "extracted").glob("**/*"):
            if f.is_file():
                zf.write(f, f.relative_to(valid_artifact.parent / "extracted"))
    
    result = runner.invoke(app, ["verify", str(tampered_epi), "--strict"])
    assert result.exit_code != 0
    assert "FAILED" in result.stdout or "mismatch" in result.stdout

def test_identity_tampering(valid_artifact):
    """Change agent_identity in manifest and expect signature failure."""
    with zipfile.ZipFile(valid_artifact, "r") as zf:
        zf.extractall(valid_artifact.parent / "extracted_id")
    
    manifest_file = valid_artifact.parent / "extracted_id" / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text())
    # Modify identity
    manifest_data["governance"]["agent_identity"]["name"] = "Attacker"
    manifest_file.write_text(json.dumps(manifest_data))
    
    # Re-pack
    tampered_epi = valid_artifact.parent / "tampered_id.epi"
    with zipfile.ZipFile(tampered_epi, "w") as zf:
        for f in (valid_artifact.parent / "extracted_id").glob("**/*"):
            if f.is_file():
                zf.write(f, f.relative_to(valid_artifact.parent / "extracted_id"))
    
    result = runner.invoke(app, ["verify", str(tampered_epi), "--strict"])
    assert result.exit_code != 0
    assert "Invalid signature" in result.stdout

def test_replay_attack_reordering(valid_artifact):
    """Reorder steps in steps.jsonl and expect sequence failure."""
    # Create an artifact with 2 steps
    from epi_guardrails.session import GuardrailsRecorderSession
    path = valid_artifact.parent / "multi_step.epi"
    session = GuardrailsRecorderSession(guard_name="test", output_path=path)
    # Mock iteration object
    mock_iter = SimpleNamespace(
        outputs=SimpleNamespace(
            llm_response_info=SimpleNamespace(output="raw"),
            parsed_output="parsed",
            validation_response=SimpleNamespace(passed=True),
            guarded_output="parsed"
        )
    )
    with session:
        session.begin_iteration(0, "i1")
        session.end_iteration(0, "i1", mock_iter)
        session.begin_iteration(1, "i2")
        session.end_iteration(1, "i2", mock_iter)
        
    # Extract and swap lines
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(path.parent / "swap")
    
    steps_file = path.parent / "swap" / "steps.jsonl"
    lines = steps_file.read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    steps_file.write_text("\n".join(lines) + "\n")
    
    # Re-pack
    swapped_epi = path.parent / "swapped.epi"
    with zipfile.ZipFile(swapped_epi, "w") as zf:
        for f in (path.parent / "swap").glob("**/*"):
            if f.is_file():
                zf.write(f, f.relative_to(path.parent / "swap"))
                
    result = runner.invoke(app, ["verify", str(swapped_epi), "--strict"])
    assert result.exit_code != 0
    # The replay attack changes the steps.jsonl hash, so it triggers integrity failure first.
    assert "Integrity compromised" in result.stdout or "sequence gap" in result.stdout
