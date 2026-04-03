from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = REPO_ROOT / "epi-official-site"
INSURANCE_KIT_ROOT = REPO_ROOT / "examples" / "starter_kits" / "insurance_claim"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, *, timeout: float = 30.0, expect_json: bool = False) -> Any:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json" if expect_json else "*/*"})
            with urllib.request.urlopen(request, timeout=5.0) as response:
                payload = response.read()
                if expect_json:
                    return json.loads(payload.decode("utf-8"))
                return payload
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _wait_for_case_state(
    gateway_url: str,
    case_id: str,
    predicate,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_payload: Any = None
    while time.time() < deadline:
        status, payload = _json_request(f"{gateway_url}/api/cases/{urllib.parse.quote(case_id, safe='')}", timeout=10.0)
        last_payload = payload
        case_payload = payload.get("case") if isinstance(payload, dict) else None
        if status == 200 and isinstance(case_payload, dict) and predicate(case_payload):
            return case_payload
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for case state on {case_id}: {last_payload}")


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[int, Any]:
    request_headers = dict(headers or {})
    body: bytes | None = None
    if isinstance(payload, dict):
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif isinstance(payload, bytes):
        body = payload
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.status, json.loads(raw.decode("utf-8"))
            return response.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, raw.decode("utf-8", errors="replace")


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    stdout_path: Path,
    stderr_path: Path,
) -> subprocess.Popen[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
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
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


class _WebhookCaptureHandler(BaseHTTPRequestHandler):
    events: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"_raw": raw.decode("utf-8", errors="replace")}
        self.__class__.events.append(
            {
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "payload": payload,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_webhook_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _WebhookCaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _require_ok(result: subprocess.CompletedProcess[str], *, label: str) -> None:
    if result.returncode == 0:
        return
    raise RuntimeError(
        f"{label} failed with exit code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def _find_latest_artifact(search_root: Path, stem: str) -> Path | None:
    candidates = list(search_root.glob(f"{stem}*.epi"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_smoke() -> dict[str, Any]:
    python_exe = sys.executable
    run_root = REPO_ROOT / ".ops-drill" / f"hosted-insurance-{time.strftime('%Y%m%d-%H%M%S')}"
    storage_dir = run_root / "gateway-storage"
    logs_dir = run_root / "logs"
    storage_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    gateway_port = _find_free_port()
    site_port = _find_free_port()
    webhook_port = _find_free_port()

    site_url = f"http://127.0.0.1:{site_port}"
    gateway_url = f"http://127.0.0.1:{gateway_port}"
    webhook_url = f"http://127.0.0.1:{webhook_port}/approval"

    site_proc: subprocess.Popen[str] | None = None
    gateway_proc: subprocess.Popen[str] | None = None
    webhook_server: ThreadingHTTPServer | None = None

    summary: dict[str, Any] = {
        "run_root": str(run_root),
        "site_url": site_url,
        "gateway_url": gateway_url,
        "webhook_url": webhook_url,
    }

    try:
        webhook_server = _start_webhook_server(webhook_port)

        site_proc = _start_process(
            [python_exe, "-m", "http.server", str(site_port), "--bind", "127.0.0.1"],
            cwd=SITE_ROOT,
            env=os.environ.copy(),
            stdout_path=logs_dir / "site.out.log",
            stderr_path=logs_dir / "site.err.log",
        )
        _wait_for_http(f"{site_url}/verify/")
        _wait_for_http(f"{site_url}/cases/")
        _wait_for_http(f"{site_url}/claim-denial-evidence.html")

        gateway_env = os.environ.copy()
        gateway_env.update(
            {
                "EPI_GATEWAY_STORAGE_DIR": str(storage_dir),
                "EPI_GATEWAY_SHARE_ENABLED": "true",
                "EPI_GATEWAY_SHARE_SITE_BASE_URL": site_url,
                "EPI_GATEWAY_SHARE_API_BASE_URL": gateway_url,
                "EPI_GATEWAY_SHARE_IP_HMAC_SECRET": "local-smoke-secret",
                "EPI_GATEWAY_ALLOWED_ORIGINS": site_url,
                "EPI_APPROVAL_BASE_URL": gateway_url,
                "EPI_APPROVAL_WEBHOOK_URL": webhook_url,
                "EPI_APPROVAL_WEBHOOK_SECRET": "local-approval-secret",
            }
        )
        gateway_proc = _start_process(
            [
                python_exe,
                "-m",
                "epi_cli.main",
                "gateway",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(gateway_port),
                "--storage-dir",
                str(storage_dir),
                "--batch-size",
                "1",
                "--batch-timeout",
                "0.1",
            ],
            cwd=REPO_ROOT,
            env=gateway_env,
            stdout_path=logs_dir / "gateway.out.log",
            stderr_path=logs_dir / "gateway.err.log",
        )
        ready_payload = _wait_for_http(f"{gateway_url}/ready", expect_json=True)
        summary["gateway_ready"] = ready_payload

        insurance_env = os.environ.copy()
        insurance_env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + insurance_env.get("PYTHONPATH", "")
        demo_result = _run_command([python_exe, "agent.py"], cwd=INSURANCE_KIT_ROOT, env=insurance_env, timeout=120.0)
        _require_ok(demo_result, label="insurance starter kit")

        artifact_path = _find_latest_artifact(INSURANCE_KIT_ROOT / "epi-recordings", "insurance_claim_case")
        if artifact_path is None or not artifact_path.exists():
            raise FileNotFoundError(f"Insurance artifact was not created: {artifact_path}")

        share_result = _run_command(
            [
                python_exe,
                "-m",
                "epi_cli.main",
                "share",
                str(artifact_path),
                "--api-base-url",
                gateway_url,
                "--no-open",
                "--json",
            ],
            cwd=REPO_ROOT,
            env=insurance_env,
            timeout=120.0,
        )
        _require_ok(share_result, label="epi share")
        share_payload = json.loads(share_result.stdout)
        summary["share"] = share_payload

        share_id = str(share_payload["id"])
        meta_status, meta_payload = _json_request(f"{gateway_url}/api/share/{urllib.parse.quote(share_id)}/meta")
        if meta_status != 200:
            raise RuntimeError(f"Share metadata check failed: {meta_status} {meta_payload}")
        summary["share_meta"] = meta_payload

        download_status, _download_payload = _json_request(f"{gateway_url}/api/share/{urllib.parse.quote(share_id)}")
        if download_status != 200:
            raise RuntimeError(f"Share download check failed: {download_status} {_download_payload}")

        summary_path = run_root / "insurance_claim_case_summary.html"
        export_result = _run_command(
            [
                python_exe,
                "-m",
                "epi_cli.main",
                "export-summary",
                "summary",
                str(artifact_path),
                "--out",
                str(summary_path),
            ],
            cwd=REPO_ROOT,
            env=insurance_env,
            timeout=120.0,
        )
        _require_ok(export_result, label="Decision Record export")
        if not summary_path.exists():
            raise FileNotFoundError(f"Decision Record was not created: {summary_path}")

        capture_payload = {
            "items": [
                {
                    "case_id": "smoke-approval-case",
                    "workflow_id": "smoke-approval-workflow",
                    "workflow_name": "Insurance claim denial",
                    "kind": "agent.run.start",
                    "content": {"goal": "Review a high-value claim denial."},
                },
                {
                    "case_id": "smoke-approval-case",
                    "workflow_id": "smoke-approval-workflow",
                    "workflow_name": "Insurance claim denial",
                    "kind": "agent.approval.request",
                    "content": {
                        "approval_id": "approval-smoke-1",
                        "action": "deny_claim",
                        "reason": "Claim exceeds manual review threshold.",
                        "requested_from": "claims.manager@carrier.com",
                        "timeout_minutes": 120,
                    },
                },
            ]
        }
        batch_status, batch_payload = _json_request(
            f"{gateway_url}/capture/batch",
            method="POST",
            payload=capture_payload,
            timeout=20.0,
        )
        if batch_status not in {200, 202}:
            raise RuntimeError(f"Capture batch failed: {batch_status} {batch_payload}")

        deadline = time.time() + 10.0
        while time.time() < deadline and not _WebhookCaptureHandler.events:
            time.sleep(0.2)
        if not _WebhookCaptureHandler.events:
            raise RuntimeError("Approval webhook was not received during the smoke test.")
        summary["approval_webhook"] = _WebhookCaptureHandler.events[-1]

        approve_status, approve_payload = _json_request(
            f"{gateway_url}/api/approve/smoke-approval-workflow/approval-smoke-1?decision=approve&reviewer=claims.manager%40carrier.com&reason=Smoke+approval",
            method="POST",
            timeout=20.0,
        )
        if approve_status != 200:
            raise RuntimeError(f"Approval callback failed: {approve_status} {approve_payload}")

        case_payload = _wait_for_case_state(
            gateway_url,
            "smoke-approval-case",
            lambda payload: "agent.approval.response" in [step.get("kind") for step in payload.get("steps") or []],
        )
        step_kinds = [step.get("kind") for step in case_payload.get("steps") or []]
        if "agent.approval.response" not in step_kinds:
            raise RuntimeError("Approval response was not recorded in the shared case.")
        summary["approved_case"] = {
            "status": case_payload.get("status"),
            "step_kinds": step_kinds,
        }

        orphan_payload = {
            "items": [
                {
                    "case_id": "smoke-orphan-case",
                    "workflow_id": "smoke-orphan-workflow",
                    "workflow_name": "Insurance claim denial",
                    "kind": "agent.run.start",
                    "content": {"goal": "Trigger crash recovery."},
                }
            ]
        }
        orphan_status, orphan_response = _json_request(
            f"{gateway_url}/capture/batch",
            method="POST",
            payload=orphan_payload,
            timeout=20.0,
        )
        if orphan_status not in {200, 202}:
            raise RuntimeError(f"Orphan session setup failed: {orphan_status} {orphan_response}")

        _stop_process(gateway_proc)
        gateway_proc = _start_process(
            [
                python_exe,
                "-m",
                "epi_cli.main",
                "gateway",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(gateway_port),
                "--storage-dir",
                str(storage_dir),
                "--batch-size",
                "1",
                "--batch-timeout",
                "0.1",
            ],
            cwd=REPO_ROOT,
            env=gateway_env,
            stdout_path=logs_dir / "gateway-restart.out.log",
            stderr_path=logs_dir / "gateway-restart.err.log",
        )
        _wait_for_http(f"{gateway_url}/ready", expect_json=True)
        orphan_case_payload = _wait_for_case_state(
            gateway_url,
            "smoke-orphan-case",
            lambda payload: "agent.run.recovered" in [step.get("kind") for step in payload.get("steps") or []],
        )
        orphan_step_kinds = [step.get("kind") for step in orphan_case_payload.get("steps") or []]
        if "agent.run.recovered" not in orphan_step_kinds:
            raise RuntimeError("Recovered orphan case did not record agent.run.recovered.")
        summary["orphan_recovery"] = {
            "status": orphan_case_payload.get("status"),
            "step_kinds": orphan_step_kinds,
        }

        return summary
    finally:
        _stop_process(gateway_proc)
        _stop_process(site_proc)
        if webhook_server is not None:
            webhook_server.shutdown()
            webhook_server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hosted insurance pilot smoke test locally.")
    parser.parse_args()
    summary = run_smoke()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
