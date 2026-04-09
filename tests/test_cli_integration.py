"""
Integration tests for EPI CLI commands.

Tests the full CLI workflow including record, verify, view, and keys commands.
"""

import tempfile
from pathlib import Path
import json
import zipfile

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.schemas import ManifestModel
from epi_core.container import EPIContainer


runner = CliRunner()


class TestCLIKeys:
    """Test epi keys command."""
    
    def test_keys_generate(self):
        """Test generating a new keypair."""
        # Keys command uses default ~/.epi/keys/, test with unique name
        import uuid
        unique_name = f"test_key_{uuid.uuid4().hex[:8]}"
        
        result = runner.invoke(app, ["keys", "generate", "--name", unique_name])
        
        assert result.exit_code == 0
        assert "Generated" in result.stdout or "generated" in result.stdout.lower() or "✅" in result.stdout
    
    def test_keys_list(self):
        """Test listing keys."""
        # List command should work even with no keys
        result = runner.invoke(app, ["keys", "list"])
        
        # Should succeed (may have no keys or default key)
        assert result.exit_code == 0
    
    def test_keys_export_default(self):
        """Test exporting default public key."""
        # Export default key (should exist due to auto-generation)
        result = runner.invoke(app, ["keys", "export", "--name", "default"])
        
        # Should succeed or fail gracefully
        assert result.exit_code in [0, 1]  # 0 if exists, 1 if not


