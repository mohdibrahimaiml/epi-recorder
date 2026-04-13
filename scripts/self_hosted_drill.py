from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any, dict[str, str]]:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                parsed = json.loads(raw.decode("utf-8"))
            else:
                parsed = raw
            return response.status, parsed, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            parsed = raw.decode("utf-8", errors="replace")
        return exc.code, parsed, dict(exc.headers.items())


def _wait_for(
    label: str,
    operation,
    *,
    timeout: float = 60.0,
    interval: float = 0.25,
):
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return operation()
        except Exception as exc:  # pragma: no cover - best effort poll loop
            last_error = exc
            time.sleep(interval)
    if last_error:
        raise RuntimeError(f"Timed out waiting for {label}: {last_error}") from last_error
    raise RuntimeError(f"Timed out waiting for {label}")


def _start_process(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> subprocess.Popen[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            creationflags=creationflags,
        )
    except Exception:
        stdout_file.close()
        stderr_file.close()
        raise


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _run_command(command: list[str], *, cwd: Path, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _find_restored_storage(restore_root: Path) -> Path:
    candidates = list(restore_root.rglob("cases.sqlite3"))
    if candidates:
        return candidates[0].parent
    storage_dir = restore_root / "storage"
    if storage_dir.exists():
        return storage_dir
    raise FileNotFoundError("No restored storage directory found after restore.")


def _wait_for_case(gateway_url: str, token: str, *, timeout: float = 30.0) -> dict[str, Any]:
    def _poll():
        status, payload, _ = _json_request(
            f"{gateway_url}/api/cases",
            headers=_auth_headers(token),
            timeout=10.0,
        )
        if status != 200:
            raise RuntimeError(f"/api/cases returned {status}: {payload}")
        cases = payload.get("cases") or []
        if not cases:
            raise RuntimeError("No shared cases available yet.")
        return cases[0]

    return _wait_for("shared case", _poll, timeout=timeout, interval=0.25)


def _wait_for_ready(gateway_url: str, *, timeout: float = 60.0) -> dict[str, Any]:
    def _poll():
        status, payload, _ = _json_request(f"{gateway_url}/ready", timeout=5.0)
        if status != 200 or not payload.get("ok"):
            raise RuntimeError(f"/ready returned {status}: {payload}")
        return payload

    return _wait_for("gateway readiness", _poll, timeout=timeout, interval=0.25)


def _wait_for_viewer(viewer_url: str, *, timeout: float = 30.0) -> None:
    def _poll():
        request = urllib.request.Request(viewer_url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=5.0) as response:
            if response.status != 200:
                raise RuntimeError(f"Viewer returned {response.status}")
            return None

    _wait_for("viewer", _poll, timeout=timeout, interval=0.25)


def _parse_verify_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    stdout = (result.stdout or "").strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": stdout}


def run_drill(args: argparse.Namespace) -> dict[str, Any]:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_root = args.root.resolve() / run_id
    live_root = run_root / "live"
    restore_root = run_root / "restore"
    logs_root = run_root / "logs"
    storage_dir = live_root / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    restore_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    gateway_url = f"http://{args.host}:{args.gateway_port}"
    restored_gateway_url = f"http://{args.host}:{args.restored_gateway_port}"
    viewer_url = f"http://{args.host}:{args.viewer_port}/web_viewer/index.html"
    export_path = run_root / "drill-export.epi"
    backup_path = run_root / "epi-gateway-backup.zip"

    gateway_process: subprocess.Popen[str] | None = None
    restored_gateway_process: subprocess.Popen[str] | None = None
    viewer_process: subprocess.Popen[str] | None = None

    summary: dict[str, Any] = {
        "run_root": str(run_root),
        "gateway_url": gateway_url,
        "restored_gateway_url": restored_gateway_url,
        "viewer_url": viewer_url,
        "storage_dir": str(storage_dir),
        "access_token_enabled": bool(args.access_token),
        "retention_mode": args.retention_mode,
        "proxy_failure_mode": args.proxy_failure_mode,
    }

    try:
        gateway_process = _start_process(
            [
                sys.executable,
                "-m",
                "epi_cli.main",
                "gateway",
                "serve",
                "--host",
                args.host,
                "--port",
                str(args.gateway_port),
                "--storage-dir",
                str(storage_dir),
                "--batch-size",
                "1",
                "--batch-timeout",
                "0.1",
                "--retention-mode",
                args.retention_mode,
                "--proxy-failure-mode",
                args.proxy_failure_mode,
                "--access-token",
                args.access_token,
            ],
            cwd=REPO_ROOT,
            stdout_path=logs_root / "gateway.out.log",
            stderr_path=logs_root / "gateway.err.log",
        )
        viewer_process = _start_process(
            [
                sys.executable,
                "-m",
                "http.server",
                str(args.viewer_port),
                "--bind",
                args.host,
            ],
            cwd=REPO_ROOT,
            stdout_path=logs_root / "viewer.out.log",
            stderr_path=logs_root / "viewer.err.log",
        )

        summary["ready"] = _wait_for_ready(gateway_url, timeout=args.startup_timeout)
        _wait_for_viewer(viewer_url, timeout=args.startup_timeout)
        status, health, _ = _json_request(f"{gateway_url}/health", timeout=10.0)
        if status != 200:
            raise RuntimeError(f"/health returned {status}: {health}")
        summary["health"] = health

        capture_payload = {
            "provider": "openai-compatible",
            "request": {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You review consequential refund decisions."},
                    {
                        "role": "user",
                        "content": "Refund order ORD-9001 for $900 after damage claim review. Approve or escalate?",
                    },
                ],
            },
            "response": {
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Escalate for human approval because the refund exceeds the automatic approval limit.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
            "meta": {
                "trace_id": "trace-self-hosted-drill",
                "decision_id": "decision-self-hosted-drill",
                "case_id": "refund-drill-001",
                "workflow_name": "Refund approvals",
                "source_app": "self-hosted-drill",
                "actor_id": "refund-bot",
            },
        }
        status, capture_response, _ = _json_request(
            f"{gateway_url}/capture/llm",
            method="POST",
            payload=capture_payload,
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 202:
            raise RuntimeError(f"/capture/llm returned {status}: {capture_response}")
        summary["capture_response"] = capture_response

        policy_event = {
            "kind": "policy.check",
            "trace_id": "trace-self-hosted-drill",
            "decision_id": "decision-self-hosted-drill",
            "case_id": "refund-drill-001",
            "workflow_name": "Refund approvals",
            "source_app": "self-hosted-drill",
            "actor_id": "refund-bot",
            "content": {
                "allowed": False,
                "rule_id": "refund.threshold.approval",
                "summary": "Amount exceeded threshold and requires human review.",
            },
        }
        status, raw_capture_response, _ = _json_request(
            f"{gateway_url}/capture",
            method="POST",
            payload=policy_event,
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 202:
            raise RuntimeError(f"/capture returned {status}: {raw_capture_response}")
        summary["policy_capture_response"] = raw_capture_response

        case_summary = _wait_for_case(gateway_url, args.access_token, timeout=30.0)
        case_id = case_summary["id"]
        summary["case_id"] = case_id
        summary["case_summary"] = case_summary

        workflow_patch = {
            "status": "assigned",
            "assignee": "pilot@epilabs.org",
            "due_at": "2026-03-29",
            "updated_by": "lead@epilabs.org",
            "reason": "Operator drill triage",
        }
        status, patched_case, _ = _json_request(
            f"{gateway_url}/api/cases/{case_id}",
            method="PATCH",
            payload=workflow_patch,
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"PATCH /api/cases/{case_id} returned {status}: {patched_case}")

        comment_payload = {
            "author": "pilot@epilabs.org",
            "body": "Running the shared review, export, backup, and restore drill.",
        }
        status, comment_response, _ = _json_request(
            f"{gateway_url}/api/cases/{case_id}/comments",
            method="POST",
            payload=comment_payload,
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"POST /api/cases/{case_id}/comments returned {status}: {comment_response}")

        status, in_review_response, _ = _json_request(
            f"{gateway_url}/api/cases/{case_id}",
            method="PATCH",
            payload={
                "status": "in_review",
                "updated_by": "pilot@epilabs.org",
                "reason": "Start operator review",
            },
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"PATCH /api/cases/{case_id} in_review returned {status}: {in_review_response}")

        review_payload = {
            "review_version": "1.0.0",
            "reviewed_by": "pilot@epilabs.org",
            "reviewed_at": "2026-03-28T12:00:00Z",
            "reviews": [
                {
                    "outcome": "confirmed_fault",
                    "notes": "Escalation confirmed during the operator drill.",
                    "reviewer": "pilot@epilabs.org",
                    "timestamp": "2026-03-28T12:00:00Z",
                }
            ],
        }
        status, review_response, _ = _json_request(
            f"{gateway_url}/api/cases/{case_id}/reviews",
            method="POST",
            payload=review_payload,
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"POST /api/cases/{case_id}/reviews returned {status}: {review_response}")
        summary["review_response"] = review_response

        status, resolved_response, _ = _json_request(
            f"{gateway_url}/api/cases/{case_id}",
            method="PATCH",
            payload={
                "status": "resolved",
                "updated_by": "pilot@epilabs.org",
                "reason": "Review completed during operator drill",
            },
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"PATCH /api/cases/{case_id} resolved returned {status}: {resolved_response}")

        export_request = urllib.request.Request(
            f"{gateway_url}/api/cases/{case_id}/export",
            method="POST",
            headers={"Accept": "application/octet-stream", **_auth_headers(args.access_token)},
        )
        with urllib.request.urlopen(export_request, timeout=args.export_timeout) as response:
            export_path.write_bytes(response.read())
            export_headers = dict(response.headers.items())
        summary["export"] = {
            "path": str(export_path),
            "size": export_path.stat().st_size,
            "headers": export_headers,
        }

        verify_result = _run_command(
            [sys.executable, "-m", "epi_cli.main", "verify", "--json", str(export_path)],
            cwd=REPO_ROOT,
            timeout=60.0,
        )
        summary["verify"] = {
            "returncode": verify_result.returncode,
            "report": _parse_verify_output(verify_result),
            "stderr": verify_result.stderr.strip(),
        }
        if verify_result.returncode != 0:
            raise RuntimeError(f"Verification failed: {verify_result.stdout}\n{verify_result.stderr}")

        backup_result = _run_command(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "backup-gateway.ps1"),
                "-StorageDir",
                str(storage_dir),
                "-OutFile",
                str(backup_path),
            ],
            cwd=REPO_ROOT,
            timeout=120.0,
        )
        summary["backup"] = {
            "returncode": backup_result.returncode,
            "stdout": backup_result.stdout.strip(),
            "stderr": backup_result.stderr.strip(),
            "path": str(backup_path),
        }
        if backup_result.returncode != 0 or not backup_path.exists():
            raise RuntimeError(f"Backup failed: {backup_result.stdout}\n{backup_result.stderr}")

        _stop_process(gateway_process)
        gateway_process = None

        restore_result = _run_command(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "restore-gateway.ps1"),
                "-BackupFile",
                str(backup_path),
                "-RestoreDir",
                str(restore_root),
            ],
            cwd=REPO_ROOT,
            timeout=120.0,
        )
        summary["restore"] = {
            "returncode": restore_result.returncode,
            "stdout": restore_result.stdout.strip(),
            "stderr": restore_result.stderr.strip(),
            "restore_root": str(restore_root),
        }
        if restore_result.returncode != 0:
            raise RuntimeError(f"Restore failed: {restore_result.stdout}\n{restore_result.stderr}")

        restored_storage = _find_restored_storage(restore_root)
        summary["restored_storage_dir"] = str(restored_storage)

        restored_gateway_process = _start_process(
            [
                sys.executable,
                "-m",
                "epi_cli.main",
                "gateway",
                "serve",
                "--host",
                args.host,
                "--port",
                str(args.restored_gateway_port),
                "--storage-dir",
                str(restored_storage),
                "--batch-size",
                "1",
                "--batch-timeout",
                "0.1",
                "--retention-mode",
                args.retention_mode,
                "--proxy-failure-mode",
                args.proxy_failure_mode,
                "--access-token",
                args.access_token,
            ],
            cwd=REPO_ROOT,
            stdout_path=logs_root / "restored-gateway.out.log",
            stderr_path=logs_root / "restored-gateway.err.log",
        )

        summary["restored_ready"] = _wait_for_ready(restored_gateway_url, timeout=args.startup_timeout)
        status, restored_detail, _ = _json_request(
            f"{restored_gateway_url}/api/cases/{case_id}",
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"Restored case detail returned {status}: {restored_detail}")
        summary["restored_case"] = restored_detail["case"]

        status, restored_comments, _ = _json_request(
            f"{restored_gateway_url}/api/cases/{case_id}/comments",
            headers=_auth_headers(args.access_token),
            timeout=15.0,
        )
        if status != 200:
            raise RuntimeError(f"Restored comments returned {status}: {restored_comments}")
        summary["restored_comments"] = restored_comments["comments"]
        return summary
    finally:
        _stop_process(restored_gateway_process)
        _stop_process(gateway_process)
        _stop_process(viewer_process)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local self-hosted EPI operator drill.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT / ".ops-drill" / "self-hosted", help="Output root for drill artifacts.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for gateway and viewer.")
    parser.add_argument("--gateway-port", type=int, default=8876, help="Gateway port for the live drill.")
    parser.add_argument("--restored-gateway-port", type=int, default=8878, help="Gateway port for the restored drill.")
    parser.add_argument("--viewer-port", type=int, default=8877, help="Viewer HTTP port.")
    parser.add_argument("--startup-timeout", type=float, default=60.0, help="Seconds to wait for viewer/gateway startup.")
    parser.add_argument("--export-timeout", type=float, default=120.0, help="Seconds to wait for HTTP export.")
    parser.add_argument("--access-token", default="pilot-secret", help="Shared bearer token for the /api workflow routes.")
    parser.add_argument(
        "--retention-mode",
        choices=("redacted_hashes", "full_content"),
        default="redacted_hashes",
        help="Gateway retention mode for captured request/response bodies.",
    )
    parser.add_argument(
        "--proxy-failure-mode",
        choices=("fail-open", "fail-closed"),
        default="fail-open",
        help="Gateway proxy failure behavior.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = run_drill(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
