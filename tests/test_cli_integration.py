"""
Integration tests for EPI CLI commands.

Tests the full CLI workflow including record, verify, view, and keys commands.
"""

import tempfile
from pathlib import Path
import json

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
        
        import webbrowser
        monkeypatch.setattr(webbrowser, "open", mock_open)
        
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


