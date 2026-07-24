import asyncio
import json
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from .models import EmploymentType, JobPosting, MatchedJob, ResumeAdvice, ResumeProfile, SeniorityLevel, WorkType, safe_enum
from .scraper import LinkedInMCPScraper
from .extractor import LLMJobExtractor
from .embedder import UniversalEmbedder
from .vector_store import QdrantVectorStore
from .resume_parser import PDFResumeParser
from .advisor import LLMResumeAdvisor

class JobMatcherOrchestrator:
    """Facade: Coordinates scraping, extraction, embedding, storage, and matching.
    
    Directly depends on concrete implementations (non-SOLID).
    """

    def __init__(
        self,
        scraper: LinkedInMCPScraper,
        extractor: LLMJobExtractor,
        embedder: UniversalEmbedder,
        vector_store: QdrantVectorStore,
        resume_parser: PDFResumeParser,
        resume_advisor: LLMResumeAdvisor,
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

        print("\n📥 Fetching job details...")
        details = await self._scraper.fetch_all_details(
            job_ids,
            progress_callback=lambda i, total, jid: print(f"  [{i}/{total}] {jid}"),
        )

        print(f"\n🤖 Extracting structured fields...")
        fields_by_id: dict[str, dict[str, Any]] = {}
        for i, (jid, detail) in enumerate(details.items(), 1):
            posting_text = (detail or {}).get("sections", {}).get("job_posting", "")
            fields = self._extractor.extract(posting_text)
            print(f"  [{i}/{len(details)}] {jid}: {fields.get('title', 'N/A')!r} @ {fields.get('company', 'N/A')!r}")
            fields_by_id[jid] = fields
            await asyncio.sleep(self._llm_delay)

        jobs: list[JobPosting] = []
        for jid, fields in fields_by_id.items():
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, jid))
            first_seen = self._vector_store.get_first_seen(point_id)
            
            # Simple builder logic
            def _to_tuple(val: Any) -> tuple[str, ...]:
                if isinstance(val, list):
                    return tuple(str(v) for v in val if v)
                return ()

            job = JobPosting(
                job_id=jid,
                company=fields.get("company"),
                title=fields.get("title"),
                location=fields.get("location"),
                work_type=safe_enum(WorkType, fields.get("work_type")),
                employment_type=safe_enum(EmploymentType, fields.get("employment_type")),
                easy_apply=bool(fields.get("easy_apply", False)),
                posted_raw_text=fields.get("posted_raw_text"),
                posted_at=None, # Simplifying posted_at for modularity
                applicants_count=fields.get("applicants_count"),
                applicants_approx=bool(fields.get("applicants_approx", False)),
                skills=_to_tuple(fields.get("skills")),
                tools_technologies=_to_tuple(fields.get("tools_technologies")),
                required_experience=fields.get("required_experience"),
                seniority_level=safe_enum(SeniorityLevel, fields.get("seniority_level")),
                education_requirements=fields.get("education_requirements"),
                key_responsibilities=_to_tuple(fields.get("key_responsibilities")),
                salary_range=fields.get("salary_range"),
                benefits=_to_tuple(fields.get("benefits")) if fields.get("benefits") else None,
                remote_type=safe_enum(WorkType, fields.get("remote_type")),
                description=fields.get("description", ""),
                hr_email=fields.get("hr_email"),
                search_keywords=keywords,
                search_location=location,
                first_seen_at=first_seen or now,
                last_seen_at=now,
                scraped_at=now,
            )
            jobs.append(job)

        if dry_run:
            return jobs

        self._vector_store.ensure_collection(
            self._vector_store._collection,
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

    async def scrape_and_store_stream(
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
        concurrency: int = 1,
    ) -> AsyncGenerator[str, None]:
        """Concurrent pipeline yielding JSON progress updates."""
        now = datetime.now(timezone.utc)
        
        yield json.dumps({"step": "init", "message": f"Searching LinkedIn for '{keywords}' in '{location or 'Anywhere'}'..."})

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

        total_jobs = len(job_ids)
        if not total_jobs:
            yield json.dumps({"step": "done", "message": "No jobs found.", "count": 0})
            return

        yield json.dumps({"step": "search_done", "message": f"Found {total_jobs} jobs. Starting processing pipeline (concurrency: {concurrency}).", "count": total_jobs})

        self._vector_store.ensure_collection(
            self._vector_store._collection,
            self._embedder.dimension,
        )

        sem = asyncio.Semaphore(concurrency)
        jobs: list[JobPosting] = []
        completed_count = 0

        def _to_tuple(val: Any) -> tuple[str, ...]:
            if isinstance(val, list):
                return tuple(str(v) for v in val if v)
            return ()

        async def process_job(jid: str, idx: int) -> None:
            nonlocal completed_count
            async with sem:
                try:
                    yield json.dumps({"step": "fetching", "job_id": jid, "message": f"Fetching details for job {idx}/{total_jobs}..."})
                    detail = await self._scraper.fetch_details(jid)
                    posting_text = (detail or {}).get("sections", {}).get("job_posting", "")
                    
                    if not posting_text:
                        yield json.dumps({"step": "warn", "job_id": jid, "message": f"No posting text found for {jid}."})
                        return

                    yield json.dumps({"step": "extracting", "job_id": jid, "message": f"Extracting structured fields for job {idx}/{total_jobs}..."})
                    fields = await asyncio.to_thread(self._extractor.extract, posting_text)
                    
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, jid))
                    first_seen = self._vector_store.get_first_seen(point_id)
                    
                    job = JobPosting(
                        job_id=jid,
                        company=fields.get("company"),
                        title=fields.get("title"),
                        location=fields.get("location"),
                        work_type=safe_enum(WorkType, fields.get("work_type")),
                        employment_type=safe_enum(EmploymentType, fields.get("employment_type")),
                        easy_apply=bool(fields.get("easy_apply", False)),
                        posted_raw_text=fields.get("posted_raw_text"),
                        posted_at=None,
                        applicants_count=fields.get("applicants_count"),
                        applicants_approx=bool(fields.get("applicants_approx", False)),
                        skills=_to_tuple(fields.get("skills")),
                        tools_technologies=_to_tuple(fields.get("tools_technologies")),
                        required_experience=fields.get("required_experience"),
                        seniority_level=safe_enum(SeniorityLevel, fields.get("seniority_level")),
                        education_requirements=fields.get("education_requirements"),
                        key_responsibilities=_to_tuple(fields.get("key_responsibilities")),
                        salary_range=fields.get("salary_range"),
                        benefits=_to_tuple(fields.get("benefits")) if fields.get("benefits") else None,
                        remote_type=safe_enum(WorkType, fields.get("remote_type")),
                        description=fields.get("description", ""),
                        hr_email=fields.get("hr_email"),
                        search_keywords=keywords,
                        search_location=location,
                        first_seen_at=first_seen or now,
                        last_seen_at=now,
                        scraped_at=now,
                    )
                    
                    yield json.dumps({"step": "embedding", "job_id": jid, "message": f"Embedding and storing job {idx}/{total_jobs}..."})
                    vector = await asyncio.to_thread(self._embedder.embed, [job.embedding_text])
                    if vector:
                        self._vector_store.upsert_jobs([(point_id, vector[0], job.to_payload())])
                    
                    jobs.append(job)
                    completed_count += 1
                    yield json.dumps({"step": "job_done", "job_id": jid, "company": job.company, "title": job.title})
                except Exception as e:
                    yield json.dumps({"step": "error", "job_id": jid, "message": f"Error processing {jid}: {e}"})

        # To yield from concurrent tasks as they complete, we can wrap them in a queue or use asyncio.as_completed.
        # But since we need to yield from the generator, we can use a small wrapper.
        # However, `process_job` itself is an async generator (because it yields). 
        # We can't easily `asyncio.gather` multiple async generators directly and interleave their yields.
        # A better way is to use an asyncio.Queue to collect events from all workers.

        event_queue = asyncio.Queue()

        async def worker_wrapper(jid: str, idx: int):
            async for event in process_job(jid, idx):
                await event_queue.put(event)
            await event_queue.put(None) # Signal completion for this worker

        tasks = [asyncio.create_task(worker_wrapper(jid, i)) for i, jid in enumerate(job_ids, 1)]
        
        active_workers = len(tasks)
        while active_workers > 0:
            event = await event_queue.get()
            if event is None:
                active_workers -= 1
            else:
                yield event

        yield json.dumps({"step": "done", "message": f"Successfully processed {completed_count} jobs.", "count": completed_count})

    def match_resume(
        self,
        resume_path: Path,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[MatchedJob]:
        print(f"\n📄 Parsing resume: {resume_path}")
        resume = self._resume_parser.parse(resume_path)
        print(f"  👤 {resume.name} | Skills: {', '.join(resume.skills[:5])}...")

        print(f"\n🔎 Searching vector store for top {top_k} matches...")
        resume_vector = self._embedder.embed([resume.embedding_text])[0]
        results = self._vector_store.search_similar(resume_vector, top_k=top_k, filters=filters)

        matched: list[MatchedJob] = []
        for result in results:
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
                hr_email=payload.get("hr_email"),
            )
            score = result.get("score", 0.0)
            matched.append(MatchedJob(job=job, similarity_score=score))

        matched.sort(key=lambda m: m.similarity_score, reverse=True)
        return matched

    def write_email_for_job(
        self,
        job: JobPosting,
        resume_profile: ResumeProfile,
    ) -> tuple[str, str]:
        """
        Use the existing LLM client (already wired in via api.py) to write a
        personalised job application email.

        Richer than agent.py's write_email node because it incorporates the
        candidate's actual skills, experience years and summary from the resume.

        Returns:
            (subject, body) — both plain strings ready to hand to EmailMCPClient.
        """
        # Build top-N lists safely even when tuples are empty
        skills_str        = ", ".join(list(resume_profile.skills)[:8])      or "various technical skills"
        job_skills_str    = ", ".join(list(job.skills)[:6])                 or "relevant skills"
        responsibilities  = "; ".join(list(job.key_responsibilities)[:3])   or "(see job description)"

        prompt = f"""You are a professional job applicant writing a concise job application email.

Candidate Profile:
- Name: {resume_profile.name or 'Applicant'}
- Experience: {resume_profile.experience_years or 'N/A'} years
- Key Skills: {skills_str}
- Summary: {resume_profile.summary or 'Experienced professional seeking new opportunities'}

Job Details:
- Company: {job.company or 'the company'}
- Role: {job.title or 'the position'}
- Location: {job.location or 'N/A'}
- Required Skills: {job_skills_str}
- Key Responsibilities: {responsibilities}

Write a professional, concise job application email (max 150 words).
Return ONLY in this exact format with no extra text:
SUBJECT: <subject line>
BODY: <full email body>"""

        try:
            resp = self._extractor._client.chat.completions.create(
                model=self._extractor._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.4,
            )
            raw = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            print(f"  ! write_email_for_job LLM call failed: {exc}")
            raw = ""

        subject, body = "", ""
        for line in raw.split("\n"):
            if line.startswith("SUBJECT:"):
                subject = line.replace("SUBJECT:", "").strip()
            elif line.startswith("BODY:"):
                body = line.replace("BODY:", "").strip()
            elif body:
                body += "\n" + line

        # Graceful fallbacks so a failed LLM call never crashes the endpoint
        if not subject:
            subject = f"Application for {job.title or 'the position'} at {job.company or 'your company'}"
        if not body:
            body = raw or (
                f"Dear Hiring Team,\n\n"
                f"I am writing to express my interest in the {job.title or 'open'} role at "
                f"{job.company or 'your company'}. "
                f"Please find my resume attached for your consideration.\n\n"
                f"Best regards,\n{resume_profile.name or 'Applicant'}"
            )

        return subject, body

    def advise_for_job(
        self,
        resume_path: Path,
        job_id: str,
    ) -> ResumeAdvice | None:
        return None
