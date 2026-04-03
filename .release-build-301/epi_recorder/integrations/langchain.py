"""
LangChain Callback Handler for EPI Recorder.

Automatically logs all LangChain events (LLM calls, tool calls,
chain execution, retriever queries) to the active EPI recording session.

Works with LangChain, LangGraph, and any framework using
LangChain's callback system.

Usage:
    from langchain_openai import ChatOpenAI
    from epi_recorder.integrations.langchain import EPICallbackHandler
    from epi_recorder import record

    handler = EPICallbackHandler()

    with record("my_agent.epi"):
        llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
        result = llm.invoke("Plan a trip to Tokyo")

    # Or set globally for all chains:
    from langchain.globals import set_llm_cache
    import langchain
    langchain.callbacks.manager.set_handler(handler)
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID


# Attempt to import from langchain-core (v0.2+), then langchain (legacy)
try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import BaseMessage
    from langchain_core.outputs import LLMResult
    from langchain_core.agents import AgentAction, AgentFinish
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.callbacks.base import BaseCallbackHandler
        from langchain.schema import LLMResult, AgentAction, AgentFinish
        from langchain.schema.messages import BaseMessage
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False
        # Provide stub
        class BaseCallbackHandler:
            pass
        class LLMResult:
            pass
        class AgentAction:
            pass
        class AgentFinish:
            pass
        class BaseMessage:
            pass


class EPICallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that logs events to EPI.

    Captures:
    - LLM calls (start, end, error) with prompts and responses
    - Tool/function calls with inputs and outputs
    - Chain execution with intermediate steps
    - Retriever queries and results
    - Agent actions and final answers

    All events are logged to the active EPI recording session.
    If no session is active, events are silently ignored.

    Usage:
        from epi_recorder.integrations.langchain import EPICallbackHandler
        handler = EPICallbackHandler()

        # Pass to any LangChain component
        llm = ChatOpenAI(callbacks=[handler])
        chain = prompt | llm | parser
        result = chain.invoke({"input": "..."}, config={"callbacks": [handler]})
    """

    name: str = "EPICallbackHandler"
    raise_error: bool = False  # Never break the chain

    def __init__(self):
        """Initialize EPI callback handler."""
        if not LANGCHAIN_AVAILABLE:
            import warnings
            warnings.warn(
                "LangChain is not installed. EPICallbackHandler will not log events. "
                "Install with: pip install langchain-core  OR  pip install langchain",
                RuntimeWarning,
                stacklevel=2,
            )
        super().__init__()
        self._call_times: Dict[str, float] = {}   # run_id -> start_time

    def _get_session(self):
        """Get the current active EPI recording session."""
        try:
            from epi_recorder.api import get_current_session
            return get_current_session()
        except ImportError:
            return None

    def _serialize_messages(self, messages: Any) -> List[Dict]:
        """Serialize LangChain messages to dicts."""
        result = []
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    result.append(msg)
                elif hasattr(msg, "type") and hasattr(msg, "content"):
                    result.append({
                        "role": getattr(msg, "type", "unknown"),
                        "content": str(getattr(msg, "content", "")),
                    })
                elif isinstance(msg, list):
                    # Batch of messages
                    for m in msg:
                        if hasattr(m, "type"):
                            result.append({
                                "role": getattr(m, "type", "unknown"),
                                "content": str(getattr(m, "content", "")),
                            })
                else:
                    result.append({"role": "unknown", "content": str(msg)})
        return result

    def _run_id_str(self, run_id: UUID) -> str:
        """Convert UUID to string."""
        return str(run_id)

    def _serialized_name(self, serialized: Any, default: str = "unknown") -> str:
        """Best-effort component name extraction across LangChain callback variants."""
        if not isinstance(serialized, dict):
            return default
        return (
            serialized.get("name")
            or serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("id", [default])[-1]
        )

    # ---- LLM Events ----

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts generating."""
        session = self._get_session()
        if not session:
            return

        self._call_times[self._run_id_str(run_id)] = time.time()

        model = self._serialized_name(serialized)

        session.log_step("llm.request", {
            "provider": "langchain",
            "model": model,
            "prompts": prompts[:5],  # Cap at 5 to avoid huge logs
            "run_id": self._run_id_str(run_id),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts."""
        session = self._get_session()
        if not session:
            return

        self._call_times[self._run_id_str(run_id)] = time.time()

        model = self._serialized_name(serialized)

        # Flatten batch messages
        flat_msgs = []
        for batch in messages:
            flat_msgs.extend(self._serialize_messages(batch))

        session.log_step("llm.request", {
            "provider": "langchain",
            "model": model,
            "messages": flat_msgs,
            "run_id": self._run_id_str(run_id),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes generating."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        # Extract response content
        generations = []
        usage = None

        if hasattr(response, "generations"):
            for gen_list in response.generations:
                for gen in gen_list:
                    gen_data = {"text": getattr(gen, "text", "")}
                    if hasattr(gen, "message") and gen.message:
                        msg = gen.message
                        gen_data["role"] = getattr(msg, "type", "assistant")
                        gen_data["content"] = str(getattr(msg, "content", ""))
                    generations.append(gen_data)

        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            if token_usage:
                usage = {
                    "prompt_tokens": token_usage.get("prompt_tokens", 0),
                    "completion_tokens": token_usage.get("completion_tokens", 0),
                    "total_tokens": token_usage.get("total_tokens", 0),
                }

        response_data = {
            "provider": "langchain",
            "generations": generations,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if usage:
            response_data["usage"] = usage
        if latency is not None:
            response_data["latency_seconds"] = round(latency, 3)

        session.log_step("llm.response", response_data)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors out."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        error_data = {
            "provider": "langchain",
            "error": str(error),
            "error_type": type(error).__name__,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if latency is not None:
            error_data["latency_seconds"] = round(latency, 3)

        session.log_step("llm.error", error_data)

    # ---- Tool Events ----

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts running."""
        session = self._get_session()
        if not session:
            return

        self._call_times[self._run_id_str(run_id)] = time.time()

        tool_name = self._serialized_name(serialized)

        session.log_step("tool.start", {
            "name": tool_name,
            "input": input_str[:2000],  # Truncate large inputs
            "run_id": self._run_id_str(run_id),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        result_data = {
            "output": str(output)[:2000],  # Truncate large outputs
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if latency is not None:
            result_data["latency_seconds"] = round(latency, 3)

        session.log_step("tool.end", result_data)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        error_data = {
            "error": str(error),
            "error_type": type(error).__name__,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if latency is not None:
            error_data["latency_seconds"] = round(latency, 3)

        session.log_step("tool.error", error_data)

    # ---- Chain Events ----

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain starts."""
        session = self._get_session()
        if not session:
            return

        self._call_times[self._run_id_str(run_id)] = time.time()

        chain_name = self._serialized_name(serialized)

        # Serialize inputs safely
        safe_inputs = {}
        for k, v in inputs.items():
            try:
                if hasattr(v, "model_dump"):
                    safe_inputs[k] = v.model_dump()
                else:
                    safe_inputs[k] = str(v)[:500]
            except Exception:
                safe_inputs[k] = f"<unserializable: {type(v).__name__}>"

        session.log_step("chain.start", {
            "name": chain_name,
            "inputs": safe_inputs,
            "run_id": self._run_id_str(run_id),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain finishes."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        # Serialize outputs safely
        safe_outputs = {}
        if isinstance(outputs, dict):
            for k, v in outputs.items():
                try:
                    safe_outputs[k] = str(v)[:500]
                except Exception:
                    safe_outputs[k] = f"<unserializable: {type(v).__name__}>"
        else:
            safe_outputs = {"output": str(outputs)[:500]}

        result_data = {
            "outputs": safe_outputs,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if latency is not None:
            result_data["latency_seconds"] = round(latency, 3)

        session.log_step("chain.end", result_data)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain errors."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        self._call_times.pop(run_key, None)

        session.log_step("chain.error", {
            "error": str(error),
            "error_type": type(error).__name__,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ---- Retriever Events ----

    def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever starts."""
        session = self._get_session()
        if not session:
            return

        self._call_times[self._run_id_str(run_id)] = time.time()

        session.log_step("retriever.query", {
            "query": query[:1000],
            "run_id": self._run_id_str(run_id),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever finishes."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        start = self._call_times.pop(run_key, None)
        latency = time.time() - start if start else None

        # Extract document summaries
        doc_summaries = []
        if isinstance(documents, list):
            for doc in documents[:10]:  # Cap at 10 docs
                if hasattr(doc, "page_content"):
                    doc_summaries.append({
                        "content": str(doc.page_content)[:200],
                        "metadata": getattr(doc, "metadata", {}),
                    })

        result_data = {
            "documents": doc_summaries,
            "document_count": len(documents) if isinstance(documents, list) else 0,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if latency is not None:
            result_data["latency_seconds"] = round(latency, 3)

        session.log_step("retriever.result", result_data)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever errors."""
        session = self._get_session()
        if not session:
            return

        run_key = self._run_id_str(run_id)
        self._call_times.pop(run_key, None)

        session.log_step("retriever.error", {
            "error": str(error),
            "error_type": type(error).__name__,
            "run_id": run_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ---- Agent Events ----

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when agent takes an action."""
        session = self._get_session()
        if not session:
            return

        action_data = {
            "run_id": self._run_id_str(run_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if hasattr(action, "tool"):
            action_data["tool"] = action.tool
            action_data["tool_input"] = str(action.tool_input)[:1000]
            action_data["log"] = str(getattr(action, "log", ""))[:500]

        session.log_step("agent.action", action_data)

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when agent finishes."""
        session = self._get_session()
        if not session:
            return

        finish_data = {
            "run_id": self._run_id_str(run_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if hasattr(finish, "return_values"):
            finish_data["return_values"] = {
                k: str(v)[:500] for k, v in finish.return_values.items()
            }
        if hasattr(finish, "log"):
            finish_data["log"] = str(finish.log)[:500]

        session.log_step("agent.finish", finish_data)
