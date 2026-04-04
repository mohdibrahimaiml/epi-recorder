"""
OpenTelemetry Exporter for EPI Recorder.

Bridges OpenTelemetry traces into cryptographically signed .epi files.
This positions EPI as a verification layer on top of the industry-standard
tracing infrastructure.

Architecture:
    OpenTelemetry SDK → EPISpanExporter → .epi file (signed, tamper-evident)

    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  Your Code   │────>│  OTel SDK    │────>│  EPI Exporter│──> .epi
    │  (any lang)  │     │  (spans)     │     │  (signed)    │
    └──────────────┘     └──────────────┘     └──────────────┘

This is the strategic long-term layer: it makes EPI work with ANY
language, ANY framework, and ANY cloud provider that supports
OpenTelemetry — which is all of them.

Usage:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from epi_recorder.integrations.opentelemetry import EPISpanExporter

    # Setup
    exporter = EPISpanExporter(output_dir="./epi-recordings")
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Use - all spans automatically become signed .epi evidence
    tracer = trace.get_tracer("my-agent")
    with tracer.start_as_current_span("agent-run") as span:
        # Your LLM calls, tool calls, etc.
        span.set_attribute("llm.model", "gpt-4")
        span.set_attribute("llm.provider", "openai")
        ...

    # One-liner setup:
    from epi_recorder.integrations.opentelemetry import setup_epi_tracing
    setup_epi_tracing()  # All OTel spans now export to .epi files

Requirements:
    pip install opentelemetry-api opentelemetry-sdk
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ---- OpenTelemetry Type Stubs (for when OTel is not installed) ----

try:
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.trace import StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

    class SpanExporter:
        """Stub for when OpenTelemetry is not installed."""
        pass

    class SpanExportResult:
        SUCCESS = 0
        FAILURE = 1

    class ReadableSpan:
        pass

    class StatusCode:
        UNSET = 0
        OK = 1
        ERROR = 2


class EPISpanExporter(SpanExporter):
    """
    OpenTelemetry SpanExporter that writes spans to .epi files.

    Each trace (group of spans sharing a trace_id) becomes a separate
    .epi file with cryptographic signatures and tamper-evident properties.

    Features:
    - Groups spans by trace_id into separate .epi files
    - Converts OTel span attributes to EPI step format
    - Auto-signs with default EPI key
    - Handles LLM-specific semantic conventions
    - Configurable batching and flush intervals

    Args:
        output_dir: Directory for .epi output files
        auto_sign: Whether to sign .epi files (default: True)
        flush_interval: Seconds between automatic flushes (default: 30)
        prefix: Filename prefix for .epi files (default: "otel")
    """

    def __init__(
        self,
        output_dir: str = "./epi-recordings",
        auto_sign: bool = True,
        flush_interval: float = 30.0,
        prefix: str = "otel",
    ):
        if not OTEL_AVAILABLE:
            raise ImportError(
                "OpenTelemetry is not installed. Install with: "
                "pip install opentelemetry-api opentelemetry-sdk"
            )

        super().__init__()
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._auto_sign = auto_sign
        self._flush_interval = flush_interval
        self._prefix = prefix

        # Buffer: trace_id -> list of span dicts
        self._traces: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()

        # Track last flush per trace
        self._trace_last_activity: Dict[str, float] = {}

        # Background flusher thread
        self._shutdown = threading.Event()
        self._flusher = threading.Thread(
            target=self._flush_loop, daemon=True, name="epi-otel-flusher"
        )
        self._flusher.start()

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        """
        Export a batch of spans to the EPI buffer.

        Spans are grouped by trace_id. When a trace completes
        (or the flush interval passes), spans are written to .epi.
        """
        try:
            with self._lock:
                for span in spans:
                    trace_id = self._format_trace_id(span)
                    step = self._span_to_step(span)

                    if trace_id not in self._traces:
                        self._traces[trace_id] = []
                    self._traces[trace_id].append(step)
                    self._trace_last_activity[trace_id] = time.time()

            return SpanExportResult.SUCCESS
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Flush all remaining spans and shut down."""
        self._shutdown.set()
        self._flusher.join(timeout=10)
        # Final flush
        self._flush_all()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force-flush all buffered spans to .epi files."""
        try:
            self._flush_all()
            return True
        except Exception:
            return False

    # ---- Internal Methods ----

    def _format_trace_id(self, span: Any) -> str:
        """Extract trace_id as hex string."""
        ctx = span.context
        return format(ctx.trace_id, '032x')

    def _format_span_id(self, span: Any) -> str:
        """Extract span_id as hex string."""
        ctx = span.context
        return format(ctx.span_id, '016x')

    def _span_to_step(self, span: Any) -> Dict:
        """Convert an OpenTelemetry span to an EPI step dict."""
        # Determine step kind from span attributes and name
        kind = self._infer_step_kind(span)

        # Build content
        content = {
            "span_name": span.name,
            "trace_id": self._format_trace_id(span),
            "span_id": self._format_span_id(span),
            "parent_span_id": format(span.parent.span_id, '016x') if span.parent else None,
            "start_time": self._format_time(span.start_time),
            "end_time": self._format_time(span.end_time),
            "duration_ms": self._duration_ms(span.start_time, span.end_time),
            "status": self._format_status(span.status),
        }

        # Add all attributes
        if span.attributes:
            attrs = dict(span.attributes)
            content["attributes"] = self._serialize_attributes(attrs)

            # Extract known LLM attributes for EPI compatibility
            if "llm.model" in attrs or "gen_ai.request.model" in attrs:
                content["model"] = attrs.get("llm.model") or attrs.get("gen_ai.request.model")
            if "llm.provider" in attrs or "gen_ai.system" in attrs:
                content["provider"] = attrs.get("llm.provider") or attrs.get("gen_ai.system")
            if "llm.usage.prompt_tokens" in attrs or "gen_ai.usage.input_tokens" in attrs:
                content["usage"] = {
                    "prompt_tokens": attrs.get("llm.usage.prompt_tokens") or attrs.get("gen_ai.usage.input_tokens", 0),
                    "completion_tokens": attrs.get("llm.usage.completion_tokens") or attrs.get("gen_ai.usage.output_tokens", 0),
                    "total_tokens": attrs.get("llm.usage.total_tokens", 0),
                }

        # Add events (logs within the span)
        if span.events:
            content["events"] = [
                {
                    "name": event.name,
                    "timestamp": self._format_time(event.timestamp),
                    "attributes": self._serialize_attributes(dict(event.attributes)) if event.attributes else {},
                }
                for event in span.events
            ]

        # Add links
        if span.links:
            content["links"] = [
                {
                    "trace_id": format(link.context.trace_id, '032x'),
                    "span_id": format(link.context.span_id, '016x'),
                    "attributes": self._serialize_attributes(dict(link.attributes)) if link.attributes else {},
                }
                for link in span.links
            ]

        return {
            "kind": kind,
            "content": content,
            "timestamp": self._format_time(span.start_time),
        }

    def _infer_step_kind(self, span: Any) -> str:
        """Infer the EPI step kind from span attributes."""
        name = span.name.lower()
        attrs = dict(span.attributes) if span.attributes else {}

        # LLM semantic conventions
        if any(k.startswith(("llm.", "gen_ai.")) for k in attrs):
            if span.status and span.status.status_code == StatusCode.ERROR:
                return "llm.error"
            return "llm.response"

        # Tool/function calls
        if "tool" in name or "function" in name:
            if span.status and span.status.status_code == StatusCode.ERROR:
                return "tool.error"
            return "tool.end"

        # HTTP calls
        if any(k.startswith("http.") for k in attrs):
            return "http.response"

        # Database
        if any(k.startswith("db.") for k in attrs):
            return "db.query"

        # Generic
        if span.status and span.status.status_code == StatusCode.ERROR:
            return "span.error"

        return "span.end"

    def _format_time(self, ns_timestamp: Optional[int]) -> str:
        """Convert nanosecond timestamp to ISO format."""
        if ns_timestamp is None:
            return datetime.now(timezone.utc).isoformat()
        dt = datetime.fromtimestamp(ns_timestamp / 1e9, tz=timezone.utc)
        return dt.isoformat()

    def _duration_ms(self, start: Optional[int], end: Optional[int]) -> Optional[float]:
        """Calculate duration in milliseconds."""
        if start is None or end is None:
            return None
        return round((end - start) / 1e6, 2)

    def _format_status(self, status: Any) -> Dict:
        """Format span status."""
        if status is None:
            return {"code": "UNSET"}
        code_name = "UNSET"
        if hasattr(status, "status_code"):
            if status.status_code == StatusCode.OK:
                code_name = "OK"
            elif status.status_code == StatusCode.ERROR:
                code_name = "ERROR"
        return {
            "code": code_name,
            "description": getattr(status, "description", None),
        }

    def _serialize_attributes(self, attrs: Dict) -> Dict:
        """Serialize attributes to JSON-safe format."""
        result = {}
        for k, v in attrs.items():
            if isinstance(v, (str, int, float, bool)):
                result[k] = v
            elif isinstance(v, (list, tuple)):
                result[k] = [str(item) for item in v]
            else:
                result[k] = str(v)
        return result

    def _flush_loop(self):
        """Background loop that flushes completed traces."""
        while not self._shutdown.is_set():
            self._shutdown.wait(timeout=self._flush_interval / 2)
            self._flush_stale()

    def _flush_stale(self):
        """Flush traces that haven't received new spans recently."""
        now = time.time()
        stale_traces = []

        with self._lock:
            for trace_id, last_activity in list(self._trace_last_activity.items()):
                if now - last_activity > self._flush_interval:
                    stale_traces.append(trace_id)

        for trace_id in stale_traces:
            self._flush_trace(trace_id)

    def _flush_all(self):
        """Flush all buffered traces."""
        with self._lock:
            trace_ids = list(self._traces.keys())

        for trace_id in trace_ids:
            self._flush_trace(trace_id)

    def _flush_trace(self, trace_id: str):
        """Write a single trace to a .epi file."""
        with self._lock:
            steps = self._traces.pop(trace_id, [])
            self._trace_last_activity.pop(trace_id, None)

        if not steps:
            return

        try:
            from epi_recorder.api import EpiRecorderSession

            # Generate filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            short_id = trace_id[:8]
            filename = f"{self._prefix}_{short_id}_{timestamp}.epi"
            output_path = self._output_dir / filename

            # Write via EPI session
            session = EpiRecorderSession(
                output_path=str(output_path),
                workflow_name=f"otel-trace-{short_id}",
                tags=["opentelemetry", "trace"],
                auto_sign=self._auto_sign,
                goal=f"OpenTelemetry trace {trace_id}",
            )

            session.__enter__()

            # Log each span as an EPI step
            for step in sorted(steps, key=lambda s: s.get("timestamp", "")):
                session.log_step(step["kind"], step["content"])

            session.__exit__(None, None, None)

        except Exception as e:
            # Log but don't crash  
            import sys
            print(f"[EPI] Failed to flush trace {trace_id}: {e}", file=sys.stderr)


