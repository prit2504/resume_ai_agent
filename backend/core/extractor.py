import json
import re
from typing import Any, Final
from openai import OpenAI

class LLMJobExtractor:
    """Strategy: Use local LLM for structured extraction."""

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
        """Extract structured fields from raw job posting text."""
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
