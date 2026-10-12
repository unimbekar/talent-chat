"""Check a résumé against one open job before the visitor applies.

The file is read in memory and dropped. Nothing is stored, logged, or sent to a model. The
scoring is the same line coverage the recruiter's ranking uses, so the visitor sees the
requirements the desk will see as met or missing.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
import threading

from app.core.extract import ExtractError, extract_text
from app.core.redact import redact_ssn
from app.core.score import MANDATORY_BAR, covers_title, section_coverage
from app.core.skills import tools_and_languages
from app.core.structure import resume_facts
from app.models import Job

MAX_BYTES = 8 * 1024 * 1024
_LOCK = threading.Lock()
_HITS: dict[str, list[datetime]] = defaultdict(list)
_LIMIT = 20
_CLEARANCE = re.compile(r"(?i)\b(clearance|ts/sci|top secret|polygraph|full scope)\b")


class CheckError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def limited(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    window = now - timedelta(hours=1)
    with _LOCK:
        recent = [stamp for stamp in _HITS[ip] if stamp > window]
        if len(recent) >= _LIMIT:
            _HITS[ip] = recent
            return True
        recent.append(now)
        _HITS[ip] = recent
        return False


def reset_check_limit() -> None:
    with _LOCK:
        _HITS.clear()


def _posting_lines(job: Job, kind: str, names: list[str]) -> list[str]:
    quotes = list((job.skill_quotes or {}).get(kind) or [])
    lines = [line.strip() for line in quotes if isinstance(line, str) and line.strip()]
    return lines or [name for name in names if name]


def _split_label(line: str) -> tuple[str | None, str]:
    """ "Front-End Development: Hands-on experience…" becomes a short label and the detail."""
    match = re.match(r"^\s*([^:]{3,60}):\s+(.+)$", line)
    if match and not re.search(r"\d", match.group(1)):
        return match.group(1).strip(), match.group(2).strip()
    return None, line.strip()


def _items(lines: list[str], coverage: dict, have: set[str]) -> list[dict]:
    met = set(coverage.get("matched") or [])
    items = []
    for line in lines:
        if _CLEARANCE.search(line) and not tools_and_languages(line):
            continue
        label, detail = _split_label(line)
        tools = tools_and_languages(line)
        items.append(
            {
                "label": label,
                "text": detail,
                "met": line in met,
                "tools": [{"name": tool, "have": tool.lower() in have} for tool in tools][:8],
            }
        )
    return items


def _summary(items: list[dict]) -> dict:
    total = len(items)
    hit = sum(1 for item in items if item["met"])
    return {"pct": round(hit / total, 3) if total else None, "hit": hit, "total": total, "items": items}


def check_resume(job: Job, filename: str, data: bytes) -> dict:
    if not data:
        raise CheckError(400, "Choose a résumé file.")
    if len(data) > MAX_BYTES:
        raise CheckError(400, "That file is larger than 8 MB.")
    try:
        text = redact_ssn(extract_text(filename or "resume.txt", data))
    except ExtractError as exc:
        raise CheckError(400, exc.message) from exc
    facts = resume_facts(text)
    names = [item["name"] for item in facts.get("skills") or [] if item.get("name")]
    have = {name.lower() for name in names}
    must = _posting_lines(job, "must", list(job.must_have_skills or []))
    nice = _posting_lines(job, "nice", list(job.nice_to_have_skills or []))
    required = _summary(_items(must, section_coverage(set(names), must, text), have))
    desired = _summary(_items(nice, section_coverage(set(names), nice, text), have))
    title_tools = [{"name": tool, "have": tool.lower() in have} for tool in tools_and_languages(job.title or "")]
    title_ok = covers_title(set(names), job.title)
    pct = required["pct"]
    if pct is None:
        verdict = "unknown"
    elif pct >= MANDATORY_BAR and title_ok:
        verdict = "strong"
    elif pct >= 0.5:
        verdict = "partial"
    else:
        verdict = "low"
    missing_tools = sorted(
        {tool["name"] for item in required["items"] if not item["met"] for tool in item["tools"] if not tool["have"]}
        | {tool["name"] for tool in title_tools if not tool["have"]}
    )
    return {
        "requisition_code": job.requisition_code,
        "title": job.title,
        "verdict": verdict,
        "required": required,
        "desired": desired,
        "title_tools": title_tools,
        "title_ok": title_ok,
        "missing_tools": missing_tools[:12],
        "found_skills": names[:18],
        "characters": len(text),
    }
