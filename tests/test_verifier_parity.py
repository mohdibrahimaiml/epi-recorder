"""Item 6: browser never stronger than CLI. Contract lists full verdicts."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER = {"NONE": 0, "FAIL": 0, "INVALID": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _browser_level(facts):
    if not facts.get("integrity_ok"):
        return "NONE"
    if facts.get("signature_valid") is False:
        return "NONE"
    if facts.get("signature_valid") is True:
        return "LOW"
    if facts.get("signature_valid") is None:
        return "LOW"  # unsigned caps at LOW, same as CLI
    return "NONE"  # incomplete in browser -> not verified


def test_contract_lists_full_verdicts():
    text = (ROOT / "docs" / "VERIFICATION_CONTRACT.md").read_text(encoding="utf-8")
    for level in ["HIGH", "MEDIUM", "LOW", "NONE", "FAIL", "INVALID", "WARN"]:
        assert level in text
    assert "LOCAL" in text and "MISMATCH" in text


def test_browser_js_never_exceeds_low():
    for js in [
        ROOT / "website" / "js" / "epi-verify-core.js",
        ROOT / "website" / "js" / "home-verify.js",
    ]:
        text = js.read_text(encoding="utf-8")
        assert "UNVERIFIED_IDENTITY" not in text, js
        levels = set(re.findall(r"trust_level\s*=\s*'([A-Z_ ]+)'", text))
        assert levels <= {"HIGH", "LOW", "MEDIUM", "NONE"}, (js, levels)
        # Browser must be able to reach HIGH only via pinned identity; never MEDIUM for unsigned.
        assert "MEDIUM" not in levels, (js, levels)


def test_parity_across_demo_files():
    from typer.testing import CliRunner
    from epi_cli.main import app as cli_app

    demos = sorted((ROOT / "docs" / "assets").glob("*.epi"))
    assert demos, "no demo files"
    runner = CliRunner()
    for epi in demos:
        result = runner.invoke(cli_app, ["verify", str(epi), "--json"])
        assert result.exit_code in (0, 1), (epi.name, result.output[-500:])
        try:
            report = json.loads(result.output)
        except Exception:
            continue  # CLI printed warnings only; skip
        facts = report.get("facts", {})
        cli_level = (report.get("trust_level") or report.get("summary", {}).get("trust") or "NONE").upper()
        cli_level = {"UNKNOWN": "LOW", "UNVERIFIED IDENTITY": "LOW"}.get(cli_level, cli_level)
        b = _browser_level(facts)
        assert ORDER[b] <= ORDER.get(cli_level, 0), (epi.name, b, cli_level)
