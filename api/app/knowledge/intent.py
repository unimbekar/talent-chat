"""Decide whether a visitor question should search jobs, the knowledge base, or both."""

import re

# Company documents: benefits, policies, and any other uploaded material.
_KNOWLEDGE = re.compile(
    r"(?i)\b("
    r"benefits?|perks?|handbook|polic(?:y|ies)|pto|vacation|401\s*\(?k\)?|retirement|"
    r"insurance|health plan|health benefits?|holidays?|parental|tuition|sick leave|bonus(?:es)?|hsa|fsa|"
    r"dress code|remote work|paternity|maternity|time off|paid leave|medical|dental|vision|"
    r"premiums?|coverage|referrals?|disability|life insurance|reimburs\w*|allowance|stipend|"
    r"timesheets?|onboarding|expenses?|travel|badge|payroll|"
    r"procedures?|processes?|guidelines?|training|orientation|paperwork|"
    r"documents?|workflow|standard operating"
    r")\b"
)
# Words that are also job-search terms. They count as a document question only when no job is named.
_KNOWLEDGE_SOFT = re.compile(
    r"(?i)\b(health|healthcare|wellness|gym|laptop|compensation|"
    r"spouse|dependents?|family|stipends?|leave)\b"
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
    if _KNOWLEDGE_SOFT.search(text) and not _JOB.search(text):
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


def names_job(message: str) -> bool:
    return bool(_JOB.search(message or ""))


_FILLER = re.compile(
    r"(?i)\b(does|do|is|are|the|a|an|this|that|it|include|includes|including|offer|offers|come with|have|has|"
    r"what|which|how|about|any|with|for|of|and|or|me|my|tell|show|give|please|there|"
    r"they|them|their|you|your|we|our|i|can|get|good|great|best|nice|decent|generous|solid|"
    r"company|janus|soft)\b"
)


def job_part(message: str) -> str:
    """The part of a mixed question that names a job, with the benefit words removed."""
    text = _KNOWLEDGE.sub(" ", message or "")
    text = _KNOWLEDGE_SOFT.sub(" ", text)
    text = _FILLER.sub(" ", text)
    text = re.sub(r"[?!.,]", " ", text)
    return " ".join(text.split())
