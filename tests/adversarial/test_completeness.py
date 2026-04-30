import pytest
import zipfile
import json
from types import SimpleNamespace
from pathlib import Path
from epi_guardrails.session import GuardrailsRecorderSession
from epi_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

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
        session.begin_iteration(0, "i1")
        session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id="i1")
        session.end_iteration(0, "i1", mock_iter)
        session.begin_iteration(1, "i2")
        session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id="i2")
        session.end_iteration(1, "i2", mock_iter)
        session.begin_iteration(2, "i3")
        session.emit_validator_result("v", "pass", corrected=False, rail_alias="test", iteration_id="i3")
        session.end_iteration(2, "i3", mock_iter)
        
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(tmp_path / "ext")
        
    steps_file = tmp_path / "ext" / "steps.jsonl"
    lines = steps_file.read_text().splitlines()
    del lines[1] # Remove a middle step to create a gap
    steps_file.write_text("\n".join(lines) + "\n")
    
    corrupt_epi = tmp_path / "corrupt.epi"
    with zipfile.ZipFile(corrupt_epi, "w") as zf:
        # Forensic requirement: mimetype MUST be first
        mimetype_file = tmp_path / "ext" / "mimetype"
        if mimetype_file.exists():
            zf.write(mimetype_file, "mimetype")
            
        for f in (tmp_path / "ext").glob("**/*"):
            if f.is_file() and f.name != "mimetype":
                zf.write(f, f.relative_to(tmp_path / "ext"))
                
    result = runner.invoke(app, ["verify", str(corrupt_epi), "--strict", "--json"])
    assert result.exit_code != 0
    report = json.loads(result.stdout)
    assert report["facts"]["sequence_ok"] is False
    # Under STRICT policy, if integrity fails, reason is 'Integrity compromised'
    # but sequence_ok fact MUST still be False.

def test_empty_iteration_attack(tmp_path):
    """Create an iteration with no validators and expect semantic failure."""
    path = tmp_path / "empty_iter.epi"
    session = GuardrailsRecorderSession(output_path=path)
    with session:
        # Note: _emit_step wraps payload in 'content'
        session._emit_step("agent.step", {
            "type": "agent.step",
            "subtype": "guardrails",
            "event_index": 1,
            "timestamp_ns": 1000,
            "iteration_index": 0,
            "iteration_id": "none",
            "validators": [],  # EMPTY
            "completed": True
        })
        
    result = runner.invoke(app, ["verify", str(path), "--strict", "--json"])
    assert result.exit_code != 0
    report = json.loads(result.stdout)
    assert report["facts"]["completeness_ok"] is False
    # Identity failure might take precedence in Reason, so we check the fact
