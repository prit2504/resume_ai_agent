from __future__ import annotations

import base64
import logging
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_mcp_server")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_ADDRESS", "")
SMTP_PASSWORD = (
    os.getenv("SMTP_PASSWORD")
    or os.getenv("GMAIL_APP_PASSWORD")
    or os.getenv("GMAIL_PASSWORD", "")
)
MCP_HOST = os.getenv("EMAIL_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("EMAIL_MCP_PORT", "9000"))
MCP_PATH = os.getenv("EMAIL_MCP_PATH", "/mcp")
MAX_ATTACHMENT_BYTES = int(
    os.getenv("EMAIL_MCP_MAX_ATTACHMENT_BYTES", str(10 * 1024 * 1024))
)

mcp = FastMCP(
    name="email_mcp_server",
    instructions=(
        "Email transport server for approved job-application outreach. "
        "It validates recipient addresses and sends a single plain-text email "
        "with an optional PDF resume attachment. Drafting and human approval "
        "happen in the Resume AI Agent before this tool is called."
    ),
)

_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
_BLACKLISTED_DOMAINS = {
    "example.com",
    "test.com",
    "placeholder.com",
    "dummy.com",
}


def _smtp_connection() -> smtplib.SMTP_SSL:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP credentials are not configured. Set SMTP_USERNAME/SMTP_PASSWORD "
            "or GMAIL_ADDRESS/GMAIL_APP_PASSWORD."
        )
    smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
    return smtp


def _decode_pdf(pdf_base64: str) -> bytes:
    if not pdf_base64:
        return b""

    try:
        payload = base64.b64decode(pdf_base64, validate=True)
    except Exception as exc:
        raise ValueError("Resume attachment is not valid base64") from exc

    if len(payload) > MAX_ATTACHMENT_BYTES:
        raise ValueError(
            f"Resume attachment exceeds {MAX_ATTACHMENT_BYTES} bytes"
        )

    if not payload.startswith(b"%PDF"):
        raise ValueError("Resume attachment is not a valid PDF")

    return payload


@mcp.tool()
def validate_email(email: str) -> dict:
    """Validate an email address and reject obvious placeholder domains."""
    cleaned = (email or "").strip().lower()

    if not _EMAIL_PATTERN.fullmatch(cleaned):
        return {
            "valid": False,
            "email": cleaned,
            "reason": "Invalid format",
        }

    domain = cleaned.rsplit("@", 1)[1]
    if domain in _BLACKLISTED_DOMAINS:
        return {
            "valid": False,
            "email": cleaned,
            "reason": "Blacklisted domain",
        }

    return {
        "valid": True,
        "email": cleaned,
        "reason": "Valid email",
    }


@mcp.tool()
def send_email(
    to_email: str,
    subject: str,
    body: str,
    pdf_base64: str = "",
    pdf_filename: str = "resume.pdf",
) -> dict:
    """Send one approved application email with an optional PDF resume."""
    validation = validate_email(to_email)
    if not validation["valid"]:
        return {
            "success": False,
            "to": validation["email"],
            "timestamp": "",
            "error": f"Invalid email: {validation['reason']}",
        }

    subject = (subject or "").strip()
    body = (body or "").strip()

    if not subject:
        return {
            "success": False,
            "to": to_email,
            "timestamp": "",
            "error": "Subject is required",
        }

    if not body:
        return {
            "success": False,
            "to": to_email,
            "timestamp": "",
            "error": "Body is required",
        }

    try:
        pdf_bytes = _decode_pdf(pdf_base64)
    except ValueError as exc:
        return {
            "success": False,
            "to": to_email,
            "timestamp": "",
            "error": str(exc),
        }

    try:
        msg = EmailMessage()
        msg["From"] = SMTP_USERNAME
        msg["To"] = validation["email"]
        msg["Subject"] = subject
        msg.set_content(body)

        if pdf_bytes:
            safe_filename = os.path.basename(pdf_filename or "resume.pdf")
            if not safe_filename.lower().endswith(".pdf"):
                safe_filename += ".pdf"

            msg.add_attachment(
                pdf_bytes,
                maintype="application",
                subtype="pdf",
                filename=safe_filename,
            )

        with _smtp_connection() as smtp:
            smtp.send_message(msg)

        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info("Email sent to %s at %s", validation["email"], timestamp)

        return {
            "success": True,
            "to": validation["email"],
            "timestamp": timestamp,
            "error": "",
        }

    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "to": validation["email"],
            "timestamp": "",
            "error": (
                "SMTP authentication failed. Check your app password "
                "or SMTP credentials."
            ),
        }
    except Exception as exc:
        logger.exception("Email send failed for %s", validation["email"])
        return {
            "success": False,
            "to": validation["email"],
            "timestamp": "",
            "error": str(exc),
        }


if __name__ == "__main__":
    print(f"Email MCP server: http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}")
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH,
    )
