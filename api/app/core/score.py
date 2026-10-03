"""Score math. Hard filters and scores are code, not a prompt."""

from functools import lru_cache
import re

from app.core.clearance import clearance_flag
from app.core.skills import aliases_for


MANDATORY_BAR = 0.9


def skill_score(
    candidate_skills: set[str],
    must_have: set[str],
    nice_to_have: set[str],
) -> tuple[float | None, list[str]]:
    job_skills = set(must_have) | set(nice_to_have)
    overlap = sorted(candidate_skills & job_skills)
    if not job_skills:
        return None, overlap
    must_hit = len(candidate_skills & set(must_have)) / max(len(must_have), 1)
    score = 0.7 * must_hit + 0.3 * (len(overlap) / max(len(job_skills), 1))
    return score, overlap


def semantic_score(raw_cosine: float) -> float:
    return (raw_cosine + 1) / 2


def final_score(skill: float | None, semantic: float) -> tuple[float, str]:
    if skill is None:
        return semantic, "low"
    return 0.55 * skill + 0.45 * semantic, "standard"


def _mentions(text: str, skill: str) -> bool:
    if not text or not skill:
        return False
    return re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", text, re.I) is not None


def item_matches(item: str, candidate_skills: set[str]) -> bool:
    """A posting line matches when the résumé lists that skill or one of its aliases."""
    if not item:
        return False
    for skill in candidate_skills:
        names = {skill, *aliases_for(skill)}
        if any(_mentions(item, name) for name in names):
            return True
    return False


_LINE_FILLER = frozenset(
    {
        "ability",
        "able",
        "active",
        "also",
        "and",
        "are",
        "across",
        "based",
        "broad",
        "broader",
        "complex",
        "deep",
        "demonstrated",
        "enterprise",
        "environment",
        "environments",
        "etc",
        "excellent",
        "experience",
        "familiarity",
        "for",
        "from",
        "hands",
        "has",
        "have",
        "high",
        "including",
        "into",
        "knowledge",
        "knowledgeable",
        "must",
        "of",
        "or",
        "our",
        "per",
        "proficiency",
        "proven",
        "skill",
        "skills",
        "strong",
        "such",
        "support",
        "supporting",
        "that",
        "the",
        "their",
        "them",
        "these",
        "this",
        "those",
        "use",
        "used",
        "using",
        "via",
        "well",
        "with",
        "within",
        "working",
        "year",
        "years",
        "algorithm",
        "algorithms",
        "analysi",
        "analysis",
        "analytical",
        "build",
        "building",
        "capabiliti",
        "capabilities",
        "capability",
        "complex",
        "conduct",
        "conducting",
        "coordination",
        "creation",
        "current",
        "customer",
        "data",
        "detection",
        "documentation",
        "engineer",
        "engineering",
        "evaluat",
        "evaluate",
        "evaluating",
        "evaluation",
        "hands-on",
        "in-depth",
        "infrastructure",
        "integration",
        "leverage",
        "leveraging",
        "new",
        "next-generation",
        "practical",
        "provid",
        "provide",
        "providing",
        "record",
        "scal",
        "scale",
        "scaling",
        "servic",
        "service",
        "services",
        "system",
        "systems",
        "techniqu",
        "technique",
        "techniques",
        "track",
        "verification",
        "workflow",
        "workflows",
    }
)


@lru_cache(maxsize=4096)
def _stems(text: str) -> frozenset[str]:
    expanded = re.sub(r"(?i)\bb\.s\.?\b", "bachelor degree", text or "")
    expanded = re.sub(r"(?i)\bm\.s\.?\b", "master degree", expanded)
    expanded = re.sub(r"(?i)\bph\.d\.?\b", "doctorate degree", expanded)
    words = re.findall(r"[a-z][a-z0-9+#-]{2,}", expanded.lower())
    stems: set[str] = set()
    for word in words:
        if word in _LINE_FILLER:
            continue
        stem = word
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                stem = word[: -len(suffix)]
                break
        if stem in _LINE_FILLER or len(stem) < 3:
            continue
        stems.add(stem)
    return frozenset(stems)


_DEGREE_GENERIC = frozenset(
    {
        "bachelor",
        "college",
        "degree",
        "doctorate",
        "education",
        "equivalent",
        "field",
        "master",
        "technical",
        "university",
    }
)


def _prose_matches(line: str, resume_text: str) -> bool:
    """A duty line with no named tool matches when the résumé uses that line's subject words.

    Shared verbs such as analysis, detection, and systems do not cover a line.
    A deepfake line needs deepfake. A multimedia-forensics line needs those subjects.
    """
    needed = _stems(line)
    if not needed or not resume_text:
        return False
    overlap = needed & _stems(resume_text)
    specific = needed - _DEGREE_GENERIC
    target = specific or needed
    hit = overlap & target
    if not hit:
        return False
    if len(target) <= 2:
        return hit == target
    return len(hit) >= 2 and len(hit) / len(target) >= 0.6


def block_coverage(coverage: dict) -> dict:
    """Drop a line score when the résumé cannot be this job."""
    return {
        **coverage,
        "pct": 0.0,
        "hit": 0,
        "matched": [],
        "missing": list(coverage.get("matched") or []) + list(coverage.get("missing") or []),
    }


def _required_tools(line: str, tools: list[str]) -> list[str]:
    """Tools named after excluding, except, or other than are not requirements."""
    from app.core.skills import tools_and_languages

    match = re.search(r"(?i)\b(?:excluding|except|other than|not including)\b(.*)$", line or "")
    if not match or not tools:
        return tools
    banned = {tool.lower() for tool in tools_and_languages(match.group(1))}
    return [tool for tool in tools if tool.lower() not in banned]


