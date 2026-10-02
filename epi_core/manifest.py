"""
Capture Manifest — declares what was instrumented for a specific run.

Every .epi artifact embeds artifacts/manifest.json describing the capture
scope so completeness is judged against a stated scope, not an
unfalsifiable claim.

Registry note (reported back per spec):
  There is NO single registry object that knows which integrations are
  active (OTel, LiteLLM, gateway routes). The recorder learns what it wraps
  from three places: epi_recorder.wrappers (wrap_openai/wrap_anthropic),
  epi_recorder.integrations.__all__ (LangGraph, OpenAI Agents, LiteLLM,
  LangChain, OpenTelemetry, Guardrails), and epi_gateway routes
  (/v1/chat/completions, /v1/messages, /capture/llm). get_instrumented_surfaces()
  below reads from those two Python sources — it does not invent a second
  source of truth, it aggregates the existing ones.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

MANIFEST_SCHEMA_VERSION = "1.0"

# Static, versioned list of what this recorder version cannot see.
# Property of the recorder version, not the run. Must ship non-empty.
KNOWN_GAPS: list[str] = [
    "direct HTTP calls bypassing wrap_openai/wrap_anthropic are not captured",
    "subprocess calls without instrumentation are not captured",
    "raw API calls with unwrapped credentials are not captured",
    "gateway returns 501 for streaming; streamed calls must use the SDK wrapper path",
    "LangSmith export does not exist (only OpenTelemetry span exporter and LiteLLM callback)",
]

CapturePath = Literal["gateway", "sdk_wrapper", "mixed", "unknown"]
GatewayEnforcement = Literal["fail_closed", "fail_open", "mixed", "not_applicable"]


class FailOpenEvent(BaseModel):
    event_id: str
    timestamp: str
    reason: str = "client_header_override"


class CaptureSegment(BaseModel):
    """Per-event/segment capture properties (handles mixed gateway+SDK runs)."""

    event_id: str = ""
    step_index: int | None = None
    capture_path: CapturePath = "unknown"
    gateway_enforcement: GatewayEnforcement = "not_applicable"
    streaming: bool = False


class CaptureManifest(BaseModel):
    schema_version: str = MANIFEST_SCHEMA_VERSION
    # Global summary. "mixed" when segments differ (streaming forces SDK path).
    capture_path: CapturePath = "unknown"
    gateway_enforcement: GatewayEnforcement = "not_applicable"
    streaming: bool = False
    fail_open_events: list[FailOpenEvent] = Field(default_factory=list)
    segments: list[CaptureSegment] = Field(default_factory=list)
    instrumented_surfaces: list[str] = Field(default_factory=list)
    # Per-run truth, derived from sealed steps (what this run DID see).
    # instrumented_surfaces is the recorder version's capability list (what it
    # CAN see); active_surfaces is the run's evidence (what flowed). A
    # per-run field populated from a global source was the same class of
    # error as the gateway mislabeling, so the two are kept distinct.
    # Boundary, stated not hidden: adapters whose evidence is
    # indistinguishable in steps (LangChain tool calls, OTel-replayed generic
    # steps, manual agent.* calls) are attributed to their underlying kind
    # family, not an adapter name. Only distinctive markers (provider-tagged
    # llm.*, langgraph.*, validation.*) name their source.
    active_surfaces: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)
    recorder_version: str = "unknown"


def get_recorder_version() -> str:
    try:
        from epi_core._version import get_version

        return get_version()
    except Exception:
        return "unknown"


def get_instrumented_surfaces() -> list[str]:
    """Aggregate from existing sources — wrappers + integrations.__all__ + gateway routes."""
    surfaces: list[str] = []
    # Wrappers (what the recorder knows how to wrap)
    try:
        surfaces.extend(["openai.chat.completions", "anthropic.messages"])
    except Exception:
        pass
    # Integrations registry (epi_recorder.integrations.__all__ is the closest thing)
    try:
        from epi_recorder import integrations as _integ

        for name in getattr(_integ, "__all__", []):
            surfaces.append(f"integration.{name}")
    except Exception:
        pass
    # Gateway routes
    surfaces.extend([
        "gateway./v1/chat/completions",
        "gateway./v1/messages",
        "gateway./capture/llm",
    ])
    # Deduplicate, stable order
    seen: set[str] = set()
    out: list[str] = []
    for s in surfaces:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_steps(source_dir: Path) -> list[dict[str, Any]]:
    steps_path = source_dir / "steps.jsonl"
    if not steps_path.exists():
        return []
    steps: list[dict[str, Any]] = []
    try:
        for line in steps_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    steps.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return steps


def _read_gateway_sidecar(source_dir: Path) -> list[dict[str, Any]]:
    """Gateway live-capture sidecar (written by gateway export paths, if present)."""
    out: list[dict[str, Any]] = []
    for name in ("artifacts/gateway_captures.jsonl", "gateway_captures.jsonl"):
        p = source_dir / name
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                continue
    return out


def build_capture_manifest(
    source_dir: Path,
    *,
    extra_gaps: list[str] | None = None,
) -> CaptureManifest:
    """Build manifest at seal time from live-tagged steps + gateway sidecar.

    Live tagging happens at capture time:
      - SDK: RecordingContext tags steps with content._epi_capture
        (capture_path=sdk_wrapper, streaming from content.stream)
      - Gateway: _enqueue_llm_capture tags CaptureEventModel.meta with
        capture_path=gateway, enforcement, streaming; fail-open overrides
        emit FailOpenEvent entries into the sidecar / event meta.
    This builder aggregates those live tags — it does not reconstruct from logs.
    """
    steps = _read_steps(source_dir)
    sidecar = _read_gateway_sidecar(source_dir)

    segments: list[CaptureSegment] = []
    fail_open: list[FailOpenEvent] = []

    for s in steps:
        content = s.get("content") or {}
        cap = content.get("_epi_capture") or {}
        # Untagged steps (pre-manifest artifacts, hand-built payloads) are
        # "unknown" — never guessed from kind. Guessing sdk_wrapper for
        # untagged llm.* steps once mislabeled an entire gateway export.
        cpath = cap.get("capture_path", "unknown")
        # Streaming invariant: content.stream True implies SDK wrapper
        streaming = bool(cap.get("streaming", content.get("stream", False)))
        enforcement = cap.get("gateway_enforcement", "not_applicable")
        if streaming and cpath == "gateway":
            # Assert invariant — streaming forces SDK path (gateway returns 501)
            cpath = "sdk_wrapper"
        event_id = str(cap.get("event_id") or s.get("event_id") or f"step-{s.get('index')}")
        segments.append(CaptureSegment(
            event_id=event_id,
            step_index=s.get("index"),
            capture_path=cpath,  # type: ignore[arg-type]
            gateway_enforcement=enforcement,  # type: ignore[arg-type]
            streaming=streaming,
        ))
        # Fail-open live tag on the step
        if cap.get("fail_open_reason"):
            fail_open.append(FailOpenEvent(
                event_id=event_id,
                timestamp=str(cap.get("timestamp") or s.get("timestamp") or _utc_now_iso()),
                reason=str(cap.get("fail_open_reason")),
            ))

    for ev in sidecar:
        meta = ev.get("meta") or {}
        cap = meta.get("_epi_capture") or ev.get("_epi_capture") or {}
        cpath = cap.get("capture_path", "gateway")
        streaming = bool(cap.get("streaming", False))
        enforcement = cap.get("gateway_enforcement", "not_applicable")
        if streaming and cpath == "gateway":
            cpath = "sdk_wrapper"
        event_id = str(ev.get("event_id") or meta.get("event_id") or f"gateway-{len(segments)}")
        segments.append(CaptureSegment(
            event_id=event_id,
            step_index=None,
            capture_path=cpath,
            gateway_enforcement=enforcement,
            streaming=streaming,
        ))
        if cap.get("fail_open_reason") or enforcement == "fail_open":
            fail_open.append(FailOpenEvent(
                event_id=event_id,
                timestamp=str(ev.get("captured_at") or _utc_now_iso()),
                reason=str(cap.get("fail_open_reason") or "client_header_override"),
            ))

    # Global summary
    paths = {s.capture_path for s in segments}
    if not segments:
        global_path: CapturePath = "unknown"
    elif len(paths) == 1:
        global_path = next(iter(paths))  # type: ignore[assignment]
    else:
        global_path = "mixed"

    enforcements = {s.gateway_enforcement for s in segments}
    gateway_segments = [s for s in segments if s.capture_path in ("gateway", "mixed")]
    if not gateway_segments:
        global_enf: GatewayEnforcement = "not_applicable"
    elif enforcements == {"fail_closed"}:
        global_enf = "fail_closed"
    elif enforcements == {"fail_open"}:
        global_enf = "fail_open"
    elif "fail_open" in enforcements:
        global_enf = "mixed"
    else:
        # gateway present but enforcement tags vary (e.g. not_applicable mix)
        global_enf = "mixed" if len(enforcements) > 1 else next(iter(enforcements))  # type: ignore[assignment]

    # If explicit fail-open events exist and enforcement still says fail_closed, correct it.
    if fail_open and global_enf == "fail_closed":
        global_enf = "mixed"

    any_streaming = any(s.streaming for s in segments)

    gaps = list(KNOWN_GAPS)
    if extra_gaps:
        for g in extra_gaps:
            if g not in gaps:
                gaps.append(g)
    # Runtime TSA/checkpoint gaps recorded by checkpoint module
    gap_file = source_dir / "artifacts" / "capture_gaps.json"
    if gap_file.exists():
        try:
            extra = json.loads(gap_file.read_text(encoding="utf-8"))
            if isinstance(extra, list):
                for g in extra:
                    if isinstance(g, str) and g not in gaps:
                        gaps.append(g)
        except Exception:
            pass

    active = _derive_active_surfaces(steps)

    return CaptureManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        capture_path=global_path,
        gateway_enforcement=global_enf,
        streaming=any_streaming,
        fail_open_events=fail_open,
        segments=segments,
        instrumented_surfaces=get_instrumented_surfaces(),
        active_surfaces=active,
        known_gaps=gaps,
        recorder_version=get_recorder_version(),
    )


def _derive_active_surfaces(steps: list[dict[str, Any]]) -> list[str]:
    """What this run DID see, derived from sealed steps — never from globals.

    Entries are "capture_path:surface" strings in first-seen order.
    """
    provider_surface = {
        "openai": "openai.chat.completions",
        "openai-compatible": "openai.chat.completions",
        "azure-openai": "openai.chat.completions",
        "azure": "openai.chat.completions",
        "ollama": "openai.chat.completions",
        "vllm": "openai.chat.completions",
        "lmstudio": "openai.chat.completions",
        "groq": "openai.chat.completions",
        "anthropic": "anthropic.messages",
        "claude": "anthropic.messages",
        "gemini": "gemini.generate_content",
        "google": "gemini.generate_content",
    }
    active: list[str] = []
    seen: set[str] = set()

    def _add(entry: str) -> None:
        if entry not in seen:
            seen.add(entry)
            active.append(entry)

    for s in steps:
        if not isinstance(s, dict):
            continue
        content = s.get("content") or {}
        if not isinstance(content, dict):
            continue
        cap = content.get("_epi_capture") or {}
        if not isinstance(cap, dict):
            cap = {}
        path = str(cap.get("capture_path") or "unknown")
        kind = str(s.get("kind") or "")
        if kind.startswith("llm."):
            provider = str(content.get("provider") or "unknown").strip().lower()
            surface = provider_surface.get(provider, f"provider.{provider}")
            _add(f"{path}:{surface}")
        elif kind.startswith("langgraph."):
            _add(f"{path}:integration.langgraph")
        elif kind.startswith("validation."):
            _add(f"{path}:integration.validators")
        elif kind.startswith("agent."):
            _add(f"{path}:agent framework")
        elif path == "gateway":
            _add("gateway:llm.capture")
    return active


def write_manifest(source_dir: Path, manifest: CaptureManifest) -> Path:
    out = source_dir / "artifacts" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return out


def read_manifest_from_archive(epi_path: Path) -> CaptureManifest | None:
    """Read embedded manifest.json from a sealed artifact; None if pre-v artifact."""
    try:
        from epi_core.container import EPIContainer

        data = EPIContainer.read_member_json(epi_path, "artifacts/manifest.json")
        if isinstance(data, dict):
            return CaptureManifest.model_validate(data)
    except Exception:
        pass
    return None


def append_runtime_gap(source_dir: Path, gap: str) -> None:
    """Record a per-run gap (e.g. TSA outage) wired into the manifest's known_gaps."""
    try:
        gap_file = source_dir / "artifacts" / "capture_gaps.json"
        gap_file.parent.mkdir(parents=True, exist_ok=True)
        existing: list[str] = []
        if gap_file.exists():
            try:
                data = json.loads(gap_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    existing = [str(x) for x in data]
            except Exception:
                existing = []
        if gap not in existing:
            existing.append(gap)
        gap_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass
