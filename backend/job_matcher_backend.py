"""
LinkedIn Job Matcher — Production-Grade Python Backend
=======================================================
SOLID principles, full type annotations, plug-and-play architecture.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                         CLI / API Entry                      │
    └──────────────────────┬──────────────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────────────┐
    │                    Orchestrator (Facade)                     │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
    │  │  Resume     │  │  Job        │  │  Vector Store       │  │
    │  │  Parser     │  │  Scraper    │  │  (Qdrant)           │  │
    │  │  (Strategy) │  │  (Adapter)  │  │                     │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────┘  │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
    │  │  LLM        │  │  Embedder   │  │  Resume Advisor     │  │
    │  │  Extractor  │  │  (Adapter)  │  │  (Strategy)           │  │
    │  │  (Strategy) │  │             │  │                     │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────┘  │
    └─────────────────────────────────────────────────────────────┘

Usage:
    # 1. Start services
    uvx mcp-server-linkedin@latest --login
    uvx mcp-server-linkedin@latest --transport streamable-http --host 127.0.0.1 --port 8080 --path /mcp
    docker run -p 6333:6333 qdrant/qdrant
    ollama serve

    # 2. Scrape jobs
    python -m job_matcher scrape --keywords "AI Engineer" --location "Remote" --max-pages 3

    # 3. Parse resume & match
    python -m job_matcher match --resume path/to/resume.pdf --top-k 10

    # 4. Get resume improvement suggestions
    python -m job_matcher advise --resume path/to/resume.pdf --job-id <uuid>

Environment:
    QDRANT_URL=http://localhost:6333
    QDRANT_API_KEY=
    QDRANT_COLLECTION=linkedin_jobs
    EMBED_BASE_URL=http://localhost:11434/v1
    EMBED_MODEL=nomic-embed-text:v1.5
    EMBED_DIM=768
    LLM_BASE_URL=http://localhost:11434/v1
    LLM_MODEL=gemma3:4b
    MCP_LINKEDIN_URL=http://localhost:8080/mcp
"""

from __future__ import annotations

__version__ = "1.0.0"

import abc
import argparse
import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Coroutine,
    Final,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    cast,
)

import httpx
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models (Immutable Data Classes)
# ═══════════════════════════════════════════════════════════════════════════════


class WorkType(Enum):
    """Work arrangement classification."""
    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"
    UNKNOWN = None


class EmploymentType(Enum):
    """Employment contract classification."""
    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    VOLUNTEER = "volunteer"
    INTERNSHIP = "internship"
    OTHER = "other"
    UNKNOWN = None


class SeniorityLevel(Enum):
    """Career seniority classification."""
    INTERN = "intern"
    ENTRY = "entry"
    ASSOCIATE = "associate"
    MID_SENIOR = "mid_senior"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
    UNKNOWN = None


def safe_enum(enum_cls: type[Enum], value: Any) -> Enum:
    """Safely cast a value to an Enum, falling back to UNKNOWN if invalid."""
    if not value:
        return enum_cls.UNKNOWN
    try:
        return enum_cls(value)
    except ValueError:
        return enum_cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class RelativeTime:
    """Structured relative posting time (LLM extracts this, Python computes absolute)."""
    amount: int
    unit: Literal["minutes", "hours", "days", "weeks", "months", "years"]


