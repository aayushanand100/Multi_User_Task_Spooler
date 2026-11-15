"""
notification.py - Settlement Calculation and Email Notification Dispatcher
Supports standard SMTP email dispatch (smtplib), simulated console dispatch, and mailto deep links.
No external third-party API or Twilio credentials required.
"""

import os
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

# Default billing constants
BASE_FEE_INR = 25.00
PER_UNIT_SEC_RATE_INR = 1.50


def calculate_settlement(
    total_allocated_units: int,
    duration_seconds: int,
    base_fee: float = BASE_FEE_INR,
    unit_rate: float = PER_UNIT_SEC_RATE_INR
) -> Dict[str, Any]:
    """
    Calculates settlement cost for a finished task:
    billing_amount = (total_allocated_units * duration_seconds * unit_rate) + base_fee
    """
    units_cost = total_allocated_units * duration_seconds * unit_rate
    total_bill = round(units_cost + base_fee, 2)
    return {
        "total_units": total_allocated_units,
        "duration_seconds": duration_seconds,
        "base_fee": base_fee,
        "unit_rate": unit_rate,
        "units_cost": round(units_cost, 2),
        "total_bill": total_bill,
        "currency": "₹"
    }


def format_email_subject(task_id: int) -> str:
    """Generates standard email subject line."""
    return f"[Task Spooler] Task #{task_id} Completed - Settlement Notice"


def format_email_body_text(
    user_name: str,
    task_id: int,
    amount: float,
    duration_seconds: int = 15,
    total_units: int = 0
) -> str:
    """Generates plain text email body."""
    return (
        f"Hello {user_name},\n\n"
        f"Your spooler task #{task_id} is completed! All allocated resources have been released back to the pool.\n\n"
        f"Settlement Summary:\n"
        f"- Task ID: #{task_id}\n"
        f"- User Name: {user_name}\n"
        f"- Processing Duration: {duration_seconds} second(s)\n"
        f"- Total Allocated Units: {total_units}\n"
        f"- Total Bill: ₹{amount:.2f}\n"
        f"- Status: DONE / COMPLETED\n\n"
        f"Thank you for using the Multi-User Task Spooler with Deadlock Avoidance.\n"
    )


def format_email_body_html(
    user_name: str,
    task_id: int,
    amount: float,
    duration_seconds: int = 15,
    total_units: int = 0
) -> str:
    """Generates styled HTML email body."""
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B; margin: 0; padding: 20px; }}
    .card {{ background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; max-width: 540px; padding: 24px; }}
    .header {{ border-bottom: 2px solid #3B82F6; padding-bottom: 12px; margin-bottom: 16px; }}
    .title {{ font-size: 18px; font-weight: bold; color: #0F172A; margin: 0; }}
    .badge {{ display: inline-block; background: #DCFCE7; color: #15803D; padding: 4px 10px; border-radius: 9999px; font-weight: bold; font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; margin-bottom: 14px; }}
    td {{ padding: 8px; border-bottom: 1px solid #F1F5F9; font-size: 14px; }}
    td.label {{ color: #64748B; width: 45%; }}
    td.value {{ font-weight: 600; color: #0F172A; }}
    .total-row td {{ font-size: 16px; font-weight: bold; color: #2563EB; border-top: 2px solid #E2E8F0; }}
    .footer {{ font-size: 12px; color: #94A3B8; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <p class="title">🖨️ Task Spooler - Completion Settlement</p>
    </div>
    <p>Hello <strong>{user_name}</strong>,</p>
    <p>Your task <strong>#{task_id}</strong> has finished executing. All hardware resources have been restored to the available pool.</p>
    <table>
      <tr><td class="label">Task ID</td><td class="value">#{task_id}</td></tr>
      <tr><td class="label">Status</td><td class="value"><span class="badge">DONE</span></td></tr>
      <tr><td class="label">Allocated Units</td><td class="value">{total_units} unit(s)</td></tr>
      <tr><td class="label">Execution Duration</td><td class="value">{duration_seconds}s</td></tr>
      <tr class="total-row"><td class="label">Total Amount Billed</td><td class="value">₹{amount:.2f}</td></tr>
    </table>
    <div class="footer">
      Multi-User Task Spooler with Deadlock Avoidance (Dijkstra's Banker's Algorithm)
    </div>
  </div>
</body>
</html>
"""


def get_mailto_link(to_email: str, subject: str, body: str) -> str:
    """Generates standard mailto: link for one-click email client composition."""
    clean_email = to_email.strip()
    encoded_sub = urllib.parse.quote(subject)
    encoded_body = urllib.parse.quote(body)
    return f"mailto:{clean_email}?subject={encoded_sub}&body={encoded_body}"


def dispatch_email_notification(
    user_email: str,
    user_name: str,
    task_id: int,
    amount: float,
    smtp_config: Optional[Dict[str, Any]] = None,
    duration_seconds: int = 15,
    total_units: int = 0
) -> Dict[str, Any]:
    """
    Sends email notification via SMTP if host/credentials are configured,
    or dispatches via simulated console with a one-click mailto: deep link.
    """
    clean_email = (user_email or "").strip()
    if not clean_email:
        clean_email = f"{user_name.lower().replace(' ', '_')}@spooler.local"

    subject = format_email_subject(task_id)
    body_text = format_email_body_text(user_name, task_id, amount, duration_seconds, total_units)
    body_html = format_email_body_html(user_name, task_id, amount, duration_seconds, total_units)
    mailto_link = get_mailto_link(clean_email, subject, body_text)

    cfg = smtp_config or {}
    smtp_host = cfg.get("smtp_host") or os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(cfg.get("smtp_port") or os.environ.get("SMTP_PORT", "587"))
    smtp_user = cfg.get("smtp_user") or os.environ.get("SMTP_USER", "").strip()
    smtp_pass = cfg.get("smtp_pass") or os.environ.get("SMTP_PASS", "").strip()
    smtp_from = cfg.get("smtp_from") or os.environ.get("SMTP_FROM", smtp_user or "spooler@local.domain").strip()
    use_tls = cfg.get("use_tls", True)

    # If SMTP host is configured, attempt live dispatch
    if smtp_host:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = clean_email

            part1 = MIMEText(body_text, "plain")
            part2 = MIMEText(body_html, "html")
            msg.attach(part1)
            msg.attach(part2)

            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=8.0)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=8.0)
                if use_tls:
                    server.starttls()

            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)

            server.sendmail(smtp_from, [clean_email], msg.as_string())
            server.quit()

            return {
                "success": True,
                "mode": f"Live SMTP ({smtp_host}:{smtp_port})",
                "email": clean_email,
                "subject": subject,
                "body_text": body_text,
                "mailto_link": mailto_link,
                "status": "SENT"
            }
        except Exception as e:
            return {
                "success": False,
                "mode": f"Live SMTP Failed ({e})",
                "email": clean_email,
                "subject": subject,
                "body_text": body_text,
                "mailto_link": mailto_link,
                "status": "FALLBACK_SIMULATED",
                "error": str(e)
            }

    # Default: Simulated Console Dispatch with instant mailto: link
    return {
        "success": True,
        "mode": "Simulated Console Dispatch",
        "email": clean_email,
        "subject": subject,
        "body_text": body_text,
        "mailto_link": mailto_link,
        "status": "SIMULATED_DISPATCHED"
    }
