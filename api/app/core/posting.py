"""The careers posting candidates read, and the LinkedIn search a recruiter opens in their own browser."""

import re
from urllib.parse import quote, urlparse

from app.models import Job


def posting_paragraphs(job: Job) -> list[str]:
    """The careers-page posting split into paragraphs, without the page chrome the crawl picked up."""
    paragraphs: list[str] = []
    seen: set[str] = set()
    title = (job.title or "").strip().lower()
    for raw in re.split(r"\n\s*\n|\n", job.careers_description_text or ""):
        text = re.sub(r"[ \t]+", " ", raw).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        if not paragraphs and (key in {"career", "careers"} or (title and key.startswith(title) and len(text) < 120)):
            continue
        paragraphs.append(text)
    return paragraphs


# Always required. A profile must name TS/SCI and a full-scope polygraph. Secret and CI poly are left out.
LINKEDIN_CLEARANCE = (
    '("TS/SCI" OR "TS SCI" OR "Top Secret/SCI" OR "Top Secret SCI") '
    'AND ("Full Scope Polygraph" OR "Full Scope Poly" OR FSP)'
)
_SKIP_TERM = re.compile(r"^(clearance|polygraph|poly|ts/?sci|top secret|full scope(?: poly(?:graph)?)?|fsp|citizenship)$", re.I)


def _quote_term(term: str) -> str:
    cleaned = re.sub(r"\s+", " ", term).replace('"', "").strip()
    if re.fullmatch(r"[A-Za-z0-9+#.-]+", cleaned):
        return cleaned
    return f'"{cleaned}"'


def _city(location: str) -> str:
    return re.split(r",|\s+[-–—]\s+", (location or "").strip(), maxsplit=1)[0].strip()


def linkedin_role_terms(job: Job) -> list[str]:
    """Short role words LinkedIn can match. Long posting sentences stay off the query."""
    terms: list[str] = []
    title = re.sub(r"\s+[-–—]\s+.*$", "", job.title or "").strip()
    if title:
        terms.append(title)
    for skill in list(job.must_have_skills or []):
        label = skill.split(":", 1)[0].strip() if ":" in skill else skill.strip()
        label = re.sub(r"\s+", " ", label)
        if not label or len(label) > 48 or "." in label or _SKIP_TERM.match(label):
            continue
        terms.append(label)
        if len(terms) >= 4:
            break
    return terms


def form_linkedin_query(terms: list[str], location: str = "", match: str = "all") -> str:
    """Boolean keyword search. The clearance clause is always first."""
    quoted: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        term = re.sub(r"\s+", " ", (raw or "")).strip().strip('"')
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        quoted.append(_quote_term(term))
        if len(quoted) == 6:
            break
    parts = [LINKEDIN_CLEARANCE]
    if match == "any" and len(quoted) > 1:
        parts.append("(" + " OR ".join(quoted) + ")")
    else:
        parts.extend(quoted)
    city = _city(location)
    if city:
        parts.append(_quote_term(city))
    return " AND ".join(parts)


def linkedin_query(job: Job) -> str:
    return form_linkedin_query(linkedin_role_terms(job), job.location or "", "all")


def linkedin_links(job: Job) -> dict[str, str | list[str]]:
    terms = linkedin_role_terms(job)
    location = _city(job.location or "")
    query = form_linkedin_query(terms, location, "all")
    encoded = quote(query, safe="")
    return {
        "clearance": LINKEDIN_CLEARANCE,
        "terms": terms,
        "location": location,
        "match": "all",
        "query": query,
        "people_url": f"https://www.linkedin.com/search/results/people/?keywords={encoded}&origin=FACETED_SEARCH",
        "recruiter_url": f"https://www.linkedin.com/talent/search?searchKeyword={encoded}",
    }


def linkedin_profile_url(value: str) -> str:
    """A profile link the recruiter pasted. Company pages and other sites are refused."""
    url = (value or "").strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in {"linkedin.com", "www.linkedin.com", "lnkd.in"}:
        raise ValueError("Paste a LinkedIn profile link.")
    if host == "lnkd.in" or "/in/" in parsed.path or "/pub/" in parsed.path:
        return url
    raise ValueError("Paste a LinkedIn profile link, the one that contains /in/.")
