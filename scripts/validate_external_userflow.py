from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_PYTHON = Path(sys.executable).resolve()
AGT_BUNDLE_INPUT = REPO_ROOT / "examples" / "agt-epi-demo" / "sample_annex_bundle.json"
AGT_DIRECTORY_INPUT = REPO_ROOT / "examples" / "agt" / "evidence-dir"
AGT_MANIFEST_INPUT = REPO_ROOT / "examples" / "agt" / "manifest-input" / "agt_import_manifest.json"
CHECKLIST_PATH = REPO_ROOT / "scripts" / "validate_external_userflow_checklist.md"

_API_KEY_ENV_VARS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LANGCHAIN_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
}


class HarnessFailure(RuntimeError):
    """Raised when a validation scenario fails."""


@dataclass
class CommandRecord:
    label: str
    argv: list[str]
    cwd: str
    returncode: int
    duration_seconds: float
    stdout_path: str
    stderr_path: str


@dataclass
class ScenarioResult:
    install_mode: str
    scenario_name: str
    status: str = "FAIL"
    commands: list[CommandRecord] = field(default_factory=list)
    verify_report: dict[str, Any] | None = None
    artifact_path: str | None = None
    extracted_review_path: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class InstallRecord:
    install_mode: str
    status: str = "FAIL"
    python_executable: str | None = None
    epi_executable: str | None = None
    python_version: str | None = None
    epi_version: str | None = None
    package_location: str | None = None
    clean_home: str | None = None
    wheel_path: str | None = None
    wheel_audit_status: str | None = None
    commands: list[CommandRecord] = field(default_factory=list)
    error: str | None = None


@dataclass
class InstallContext:
    install_mode: str
    env_dir: Path
    home_dir: Path
    work_dir: Path
    report_dir: Path
    artifact_dir: Path
    extract_dir: Path
    helper_dir: Path
    python_executable: Path
    epi_executable: Path
    base_env: dict[str, str]
    install_record: InstallRecord


def _slug(value: str) -> str:
    parts = []
    for char in value.lower():
        parts.append(char if char.isalnum() else "-")
    return "-".join(filter(None, "".join(parts).split("-")))


def _venv_python(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )


def _venv_epi(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if os.name == "nt" else "bin") / (
        "epi.exe" if os.name == "nt" else "epi"
    )


def _discover_shared_pip_cache() -> str | None:
    explicit = os.environ.get("PIP_CACHE_DIR")
    if explicit:
        return explicit

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return str(Path(local_app_data) / "pip" / "Cache")

    fallback = Path.home() / ".cache" / "pip"
    if fallback.exists():
        return str(fallback)
    return None


