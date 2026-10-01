from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .extractor import LLMJobExtractor
from .models import JobPosting, ResumeProfile


class LLMOutreachDrafter:
    """Draft a truthful, job-specific outreach email for human approval."""

    SYSTEM_PROMPT = """
You write concise professional job-application outreach emails.

Use ONLY facts present in the candidate resume profile and the job posting.
Never invent experience, achievements, skills, recruiter names, referrals, or relationships.
The recipient email is already verified from the job text; do not infer any other contact.
Write 120-180 words. Mention the exact role and company, 2-3 strongest relevant facts
from the resume, a clear expression of interest, and that the resume is attached.
Do not sound overly promotional. Do not use placeholders.

Return STRICT JSON ONLY:
{
  "subject": "string",
  "body": "string"
}
"""

    def __init__(self, llm_client: OpenAI, llm_model: str) -> None:
        self._llm_client = llm_client
        self._llm_model = llm_model

    def generate(self, resume: ResumeProfile, job: JobPosting, recipient: str) -> dict[str, str]:
        content = (
            f"RECIPIENT EMAIL: {recipient}\n\n"
            f"JOB:\nTitle: {job.title}\nCompany: {job.company}\n"
            f"Location: {job.location}\nDescription: {job.description}\n"
            f"Skills: {', '.join(job.skills)}\n"
            f"Responsibilities: {', '.join(job.key_responsibilities)}\n\n"
            f"CANDIDATE:\nName: {resume.name}\nEmail: {resume.email}\n"
            f"Summary: {resume.summary}\nSkills: {', '.join(resume.skills)}\n"
            f"Tools: {', '.join(resume.tools_technologies)}\n"
            f"Experience: {resume.experience_years} years\n"
            f"Projects: {', '.join(resume.projects)}\n"
            f"Education: {', '.join(resume.education)}"
        )

        try:
            response = self._llm_client.chat.completions.create(
                model=self._llm_model,
                temperature=0.25,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            data: dict[str, Any] = json.loads(LLMJobExtractor._strip_json_fences(raw))
            subject = str(data.get("subject") or "").strip()
            body = str(data.get("body") or "").strip()
            if subject and body:
                return {"subject": subject, "body": body}
        except Exception as exc:
            print(f"  ! Outreach drafting failed: {exc}")

        name = resume.name or "Candidate"
        role = job.title or "the position"
        company = job.company or "your company"
        skills = ", ".join(resume.skills[:3])
        body = (
            f"Hello,\n\n"
            f"I am writing to express my interest in {role} at {company}. "
            f"My background includes {skills or 'relevant technical experience'}, "
            f"and I believe my experience aligns well with the role's requirements. "
            f"I would welcome the opportunity to discuss how I could contribute to your team.\n\n"
            f"Please find my resume attached for your review. Thank you for your time and consideration.\n\n"
            f"Kind regards,\n{name}"
        )
        return {"subject": f"Application for {role} - {name}", "body": body}
