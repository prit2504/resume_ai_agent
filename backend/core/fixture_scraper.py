from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class LocalFixtureJobsScraper:
    """Offline job source for end-to-end development without SerpApi."""

    def __init__(self, fixture_path: str | Path) -> None:
        self._fixture_path = Path(fixture_path)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._scores: dict[str, float] = {}

    def _load(self) -> list[dict[str, Any]]:
        if not self._fixture_path.exists():
            raise FileNotFoundError(f"Job fixture not found: {self._fixture_path}")
        data = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Local job fixture must contain a JSON array")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _job_id(job: dict[str, Any], index: int) -> str:
        return str(job.get("job_id") or f"fixture-job-{index}")

    @staticmethod
    def _search_text(job: dict[str, Any]) -> str:
        return " ".join(
            str(job.get(key) or "")
            for key in ("title", "company_name", "location", "description")
        ).lower()

    async def search_many(
        self,
        queries: list[str],
        location: str | None = None,
        max_pages: int = 1,
        date_posted: str | None = None,
        job_type: str | None = None,
        work_type: str | None = None,
        radius_km: int | None = None,
        country: str | None = None,
        language: str | None = None,
        uds: str | None = None,
        max_jobs: int = 50,
    ) -> list[str]:
        jobs = self._load()
        query_tokens = {
            token
            for query in queries
            for token in query.lower().split()
            if len(token) > 2
        }

        ranked: list[tuple[dict[str, Any], float]] = []
        for job in jobs:
            haystack = self._search_text(job)
            score = sum(1 for token in query_tokens if token in haystack)
            if location and location.lower() not in haystack:
                score -= 0.25
            ranked.append((job, float(score)))

        ranked.sort(key=lambda item: item[1], reverse=True)
        self._jobs = {}
        self._scores = {}

        for index, (job, score) in enumerate(ranked[: max(1, max_jobs)], start=1):
            jid = self._job_id(job, index)
            normalized = dict(job)
            normalized["job_id"] = jid
            self._jobs[jid] = normalized
            self._scores[jid] = score

        return list(self._jobs.keys())

    async def search(self, keywords: str, **kwargs: Any) -> list[str]:
        return await self.search_many([keywords], **kwargs)

    def get_discovery_score(self, job_id: str) -> float | None:
        return self._scores.get(job_id)

    @staticmethod
    def _format(job: dict[str, Any]) -> str:
        lines = [
            f"Title: {job.get('title') or ''}",
            f"Company: {job.get('company_name') or ''}",
            f"Location: {job.get('location') or ''}",
            f"Source: {job.get('via') or 'Local fixture'}",
            "",
            "Description:",
            str(job.get("description") or ""),
        ]
        return "\n".join(lines).strip()

    async def fetch_details(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Fixture job not found: {job_id}")
        return {
            "sections": {"job_posting": self._format(job)},
            "serpapi_job": job,
        }

    async def fetch_all_details(
        self,
        job_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        total = len(job_ids)
        for index, job_id in enumerate(job_ids, start=1):
            results[job_id] = await self.fetch_details(job_id)
            if progress_callback:
                progress_callback(index, total, job_id)
        return results
