"""Signed pre-action approvals: gate, witness order, forged steps, reuse."""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()


def _policy(path: Path, tool: str = "refund") -> Path:
    path.write_text(
        json.dumps(
            {
                "policy_format_version": "2.0",
                "policy_id": "preaction",
                "system_name": "claims",
                "system_version": "1.0",
                "policy_version": "1.0",
                "rules": [
                    {
                        "id": "R-APPROVE",
                        "name": "Approval required",
                        "severity": "critical",
                        "description": "The tool needs approval before it runs.",
                        "type": "approval_guard",
                        "mode": "require_approval",
                        "approval_action": tool,
                        "approval_policy_ref": "approval-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _env(monkeypatch, tmp_path: Path) -> dict:
    agent_home = tmp_path / "agent-home"
    approver_home = tmp_path / "approver-home"
    monkeypatch.setenv("EPI_HOME", str(agent_home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(agent_home / "keys"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(agent_home / "approver_keys"))
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(agent_home / "trusted_approvers"))
    monkeypatch.setenv("EPI_APPROVAL_INBOX_DIR", str(agent_home / "approvals" / "inbox"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    monkeypatch.setenv("EPI_KEY_PASSWORD", "preaction-password")
    monkeypatch.delenv("EPI_AUTO_APPROVE", raising=False)
    monkeypatch.chdir(tmp_path)
    return {"agent": agent_home, "approver": approver_home}


def _approver_key(approver_home: Path, name: str = "alice@bank.com"):
    from cryptography.hazmat.primitives import serialization

    from epi_core.keys import KeyManager, key_fingerprint

    km = KeyManager(keys_dir=approver_home / "keys")
    if not km.has_key(name):
        km.generate_keypair(name)
    private = km.load_private_key(name)
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private, public, key_fingerprint(public, grouped=False)


def _pin(name: str, public_hex: str) -> None:
    from epi_core.approvers import ApproverRegistry

    ApproverRegistry().add(name, public_hex, overwrite=True)


def _signer(
    inbox: Path,
    private,
    public: str,
    fingerprint: str,
    *,
    decision: str = "approve",
    signed_at: str | None = None,
    stop: threading.Event,
) -> threading.Thread:
    from epi_core.pre_action import sign_response

    def _run() -> None:
        while not stop.is_set():
            for request_path in inbox.glob("*.request.json"):
                request_id = request_path.name.split(".")[0]
                response_path = inbox / f"{request_id}.response.json"
                if response_path.exists():
                    continue
                try:
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    response = sign_response(
                        request,
                        decision=decision,
                        approver="alice@bank.com",
                        key_fingerprint=fingerprint,
                        public_key=public,
                        private_key=private,
                        reason="checked",
                        signed_at=signed_at,
                    )
                    response_path.write_text(
                        json.dumps(response, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass
            time.sleep(0.05)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _run_gate(
    monkeypatch,
    tmp_path: Path,
    *,
    decision: str = "approve",
    signed_at: str | None = None,
    timeout: float = 10,
    colocated: bool = False,
    witness_url: str | None = None,
):
    from epi_recorder import record
    from epi_recorder.trust import ApprovalGate, RuntimePolicyEngine, TrustInterceptor

    env = _env(monkeypatch, tmp_path)
    if colocated:
        # The agent can read the approver private key: openly flagged.
        monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(env["approver"] / "keys"))
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    policy = _policy(tmp_path / "policy.json")
    inbox = Path(os.environ["EPI_APPROVAL_INBOX_DIR"])
    calls: list[dict] = []
    stop = threading.Event()
    thread = _signer(
        inbox,
        private,
        public,
        fingerprint,
        decision=decision,
        signed_at=signed_at,
        stop=stop,
    )

    def refund(amount: int, customer: str) -> dict:
        calls.append({"amount": amount, "customer": customer})
        return {"ok": True}

    out = tmp_path / "decision.epi"
    try:
        with record(
            str(out),
            goal="refund",
            witness_url=witness_url,
            witness_secret="preaction-secret" if witness_url else None,
        ) as epi:
            gate = ApprovalGate(
                default_timeout=timeout,
                workflow_id="wf-1",
                witness_url=witness_url,
                witness_secret="preaction-secret" if witness_url else None,
            )
            engine = RuntimePolicyEngine(str(policy), enable_blocking=True)
            interceptor = TrustInterceptor(engine, gate=gate)
            safe = interceptor.wrap_tool(refund, "refund")
            safe(amount=5000, customer="CUST-1")
    finally:
        stop.set()
        thread.join(timeout=2)
    return out, calls, inbox


def _log(payloads: list[dict], path: Path, *, swap: bool = False) -> Path:
    entries = []
    for index, payload in enumerate(payloads):
        entry = dict(payload)
        entry["received_at"] = f"2026-11-08T10:00:0{index}+00:00"
        entries.append(entry)
    if swap:
        response = next(e for e in entries if e.get("type") == "epi.approval_response")
        executed = next(e for e in entries if e.get("type") == "epi.approval_executed")
        response["received_at"] = "2026-11-08T10:00:09+00:00"
        executed["received_at"] = "2026-11-08T10:00:01+00:00"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _verify(path: Path, log: Path | None = None) -> tuple[dict, int]:
    args = ["verify", str(path), "--json", "--require-pre-action-approval"]
    if log is not None:
        args += ["--witness-log", str(log)]
    result = runner.invoke(cli_app, args)
    return json.loads(result.output), result.exit_code


def test_happy_path_with_witness_order(monkeypatch, tmp_path: Path) -> None:
    from tests.test_seal_witness import SECRET, _serve

    server, url = _serve()
    try:
        out, calls, inbox = _run_gate(monkeypatch, tmp_path, witness_url=url)
        assert calls == [{"amount": 5000, "customer": "CUST-1"}]
        assert list(inbox.glob("*.response.json"))
        from tests.test_seal_witness import CaptureHandler

        payloads = [json.loads(item["body"]) for item in CaptureHandler.received]
        log = _log(payloads, tmp_path / "received.jsonl")
        report, code = _verify(out, log)
        item = report["pre_action_approval"]["requests"][0]
        assert item["status"] == "approved_before_action", item
        assert item["basis"] == "witness received_at (independent)"
        assert item["approver_key_colocated"] is False
        assert code == 0, report["decision"]
    finally:
        server.shutdown()


def test_deny_blocks_the_tool(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder.trust import PreActionApprovalBlocked

    with pytest.raises(PreActionApprovalBlocked):
        _run_gate(monkeypatch, tmp_path, decision="deny")


def test_timeout_blocks_the_tool(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record

    env = _env(monkeypatch, tmp_path)
    policy = _policy(tmp_path / "policy.json")
    calls: list = []

    def refund() -> None:
        calls.append(1)

    from epi_recorder.trust import (
        ApprovalGate,
        PreActionApprovalBlocked,
        RuntimePolicyEngine,
        TrustInterceptor,
    )

    with pytest.raises(PreActionApprovalBlocked):
        with record(str(tmp_path / "timeout.epi")) as epi:
            gate = ApprovalGate(default_timeout=1)
            engine = RuntimePolicyEngine(str(policy), enable_blocking=True)
            safe = TrustInterceptor(engine, gate=gate).wrap_tool(refund, "refund")
            safe()
    assert calls == []


def test_expired_approval_is_rejected(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder.trust import PreActionApprovalBlocked

    with pytest.raises(PreActionApprovalBlocked):
        _run_gate(
            monkeypatch,
            tmp_path,
            signed_at="2030-01-01T00:00:00+00:00",
            timeout=10,
        )


def test_colocated_approver_key_is_openly_flagged(monkeypatch, tmp_path: Path) -> None:
    from tests.test_seal_witness import _serve

    server, url = _serve()
    try:
        out, _calls, _inbox = _run_gate(
            monkeypatch, tmp_path, colocated=True, witness_url=url
        )
        from tests.test_seal_witness import CaptureHandler

        payloads = [json.loads(item["body"]) for item in CaptureHandler.received]
        log = _log(payloads, tmp_path / "received.jsonl")
        report, code = _verify(out, log)
        item = report["pre_action_approval"]["requests"][0]
        assert item["status"] == "approved_before_action"
        assert item["approver_key_colocated"] is True
        assert code == 1
        human = runner.invoke(
            cli_app,
            [
                "verify",
                str(out),
                "--witness-log",
                str(log),
                "--require-pre-action-approval",
            ],
        )
        assert "approver key on agent host" in human.output
    finally:
        server.shutdown()


def test_denied_but_executed_is_detected(monkeypatch, tmp_path: Path) -> None:
    from epi_core.approvers import ApproverRegistry
    from epi_core.pre_action import (
        DENIED_BUT_EXECUTED,
        analyze,
        build_request,
        sign_response,
    )

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    request = build_request(
        tool="refund",
        arguments={"amount": 5000},
        workflow_id="wf",
        request_id="aprq_deny",
        nonce="n" * 32,
        timeout_seconds=600,
    )
    response = sign_response(
        request,
        decision="deny",
        approver="alice@bank.com",
        key_fingerprint=fingerprint,
        public_key=public,
        private_key=private,
    )
    steps = [
        {"index": 0, "kind": "approval.request", "content": request},
        {
            "index": 1,
            "kind": "approval.response",
            "content": {
                "request_id": request["request_id"],
                "request_digest": request["request_digest"],
                "response": response,
                "approver_key_colocated": False,
            },
        },
        {
            "index": 2,
            "kind": "approval.executed",
            "content": {
                "request_id": request["request_id"],
                "args_digest": request["args_digest"],
            },
        },
    ]
    result = analyze(
        steps,
        None,
        registry=ApproverRegistry(),
        sealing_key="00" * 32,
    )
    assert result["requests"][0]["status"] == DENIED_BUT_EXECUTED


def test_approval_cli_exports_signs_and_imports(monkeypatch, tmp_path: Path) -> None:
    from epi_core.pre_action import build_request, request_digest

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    inbox = Path(os.environ["EPI_APPROVAL_INBOX_DIR"])
    inbox.mkdir(parents=True, exist_ok=True)
    request = build_request(
        tool="refund",
        arguments={"amount": 5000, "customer": "CUST-1"},
        workflow_id="wf",
        request_id="aprq_cli",
        nonce="n" * 32,
        timeout_seconds=600,
        vendor_description="refund the customer",
    )
    (inbox / "aprq_cli.request.json").write_text(json.dumps(request), encoding="utf-8")

    exported = tmp_path / "exported-request.json"
    result = runner.invoke(
        cli_app, ["approval", "export", "aprq_cli", "--out", str(exported)]
    )
    assert result.exit_code == 0, result.output
    assert exported.is_file()

    response_path = tmp_path / "response.json"
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(env["approver"] / "keys"))
    signed = runner.invoke(
        cli_app,
        [
            "approval",
            "sign",
            str(exported),
            "--as",
            "alice@bank.com",
            "--out",
            str(response_path),
            "--yes",
        ],
    )
    assert signed.exit_code == 0, signed.output
    assert "5000" in signed.output
    assert "Vendor description" in signed.output

    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(env["agent"] / "approver_keys"))
    imported = runner.invoke(cli_app, ["approval", "import", str(response_path)])
    assert imported.exit_code == 0, imported.output
    assert (inbox / "aprq_cli.response.json").is_file()

    listing = runner.invoke(cli_app, ["approval", "list", "--json"])
    assert listing.exit_code == 0, listing.output
    rows = json.loads(listing.output)["requests"]
    assert rows[0]["answered"] is True


def test_lying_vendor_description_is_not_the_approved_arguments(
    monkeypatch, tmp_path: Path
) -> None:
    from epi_core.pre_action import build_request, request_digest

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    request = build_request(
        tool="refund",
        arguments={"amount": 5000},
        workflow_id="wf",
        request_id="aprq_lie",
        nonce="n" * 32,
        timeout_seconds=600,
        vendor_description="refund $50",
    )
    # The vendor rewrites the display and re-seals the request digest: the
    # description says $50 while args_digest still covers $5000.
    request["args_display"]["amount"] = 50
    request["request_digest"] = request_digest(request)
    request_path = tmp_path / "lie.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(env["approver"] / "keys"))
    result = runner.invoke(
        cli_app,
        ["approval", "sign", str(request_path), "--as", "alice@bank.com", "--yes"],
    )
    assert result.exit_code == 1
    assert "displayed arguments do not match the approved digest" in result.output


def test_forged_chain_order_is_caught_by_the_witness(monkeypatch, tmp_path: Path) -> None:
    from tests.test_seal_witness import _serve

    server, url = _serve()
    try:
        out, _calls, _inbox = _run_gate(monkeypatch, tmp_path, witness_url=url)
        from tests.test_seal_witness import CaptureHandler

        payloads = [json.loads(item["body"]) for item in CaptureHandler.received]
        forged = _log(payloads, tmp_path / "forged.jsonl", swap=True)
        report, code = _verify(out, forged)
        item = report["pre_action_approval"]["requests"][0]
        assert item["status"] == "action_before_approval", item
        assert code == 1
    finally:
        server.shutdown()


def test_args_change_blocks_and_is_recorded(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record
    from epi_recorder.trust import (
        ApprovalGate,
        PreActionApprovalBlocked,
        RuntimePolicyEngine,
        TrustInterceptor,
    )

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    stop = threading.Event()
    thread = _signer(
        Path(os.environ["EPI_APPROVAL_INBOX_DIR"]),
        private,
        public,
        fingerprint,
        stop=stop,
    )
    from epi_core.container import EPIContainer

    try:
        with record(str(tmp_path / "args.epi")) as epi:
            gate = ApprovalGate(default_timeout=10)
            engine = RuntimePolicyEngine(str(_policy(tmp_path / "policy.json")), enable_blocking=True)
            grant = gate.request_signed(
                tool="refund", arguments={"amount": 5000, "customer": "CUST-1"}
            )
            with pytest.raises(PreActionApprovalBlocked):
                grant.release(arguments={"amount": 1, "customer": "CUST-1"})
    finally:
        stop.set()
        thread.join(timeout=2)
    steps = EPIContainer.read_steps(tmp_path / "args.epi")
    assert any(step.get("kind") == "approval.args_mismatch" for step in steps)


def test_nonce_reuse_blocks_the_second_execution(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record
    from epi_recorder.trust import (
        ApprovalGate,
        PreActionApprovalBlocked,
        RuntimePolicyEngine,
    )

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    stop = threading.Event()
    thread = _signer(
        Path(os.environ["EPI_APPROVAL_INBOX_DIR"]),
        private,
        public,
        fingerprint,
        stop=stop,
    )
    try:
        with record(str(tmp_path / "reuse.epi")) as epi:
            gate = ApprovalGate(default_timeout=10)
            grant = gate.request_signed(tool="refund", arguments={"amount": 1})
            grant.release(arguments={"amount": 1})
            with pytest.raises(PreActionApprovalBlocked):
                grant.release(arguments={"amount": 1})
    finally:
        stop.set()
        thread.join(timeout=2)


def test_sealing_key_and_unpinned_key_do_not_unlock(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record
    from epi_recorder.trust import ApprovalGate, PreActionApprovalBlocked
    from epi_core.keys import KeyManager

    env = _env(monkeypatch, tmp_path)
    inbox = Path(os.environ["EPI_APPROVAL_INBOX_DIR"])
    sealing = KeyManager()
    if not sealing.has_key("default"):
        sealing.generate_keypair("default")
    sealing_key = sealing.load_private_key("default")
    sealing_pub = sealing.load_public_key("default").hex()

    # Sealing key: explicitly rejected.
    stop = threading.Event()
    thread = _signer(inbox, sealing_key, sealing_pub, "", stop=stop)
    try:
        with pytest.raises(PreActionApprovalBlocked):
            with record(str(tmp_path / "seal.epi")):
                gate = ApprovalGate(default_timeout=5, sealing_key=sealing_pub)
                grant = gate.request_signed(tool="refund", arguments={"amount": 1}, timeout=5)
                grant.release(arguments={"amount": 1})
    finally:
        stop.set()
        thread.join(timeout=2)

    # Unpinned key: rejected by the approver registry.
    private, public, fingerprint = _approver_key(env["approver"], "mallory@example.test")
    stop = threading.Event()
    thread = _signer(inbox, private, public, fingerprint, stop=stop)
    try:
        with pytest.raises(PreActionApprovalBlocked):
            with record(str(tmp_path / "unpinned.epi")):
                gate = ApprovalGate(default_timeout=5)
                grant = gate.request_signed(tool="refund", arguments={"amount": 1}, timeout=5)
                grant.release(arguments={"amount": 1})
    finally:
        stop.set()
        thread.join(timeout=2)


def test_auto_approve_is_recorded_as_not_human(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record
    from epi_recorder.trust import ApprovalGate, RuntimePolicyEngine, TrustInterceptor

    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_AUTO_APPROVE", "1")
    calls = []

    def refund() -> None:
        calls.append(1)

    out = tmp_path / "auto.epi"
    with record(str(out)):
        gate = ApprovalGate(default_timeout=5)
        engine = RuntimePolicyEngine(str(_policy(tmp_path / "policy.json")), enable_blocking=True)
        TrustInterceptor(engine, gate=gate).wrap_tool(refund, "refund")()
    assert calls == [1]

    from epi_core.container import EPIContainer
    from epi_core.pre_action import analyze, AUTO_APPROVED

    steps = EPIContainer.read_steps(out)
    result = analyze(steps)
    assert result["requests"][0]["status"] == AUTO_APPROVED


def test_old_artifact_has_no_pre_action_claim(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record

    _env(monkeypatch, tmp_path)
    out = tmp_path / "old.epi"
    with record(str(out)) as epi:
        epi.log_step("tool.call", {"tool": "refund"})

    from epi_core.container import EPIContainer
    from epi_core.pre_action import NOT_USED, analyze

    result = analyze(EPIContainer.read_steps(out))
    assert result["status"] == NOT_USED
    assert result["requests"] == []


def test_no_session_persists_files_and_warns(monkeypatch, tmp_path: Path, capsys) -> None:
    from epi_recorder.trust import ApprovalGate

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    inbox = Path(os.environ["EPI_APPROVAL_INBOX_DIR"])
    stop = threading.Event()
    thread = _signer(inbox, private, public, fingerprint, stop=stop)
    try:
        gate = ApprovalGate(default_timeout=10)
        grant = gate.request_signed(tool="refund", arguments={"amount": 1})
        grant.release(arguments={"amount": 1})
    finally:
        stop.set()
        thread.join(timeout=2)
    assert list(inbox.glob("*.request.json"))
    assert list(inbox.glob("*.response.json"))
    assert list(inbox.glob("*.approval_executed.json"))
    assert "no recording session" in capsys.readouterr().err


def test_thread_pool_with_context_propagates_the_sink(monkeypatch, tmp_path: Path) -> None:
    from epi_recorder import record
    from epi_recorder.trust import ApprovalGate, RuntimePolicyEngine, TrustInterceptor

    env = _env(monkeypatch, tmp_path)
    private, public, fingerprint = _approver_key(env["approver"])
    _pin("alice@bank.com", public)
    stop = threading.Event()
    thread = _signer(
        Path(os.environ["EPI_APPROVAL_INBOX_DIR"]),
        private,
        public,
        fingerprint,
        stop=stop,
    )
    out = tmp_path / "thread.epi"
    try:
        with record(str(out)):
            gate = ApprovalGate(default_timeout=10)
            engine = RuntimePolicyEngine(str(_policy(tmp_path / "policy.json")), enable_blocking=True)
            safe = TrustInterceptor(engine, gate=gate).wrap_tool(lambda: "ok", "refund")
            context = contextvars.copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(context.run, safe).result() == "ok"
    finally:
        stop.set()
        thread.join(timeout=2)
    from epi_core.container import EPIContainer

    assert any(
        step.get("kind") == "approval.executed"
        for step in EPIContainer.read_steps(out)
    )


def test_witness_audit_reports_approval_reuse(monkeypatch, tmp_path: Path) -> None:
    from epi_core.seal_ledger import analyze

    entry = {
        "schema": "epi-witness/v1",
        "type": "epi.approval_executed",
        "request_id": "aprq_1",
        "request_digest": "a",
        "args_digest": "b",
        "response_signature_hash": "c",
        "executed_at": "2026-11-08T10:00:00+00:00",
        "received_at": "2026-11-08T10:00:01+00:00",
    }
    result = analyze([entry, {**entry, "received_at": "2026-11-08T10:00:02+00:00"}])
    assert result["problems"]["approval_reuse"] == 1
    assert result["ok"] is False
