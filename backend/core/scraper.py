from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

import httpx


class SerpApiGoogleJobsScraper:
    """Google Jobs discovery adapter backed by SerpApi."""

    _ENDPOINT = "https://serpapi.com/search"
    _TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")

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
        self._discovery_scores: dict[str, float] = {}

    @staticmethod
    def _stable_job_id(job: dict[str, Any]) -> str:
        if job.get("job_id"):
            return str(job["job_id"])
        identity = "|".join(
            str(job.get(key) or "").strip().lower()
            for key in ("title", "company_name", "location", "share_link")
        )
        return f"serpapi-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _dedupe_key(job: dict[str, Any]) -> str:
        if job.get("job_id"):
            return f"id:{job['job_id']}"
        identity = "|".join(
            str(job.get(key) or "").strip().lower()
            for key in ("title", "company_name", "location")
        )
        return f"fp:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return set(cls._TOKEN_RE.findall((text or "").lower()))

    @classmethod
    def _rank_job(cls, job: dict[str, Any], queries: list[str]) -> float:
        query_tokens = set().union(*(cls._tokens(q) for q in queries))
        if not query_tokens:
            return 0.0
        title_tokens = cls._tokens(str(job.get("title") or ""))
        description_tokens = cls._tokens(str(job.get("description") or ""))
        title_overlap = len(query_tokens & title_tokens) / max(len(query_tokens), 1)
        description_overlap = len(query_tokens & description_tokens) / max(len(query_tokens), 1)

        posted = str((job.get("detected_extensions") or {}).get("posted_at") or "").lower()
        recency = 0.0
        if "minute" in posted or "hour" in posted or "today" in posted:
            recency = 1.0
        elif "day" in posted or "yesterday" in posted:
            recency = 0.8
        elif "week" in posted:
            recency = 0.5
        elif "month" in posted:
            recency = 0.2

        return round((0.65 * title_overlap) + (0.25 * description_overlap) + (0.10 * recency), 4)

    @staticmethod
    def _build_query(
        keywords: str,
        date_posted: str | None,
        job_type: str | None,
        work_type: str | None,
    ) -> str:
        terms = [keywords.strip()]
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
            "internship": "internship",
        }
        work_type_terms = {
            "remote": "remote",
            "on_site": "on-site",
            "hybrid": "hybrid",
        }
        for value, mapping in (
            (date_posted, date_terms),
            (job_type, job_type_terms),
            (work_type, work_type_terms),
        ):
            term = mapping.get(value or "")
            if term:
                terms.append(term)
        return " ".join(term for term in terms if term).strip()

    async def _fetch_query(
        self,
        query: str,
        location: str | None,
        max_pages: int,
        radius_km: int | None,
        country: str | None,
        language: str | None,
        uds: str | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "engine": "google_jobs",
            "q": query,
            "api_key": self._api_key,
            "google_domain": self._google_domain,
            "output": "json",
        }
        if location:
            params["location"] = location
        if radius_km is not None:
            params["lrad"] = radius_km
        if country or self._gl:
            params["gl"] = country or self._gl
        if language or self._hl:
            params["hl"] = language or self._hl
        if uds:
            params["uds"] = uds
        if self._no_cache:
            params["no_cache"] = "true"

        jobs: list[dict[str, Any]] = []
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
                jobs.extend(payload.get("jobs_results", []) or [])
                next_page_token = (payload.get("serpapi_pagination") or {}).get("next_page_token")
                if not next_page_token:
                    break
        return jobs

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
        radius_km: int | None = None,
        country: str | None = None,
        language: str | None = None,
        uds: str | None = None,
        max_jobs: int = 50,
    ) -> list[str]:
        queries = [keywords]
        if experience_level:
            queries[0] = f"{queries[0]} {experience_level.replace('_', ' ')}"
        if easy_apply:
            queries[0] = f'{queries[0]} "easy apply"'
        if sort_by == "date" and not date_posted:
            queries[0] = f"{queries[0]} recent"
        return await self.search_many(
            queries=queries,
            location=location,
            max_pages=max_pages,
            date_posted=date_posted,
            job_type=job_type,
            work_type=work_type,
            radius_km=radius_km,
            country=country,
            language=language,
            uds=uds,
            max_jobs=max_jobs,
        )

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
        if not self._api_key:
            raise RuntimeError("SERPAPI_API_KEY is required. Add it to backend/.env before searching.")

        clean_queries = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
        if not clean_queries:
            return []

        deduped: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}

        for raw_query in clean_queries:
            query = self._build_query(raw_query, date_posted, job_type, work_type)
            jobs = await self._fetch_query(
                query=query,
                location=location,
                max_pages=max_pages,
                radius_km=radius_km,
                country=country,
                language=language,
                uds=uds,
            )
            for job in jobs:
                key = self._dedupe_key(job)
                score = self._rank_job(job, clean_queries)
                if key not in deduped or score > scores[key]:
                    enriched = dict(job)
                    enriched["_matched_query"] = raw_query
                    deduped[key] = enriched
                    scores[key] = score

        ranked = sorted(
            ((job, scores[key]) for key, job in deduped.items()),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, max_jobs)]

        self._jobs = {}
        self._discovery_scores = {}
        for job, score in ranked:
            job_id = self._stable_job_id(job)
            self._jobs[job_id] = job
            self._discovery_scores[job_id] = score

        return list(self._jobs.keys())

    def get_discovery_score(self, job_id: str) -> float | None:
        return self._discovery_scores.get(job_id)

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
                    lines.append(f"- {option.get('title') or 'Apply'}: {option['link']}")
        return "\n".join(lines).strip()

    async def fetch_details(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job ID not found in current SerpApi result set: {job_id}")
        return {"sections": {"job_posting": self._format_job_text(job)}, "serpapi_job": job}

    async def fetch_all_details(
        self,
        job_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
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
