"""epi demo fast path: record → seal → verify without gateway."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()


@pytest.fixture
def demo_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "epi_home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY_HINTS", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")
    return tmp_path


def test_demo_no_browser_produces_verified_epi(demo_cwd: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert "record · seal · verify · view" in result.output or "Sealed artifact" in result.output
    epi = demo_cwd / "epi-recordings" / "demo_refund.epi"
    assert epi.is_file(), f"missing {epi}; output was:\n{result.output}"
    # Data-only is the default seal: small enough to email. The 80 KB ceiling
    # is the contract; the printed size makes any growth visible.
    size = epi.stat().st_size
    print(f"\n[epi demo data-only] {size} bytes")
    assert size < 80 * 1024, f"data-only demo was {size} bytes"
    assert "integrity=PASS" in result.output or "Offline verify" in result.output
    # intentional demo secret must not leak
    from epi_core.container import EPIContainer

    steps = EPIContainer.read_steps(epi)
    assert "sk-" + ("d" * 40) not in str(steps)


def test_demo_does_not_silently_pin_local_key(demo_cwd: Path):
    """B3: demo may create a key, but it must not add it to the trust store."""
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert "IDENTITY PINNED" not in result.output

    trusted = demo_cwd / "epi_home" / "trusted_keys"
    pinned = sorted(trusted.glob("*.pub")) if trusted.exists() else []
    assert pinned == [], f"epi demo silently pinned: {pinned}"

    epi = demo_cwd / "epi-recordings" / "demo_refund.epi"
    verify = runner.invoke(cli_app, ["verify", str(epi), "--json"])
    assert verify.exit_code in (0, 1), verify.output


def test_demo_help_mentions_review_flag():
    result = runner.invoke(cli_app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "--review" in result.output or "review" in result.output.lower()


def test_demo_push_helper_false_when_not_logged_in(demo_cwd: Path, capsys):
    from epi_cli.dev import _demo_push_if_logged_in

    epi = demo_cwd / "run.epi"
    epi.write_bytes(b"fake")
    assert _demo_push_if_logged_in(epi) is False
    out = capsys.readouterr().out
    assert "not logged in to EPI Cloud" in out


def test_demo_push_helper_true_when_push_succeeds(demo_cwd: Path, monkeypatch, capsys):
    import json

    from epi_cli.dev import _demo_push_if_logged_in

    (demo_cwd / "epi_home" / "cloud.json").write_text(
        json.dumps({"url": "https://cloud.test", "org_id": "org_1", "api_key": "k",
                    "customer": "Acme Bank"}),
        encoding="utf-8",
    )

    class _OkRunner:
        def invoke(self, app, args):
            class R:
                exit_code = 0
                output = "ok"

            return R()

    monkeypatch.setattr("typer.testing.CliRunner", _OkRunner)
    epi = demo_cwd / "run.epi"
    epi.write_bytes(b"fake")
    assert _demo_push_if_logged_in(epi) is True
    out = capsys.readouterr().out
    assert "Pushed to EPI Cloud" in out
    assert "customer: Acme Bank" in out
    assert "Evidence Room" not in out


def test_demo_done_lines_pushed_uses_saved_host(demo_cwd: Path):
    import json

    from epi_cli.dev import _demo_cloud_host, _demo_done_lines
    from pathlib import Path as _Path

    assert _demo_cloud_host() == "cloud.epilabs.org"
    (demo_cwd / "epi_home" / "cloud.json").write_text(
        json.dumps({"url": "https://example.test/"}), encoding="utf-8"
    )
    assert _demo_cloud_host() == "example.test"
    pushed = "\n".join(_demo_done_lines(epi_path=_Path("a.epi"), pushed=True))
    assert "Next: open https://example.test and create a share link for your customer" in pushed
    assert pushed.count("Next:") == 1
    assert "Done." in pushed
    missing = "\n".join(_demo_done_lines(epi_path=_Path("a.epi"), pushed=False, witness="none"))
    assert "Next: run epi cloud login, then epi demo again to share it" in missing
    assert missing.count("Next:") == 1
    assert "share link" not in missing


def test_demo_done_lines_not_witnessed_is_not_a_clean_done(demo_cwd: Path):
    from pathlib import Path as _Path

    from epi_cli.dev import _demo_done_lines

    text = "\n".join(_demo_done_lines(
        epi_path=_Path("a.epi"), pushed=True, witness="failed", witness_fix="run: epi cloud login",
    ))
    assert "Done." not in text
    assert "not witnessed" in text
    assert "Next: run epi cloud login, then epi demo again" in text
    assert "share link" not in text and "flush" not in text


def test_demo_witness_line_from_seal_result(demo_cwd: Path, capsys):
    from epi_cli.dev import _witness_verdict

    assert _witness_verdict({"delivered": ["x"], "failed": [], "cloud_login": True}) == ("ok", None)
    assert "✓ Witnessed by EPI Cloud" in capsys.readouterr().out
    state, fix = _witness_verdict({"delivered": [], "cloud_login": True, "failed": [{
        "reason": "the customer 'Test Bank' was closed in the dashboard",
        "fix": "pick another: epi cloud login", "status": 410}]})
    out = " ".join(capsys.readouterr().out.split())
    assert state == "failed" and fix == "pick another: epi cloud login"
    assert "✗ Not witnessed: the customer 'Test Bank' was closed in the dashboard — pick another: epi cloud login" in out


def test_demo_decision_line_cut_on_word_boundary(tmp_path: Path):
    """The generated script never cuts the decision mid-word ("windo")."""
    import subprocess
    import sys

    from epi_cli.dev import _DEMO_SCRIPT

    body = _DEMO_SCRIPT.split("        short = answer\n", 1)[1].split("        print(", 1)[0]
    probe = tmp_path / "probe.py"
    probe.write_text(
        "answer = 'Approved. Order ORD-9001 qualifies: Gold customer, $900, "
        "12 days since purchase (within 30-day window). Risk: low.'\n"
        "short = answer\n" + "\n".join(l[8:] for l in body.splitlines()) + "\nprint(short)\n",
        encoding="utf-8",
    )
    import os

    # Windows: the child would print "…" in the console code page (cp1252)
    # while we decode UTF-8; pin the child's stdout to UTF-8.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env)
    assert res.returncode == 0, res.stderr
    out = (res.stdout or "").strip()
    assert out.endswith("…"), out
    assert "windo…" not in out and len(out) <= 101
    assert out.startswith("Approved. Order ORD-9001 qualifies")


def test_demo_end_panel_when_not_logged_in(demo_cwd: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert "Next: run epi cloud login, then epi demo again to share it" in result.output
    assert "share link" not in result.output
    assert "[EPI demo]" not in result.output
    assert "x custom" not in result.output


def test_demo_done_lines_closed_customer_next_step(demo_cwd: Path):
    from pathlib import Path as _Path

    from epi_cli.dev import _demo_done_lines

    text = "\n".join(_demo_done_lines(
        epi_path=_Path("a.epi"), pushed=True, witness="failed", witness_fix="pick another: epi cloud login",
    ))
    assert "Next: run epi cloud login and type another customer's name, then epi demo again" in text
