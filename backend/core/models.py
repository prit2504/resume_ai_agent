from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

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
    hr_email: str | None = None
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
            "work_type": self.work_type.value if self.work_type else None,
            "employment_type": self.employment_type.value if self.employment_type else None,
            "easy_apply": self.easy_apply,
            "posted_raw_text": self.posted_raw_text,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "applicants_count": self.applicants_count,
            "applicants_approx": self.applicants_approx,
            "skills": list(self.skills),
            "tools_technologies": list(self.tools_technologies),
            "required_experience": self.required_experience,
            "seniority_level": self.seniority_level.value if self.seniority_level else None,
            "education_requirements": self.education_requirements,
            "key_responsibilities": list(self.key_responsibilities),
            "salary_range": self.salary_range,
            "benefits": list(self.benefits) if self.benefits else None,
            "remote_type": self.remote_type.value if self.remote_type else None,
            "description": self.description,
            "hr_email": self.hr_email,
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
            f"work_type: {self.work_type.value if self.work_type else ''}",
            f"employment_type: {self.employment_type.value if self.employment_type else ''}",
        ]
        if self.skills:
            parts.append(f"skills: {', '.join(self.skills)}")
        if self.required_experience:
            parts.append(f"required_experience: {self.required_experience}")
        if self.seniority_level != SeniorityLevel.UNKNOWN:
            parts.append(f"seniority_level: {self.seniority_level.value if self.seniority_level else ''}")
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
            f"seniority: {self.seniority_level.value if self.seniority_level else ''}",
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
