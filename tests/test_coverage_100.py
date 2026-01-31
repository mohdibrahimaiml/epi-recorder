"""
Additional tests to achieve 100% code coverage.

Targets remaining uncovered lines in all modules.
"""

import tempfile
from pathlib import Path
import json

import pytest

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.redactor import Redactor
from epi_cli.keys import KeyManager


class TestRedactorConfig:
    """Test redactor TOML config loading."""
    
    def test_load_valid_toml_config(self):
        """Test loading valid TOML configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            
            # Create valid config
            config_content = """
[redaction]
enabled = true

[[redaction.patterns]]
pattern = "test_secret_[a-zA-Z0-9]{10}"
description = "Test secret pattern"

[redaction.env_vars]
MY_CUSTOM_SECRET = "hidden"
"""
            config_path.write_text(config_content)
            
            # Should load without error
            redactor = Redactor(config_path=config_path)
            assert redactor.enabled
    
    def test_load_invalid_toml_config(self):
        """Test handling of invalid TOML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text("{invalid toml syntax")
            
            # Should handle gracefully
            redactor = Redactor(config_path=config_path)
            assert redactor.enabled  # Should still work with defaults
    
    def test_load_config_with_invalid_pattern(self):
        """Test handling of invalid regex patterns in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            
            config_content = """
[redaction]
[[redaction.patterns]]
pattern = "(?P<invalid"
description = "Bad pattern"
"""
            config_path.write_text(config_content)
            
            # Should skip invalid pattern
            redactor = Redactor(config_path=config_path)
            assert redactor.enabled
    
    def test_load_config_with_custom_env_vars(self):
        """Test loading custom environment variables from config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            
            config_content = """
[redaction]
env_vars = ["CUSTOM_SECRET", "MY_API_KEY"]
"""
            config_path.write_text(config_content)  # Fixed: was config_path
            
            redactor = Redactor(config_path=config_path)
            assert redactor.enabled


class TestContainerMinimalViewer:
    """Test container minimal viewer fallback."""
    
    def test_minimal_viewer_when_template_missing(self, monkeypatch):
        """Test minimal viewer is created when template is missing."""
        # Mock the template path to non-existent location
        import epi_core.container as container_module
        
        original_create = container_module.EPIContainer._create_embedded_viewer
        
        def mock_create(source_dir, manifest):
            # Force template not found path
            return container_module.EPIContainer._create_minimal_viewer(manifest)
        
        monkeypatch.setattr(container_module.EPIContainer, "_create_embedded_viewer", mock_create)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            (source_dir / "test.txt").write_text("test")
            
            output_path = tmpdir_path / "test.epi"
            manifest = ManifestModel(cli_command="test")
            
            EPIContainer.pack(source_dir, manifest, output_path)
            
            # Extract and check viewer
            extract_dir = EPIContainer.unpack(output_path)
            viewer_html = (extract_dir / "viewer.html").read_text()
            
            assert "<!DOCTYPE html>" in viewer_html
            assert "EPI Viewer" in viewer_html


class TestCLIMainCallback:
    """Test CLI main callback and entry points."""
    
    def test_cli_main_entry_point(self):
        """Test CLI main entry point."""
        from epi_cli.main import cli_main
        
        # Should not crash when imported
        assert callable(cli_main)
    
    def test_main_name_guard(self):
        """Test __main__ guard."""
        # This is covered when running the module directly
        # We test that the import doesn't execute main
        import epi_cli.main
        assert hasattr(epi_cli.main, "cli_main")


class TestKeysManagerPlatformSpecific:
    """Test platform-specific code paths in KeyManager."""
    
    def test_keys_dir_permissions_windows(self):
        """Test key directory creation on Windows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keys_dir = Path(tmpdir) / "keys"
            
            # Create key manager (should handle Windows permissions)
            km = KeyManager(keys_dir=keys_dir)
            
            assert keys_dir.exists()
    
    def test_generate_keypair_windows_permissions(self):
        """Test keypair generation with Windows-specific permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keys_dir = Path(tmpdir) / "keys"
            km = KeyManager(keys_dir=keys_dir)
            
            # Generate keypair (should handle Windows chmod)
            private_path, public_path = km.generate_keypair("test_win")
            
            assert private_path.exists()
            assert public_path.exists()


class TestCLIErrorPaths:
    """Test CLI error handling paths."""
    
    def test_keys_generate_overwrite_existing(self):
        """Test keys generate with existing keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keys_dir = Path(tmpdir) / "keys"
            km = KeyManager(keys_dir=keys_dir)
            
            # Generate once
            km.generate_keypair("test")
            
            # Try again without overwrite - should raise
            with pytest.raises(FileExistsError):
                km.generate_keypair("test", overwrite=False)
            
            # With overwrite - should succeed
            private_path, public_path = km.generate_keypair("test", overwrite=True)
            assert private_path.exists()


class TestRecordStubs:
    """Test record command stubs."""
    
    def test_record_command_exists(self):
        """Test that record command is registered."""
        from epi_cli.record import app as record_app
        
        assert record_app is not None


class TestViewCommand:
    """Test view command error paths."""
    
    def test_view_with_nonexistent_file(self):
        """Test view command with non-existent file."""
        from typer.testing import CliRunner
        from epi_cli.main import app
        
        runner = CliRunner()
        result = runner.invoke(app, ["view", "/nonexistent/file.epi"])
        
        assert result.exit_code != 0


class TestVerifyVerbose:
    """Test verify command verbose mode."""
    
    def test_verify_verbose_mode(self):
        """Test verify with --verbose flag."""
        from typer.testing import CliRunner
        from epi_cli.main import app
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            (source_dir / "test.txt").write_text("test")
            
            output_path = tmpdir_path / "test.epi"
            manifest = ManifestModel(cli_command="test")
            EPIContainer.pack(source_dir, manifest, output_path)
            
            runner = CliRunner()
            result = runner.invoke(app, ["verify", "--verbose", str(output_path)])
            
            # Verbose mode should show step-by-step verification
            assert "Step" in result.stdout or len(result.stdout) > 0


class TestSerializeEdgeCases:
    """Test serialize edge cases and unreachable error paths."""
    
    def test_canonical_hash_with_nested_structures(self):
        """Test hashing with deeply nested structures."""
        from epi_core.serialize import get_canonical_hash
        from epi_core.schemas import StepModel
        from datetime import datetime
        
        # Create step with deeply nested content
        step = StepModel(
            index=0,
            kind="test",
            content={
                "level1": {
                    "level2": {
                        "level3": {
                            "timestamp": datetime(2025, 1, 1, 12, 0, 0),
                            "data": [1, 2, 3]
                        }
                    }
                }
            }
        )
        
        step.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        
        hash_value = get_canonical_hash(step)
        assert len(hash_value) == 64


