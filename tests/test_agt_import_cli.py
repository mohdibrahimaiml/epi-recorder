import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_cli.review import app as review_app
from epi_core.container import EPIContainer

runner = CliRunner()
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agt"


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def _step_count(epi_path: Path) -> int:
    with zipfile.ZipFile(epi_path, "r") as zf:
        return len(
            [line for line in zf.read("steps.jsonl").decode("utf-8").splitlines() if line.strip()]
        )


class TestAGTImportCLI:
    def test_help_renders(self):
        result = runner.invoke(cli_app, ["import", "agt", "--help"])
        assert result.exit_code == 0
        assert "Import external evidence" in result.output or "AGT" in result.output

    def test_successful_import_writes_epi(self, tmp_path):
        output_path = tmp_path / "imported.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(_fixture_path("combined_clean")),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        assert output_path.exists()
        manifest = EPIContainer.read_manifest(output_path)
        integrity_ok, _ = EPIContainer.verify_integrity(output_path)
        assert manifest.signature is None
        assert integrity_ok is True

    def test_invalid_json_exits_nonzero(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app, ["import", "agt", str(bad_json), "--out", str(tmp_path / "bad.epi")]
            )
        assert result.exit_code != 0
        assert "Invalid JSON" in result.output

    def test_missing_file_exits_nonzero(self, tmp_path):
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(tmp_path / "missing.json"),
                    "--out",
                    str(tmp_path / "missing.epi"),
                ],
            )
        assert result.exit_code != 0

    def test_strict_requires_fail_dedupe(self, tmp_path):
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(_fixture_path("combined_clean")),
                    "--out",
                    str(tmp_path / "strict.epi"),
                    "--strict",
                    "--no-sign",
                ],
            )
        assert result.exit_code != 0
        assert "Strict import requires --dedupe fail" in result.output

    def test_analysis_none_warns_and_omits_analysis(self, tmp_path):
        output_path = tmp_path / "analysis_none.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(_fixture_path("combined_clean")),
                    "--out",
                    str(output_path),
                    "--analysis",
                    "none",
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "analysis.json will be omitted" in result.output
        with zipfile.ZipFile(output_path, "r") as zf:
            assert "analysis.json" not in set(zf.namelist())
            assert "artifacts/agt/mapping_report.json" in set(zf.namelist())

    def test_dedupe_keep_both_preserves_both(self, tmp_path):
        output_path = tmp_path / "keep_both.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(_fixture_path("combined_clean")),
                    "--out",
                    str(output_path),
                    "--dedupe",
                    "keep-both",
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        assert _step_count(output_path) == 4

    def test_end_to_end_summary_and_review_flow(self, tmp_path):
        output_path = tmp_path / "imported.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            import_result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(_fixture_path("combined_clean")),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert import_result.exit_code == 0, import_result.output

        summary_result = runner.invoke(
            cli_app, ["export-summary", "summary", str(output_path), "--text"]
        )
        assert summary_result.exit_code == 0
        assert "EPI DECISION RECORD" in summary_result.output
        assert "POLICY COMPLIANCE" in summary_result.output

        review_result = runner.invoke(
            review_app,
            [str(output_path), "--reviewer", "reviewer@example.com"],
            input="c\nImported AGT failure confirmed\n",
        )
        assert review_result.exit_code == 0, review_result.output
        assert "Review saved" in review_result.output

        with zipfile.ZipFile(output_path, "r") as zf:
            review_payload = json.loads(zf.read("review.json").decode("utf-8"))

        assert review_payload["reviews"][0]["outcome"] == "confirmed_fault"
