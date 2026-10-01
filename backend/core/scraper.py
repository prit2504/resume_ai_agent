from __future__ import annotations

import hashlib
from typing import Any, Callable

import httpx


class SerpApiGoogleJobsScraper:
    """Google Jobs scraper backed by SerpApi.

    The adapter preserves the scraper interface used by the orchestrator:
    search() returns stable job IDs and fetch_details() returns a normalized
    detail object. SerpApi already includes the full job description in
    jobs_results, so details are cached from the search response instead of
    making one extra request per job.
    """

    _ENDPOINT = "https://serpapi.com/search"

    def __init__(
        self,
        api_key: str,
        google_domain: str = "google.com",
        gl: str | None = None,
        hl: str | None = "en",
        timeout: float = 30.0,
        no_cache: bool = False,
    ) -> None:
        self._api_key = api_key.strip()
        self._google_domain = google_domain
        self._gl = gl
        self._hl = hl
        self._timeout = timeout
        self._no_cache = no_cache
        self._jobs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _stable_job_id(job: dict[str, Any]) -> str:
        if job.get("job_id"):
            return str(job["job_id"])

        identity = "|".join(
            str(job.get(key) or "")
            for key in ("title", "company_name", "location", "share_link")
        )
        return f"serpapi-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _build_query(
        keywords: str,
        location: str | None,
        date_posted: str | None,
        job_type: str | None,
        experience_level: str | None,
        work_type: str | None,
        easy_apply: bool,
        sort_by: str | None,
    ) -> tuple[str, str | None]:
        terms = [keywords.strip()]
        api_location = location.strip() if location else None

        if api_location and api_location.lower() == "remote":
            api_location = None
            terms.append("remote")

        date_terms = {
            "past_hour": "posted in the last hour",
            "past_24_hours": "since yesterday",
            "past_week": "in the last week",
            "past_month": "in the last month",
        }
        job_type_terms = {
            "full_time": "full time",
            "part_time": "part time",
            "contract": "contract",
            "temporary": "temporary",
            "volunteer": "volunteer",
            "internship": "internship",
            "other": "",
        }
        experience_terms = {
            "internship": "internship",
            "entry": "entry level",
            "associate": "associate",
            "mid_senior": "mid senior",
            "director": "director",
            "executive": "executive",
        }
        work_type_terms = {
            "remote": "remote",
            "on_site": "on-site",
            "hybrid": "hybrid",
        }

        for value, mapping in (
            (date_posted, date_terms),
            (job_type, job_type_terms),
            (experience_level, experience_terms),
            (work_type, work_type_terms),
        ):
            term = mapping.get(value or "")
            if term:
                terms.append(term)

        if easy_apply:
            terms.append('"easy apply"')
        if sort_by == "date" and not date_posted:
            terms.append("recent")

        return " ".join(term for term in terms if term).strip(), api_location

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
        """Search Google Jobs and cache result objects for downstream processing."""
        if not self._api_key:
            raise RuntimeError(
                "SERPAPI_API_KEY is required. Add it to backend/.env before scraping."
            )

        query, api_location = self._build_query(
            keywords=keywords,
            location=location,
            date_posted=date_posted,
            job_type=job_type,
            experience_level=experience_level,
            work_type=work_type,
            easy_apply=easy_apply,
            sort_by=sort_by,
        )

        params: dict[str, Any] = {
            "engine": "google_jobs",
            "q": query,
            "api_key": self._api_key,
            "google_domain": self._google_domain,
            "output": "json",
        }
        if api_location:
            params["location"] = api_location
        if self._gl:
            params["gl"] = self._gl
        if self._hl:
            params["hl"] = self._hl
        if self._no_cache:
            params["no_cache"] = "true"

        self._jobs = {}
        next_page_token: str | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for _ in range(max(1, max_pages)):
                page_params = dict(params)
                if next_page_token:
                    page_params["next_page_token"] = next_page_token

                response = await client.get(self._ENDPOINT, params=page_params)
                response.raise_for_status()
                payload = response.json()

                if payload.get("error"):
                    raise RuntimeError(f"SerpApi Google Jobs error: {payload['error']}")

                for job in payload.get("jobs_results", []) or []:
                    job_id = self._stable_job_id(job)
                    self._jobs[job_id] = job

                pagination = payload.get("serpapi_pagination") or {}
                next_page_token = pagination.get("next_page_token")
                if not next_page_token:
                    break

        return list(self._jobs.keys())

    @staticmethod
    def _format_job_text(job: dict[str, Any]) -> str:
        detected = job.get("detected_extensions") or {}
        lines = [
            f"Title: {job.get('title') or ''}",
            f"Company: {job.get('company_name') or ''}",
            f"Location: {job.get('location') or ''}",
            f"Source: {job.get('via') or 'Google Jobs'}",
        ]

        if detected.get("posted_at"):
            lines.append(f"Posted: {detected['posted_at']}")
        if detected.get("schedule_type"):
            lines.append(f"Schedule: {detected['schedule_type']}")
        if detected.get("work_from_home"):
            lines.append("Work arrangement: Remote")

        description = (job.get("description") or "").strip()
        if description:
            lines.extend(["", "Description:", description])

        for highlight in job.get("job_highlights", []) or []:
            title = highlight.get("title")
            items = highlight.get("items") or []
            if title and items:
                lines.extend(["", f"{title}:"])
                lines.extend(f"- {item}" for item in items if item)

        apply_options = job.get("apply_options") or []
        if apply_options:
            lines.extend(["", "Application options:"])
            for option in apply_options:
                if option.get("link"):
                    lines.append(
                        f"- {option.get('title') or 'Apply'}: {option['link']}"
                    )

        return "\n".join(lines).strip()

    async def fetch_details(self, job_id: str) -> dict[str, Any]:
        """Return a normalized detail object from the cached SerpApi result."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job ID not found in current SerpApi result set: {job_id}")

        return {
            "sections": {"job_posting": self._format_job_text(job)},
            "serpapi_job": job,
        }

    async def fetch_all_details(
        self,
        job_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return cached details while preserving the orchestrator contract."""
        results: dict[str, dict[str, Any]] = {}
        total = len(job_ids)

        for idx, job_id in enumerate(job_ids, start=1):
            try:
                results[job_id] = await self.fetch_details(job_id)
                if progress_callback:
                    progress_callback(idx, total, job_id)
            except Exception as exc:
                if progress_callback:
                    progress_callback(idx, total, f"{job_id} (ERROR: {exc})")

        return results
