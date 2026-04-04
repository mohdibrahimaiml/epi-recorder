from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\epi-temp\epi_pypi_validation_20260404_011400").resolve()
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
EPI = ROOT / ".venv" / "Scripts" / "epi.exe"
PYTEST = ROOT / ".venv" / "Scripts" / "pytest.exe"

SCRIPTS = ROOT / "scripts"
ARTIFACTS = ROOT / "artifacts"
REPORTS = ROOT / "reports"
EXTRACTED = ROOT / "extracted"
EVIDENCE_FAIL_ONLY = ROOT / "evidence_fail_only"
EVIDENCE_ALL = ROOT / "evidence_all"
HOME = ROOT / "home"
TMP_RUNTIME = ROOT / "temp_runtime"
SUMMARY_JSON = ROOT / "validation_summary.json"
SUMMARY_MD = ROOT / "validation_report.md"
CURRENT_RESULT: "TestResult | None" = None


def ensure_dirs() -> None:
    for path in (
        ROOT,
        SCRIPTS,
        ARTIFACTS,
        REPORTS,
        EXTRACTED,
        EVIDENCE_FAIL_ONLY,
        EVIDENCE_ALL,
        HOME / "AppData" / "Local",
        HOME / "AppData" / "Roaming",
        TMP_RUNTIME,
    ):
        path.mkdir(parents=True, exist_ok=True)


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "LANGCHAIN_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "MISTRAL_API_KEY",
            "COHERE_API_KEY",
            "TOGETHER_API_KEY",
            "PYTHONPATH",
            "PYTHONHOME",
        }:
            env.pop(key, None)
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["HOME"] = str(HOME)
    env["USERPROFILE"] = str(HOME)
    env["APPDATA"] = str(HOME / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(HOME / "AppData" / "Local")
    env["TEMP"] = str(TMP_RUNTIME)
    env["TMP"] = str(TMP_RUNTIME)
    return env


def list_cmdline(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def read_json_member(epi_path: Path, member: str) -> Any:
    with zipfile.ZipFile(epi_path, "r") as zf:
        return json.loads(zf.read(member).decode("utf-8"))


def read_member_bytes(epi_path: Path, member: str) -> bytes:
    with zipfile.ZipFile(epi_path, "r") as zf:
        return zf.read(member)


def read_steps(epi_path: Path) -> list[dict[str, Any]]:
    raw = read_member_bytes(epi_path, "steps.jsonl").decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def member_exists(epi_path: Path, member: str) -> bool:
    with zipfile.ZipFile(epi_path, "r") as zf:
        return member in zf.namelist()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def newest_html(root: Path) -> Path | None:
    candidates = list(root.glob("*.html"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class CommandRun:
    label: str
    command: list[str]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    timeout: int | None = None


@dataclass
class TestResult:
    number: int
    name: str
    status: str = "FAIL"
    notes: list[str] = field(default_factory=list)
    commands: list[CommandRun] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    scripts: list[Path] = field(default_factory=list)

    @property
    def report_dir(self) -> Path:
        return REPORTS / f"test{self.number:02d}"

    def add_note(self, text: str) -> None:
        self.notes.append(text)

    def add_artifact(self, path: Path | str) -> None:
        self.artifacts.append(str(path))

    def add_script(self, path: Path) -> None:
        self.scripts.append(path)

    def save(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        command_parts: list[str] = []
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        for idx, run in enumerate(self.commands, start=1):
            command_parts.append(
                f"[{idx}] {run.label}\nCWD: {run.cwd}\nCMD: {list_cmdline(run.command)}\nRETURN CODE: {run.returncode}\n"
            )
            stdout_parts.append(f"[{idx}] {run.label}\n{run.stdout}")
            stderr_parts.append(f"[{idx}] {run.label}\n{run.stderr}")
        (self.report_dir / "command.txt").write_text("\n\n".join(command_parts), encoding="utf-8")
        (self.report_dir / "stdout.txt").write_text("\n\n".join(stdout_parts), encoding="utf-8")
        (self.report_dir / "stderr.txt").write_text("\n\n".join(stderr_parts), encoding="utf-8")
        notes = [f"Status: {self.status}", "", "Notes:", *self.notes, "", "Artifacts:", *self.artifacts]
        (self.report_dir / "notes.txt").write_text("\n".join(notes), encoding="utf-8")
        for script in self.scripts:
            if script.exists():
                shutil.copy2(script, self.report_dir / script.name)
        (self.report_dir / "result.json").write_text(
            json.dumps(
                {
                    "number": self.number,
                    "name": self.name,
                    "status": self.status,
                    "notes": self.notes,
                    "artifacts": self.artifacts,
                    "extra": self.extra,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class HarnessError(RuntimeError):
    pass


def activate(result: TestResult) -> TestResult:
    global CURRENT_RESULT
    CURRENT_RESULT = result
    return result


def run_command(
    result: TestResult,
    label: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 180,
    input_text: str | None = None,
) -> CommandRun:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env or base_env(),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    run = CommandRun(label, command, cwd, completed.returncode, completed.stdout, completed.stderr, timeout)
    result.commands.append(run)
    return run


def write_script(name: str, content: str) -> Path:
    path = SCRIPTS / name
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def verify_artifact(result: TestResult, artifact: Path, *, label: str = "epi verify") -> CommandRun:
    return run_command(result, label, [str(EPI), "verify", str(artifact)], cwd=ROOT, timeout=120)


def artifact_signature_present(artifact: Path) -> bool:
    manifest = read_json_member(artifact, "manifest.json")
    return bool(manifest.get("signature"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def isolation_probe() -> dict[str, Any]:
    probe_script = write_script(
        "isolation_probe.py",
        """
        import inspect
        import json
        import sys
        import epi_recorder

        payload = {
            "sys_executable": sys.executable,
            "sys_path": sys.path,
            "epi_recorder_file": inspect.getfile(epi_recorder),
        }
        print(json.dumps(payload, indent=2))
        """,
    )
    result = activate(TestResult(0, "Isolation Probe"))
    result.add_script(probe_script)
    run = run_command(result, "Isolation probe", [str(PYTHON), "-I", str(probe_script)], cwd=ROOT, timeout=60)
    result.save()
    if run.returncode != 0:
        raise HarnessError("Isolation probe failed to run.")
    return json.loads(run.stdout)


def test01_basic() -> TestResult:
    result = activate(TestResult(1, "Basic Recording"))
    artifact = ARTIFACTS / "test01_basic.epi"
    script = write_script(
        "test01_basic.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), workflow_name="Basic Recording Test") as epi:
            epi.log_step("tool.call", {{"tool": "lookup_order", "input": {{"order_id": "123"}}}})
            epi.log_step("tool.response", {{"tool": "lookup_order", "status": "success", "output": {{"order_id": "123", "amount": 99}}}})
            epi.log_step("agent.decision", {{"decision": "approve_refund", "confidence": 0.9}})
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run basic recording script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Basic recording did not create the .epi file.")
    result.add_artifact(artifact)
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "epi verify failed for Test 1.")
    require(artifact_signature_present(artifact), "Basic recording artifact is unsigned.")
    result.status = "PASS"
    result.add_note("Artifact created, verified successfully, and manifest includes a signature.")
    result.save()
    return result


def test02_metadata() -> TestResult:
    result = activate(TestResult(2, "Metadata and Goal"))
    artifact = ARTIFACTS / "test02_metadata.epi"
    script = write_script(
        "test02_metadata.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), goal="Process refund", notes="Test run", metrics={{"amount": 500}}):
            pass
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run metadata script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Metadata test did not create the .epi file.")
    result.add_artifact(artifact)
    manifest = read_json_member(artifact, "manifest.json")
    require(manifest.get("goal") == "Process refund", "Manifest goal is incorrect.")
    require(manifest.get("notes") == "Test run", "Manifest notes are incorrect.")
    require(manifest.get("metrics") == {"amount": 500}, "Manifest metrics are incorrect.")
    result.status = "PASS"
    result.add_note("Manifest goal, notes, and metrics match expected values.")
    result.save()
    return result


def test03_agent_run() -> TestResult:
    result = activate(TestResult(3, "AgentRun API"))
    artifact = ARTIFACTS / "test03_agent_run.epi"
    script = write_script(
        "test03_agent_run.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), goal="AgentRun API Test") as epi:
            with epi.agent_run("claims-agent", user_input="Review claim", goal="Decide claim") as agent:
                agent.plan("Check claim, ask for approval, then decide.")
                agent.tool_call("lookup_claim", {{"claim_id": "CLM-1"}})
                agent.tool_result("lookup_claim", {{"claim_id": "CLM-1", "amount": 500}})
                agent.approval_request("deny_claim", reason="Large denial")
                agent.approval_response("deny_claim", approved=True, reviewer="manager@example.com")
                agent.decision("deny_claim", confidence=0.95)
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run AgentRun script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "AgentRun test did not create the .epi file.")
    result.add_artifact(artifact)
    kinds = [step["kind"] for step in read_steps(artifact)]
    target = [
        "agent.plan",
        "tool.call",
        "tool.response",
        "agent.approval.request",
        "agent.approval.response",
        "agent.decision",
    ]
    indices = [kinds.index(kind) for kind in target]
    require(indices == sorted(indices), "AgentRun step ordering is incorrect.")
    for kind in target:
        require(kind in kinds, f"Missing AgentRun step kind: {kind}")
    result.status = "PASS"
    result.add_note("All six expected AgentRun step kinds are present in the correct order.")
    result.save()
    return result


def test04_langchain() -> TestResult:
    result = activate(TestResult(4, "LangChain Integration"))
    artifact = ARTIFACTS / "test04_langchain.epi"
    script = write_script(
        "test04_langchain.py",
        f"""
        from pathlib import Path
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from epi_recorder import record
        from epi_recorder.integrations.langchain import EPICallbackHandler

        output = Path(r"{artifact}")
        handler = EPICallbackHandler()
        model = FakeListChatModel(responses=["Synthetic offline response"])

        with record(str(output), goal="LangChain callback test"):
            response = model.invoke("Hello from fake model", config={{"callbacks": [handler]}})
            print(getattr(response, "content", response))
        print(output)
        """,
    )
    result.add_script(script)
    run = run_command(result, "Run LangChain integration script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "LangChain test did not create the .epi file.")
    result.add_artifact(artifact)
    kinds = [step["kind"] for step in read_steps(artifact)]
    require("llm.request" in kinds, "LangChain test missing llm.request.")
    require("llm.response" in kinds, "LangChain test missing llm.response.")
    require("Error in EPICallbackHandler" not in run.stdout + run.stderr, "LangChain callback emitted an error banner.")
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "LangChain artifact failed verification.")
    result.status = "PASS"
    result.add_note("Callback captured llm.request and llm.response with no handler error text.")
    result.save()
    return result


def test05_wrap_openai() -> TestResult:
    result = activate(TestResult(5, "OpenAI Wrapper Offline"))
    script = write_script(
        "test05_wrap_openai.py",
        """
        from openai import OpenAI
        from epi_recorder import wrap_openai

        client = wrap_openai(OpenAI(api_key="fake"))
        print(type(client).__name__)
        print(hasattr(client, "chat"))
        """,
    )
    result.add_script(script)
    run = run_command(result, "Run wrap_openai script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(run.returncode == 0, "wrap_openai script failed.")
    require("TracedOpenAI" in run.stdout, "wrap_openai did not return the expected wrapped client type.")
    result.status = "PASS"
    result.add_note("wrap_openai returned a traced client object without making any API call.")
    result.save()
    return result


def test06_policy_init() -> TestResult:
    result = activate(TestResult(6, "Policy Init"))
    policy_path = ROOT / "epi_policy.json"
    if policy_path.exists():
        policy_path.unlink()
    run = run_command(
        result,
        "Run epi policy init",
        [str(EPI), "policy", "init", "--profile", "insurance.claim-denial", "--yes"],
        cwd=ROOT,
        timeout=120,
    )
    require(run.returncode == 0, "epi policy init failed.")
    require(policy_path.exists(), "epi_policy.json was not created.")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    types = {rule["type"] for rule in policy.get("rules", [])}
    require("threshold_guard" in types, "Policy init missing threshold_guard.")
    require("sequence_guard" in types, "Policy init missing sequence_guard.")
    require("prohibition_guard" in types, "Policy init missing prohibition_guard.")
    result.add_artifact(policy_path)
    result.status = "PASS"
    result.add_note("Insurance policy profile was created with the expected rule categories.")
    result.save()
    return result


def test07_policy_bad() -> TestResult:
    result = activate(TestResult(7, "Policy Violation Detection"))
    artifact = ARTIFACTS / "test07_policy_bad.epi"
    script = write_script(
        "test07_policy_bad.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), goal="Bad insurance denial"):
            from epi_recorder import get_current_session
            epi = get_current_session()
            epi.log_step("tool.call", {{"tool": "claim_lookup", "input": {{"claim_id": "CLM-BAD"}}}})
            epi.log_step("tool.response", {{"tool": "claim_lookup", "status": "success", "output": {{"claim_id": "CLM-BAD", "amount": 15000, "claim_amount": 15000}}}})
            epi.log_step("agent.decision", {{"decision": "deny_claim", "amount": 15000, "reason": "Immediate denial without checks"}})
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run bad policy script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Bad policy test did not create the .epi file.")
    result.add_artifact(artifact)
    require(member_exists(artifact, "policy_evaluation.json"), "Bad policy artifact missing policy_evaluation.json.")
    policy_eval = read_json_member(artifact, "policy_evaluation.json")
    failed = [item for item in policy_eval.get("results", []) if item.get("status") == "failed"]
    require(bool(failed), "Bad policy path did not fail any rules.")
    failed_names = [item["rule_name"] for item in failed]
    result.extra["failed_rules"] = failed_names
    result.add_note(f"Failed rules: {', '.join(failed_names)}")
    result.status = "PASS"
    result.save()
    return result


def test08_policy_good() -> TestResult:
    result = activate(TestResult(8, "Policy Compliance Good Path"))
    artifact = ARTIFACTS / "test08_policy_good.epi"
    script = write_script(
        "test08_policy_good.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), goal="Good insurance denial"):
            from epi_recorder import get_current_session
            epi = get_current_session()
            epi.log_step("tool.call", {{"tool": "claim_lookup", "input": {{"claim_id": "CLM-GOOD"}}}})
            epi.log_step("tool.response", {{"tool": "claim_lookup", "status": "success", "output": {{"claim_id": "CLM-GOOD", "amount": 15000, "claim_amount": 15000}}}})
            epi.log_step("tool.call", {{"tool": "run_fraud_check", "input": {{"claim_id": "CLM-GOOD"}}}})
            epi.log_step("tool.response", {{"tool": "run_fraud_check", "status": "success", "output": {{"risk_level": "low", "score": 0.01}}}})
            epi.log_step("tool.call", {{"tool": "check_coverage", "input": {{"claim_id": "CLM-GOOD"}}}})
            epi.log_step("tool.response", {{"tool": "check_coverage", "status": "success", "output": {{"coverage_status": "excluded"}}}})
            epi.log_step("agent.approval.response", {{"action": "deny_claim", "approved": True, "reviewer": "manager"}})
            epi.log_step("tool.call", {{"tool": "record_denial_reason", "input": {{"claim_id": "CLM-GOOD"}}}})
            epi.log_step("tool.response", {{"tool": "record_denial_reason", "status": "success", "output": {{"summary": "Coverage exclusion confirmed"}}}})
            epi.log_step("agent.decision", {{"decision": "deny_claim", "amount": 15000, "reason": "Coverage excluded"}})
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run good policy script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Good policy test did not create the .epi file.")
    result.add_artifact(artifact)
    require(member_exists(artifact, "policy_evaluation.json"), "Good policy artifact missing policy_evaluation.json.")
    policy_eval = read_json_member(artifact, "policy_evaluation.json")
    failed = [item for item in policy_eval.get("results", []) if item.get("status") == "failed"]
    require(not failed, "Good policy path still failed rules.")
    bad_policy = read_json_member(ARTIFACTS / "test07_policy_bad.epi", "policy_evaluation.json")
    require(policy_eval != bad_policy, "Good and bad policy evaluation outputs should differ.")
    result.status = "PASS"
    result.add_note("All policy rules passed and the evaluation differs from the bad path.")
    result.save()
    return result


def test09_tamper() -> TestResult:
    result = activate(TestResult(9, "Tamper Detection"))
    original = ARTIFACTS / "test01_basic.epi"
    tampered = ARTIFACTS / "test09_tampered_copy.epi"
    shutil.copy2(original, tampered)
    with zipfile.ZipFile(original, "r") as zin:
        payloads = {name: zin.read(name) for name in zin.namelist()}
    steps_text = payloads["steps.jsonl"].decode("utf-8").replace("approve_refund", "deny_refund", 1)
    payloads["steps.jsonl"] = steps_text.encode("utf-8")
    with zipfile.ZipFile(tampered, "w") as zout:
        for name, data in payloads.items():
            compression = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(name, data, compress_type=compression)
    result.add_artifact(original)
    result.add_artifact(tampered)
    verify_orig = verify_artifact(result, original, label="Verify original artifact")
    verify_tampered = verify_artifact(result, tampered, label="Verify tampered artifact")
    require(verify_orig.returncode == 0, "Original artifact should still verify successfully.")
    require(verify_tampered.returncode != 0, "Tampered artifact should fail verification.")
    result.extra["tamper_message"] = (verify_tampered.stdout + verify_tampered.stderr).strip()
    result.add_note("Tampered copy failed verification as expected.")
    result.status = "PASS"
    result.save()
    return result


def test10_viewer() -> TestResult:
    result = activate(TestResult(10, "Browser Viewer"))
    artifact = ARTIFACTS / "test07_policy_bad.epi"
    extract_dir = EXTRACTED / "test10_viewer"
    clean_dir(extract_dir)
    view_run = run_command(result, "Run epi view", [str(EPI), "view", str(artifact)], cwd=ROOT, timeout=120)
    extract_run = run_command(
        result,
        "Run epi view --extract",
        [str(EPI), "view", "--extract", str(extract_dir), str(artifact)],
        cwd=ROOT,
        timeout=120,
    )
    require(extract_run.returncode == 0, "epi view --extract failed.")
    viewer_html = extract_dir / "viewer.html"
    require(viewer_html.exists(), "viewer.html was not extracted.")
    html = viewer_html.read_text(encoding="utf-8")
    require("Decision Summary" in html or "Decision" in html, "viewer.html is missing decision-summary text.")
    require(
        "policy_evaluation" in html or "Policy Compliance" in html or "policy evaluation" in html.lower(),
        "viewer.html is missing policy evaluation data.",
    )
    has_external = "https://" in html or "http://" in html
    result.extra["browser_launch_observable"] = any(
        marker in view_run.stdout for marker in ("Opened:", "Browser opened", "http://127.0.0.1")
    )
    result.extra["external_dependencies_found"] = has_external
    if has_external:
        result.add_note("viewer.html includes external dependencies.")
    else:
        result.add_note("viewer.html appears self-contained.")
    require(not has_external, "viewer.html contains external dependencies.")
    result.add_artifact(viewer_html)
    result.status = "PASS"
    result.save()
    return result


def test11_export_summary() -> TestResult:
    result = activate(TestResult(11, "Decision Record Export"))
    artifact = ARTIFACTS / "test07_policy_bad.epi"
    default_output = artifact.parent / f"{artifact.stem}_summary.html"
    if default_output.exists():
        default_output.unlink()
    run = run_command(result, "Run epi export-summary summary", [str(EPI), "export-summary", "summary", str(artifact)], cwd=ROOT, timeout=120)
    require(run.returncode == 0, "epi export-summary summary failed.")
    html_path = default_output if default_output.exists() else newest_html(artifact.parent)
    require(html_path is not None and html_path.exists(), "Could not locate exported Decision Record HTML.")
    html = html_path.read_text(encoding="utf-8")
    require("EPI Decision Record" in html, "Decision Record title is missing.")
    require(
        "Policy Compliance" in html or "Policy violations" in html or "Policy Compliance Summary" in html,
        "Policy section is missing from exported HTML.",
    )
    require("Trust" in html or "Verification" in html, "Trust/verification status is missing from exported HTML.")
    require("@media print" in html or "print" in html.lower(), "Exported HTML does not appear print-oriented.")
    result.add_artifact(html_path)
    result.status = "PASS"
    result.add_note("Decision Record HTML contains workflow context, policy section, trust text, and print-oriented markup.")
    result.save()
    return result


def test12_artifact_attachment() -> TestResult:
    result = activate(TestResult(12, "Artifact Attachment"))
    artifact = ARTIFACTS / "test12_attachment.epi"
    attachment = ARTIFACTS / "test12_attachment.txt"
    attachment.write_text("attached evidence\n", encoding="utf-8")
    script = write_script(
        "test12_attachment.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        attachment = Path(r"{attachment}")
        with record(str(output), goal="Attachment test") as epi:
            epi.log_artifact(attachment)
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run artifact attachment script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Attachment test did not create the .epi file.")
    result.add_artifact(artifact)
    require(member_exists(artifact, "artifacts/test12_attachment.txt"), "Attached file missing from artifacts/ in ZIP.")
    manifest = read_json_member(artifact, "manifest.json")
    require("artifacts/test12_attachment.txt" in manifest.get("file_manifest", {}), "Attached file missing from manifest file_manifest.")
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "Artifact with attachment failed verification.")
    result.status = "PASS"
    result.add_note("Attachment is present in the archive, listed in manifest file_manifest, and verifies cleanly.")
    result.save()
    return result


def test13_multiple_recordings() -> TestResult:
    result = activate(TestResult(13, "Multiple Recordings"))
    paths = [ARTIFACTS / f"test13_multi_{idx}.epi" for idx in range(1, 4)]
    script = write_script(
        "test13_multiple.py",
        f"""
        from epi_recorder import record

        outputs = {[str(p) for p in paths]!r}
        for idx, output in enumerate(outputs, start=1):
            with record(output, goal=f"Multiple recording {{idx}}") as epi:
                epi.log_step("agent.decision", {{"decision": f"record_{{idx}}"}})
        print("\\n".join(outputs))
        """,
    )
    result.add_script(script)
    run_command(result, "Run multiple recordings script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    workflow_ids: list[str] = []
    for path in paths:
        require(path.exists(), f"Missing multi-recording artifact: {path.name}")
        result.add_artifact(path)
        workflow_ids.append(read_json_member(path, "manifest.json").get("workflow_id"))
        verify = verify_artifact(result, path, label=f"Verify {path.name}")
        require(verify.returncode == 0, f"{path.name} failed verification.")
    require(len(set(workflow_ids)) == 3, "Workflow IDs are not unique across the three artifacts.")
    result.status = "PASS"
    result.add_note("Three independent artifacts were created with unique workflow IDs and all passed verification.")
    result.save()
    return result


def test14_error_handling() -> TestResult:
    result = activate(TestResult(14, "Error Handling"))
    artifact = ARTIFACTS / "test14_error.epi"
    script = write_script(
        "test14_error.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        try:
            with record(str(output), goal="Error handling test") as epi:
                epi.log_step("tool.call", {{"tool": "partial_work"}})
                raise RuntimeError("planned failure")
        except RuntimeError as exc:
            print(f"caught: {{exc}}")
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run error handling script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Error-handling test did not create the .epi file.")
    result.add_artifact(artifact)
    error_steps = [step for step in read_steps(artifact) if step["kind"] == "session.error"]
    require(len(error_steps) == 1, "session.error step was not captured.")
    require(error_steps[0]["content"].get("error_type") == "RuntimeError", "session.error type is incorrect.")
    require("planned failure" in error_steps[0]["content"].get("error_message", ""), "session.error message is incorrect.")
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "Error-handling artifact failed verification.")
    result.status = "PASS"
    result.add_note("session.error was captured and the artifact still verifies successfully.")
    result.save()
    return result


def test15_cli_help() -> TestResult:
    result = activate(TestResult(15, "CLI Help Commands"))
    commands = [
        ["--help"],
        ["verify", "--help"],
        ["view", "--help"],
        ["policy", "--help"],
        ["export-summary", "--help"],
        ["demo", "--help"],
    ]
    for args in commands:
        run = run_command(result, f"Run {' '.join(args)}", [str(EPI), *args], cwd=ROOT, timeout=120)
        require(run.returncode == 0, f"{' '.join(args)} failed.")
        require(run.stdout.strip() or run.stderr.strip(), f"{' '.join(args)} did not print help text.")
    result.status = "PASS"
    result.add_note("All requested CLI help commands printed help text without errors.")
    result.save()
    return result


def test16_environment() -> TestResult:
    result = activate(TestResult(16, "Environment Capture"))
    artifact = ARTIFACTS / "test16_environment.epi"
    script = write_script(
        "test16_environment.py",
        f"""
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")
        with record(str(output), goal="Environment capture test"):
            pass
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run environment capture script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Environment test did not create the .epi file.")
    result.add_artifact(artifact)
    env_json = read_json_member(artifact, "environment.json")
    require(isinstance(env_json.get("os"), dict), "environment.json missing nested os info.")
    require(isinstance(env_json.get("python"), dict), "environment.json missing nested python info.")
    require(isinstance(env_json.get("packages"), dict), "environment.json missing package list.")
    require("version" in env_json["python"], "environment.json missing python version.")
    package_names = {name.lower() for name in env_json["packages"].keys()}
    require("epi-recorder" in package_names or "epi_recorder" in package_names, "environment.json does not list epi-recorder.")
    result.status = "PASS"
    result.add_note("environment.json contains nested os/python metadata and installed packages including epi-recorder.")
    result.save()
    return result


def test17_async_recording() -> TestResult:
    result = activate(TestResult(17, "Async Recording"))
    artifact = ARTIFACTS / "test17_async.epi"
    script = write_script(
        "test17_async.py",
        f"""
        import asyncio
        from pathlib import Path
        from epi_recorder import record

        output = Path(r"{artifact}")

        async def main():
            async with record(str(output), goal="Async recording test") as epi:
                await epi.alog_step("tool.call", {{"tool": "lookup_async", "input": {{"id": "1"}}}})
                await epi.alog_step("tool.response", {{"tool": "lookup_async", "status": "success", "output": {{"id": "1"}}}})
                await epi.alog_step("agent.decision", {{"decision": "finish_async"}})

        asyncio.run(main())
        print(output)
        """,
    )
    result.add_script(script)
    run_command(result, "Run async recording script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(artifact.exists(), "Async recording test did not create the .epi file.")
    result.add_artifact(artifact)
    kinds = [step["kind"] for step in read_steps(artifact)]
    for kind in ("tool.call", "tool.response", "agent.decision"):
        require(kind in kinds, f"Async artifact missing {kind}.")
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "Async artifact failed verification.")
    result.status = "PASS"
    result.add_note("Async recording captured alog_step events and passed verification.")
    result.save()
    return result


def test18_pytest_plugin() -> TestResult:
    result = activate(TestResult(18, "Pytest Plugin"))
    test_file = write_script(
        "test18_pytest_file.py",
        """
        def test_pass_case():
            assert 1 == 1

        def test_fail_case():
            assert 1 == 2
        """,
    )
    result.add_script(test_file)
    clean_dir(EVIDENCE_FAIL_ONLY)
    clean_dir(EVIDENCE_ALL)
    run_fail_only = run_command(
        result,
        "Run pytest --epi",
        [str(PYTEST), "--epi", "--epi-dir", str(EVIDENCE_FAIL_ONLY), str(test_file)],
        cwd=ROOT,
        timeout=180,
    )
    fail_only_artifacts = sorted(EVIDENCE_FAIL_ONLY.glob("*.epi"))
    require(run_fail_only.returncode != 0, "First pytest run should fail because one test fails.")
    require(len(fail_only_artifacts) == 1, "Fail-only pytest run should keep exactly one artifact.")
    require("fail" in fail_only_artifacts[0].name.lower(), "Fail-only artifact does not appear to come from the failing test.")
    result.add_artifact(fail_only_artifacts[0])
    verify_fail_only = verify_artifact(result, fail_only_artifacts[0], label="Verify failing-test artifact")
    require(verify_fail_only.returncode == 0, "Fail-only pytest artifact failed verification.")

    run_all = run_command(
        result,
        "Run pytest --epi --epi-on-pass",
        [str(PYTEST), "--epi", "--epi-on-pass", "--epi-dir", str(EVIDENCE_ALL), str(test_file)],
        cwd=ROOT,
        timeout=180,
    )
    all_artifacts = sorted(EVIDENCE_ALL.glob("*.epi"))
    require(run_all.returncode != 0, "Second pytest run should still fail because one test fails.")
    require(len(all_artifacts) == 2, "Pass+fail pytest run should keep exactly two artifacts.")
    for artifact in all_artifacts:
        result.add_artifact(artifact)
        verify = verify_artifact(result, artifact, label=f"Verify {artifact.name}")
        require(verify.returncode == 0, f"Pytest artifact {artifact.name} failed verification.")
    result.status = "PASS"
    result.add_note("pytest --epi kept only the failing artifact by default, and --epi-on-pass kept both artifacts.")
    result.save()
    return result


def test19_demo() -> TestResult:
    result = activate(TestResult(19, "epi demo Front Door"))
    result.report_dir.mkdir(parents=True, exist_ok=True)
    demo_artifact = ROOT / "epi-recordings" / "demo_refund.epi"
    if demo_artifact.exists():
        demo_artifact.unlink()
    env = base_env()
    env["PYTHONUNBUFFERED"] = "1"
    start = time.time()
    stdout_path = result.report_dir / "live_stdout.txt"
    stderr_path = result.report_dir / "live_stderr.txt"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(EPI), "demo"],
        cwd=ROOT,
        env=env,
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    ready_patterns = ("Demo ready", "Local review workspace ready", "Browser opened", "http://127.0.0.1")
    ready = False
    try:
        while time.time() - start < 180:
            stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
            combined = stdout_text + stderr_text
            if any(pattern in combined for pattern in ready_patterns):
                ready = True
            if demo_artifact.exists() and ready:
                break
            if proc.poll() is not None:
                break
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.wait(timeout=20)
            except Exception:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
                    proc.wait(timeout=10)
        stdout_file.close()
        stderr_file.close()
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    result.commands.append(
        CommandRun(
            label="Run epi demo",
            command=[str(EPI), "demo"],
            cwd=ROOT,
            returncode=proc.returncode if proc.returncode is not None else -999,
            stdout=stdout_text,
            stderr=stderr_text,
            timeout=180,
        )
    )
    require(ready, "epi demo did not reach ready state.")
    require(demo_artifact.exists(), "epi demo did not produce demo_refund.epi.")
    output_text = stdout_text + stderr_text
    require(
        "http://127.0.0.1" in output_text or "Browser opened" in output_text or "Opened" in output_text,
        "epi demo did not print local review/browser information.",
    )
    result.add_artifact(demo_artifact)
    verify = verify_artifact(result, demo_artifact, label="Verify demo artifact")
    require(verify.returncode == 0, "Demo artifact failed verification.")
    result.status = "PASS"
    result.add_note("epi demo reached ready state, produced demo_refund.epi, printed local review info, and the artifact verified successfully.")
    result.save()
    return result


def test20_review_append() -> TestResult:
    result = activate(TestResult(20, "Review Append"))
    artifact = ARTIFACTS / "test07_policy_bad.epi"
    before_steps = read_member_bytes(artifact, "steps.jsonl")
    script = write_script(
        "test20_review_append.py",
        f"""
        import json
        import zipfile
        from pathlib import Path
        from epi_core.review import ReviewRecord, add_review_to_artifact, make_review_entry

        artifact = Path(r"{artifact}")
        with zipfile.ZipFile(artifact, "r") as zf:
            analysis = json.loads(zf.read("analysis.json").decode("utf-8"))
        fault = analysis.get("primary_fault")
        if not fault:
            raise RuntimeError("No primary_fault found in analysis.json")
        entry = make_review_entry(
            fault=fault,
            outcome="confirmed_fault",
            notes="Reviewed externally during PyPI validation.",
            reviewer="validator@example.com",
        )
        record = ReviewRecord(reviewed_by="validator@example.com", reviews=[entry])
        add_review_to_artifact(artifact, record)
        print(artifact)
        """,
    )
    result.add_script(script)
    run_command(result, "Run review append script", [str(PYTHON), "-I", str(script)], cwd=ROOT, timeout=120)
    require(member_exists(artifact, "review.json"), "review.json was not appended.")
    after_steps = read_member_bytes(artifact, "steps.jsonl")
    require(hash_bytes(before_steps) == hash_bytes(after_steps), "steps.jsonl changed after review append.")
    verify = verify_artifact(result, artifact)
    require(verify.returncode == 0, "Artifact failed verification after review append.")
    result.add_artifact(artifact)
    result.status = "PASS"
    result.add_note("review.json was appended, verification still passes, and steps.jsonl remained byte-for-byte unchanged.")
    result.save()
    return result


TESTS = [
    test01_basic,
    test02_metadata,
    test03_agent_run,
    test04_langchain,
    test05_wrap_openai,
    test06_policy_init,
    test07_policy_bad,
    test08_policy_good,
    test09_tamper,
    test10_viewer,
    test11_export_summary,
    test12_artifact_attachment,
    test13_multiple_recordings,
    test14_error_handling,
    test15_cli_help,
    test16_environment,
    test17_async_recording,
    test18_pytest_plugin,
    test19_demo,
    test20_review_append,
]


def analyze_failure(test: TestResult) -> None:
    text = "\n".join(test.notes + [run.stdout + "\n" + run.stderr for run in test.commands]).lower()
    if "browser" in text and ("could not open" in text or "startfile" in text):
        classification = "environment limitation"
    elif "timeout" in text or "timed out" in text:
        classification = "environment limitation"
    else:
        classification = "product bug"
    test.extra["failure_classification"] = classification


def write_summary(results: list[TestResult], elapsed_minutes: float, probe_payload: dict[str, Any]) -> None:
    summary = {
        "root": str(ROOT),
        "probe": probe_payload,
        "elapsed_minutes": elapsed_minutes,
        "results": [
            {
                "number": test.number,
                "name": test.name,
                "status": test.status,
                "notes": test.notes,
                "artifacts": test.artifacts,
                "extra": test.extra,
            }
            for test in results
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# epi-recorder 3.0.1 External PyPI Validation",
        "",
        f"Workspace: `{ROOT}`",
        f"Elapsed minutes: `{elapsed_minutes:.2f}`",
        "",
        "## Isolation Probe",
        "",
        "```json",
        json.dumps(probe_payload, indent=2),
        "```",
        "",
        "## Scorecard",
        "",
        "| # | Test Name | Pass/Fail | Notes |",
        "|---|-----------|-----------|-------|",
    ]
    for test in results:
        note = (test.notes[0] if test.notes else "").replace("\n", " ")
        lines.append(f"| {test.number} | {test.name} | {test.status} | {note} |")
    passed = sum(1 for test in results if test.status == "PASS")
    lines.extend(["", "## Totals", "", f"- Passed: {passed} / {len(results)}", f"- Failed: {len(results) - passed}"])
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    global CURRENT_RESULT
    parser = argparse.ArgumentParser(description="Run external PyPI validation for epi-recorder.")
    parser.add_argument("--start", type=int, default=1, help="First test number to run.")
    parser.add_argument("--end", type=int, default=len(TESTS), help="Last test number to run.")
    args = parser.parse_args()
    ensure_dirs()
    start = time.time()
    probe_payload = isolation_probe()
    probe_path = str(probe_payload["epi_recorder_file"]).lower()
    require("site-packages" in probe_path, "Isolation probe resolved epi_recorder outside site-packages.")
    require("c:\\users\\dell\\epi-recorder" not in probe_path, "Isolation probe resolved epi_recorder to the repo source.")
    results: list[TestResult] = []
    selected_tests = [test_func for test_func in TESTS if args.start <= int(re.search(r"test(\d+)", test_func.__name__).group(1)) <= args.end]
    require(bool(selected_tests), f"No tests selected for range {args.start}..{args.end}.")
    for test_func in selected_tests:
        CURRENT_RESULT = None
        try:
            result = test_func()
        except Exception as exc:
            match = re.search(r"test(\d+)", test_func.__name__)
            number = int(match.group(1)) if match else -1
            name = test_func.__name__.replace("test", "").strip("_")
            result = CURRENT_RESULT or TestResult(number, name)
            result.add_note(f"Test raised {type(exc).__name__}: {exc}")
            result.status = "FAIL"
        if result.status != "PASS":
            analyze_failure(result)
            result.save()
        results.append(result)
    elapsed_minutes = (time.time() - start) / 60.0
    write_summary(results, elapsed_minutes, probe_payload)
    print(SUMMARY_MD)
    print(SUMMARY_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