# ---- Convenience Functions ----

def setup_epi_tracing(
    output_dir: str = "./epi-recordings",
    auto_sign: bool = True,
    flush_interval: float = 30.0,
    service_name: str = "epi-agent",
) -> "EPISpanExporter":
    """
    One-liner setup for OpenTelemetry + EPI.

    Configures the OTel SDK with an EPI exporter so all spans
    are automatically written to signed .epi files.

    Usage:
        from epi_recorder.integrations.opentelemetry import setup_epi_tracing

        exporter = setup_epi_tracing(service_name="my-agent")

        # All OTel-instrumented code now generates .epi evidence
        tracer = trace.get_tracer("my-agent")
        with tracer.start_as_current_span("run"):
            ...

        # Shutdown when done
        exporter.shutdown()

    Args:
        output_dir: Directory for .epi output files
        auto_sign: Whether to sign .epi files
        flush_interval: Seconds between flushes
        service_name: OTel service name

    Returns:
        EPISpanExporter instance (call .shutdown() when done)
    """
    if not OTEL_AVAILABLE:
        raise ImportError(
            "OpenTelemetry is not installed. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk"
        )

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource

    # Create exporter
    exporter = EPISpanExporter(
        output_dir=output_dir,
        auto_sign=auto_sign,
        flush_interval=flush_interval,
    )

    # Create and set tracer provider
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return exporter
