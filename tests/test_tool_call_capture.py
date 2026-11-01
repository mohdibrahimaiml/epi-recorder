"""Tool-call decisions must survive into the sealed record.

Most agents do not answer in prose; they answer by calling a tool. The wrappers
used to copy only ``role`` and ``content`` off each response, so a decision like
``deny_claim({"reason": "excluded peril"})`` was sealed as ``content: null``.
These tests seal a tool-call response and read the bytes back.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fn(name, arguments):
    return SimpleNamespace(name=name, arguments=json.dumps(arguments))


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=_fn(name, arguments),
    )


def _steps(epi_path) -> list[dict]:
    with zipfile.ZipFile(epi_path) as zf:
        raw = zf.read("steps.jsonl").decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _sealed_text(epi_path) -> bytes:
    """Everything inside the sealed container, decompressed.

    Checking ``read_bytes()`` would only see zip-compressed member data, so a
    missing string there proves nothing. This is what a verifier reads.
    """
    with zipfile.ZipFile(epi_path) as zf:
        return b"\n".join(zf.read(name) for name in zf.namelist())


def _step(steps, kind, provider=None):
    found = [
        s
        for s in steps
        if s["kind"] == kind and (provider is None or s["content"].get("provider") == provider)
    ]
    assert found, f"no {kind} step for {provider} in {[s['kind'] for s in steps]}"
    return found[-1]["content"]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _openai_response(tool_calls, *, text=None):
    return SimpleNamespace(
        id="chatcmpl-abc123",
        model="gpt-4o-2024-08-06",
        created=1730000000,
        system_fingerprint="fp_9f2c1",
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=18, total_tokens=138),
        choices=[
            SimpleNamespace(
                index=0,
                finish_reason="tool_calls" if tool_calls else "stop",
                message=SimpleNamespace(
                    role="assistant",
                    content=text,
                    tool_calls=tool_calls,
                    refusal=None,
                ),
            )
        ],
    )


def test_openai_tool_call_decision_is_sealed(tmp_path):
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    decision_args = {"claim_id": "CLM-4471", "reason": "excluded peril"}
    completions = SimpleNamespace(
        create=lambda *a, **k: _openai_response([_tool_call("call_7", "deny_claim", decision_args)])
    )

    epi = tmp_path / "case.epi"
    with record(str(epi)):
        TracedCompletions(completions).create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Assess claim CLM-4471"}],
            temperature=0.2,
            max_tokens=256,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "deny_claim",
                        "description": "Deny a claim with a reason code",
                        "parameters": {"type": "object"},
                    },
                },
                {
                    "type": "function",
                    "function": {"name": "pay_claim", "description": "Approve payment"},
                },
            ],
        )

    steps = _steps(epi)
    response = _step(steps, "llm.response")
    request = _step(steps, "llm.request")

    # The decision itself: tool name and the arguments it decided with.
    assert response["tool_calls"] == [
        {
            "id": "call_7",
            "name": "deny_claim",
            "arguments": json.dumps(decision_args),
            "arguments_parsed": decision_args,
        }
    ]
    assert response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "deny_claim"
    assert response["choices"][0]["finish_reason"] == "tool_calls"

    # Server-side identity: which request, which model version answered.
    assert response["served_model"] == "gpt-4o-2024-08-06"
    assert response["model"] == "gpt-4o"
    assert response["response_id"] == "chatcmpl-abc123"
    assert response["system_fingerprint"] == "fp_9f2c1"
    assert response["created"] == 1730000000

    # Request settings and the tools the model could choose between.
    assert request["temperature"] == 0.2
    assert request["max_tokens"] == 256
    assert [t["name"] for t in request["tools"]] == ["deny_claim", "pay_claim"]

    # And it is in the sealed bytes, not just in memory.
    blob = _sealed_text(epi)
    assert b"deny_claim" in blob
    assert b"excluded peril" in blob


def test_openai_text_answer_has_no_tool_section(tmp_path):
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    completions = SimpleNamespace(create=lambda *a, **k: _openai_response([], text="Approved."))

    epi = tmp_path / "text.epi"
    with record(str(epi)):
        TracedCompletions(completions).create(
            model="gpt-4o", messages=[{"role": "user", "content": "hello"}]
        )

    response = _step(_steps(epi), "llm.response")
    assert response["choices"][0]["message"]["content"] == "Approved."
    assert "tool_calls" not in response


def test_openai_streaming_tool_call_is_sealed(tmp_path):
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    def chunk(delta, *, finish=None, fingerprint="fp_stream"):
        return SimpleNamespace(
            id="chatcmpl-stream",
            model="gpt-4o-2024-08-06",
            created=1730000001,
            system_fingerprint=fingerprint,
            usage=None,
            choices=[SimpleNamespace(index=0, finish_reason=finish, delta=delta)],
        )

    def stream():
        yield chunk(
            SimpleNamespace(
                content=None,
                reasoning=None,
                refusal=None,
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_stream",
                        type="function",
                        function=SimpleNamespace(name="deny_claim", arguments='{"claim_id":'),
                    )
                ],
            )
        )
        yield chunk(
            SimpleNamespace(
                content=None,
                reasoning=None,
                refusal=None,
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id=None,
                        type=None,
                        function=SimpleNamespace(name=None, arguments='"CLM-9", "reason": "excluded peril"}'),
                    )
                ],
            )
        )
        yield chunk(
            SimpleNamespace(content=None, reasoning=None, refusal=None, tool_calls=None),
            finish="tool_calls",
        )

    completions = SimpleNamespace(create=lambda *a, **k: stream())

    epi = tmp_path / "stream.epi"
    with record(str(epi)):
        for _ in TracedCompletions(completions).create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "assess"}],
            stream=True,
        ):
            pass

    response = _step(_steps(epi), "llm.response")
    assert response["tool_calls"][0]["name"] == "deny_claim"
    assert response["tool_calls"][0]["arguments_parsed"] == {
        "claim_id": "CLM-9",
        "reason": "excluded peril",
    }
    assert response["served_model"] == "gpt-4o-2024-08-06"
    assert response["response_id"] == "chatcmpl-stream"
    assert response["system_fingerprint"] == "fp_stream"
    assert b"excluded peril" in _sealed_text(epi)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _anthropic_response(blocks, *, stop_reason="tool_use"):
    return SimpleNamespace(
        id="msg_01XYZ",
        model="claude-sonnet-4-20250514",
        role="assistant",
        type="message",
        stop_reason=stop_reason,
        stop_sequence=None,
        content=blocks,
        usage=SimpleNamespace(input_tokens=310, output_tokens=44),
    )


def test_anthropic_tool_use_decision_is_sealed(tmp_path):
    from epi_recorder import record
    from epi_recorder.wrappers.anthropic import TracedMessages

    decision_input = {"claim_id": "CLM-4471", "reason": "excluded peril"}
    response = _anthropic_response(
        [
            SimpleNamespace(type="text", text="I will deny this claim."),
            SimpleNamespace(type="tool_use", id="toolu_01", name="deny_claim", input=decision_input),
        ]
    )
    messages = SimpleNamespace(create=lambda *a, **k: response)

    epi = tmp_path / "case.epi"
    with record(str(epi)):
        TracedMessages(messages).create(
            model="claude-sonnet-4",
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": "Assess claim CLM-4471"}],
            tools=[{"name": "deny_claim", "description": "Deny a claim with a reason code"}],
        )

    steps = _steps(epi)
    logged = _step(steps, "llm.response")
    request = _step(steps, "llm.request")

    assert logged["tool_uses"] == [
        {"id": "toolu_01", "name": "deny_claim", "input": decision_input}
    ]
    assert logged["content"][0] == {"type": "text", "text": "I will deny this claim."}
    assert logged["content"][1]["type"] == "tool_use"
    assert logged["stop_reason"] == "tool_use"
    assert logged["served_model"] == "claude-sonnet-4-20250514"
    assert logged["response_id"] == "msg_01XYZ"
    assert [t["name"] for t in request["tools"]] == ["deny_claim"]

    blob = _sealed_text(epi)
    assert b"deny_claim" in blob
    assert b"excluded peril" in blob


def test_anthropic_streaming_tool_use_is_sealed(tmp_path):
    from epi_recorder import record
    from epi_recorder.wrappers.anthropic import TracedMessages

    events = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                id="msg_stream",
                model="claude-sonnet-4-20250514",
                usage=SimpleNamespace(input_tokens=88, output_tokens=1),
            ),
        ),
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", id="toolu_02", name="deny_claim"),
            delta=None,
            message=None,
        ),
        SimpleNamespace(
            type="content_block_delta",
            content_block=None,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"claim_id": "CLM-9", '),
            message=None,
        ),
        SimpleNamespace(
            type="content_block_delta",
            content_block=None,
            delta=SimpleNamespace(type="input_json_delta", partial_json='"reason": "excluded peril"}'),
            message=None,
        ),
        SimpleNamespace(
            type="message_delta",
            content_block=None,
            delta=SimpleNamespace(stop_reason="tool_use"),
            message=None,
            usage=SimpleNamespace(input_tokens=88, output_tokens=44),
        ),
    ]
    messages = SimpleNamespace(create=lambda *a, **k: iter(events))

    epi = tmp_path / "stream.epi"
    with record(str(epi)):
        for _ in TracedMessages(messages).stream(
            model="claude-sonnet-4",
            max_tokens=256,
            messages=[{"role": "user", "content": "assess"}],
        ):
            pass

    logged = _step(_steps(epi), "llm.response")
    assert logged["tool_uses"] == [
        {
            "id": "toolu_02",
            "name": "deny_claim",
            "input": {"claim_id": "CLM-9", "reason": "excluded peril"},
        }
    ]
    assert logged["served_model"] == "claude-sonnet-4-20250514"
    assert logged["response_id"] == "msg_stream"
    assert logged["stop_reason"] == "tool_use"
    assert b"excluded peril" in _sealed_text(epi)


# ---------------------------------------------------------------------------
# Explicit API + structured decision
# ---------------------------------------------------------------------------

def test_log_llm_call_keeps_tool_calls(tmp_path):
    from epi_recorder import record

    response = _openai_response([_tool_call("call_9", "deny_claim", {"reason": "excluded peril"})])

    epi = tmp_path / "manual.epi"
    with record(str(epi)) as session:
        session.log_llm_call(response, messages=[{"role": "user", "content": "assess"}])

    logged = _step(_steps(epi), "llm.response")
    assert logged["tool_calls"][0]["name"] == "deny_claim"
    assert logged["tool_calls"][0]["arguments_parsed"] == {"reason": "excluded peril"}
    assert logged["response_id"] == "chatcmpl-abc123"


def test_structured_decision_records_outcome_reason_and_basis(tmp_path):
    from epi_recorder import record

    epi = tmp_path / "decision.epi"
    with record(str(epi)) as session:
        with session.agent_run("claims-agent", user_input="CLM-4471") as agent:
            agent.decision(
                "deny_claim",
                rationale="Policy exclusion 4.2 (flood) applies to this peril.",
                basis={"policy": "POL-4.2", "tool_results": ["lookup_policy:POL-4.2"]},
            )

    step = _step(_steps(epi), "agent.decision")
    assert step["decision"] == "deny_claim"
    assert "exclusion 4.2" in step["rationale"]
    assert step["basis"]["policy"] == "POL-4.2"


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_no_provider_object_leaks_into_the_record(tmp_path, provider):
    """SDK objects must be serialized, never str()'d into the evidence file."""
    from epi_recorder import record

    epi = tmp_path / f"{provider}.epi"
    with record(str(epi)):
        if provider == "openai":
            from epi_recorder.wrappers.openai import TracedCompletions

            completions = SimpleNamespace(
                create=lambda *a, **k: _openai_response(
                    [_tool_call("call_1", "deny_claim", {"reason": "excluded peril"})]
                )
            )
            TracedCompletions(completions).create(
                model="gpt-4o", messages=[{"role": "user", "content": "x"}]
            )
        else:
            from epi_recorder.wrappers.anthropic import TracedMessages

            messages = SimpleNamespace(
                create=lambda *a, **k: _anthropic_response(
                    [SimpleNamespace(type="tool_use", id="toolu_1", name="deny_claim", input={})]
                )
            )
            TracedMessages(messages).create(
                model="claude-sonnet-4", max_tokens=16, messages=[{"role": "user", "content": "x"}]
            )

    blob = _sealed_text(epi)
    assert b"SimpleNamespace" not in blob
    assert b"object at 0x" not in blob