@dataclass(frozen=True, slots=True)
class JobPosting:
    """Canonical representation of a scraped LinkedIn job posting."""
    job_id: str
    company: str | None
    title: str | None
    location: str | None
    work_type: WorkType
    employment_type: EmploymentType
    easy_apply: bool
    posted_raw_text: str | None
    posted_at: datetime | None
    applicants_count: int | None
    applicants_approx: bool
    skills: tuple[str, ...]
    tools_technologies: tuple[str, ...]
    required_experience: str | None
    seniority_level: SeniorityLevel
    education_requirements: str | None
    key_responsibilities: tuple[str, ...]
    salary_range: str | None
    benefits: tuple[str, ...] | None
    remote_type: WorkType
    description: str
    search_keywords: str | None = None
    search_location: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    scraped_at: datetime | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize to Qdrant-compatible payload dict."""
        return {
            "job_id": self.job_id,
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "work_type": self.work_type.value,
            "employment_type": self.employment_type.value,
            "easy_apply": self.easy_apply,
            "posted_raw_text": self.posted_raw_text,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "applicants_count": self.applicants_count,
            "applicants_approx": self.applicants_approx,
            "skills": list(self.skills),
            "tools_technologies": list(self.tools_technologies),
            "required_experience": self.required_experience,
            "seniority_level": self.seniority_level.value,
            "education_requirements": self.education_requirements,
            "key_responsibilities": list(self.key_responsibilities),
            "salary_range": self.salary_range,
            "benefits": list(self.benefits) if self.benefits else None,
            "remote_type": self.remote_type.value,
            "description": self.description,
            "search_keywords": self.search_keywords,
            "search_location": self.search_location,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }

    @property
    def linkedin_url(self) -> str:
        """Generate the direct LinkedIn job application URL."""
        return f"https://www.linkedin.com/jobs/view/{self.job_id}"

    @property
    def embedding_text(self) -> str:
        """Text representation used for semantic embedding."""
        parts = [
            f"title: {self.title}",
            f"company: {self.company}",
            f"location: {self.location}",
            f"work_type: {self.work_type.value}",
            f"employment_type: {self.employment_type.value}",
        ]
        if self.skills:
            parts.append(f"skills: {', '.join(self.skills)}")
        if self.required_experience:
            parts.append(f"required_experience: {self.required_experience}")
        if self.seniority_level != SeniorityLevel.UNKNOWN:
            parts.append(f"seniority_level: {self.seniority_level.value}")
        parts.append(self.description)
        return "\n".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class ResumeProfile:
    """Structured representation of a parsed resume."""
    raw_text: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: tuple[str, ...] = field(default_factory=tuple)
    tools_technologies: tuple[str, ...] = field(default_factory=tuple)
    experience_years: float | None = None
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    education: tuple[str, ...] = field(default_factory=tuple)
    certifications: tuple[str, ...] = field(default_factory=tuple)
    projects: tuple[str, ...] = field(default_factory=tuple)
    industries: tuple[str, ...] = field(default_factory=tuple)
    target_roles: tuple[str, ...] = field(default_factory=tuple)

    @property
    def embedding_text(self) -> str:
        """Text representation used for semantic embedding / search."""
        parts = [
            f"summary: {self.summary}",
            f"skills: {', '.join(self.skills)}",
            f"tools: {', '.join(self.tools_technologies)}",
            f"experience: {self.experience_years} years",
            f"seniority: {self.seniority_level.value}",
            f"education: {', '.join(self.education)}",
            f"projects: {', '.join(self.projects)}",
            f"target_roles: {', '.join(self.target_roles)}",
        ]
        return "\n".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class MatchedJob:
    """A job posting with its similarity score to a resume."""
    job: JobPosting
    similarity_score: float
    match_reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResumeAdvice:
    """Actionable advice for improving a resume for a specific job."""
    job_id: str
    job_title: str | None
    company: str | None
    overall_score: float  # 0.0 - 1.0
    summary_suggestions: tuple[str, ...]
    skills_to_add: tuple[str, ...]
    skills_to_emphasize: tuple[str, ...]
    project_suggestions: tuple[str, ...]
    experience_gaps: tuple[str, ...]
    certification_suggestions: tuple[str, ...]
    tailored_summary: str | None  # AI-generated improved summary


# ═══════════════════════════════════════════════════════════════════════════════
# Protocols (Interfaces) — The "I" in SOLID
# ═══════════════════════════════════════════════════════════════════════════════


class IJobScraper(Protocol):
    """Interface for job scraping adapters."""

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
        """Return list of job IDs matching search criteria."""
        ...

    async def fetch_details(self, job_id: str) -> dict[str, Any]:
        """Fetch raw details for a single job ID."""
        ...


class IJobExtractor(Protocol):
    """Interface for structured field extraction from raw job text."""

    def extract(self, raw_job_text: str) -> dict[str, Any]:
        """Extract structured fields from raw job posting text."""
        ...


class IEmbedder(Protocol):
    """Interface for text embedding adapters."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into dense vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimensionality."""
        ...


