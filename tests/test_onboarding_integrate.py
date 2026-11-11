from typer.testing import CliRunner

from epi_cli.main import app


runner = CliRunner()


def test_init_github_action_does_not_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    workflow = tmp_path / ".github" / "workflows" / "epi-audit.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing", encoding="utf-8")

    from epi_cli.main import init
    from unittest.mock import MagicMock, patch

    (tmp_path / "epi-recordings").mkdir()
    (tmp_path / "epi-recordings" / "epi_demo.epi").write_text("demo", encoding="utf-8")
    with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("epi_cli.main._count_steps_in_artifact", return_value=3):
        init(demo_filename="epi_demo.py", no_open=True, framework="generic", github_action=True)

    assert workflow.read_text(encoding="utf-8") == "existing"
