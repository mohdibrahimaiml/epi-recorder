#!/usr/bin/env python3
"""A small refund agent, recorded with EPI, for the pilot demo.

Runs deterministically with **no API key** (``--offline`` is the default): a
scripted "model" makes the decision, so the demo is repeatable. ``--openai``
uses OpenAI through ``wrap_openai`` when ``OPENAI_API_KEY`` is set.

The agent asks for two human approvals (``refund-7``, ``refund-8``) and records
the run with :func:`epi_recorder.record`. If LangGraph is installed the same
decisions are executed as a three-node graph; without it a tiny scripted graph
runs instead. Either way the recorded steps are identical.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from epi_recorder import get_current_session, record


def _log(kind: str, **content):
    session = get_current_session()
    if session is None:
        raise RuntimeError("agent.py must run inside record()")
    session.log(kind, content)


def _lookup(ref: str) -> int:
    _log("tool.call", tool="lookup_ledger", id=ref)
    balance = 250
    _log("tool.response", tool="lookup_ledger", ok=True, balance=balance)
    return balance


def _decide(balance: int) -> str:
    decision = "approve" if balance <= 500 else "escalate"
    _log("agent.decision", decision=decision, reason=f"balance {balance} is within the limit")
    return decision


def _request_approvals() -> None:
    session = get_current_session()
    if session is None:
        raise RuntimeError("agent.py must run inside record()")
    for approval_id, action in (("refund-7", "refund REF-7"), ("refund-8", "refund REF-8")):
        session.approval_request(
            action,
            approval_id=approval_id,
            reason="high-value refund needs a human decision",
        )
    # Deliberately NO self-reported approval response step: the agent does not
    # answer its own request. The answer is the approver's signed approval,
    # added after sealing with their own key (epi review <file.epi> approve),
    # and strict completeness counts that bound approval as the response.


def _run_scripted() -> None:
    _request_approvals()
    _decide(_lookup("REF-7"))


def _run_langgraph() -> bool:
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return False

    class _State(dict):
        pass

    def request_approvals(state):
        _request_approvals()
        return state

    def lookup(state):
        _lookup("REF-7")
        return state

    def decide(state):
        _decide(250)
        return state

    graph = StateGraph(_State)
    graph.add_node("request_approvals", request_approvals)
    graph.add_node("lookup", lookup)
    graph.add_node("decide", decide)
    graph.set_entry_point("request_approvals")
    graph.add_edge("request_approvals", "lookup")
    graph.add_edge("lookup", "decide")
    graph.add_edge("decide", END)
    try:
        graph.compile().invoke(_State())
    except Exception as exc:  # a LangGraph API change must not hide the demo
        print(f"[agent] LangGraph run failed ({exc}); using the scripted graph.", file=sys.stderr)
        return False
    return True


def _run_openai() -> None:
    from openai import OpenAI

    from epi_recorder import wrap_openai

    client = wrap_openai(OpenAI())
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Approve refund REF-7? Answer in one word."}],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refund agent recorded with EPI.")
    parser.add_argument("--out", default="run.epi", help="Output .epi path.")
    parser.add_argument("--offline", dest="offline", action="store_true", default=True)
    parser.add_argument("--openai", dest="offline", action="store_false")
    args = parser.parse_args(argv)

    if not args.offline:
        if not os.environ.get("OPENAI_API_KEY"):
            print("--openai needs OPENAI_API_KEY; run without it for the offline demo.", file=sys.stderr)
            return 2
        with record(args.out, goal="Refund decision with two human approvals"):
            _request_approvals()
            _run_openai()
        return 0

    with record(args.out, goal="Refund decision with two human approvals"):
        if _run_langgraph():
            print("[agent] ran as a LangGraph graph")
        else:
            print("[agent] LangGraph not installed — ran the scripted graph")
            _run_scripted()
    print(f"[agent] sealed {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