class IVectorStore(Protocol):
    """Interface for vector database adapters."""

    def ensure_collection(self, name: str, dimension: int) -> None:
        """Create collection if it doesn't exist."""
        ...

    def upsert_jobs(self, jobs: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        """Upsert jobs: (point_id, vector, payload)."""
        ...

    def search_similar(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors, return payloads."""
        ...

    def get_first_seen(self, point_id: str) -> datetime | None:
        """Retrieve first_seen_at timestamp for idempotency."""
        ...


class IResumeParser(Protocol):
    """Interface for resume parsing strategies."""

    def parse(self, file_path: Path) -> ResumeProfile:
        """Parse a resume file into a structured profile."""
        ...


class IResumeAdvisor(Protocol):
    """Interface for resume improvement advice generation."""

    def generate_advice(
        self,
        resume: ResumeProfile,
        job: JobPosting,
    ) -> ResumeAdvice:
        """Generate tailored advice for a resume-job pair."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Time Utilities (Deterministic, Single Responsibility)
# ═══════════════════════════════════════════════════════════════════════════════

VALID_TIME_UNITS: Final[frozenset[str]] = frozenset(
    {"minutes", "hours", "days", "weeks", "months", "years"}
)

_UNIT_TO_DELTA: Final[dict[str, Callable[[int], timedelta]]] = {
    "minutes": lambda n: timedelta(minutes=n),
    "hours": lambda n: timedelta(hours=n),
    "days": lambda n: timedelta(days=n),
    "weeks": lambda n: timedelta(weeks=n),
    "months": lambda n: timedelta(days=n * 30),
    "years": lambda n: timedelta(days=n * 365),
}


def compute_posted_at(
    amount: int | None,
    unit: str | None,
    reference: datetime,
) -> datetime | None:
    """Convert relative time to absolute UTC timestamp.

    Args:
        amount: Numeric amount (e.g., 10).
        unit: Time unit from VALID_TIME_UNITS.
        reference: Anchor datetime (typically scrape time).

    Returns:
        Absolute UTC datetime, or None if inputs invalid.
    """
    if amount is None or unit is None:
        return None
    if unit not in VALID_TIME_UNITS:
        return None
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return None
    if amount < 0:
        return None

    posted_at = reference - _UNIT_TO_DELTA[unit](amount)
    return min(posted_at, reference)  # Guard against future dates


# ═══════════════════════════════════════════════════════════════════════════════
# Concrete Implementations
# ═══════════════════════════════════════════════════════════════════════════════


class LinkedInMCPScraper:
    """Adapter: LinkedIn MCP Server via langchain-mcp-adapters.

    Implements IJobScraper. Handles connection lifecycle and retry logic
    for truncated responses.
    """

    def __init__(
        self,
        mcp_url: str = "http://localhost:8080/mcp",
        detail_delay: float = 1.5,
        concurrency: int = 1,
        min_posting_chars: int = 300,
        max_retries: int = 3,
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


class LLMJobExtractor:
    """Strategy: Use local LLM (e.g., gemma3:4b via Ollama) for structured extraction.

    Implements IJobExtractor. The model handles language understanding;
    Python owns all arithmetic (posted_at computation).
    """

    SYSTEM_PROMPT: Final[str] = (
        "You are an information extraction engine for LinkedIn job postings.\n"
        "Given the raw text of a LinkedIn job posting, extract structured fields.\n\n"
        "Respond with STRICT JSON ONLY — no markdown fences, no commentary.\n"
        "Use null for anything not mentioned. Keep lists short and deduplicated.\n\n"
        "IMPORTANT about dates: do NOT calculate an actual calendar date.\n"
        "Only report the relative time as structured components.\n"
        'For example "10 hours ago" -> posted_amount=10, posted_unit="hours".\n'
        '"Reposted 2 weeks ago" -> posted_amount=2, posted_unit="weeks".\n'
        '"Yesterday" -> posted_amount=1, posted_unit="days".\n'
        '"Today" / "Just now" -> posted_amount=0, posted_unit="hours".\n\n'
        "JSON schema:\n"
        "{\n"
        '  "company": string or null,\n'
        '  "title": string or null,\n'
        '  "location": string or null,\n'
        '  "work_type": one of ["remote","onsite","hybrid", null],\n'
        '  "employment_type": one of ["full-time","part-time","contract","temporary","volunteer","internship","other", null],\n'
        '  "easy_apply": boolean,\n'
        '  "posted_raw_text": string or null,\n'
        '  "posted_amount": integer or null,\n'
        '  "posted_unit": one of ["minutes","hours","days","weeks","months","years", null],\n'
        '  "applicants_count": integer or null,\n'
        '  "applicants_approx": boolean,\n'
        '  "skills": [string],\n'
        '  "tools_technologies": [string],\n'
        '  "required_experience": string or null,\n'
        '  "seniority_level": one of ["intern","entry","associate","mid_senior","director","executive", null],\n'
        '  "education_requirements": string or null,\n'
        '  "key_responsibilities": [string],\n'
        '  "salary_range": string or null,\n'
        '  "benefits": [string] or null,\n'
        '  "remote_type": one of ["remote","hybrid","onsite", null],\n'
        '  "description": string\n'
        "}"
    )

    def __init__(
        self,
        client: OpenAI,
        model: str,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def extract(self, raw_job_text: str) -> dict[str, Any]:
        """Extract structured fields from raw job posting text.

        Args:
            raw_job_text: The complete raw text of the job posting.

        Returns:
            Dictionary of extracted fields, empty dict on failure.
        """
        user_prompt = f"Job posting:\n\n{raw_job_text}\n\nExtract the fields as JSON."
        last_err: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                raw = resp.choices[0].message.content
                cleaned = self._strip_json_fences(raw or "")
                return json.loads(cleaned)
            except Exception as e:
                last_err = e
                if attempt < self._max_retries:
                    continue

        print(f"  ! LLM extraction failed after {self._max_retries} attempts: {last_err}")
        return {}


class OllamaEmbedder:
    """Adapter: Ollama/OpenAI-compatible embedding endpoint.

    Implements IEmbedder. Uses nomic-embed-text or similar local models.
    """

    def __init__(self, client: OpenAI, model: str, dimension: int) -> None:
        self._client = client
        self._model = model
        self._dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    @property
    def dimension(self) -> int:
        return self._dimension


class QdrantVectorStore:
    """Adapter: Qdrant vector database.

    Implements IVectorStore. Handles collection management, idempotent
    upserts, and semantic search.
    """

    NAMESPACE: Final = uuid.NAMESPACE_URL

    def __init__(self, client: QdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection = collection_name

    def _point_id(self, job_id: str) -> str:
        return str(uuid.uuid5(self.NAMESPACE, job_id))

    def ensure_collection(self, name: str, dimension: int) -> None:
        existing = [c.name for c in self._client.get_collections().collections]
        if name not in existing:
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=dimension, distance=qmodels.Distance.COSINE
                ),
            )
            print(f"Created Qdrant collection '{name}' (dim={dimension}, cosine)")

    def upsert_jobs(self, jobs: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        points = [
            qmodels.PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in jobs
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def search_similar(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        qfilter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchAny(any=value),
                        )
                    )
                else:
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value),
                        )
                    )
            qfilter = qmodels.Filter(must=conditions)

        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        ).points
        return [{**r.payload, "score": r.score} for r in results if r.payload]

    def get_first_seen(self, point_id: str) -> datetime | None:
        try:
            pts = self._client.retrieve(
                collection_name=self._collection,
                ids=[point_id],
                with_payload=True,
            )
            if pts:
                fs = pts[0].payload.get("first_seen_at")
                if fs:
                    return datetime.fromisoformat(fs)
        except Exception:
            pass
        return None


