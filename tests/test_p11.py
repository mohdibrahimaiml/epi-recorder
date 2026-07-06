import json
from epi_core.fault_analyzer import FaultAnalyzer

NL = chr(10)


class TestPass11CoverageGap:
    def test_empty_artifact_fires(self):
        meta = {"goal": "agent pipeline"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        p11 = [f for f in r._all_flags() if f.rule_id == "P11"]
        assert len(p11) == 1

    def test_tool_steps_short_circuit(self):
        meta = {"goal": "openai agent orchestration"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"tool.call","content":{"tool":"lookup"}},{"index":2,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        assert len([f for f in r._all_flags() if f.rule_id == "P11"]) == 0

    def test_llm_steps_short_circuit(self):
        meta = {"goal": "llm classification with claude"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"llm.request","content":{"model":"claude-3"}},{"index":2,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        assert len([f for f in r._all_flags() if f.rule_id == "P11"]) == 0

    def test_loan_decision_v2_no_false_flag(self):
        meta = {"goal": "loan decision v2"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"llm.request","content":{"model":"gpt-4"}},{"index":2,"kind":"llm.response","content":{"result":"approved"}},{"index":3,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        assert len([f for f in r._all_flags() if f.rule_id == "P11"]) == 0

    def test_hello_world_no_flag(self):
        meta = {"goal": "simple script"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        assert len([f for f in r._all_flags() if f.rule_id == "P11"]) == 0

    def test_anthropic_tool_no_flag(self):
        meta = {"goal": "claude-powered claim analysis", "notes": "Uses Anthropic"}
        steps = [{"index":0,"kind":"session.start","content":{"workflow":"test"}},{"index":1,"kind":"tool.call","content":{"tool":"fraud_check"}},{"index":2,"kind":"session.end","content":{"success":True}}]
        r = FaultAnalyzer(manifest_meta=meta).analyze(NL.join(json.dumps(s) for s in steps))
        assert len([f for f in r._all_flags() if f.rule_id == "P11"]) == 0
