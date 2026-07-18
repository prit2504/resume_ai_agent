import asyncio
import json
from typing import Any, Callable

class LinkedInMCPScraper:
    """Adapter: LinkedIn MCP Server via langchain-mcp-adapters.

    Handles connection lifecycle and retry logic for truncated responses.
    """

    def __init__(
        self,
        mcp_url: str = "http://localhost:8080/mcp",
        detail_delay: float = 1.5,
        concurrency: int = 1,
        min_posting_chars: int = 300,
        max_retries: int = 1,
        retry_delay: float = 2.0,
    ) -> None:
        self._mcp_url = mcp_url
        self._detail_delay = detail_delay
        self._concurrency = concurrency
        self._min_posting_chars = min_posting_chars
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        """Lazy initialization of MCP client."""
        if self._client is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            import os

            transport = os.environ.get("MCP_TRANSPORT", "stdio")

            if transport == "stdio":
                self._client = MultiServerMCPClient(
                    {
                        "linkedin": {
                            "command": "uvx",
                            "args": ["mcp-server-linkedin"],
                            "transport": "stdio",
                        }
                    }
                )
            else:
                self._client = MultiServerMCPClient(
                    {
                        "linkedin": {
                            "url": self._mcp_url,
                            "transport": "streamable_http",
                        }
                    }
                )
        return self._client

    async def _get_tool(self, name: str) -> Any:
        """Retrieve a named tool from the MCP server."""
        client = await self._get_client()
        tools = await client.get_tools()
        return next(t for t in tools if t.name == name)

    async def search(
        self,
        keywords: str,
        location: str | None = None,
        max_pages: int = 3,
        date_posted: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        work_type: str | None = None,
        easy_apply: bool = False,
        sort_by: str | None = None,
    ) -> list[str]:
        """Search LinkedIn jobs and return job IDs."""
        tool = await self._get_tool("search_jobs")
        payload = {
            "keywords": keywords,
            "location": location,
            "max_pages": max_pages,
            "date_posted": date_posted,
            "job_type": job_type,
            "experience_level": experience_level,
            "work_type": work_type,
            "easy_apply": easy_apply,
            "sort_by": sort_by,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        result = await tool.ainvoke(payload)
        parsed = json.loads(result[0]["text"])
        return parsed.get("job_ids", [])

    async def fetch_details(self, job_id: str) -> dict[str, Any]:
        """Fetch raw job details with retry for truncated responses."""
        tool = await self._get_tool("get_job_details")
        best_detail: dict[str, Any] | None = None
        best_len = -1

        for attempt in range(1, self._max_retries + 1):
            result = await tool.ainvoke({"job_id": job_id})
            detail = json.loads(result[0]["text"])
            text_len = len((detail or {}).get("sections", {}).get("job_posting", "") or "")

            if text_len > best_len:
                best_detail, best_len = detail, text_len

            if text_len >= self._min_posting_chars:
                return best_detail

            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_delay)

        return best_detail or {}

    async def fetch_all_details(
        self,
        job_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fetch details for all job IDs with concurrency control."""
        sem = asyncio.Semaphore(self._concurrency)
        results: dict[str, dict[str, Any]] = {}

        async def _one(job_id: str, idx: int) -> None:
            async with sem:
                try:
                    detail = await self.fetch_details(job_id)
                    results[job_id] = detail
                    if progress_callback:
                        progress_callback(idx, len(job_ids), job_id)
                except Exception as e:
                    if progress_callback:
                        progress_callback(idx, len(job_ids), f"{job_id} (ERROR: {e})")
                finally:
                    await asyncio.sleep(self._detail_delay)

        tasks = [_one(jid, i) for i, jid in enumerate(job_ids, start=1)]
        await asyncio.gather(*tasks)
        return results
