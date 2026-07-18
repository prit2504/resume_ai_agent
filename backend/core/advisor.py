import json
from typing import Any, Final
from openai import OpenAI

from .models import JobPosting, ResumeAdvice, ResumeProfile
from .extractor import LLMJobExtractor

class LLMResumeAdvisor:
    """Strategy: Generate resume improvement advice using LLM."""

    # ADVICE_PROMPT: Final[str] = (
    #     "You are an expert career coach and resume optimizer.\n"
    #     "Given a candidate's resume profile and a job posting, analyze the match\n"
    #     "and provide structured, actionable advice to improve the resume for THIS specific job.\n\n"
    #     "Respond with STRICT JSON ONLY — no markdown fences, no commentary.\n\n"
    #     "JSON schema:\n"
    #     "{\n"
    #     '  "overall_score": number (0.0-1.0),\n'
    #     '  "summary_suggestions": [string],\n'
    #     '  "skills_to_add": [string],\n'
    #     '  "skills_to_emphasize": [string],\n'
    #     '  "project_suggestions": [string],\n'
    #     '  "experience_gaps": [string],\n'
    #     '  "certification_suggestions": [string],\n'
    #     '  "tailored_summary": string or null\n'
    #     "}\n\n"
    #     "overall_score: How well the resume matches the job (0.0 = no match, 1.0 = perfect).\n"
    #     "summary_suggestions: Specific changes to the professional summary.\n"
    #     "skills_to_add: Technical/soft skills missing from the resume but required by the job.\n"
    #     "skills_to_emphasize: Skills the candidate has that are highly relevant and should be highlighted.\n"
    #     "project_suggestions: Project ideas or ways to reframe existing projects to match job requirements.\n"
    #     "experience_gaps: Missing experience areas that the job requires.\n"
    #     "certification_suggestions: Certifications that would strengthen the application.\n"
    #     "tailored_summary: A rewritten professional summary optimized for this job."
    # )

    ADVICE_PROMPT: Final[str] = """
    You are an expert ATS resume reviewer, technical recruiter, and career coach.

    Your task is to compare a candidate's resume profile against ONE specific job posting and generate precise, actionable resume improvement advice.

    Your objective is NOT to rewrite the entire resume.
    Your objective is to identify the highest-impact improvements that would increase the candidate's chances of passing ATS screening and recruiter review.

    ========================
    ANALYSIS PROCESS
    ========================

    Compare the resume against the job posting in these areas:

    1. Professional summary
    2. Technical skills
    3. Tools & technologies
    4. Experience level
    5. Projects
    6. Education
    7. Certifications
    8. Keywords likely important for ATS

    For every recommendation, compare BOTH inputs before making suggestions.

    ========================
    RULES
    ========================

    - Only use information provided in the resume and job posting.
    - Never invent candidate experience.
    - Never claim the candidate has skills they do not possess.
    - Never fabricate certifications.
    - Never exaggerate qualifications.
    - If a recommendation requires gaining new knowledge or experience, clearly suggest it as a future improvement.
    - Prefer high-impact suggestions over generic resume advice.
    - Keep suggestions concise and specific.
    - Avoid duplicate recommendations.
    - Ignore company marketing language and focus on actual technical requirements.

    ========================
    MATCH SCORE
    ========================

    Return overall_score between 0.0 and 1.0.

    Use this guideline:

    0.90-1.00
    Excellent match with only minor improvements.

    0.75-0.89
    Strong match with several improvements.

    0.50-0.74
    Partial match. Important gaps exist.

    0.25-0.49
    Weak match. Major missing skills or experience.

    0.00-0.24
    Very poor match.

    ========================
    OUTPUT REQUIREMENTS
    ========================

    Return STRICT JSON ONLY.

    Do not include markdown.
    Do not explain your reasoning.
    Do not output additional text.

    JSON Schema:

    {
    "overall_score": number,
    "summary_suggestions": [string],
    "skills_to_add": [string],
    "skills_to_emphasize": [string],
    "project_suggestions": [string],
    "experience_gaps": [string],
    "certification_suggestions": [string],
    "tailored_summary": string|null
    }

    Field requirements:

    overall_score
    - Decimal between 0.0 and 1.0.

    summary_suggestions
    - 3-5 concrete improvements to the professional summary.

    skills_to_add
    - Skills required by the job but missing from the resume.

    skills_to_emphasize
    - Existing candidate skills that should receive greater emphasis.

    project_suggestions
    - Suggest projects that demonstrate missing required skills, OR explain how existing projects could be reframed to better match the role.
    - Do not invent completed projects.

    experience_gaps
    - Missing experience areas compared with job requirements.

    certification_suggestions
    - Relevant certifications only if they would meaningfully strengthen the application.

    tailored_summary
    - Rewrite the candidate's professional summary using ONLY verified resume information while naturally incorporating important job keywords.
    - Do not fabricate experience or achievements.
    """

    def __init__(self, llm_client: OpenAI, llm_model: str) -> None:
        self._llm_client = llm_client
        self._llm_model = llm_model

    def generate_advice(
        self,
        resume: ResumeProfile,
        job: JobPosting,
    ) -> ResumeAdvice:
        """Generate tailored resume advice for a specific job."""
        user_content = (
            f"RESUME PROFILE:\n"
            f"Name: {resume.name}\n"
            f"Summary: {resume.summary}\n"
            f"Skills: {', '.join(resume.skills)}\n"
            f"Tools: {', '.join(resume.tools_technologies)}\n"
            f"Experience: {resume.experience_years} years\n"
            f"Seniority: {resume.seniority_level.value if resume.seniority_level else ''}\n"
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
            f"Seniority: {job.seniority_level.value if job.seniority_level else ''}\n"
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