class PDFResumeParser:
    """Strategy: Parse PDF resumes using pdfplumber + LLM enhancement.

    Implements IResumeParser. Extracts raw text, then uses LLM for
    structured field extraction.
    """

    RESUME_EXTRACTION_PROMPT: Final[str] = (
        "You are a resume parsing engine. Extract structured information from the following resume text.\n"
        "Respond with STRICT JSON ONLY — no markdown fences, no commentary.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "name": string or null,\n'
        '  "email": string or null,\n'
        '  "phone": string or null,\n'
        '  "location": string or null,\n'
        '  "summary": string or null,\n'
        '  "skills": [string],\n'
        '  "tools_technologies": [string],\n'
        '  "experience_years": number or null,\n'
        '  "seniority_level": one of ["intern","entry","associate","mid_senior","director","executive", null],\n'
        '  "education": [string],\n'
        '  "certifications": [string],\n'
        '  "projects": [string],\n'
        '  "industries": [string],\n'
        '  "target_roles": [string]\n'
        "}"
    )

    def __init__(
        self,
        llm_client: OpenAI,
        llm_model: str,
    ) -> None:
        self._llm_client = llm_client
        self._llm_model = llm_model

    def _extract_text(self, file_path: Path) -> str:
        """Extract raw text from PDF."""
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _llm_enhance(self, raw_text: str) -> dict[str, Any]:
        """Use LLM to structure the raw resume text."""
        try:
            resp = self._llm_client.chat.completions.create(
                model=self._llm_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": self.RESUME_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Resume text:\n\n{raw_text}"},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            cleaned = LLMJobExtractor._strip_json_fences(raw)
            return json.loads(cleaned)
        except Exception as e:
            print(f"  ! Resume LLM extraction failed: {e}")
            return {}

    def parse(self, file_path: Path) -> ResumeProfile:
        """Parse a PDF resume into a structured profile.

        Args:
            file_path: Path to the PDF resume file.

        Returns:
            Structured ResumeProfile.
        """
        raw_text = self._extract_text(file_path)
        extracted = self._llm_enhance(raw_text)

        def _to_tuple(val: Any) -> tuple[str, ...]:
            if isinstance(val, list):
                return tuple(str(v) for v in val if v)
            return ()

        def _safe_seniority(val: Any) -> SeniorityLevel:
            if not val:
                return SeniorityLevel.UNKNOWN
            try:
                return SeniorityLevel(val)
            except ValueError:
                return SeniorityLevel.UNKNOWN

        return ResumeProfile(
            raw_text=raw_text,
            name=extracted.get("name"),
            email=extracted.get("email"),
            phone=extracted.get("phone"),
            location=extracted.get("location"),
            summary=extracted.get("summary"),
            skills=_to_tuple(extracted.get("skills")),
            tools_technologies=_to_tuple(extracted.get("tools_technologies")),
            experience_years=extracted.get("experience_years"),
            seniority_level=_safe_seniority(extracted.get("seniority_level")),
            education=_to_tuple(extracted.get("education")),
            certifications=_to_tuple(extracted.get("certifications")),
            projects=_to_tuple(extracted.get("projects")),
            industries=_to_tuple(extracted.get("industries")),
            target_roles=_to_tuple(extracted.get("target_roles")),
        )


