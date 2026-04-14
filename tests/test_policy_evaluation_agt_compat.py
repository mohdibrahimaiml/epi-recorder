"""Unit test verifying the `agt_compat` extension is present in
policy evaluation outputs produced by `FaultAnalyzer`.
"""

from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.policy import EPIPolicy, PolicyRule


def _make_step(index, kind, content, timestamp="2025-01-01T00:00:00"):
    import json
    return json.dumps({"index": index, "kind": kind, "content": content, "timestamp": timestamp})


def test_policy_evaluation_contains_agt_compat():
    # Steps that will trigger a threshold rule (amount > 10000)
    steps = "\n".join([
        _make_step(0, "session.start", {"workflow_name": "test"}),
        _make_step(1, "tool.response", {"tool": "lookup_order", "amount": 20000.0}),
        _make_step(2, "agent.decision", {"decision": "approve_payment"}),
        _make_step(3, "session.end", {"success": True}),
    ])

    policy = EPIPolicy(
        system_name="test",
        system_version="1.0",
        policy_version="2026-01-01",
        rules=[
            PolicyRule(
                id="R010",
                name="Large Transaction Approval",
                severity="high",
                description="Amounts above 10k require human approval.",
                type="threshold_guard",
                threshold_value=10000,
                threshold_field="amount",
                required_action="human_approval",
            )
        ],
    )

    analyzer = FaultAnalyzer(policy=policy)
    result = analyzer.analyze(steps)
    peval = result.to_policy_evaluation_dict()

    assert peval is not None
    assert "agt_compat" in peval
    agt = peval["agt_compat"]
    assert agt.get("controls_evaluated") == peval.get("controls_evaluated")
    assert isinstance(agt.get("controls_failed"), int)
    assert agt.get("compliance_status") in {"passed", "failed"}
