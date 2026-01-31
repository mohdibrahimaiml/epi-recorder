"""
Robust Agent Simulation for EPI Viewer Testing.

This script simulates a complex "Research Agent" workflow to test
the EPI Viewer's ability to render rich, multi-step agent interactions
including tool usage, reasoning, and file operations.

This allows us to test the VIEWER without needing live API keys.
"""

import time
import json
import sys
from pathlib import Path
from epi_recorder import record

# Try to import low-level context accessor (what 'epi run' uses)
try:
    from epi_recorder.patcher import get_recording_context
except ImportError:
    get_recording_context = None

# Try to import high-level session accessor (what 'record()' uses)
try:
    from epi_recorder.api import get_current_session
except ImportError:
    get_current_session = None

def get_recorder():
    """Get active recorder context or session"""
    # 1. Try 'epi run' context (RecordingContext)
    if get_recording_context:
        ctx = get_recording_context()
        if ctx:
            return ctx
            
    # 2. Try 'record()' session (EpiRecorderSession)
    if get_current_session:
        session = get_current_session()
        if session:
            return session
    
    return None

def simulate_research_agent():
    # Define our simulated mission
    mission = "Research latest advancements in Solid State Batteries for 2026"
    
    print(f"[AGENT] Starting mission: {mission}")
    
    # Get recorder
    ctx = get_recorder()
    if not ctx:
        print("[ERROR] Cannot record steps - not in valid context", file=sys.stderr)
        return

    # Check which method to use (Session has log_step, Context has add_step)
    log_func = getattr(ctx, "add_step", getattr(ctx, "log_step", None))
    if not log_func:
        print("[ERROR] Recorder has no add_step/log_step method", file=sys.stderr)
        return

    start_time = time.time()
    
    # 1. INITIAL THOUGHT / PLANNING
    # =============================
    print("[AGENT] Planning research strategy...")
    time.sleep(1) # Simulate think time
    
    planning_prompt = {
        "model": "gpt-4-turbo",
        "messages": [
            {"role": "system", "content": "You are a senior research analyst AI."},
            {"role": "user", "content": f"Research topic: {mission}. Create a plan."}
        ]
    }
    
    planning_response = {
        "model": "gpt-4-turbo",
        "choices": [{
            "message": {
                "role": "assistant", 
                "content": "I will break this down into 3 steps:\n1. Search for recent breakthroughs.\n2. Analyze stability data.\n3. Summarize findings in a report."
            },
            "finish_reason": "stop"
        }],
        "usage": {"total_tokens": 150}
    }
    
    # Manually log these as if they happened via API
    log_func("llm.request", planning_prompt)
    log_func("llm.response", planning_response)
    
    # 2. TOOL USE: SEARCH
    # ===================
    print("[AGENT] Executing search tool...")
    time.sleep(1.5)
    
    tool_call_prompt = {
        "model": "gpt-4-turbo",
        "messages": [
            {"role": "user", "content": "Execute step 1."}
        ]
    }
    
    tool_call_response = {
        "model": "gpt-4-turbo",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_search_123",
                    "type": "function",
                    "function": {
                        "name": "search_database",
                        "arguments": "{\"query\": \"solid state battery breakthrough 2025 2026\", \"limit\": 3}"
                    }
                }]
            }
        }]
    }
    
    log_func("llm.request", tool_call_prompt)
    log_func("llm.response", tool_call_response)
    
    # Log the actual tool execution (Custom Step)
    search_results = [
        {"title": "Toyota announces 700-mile solid state battery", "date": "2025-11-15", "source": "TechDaily"},
        {"title": "MIT discovers new electrolyte material", "date": "2026-01-02", "source": "ScienceNet"},
        {"title": "QuantumScape creates flexible ceramic separator", "date": "2025-12-10", "source": "BatteryJournal"}
    ]
    
    log_func("tool.execution", {
        "tool": "search_database",
        "input": {"query": "solid state battery breakthrough 2025 2026"},
        "output": search_results,
        "duration_ms": 450
    })
    
    # 3. ANALYSIS & REASONING
    # =======================
    print("[AGENT] Analyzing findings...")
    time.sleep(2)
    
    analysis_prompt = {
        "model": "gpt-4-turbo",
        "messages": [
            {"role": "user", "content": f"Analyze these search results: {json.dumps(search_results)}"}
        ]
    }
    
    analysis_content = """
    Based on the search results, there are two major trends:
    1. **Extended Range**: Toyota's 700-mile claim suggests commercial viability is near.
    2. **Material Science**: New electrolytes from MIT and ceramic separators from QuantumScape solve the dendrite problem.
    
    Conclusion: 2026 is a pivotal year for solid-state commercialization.
    """
    
    analysis_response = {
        "model": "gpt-4-turbo",
        "choices": [{
            "message": {
                "role": "assistant", 
                "content": analysis_content
            }
        }],
        "usage": {"total_tokens": 450}
    }
    
    log_func("llm.request", analysis_prompt)
    log_func("llm.response", analysis_response)
    
    # 4. ACTION: WRITE REPORT
    # =======================
    print("[AGENT] Writing final report...")
    
    report_file = Path("battery_report_2026.md")
    report_content = f"# Solid State Battery Report 2026\n\n{analysis_content}\n\n*Generated by Agent Simulation*"
    report_file.write_text(report_content, encoding="utf-8")
    
    # Log file creation (File IO)
    log_func("file.write", {
        "path": str(report_file),
        "size_bytes": len(report_content),
        "operation": "write"
    })
    
    print(f"[OK] MISSION COMPLETE. Report saved to {report_file}")

if __name__ == "__main__":
    # If running via 'epi run', session is already active
    if get_recorder():
        simulate_research_agent()
    else:
        # If running standalone
        print("Starting standalone recording session...")
        with record() as r:
            simulate_research_agent()


