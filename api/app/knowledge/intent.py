"""Decide whether a visitor question should search jobs, the knowledge base, or both."""

import re

# Company documents: benefits, policies, and any other uploaded material.
_KNOWLEDGE = re.compile(
    r"(?i)\b("
    r"benefits?|handbook|polic(?:y|ies)|pto|vacation|401\s*\(?k\)?|retirement|"
    r"insurance|health plan|holidays?|parental|tuition|sick leave|bonus|hsa|fsa|"
    r"dress code|remote work|paternity|maternity|time off|paid leave|dental|vision|"
    r"timesheets?|onboarding|expenses?|reimburs\w*|travel|badge|payroll|"
    r"procedures?|processes?|guidelines?|training|orientation|paperwork|"
    r"documents?|workflow|standard operating"
    r")\b"
)
_QUESTION = re.compile(
    r"(?i)\b(how do|how can|how does|what is|what are|when is|when do|where is|where do|"
    r"who do|can i|can we|do we|does the company|is there)\b"
)
_JOB = re.compile(
    r"(?i)\b(jobs?|roles?|openings?|positions?|hiring|requisitions?|apply|postings?)\b"
    r"|\b[A-LN-Z]\d{3,4}\b"
)


def wants_knowledge(message: str) -> bool:
    """True when the question is about uploaded documents rather than open jobs."""
    text = message or ""
    if _KNOWLEDGE.search(text):
        return True
    return bool(_QUESTION.search(text) and not _JOB.search(text))


def wants_policy(message: str) -> bool:
    """Older name. Policy questions are one kind of knowledge question."""
    return wants_knowledge(message)


def wants_jobs(message: str) -> bool:
    """Job search stays the default for skills and cities. A document question does not search postings."""
    if _JOB.search(message or ""):
        return True
    return not wants_knowledge(message)