# ---------------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------------

_VIEWER_HARNESS = r'''
const fs = require('fs');
const vm = require('vm');
const el = () => ({ _v: '', set textContent(v) { this._v = v; }, get textContent() { return this._v; },
  get innerHTML() { return String(this._v); }, style: {}, dataset: {}, children: [],
  classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {}, appendChild() {},
  setAttribute() {}, getAttribute() { return null; }, querySelector() { return null; },
  querySelectorAll() { return []; } });
const document = { readyState: 'loading', addEventListener() {}, removeEventListener() {},
  createElement: el, createTextNode: (t) => ({ textContent: t }), getElementById() { return null; },
  querySelector() { return null; }, querySelectorAll() { return []; }, body: el(),
  documentElement: el(), head: el() };
const window = { addEventListener() {}, removeEventListener() {},
  location: { protocol: 'file:', href: 'file:///x.epi', search: '' },
  localStorage: { getItem() { return null; }, setItem() {} },
  matchMedia() { return { matches: false, addEventListener() {} }; } };
const ctx = { document, window, console, navigator: { clipboard: { writeText() {} }, userAgent: 'node' },
  JSZip: function () {}, Blob: function () {}, FileReader: function () {}, URL,
  setTimeout, clearTimeout, setInterval, clearInterval, TextEncoder, TextDecoder, atob, btoa,
  fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
  crypto: require('crypto').webcrypto, location: window.location, localStorage: window.localStorage };
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('web_viewer/app.js', 'utf8'), ctx, { filename: 'app.js' });

const summarize = (content) => ctx.summarizeStep({ kind: 'llm.response', content });
const openai = summarize({ model: 'gpt-4o', choices: [{ message: { role: 'assistant', content: null,
  tool_calls: [{ id: 'c1', type: 'function', function: { name: 'deny_claim', arguments: '{"reason":"excluded peril"}' } }] } }] });
const anthropic = summarize({ model: 'claude', content: [{ type: 'tool_use', id: 't1', name: 'deny_claim', input: { reason: 'excluded peril' } }] });
const prose = summarize({ model: 'gpt-4o', choices: [{ message: { content: 'Approved.' } }] });

const fail = (msg) => { console.error(msg); process.exit(1); };
if (!openai.includes('deny_claim') || !openai.includes('excluded peril')) fail('openai summary lost the decision: ' + openai);
if (!anthropic.includes('deny_claim') || !anthropic.includes('excluded peril')) fail('anthropic summary lost the decision: ' + anthropic);
if (prose !== 'Approved.') fail('text summary changed: ' + prose);
console.log('viewer summary OK');
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_viewer_shows_the_tool_call_instead_of_a_blank_response(tmp_path):
    """A tool decision has no prose; the timeline must still show the call."""
    harness = tmp_path / "viewer_harness.js"
    harness.write_text(_VIEWER_HARNESS, encoding="utf-8")

    result = subprocess.run(
        [shutil.which("node"), str(harness)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_session_decision_works_without_an_agent_run(tmp_path):
    """The obvious call must exist: epi.decision(...) on the session itself."""
    from epi_recorder import record

    epi = tmp_path / "flat.epi"
    with record(str(epi)) as session:
        session.decision(
            "deny_claim",
            rationale="Policy exclusion 4.2 (flood) applies.",
            basis={"policy": "HO3-4.2"},
        )

    step = _step(_steps(epi), "agent.decision")
    assert step["decision"] == "deny_claim"
    assert "exclusion 4.2" in step["rationale"]
    assert step["basis"]["policy"] == "HO3-4.2"
