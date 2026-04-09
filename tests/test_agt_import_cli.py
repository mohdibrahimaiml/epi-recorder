from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_cli.review import app as review_app
from epi_core.container import EPIContainer

runner = CliRunner()
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agt"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_BUNDLE = REPO_ROOT / "examples" / "agt-epi-demo" / "sample_annex_bundle.json"
EXAMPLE_EVIDENCE_DIR = REPO_ROOT / "examples" / "agt" / "evidence-dir"
EXAMPLE_MANIFEST = REPO_ROOT / "examples" / "agt" / "manifest-input" / "agt_import_manifest.json"


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def _step_count(epi_path: Path) -> int:
    return EPIContainer.count_steps(epi_path)


def _assert_expected_agt_members(epi_path: Path) -> None:
    names = set(EPIContainer.list_members(epi_path))
    assert "steps.jsonl" in names
    assert "policy.json" in names
    assert "policy_evaluation.json" in names
    assert "analysis.json" in names
    assert "artifacts/annex_iv.md" in names
    assert "artifacts/annex_iv.json" in names
    assert "artifacts/agt/mapping_report.json" in names
    assert "artifacts/agt/bundle.json" in names


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

    def test_invalid_json_shape_exits_with_supported_shape_guidance(self, tmp_path):
        weird_json = tmp_path / "weird.json"
        weird_json.write_text('{"hello":"world"}', encoding="utf-8")
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                ["import", "agt", str(weird_json), "--out", str(tmp_path / "weird.epi"), "--no-sign"],
            )
        assert result.exit_code != 0
        assert "neutral AGT bundle" in result.output
        assert "top-level" in result.output
        assert "'files'" in result.output
        assert "mapping" in result.output
        assert "Supported AGT inputs" in result.output

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
        assert "Supported AGT inputs" in result.output

    def test_empty_directory_exits_with_directory_guidance(self, tmp_path):
        empty_dir = tmp_path / "empty-dir"
        empty_dir.mkdir()
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(empty_dir),
                    "--out",
                    str(tmp_path / "empty.epi"),
                    "--no-sign",
                ],
            )
        assert result.exit_code != 0
        assert "No recognized AGT files were found in directory" in result.output
        assert "audit_logs.json" in result.output
        assert "agt_import_manifest.json" in result.output

    def test_single_section_file_exits_with_pass_directory_guidance(self, tmp_path):
        single_section = tmp_path / "audit_logs.json"
        single_section.write_text('[{"entry_id":"one","timestamp":"2026-04-06T10:00:00Z"}]', encoding="utf-8")

        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(single_section),
                    "--out",
                    str(tmp_path / "single.epi"),
                    "--no-sign",
                ],
            )

        assert result.exit_code != 0
        assert "single AGT section file" in result.output
        assert "Pass the directory" in result.output

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
        names = set(EPIContainer.list_members(output_path))
        assert "analysis.json" not in names
        assert "artifacts/agt/mapping_report.json" in names

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

    def test_directory_import_writes_epi(self, tmp_path):
        output_path = tmp_path / "directory.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(EXAMPLE_EVIDENCE_DIR),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        _assert_expected_agt_members(output_path)

    def test_manifest_import_writes_epi(self, tmp_path):
        output_path = tmp_path / "manifest.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(EXAMPLE_MANIFEST),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        _assert_expected_agt_members(output_path)

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

        review_payload = EPIContainer.read_member_json(output_path, "review.json")

        assert review_payload["reviews"][0]["outcome"] == "confirmed_fault"

    def test_demo_bundle_round_trip_contains_expected_artifact_members(self, tmp_path):
        output_path = tmp_path / "demo_case.epi"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(DEMO_BUNDLE),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "epi verify" in result.output
        assert "epi view --extract review" in result.output
        assert "epi view" in result.output
        _assert_expected_agt_members(output_path)

    def test_demo_bundle_extract_review_creates_viewer_html(self, tmp_path):
        output_path = tmp_path / "demo_case.epi"
        review_dir = tmp_path / "review"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            import_result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(DEMO_BUNDLE),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert import_result.exit_code == 0, import_result.output

        view_result = runner.invoke(
            cli_app,
            ["view", "--extract", str(review_dir), str(output_path)],
        )
        assert view_result.exit_code == 0, view_result.output
        assert (review_dir / "viewer.html").exists()
        assert (review_dir / "artifacts" / "agt" / "mapping_report.json").exists()

    def test_directory_import_extract_review_creates_viewer_html(self, tmp_path):
        output_path = tmp_path / "directory_case.epi"
        review_dir = tmp_path / "directory_review"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            import_result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(EXAMPLE_EVIDENCE_DIR),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert import_result.exit_code == 0, import_result.output

        view_result = runner.invoke(
            cli_app,
            ["view", "--extract", str(review_dir), str(output_path)],
        )
        assert view_result.exit_code == 0, view_result.output
        assert (review_dir / "viewer.html").exists()
        assert (review_dir / "artifacts" / "annex_iv.json").exists()

    def test_manifest_import_extract_review_creates_viewer_html(self, tmp_path):
        output_path = tmp_path / "manifest_case.epi"
        review_dir = tmp_path / "manifest_review"
        with patch("epi_cli.keys.generate_default_keypair_if_missing", return_value=False):
            import_result = runner.invoke(
                cli_app,
                [
                    "import",
                    "agt",
                    str(EXAMPLE_MANIFEST),
                    "--out",
                    str(output_path),
                    "--no-sign",
                ],
            )
        assert import_result.exit_code == 0, import_result.output

        view_result = runner.invoke(
            cli_app,
            ["view", "--extract", str(review_dir), str(output_path)],
        )
        assert view_result.exit_code == 0, view_result.output
        assert (review_dir / "viewer.html").exists()
        assert (review_dir / "artifacts" / "agt" / "mapping_report.json").exists()