class LLMResumeAdvisor:
    """Strategy: Generate resume improvement advice using LLM.

    Implements IResumeAdvisor. Compares resume against job requirements
    and produces actionable, structured feedback.
    """

    ADVICE_PROMPT: Final[str] = (
        "You are an expert career coach and resume optimizer.\n"
        "Given a candidate's resume profile and a job posting, analyze the match\n"
        "and provide structured, actionable advice to improve the resume for THIS specific job.\n\n"
        "Respond with STRICT JSON ONLY — no markdown fences, no commentary.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "overall_score": number (0.0-1.0),\n'
        '  "summary_suggestions": [string],\n'
        '  "skills_to_add": [string],\n'
        '  "skills_to_emphasize": [string],\n'
        '  "project_suggestions": [string],\n'
        '  "experience_gaps": [string],\n'
        '  "certification_suggestions": [string],\n'
        '  "tailored_summary": string or null\n'
        "}\n\n"
        "overall_score: How well the resume matches the job (0.0 = no match, 1.0 = perfect).\n"
        "summary_suggestions: Specific changes to the professional summary.\n"
        "skills_to_add: Technical/soft skills missing from the resume but required by the job.\n"
        "skills_to_emphasize: Skills the candidate has that are highly relevant and should be highlighted.\n"
        "project_suggestions: Project ideas or ways to reframe existing projects to match job requirements.\n"
        "experience_gaps: Missing experience areas that the job requires.\n"
        "certification_suggestions: Certifications that would strengthen the application.\n"
        "tailored_summary: A rewritten professional summary optimized for this job."
    )

    def __init__(self, llm_client: OpenAI, llm_model: str) -> None:
        self._llm_client = llm_client
        self._llm_model = llm_model

    def generate_advice(
        self,
        resume: ResumeProfile,
        job: JobPosting,
    ) -> ResumeAdvice:
        """Generate tailored resume advice for a specific job.

        Args:
            resume: Parsed candidate resume.
            job: Target job posting.

        Returns:
            Structured advice with actionable improvements.
        """
        user_content = (
            f"RESUME PROFILE:\n"
            f"Name: {resume.name}\n"
            f"Summary: {resume.summary}\n"
            f"Skills: {', '.join(resume.skills)}\n"
            f"Tools: {', '.join(resume.tools_technologies)}\n"
            f"Experience: {resume.experience_years} years\n"
            f"Seniority: {resume.seniority_level.value}\n"
            f"Education: {', '.join(resume.education)}\n"
            f"Certifications: {', '.join(resume.certifications)}\n"
            f"Projects: {', '.join(resume.projects)}\n"
            f"Target Roles: {', '.join(resume.target_roles)}\n\n"
            f"JOB POSTING:\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description: {job.description}\n"
            f"Required Skills: {', '.join(job.skills)}\n"
            f"Tools: {', '.join(job.tools_technologies)}\n"
            f"Experience Required: {job.required_experience}\n"
            f"Seniority: {job.seniority_level.value}\n"
            f"Education: {job.education_requirements}\n"
            f"Responsibilities: {', '.join(job.key_responsibilities)}"
        )

        try:
            resp = self._llm_client.chat.completions.create(
                model=self._llm_model,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": self.ADVICE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            cleaned = LLMJobExtractor._strip_json_fences(raw)
            data = json.loads(cleaned)
        except Exception as e:
            print(f"  ! Advice generation failed: {e}")
            data = {}

        def _to_tuple(val: Any) -> tuple[str, ...]:
            return tuple(v for v in (val or []) if v)

        return ResumeAdvice(
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            overall_score=float(data.get("overall_score", 0.0)),
            summary_suggestions=_to_tuple(data.get("summary_suggestions")),
            skills_to_add=_to_tuple(data.get("skills_to_add")),
            skills_to_emphasize=_to_tuple(data.get("skills_to_emphasize")),
            project_suggestions=_to_tuple(data.get("project_suggestions")),
            experience_gaps=_to_tuple(data.get("experience_gaps")),
            certification_suggestions=_to_tuple(data.get("certification_suggestions")),
            tailored_summary=data.get("tailored_summary"),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Job Builder (Single Responsibility: Map raw -> domain model)
# ═══════════════════════════════════════════════════════════════════════════════


class JobPostingBuilder:
    """Builder pattern: Construct JobPosting from raw extraction + metadata.

    Handles all enum mapping, tuple conversion, and timestamp computation.
    """

    @staticmethod
    def _map_enum(value: str | None, enum_cls: type[Enum], default: Enum) -> Enum:
        if not value:
            return default
        try:
            return enum_cls(value.lower())
        except ValueError:
            return default

    @classmethod
    def build(
        cls,
        job_id: str,
        raw_fields: dict[str, Any],
        search_keywords: str | None,
        search_location: str | None,
        scrape_time: datetime,
        first_seen: datetime | None,
    ) -> JobPosting:
        """Build a canonical JobPosting from LLM-extracted fields.

        Args:
            job_id: LinkedIn internal job ID.
            raw_fields: Dict from LLMJobExtractor.extract().
            search_keywords: Original search query keywords.
            search_location: Original search query location.
            scrape_time: UTC datetime of this scrape run.
            first_seen: First time this job was seen (for idempotency).

        Returns:
            Fully populated JobPosting domain model.
        """
        posted_at = compute_posted_at(
            raw_fields.get("posted_amount"),
            raw_fields.get("posted_unit"),
            scrape_time,
        )

        def _to_tuple(val: Any) -> tuple[str, ...]:
            if isinstance(val, list):
                return tuple(str(v) for v in val if v)
            return ()

        return JobPosting(
            job_id=job_id,
            company=raw_fields.get("company"),
            title=raw_fields.get("title"),
            location=raw_fields.get("location"),
            work_type=cls._map_enum(raw_fields.get("work_type"), WorkType, WorkType.UNKNOWN),
            employment_type=cls._map_enum(
                raw_fields.get("employment_type"), EmploymentType, EmploymentType.UNKNOWN
            ),
            easy_apply=bool(raw_fields.get("easy_apply", False)),
            posted_raw_text=raw_fields.get("posted_raw_text"),
            posted_at=posted_at,
            applicants_count=raw_fields.get("applicants_count"),
            applicants_approx=bool(raw_fields.get("applicants_approx", False)),
            skills=_to_tuple(raw_fields.get("skills")),
            tools_technologies=_to_tuple(raw_fields.get("tools_technologies")),
            required_experience=raw_fields.get("required_experience"),
            seniority_level=cls._map_enum(
                raw_fields.get("seniority_level"), SeniorityLevel, SeniorityLevel.UNKNOWN
            ),
            education_requirements=raw_fields.get("education_requirements"),
            key_responsibilities=_to_tuple(raw_fields.get("key_responsibilities")),
            salary_range=raw_fields.get("salary_range"),
            benefits=_to_tuple(raw_fields.get("benefits")) if raw_fields.get("benefits") else None,
            remote_type=cls._map_enum(raw_fields.get("remote_type"), WorkType, WorkType.UNKNOWN),
            description=raw_fields.get("description", ""),
            search_keywords=search_keywords,
            search_location=search_location,
            first_seen_at=first_seen or scrape_time,
            last_seen_at=scrape_time,
            scraped_at=scrape_time,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator (Facade Pattern — Coordinates all subsystems)
# ═══════════════════════════════════════════════════════════════════════════════


class JobMatcherOrchestrator:
    """Facade: Coordinates scraping, extraction, embedding, storage, and matching.

    This is the main entry point. It owns no business logic itself;
    it delegates to injected adapters and strategies.
    """

    def __init__(
        self,
        scraper: IJobScraper,
        extractor: IJobExtractor,
        embedder: IEmbedder,
        vector_store: IVectorStore,
        resume_parser: IResumeParser,
        resume_advisor: IResumeAdvisor,
        llm_delay: float = 0.5,
    ) -> None:
        self._scraper = scraper
        self._extractor = extractor
        self._embedder = embedder
        self._vector_store = vector_store
        self._resume_parser = resume_parser
        self._resume_advisor = resume_advisor
        self._llm_delay = llm_delay

    async def scrape_and_store(
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
        dry_run: bool = False,
    ) -> list[JobPosting]:
        """Full pipeline: search -> fetch -> extract -> embed -> store.

        Returns:
            List of successfully processed JobPostings.
        """
        now = datetime.now(timezone.utc)
        print(f"🔍 Searching LinkedIn: keywords='{keywords}' location='{location}'")

        job_ids = await self._scraper.search(
            keywords=keywords,
            location=location,
            max_pages=max_pages,
            date_posted=date_posted,
            job_type=job_type,
            experience_level=experience_level,
            work_type=work_type,
            easy_apply=easy_apply,
            sort_by=sort_by,
        )
        print(f"📋 Found {len(job_ids)} jobs")

        if not job_ids:
            return []

        # Fetch details
        print("\n📥 Fetching job details...")
        if hasattr(self._scraper, "fetch_all_details"):
            details = await self._scraper.fetch_all_details(
                job_ids,
                progress_callback=lambda i, total, jid: print(f"  [{i}/{total}] {jid}"),
            )
        else:
            details = {}
            for i, jid in enumerate(job_ids, 1):
                print(f"  [{i}/{len(job_ids)}] {jid}")
                details[jid] = await self._scraper.fetch_details(jid)

        # Extract structured fields
        print(f"\n🤖 Extracting structured fields...")
        fields_by_id: dict[str, dict[str, Any]] = {}
        for i, (jid, detail) in enumerate(details.items(), 1):
            posting_text = (detail or {}).get("sections", {}).get("job_posting", "")
            fields = self._extractor.extract(posting_text)
            print(f"  [{i}/{len(details)}] {jid}: {fields.get('title', 'N/A')!r} @ {fields.get('company', 'N/A')!r}")
            fields_by_id[jid] = fields
            await asyncio.sleep(self._llm_delay)

        # Build domain models
        jobs: list[JobPosting] = []
        for jid, fields in fields_by_id.items():
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, jid))
            first_seen = self._vector_store.get_first_seen(point_id)
            job = JobPostingBuilder.build(
                job_id=jid,
                raw_fields=fields,
                search_keywords=keywords,
                search_location=location,
                scrape_time=now,
                first_seen=first_seen,
            )
            jobs.append(job)

        if dry_run:
            print("\n[dry-run] Results:")
            for job in jobs:
                print(json.dumps(job.to_payload(), indent=2, default=str))
            return jobs

        # Embed and store
        self._vector_store.ensure_collection(
            self._vector_store._collection if hasattr(self._vector_store, "_collection") else "linkedin_jobs",
            self._embedder.dimension,
        )

        texts = [job.embedding_text for job in jobs]
        print(f"\n🔢 Embedding {len(texts)} jobs...")
        vectors = self._embedder.embed(texts)

        store_jobs = []
        for job, vector in zip(jobs, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, job.job_id))
            store_jobs.append((point_id, vector, job.to_payload()))

        self._vector_store.upsert_jobs(store_jobs)
        print(f"\n✅ Upserted {len(store_jobs)} jobs into vector store.")

        return jobs

    def match_resume(
        self,
        resume_path: Path,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[MatchedJob]:
        """Parse resume and find top-k similar jobs from vector store.

        Args:
            resume_path: Path to PDF resume.
            top_k: Number of matches to return.
            filters: Optional Qdrant payload filters (e.g., {"work_type": "remote"}).

        Returns:
            List of MatchedJob ordered by similarity (descending).
        """
        print(f"\n📄 Parsing resume: {resume_path}")
        resume = self._resume_parser.parse(resume_path)
        print(f"  👤 {resume.name} | Skills: {', '.join(resume.skills[:5])}...")

        print(f"\n🔎 Searching vector store for top {top_k} matches...")
        resume_vector = self._embedder.embed([resume.embedding_text])[0]
        results = self._vector_store.search_similar(resume_vector, top_k=top_k, filters=filters)

        matched: list[MatchedJob] = []
        for result in results:
            # Reconstruct JobPosting from payload
            payload = result
            job = JobPosting(
                job_id=payload.get("job_id", ""),
                company=payload.get("company"),
                title=payload.get("title"),
                location=payload.get("location"),
                work_type=safe_enum(WorkType, payload.get("work_type")),
                employment_type=safe_enum(EmploymentType, payload.get("employment_type")),
                easy_apply=payload.get("easy_apply", False),
                posted_raw_text=payload.get("posted_raw_text"),
                posted_at=datetime.fromisoformat(payload["posted_at"]) if payload.get("posted_at") else None,
                applicants_count=payload.get("applicants_count"),
                applicants_approx=payload.get("applicants_approx", False),
                skills=tuple(payload.get("skills", [])),
                tools_technologies=tuple(payload.get("tools_technologies", [])),
                required_experience=payload.get("required_experience"),
                seniority_level=safe_enum(SeniorityLevel, payload.get("seniority_level")),
                education_requirements=payload.get("education_requirements"),
                key_responsibilities=tuple(payload.get("key_responsibilities", [])),
                salary_range=payload.get("salary_range"),
                benefits=tuple(payload.get("benefits", [])) if payload.get("benefits") else None,
                remote_type=safe_enum(WorkType, payload.get("remote_type")),
                description=payload.get("description", ""),
            )
            score = result.get("score", 0.0)
            matched.append(MatchedJob(job=job, similarity_score=score))

        matched.sort(key=lambda m: m.similarity_score, reverse=True)
        return matched

    def advise_for_job(
        self,
        resume_path: Path,
        job_id: str,
    ) -> ResumeAdvice | None:
        """Generate resume improvement advice for a specific job.

        Args:
            resume_path: Path to PDF resume.
            job_id: LinkedIn job ID to target.

        Returns:
            ResumeAdvice or None if job not found.
        """
        resume = self._resume_parser.parse(resume_path)

        # Fetch job from vector store by ID
        # Note: This requires a get_by_id method; for now we search with high limit
        # and filter manually, or the caller should have the JobPosting object.
        # In a real implementation, add IVectorStore.get_by_job_id()
        print(f"\n💡 Generating advice for job {job_id}...")

        # Placeholder: In production, implement get_by_id in QdrantVectorStore
        # For now, we assume the caller passes the job or we search broadly
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════════


def _build_orchestrator(args: argparse.Namespace) -> JobMatcherOrchestrator:
    """Factory: Wire up all dependencies based on CLI args / env vars."""
    # LLM client (shared)
    llm_client = OpenAI(base_url=args.llm_base_url, api_key="local")

    # Scraper
    scraper = LinkedInMCPScraper(
        mcp_url=args.mcp_url,
        detail_delay=args.detail_delay,
        concurrency=args.concurrency,
        min_posting_chars=args.min_posting_chars,
        max_retries=args.detail_max_retries,
        retry_delay=args.detail_retry_delay,
    )

    # Extractor
    extractor = LLMJobExtractor(
        client=llm_client,
        model=args.llm_model,
    )

    # Embedder
    embed_client = OpenAI(base_url=args.embed_base_url, api_key="local")
    embedder = OllamaEmbedder(
        client=embed_client,
        model=args.embed_model,
        dimension=args.embed_dim,
    )

    # Vector Store
    qdrant = QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key)
    vector_store = QdrantVectorStore(qdrant, args.collection)

    # Resume Parser
    resume_parser = PDFResumeParser(llm_client=llm_client, llm_model=args.llm_model)

    # Resume Advisor
    resume_advisor = LLMResumeAdvisor(llm_client=llm_client, llm_model=args.llm_model)

    return JobMatcherOrchestrator(
        scraper=scraper,
        extractor=extractor,
        embedder=embedder,
        vector_store=vector_store,
        resume_parser=resume_parser,
        resume_advisor=resume_advisor,
        llm_delay=args.llm_delay,
    )


