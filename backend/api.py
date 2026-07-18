"""
FastAPI Microservice Wrapper for Job Matcher
============================================
Exposes the orchestrator via REST API for the Next.js frontend.

Run: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dotenv import load_dotenv

load_dotenv()

from core.models import JobPosting
from core.scraper import LinkedInMCPScraper
from core.extractor import LLMJobExtractor
from core.embedder import UniversalEmbedder
from core.vector_store import QdrantVectorStore
from core.resume_parser import PDFResumeParser
from core.advisor import LLMResumeAdvisor
from core.orchestrator import JobMatcherOrchestrator
from openai import OpenAI
from qdrant_client import QdrantClient


app = FastAPI(
    title="Job Matcher API",
    description="LinkedIn job scraping, resume matching, and AI resume advice",
    version="1.0.0",
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dependency Injection Container ──────────────────────────────────────────

_orch: JobMatcherOrchestrator | None = None


def get_orchestrator() -> JobMatcherOrchestrator:
    """Singleton orchestrator with lazy initialization."""
    global _orch
    if _orch is None:
        provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
        emb_provider = os.environ.get("EMBEDDING_PROVIDER", "ollama").lower()
        
        # Default to ollama configurations
        llm_base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
        llm_api_key = "local"
        embed_base_url = os.environ.get("EMBED_BASE_URL", "http://localhost:11434/v1")
        embed_api_key = "local"

        if provider == "openai":
            llm_base_url = "https://api.openai.com/v1"
            llm_api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "gemini":
            llm_base_url = embed_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            llm_api_key = os.environ.get("GEMINI_API_KEY", "")
        elif provider == "huggingface":
            llm_base_url = "https://router.huggingface.co/v1"
            llm_api_key = os.environ.get("HF_TOKEN", "")

        if emb_provider == "openai":
            embed_base_url = "https://api.openai.com/v1"
            embed_api_key = os.environ.get("OPENAI_API_KEY", "")
        elif emb_provider == "gemini":
            embed_base_url = embed_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            embed_api_key = os.environ.get("GEMINI_API_KEY", "")
        elif emb_provider == "huggingface":
            embed_base_url = "https://router.huggingface.co/v1"
            embed_api_key = os.environ.get("HF_TOKEN", "")

        llm_client = OpenAI(
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
        embed_client = OpenAI(
            base_url=embed_base_url,
            api_key=embed_api_key,
        )

        scraper = LinkedInMCPScraper(
            mcp_url=os.environ.get("MCP_LINKEDIN_URL", "http://localhost:8080/mcp"),
        )
        
        # Backward compatibility fallback
        fallback_model = os.environ.get("LLM_MODEL", "gemma3:4b")
        extractor_model = os.environ.get("EXTRACTOR_MODEL", fallback_model)
        advisor_model = os.environ.get("ADVISOR_MODEL", fallback_model)
        
        extractor = LLMJobExtractor(
            client=llm_client,
            model=extractor_model,
        )
        embedder = UniversalEmbedder(
            client=embed_client,
            model=os.environ.get("EMBED_MODEL", "nomic-embed-text:v1.5"),
            dimension=int(os.environ.get("EMBED_DIM", "768")),
        )
        qdrant = QdrantClient(
            url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY"),
        )
        vector_store = QdrantVectorStore(
            qdrant,
            os.environ.get("QDRANT_COLLECTION", "linkedin_jobs"),
        )
        resume_parser = PDFResumeParser(
            llm_client=llm_client,
            llm_model=advisor_model,
        )
        resume_advisor = LLMResumeAdvisor(
            llm_client=llm_client,
            llm_model=advisor_model,
        )

        _orch = JobMatcherOrchestrator(
            scraper=scraper,
            extractor=extractor,
            embedder=embedder,
            vector_store=vector_store,
            resume_parser=resume_parser,
            resume_advisor=resume_advisor,
        )
    return _orch


# ── Pydantic Models ─────────────────────────────────────────────────────────


class ScrapeRequest(BaseModel):
    keywords: str
    location: str | None = None
    max_pages: int = Field(default=3, ge=1, le=10)
    date_posted: str | None = None
    job_type: str | None = None
    experience_level: str | None = None
    work_type: str | None = None
    easy_apply: bool = False
    sort_by: str | None = None


class MatchResponse(BaseModel):
    success: bool
    resume: dict[str, Any]
    matches: list[dict[str, Any]]





class AdviceResponse(BaseModel):
    success: bool
    advice: dict[str, Any]


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/v1/scrape", response_model=dict)
async def scrape_jobs(req: ScrapeRequest) -> dict[str, Any]:
    """Trigger a LinkedIn job scrape and store results in Qdrant."""
    orch = get_orchestrator()
    jobs = await orch.scrape_and_store(
        keywords=req.keywords,
        location=req.location,
        max_pages=req.max_pages,
        date_posted=req.date_posted,
        job_type=req.job_type,
        experience_level=req.experience_level,
        work_type=req.work_type,
        easy_apply=req.easy_apply,
        sort_by=req.sort_by,
    )
    return {
        "success": True,
        "scraped": len(jobs),
        "jobs": [j.to_payload() for j in jobs],
    }

@app.post("/api/v1/scrape/stream")
async def scrape_jobs_stream(req: ScrapeRequest):
    """Stream SSE events during a scrape."""
    orch = get_orchestrator()
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    concurrency = 3 if provider in ["gemini", "openai", "huggingface"] else 1
    
    async def event_generator():
        async for event in orch.scrape_and_store_stream(
            keywords=req.keywords,
            location=req.location,
            max_pages=req.max_pages,
            date_posted=req.date_posted,
            job_type=req.job_type,
            experience_level=req.experience_level,
            work_type=req.work_type,
            easy_apply=req.easy_apply,
            sort_by=req.sort_by,
            concurrency=concurrency,
        ):
            yield f"data: {event}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/v1/match", response_model=MatchResponse)
async def match_resume(
    resume: UploadFile = File(...),
    top_k: int = Form(default=10),
    filters: str | None = Form(default=None),
) -> MatchResponse:
    """Upload a PDF resume and get top-k matching jobs."""
    if not resume.filename or not resume.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF resumes are supported")

    # Save uploaded file
    suffix = f"_{uuid.uuid4().hex[:8]}.pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await resume.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        orch = get_orchestrator()
        import json
        filter_dict = json.loads(filters) if filters else None
        matches = orch.match_resume(tmp_path, top_k=top_k, filters=filter_dict)

        # Parse resume for response
        profile = orch._resume_parser.parse(tmp_path)

        return MatchResponse(
            success=True,
            resume={
                "name": profile.name,
                "email": profile.email,
                "skills": list(profile.skills),
                "tools_technologies": list(profile.tools_technologies),
                "experience_years": profile.experience_years,
                "seniority_level": profile.seniority_level.value,
                "target_roles": list(profile.target_roles),
                "summary": profile.summary,
            },
            matches=[
                {
                    "job": {
                        **m.job.to_payload(),
                        "linkedin_url": m.job.linkedin_url,
                    },
                    "similarity_score": m.similarity_score,
                    "match_reasons": list(m.match_reasons),
                }
                for m in matches
            ],
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/v1/advise", response_model=AdviceResponse)
async def get_advice(
    resume: UploadFile = File(...),
    job_id: str = Form(...),
) -> AdviceResponse:
    """Upload a PDF resume and get improvement advice for a specific job."""
    if not resume.filename or not resume.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF resumes are supported")

    # Save uploaded file
    suffix = f"_{uuid.uuid4().hex[:8]}.pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await resume.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        orch = get_orchestrator()
        resume_profile = orch._resume_parser.parse(tmp_path)

        # Fetch job from vector store
        resume_vector = orch._embedder.embed([resume_profile.embedding_text])[0]
        results = orch._vector_store.search_similar(resume_vector, top_k=50)

        target_payload = next(
            (r for r in results if r.get("job_id") == job_id), None
        )
        if not target_payload:
            raise HTTPException(404, f"Job {job_id} not found")

        # Reconstruct JobPosting
        from core.models import EmploymentType, SeniorityLevel, WorkType, safe_enum

        job = JobPosting(
            job_id=target_payload["job_id"],
            company=target_payload.get("company"),
            title=target_payload.get("title"),
            location=target_payload.get("location"),
            work_type=safe_enum(WorkType, target_payload.get("work_type")),
            employment_type=safe_enum(EmploymentType, target_payload.get("employment_type")),
            easy_apply=target_payload.get("easy_apply", False),
            posted_raw_text=target_payload.get("posted_raw_text"),
            posted_at=datetime.fromisoformat(target_payload["posted_at"]) if target_payload.get("posted_at") else None,
            applicants_count=target_payload.get("applicants_count"),
            applicants_approx=target_payload.get("applicants_approx", False),
            skills=tuple(target_payload.get("skills", [])),
            tools_technologies=tuple(target_payload.get("tools_technologies", [])),
            required_experience=target_payload.get("required_experience"),
            seniority_level=safe_enum(SeniorityLevel, target_payload.get("seniority_level")),
            education_requirements=target_payload.get("education_requirements"),
            key_responsibilities=tuple(target_payload.get("key_responsibilities", [])),
            salary_range=target_payload.get("salary_range"),
            benefits=tuple(target_payload.get("benefits", [])) if target_payload.get("benefits") else None,
            remote_type=safe_enum(WorkType, target_payload.get("remote_type")),
            description=target_payload.get("description", ""),

        )

        advice = orch._resume_advisor.generate_advice(resume_profile, job)

        return AdviceResponse(
            success=True,
            advice={
                "job_id": advice.job_id,
                "job_title": advice.job_title,
                "company": advice.company,
                "overall_score": advice.overall_score,
                "summary_suggestions": list(advice.summary_suggestions),
                "skills_to_add": list(advice.skills_to_add),
                "skills_to_emphasize": list(advice.skills_to_emphasize),
                "project_suggestions": list(advice.project_suggestions),
                "experience_gaps": list(advice.experience_gaps),
                "certification_suggestions": list(advice.certification_suggestions),
                "tailored_summary": advice.tailored_summary,
            },
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