class TestCLIVerify:
    """Test epi verify command."""
    
    @pytest.fixture
    def sample_epi_file(self):
        """Create a sample .epi file for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source directory with files
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            (source_dir / "test.txt").write_text("Hello EPI")
            
            # Create .epi file
            output_path = tmpdir_path / "test.epi"
            manifest = ManifestModel(cli_command="test command")
            EPIContainer.pack(source_dir, manifest, output_path)
            
            yield output_path
    
    def test_verify_valid_epi(self, sample_epi_file):
        """Test verifying a valid .epi file."""
        result = runner.invoke(app, ["verify", str(sample_epi_file)])
        
        assert result.exit_code == 0
        # Should show verification results
        assert "integrity" in result.stdout.lower() or "trust" in result.stdout.lower()
    
    def test_verify_with_json_output(self, sample_epi_file):
        """Test verify with JSON output."""
        result = runner.invoke(app, ["verify", "--json", str(sample_epi_file)])

        assert result.exit_code == 0
        # Should be valid JSON
        try:
            output_data = json.loads(result.stdout)
            assert "integrity_ok" in output_data
        except json.JSONDecodeError:
            # If not JSON, at least check it ran
            assert len(result.stdout) > 0

    def test_verify_with_json_output_on_bad_archive(self, tmp_path):
        """Structural failures should still produce machine-readable JSON."""
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")

        result = runner.invoke(app, ["verify", "--json", str(bad)])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["trust_level"] == "NONE"
        assert payload["integrity_ok"] is False
        assert payload["error_type"] == "structural_validation_failed"
        assert "Structural validation failed" in payload["error"]

    def test_verify_with_json_output_on_missing_file(self, tmp_path):
        """Missing files should still return a JSON failure payload."""
        missing = tmp_path / "missing.epi"

        result = runner.invoke(app, ["verify", "--json", str(missing)])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["trust_level"] == "NONE"
        assert payload["error_type"] == "file_not_found"
        assert "File not found" in payload["error"]


class TestCLIView:
    """Test epi view command."""
    
    @pytest.fixture
    def sample_epi_file(self):
        """Create a sample .epi file for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source directory with files
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            (source_dir / "test.txt").write_text("Hello EPI")
            
            # Create .epi file
            output_path = tmpdir_path / "test.epi"
            manifest = ManifestModel(cli_command="test command")
            EPIContainer.pack(source_dir, manifest, output_path)
            
            yield output_path
    
    def test_view_epi_file(self, sample_epi_file, monkeypatch):
        """Test viewing .epi file (mock browser opening)."""
        # Mock webbrowser.open to avoid actually opening browser
        opened_url = []
        
        def mock_open(url):
            opened_url.append(url)
            return True
        
        import epi_cli.view
        monkeypatch.setattr(epi_cli.view, "_open_native_viewer", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(epi_cli.view, "_open_in_browser", mock_open)
        
        result = runner.invoke(app, ["view", str(sample_epi_file)])
        
        assert result.exit_code == 0
        assert len(opened_url) > 0


class TestCLIVersion:
    """Test epi version command."""
    
    def test_version_command(self):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "EPI" in result.stdout or "epi" in result.stdout.lower()


class TestCLIReview:
    """Test epi review command routing."""

    @pytest.fixture
    def analyzed_epi_file(self):
        """Create a minimal .epi with analysis.json for review command tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            (source_dir / "steps.jsonl").write_text('{"index":0,"kind":"session.start","content":{}}\n')
            (source_dir / "analysis.json").write_text(json.dumps({
                "fault_detected": False,
                "primary_fault": None,
                "secondary_flags": [],
                "coverage": {"steps_recorded": 1, "coverage_percentage": 100},
            }))
            output_path = tmpdir_path / "review_test.epi"
            manifest = ManifestModel(cli_command="test review command")
            EPIContainer.pack(source_dir, manifest, output_path)
            yield output_path

    def test_review_interactive_entrypoint_accepts_epi_file(self, analyzed_epi_file):
        """`epi review <file>` should execute callback path, not parser-error on EPI_FILE."""
        result = runner.invoke(
            app,
            ["review", str(analyzed_epi_file), "--reviewer", "cli.tester@epilabs.org"],
        )
        assert result.exit_code == 0
        assert "Missing argument 'EPI_FILE'" not in result.stdout
        assert "Nothing to review" in result.stdout or "No faults detected" in result.stdout

    def test_review_show_still_works(self, analyzed_epi_file):
        result = runner.invoke(app, ["review", str(analyzed_epi_file), "show"])
        assert result.exit_code == 0

    def test_review_blocks_tampered_artifact_before_review(self, analyzed_epi_file):
        tampered_path = analyzed_epi_file.parent / "tampered_review_test.epi"
        with zipfile.ZipFile(analyzed_epi_file, "r") as zin:
            files = {name: zin.read(name) for name in zin.namelist()}
        files["analysis.json"] = json.dumps(
            {
                "fault_detected": True,
                "primary_fault": {
                    "step_number": 1,
                    "fault_type": "POLICY_VIOLATION",
                    "severity": "critical",
                    "plain_english": "Tampered copy",
                },
                "secondary_flags": [],
            }
        ).encode("utf-8")
        with zipfile.ZipFile(tampered_path, "w") as zout:
            for name, data in files.items():
                zout.writestr(name, data)

        result = runner.invoke(
            app,
            ["review", str(tampered_path), "--reviewer", "cli.tester@epilabs.org"],
        )
        assert result.exit_code == 1
        assert "Review stopped" in result.stdout
        assert "trustworthy evidence" in result.stdout

    def test_review_shows_unsigned_trust_summary_for_intact_artifact(self, analyzed_epi_file):
        result = runner.invoke(
            app,
            ["review", str(analyzed_epi_file), "--reviewer", "cli.tester@epilabs.org"],
        )
        assert result.exit_code == 0
        assert "Trust Check" in result.stdout
        assert "Unsigned" in result.stdout


class TestCLIErrors:
    """Test CLI error handling."""
    
    def test_verify_nonexistent_file(self):
        """Test verify with nonexistent file."""
        result = runner.invoke(app, ["verify", "/nonexistent/file.epi"])
        
        assert result.exit_code != 0
    
    def test_view_nonexistent_file(self):
        """Test view with nonexistent file."""
        result = runner.invoke(app, ["view", "/nonexistent/file.epi"])
        
        assert result.exit_code != 0
    
    def test_keys_export_nonexistent(self):
        """Test exporting nonexistent key."""
        import uuid
        nonexistent_name = f"nonexistent_{uuid.uuid4().hex[:8]}"
        
        result = runner.invoke(app, ["keys", "export", "--name", nonexistent_name])
        
        assert result.exit_code != 0



 
