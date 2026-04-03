from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


logger = logging.getLogger("epi-gateway.approval")


def send_signed_webhook(
    webhook_url: str,
    payload: dict,
    *,
    secret: str | None = None,
    timeout_seconds: int = 10,
) -> None:
    if not str(webhook_url or "").strip():
        return

    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        headers["X-EPI-Signature"] = f"sha256={digest}"

    delays = [0, 1, 2, 4]
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            request = urllib.request.Request(
                webhook_url,
                data=payload_bytes,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds):
                return
        except Exception as exc:
            if attempt < len(delays):
                logger.warning(
                    "Approval webhook attempt %s failed for %s: %s",
                    attempt,
                    webhook_url,
                    exc,
                )
            else:
                logger.warning(
                    "Approval webhook failed after %s attempts for %s: %s",
                    len(delays),
                    webhook_url,
                    exc,
                )


def send_approval_email(
    *,
    to_address: str,
    workflow_id: str,
    action: str,
    reason: str,
    approve_url: str,
    deny_url: str,
    case_url: str | None,
    smtp_host: str,
    smtp_port: int = 587,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    smtp_from: str | None = None,
) -> None:
    recipient = str(to_address or "").strip()
    if not recipient or not str(smtp_host or "").strip() or not str(smtp_from or "").strip():
        return

    subject = f"EPI approval required: {action or 'review requested'}"
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = recipient

    case_link_html = (
        f'<p><a href="{case_url}">Open the case</a></p>'
        if str(case_url or "").strip()
        else ""
    )
    html = f"""
    <html>
      <body style="font-family:Segoe UI,Arial,sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#0f172a">
        <h2 style="margin-bottom:8px">Approval required</h2>
        <p style="margin-top:0">Workflow <strong>{workflow_id}</strong> is waiting for a human decision.</p>
        <p><strong>Action:</strong> {action or "Review required"}</p>
        <p><strong>Reason:</strong> {reason or "No reason supplied."}</p>
        <p style="margin:24px 0">
          <a href="{approve_url}" style="background:#15803d;color:#ffffff;padding:12px 18px;border-radius:6px;text-decoration:none;font-weight:600">Approve</a>
          <a href="{deny_url}" style="background:#b91c1c;color:#ffffff;padding:12px 18px;border-radius:6px;text-decoration:none;font-weight:600;margin-left:12px">Deny</a>
        </p>
        {case_link_html}
      </body>
    </html>
    """
    message.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=10) as server:
            server.ehlo()
            if smtp_user or smtp_password:
                server.starttls()
                server.ehlo()
                server.login(smtp_user or "", smtp_password or "")
            server.send_message(message)
    except Exception as exc:
        logger.warning("Approval email delivery failed for %s: %s", recipient, exc)
