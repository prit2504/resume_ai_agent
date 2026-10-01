from __future__ import annotations

import base64
import json
from typing import Any


class MCPEmailSender:
    """Adapter for the project's email MCP server."""

    def __init__(
        self,
        transport: str = "streamable_http",
        url: str | None = None,
        command: str | None = None,
        args_json: str = "[]",
        tool_name: str = "send_email",
    ) -> None:
        self._transport = transport
        self._url = url
        self._command = command
        self._args_json = args_json
        self._tool_name = tool_name
        self._client: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self._command) if self._transport == "stdio" else bool(self._url)

    async def _get_client(self) -> Any:
        if not self.configured:
            raise RuntimeError(
                "Email MCP is not configured. Set EMAIL_MCP_URL for HTTP, "
                "or EMAIL_MCP_COMMAND/EMAIL_MCP_ARGS_JSON for stdio."
            )

        if self._client is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            if self._transport == "stdio":
                try:
                    args = json.loads(self._args_json or "[]")
                except json.JSONDecodeError as exc:
                    raise RuntimeError("EMAIL_MCP_ARGS_JSON must be a JSON array") from exc

                self._client = MultiServerMCPClient(
                    {"email": {"command": self._command, "args": args, "transport": "stdio"}}
                )
            else:
                self._client = MultiServerMCPClient(
                    {"email": {"url": self._url, "transport": "streamable_http"}}
                )
        return self._client

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {"success": True, "raw": result}

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        attachment_name: str,
        attachment_bytes: bytes,
    ) -> dict[str, Any]:
        client = await self._get_client()
        tools = await client.get_tools()
        tool = next((item for item in tools if item.name == self._tool_name), None)
        if tool is None:
            raise RuntimeError(
                f"Email MCP tool '{self._tool_name}' was not found. "
                "Set EMAIL_MCP_TOOL_NAME to your server's send tool."
            )

        payload = {
            "to_email": recipient,
            "subject": subject,
            "body": body,
            "pdf_base64": base64.b64encode(attachment_bytes).decode("ascii"),
            "pdf_filename": attachment_name,
        }
        result = self._normalize_result(await tool.ainvoke(payload))
        if not result.get("success", False):
            raise RuntimeError(result.get("error") or "Email MCP send failed")
        return result
