from __future__ import annotations

from pathlib import Path

import pytest

from epi_core.container import EPIContainer
from epi_recorder.integrations.litellm import disable_epi, enable_epi
from tests.helpers.artifacts import make_decision_epi


pytestmark = pytest.mark.framework


def test_real_langchain_runnable_emits_chain_callbacks_when_installed(monkeypatch):
    runnables = pytest.importorskip("langchain_core.runnables")
    from epi_recorder.integrations.langchain import EPICallbackHandler

    class Session:
        def __init__(self):
            self.logged: list[tuple[str, dict]] = []

        def log_step(self, kind: str, payload: dict) -> None:
            self.logged.append((kind, payload))

    session = Session()
    handler = EPICallbackHandler()
    monkeypatch.setattr(handler, "_get_session", lambda: session)

    chain = runnables.RunnableLambda(lambda payload: {"answer": payload["question"].upper()})
    assert chain.invoke({"question": "refund"}, config={"callbacks": [handler]}) == {
        "answer": "REFUND"
    }

    kinds = [kind for kind, _ in session.logged]
    assert "chain.start" in kinds
    assert "chain.end" in kinds


def test_real_litellm_callback_registration_when_installed():
    litellm = pytest.importorskip("litellm")
    original = {
        "callbacks": getattr(litellm, "callbacks", None),
        "success_callback": getattr(litellm, "success_callback", None),
        "failure_callback": getattr(litellm, "failure_callback", None),
    }
    try:
        callback = enable_epi()
        registered = getattr(litellm, "callbacks", None) or getattr(litellm, "success_callback", None)
        assert any(item is callback for item in (registered or []))
    finally:
        disable_epi()
        for attr, value in original.items():
            if value is not None:
                setattr(litellm, attr, value)


def test_real_opentelemetry_trace_exports_epi_when_installed(tmp_path: Path):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from epi_recorder.integrations.opentelemetry import EPISpanExporter

    exporter = EPISpanExporter(output_dir=str(tmp_path), auto_sign=False, flush_interval=60)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("epi-framework-test")

    try:
        with tracer.start_as_current_span("llm.offline") as span:
            span.set_attribute("gen_ai.request.model", "offline-model")
            span.set_attribute("gen_ai.system", "local")
        assert exporter.force_flush()
    finally:
        exporter.shutdown()

    artifacts = list(tmp_path.glob("otel_*.epi"))
    assert len(artifacts) == 1
    assert EPIContainer.count_steps(artifacts[0]) == 1


def test_agt_import_is_first_class_framework_bridge(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=False)

    assert EPIContainer.verify_integrity(artifact)[0] is True
    assert EPIContainer.count_steps(artifact) >= 5


def test_crewai_optional_generic_capture_smoke(tmp_path: Path):
    pytest.importorskip("crewai")
    artifact, _ = make_decision_epi(tmp_path, name="crewai-generic.epi", signed=False)
    assert EPIContainer.verify_integrity(artifact)[0] is True


def test_autogen_optional_generic_capture_smoke(tmp_path: Path):
    pytest.importorskip("autogen")
    artifact, _ = make_decision_epi(tmp_path, name="autogen-generic.epi", signed=False)
    assert EPIContainer.verify_integrity(artifact)[0] is True