def _pick_runtime_temp_dir(install_mode: str, preferred: Path) -> Path:
    candidates = [
        preferred,
        Path(tempfile.gettempdir()) / "epi_external_userflow" / install_mode,
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".epi_tmp_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue
    raise HarnessFailure(f"Could not find a writable temp directory for {install_mode}.")


def _base_env(clean_home: Path, temp_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in _API_KEY_ENV_VARS | {"PYTHONPATH", "PYTHONHOME"}:
        env.pop(key, None)

    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    env["HOME"] = str(clean_home)
    env["USERPROFILE"] = str(clean_home)
    env["APPDATA"] = str(clean_home / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(clean_home / "AppData" / "Local")
    env["TMP"] = str(temp_dir)
    env["TEMP"] = str(temp_dir)

    shared_cache = _discover_shared_pip_cache()
    if shared_cache:
        env["PIP_CACHE_DIR"] = shared_cache

    return env


def _write_python_temp_shim(shim_dir: Path, safe_temp_dir: Path) -> None:
    """Keep clean-room venv/pip temp files inside a known writable directory."""
    shim_dir.mkdir(parents=True, exist_ok=True)
    safe_temp_dir.mkdir(parents=True, exist_ok=True)
    shim = f"""
import os
import pathlib
import shutil
import tempfile
import uuid

_SAFE_BASE = pathlib.Path(r"{safe_temp_dir}")
_SAFE_BASE.mkdir(parents=True, exist_ok=True)

def _manual_mkdtemp(suffix=None, prefix=None, dir=None):
    base = pathlib.Path(dir) if dir else _SAFE_BASE
    base.mkdir(parents=True, exist_ok=True)
    name = f"{{prefix or 'tmp'}}{{uuid.uuid4().hex}}{{suffix or ''}}"
    path = base / name
    path.mkdir(parents=True, exist_ok=False)
    return str(path)

class _ManualTemporaryDirectory:
    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors=False):
        self.name = _manual_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        self._ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self):
        return self.name

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def cleanup(self):
        shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)

tempfile.mkdtemp = _manual_mkdtemp
tempfile.TemporaryDirectory = _ManualTemporaryDirectory
tempfile.tempdir = str(_SAFE_BASE)
os.environ["TMP"] = str(_SAFE_BASE)
os.environ["TEMP"] = str(_SAFE_BASE)
"""
    (shim_dir / "sitecustomize.py").write_text(textwrap.dedent(shim).strip() + "\n", encoding="utf-8")


def _write_helper(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def _run_command(
    *,
    log_dir: Path,
    label: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    input_text: str | None = None,
    timeout_seconds: int = 600,
) -> CommandRecord:
    log_dir.mkdir(parents=True, exist_ok=True)
    base_name = _slug(label)
    start = time.time()
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        encoding="utf-8",
        errors="replace",
    )
    duration = round(time.time() - start, 3)

    stdout_path = log_dir / f"{base_name}.stdout.txt"
    stderr_path = log_dir / f"{base_name}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    return CommandRecord(
        label=label,
        argv=[str(arg) for arg in argv],
        cwd=str(cwd),
        returncode=completed.returncode,
        duration_seconds=duration,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _load_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessFailure(message)


def _parse_json_stdout(record: CommandRecord) -> Any:
    stdout = _load_text(record.stdout_path).strip()
    if not stdout:
        raise HarnessFailure(f"{record.label} did not produce JSON output.")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HarnessFailure(f"{record.label} produced invalid JSON: {exc}") from exc


def _new_scenario(ctx: InstallContext, name: str) -> ScenarioResult:
    return ScenarioResult(install_mode=ctx.install_mode, scenario_name=name)


def _write_shared_helpers(helper_dir: Path) -> dict[str, Path]:
    helper_dir.mkdir(parents=True, exist_ok=True)

    return {
        "record_workflow": _write_helper(
            helper_dir / "record_workflow.py",
            """
            import json
            import sys
            from pathlib import Path

            output_file = Path(sys.argv[1])
            payload = {"stage": "local-record", "status": "ok", "value": 42}
            print(json.dumps(payload))
            output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            """,
        ),
        "api_capture": _write_helper(
            helper_dir / "api_capture.py",
            """
            import sys
            from pathlib import Path

            from epi_recorder import record

            output_path = Path(sys.argv[1])
            with record(str(output_path), workflow_name="Harness API Capture", goal="API capture smoke") as epi:
                epi.log_step("tool.call", {"tool": "lookup_order", "input": {"order_id": "A-100"}})
                epi.log_step("tool.response", {"tool": "lookup_order", "status": "success", "output": {"amount": 125}})
                epi.log_step("agent.decision", {"decision": "approve_refund", "confidence": 0.82})
            print(output_path)
            """,
        ),
        "inspect_artifact": _write_helper(
            helper_dir / "inspect_artifact.py",
            """
            import json
            import sys
            from pathlib import Path

            from epi_core.container import EPIContainer

            artifact = Path(sys.argv[1])
            manifest = EPIContainer.read_manifest(artifact)
            payload = {
                "members": sorted(EPIContainer.list_members(artifact)),
                "has_signature": bool(manifest.signature),
                "has_public_key": bool(manifest.public_key),
                "container_format": EPIContainer.detect_container_format(artifact),
            }
            print(json.dumps(payload, indent=2))
            """,
        ),
        "mutate_artifact": _write_helper(
            helper_dir / "mutate_artifact.py",
            """
            import json
            import shutil
            import sys
            import tempfile
            import zipfile
            from pathlib import Path

            from epi_core.container import EPIContainer


            def rewrite_payload(source: Path, destination: Path, updates: dict[str, bytes]) -> None:
                container_format = EPIContainer.detect_container_format(source)
                temp_root = Path(tempfile.mkdtemp(prefix="epi_harness_mutate_"))
                payload_zip = temp_root / "payload.zip"
                mutated_zip = temp_root / "mutated.zip"
                temp_artifact = temp_root / destination.name
                try:
                    EPIContainer.extract_inner_payload(source, payload_zip)
                    with zipfile.ZipFile(payload_zip, "r") as zin, zipfile.ZipFile(mutated_zip, "w") as zout:
                        for item in zin.infolist():
                            data = updates.get(item.filename)
                            if data is None:
                                data = zin.read(item.filename)
                            zout.writestr(item, data)
                    EPIContainer.write_from_payload(mutated_zip, temp_artifact, container_format=container_format)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(temp_artifact, destination)
                finally:
                    shutil.rmtree(temp_root, ignore_errors=True)


            def mutate_signature(signature: str) -> str:
                replacement = "0" if not signature.endswith("0") else "1"
                return signature[:-1] + replacement


            def pick_tamper_target(source: Path) -> str:
                preferred = [
                    "steps.jsonl",
                    "stdout.log",
                    "stderr.log",
                    "environment.json",
                    "analysis.json",
                    "policy.json",
                    "policy_evaluation.json",
                ]
                members = set(EPIContainer.list_members(source))
                for name in preferred:
                    if name in members:
                        return name
                for name in sorted(members):
                    if name not in {"manifest.json", "mimetype"}:
                        return name
                raise RuntimeError("No mutable payload member found for tamper test.")


            def tamper_bytes(data: bytes) -> bytes:
                if not data:
                    return b"tampered"
                first = bytes([(data[0] + 1) % 256])
                return first + data[1:]


            mode = sys.argv[1]
            source = Path(sys.argv[2])
            destination = Path(sys.argv[3])

            if mode == "bad-archive":
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"not a valid .epi artifact")
                raise SystemExit(0)

            manifest = EPIContainer.read_member_json(source, "manifest.json")

            if mode == "tamper":
                target = pick_tamper_target(source)
                rewrite_payload(
                    source,
                    destination,
                    {target: tamper_bytes(EPIContainer.read_member_bytes(source, target))},
                )
                raise SystemExit(0)

            if mode == "invalid-signature":
                if not manifest.get("signature"):
                    raise RuntimeError("Source artifact has no signature to invalidate.")
                manifest["signature"] = mutate_signature(str(manifest["signature"]))
                rewrite_payload(
                    source,
                    destination,
                    {"manifest.json": json.dumps(manifest, indent=2).encode("utf-8")},
                )
                raise SystemExit(0)

            if mode == "missing-public-key":
                if not manifest.get("signature"):
                    raise RuntimeError("Source artifact has no signature to test missing public key.")
                manifest["public_key"] = None
                rewrite_payload(
                    source,
                    destination,
                    {"manifest.json": json.dumps(manifest, indent=2).encode("utf-8")},
                )
                raise SystemExit(0)

            raise RuntimeError(f"Unknown mutation mode: {mode}")
            """,
        ),
    }


def _inspect_artifact(ctx: InstallContext, artifact_path: Path, scenario_log_dir: Path) -> dict[str, Any]:
    inspect_helper = ctx.helper_dir / "inspect_artifact.py"
    record = _run_command(
        log_dir=scenario_log_dir,
        label=f"Inspect {artifact_path.name}",
        argv=[str(ctx.python_executable), "-I", str(inspect_helper), str(artifact_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=120,
    )
    if record.returncode != 0:
        stdout = _load_text(record.stdout_path)
        stderr = _load_text(record.stderr_path)
        raise HarnessFailure(
            f"Artifact inspection failed for {artifact_path.name}: {stdout or stderr}"
        )
    return _parse_json_stdout(record)


def _verify_artifact(
    ctx: InstallContext,
    scenario: ScenarioResult,
    artifact_path: Path,
    *,
    expect_exit: int,
    expected_trust_level: str | None = None,
    expect_signature_valid: bool | None = None,
    expect_integrity: bool | None = None,
    verbose_reason_contains: str | None = None,
) -> dict[str, Any] | None:
    log_dir = ctx.report_dir / _slug(scenario.scenario_name)

    verify_record = _run_command(
        log_dir=log_dir,
        label=f"Verify {artifact_path.name}",
        argv=[str(ctx.epi_executable), "verify", str(artifact_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=120,
    )
    scenario.commands.append(verify_record)
    _assert(
        verify_record.returncode == expect_exit,
        f"`epi verify` returned {verify_record.returncode} for {artifact_path.name}, expected {expect_exit}.",
    )

    json_record = _run_command(
        log_dir=log_dir,
        label=f"Verify JSON {artifact_path.name}",
        argv=[str(ctx.epi_executable), "verify", "--json", str(artifact_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=120,
    )
    scenario.commands.append(json_record)
    _assert(
        json_record.returncode == expect_exit,
        f"`epi verify --json` returned {json_record.returncode} for {artifact_path.name}, expected {expect_exit}.",
    )

    if expect_exit != 0 and verbose_reason_contains:
        verbose_record = _run_command(
            log_dir=log_dir,
            label=f"Verify verbose {artifact_path.name}",
            argv=[str(ctx.epi_executable), "verify", "--verbose", str(artifact_path)],
            cwd=REPO_ROOT,
            env=ctx.base_env,
            timeout_seconds=120,
        )
        scenario.commands.append(verbose_record)
        combined = (_load_text(verbose_record.stdout_path) + "\n" + _load_text(verbose_record.stderr_path)).lower()
        _assert(
            verbose_reason_contains.lower() in combined,
            f"Expected verify verbose output for {artifact_path.name} to include '{verbose_reason_contains}'.",
        )

    report = _parse_json_stdout(json_record)
    _assert(isinstance(report, dict), f"`epi verify --json` returned a non-object for {artifact_path.name}.")

    if expected_trust_level is not None:
        _assert(
            report.get("trust_level") == expected_trust_level,
            f"Unexpected trust level for {artifact_path.name}: {report.get('trust_level')} != {expected_trust_level}.",
        )
    if expect_signature_valid is not None:
        _assert(
            report.get("signature_valid") is expect_signature_valid,
            f"Unexpected signature_valid for {artifact_path.name}: {report.get('signature_valid')} != {expect_signature_valid}.",
        )
    if expect_integrity is not None:
        _assert(
            report.get("integrity_ok") is expect_integrity,
            f"Unexpected integrity_ok for {artifact_path.name}: {report.get('integrity_ok')} != {expect_integrity}.",
        )
    scenario.verify_report = report
    return report


def _extract_view(
    ctx: InstallContext,
    scenario: ScenarioResult,
    artifact_path: Path,
    extract_dir: Path,
    *,
    expect_members: list[str] | None = None,
) -> None:
    log_dir = ctx.report_dir / _slug(scenario.scenario_name)
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.parent.mkdir(parents=True, exist_ok=True)

    record = _run_command(
        log_dir=log_dir,
        label=f"Extract view {artifact_path.name}",
        argv=[str(ctx.epi_executable), "view", "--extract", str(extract_dir), str(artifact_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=180,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"`epi view --extract` failed for {artifact_path.name}.")

    viewer_html = extract_dir / "viewer.html"
    _assert(viewer_html.exists(), f"viewer.html was not extracted for {artifact_path.name}.")

    html = viewer_html.read_text(encoding="utf-8", errors="replace")
    _assert('id="epi-preloaded-cases"' in html, f"viewer.html missing epi-preloaded-cases marker for {artifact_path.name}.")
    _assert('id="epi-view-context"' in html, f"viewer.html missing epi-view-context marker for {artifact_path.name}.")
    _assert('"embeddedArtifactMode": true' in html, f"viewer.html missing embeddedArtifactMode marker for {artifact_path.name}.")

    for relative_member in expect_members or []:
        _assert(
            (extract_dir / relative_member).exists(),
            f"Extracted view missing expected member {relative_member} for {artifact_path.name}.",
        )

    scenario.extracted_review_path = str(extract_dir)


def _export_summary_text(
    ctx: InstallContext,
    scenario: ScenarioResult,
    artifact_path: Path,
) -> None:
    log_dir = ctx.report_dir / _slug(scenario.scenario_name)
    record = _run_command(
        log_dir=log_dir,
        label=f"Export summary {artifact_path.name}",
        argv=[str(ctx.epi_executable), "export-summary", "summary", str(artifact_path), "--text"],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=120,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"`epi export-summary summary --text` failed for {artifact_path.name}.")
    stdout = _load_text(record.stdout_path)
    _assert("EPI DECISION RECORD" in stdout, "Text summary missing EPI DECISION RECORD heading.")
    _assert("POLICY COMPLIANCE" in stdout, "Text summary missing POLICY COMPLIANCE section.")


def _create_install_context(root: Path, install_mode: str) -> InstallContext:
    env_dir = root / f"{install_mode}_env"
    home_dir = root / "homes" / install_mode
    work_dir = root / "work" / install_mode
    report_dir = root / "reports" / install_mode
    artifact_dir = root / "artifacts" / install_mode
    extract_dir = root / "extracted" / install_mode
    helper_dir = root / "helpers"

    for path in (
        home_dir / "AppData" / "Roaming",
        home_dir / "AppData" / "Local",
        report_dir,
        artifact_dir,
        extract_dir,
        helper_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    install_record = InstallRecord(install_mode=install_mode)
    runtime_temp = _pick_runtime_temp_dir(install_mode, work_dir / "tmp")
    base_env = _base_env(home_dir, runtime_temp)
    shim_dir = work_dir / "python-temp-shim"
    safe_temp_dir = work_dir / "python-safe-temp"
    _write_python_temp_shim(shim_dir, safe_temp_dir)
    base_env["PYTHONPATH"] = str(shim_dir)

    return InstallContext(
        install_mode=install_mode,
        env_dir=env_dir,
        home_dir=home_dir,
        work_dir=work_dir,
        report_dir=report_dir,
        artifact_dir=artifact_dir,
        extract_dir=extract_dir,
        helper_dir=helper_dir,
        python_executable=_venv_python(env_dir),
        epi_executable=_venv_epi(env_dir),
        base_env=base_env,
        install_record=install_record,
    )


def _collect_install_info(ctx: InstallContext) -> None:
    info_code = (
        "import inspect, json, platform, sys; "
        "import epi_core, epi_recorder; "
        "print(json.dumps({"
        "'python_version': platform.python_version(), "
        "'epi_version': getattr(epi_recorder, '__version__', getattr(epi_core, '__version__', 'unknown')), "
        "'package_location': inspect.getfile(epi_recorder), "
        "'python_executable': sys.executable"
        "}, indent=2))"
    )
    record = _run_command(
        log_dir=ctx.report_dir / "install",
        label=f"{ctx.install_mode} environment info",
        argv=[str(ctx.python_executable), "-I", "-c", info_code],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=120,
    )
    ctx.install_record.commands.append(record)
    _assert(record.returncode == 0, f"Could not collect install info for {ctx.install_mode}.")
    payload = _parse_json_stdout(record)
    _assert(isinstance(payload, dict), f"Install info payload was not an object for {ctx.install_mode}.")
    ctx.install_record.python_executable = payload.get("python_executable")
    ctx.install_record.epi_executable = str(ctx.epi_executable)
    ctx.install_record.python_version = payload.get("python_version")
    ctx.install_record.epi_version = payload.get("epi_version")
    ctx.install_record.package_location = payload.get("package_location")
    ctx.install_record.clean_home = str(ctx.home_dir)


def _bootstrap_source_install(ctx: InstallContext) -> None:
    create_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Create source venv",
        argv=[str(HOST_PYTHON), "-m", "venv", "--without-pip", str(ctx.env_dir)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    ctx.install_record.commands.append(create_record)
    _assert(create_record.returncode == 0, "Failed to create source validation venv.")

    ensurepip_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Bootstrap source pip",
        argv=[str(ctx.python_executable), "-m", "ensurepip", "--upgrade", "--default-pip"],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    ctx.install_record.commands.append(ensurepip_record)
    _assert(ensurepip_record.returncode == 0, "Failed to bootstrap pip in source validation venv.")

    install_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Source install",
        argv=[str(ctx.python_executable), "-m", "pip", "install", "."],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=900,
    )
    ctx.install_record.commands.append(install_record)
    _assert(install_record.returncode == 0, "Source install failed.")
    _collect_install_info(ctx)
    ctx.install_record.status = "PASS"


def _build_wheel(root: Path, base_env: dict[str, str]) -> tuple[Path, str, list[CommandRecord]]:
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir(parents=True, exist_ok=True)

    build_log_dir = root / "reports" / "wheel-build"
    wheel_record = _run_command(
        log_dir=build_log_dir,
        label="Build wheel",
        argv=[str(HOST_PYTHON), "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheelhouse)],
        cwd=REPO_ROOT,
        env=base_env,
        timeout_seconds=900,
    )
    _assert(wheel_record.returncode == 0, "Wheel build failed.")

    wheels = sorted(wheelhouse.glob("epi_recorder-*.whl"), key=lambda path: path.stat().st_mtime)
    _assert(bool(wheels), "Wheel build completed but no epi_recorder wheel was produced.")
    wheel_path = wheels[-1]

    audit_record = _run_command(
        log_dir=build_log_dir,
        label="Audit wheel",
        argv=[str(HOST_PYTHON), str(REPO_ROOT / "scripts" / "audit_wheel.py"), str(wheel_path)],
        cwd=REPO_ROOT,
        env=base_env,
        timeout_seconds=300,
    )
    _assert(audit_record.returncode == 0, f"Wheel audit failed for {wheel_path.name}.")

    return wheel_path, "PASS", [wheel_record, audit_record]


def _bootstrap_wheel_install(ctx: InstallContext, wheel_path: Path, wheel_audit_status: str) -> None:
    create_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Create wheel venv",
        argv=[str(HOST_PYTHON), "-m", "venv", "--without-pip", str(ctx.env_dir)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    ctx.install_record.commands.append(create_record)
    _assert(create_record.returncode == 0, "Failed to create wheel validation venv.")

    ensurepip_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Bootstrap wheel pip",
        argv=[str(ctx.python_executable), "-m", "ensurepip", "--upgrade", "--default-pip"],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    ctx.install_record.commands.append(ensurepip_record)
    _assert(ensurepip_record.returncode == 0, "Failed to bootstrap pip in wheel validation venv.")

    install_record = _run_command(
        log_dir=ctx.report_dir / "install",
        label="Wheel install",
        argv=[str(ctx.python_executable), "-m", "pip", "install", str(wheel_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=900,
    )
    ctx.install_record.commands.append(install_record)
    _assert(install_record.returncode == 0, "Wheel install failed.")
    _collect_install_info(ctx)
    ctx.install_record.wheel_path = str(wheel_path)
    ctx.install_record.wheel_audit_status = wheel_audit_status
    ctx.install_record.status = "PASS"


def _run_epi_record(
    ctx: InstallContext,
    scenario: ScenarioResult,
    *,
    output_path: Path,
    script_path: Path,
    signed: bool,
) -> None:
    argv = [str(ctx.epi_executable), "record", "--out", str(output_path)]
    if not signed:
        argv.append("--no-sign")
    argv.extend(["--", str(ctx.python_executable), "-I", str(script_path), str(output_path.with_suffix(".json"))])

    record = _run_command(
        log_dir=ctx.report_dir / _slug(scenario.scenario_name),
        label=f"Record {output_path.name}",
        argv=argv,
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"`epi record` failed for {output_path.name}.")
    _assert(output_path.exists(), f"Expected artifact was not created: {output_path}.")
    scenario.artifact_path = str(output_path)


def _run_api_capture(
    ctx: InstallContext,
    scenario: ScenarioResult,
    *,
    output_path: Path,
    helper_path: Path,
) -> None:
    record = _run_command(
        log_dir=ctx.report_dir / _slug(scenario.scenario_name),
        label=f"API capture {output_path.name}",
        argv=[str(ctx.python_executable), "-I", str(helper_path), str(output_path)],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"API capture script failed for {output_path.name}.")
    _assert(output_path.exists(), f"Expected API artifact was not created: {output_path}.")
    scenario.artifact_path = str(output_path)


def _mutate_artifact(
    ctx: InstallContext,
    scenario: ScenarioResult,
    *,
    source_path: Path,
    destination_path: Path,
    mode: str,
) -> None:
    record = _run_command(
        log_dir=ctx.report_dir / _slug(scenario.scenario_name),
        label=f"Mutate {destination_path.name}",
        argv=[
            str(ctx.python_executable),
            "-I",
            str(ctx.helper_dir / "mutate_artifact.py"),
            mode,
            str(source_path),
            str(destination_path),
        ],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=180,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"Artifact mutation failed for {destination_path.name}.")
    _assert(destination_path.exists(), f"Mutated artifact was not created: {destination_path}.")
    scenario.artifact_path = str(destination_path)


def _run_agt_import(
    ctx: InstallContext,
    scenario: ScenarioResult,
    *,
    agt_input: Path,
    output_path: Path,
    signed: bool = True,
) -> None:
    argv = [str(ctx.epi_executable), "import", "agt", str(agt_input), "--out", str(output_path)]
    if not signed:
        argv.append("--no-sign")

    record = _run_command(
        log_dir=ctx.report_dir / _slug(scenario.scenario_name),
        label=f"Import AGT {output_path.name}",
        argv=argv,
        cwd=REPO_ROOT,
        env=ctx.base_env,
        timeout_seconds=300,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"`epi import agt` failed for {agt_input}.")
    _assert(output_path.exists(), f"Expected AGT artifact was not created: {output_path}.")
    scenario.artifact_path = str(output_path)


def _run_review_save(
    ctx: InstallContext,
    scenario: ScenarioResult,
    *,
    artifact_path: Path,
) -> None:
    review_input = ("c\nHarness review note\n" * 5)
    record = _run_command(
        log_dir=ctx.report_dir / _slug(scenario.scenario_name),
        label=f"Review {artifact_path.name}",
        argv=[str(ctx.epi_executable), "review", str(artifact_path), "--reviewer", "validator@example.com"],
        cwd=REPO_ROOT,
        env=ctx.base_env,
        input_text=review_input,
        timeout_seconds=300,
    )
    scenario.commands.append(record)
    _assert(record.returncode == 0, f"`epi review` failed for {artifact_path.name}.")
    combined = _load_text(record.stdout_path) + "\n" + _load_text(record.stderr_path)
    _assert("Review saved" in combined, f"`epi review` did not save a review for {artifact_path.name}.")


def _run_valid_local_scenarios(ctx: InstallContext, helpers: dict[str, Path]) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []

    signed = _new_scenario(ctx, "local signed artifact")
    signed_path = ctx.artifact_dir / "local_signed.epi"
    try:
        _run_epi_record(ctx, signed, output_path=signed_path, script_path=helpers["record_workflow"], signed=True)
        inspect = _inspect_artifact(ctx, signed_path, ctx.report_dir / _slug(signed.scenario_name))
        _assert(inspect.get("has_signature") is True, "Signed local artifact has no signature.")
        _assert(inspect.get("container_format") == "envelope-v2", "Signed local artifact did not use envelope-v2.")
        _verify_artifact(ctx, signed, signed_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
        _extract_view(ctx, signed, signed_path, ctx.extract_dir / "local_signed")
        signed.status = "PASS"
        signed.notes.append("Signed local artifact recorded, verified at HIGH trust, and extracted cleanly.")
    except Exception as exc:
        signed.error = str(exc)
    results.append(signed)

    unsigned = _new_scenario(ctx, "local unsigned artifact")
    unsigned_path = ctx.artifact_dir / "local_unsigned.epi"
    try:
        _run_epi_record(ctx, unsigned, output_path=unsigned_path, script_path=helpers["record_workflow"], signed=False)
        inspect = _inspect_artifact(ctx, unsigned_path, ctx.report_dir / _slug(unsigned.scenario_name))
        _assert(inspect.get("has_signature") is False, "Unsigned local artifact unexpectedly has a signature.")
        _verify_artifact(ctx, unsigned, unsigned_path, expect_exit=0, expected_trust_level="MEDIUM", expect_signature_valid=None, expect_integrity=True)
        _extract_view(ctx, unsigned, unsigned_path, ctx.extract_dir / "local_unsigned")
        unsigned.status = "PASS"
        unsigned.notes.append("Unsigned local artifact verified at MEDIUM trust and extracted cleanly.")
    except Exception as exc:
        unsigned.error = str(exc)
    results.append(unsigned)

    api_capture = _new_scenario(ctx, "local api artifact")
    api_capture_path = ctx.artifact_dir / "api_capture.epi"
    try:
        _run_api_capture(ctx, api_capture, output_path=api_capture_path, helper_path=helpers["api_capture"])
        inspect = _inspect_artifact(ctx, api_capture_path, ctx.report_dir / _slug(api_capture.scenario_name))
        _assert(inspect.get("has_signature") is True, "API artifact has no signature.")
        _verify_artifact(ctx, api_capture, api_capture_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
        _extract_view(ctx, api_capture, api_capture_path, ctx.extract_dir / "api_capture")
        api_capture.status = "PASS"
        api_capture.notes.append("API-recorded artifact verified at HIGH trust and extracted cleanly.")
    except Exception as exc:
        api_capture.error = str(exc)
    results.append(api_capture)

    return results


def _run_invalid_local_scenarios(ctx: InstallContext, source_artifact: Path) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []

    tampered = _new_scenario(ctx, "local tampered artifact")
    tampered_path = ctx.artifact_dir / "local_tampered.epi"
    try:
        _mutate_artifact(ctx, tampered, source_path=source_artifact, destination_path=tampered_path, mode="tamper")
        _verify_artifact(ctx, tampered, tampered_path, expect_exit=1, expected_trust_level="NONE", expect_signature_valid=True, expect_integrity=False)
        tampered.status = "PASS"
        tampered.notes.append("Tampered local artifact fails verification with integrity compromise.")
    except Exception as exc:
        tampered.error = str(exc)
    results.append(tampered)

    bad_signature = _new_scenario(ctx, "local invalid signature artifact")
    bad_signature_path = ctx.artifact_dir / "local_invalid_signature.epi"
    try:
        _mutate_artifact(ctx, bad_signature, source_path=source_artifact, destination_path=bad_signature_path, mode="invalid-signature")
        _verify_artifact(ctx, bad_signature, bad_signature_path, expect_exit=1, expected_trust_level="NONE", expect_signature_valid=False, expect_integrity=True)
        bad_signature.status = "PASS"
        bad_signature.notes.append("Local artifact with corrupted signature fails verification while integrity remains intact.")
    except Exception as exc:
        bad_signature.error = str(exc)
    results.append(bad_signature)

    missing_key = _new_scenario(ctx, "local missing public key artifact")
    missing_key_path = ctx.artifact_dir / "local_missing_public_key.epi"
    try:
        _mutate_artifact(ctx, missing_key, source_path=source_artifact, destination_path=missing_key_path, mode="missing-public-key")
        _verify_artifact(
            ctx,
            missing_key,
            missing_key_path,
            expect_exit=1,
            expected_trust_level="NONE",
            expect_signature_valid=False,
            expect_integrity=True,
            verbose_reason_contains="no public key embedded",
        )
        missing_key.status = "PASS"
        missing_key.notes.append("Local artifact with missing embedded public key fails signature verification with the expected reason.")
    except Exception as exc:
        missing_key.error = str(exc)
    results.append(missing_key)

    bad_archive = _new_scenario(ctx, "local bad archive artifact")
    bad_archive_path = ctx.artifact_dir / "local_bad_archive.epi"
    try:
        _mutate_artifact(ctx, bad_archive, source_path=source_artifact, destination_path=bad_archive_path, mode="bad-archive")
        _verify_artifact(
            ctx,
            bad_archive,
            bad_archive_path,
            expect_exit=1,
            expected_trust_level="NONE",
            expect_integrity=False,
            verbose_reason_contains="structural validation failed",
        )
        bad_archive.status = "PASS"
        bad_archive.notes.append("Broken archive fails structural verification as expected.")
    except Exception as exc:
        bad_archive.error = str(exc)
    results.append(bad_archive)

    return results


def _assert_agt_members(members: list[str], artifact_name: str) -> None:
    required = {
        "steps.jsonl",
        "policy.json",
        "policy_evaluation.json",
        "analysis.json",
        "artifacts/annex_iv.md",
        "artifacts/annex_iv.json",
        "artifacts/agt/mapping_report.json",
        "artifacts/agt/bundle.json",
    }
    missing = sorted(required - set(members))
    _assert(not missing, f"{artifact_name} is missing expected AGT members: {', '.join(missing)}")


def _run_agt_scenarios(ctx: InstallContext) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []

    bundle = _new_scenario(ctx, "agt bundle import")
    bundle_path = ctx.artifact_dir / "agt_bundle.epi"
    try:
        _run_agt_import(ctx, bundle, agt_input=AGT_BUNDLE_INPUT, output_path=bundle_path, signed=True)
        inspect = _inspect_artifact(ctx, bundle_path, ctx.report_dir / _slug(bundle.scenario_name))
        _assert(inspect.get("has_signature") is True, "Signed AGT bundle import has no signature.")
        _assert_agt_members(inspect.get("members", []), bundle_path.name)
        _verify_artifact(ctx, bundle, bundle_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
        _extract_view(
            ctx,
            bundle,
            bundle_path,
            ctx.extract_dir / "agt_bundle",
            expect_members=["artifacts/annex_iv.json", "artifacts/annex_iv.md", "artifacts/agt/mapping_report.json"],
        )
        _export_summary_text(ctx, bundle, bundle_path)
        bundle.status = "PASS"
        bundle.notes.append("Signed AGT bundle import verified, extracted, and exported summary text successfully.")
    except Exception as exc:
        bundle.error = str(exc)
    results.append(bundle)

    directory = _new_scenario(ctx, "agt directory import")
    directory_path = ctx.artifact_dir / "agt_directory.epi"
    try:
        _run_agt_import(ctx, directory, agt_input=AGT_DIRECTORY_INPUT, output_path=directory_path, signed=True)
        inspect = _inspect_artifact(ctx, directory_path, ctx.report_dir / _slug(directory.scenario_name))
        _assert_agt_members(inspect.get("members", []), directory_path.name)
        _verify_artifact(ctx, directory, directory_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
        _extract_view(
            ctx,
            directory,
            directory_path,
            ctx.extract_dir / "agt_directory",
            expect_members=["artifacts/annex_iv.json", "artifacts/agt/mapping_report.json"],
        )
        directory.status = "PASS"
        directory.notes.append("Signed AGT directory import verified and extracted cleanly.")
    except Exception as exc:
        directory.error = str(exc)
    results.append(directory)

    manifest = _new_scenario(ctx, "agt manifest import")
    manifest_path = ctx.artifact_dir / "agt_manifest.epi"
    try:
        _run_agt_import(ctx, manifest, agt_input=AGT_MANIFEST_INPUT, output_path=manifest_path, signed=True)
        inspect = _inspect_artifact(ctx, manifest_path, ctx.report_dir / _slug(manifest.scenario_name))
        _assert_agt_members(inspect.get("members", []), manifest_path.name)
        _verify_artifact(ctx, manifest, manifest_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
        _extract_view(
            ctx,
            manifest,
            manifest_path,
            ctx.extract_dir / "agt_manifest",
            expect_members=["artifacts/annex_iv.json", "artifacts/agt/mapping_report.json"],
        )
        manifest.status = "PASS"
        manifest.notes.append("Signed AGT manifest import verified and extracted cleanly.")
    except Exception as exc:
        manifest.error = str(exc)
    results.append(manifest)

    unsigned = _new_scenario(ctx, "agt unsigned import")
    unsigned_path = ctx.artifact_dir / "agt_unsigned.epi"
    try:
        _run_agt_import(ctx, unsigned, agt_input=AGT_BUNDLE_INPUT, output_path=unsigned_path, signed=False)
        inspect = _inspect_artifact(ctx, unsigned_path, ctx.report_dir / _slug(unsigned.scenario_name))
        _assert(inspect.get("has_signature") is False, "Unsigned AGT import unexpectedly has a signature.")
        _assert_agt_members(inspect.get("members", []), unsigned_path.name)
        _verify_artifact(ctx, unsigned, unsigned_path, expect_exit=0, expected_trust_level="MEDIUM", expect_signature_valid=None, expect_integrity=True)
        _extract_view(
            ctx,
            unsigned,
            unsigned_path,
            ctx.extract_dir / "agt_unsigned",
            expect_members=["artifacts/annex_iv.json", "artifacts/agt/mapping_report.json"],
        )
        unsigned.status = "PASS"
        unsigned.notes.append("Unsigned AGT import verified at MEDIUM trust and extracted cleanly.")
    except Exception as exc:
        unsigned.error = str(exc)
    results.append(unsigned)

    tampered = _new_scenario(ctx, "agt tampered import")
    tampered_path = ctx.artifact_dir / "agt_tampered.epi"
    if bundle.status != "PASS":
        tampered.error = "Skipped because the signed AGT bundle import scenario failed."
    else:
        try:
            _mutate_artifact(ctx, tampered, source_path=bundle_path, destination_path=tampered_path, mode="tamper")
            _verify_artifact(ctx, tampered, tampered_path, expect_exit=1, expected_trust_level="NONE", expect_signature_valid=True, expect_integrity=False)
            tampered.status = "PASS"
            tampered.notes.append("Tampered AGT import fails verification with integrity compromise.")
        except Exception as exc:
            tampered.error = str(exc)
    results.append(tampered)

    reviewed = _new_scenario(ctx, "agt review save and reverify")
    if bundle.status != "PASS":
        reviewed.error = "Skipped because the signed AGT bundle import scenario failed."
    else:
        try:
            _run_review_save(ctx, reviewed, artifact_path=bundle_path)
            inspect = _inspect_artifact(ctx, bundle_path, ctx.report_dir / _slug(reviewed.scenario_name))
            _assert("review.json" in inspect.get("members", []), "Reviewed AGT artifact is missing review.json.")
            _verify_artifact(ctx, reviewed, bundle_path, expect_exit=0, expected_trust_level="HIGH", expect_signature_valid=True, expect_integrity=True)
            reviewed.artifact_path = str(bundle_path)
            reviewed.status = "PASS"
            reviewed.notes.append("AGT review record was appended and the artifact still verifies at HIGH trust.")
        except Exception as exc:
            reviewed.error = str(exc)
    results.append(reviewed)

    return results


def _write_summary_json(
    out_dir: Path,
    installs: list[InstallRecord],
    scenarios: list[ScenarioResult],
    started_at: float,
) -> Path:
    summary_path = out_dir / "reports" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo_root": str(REPO_ROOT),
        "out_dir": str(out_dir),
        "generated_at_unix": int(time.time()),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "manual_checklist": str(CHECKLIST_PATH),
        "installs": [asdict(item) for item in installs],
        "scenarios": [asdict(item) for item in scenarios],
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def _write_summary_markdown(
    out_dir: Path,
    installs: list[InstallRecord],
    scenarios: list[ScenarioResult],
) -> Path:
    summary_path = out_dir / "reports" / "summary.md"
    lines = [
        "# External User Validation Summary",
        "",
        f"- Repo: `{REPO_ROOT}`",
        f"- Checklist: `{CHECKLIST_PATH}`",
        "",
        "## Installs",
        "",
        "| Mode | Status | Python | EPI | Home | Wheel Audit |",
        "|---|---|---|---|---|---|",
    ]
    for install in installs:
        lines.append(
            "| {mode} | {status} | {python} | {epi} | `{home}` | {wheel_audit} |".format(
                mode=install.install_mode,
                status=install.status,
                python=install.python_version or "n/a",
                epi=install.epi_version or "n/a",
                home=install.clean_home or "n/a",
                wheel_audit=install.wheel_audit_status or "n/a",
            )
        )

    lines.extend(["", "## Scenarios", "", "| Install | Scenario | Status | Trust | Artifact | Extracted Review | Notes |", "|---|---|---|---|---|---|---|"])

    for scenario in scenarios:
        trust = (scenario.verify_report or {}).get("trust_level", "n/a")
        notes = scenario.error or ("; ".join(scenario.notes) if scenario.notes else "")
        lines.append(
            "| {install} | {scenario_name} | {status} | {trust} | `{artifact}` | `{extract}` | {notes} |".format(
                install=scenario.install_mode,
                scenario_name=scenario.scenario_name,
                status=scenario.status,
                trust=trust,
                artifact=scenario.artifact_path or "n/a",
                extract=scenario.extracted_review_path or "n/a",
                notes=notes.replace("\n", " "),
            )
        )

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def _run_install_mode(ctx: InstallContext, helpers: dict[str, Path]) -> list[ScenarioResult]:
    local_results = _run_valid_local_scenarios(ctx, helpers)
    signed_local = next(
        (
            Path(item.artifact_path)
            for item in local_results
            if item.scenario_name == "local signed artifact" and item.status == "PASS" and item.artifact_path
        ),
        None,
    )
    invalid_results: list[ScenarioResult] = []
    if signed_local is not None:
        invalid_results = _run_invalid_local_scenarios(ctx, signed_local)
    else:
        placeholder = _new_scenario(ctx, "local invalid trust matrix")
        placeholder.error = "Skipped because the signed local artifact scenario failed."
        invalid_results.append(placeholder)

    agt_results = _run_agt_scenarios(ctx)
    return local_results + invalid_results + agt_results


def _fail_install_context(ctx: InstallContext, exc: Exception) -> None:
    ctx.install_record.status = "FAIL"
    ctx.install_record.error = str(exc)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean-room external user validation for epi-recorder.")
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Workspace directory for venvs, artifacts, extracts, and reports.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    started_at = time.time()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    helpers = _write_shared_helpers(out_dir / "helpers")
    installs: list[InstallRecord] = []
    scenarios: list[ScenarioResult] = []

    source_ctx = _create_install_context(out_dir, "source")
    try:
        _bootstrap_source_install(source_ctx)
    except Exception as exc:
        _fail_install_context(source_ctx, exc)
    installs.append(source_ctx.install_record)
    if source_ctx.install_record.status == "PASS":
        scenarios.extend(_run_install_mode(source_ctx, helpers))

    wheel_ctx = _create_install_context(out_dir, "wheel")
    try:
        wheel_path, wheel_audit_status, wheel_build_records = _build_wheel(out_dir, wheel_ctx.base_env)
        wheel_ctx.install_record.commands.extend(wheel_build_records)
        _bootstrap_wheel_install(wheel_ctx, wheel_path, wheel_audit_status)
    except Exception as exc:
        _fail_install_context(wheel_ctx, exc)
    installs.append(wheel_ctx.install_record)
    if wheel_ctx.install_record.status == "PASS":
        scenarios.extend(_run_install_mode(wheel_ctx, helpers))

    summary_json = _write_summary_json(out_dir, installs, scenarios, started_at)
    summary_md = _write_summary_markdown(out_dir, installs, scenarios)

    failed_installs = [item for item in installs if item.status != "PASS"]
    failed_scenarios = [item for item in scenarios if item.status != "PASS"]

    print(summary_md)
    print(summary_json)

    return 1 if failed_installs or failed_scenarios else 0


if __name__ == "__main__":
    raise SystemExit(main())
