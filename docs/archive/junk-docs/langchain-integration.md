# EPI + LangChain Integration  
  
## Overview  
  
EPI Recorder provides `EPICallbackHandler` - a LangChain-compatible callback handler that captures every LLM call, tool invocation, chain step, and agent action into a signed .epi evidence file.  
  
## Quick Start  
  
\`\`\`python  
pip install epi-recorder langchain-core  
\`\`\`  
  
\`\`\`python  
from epi_recorder.integrations.langchain import EPICallbackHandler  
from langchain_openai import ChatOpenAI  
from epi_recorder import record  
  
llm = ChatOpenAI(model="gpt-4", callbacks=[EPICallbackHandler()])  
  
with record("agent-run.epi"):  
    response = llm.invoke("Analyze this application")  
\`\`\`  
  
## Features  
  
- Captures on_llm_start, on_llm_end, on_llm_error  
- Captures on_tool_start, on_tool_end, on_tool_error  
- Captures on_chain_start, on_chain_end  
- Captures on_agent_action, on_agent_finish  
- Auto-signs with Ed25519  
- Produces browser-verifiable .epi files  
  
## Integration Path  
  
The `EPICallbackHandler` is modeled on LangChain's `LangChainTracer`. It can be submitted as an optional dependency to langchain-core following the same pattern. The handler code is at:  
  
\`\`\`  
epi_recorder/integrations/langchain.py  
