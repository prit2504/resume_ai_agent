import json
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from openai import OpenAI

from .models import ResumeProfile, SeniorityLevel
from .extractor import LLMJobExtractor

class PDFResumeParser:
    """Strategy: Parse PDF resumes using pdfplumber + LLM enhancement."""

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
            current_date = datetime.now().strftime("%B %Y")
            system_prompt = self.RESUME_EXTRACTION_PROMPT + f"\n\nIMPORTANT CONTEXT: The current date is {current_date}. Use this date to accurately calculate the total `experience_years` if the resume lists 'Present' or 'Current' as the end date for a job."

            resp = self._llm_client.chat.completions.create(
                model=self._llm_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
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
        """Parse a PDF resume into a structured profile."""
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
