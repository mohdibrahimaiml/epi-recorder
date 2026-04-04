from epi_core.llm_capture import LLMCaptureRequest, build_llm_capture_events


def test_build_llm_capture_events_normalizes_openai_compatible_ollama():
    events = build_llm_capture_events(
        LLMCaptureRequest(
            provider="ollama",
            request={
                "model": "llama3.2",
                "messages": [{"role": "user", "content": "Approve refund?"}],
                "stream": False,
            },
            response={
                "model": "llama3.2",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Approve with review."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
            },
            meta={"trace_id": "trace-1", "decision_id": "decision-1"},
        )
    )

    assert [event.kind for event in events] == ["llm.request", "llm.response"]
    assert events[0].provider == "ollama"
    assert events[0].meta["provider_profile"] == "openai-compatible"
    assert events[1].content["output_text"] == "Approve with review."
    assert events[1].content["usage"]["total_tokens"] == 16


def test_build_llm_capture_events_normalizes_anthropic_payload():
    events = build_llm_capture_events(
        {
            "provider": "anthropic",
            "request": {
                "model": "claude-3-5-sonnet",
                "messages": [{"role": "user", "content": "Summarize the policy."}],
                "max_tokens": 256,
            },
            "response": {
                "model": "claude-3-5-sonnet",
                "role": "assistant",
                "content": [{"type": "text", "text": "Policy summary"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "stop_reason": "end_turn",
            },
        }
    )

    assert events[0].meta["provider_profile"] == "anthropic-messages"
    assert events[1].content["output_text"] == "Policy summary"
    assert events[1].content["stop_reason"] == "end_turn"


def test_build_llm_capture_events_normalizes_gemini_payload():
    events = build_llm_capture_events(
        {
            "provider": "google",
            "request": {
                "model": "gemini-1.5-pro",
                "contents": [{"role": "user", "parts": [{"text": "Check eligibility"}]}],
            },
            "response": {
                "modelVersion": "gemini-1.5-pro",
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Eligible with manual approval"}],
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 6},
            },
        }
    )

    assert events[0].provider == "gemini"
    assert events[0].meta["provider_profile"] == "gemini-generate-content"
    assert events[1].content["output_text"] == "Eligible with manual approval"


def test_build_llm_capture_events_resolves_litellm_to_actual_provider():
    events = build_llm_capture_events(
        {
            "provider": "litellm",
            "request": {
                "model": "anthropic/claude-3-5-sonnet",
                "messages": [{"role": "user", "content": "Review this claim"}],
            },
            "response": {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Needs manager review"},
                        "finish_reason": "stop",
                    }
                ]
            },
        }
    )

    assert events[0].provider == "anthropic"
    assert events[0].meta["provider_adapter"] == "litellm"
    assert events[0].meta["provider_profile"] == "openai-compatible"


def test_build_llm_capture_events_emits_error_event():
    events = build_llm_capture_events(
        {
            "provider": "vllm",
            "request": {
                "model": "mistral-large",
                "messages": [{"role": "user", "content": "Draft the decision"}],
            },
            "error": {
                "error": "upstream timeout",
                "error_type": "TimeoutError",
            },
            "meta": {"latency_seconds": 3.2},
        }
    )

    assert [event.kind for event in events] == ["llm.request", "llm.error"]
    assert events[1].provider == "vllm"
    assert events[1].content["provider_profile"] == "openai-compatible"
    assert events[1].content["latency_seconds"] == 3.2
