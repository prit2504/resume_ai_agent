from __future__ import annotations

import re
from typing import Iterable

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,14}\d(?!\d)"
)

_PRIORITY_HINTS = ("recruit", "talent", "hiring", "career", "jobs", "hr", "people")
_NEGATIVE_HINTS = ("noreply", "no-reply", "donotreply", "do-not-reply")


def extract_job_contacts(text: str) -> dict[str, tuple[str, ...]]:
    """Extract only contact details literally present in the source job text."""
    emails = {
        match.group(1).strip(".,;:()[]{}<>").lower()
        for match in _EMAIL_RE.finditer(text or "")
    }

    phones: set[str] = set()
    for match in _PHONE_RE.finditer(text or ""):
        raw = match.group(0).strip(".,;:()[]{}<> ")
        digits = re.sub(r"\D", "", raw)
        if 8 <= len(digits) <= 15:
            phones.add(raw)

    return {"emails": tuple(sorted(emails)), "phones": tuple(sorted(phones))}


def select_outreach_email(emails: Iterable[str]) -> str | None:
    """Prefer recruiter/HR-looking addresses without inventing any address."""
    values = [email.strip().lower() for email in emails if email and email.strip()]
    if not values:
        return None

    def score(email: str) -> tuple[int, int]:
        local = email.split("@", 1)[0]
        priority = sum(5 for hint in _PRIORITY_HINTS if hint in local)
        penalty = sum(20 for hint in _NEGATIVE_HINTS if hint in local)
        return priority - penalty, -len(email)

    return max(values, key=score)
