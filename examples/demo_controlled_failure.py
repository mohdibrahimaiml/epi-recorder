import logging
import json
from typing import TypedDict, Annotated, Sequence
import operator

# Framework integrations as requested
import litellm
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from epi_recorder.integrations.opentelemetry import setup_epi_tracing
from epi_recorder.integrations.litellm import EPICallback

# Optional: Set up OTel tracing to demonstrate failure capture
setup_epi_tracing(service_name="Agent[MultiStep]")
litellm.callbacks = [EPICallback()]

# Configure standard logging to look "fine"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Agent[MultiStep]")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    step: int
    extracted_items: int

def llm_reasoning_node(state):
    """Simulates a LangChain/LiteLLM node reasoning over data"""
    step = state.get("step", 1)
    logger.info(f"Step {step}/32: Processing data chunk via LiteLLM...")
    
    # Simulate processing time
    msg = AIMessage(content=f"Analyzed subset {step}. No anomalies detected.")
    
    if step == 31:
        # At step 31, the LLM decides to use a tool but hallucinates a schema drift
        logger.info(f"Call tool 'update_database' initiated by LLM.")
        tool_call = {
            "name": "update_database",
            "args": {"user_id": "thirty_one", "data": "metrics"}, # subtle drift: string instead of int
            "id": "call_drift890"
        }
        msg = AIMessage(content="", tool_calls=[tool_call])
        
    return {"messages": [msg], "step": step + 1}

def tool_execution_node(state):
    """Simulates a typical tool execution that fails silently on schema mismatch"""
    logger.info("Executing Tool: update_database")
    
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        args = last_message.tool_calls[0]["args"]
        user_id = args.get("user_id")
        
        # Standard APIs might ignore invalid types or cast them incorrectly,
        # leading to an HTTP 200 OK but corrupted data under the hood.
        if isinstance(user_id, str):
            logger.warning("Type coercion warning: user_id provided as string. Coercing to default.")
            # Fails silently, returning OK but actually it didn't update the correct row.
            logger.info("Tool execution HTTP 200 OK.")
            return {"messages": [ToolMessage(content="{\"status\": \"success\", \"rows_affected\": 0}", tool_call_id=last_message.tool_calls[0]["id"])], "extracted_items": -1}
            
    return {"messages": [ToolMessage(content="{\"status\": \"success\"}", tool_call_id="call_mock")], "extracted_items": state.get("extracted_items", 0) + 1}

def router_logic(state):
    step = state.get("step", 1)
    if step <= 30:
        return "reasoning"
    elif step == 31:
        # Tool call
        return "tool_node"
    else:
        return END

# Build LangGraph workflow
workflow = StateGraph(AgentState)
workflow.add_node("reasoning", llm_reasoning_node)
workflow.add_node("tool_node", tool_execution_node)
workflow.set_entry_point("reasoning")

workflow.add_conditional_edges("reasoning", router_logic)
workflow.add_edge("tool_node", END)

agent_app = workflow.compile()

def main():
    logger.info("Initializing Agent System...")
    inputs = {
        "messages": [HumanMessage(content="Perform deep analysis and ingest to DB.")],
        "step": 1,
        "extracted_items": 30
    }
    
    # ---------------------------------------------------------
    # EPI RECORDER HIGHLIGHT (Toggle this for the 60-second Demo)
    # ---------------------------------------------------------
    use_epi = False
    
    if use_epi:
        from epi_recorder import record
        with record("agent_failure.epi"):
            result = agent_app.invoke(inputs)
    else:
        result = agent_app.invoke(inputs)
    # ---------------------------------------------------------
        
    logger.info("Agent pipeline complete.")
    if result.get("extracted_items", 0) < 0:
        logger.error("FATAL: Final state verification failed. Data corrupted.")
    else:
        logger.info("Success! All processes finished.")

if __name__ == "__main__":
    main()
