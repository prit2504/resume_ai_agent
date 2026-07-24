"""
Email MCP Client Bridge
=======================
Provides EmailMCPClient — a thin, synchronous wrapper that lets the FastAPI
orchestrator call tools on the Email MCP server (server.py running on
http://localhost:9000/mcp) without spawning a separate process.

The MCP handshake + SSE-parsing logic is ported directly from agent.py so 
agent.py itself stays untouched and still works as a standalone CLI tool.
"""

from __future__ import annotations

import json
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

EMAIL_MCP_URL: str = os.getenv("EMAIL_MCP_URL", "http://localhost:9000/mcp")

# Module-level session ID cache — one handshake per process lifetime.
_session_id: str | None = None


# ── MCP transport helpers ─────────────────────────────────────────────────────

def _mcp_initialize(client: httpx.Client) -> str:
    """
    Perform the MCP initialize handshake and return the session ID.
    Mirrors agent.py's _mcp_initialize exactly.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    init_payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "resume-ai-agent", "version": "1.0"},
        },
    }
    resp = client.post(EMAIL_MCP_URL, json=init_payload, headers=headers)
    resp.raise_for_status()

    sid = resp.headers.get("mcp-session-id")
    if not sid:
        raise RuntimeError(
            f"Email MCP server did not return a session ID. Body: {resp.text}"
        )

    # Required follow-up notification per MCP spec
    notify_headers = {**headers, "Mcp-Session-Id": sid}
    client.post(
        EMAIL_MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=notify_headers,
    )
    logger.info("[EmailMCP] Session established: %s", sid)
    return sid


def _parse_sse_response(text: str) -> dict:
    """
    Parse an SSE (text/event-stream) response body and return the first
    valid JSON result payload.  Falls back to {} on parse failures.
    Mirrors agent.py's response-parsing loop.
    """
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            parsed = json.loads(line[5:].strip())
            content = parsed.get("result", {}).get("content", [])
            if content:
                return json.loads(content[0].get("text", "{}"))
        except Exception:
            continue
    return {}


def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Call any tool on the Email MCP server synchronously.
    Re-uses a cached session ID so the handshake only happens once per process.
    """
    global _session_id

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    with httpx.Client(timeout=60) as client:
        if _session_id is None:
            _session_id = _mcp_initialize(client)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": _session_id,
        }

        resp = client.post(EMAIL_MCP_URL, json=payload, headers=headers)

        if resp.status_code >= 400:
            logger.error(
                "[EmailMCP] %s → HTTP %s: %s", tool_name, resp.status_code, resp.text
            )

        resp.raise_for_status()
        result = _parse_sse_response(resp.text)

        if not result:
            logger.warning("[EmailMCP] %s returned empty result body.", tool_name)
            return {"success": False, "error": "Empty response from Email MCP server"}

        return result


# ── High-level client class ───────────────────────────────────────────────────

class EmailMCPClient:
    """
    Thin facade around call_mcp_tool() for use by the FastAPI orchestrator.

    Usage:
        client = EmailMCPClient()
        result = client.send_email("hr@company.com", "Subject", "Body", "/path/resume.pdf")
    """

    # ── single email ──────────────────────────────────────────────────────────

    def validate_email(self, email: str) -> dict:
        """
        Validate an email address format via the Email MCP server.

        Returns:
            {"valid": bool, "email": str, "reason": str}
        """
        return call_mcp_tool("validate_email", {"email": email})

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        pdf_path: str = "",
    ) -> dict:
        """
        Send a single job application email through the Email MCP server.

        Returns:
            {"success": bool, "to": str, "timestamp": str, "error": str}
        """
        logger.info("[EmailMCP] Sending email to %s | subject: %s", to_email, subject)
        return call_mcp_tool(
            "send_email",
            {
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "pdf_path": pdf_path,
            },
        )

    # ── bulk from CSV (uses server.py's built-in bulk_send_emails tool) ───────

    def bulk_send_from_csv(
        self,
        csv_path: str,
        subject_template: str,
        body_template: str,
        pdf_path: str = "",
    ) -> dict:
        """
        Send templated emails to every valid contact in a CSV file using the
        Email MCP server's built-in bulk_send_emails tool.

        Template placeholders supported: {name}, {company}, {job_title}

        Returns:
            {
              "total_attempted": int,
              "sent_count": int,
              "failed_count": int,
              "results": list[dict],
              "summary": str,
            }
        """
        logger.info("[EmailMCP] Bulk-sending from CSV: %s", csv_path)
        return call_mcp_tool(
            "bulk_send_emails",
            {
                "subject_template": subject_template,
                "body_template": body_template,
                "csv_path": csv_path,
                "pdf_path": pdf_path,
            },
        )

    # ── load contacts from CSV (server-side validation) ───────────────────────

    def load_hr_contacts(self, csv_path: str = "") -> dict:
        """
        Ask the Email MCP server to load and validate contacts from a CSV.

        Returns:
            {
              "success": bool,
              "total": int,
              "valid_count": int,
              "invalid_count": int,
              "contacts": list[dict],
              "invalid": list[dict],
              "error": str,
            }
        """
        return call_mcp_tool("load_hr_contacts", {"csv_path": csv_path})

    # ── batch of individually-written emails (one SMTP connection) ────────────

    def send_bulk_individual(
        self,
        emails: list[dict],
        pdf_path: str = "",
    ) -> dict:
        """
        Send a batch of LLM-written emails in ONE SMTP connection via the
        Email MCP server's send_bulk_individual tool.

        Each dict in `emails` must have:
            - to_email (str)
            - subject  (str)
            - body     (str)

        Use this from /bulk-apply instead of calling send_email() in a loop.
        It is significantly faster because only one SMTP handshake is made.

        Returns:
            {
              "total_attempted": int,
              "sent_count": int,
              "failed_count": int,
              "results": list[dict],
              "summary": str,
            }
        """
        logger.info(
            "[EmailMCP] send_bulk_individual: %d email(s), pdf=%s",
            len(emails), pdf_path or "none",
        )
        return call_mcp_tool(
            "send_bulk_individual",
            {"emails": emails, "pdf_path": pdf_path},
        )
