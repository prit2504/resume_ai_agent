import asyncio
import json
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from .models import EmploymentType, JobPosting, MatchedJob, ResumeAdvice, SeniorityLevel, WorkType, safe_enum
from .scraper import SerpApiGoogleJobsScraper
from .extractor import LLMJobExtractor
from .embedder import UniversalEmbedder
from .vector_store import QdrantVectorStore
from .resume_parser import PDFResumeParser
from .advisor import LLMResumeAdvisor
from .contact import extract_job_contacts, select_outreach_email
from .outreach import LLMOutreachDrafter
from .email_sender import MCPEmailSender

class JobMatcherOrchestrator:
    """Facade: Coordinates scraping, extraction, embedding, storage, and matching.
    
    Directly depends on concrete implementations (non-SOLID).
    """

    def __init__(
        self,
        scraper: SerpApiGoogleJobsScraper,
        extractor: LLMJobExtractor,
        embedder: UniversalEmbedder,
        vector_store: QdrantVectorStore,
        resume_parser: PDFResumeParser,
        resume_advisor: LLMResumeAdvisor,
        outreach_drafter: LLMOutreachDrafter | None = None,
        email_sender: MCPEmailSender | None = None,
        llm_delay: float = 0.5,
    ) -> None:
        self._scraper = scraper
        self._extractor = extractor
        self._embedder = embedder
        self._vector_store = vector_store
        self._resume_parser = resume_parser
        self._resume_advisor = resume_advisor
        self._outreach_drafter = outreach_drafter
        self._email_sender = email_sender
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
        radius_km: int | None = None,
        country: str | None = None,
        language: str | None = None,
        uds: str | None = None,
        max_jobs: int = 50,
        search_queries: list[str] | None = None,
        dry_run: bool = False,
    ) -> list[JobPosting]:
        now = datetime.now(timezone.utc)
        print(f"🔍 Searching Google Jobs via SerpApi: keywords='{keywords}' location='{location}'")

        queries = [q for q in (search_queries or [keywords]) if q and q.strip()]
        job_ids = await self._scraper.search_many(
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
            detail = details.get(jid) or {}
            raw_job = detail.get("serpapi_job", {}) or {}
            apply_options = raw_job.get("apply_options") or []
            apply_url = next(
                (option.get("link") for option in apply_options if option.get("link")),
                None,
            )
            posting_text = (detail or {}).get("sections", {}).get("job_posting", "")
            contacts = extract_job_contacts(posting_text)

            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, jid))
            first_seen = self._vector_store.get_first_seen(point_id)
            
            # Simple builder logic
            def _to_tuple(val: Any) -> tuple[str, ...]:
                if isinstance(val, list):
                    return tuple(str(v) for v in val if v)
                return ()

            job = JobPosting(
                job_id=jid,
                company=raw_job.get("company_name") or fields.get("company"),
                title=raw_job.get("title") or fields.get("title"),
                location=raw_job.get("location") or fields.get("location"),
                work_type=safe_enum(WorkType, fields.get("work_type")),
                employment_type=safe_enum(EmploymentType, fields.get("employment_type")),
                easy_apply=bool(fields.get("easy_apply", False)),
                posted_raw_text=(raw_job.get("detected_extensions") or {}).get("posted_at") or fields.get("posted_raw_text"),
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
                description=raw_job.get("description") or fields.get("description", ""),
                search_keywords=keywords,
                search_location=location,
                first_seen_at=first_seen or now,
                last_seen_at=now,
                scraped_at=now,
                source=raw_job.get("via") or "Google Jobs",
                source_url=raw_job.get("share_link"),
                apply_url=apply_url,
                contact_emails=contacts["emails"],
                contact_phones=contacts["phones"],
                discovery_score=self._scraper.get_discovery_score(jid),
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
        radius_km: int | None = None,
        country: str | None = None,
        language: str | None = None,
        uds: str | None = None,
        max_jobs: int = 50,
        search_queries: list[str] | None = None,
        concurrency: int = 1,
    ) -> AsyncGenerator[str, None]:
        """Concurrent pipeline yielding JSON progress updates."""
        now = datetime.now(timezone.utc)
        
        yield json.dumps({"step": "init", "message": f"Searching Google Jobs via SerpApi for '{keywords}' in '{location or 'Anywhere'}'..."})

        queries = [q for q in (search_queries or [keywords]) if q and q.strip()]
        job_ids = await self._scraper.search_many(
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
                    raw_job = (detail or {}).get("serpapi_job", {}) or {}
                    apply_options = raw_job.get("apply_options") or []
                    apply_url = next(
                        (option.get("link") for option in apply_options if option.get("link")),
                        None,
                    )
                    posting_text = (detail or {}).get("sections", {}).get("job_posting", "")
                    contacts = extract_job_contacts(posting_text)
                    
                    if not posting_text:
                        yield json.dumps({"step": "warn", "job_id": jid, "message": f"No posting text found for {jid}."})
                        return

                    yield json.dumps({"step": "extracting", "job_id": jid, "message": f"Extracting structured fields for job {idx}/{total_jobs}..."})
                    fields = await asyncio.to_thread(self._extractor.extract, posting_text)
                    
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, jid))
                    first_seen = self._vector_store.get_first_seen(point_id)
                    
                    job = JobPosting(
                        job_id=jid,
                        company=raw_job.get("company_name") or fields.get("company"),
                        title=raw_job.get("title") or fields.get("title"),
                        location=raw_job.get("location") or fields.get("location"),
                        work_type=safe_enum(WorkType, fields.get("work_type")),
                        employment_type=safe_enum(EmploymentType, fields.get("employment_type")),
                        easy_apply=bool(fields.get("easy_apply", False)),
                        posted_raw_text=(raw_job.get("detected_extensions") or {}).get("posted_at") or fields.get("posted_raw_text"),
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
                        description=raw_job.get("description") or fields.get("description", ""),
                        search_keywords=keywords,
                        search_location=location,
                        first_seen_at=first_seen or now,
                        last_seen_at=now,
                        scraped_at=now,
                        source=raw_job.get("via") or "Google Jobs",
                        source_url=raw_job.get("share_link"),
                        apply_url=apply_url,
                contact_emails=contacts["emails"],
                contact_phones=contacts["phones"],
                discovery_score=self._scraper.get_discovery_score(jid),
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

    @staticmethod
    def build_resume_search_queries(resume: Any, max_roles: int = 3) -> list[str]:
        queries: list[str] = []
        for role in resume.target_roles:
            role = str(role).strip()
            if role and role.lower() not in {q.lower() for q in queries}:
                queries.append(role)
            if len(queries) >= max_roles:
                break
        if not queries:
            skills = [str(skill).strip() for skill in resume.skills[:3] if str(skill).strip()]
            queries.append(" ".join(skills + ["jobs"]) if skills else "software engineer")
        return queries[:max_roles]

    async def scrape_resume_and_store_stream(
        self,
        resume_path: Path,
        location: str | None = None,
        max_roles: int = 3,
        max_pages: int = 1,
        date_posted: str | None = None,
        job_type: str | None = None,
        work_type: str | None = None,
        radius_km: int | None = None,
        country: str | None = None,
        language: str | None = None,
        max_jobs: int = 50,
        concurrency: int = 1,
    ) -> AsyncGenerator[str, None]:
        resume = await asyncio.to_thread(self._resume_parser.parse, resume_path)
        queries = self.build_resume_search_queries(resume, max_roles=max_roles)
        yield json.dumps({"step": "resume_search", "message": f"Searching {len(queries)} resume-derived roles.", "queries": queries})
        async for event in self.scrape_and_store_stream(
            keywords=queries[0],
            location=location,
            max_pages=max_pages,
            date_posted=date_posted,
            job_type=job_type,
            work_type=work_type,
            radius_km=radius_km,
            country=country,
            language=language,
            max_jobs=max_jobs,
            search_queries=queries,
            concurrency=concurrency,
        ):
            yield event

    @staticmethod
    def _job_from_payload(payload: dict[str, Any]) -> JobPosting:
        return JobPosting(
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
            source=payload.get("source"),
            source_url=payload.get("source_url"),
            apply_url=payload.get("apply_url"),
            contact_emails=tuple(payload.get("contact_emails", [])),
            contact_phones=tuple(payload.get("contact_phones", [])),
            discovery_score=payload.get("discovery_score"),
        )

    def draft_outreach(self, resume_path: Path, job_id: str) -> dict[str, Any]:
        if self._outreach_drafter is None:
            raise RuntimeError("Outreach drafter is not configured")
        payload = self._vector_store.get_job(job_id)
        if not payload:
            raise ValueError(f"Job {job_id} was not found in the vector store")
        job = self._job_from_payload(payload)
        recipient = select_outreach_email(job.contact_emails)
        if not recipient:
            return {
                "available": False,
                "job_id": job_id,
                "contact_emails": list(job.contact_emails),
                "contact_phones": list(job.contact_phones),
                "message": "No email address was found in the stored job posting.",
            }
        resume = self._resume_parser.parse(resume_path)
        generated = self._outreach_drafter.generate(resume, job, recipient)
        return {
            "available": True,
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "recipient": recipient,
            "contact_emails": list(job.contact_emails),
            "contact_phones": list(job.contact_phones),
            "subject": generated["subject"],
            "body": generated["body"],
        }

    async def send_outreach(
        self,
        resume_path: Path,
        attachment_name: str,
        job_id: str,
        recipient: str,
        subject: str,
        body: str,
        approved: bool,
    ) -> Any:
        if not approved:
            raise PermissionError("Human approval is required before sending")
        if self._email_sender is None or not self._email_sender.configured:
            raise RuntimeError("Email MCP server is not configured")
        payload = self._vector_store.get_job(job_id)
        if not payload:
            raise ValueError(f"Job {job_id} was not found in the vector store")
        allowed = {str(email).lower() for email in payload.get("contact_emails", [])}
        if recipient.lower() not in allowed:
            raise PermissionError("Recipient must be an email extracted from this job posting")
        return await self._email_sender.send(
            recipient=recipient,
            subject=subject.strip(),
            body=body.strip(),
            attachment_name=attachment_name,
            attachment_bytes=resume_path.read_bytes(),
        )

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
                source=payload.get("source"),
                source_url=payload.get("source_url"),
                apply_url=payload.get("apply_url"),
                contact_emails=tuple(payload.get("contact_emails", [])),
                contact_phones=tuple(payload.get("contact_phones", [])),
                discovery_score=payload.get("discovery_score"),
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
        return None
