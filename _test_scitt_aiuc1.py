from epi_recorder import record  
with record("scitt_test.epi", workflow_name="Test-SCITT-AIUC1", goal="verify alignment") as epi:  
    epi.log_step("tool.call", {"tool": "test", "input": {"x": 1}})  
    epi.log_step("tool.response", {"tool": "test", "output": {"y": 2}})  
    epi.log_step("agent.decision", {"decision": "approved", "confidence": 0.95})  