def _add_scrape_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-k", "--keywords", required=True, help="Search keywords")
    parser.add_argument("-l", "--location", default=None, help="Location filter")
    parser.add_argument("--max-pages", type=int, default=3, choices=range(1, 11), metavar="[1-10]")
    parser.add_argument("--date-posted", choices=["past_hour", "past_24_hours", "past_week", "past_month"], default=None)
    parser.add_argument("--job-type", default=None, help="Comma-separated job types")
    parser.add_argument("--experience-level", default=None)
    parser.add_argument("--work-type", default=None, help="Comma-separated: on_site,remote,hybrid")
    parser.add_argument("--easy-apply", action="store_true")
    parser.add_argument("--sort-by", choices=["date", "relevance"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Skip embedding and storage")


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mcp-url", default=os.environ.get("MCP_LINKEDIN_URL", "http://localhost:8080/mcp"))
    parser.add_argument("--detail-delay", type=float, default=1.5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--min-posting-chars", type=int, default=300)
    parser.add_argument("--detail-max-retries", type=int, default=3)
    parser.add_argument("--detail-retry-delay", type=float, default=2.0)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", "linkedin_jobs"))
    parser.add_argument("--embed-base-url", default=os.environ.get("EMBED_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "nomic-embed-text:v1.5"))
    parser.add_argument("--embed-dim", type=int, default=int(os.environ.get("EMBED_DIM", "768")))
    parser.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", "gemma3:4b"))
    parser.add_argument("--llm-delay", type=float, default=0.5)


def _cmd_scrape(args: argparse.Namespace) -> None:
    """Execute the scrape command."""
    orchestrator = _build_orchestrator(args)
    jobs = asyncio.run(orchestrator.scrape_and_store(
        keywords=args.keywords,
        location=args.location,
        max_pages=args.max_pages,
        date_posted=args.date_posted,
        job_type=args.job_type,
        experience_level=args.experience_level,
        work_type=args.work_type,
        easy_apply=args.easy_apply,
        sort_by=args.sort_by,
        dry_run=args.dry_run,
    ))
    print(f"\n🎉 Scraped and stored {len(jobs)} jobs.")


def _cmd_match(args: argparse.Namespace) -> None:
    """Execute the match command."""
    orchestrator = _build_orchestrator(args)
    matches = orchestrator.match_resume(
        resume_path=Path(args.resume),
        top_k=args.top_k,
        filters=json.loads(args.filters) if args.filters else None,
    )

    print(f"\n{'='*60}")
    print(f"🎯 TOP {len(matches)} MATCHING JOBS")
    print(f"{'='*60}")

    for i, match in enumerate(matches, 1):
        job = match.job
        score = match.similarity_score
        print(f"\n{i}. {job.title} @ {job.company}")
        print(f"   📍 {job.location} | 🏢 {job.work_type.value} | 💼 {job.employment_type.value}")
        print(f"   🔗 {job.linkedin_url}")
        print(f"   🎯 Match Score: {score:.3f}")
        print(f"   🛠️  Skills: {', '.join(job.skills[:5])}")
        if job.salary_range:
            print(f"   💰 {job.salary_range}")


def _cmd_advise(args: argparse.Namespace) -> None:
    """Execute the advise command."""
    orchestrator = _build_orchestrator(args)

    # First match to get the job
    matches = orchestrator.match_resume(
        resume_path=Path(args.resume),
        top_k=50,
    )
    target_job = next((m.job for m in matches if m.job.job_id == args.job_id), None)

    if not target_job:
        print(f"❌ Job {args.job_id} not found. Run 'match' first to see available jobs.")
        return

    resume = orchestrator._resume_parser.parse(Path(args.resume))
    advice = orchestrator._resume_advisor.generate_advice(resume, target_job)

    print(f"\n{'='*60}")
    print(f"💡 RESUME ADVISOR: {advice.job_title} @ {advice.company}")
    print(f"{'='*60}")
    print(f"\n📊 Overall Match Score: {advice.overall_score:.1%}")

    if advice.tailored_summary:
        print(f"\n✨ SUGGESTED PROFESSIONAL SUMMARY:")
        print(f"   {advice.tailored_summary}")

    if advice.summary_suggestions:
        print(f"\n📝 Summary Improvements:")
        for s in advice.summary_suggestions:
            print(f"   • {s}")

    if advice.skills_to_add:
        print(f"\n➕ Skills to Add:")
        for s in advice.skills_to_add:
            print(f"   • {s}")

    if advice.skills_to_emphasize:
        print(f"\n⭐ Skills to Emphasize:")
        for s in advice.skills_to_emphasize:
            print(f"   • {s}")

    if advice.project_suggestions:
        print(f"\n🚀 Project Suggestions:")
        for s in advice.project_suggestions:
            print(f"   • {s}")

    if advice.experience_gaps:
        print(f"\n⚠️  Experience Gaps:")
        for s in advice.experience_gaps:
            print(f"   • {s}")

    if advice.certification_suggestions:
        print(f"\n📜 Certification Suggestions:")
        for s in advice.certification_suggestions:
            print(f"   • {s}")


def main() -> None:
    """CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="job_matcher",
        description="LinkedIn Job Scraper + Resume Matcher + AI Advisor",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scrape
    scrape_parser = subparsers.add_parser("scrape", help="Scrape LinkedIn jobs and store in Qdrant")
    _add_scrape_args(scrape_parser)
    _add_shared_args(scrape_parser)
    scrape_parser.set_defaults(func=_cmd_scrape)

    # match
    match_parser = subparsers.add_parser("match", help="Parse resume and find matching jobs")
    match_parser.add_argument("--resume", required=True, help="Path to PDF resume")
    match_parser.add_argument("--top-k", type=int, default=10, help="Number of matches")
    match_parser.add_argument("--filters", default=None, help='JSON filter object, e.g., {"work_type": "remote"}')
    _add_shared_args(match_parser)
    match_parser.set_defaults(func=_cmd_match)

    # advise
    advise_parser = subparsers.add_parser("advise", help="Get resume improvement advice for a job")
    advise_parser.add_argument("--resume", required=True, help="Path to PDF resume")
    advise_parser.add_argument("--job-id", required=True, help="LinkedIn job ID to target")
    _add_shared_args(advise_parser)
    advise_parser.set_defaults(func=_cmd_advise)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
