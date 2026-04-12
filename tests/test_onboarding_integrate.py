from typer.testing import CliRunner

from epi_cli.main import app


runner = CliRunner()


def test_integrate_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["integrate", "langchain", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert not (tmp_path / ".epi").exists()


def test_integrate_write_examples(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["integrate", "langchain", "--write-examples"])

    assert result.exit_code == 0, result.output
    example = tmp_path / ".epi" / "examples" / "langchain_epi_example.py"
    assert example.exists()
    assert "EPICallbackHandler" in example.read_text(encoding="utf-8")


def test_integrate_pytest_apply_writes_workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()

    result = runner.invoke(app, ["integrate", "pytest", "--apply"])

    assert result.exit_code == 0, result.output
    workflow = tmp_path / ".github" / "workflows" / "epi-audit.yml"
    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "pytest --epi --epi-dir=evidence" in content
    assert "mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main" in content


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
