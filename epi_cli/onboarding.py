"""Shared onboarding helpers for init and integrate commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GITHUB_WORKFLOW_PATH = Path(".github") / "workflows" / "epi-audit.yml"


@dataclass(frozen=True)
class WriteResult:
    path: Path
    created: bool
    skipped: bool
    reason: str = ""


def detect_pytest_project(root: Path | None = None) -> bool:
    root = root or Path.cwd()
    if (root / "pytest.ini").exists() or (root / "tests").is_dir():
        return True
    for candidate in (root / "pyproject.toml", root / "requirements.txt", root / "requirements-dev.txt"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore").lower()
        except FileNotFoundError:
            continue
        if "pytest" in text:
            return True
    return False


def github_action_workflow(*, pytest_detected: bool = True) -> str:
    if pytest_detected:
        test_step = """      - name: Install project and test dependencies
        run: |
          python -m pip install -U pip
          if [ -f pyproject.toml ]; then
            python -m pip install -e ".[dev]" || python -m pip install -e .
          elif [ -f requirements.txt ]; then
            python -m pip install -r requirements.txt
          fi
          python -m pip install epi-recorder pytest

      - name: Run tests with EPI evidence
        run: pytest --epi --epi-dir=evidence

      - name: Upload EPI evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: epi-evidence
          path: evidence/
          if-no-files-found: ignore
"""
        path = "./evidence"
    else:
        test_step = """      - name: Install EPI Recorder
        run: |
          python -m pip install -U pip
          python -m pip install epi-recorder

      - name: Create recordings directory
        run: mkdir -p epi-recordings
"""
        path = "./epi-recordings"

    return f"""name: EPI Evidence

on:
  push:
  pull_request:

jobs:
  epi-evidence:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

{test_step}
      - name: Verify EPI evidence
        uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main
        with:
          path: {path}
          fail-on-tampered: true
          fail-on-unsigned: false
"""


def write_github_action_workflow(*, root: Path | None = None, force: bool = False) -> WriteResult:
    root = root or Path.cwd()
    workflow_path = root / GITHUB_WORKFLOW_PATH
    if workflow_path.exists() and not force:
        return WriteResult(workflow_path, created=False, skipped=True, reason="exists")
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        github_action_workflow(pytest_detected=detect_pytest_project(root)),
        encoding="utf-8",
    )
    return WriteResult(workflow_path, created=True, skipped=False)


def integration_example(target: str) -> tuple[str, str]:
    target = target.strip().lower()
    if target == "pytest":
        return (
            "pytest-ci.md",
            """# EPI + pytest

Run tests with portable evidence:

```bash
pytest --epi --epi-dir=evidence
epi verify evidence
```
""",
        )
    if target == "langchain":
        return (
            "langchain_epi_example.py",
            '''from langchain_openai import ChatOpenAI
from epi_recorder import record
from epi_recorder.integrations import EPICallbackHandler

with record("epi-recordings/langchain-run.epi", goal="Capture one LangChain run"):
    llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[EPICallbackHandler()])
    result = llm.invoke("Summarize this run in one sentence.")
    print(result.content)
''',
        )
    if target == "litellm":
        return (
            "litellm_epi_example.py",
            '''import litellm
from epi_recorder import record
from epi_recorder.integrations.litellm import enable_epi

enable_epi()

with record("epi-recordings/litellm-run.epi", goal="Capture one LiteLLM run"):
    response = litellm.completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Summarize this run in one sentence."}],
    )
    print(response.choices[0].message.content)
''',
        )
    if target == "opentelemetry":
        return (
            "opentelemetry_epi_example.py",
            '''from opentelemetry import trace
from epi_recorder.integrations.opentelemetry import setup_epi_tracing

exporter = setup_epi_tracing(output_dir="./epi-recordings", service_name="my-agent")
tracer = trace.get_tracer("my-agent")

with tracer.start_as_current_span("agent-run"):
    pass

exporter.shutdown()
''',
        )
    if target == "agt":
        return (
            "agt_epi_import.md",
            """# AGT -> EPI

Package exported AGT evidence as a portable `.epi` artifact:

```bash
epi import agt path/to/agt/evidence-dir --out agt-case.epi
epi verify agt-case.epi
epi view agt-case.epi
```
""",
        )
    raise ValueError(f"unsupported integration target: {target}")


def write_integration_example(target: str, *, root: Path | None = None, force: bool = False) -> WriteResult:
    root = root or Path.cwd()
    filename, content = integration_example(target)
    output_path = root / ".epi" / "examples" / filename
    if output_path.exists() and not force:
        return WriteResult(output_path, created=False, skipped=True, reason="exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return WriteResult(output_path, created=True, skipped=False)