def _any_tool_satisfies(line: str, tools: list[str]) -> bool:
    """Example lists and explicit alternatives match when any one tool is present."""
    if re.search(r"(?i)\bsuch as\b|\betc\b|\bor\b", line or ""):
        return True
    names = [re.escape(tool) for tool in tools]
    names.append("Elastic")
    for left in names:
        for right in names:
            if left == right:
                continue
            if re.search(rf"(?i){left}\s*/\s*{right}", line or ""):
                return True
    return False


def _search_cluster(line: str, resume_text: str, candidate_skills: set[str]) -> bool:
    """A search-cluster line matches a résumé that describes an Elasticsearch or Solr cluster."""
    if not re.search(r"(?i)\bclusters?\b", line or "") or not re.search(r"(?i)search|solr|elastic", line or ""):
        return False
    have = {skill.lower() for skill in candidate_skills}
    if "elasticsearch" not in have and "solr" not in have:
        return False
    return re.search(
        r"(?i)(elasticsearch|solr).{0,60}cluster|cluster.{0,60}(elasticsearch|solr)",
        resume_text or "",
    ) is not None


def gate_mandatory(
    coverage: dict,
    *,
    skills: set[str],
    job_title: str | None,
    filename: str,
    text: str,
    titles: list[str] | None,
) -> dict:
    """Zero the line score when a title tool is missing or the résumé is a different role."""
    from app.core.labor import role_conflict

    if not covers_title(skills, job_title) or role_conflict(filename, text, titles, job_title):
        return block_coverage(coverage)
    return coverage


def covers_title(candidate_skills: set[str], title: str | None) -> bool:
    """A tool named in the job title has to be on the résumé. Other titles pass."""
    from app.core.skills import tools_and_languages

    needed = tools_and_languages(title or "")
    if not needed:
        return True
    have = {skill.lower() for skill in candidate_skills}
    return all(tool.lower() in have for tool in needed)


def section_coverage(candidate_skills: set[str], items: list[str], resume_text: str = "") -> dict:
    """Share of posting lines the résumé covers. None when the posting has no lines.

    A tool line counts when the résumé has that line's own tools. A vendor word
    repeated on every line, such as Oracle in an Exadata posting, does not by
    itself satisfy Oracle Linux or Exadata. A line that only names examples
    ("such as Selenium, Cypress") counts when any one of those tools is present.
    A duty line with no tool counts when the résumé describes that same work.
    """
    from app.core.clearance import is_clearance_only
    from app.core.skills import tools_and_languages

    lines = [item.strip() for item in items if item and item.strip()]
    if not lines:
        return {"pct": None, "hit": 0, "total": 0, "matched": [], "missing": []}
    lines = [re.sub(r"(?i)\bsolr\s*/\s*elastic\b", "Solr or Elasticsearch", line) for line in lines]
    parsed = [(line, tools_and_languages(line)) for line in lines]
    tool_sets = [{tool.lower() for tool in tools} for _, tools in parsed if tools]
    shared = set.intersection(*tool_sets) if len(tool_sets) >= 2 else set()
    have = {skill.lower() for skill in candidate_skills}
    matched: list[str] = []
    for line, tools in parsed:
        if is_clearance_only(line):
            continue
        tools = _required_tools(line, tools)
        if tools:
            distinctive = [tool for tool in tools if tool.lower() not in shared]
            needed = distinctive or tools
            alternatives = _any_tool_satisfies(line, needed)
            ok = any(tool.lower() in have for tool in needed) if alternatives else all(tool.lower() in have for tool in needed)
            if ok:
                matched.append(line)
            continue
        if _prose_matches(line, resume_text) or _search_cluster(line, resume_text, candidate_skills):
            matched.append(line)
    return {
        "pct": len(matched) / len(lines),
        "hit": len(matched),
        "total": len(lines),
        "matched": matched,
        "missing": [line for line in lines if line not in matched and not is_clearance_only(line)],
    }


def required_coverage(candidate_skills: set[str], job_items: list[str], required: list[str]) -> dict:
    """Each admin-required skill must appear on the résumé and on the job. That is the 100% gate."""
    needed = [skill.strip() for skill in required if skill and skill.strip()]
    if not needed:
        return {"pct": None, "matched": [], "missing": []}
    matched: list[str] = []
    missing: list[str] = []
    for skill in needed:
        on_resume = item_matches(skill, candidate_skills) or any(skill.lower() == name.lower() for name in candidate_skills)
        on_job = any(item_matches(item, {skill}) or skill.lower() == item.lower() for item in job_items)
        if on_resume and on_job:
            matched.append(skill)
        else:
            missing.append(skill)
    return {"pct": len(matched) / len(needed), "matched": matched, "missing": missing}


def rank_pair(
    candidate_skills: set[str],
    must_have: set[str],
    nice_to_have: set[str],
    raw_cosine: float,
    *,
    description_on_file: bool,
    candidate_clearance: str | None,
    candidate_poly: str | None,
    job_clearance: str | None,
    job_poly: str | None,
) -> dict:
    skill, overlap = skill_score(candidate_skills, must_have, nice_to_have)
    semantic = semantic_score(raw_cosine)
    final, confidence = final_score(skill, semantic)
    if not description_on_file:
        confidence = "low"
    return {
        "skill_score": skill,
        "raw_cosine": raw_cosine,
        "semantic": semantic,
        "final": final,
        "confidence": confidence,
        "overlap_skills": overlap,
        "clearance_flag": clearance_flag(
            candidate_clearance, candidate_poly, job_clearance, job_poly
        ),
    }
