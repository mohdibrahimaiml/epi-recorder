from __future__ import annotations

import html as _html
import logging
import smtplib
import urllib.request  # noqa: F401 — kept as the patch target for webhook tests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


from epi_core.webhook import send_signed_webhook

__all__ = ["send_signed_webhook", "send_approval_email"]

logger = logging.getLogger("epi-gateway.approval")


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

    # Header values must not be able to inject CRLF into the message.
    subject_action = " ".join(str(action or "review requested").split())
    subject = f"EPI approval required: {subject_action}"
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = recipient

    # Everything below is attacker-influenceable (it comes from captured run
    # content and request parameters), so it is escaped for the HTML context.
    escaped_workflow = _html.escape(str(workflow_id or ""))
    escaped_action = _html.escape(str(action or "Review required"))
    escaped_reason = _html.escape(str(reason or "No reason supplied."))
    escaped_approve = _html.escape(str(approve_url or ""), quote=True)
    escaped_deny = _html.escape(str(deny_url or ""), quote=True)
    case_link_html = (
        f'<p><a href="{_html.escape(str(case_url), quote=True)}">Open the case</a></p>'
        if str(case_url or "").strip()
        else ""
    )
    html = f"""
    <html>
      <body style="font-family:Segoe UI,Arial,sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#0f172a">
        <h2 style="margin-bottom:8px">Approval required</h2>
        <p style="margin-top:0">Workflow <strong>{escaped_workflow}</strong> is waiting for a human decision.</p>
        <p><strong>Action:</strong> {escaped_action}</p>
        <p><strong>Reason:</strong> {escaped_reason}</p>
        <p style="margin:24px 0">
          <a href="{escaped_approve}" style="background:#15803d;color:#ffffff;padding:12px 18px;border-radius:6px;text-decoration:none;font-weight:600">Approve</a>
          <a href="{escaped_deny}" style="background:#b91c1c;color:#ffffff;padding:12px 18px;border-radius:6px;text-decoration:none;font-weight:600;margin-left:12px">Deny</a>
        </p>
        {case_link_html}
        <p style="color:#64748b;font-size:13px">These links open a confirmation page; clicking records a
        <strong>link click</strong>, not a signed human approval.</p>
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
