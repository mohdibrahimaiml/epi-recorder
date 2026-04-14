"""
pytest-epi: Pytest plugin for automatic EPI recording.

Automatically generates .epi evidence files for test functions
that make LLM calls. Turns EPI into test verification infrastructure.

Installation:
    pip install epi-recorder  (plugin auto-registers via entry point)

Usage:
    # Enable via command line flag
    pytest --epi

    # Or enable via pytest.ini / pyproject.toml
    [tool.pytest.ini_options]
    epi = true

    # Configure output directory
    pytest --epi --epi-dir ./test-evidence

    # Keep artifacts for passing tests too
    pytest --epi --epi-on-pass

    # Only record tests matching a pattern
    pytest --epi -k "test_agent"

How it works:
    When --epi is enabled, each test function runs inside an
    EPI recording session. If the test makes any LLM calls
    (via wrapped clients or patched libraries), they are
    automatically captured in a .epi file named after the test.

    Test results (pass/fail/skip) are logged as the final step.
    By default, artifacts are kept for failing tests. Use
    --epi-on-pass to keep successful test artifacts too.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


def pytest_addoption(parser):
    """Register pytest command-line options."""
    group = parser.getgroup("epi", "EPI Recorder evidence generation")
    group.addoption(
        "--epi",
        action="store_true",
        default=False,
        help="Enable EPI recording for each test",
    )
    group.addoption(
        "--epi-dir",
        action="store",
        default="./test-evidence",
        help="Directory for .epi output files (default: ./test-evidence)",
    )
    group.addoption(
        "--epi-sign",
        action="store_true",
        default=True,
        help="Sign .epi files with default key (default: True)",
    )
    group.addoption(
        "--epi-no-sign",
        action="store_true",
        default=False,
        help="Disable signing of .epi files",
    )
    group.addoption(
        "--epi-on-pass",
        action="store_true",
        default=False,
        help="Keep .epi files for passing tests too (default: keep failures only)",
    )


def pytest_configure(config):
    """Register the EPI marker."""
    config.addinivalue_line(
        "markers",
        "epi: Mark test for EPI recording (automatic when --epi is used)",
    )

    # Also support pyproject.toml config
    try:
        ini_epi = config.getini("epi")
    except (ValueError, KeyError):
        ini_epi = False
    if ini_epi or config.getoption("--epi", default=False):
        config._epi_enabled = True
    else:
        config._epi_enabled = False


def pytest_collection_modifyitems(config, items):
    """Apply EPI marker to all tests when --epi flag is active."""
    if not getattr(config, "_epi_enabled", False):
        return

    epi_marker = pytest.mark.epi
    for item in items:
        if "epi" not in item.keywords:
            item.add_marker(epi_marker)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Start EPI recording session before test runs."""
    if not getattr(item.config, "_epi_enabled", False):
        return

    # Only record tests with the epi marker
    if "epi" not in item.keywords:
        return

    try:
        from epi_recorder.api import EpiRecorderSession

        # Build output path from test name
        epi_dir = Path(item.config.getoption("--epi-dir"))
        epi_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize test name for filename
        test_name = item.nodeid.replace("::", "_").replace("/", "_").replace("\\", "_")
        test_name = test_name.replace("[", "_").replace("]", "").replace(" ", "_")
        if not test_name.endswith(".epi"):
            test_name += ".epi"

        output_path = epi_dir / test_name

        # Determine signing preference
        auto_sign = not item.config.getoption("--epi-no-sign", default=False)

        # Create and enter session
        session = EpiRecorderSession(
            output_path=str(output_path),
            workflow_name=f"pytest:{item.nodeid}",
            tags=["pytest", "test"],
            auto_sign=auto_sign,
            goal=f"Test execution: {item.nodeid}",
        )

        session.__enter__()

        # Log test metadata
        session.log_step("test.start", {
            "test_id": item.nodeid,
            "test_name": item.name,
            "test_file": str(item.fspath) if hasattr(item, "fspath") else None,
            "markers": [str(m) for m in item.iter_markers()],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Store session on the item for later cleanup
        item._epi_session = session
        item._epi_start_time = time.time()
        item._epi_output_path = output_path

    except Exception as e:
        # Don't let EPI failures break the test suite
        import warnings
        warnings.warn(f"EPI recording setup failed: {e}", RuntimeWarning)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """Finalize EPI recording after test completes."""
    session = getattr(item, "_epi_session", None)
    if session is None:
        return

    try:
        start_time = getattr(item, "_epi_start_time", None)
        duration = time.time() - start_time if start_time else None

        # Get test outcome from the report
        report = getattr(item, "_epi_report", None)
        outcome = "unknown"
        if report:
            if report.passed:
                outcome = "passed"
            elif report.failed:
                outcome = "failed"
            elif report.skipped:
                outcome = "skipped"

        # Log test result
        result_data = {
            "test_id": item.nodeid,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if duration is not None:
            result_data["duration_seconds"] = round(duration, 3)

        # Log failure details if available
        if report and report.failed and hasattr(report, "longreprtext"):
            result_data["error"] = report.longreprtext[:2000]  # Truncate

        session.log_step("test.result", result_data)
        session.__exit__(None, None, None)

        keep_on_pass = item.config.getoption("--epi-on-pass", default=False)
        output_path = getattr(item, "_epi_output_path", None)
        keep_artifact = outcome == "failed" or keep_on_pass
        if output_path and not keep_artifact:
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

    except Exception as e:
        import warnings
        warnings.warn(f"EPI recording teardown failed: {e}", RuntimeWarning)
        try:
            session.__exit__(None, None, None)
        except Exception:
            pass



@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test result and store on item for teardown access."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item._epi_report = report


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print EPI summary at the end of the test run."""
    if not getattr(config, "_epi_enabled", False):
        return

    epi_dir = config.getoption("--epi-dir")
    epi_files = list(Path(epi_dir).glob("*.epi")) if Path(epi_dir).exists() else []

    if epi_files:
        terminalreporter.section("EPI Evidence")
        terminalreporter.write_line(
            f"Generated {len(epi_files)} .epi evidence file(s) in {epi_dir}/"
        )
        for f in sorted(epi_files)[-5:]:  # Show last 5
            terminalreporter.write_line(f"  {f.name}")
        if len(epi_files) > 5:
            terminalreporter.write_line(f"  ... and {len(epi_files) - 5} more")
