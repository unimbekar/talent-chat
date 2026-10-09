"""Read-only tools the recruiter assistant can call.

Each tool runs the same code as the admin page it stands for, so the chat and the
page never disagree. A tool returns three things: compact data the model reads,
a block the browser draws (a table or a card), and a one-line summary for the
step list. No tool writes to the database.

Filters the model passes are checked against the recruiter's own words before
SQL sees them, the same way the Find page checks them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import re
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.admin.find import FindResult, ground_filters, run_filters
from app.admin.pipeline import STAGE_BY_KEY, STAGES, _card, _detail, counts_by_stage, list_submissions
from app.admin.reports import CLEARANCE_LABELS, POLY_LABELS, build_report
from app.admin.routes import (
    _candidate_out,
    _job_out,
    _match_out,
    _coverage_sort,
    _person_name,
    job_candidates as _job_candidates,
    overview as _overview,
    review_pair as _review_pair,
)
from app.core.labor import categories_for_question
from app.core.skills import find_canonicals
from app.core.us_states import state_code, state_name
from app.models import Candidate, Job, Match, Submission
from app.public.search import search_jobs as _search_jobs

MODEL_ROWS = 10
BLOCK_ROWS = 200


class ToolError(Exception):
    """A message for the model, such as an unknown code. The chat keeps going."""


@dataclass
class ToolContext:
    session: Session
    llm: object | None = None
    embedder: object | None = None
    # Recent recruiter messages. Filters must be grounded in these words.
    grounding: str = ""
    zone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    today: date = field(default_factory=date.today)


@dataclass
class ToolResult:
    data: dict
    summary: str
    block: dict | None = None
    codes: set[str] = field(default_factory=set)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: object
    label: str

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _str(args: dict, key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def _int(args: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(args.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _strings(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, (str, int)) and str(item).strip()]


def _bool(args: dict, key: str) -> bool:
    value = args.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _detail_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _skill_names(candidate: Candidate, wanted: set[str] | None = None, limit: int = 6) -> list[str]:
    names = [item.get("name") for item in (candidate.skills or []) if isinstance(item, dict) and item.get("name")]
    if wanted:
        names.sort(key=lambda name: name.lower() not in wanted)
    return names[:limit]


def _candidate_row(candidate: Candidate, wanted: set[str] | None = None) -> dict:
    return {
        "id": str(candidate.id),
        "name": _person_name(candidate) or candidate.original_filename or "Unnamed résumé",
        "email": candidate.email,
        "location": candidate.location,
        "titles": list(candidate.titles or [])[:2],
        "skills": _skill_names(candidate, wanted),
        "clearance": CLEARANCE_LABELS.get(candidate.clearance, candidate.clearance) if candidate.clearance else None,
    }


def _job_row(job: Job, submissions: int | None = None) -> dict:
    row = {
        "code": job.requisition_code,
        "title": job.title,
        "location": job.location,
        "status": job.status,
        "needs_review": bool(job.needs_review),
        "must_have": list(job.must_have_skills or [])[:8],
        "clearance": job.clearance_required,
        "posting_url": job.source_url,
    }
    if submissions is not None:
        row["submissions"] = submissions
    return row


def _submission_counts(session: Session, job_ids: list) -> dict:
    if not job_ids:
        return {}
    rows = session.execute(
        select(Submission.job_id, func.count()).where(Submission.job_id.in_(job_ids)).group_by(Submission.job_id)
    ).all()
    return {job_id: total for job_id, total in rows}


def _job(session: Session, code: str) -> Job:
    code = (code or "").strip().upper()
    if not code:
        raise ToolError("A job code such as A1001 is required.")
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise ToolError(f"No job with code {code} is on file.")
    return job


def _candidates_named(session: Session, name: str, limit: int = 10) -> list[Candidate]:
    words = [word for word in re.split(r"\s+", name.strip()) if word]
    if not words:
        return []
    stmt = select(Candidate)
    for word in words:
        pattern = _like(word)
        stmt = stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.original_filename.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
            )
        )
    return list(session.scalars(stmt.order_by(func.lower(Candidate.full_name)).limit(limit)).all())


def _one_candidate(session: Session, args: dict) -> Candidate:
    raw_id = _str(args, "candidate_id")
    if raw_id:
        try:
            candidate = session.get(Candidate, uuid.UUID(raw_id))
        except ValueError:
            candidate = None
        if candidate is not None:
            return candidate
    name = _str(args, "candidate_name") or _str(args, "name") or (raw_id if raw_id and not _looks_like_uuid(raw_id) else "")
    if not name:
        raise ToolError("Give a candidate_id or a candidate_name.")
    found = _candidates_named(session, name)
    if not found:
        raise ToolError(f"No candidate named {name} is on file.")
    if len(found) > 1:
        options = "; ".join(
            f"{_person_name(c) or c.original_filename}, {c.location or 'location not on file'} (candidate_id {c.id})"
            for c in found[:6]
        )
        raise ToolError(f"More than one candidate matches {name}: {options}. Ask the recruiter which one.")
    return found[0]


def _looks_like_uuid(text: str) -> bool:
    try:
        uuid.UUID(text)
        return True
    except ValueError:
        return False


# Clearance and polygraph filters, each checked against the recruiter's words.
_CLEARANCE_WORDS = {
    "ts_sci": r"\bts\s*/?\s*sci\b|\bsci\b",
    "ts": r"\btop[\s-]*secret\b|\bts\b",
    "secret": r"\bsecret\b",
    "public_trust": r"\bpublic[\s-]*trust\b",
    "any": r"\bclear(ed|ance|ances)?\b",
}
# Asking for a level means that level or higher.
_CLEARANCE_AT_LEAST = {
    "ts_sci": ["ts_sci"],
    "ts": ["ts", "ts_sci"],
    "secret": ["secret", "ts", "ts_sci"],
    "public_trust": ["public_trust", "secret", "ts", "ts_sci"],
}
_POLY_WORDS = {
    "full_scope": r"\bfull[\s-]*scope\b|\bfsp\b|\blifestyle\b",
    "ci": r"\bci\b|counter[\s-]*intelligence",
    "any": r"\bpoly(graph)?s?\b",
}


def _clearance_clauses(args: dict, grounding: str) -> tuple[list, list[str], list[str]]:
    clauses: list = []
    labels: list[str] = []
    dropped: list[str] = []
    text = grounding.lower()
    level = _str(args, "clearance").lower().replace("/", "_").replace(" ", "_").replace("-", "_")
    level = {"top_secret": "ts", "tssci": "ts_sci", "ts_sci": "ts_sci", "cleared": "any"}.get(level, level)
    if level:
        if level in _CLEARANCE_WORDS and re.search(_CLEARANCE_WORDS[level], text):
            if level == "any":
                clauses.append(Candidate.clearance.is_not(None))
                labels.append("any clearance on file")
            else:
                clauses.append(Candidate.clearance.in_(_CLEARANCE_AT_LEAST[level]))
                labels.append(f"at least {CLEARANCE_LABELS[level]}")
        else:
            dropped.append(f"clearance {level}")
    poly = _str(args, "polygraph").lower().replace(" ", "_").replace("-", "_")
    if poly:
        if poly in _POLY_WORDS and re.search(_POLY_WORDS[poly], text):
            if poly == "any":
                clauses.append(Candidate.polygraph.is_not(None))
                labels.append("any polygraph")
            else:
                clauses.append(Candidate.polygraph == poly)
                labels.append(POLY_LABELS[poly])
        else:
            dropped.append(f"polygraph {poly}")
    return clauses, labels, dropped


def find_candidates(ctx: ToolContext, args: dict) -> ToolResult:
    name = _str(args, "name")
    if name:
        rows = _candidates_named(ctx.session, name, limit=25)
        payload = [_candidate_row(row) for row in rows]
        return ToolResult(
            data={"total": len(rows), "candidates": payload[:MODEL_ROWS]},
            summary=f"{len(rows)} candidate{'s' if len(rows) != 1 else ''} named “{name}”",
            block={"type": "candidates", "title": f"Candidates named “{name}”", "total": len(rows), "rows": payload},
        )
    asked = {key: args.get(key) for key in ("skills", "states", "exclude_states", "cities", "roles", "keywords")}
    # "Java developer" as a role still means the skill Java.
    role_skills = [name for role in _strings(asked.get("roles")) for name in find_canonicals(role)]
    if role_skills:
        asked["skills"] = _strings(asked.get("skills")) + role_skills
    filters = ground_filters(asked, ctx.grounding, add_named=False)
    extra, extra_labels, dropped = _clearance_clauses(args, ctx.grounding)
    kept = {value.lower() for value in filters.skills + filters.keywords + filters.categories}
    for key in ("skills", "keywords", "roles"):
        for value in _strings(asked.get(key)):
            if value.lower() in kept or any(name.lower() in kept for name in find_canonicals(value)):
                continue
            if key == "roles" and any(label.lower() in kept for label in categories_for_question(value)):
                continue
            dropped.append(value)
    for key, chosen in (("states", filters.states), ("exclude_states", filters.exclude_states)):
        for value in _strings(asked.get(key)):
            if state_code(value) not in chosen:
                dropped.append(value)
    if filters.empty() and not extra:
        return ToolResult(
            data={
                "total": 0,
                "error": "No skill, role, state, or clearance from the recruiter's words was usable as a filter.",
                "ignored_filters": dropped,
            },
            summary="No usable filters",
        )
    result: FindResult = run_filters(ctx.session, filters, "", extra)
    wanted = {skill.lower() for skill in filters.skills}
    rows = [_candidate_row(row, wanted) for row in result.rows]
    applied = filters.as_dict()
    parts = []
    if filters.categories:
        parts.append(", ".join(filters.categories))
    if filters.skills:
        parts.append(" + ".join(filters.skills))
    if filters.keywords:
        parts.append(" + ".join(f"“{k}”" for k in filters.keywords))
    if filters.states:
        parts.append("in " + "/".join(filters.states))
    if filters.exclude_states:
        parts.append("outside " + "/".join(filters.exclude_states))
    parts.extend(extra_labels)
    title = "Candidates · " + " · ".join(parts)
    data = {
        "total": len(rows),
        "capped_at": 200 if len(rows) >= 200 else None,
        "filters_applied": {
            "skills": filters.skills,
            "roles": filters.categories,
            "keywords": filters.keywords,
            "states": [state_name(code) for code in filters.states],
            "exclude_states": [state_name(code) for code in filters.exclude_states],
            "clearance": extra_labels,
        },
        "ignored_filters": dropped,
        "unknown_location": result.unknown_location,
        "candidates": rows[:MODEL_ROWS],
    }
    return ToolResult(
        data=data,
        summary=f"{len(rows)} candidate{'s' if len(rows) != 1 else ''} · {' · '.join(parts)}",
        block={
            "type": "candidates",
            "title": title,
            "total": len(rows),
            "rows": rows[:BLOCK_ROWS],
            "filters": applied,
            "clearance": extra_labels,
            "unknown_location": result.unknown_location,
        },
    )


def candidate_profile(ctx: ToolContext, args: dict) -> ToolResult:
    candidate = _one_candidate(ctx.session, args)
    profile = _candidate_out(candidate)
    matches = ctx.session.scalars(select(Match).where(Match.candidate_id == candidate.id)).all()
    ranked = sorted((_match_out(ctx.session, row) for row in matches), key=_coverage_sort, reverse=True)[:5]
    submissions = list_submissions(ctx.session, stage=None, scope="all", code=None, candidate_id=candidate.id, q="")
    data = {
        "id": profile["id"],
        "name": profile["full_name"],
        "email": profile["email"],
        "phone": profile["phone"],
        "location": profile["location"],
        "status": profile["status"],
        "titles": profile["titles"][:5],
        "skills": [item["name"] for item in profile["skills"]][:25],
        "clearance": CLEARANCE_LABELS.get(candidate.clearance, candidate.clearance or "Not on file"),
        "polygraph": POLY_LABELS.get(candidate.polygraph, candidate.polygraph or "Not on file"),
        "citizenship": profile["citizenship"],
        "summary": (profile["summary"] or "")[:600],
        "best_matching_jobs": [
            {
                "code": item["requisition_code"],
                "title": item["title"],
                "mandatory_pct": item["mandatory_pct"],
                "meets_bar": item["meets_bar"],
            }
            for item in ranked
        ],
        "submissions": [
            {"id": str(row.id), "code": row.job.requisition_code, "title": row.job.title, "stage": row.stage, "salary_usd": row.salary_usd}
            for row in submissions
        ],
    }
    return ToolResult(
        data=data,
        summary=f"Profile of {data['name'] or 'candidate'}",
        block={"type": "profile", "candidate": {**data, "has_file": bool(candidate.original_path)}},
        codes={item["code"] for item in data["best_matching_jobs"] if item["code"]}
        | {item["code"] for item in data["submissions"]},
    )


def find_jobs(ctx: ToolContext, args: dict) -> ToolResult:
    query = _str(args, "query")
    status = _str(args, "status").lower() or "open"
    if status not in {"open", "closed", "all"}:
        status = "open"
    evidence: dict[str, str] = {}
    if query and status == "open":
        result = _search_jobs(ctx.session, query, None, ctx.embedder)
        jobs = [hit.job for hit in result.hits]
        evidence = {hit.job.requisition_code: hit.evidence for hit in result.hits if hit.evidence}
    else:
        stmt = select(Job)
        if status != "all":
            stmt = stmt.where(Job.status == "closed") if status == "closed" else stmt.where(Job.status != "closed")
        if query:
            pattern = _like(query)
            stmt = stmt.where(
                or_(
                    Job.title.ilike(pattern, escape="\\"),
                    Job.location.ilike(pattern, escape="\\"),
                    Job.requisition_code.ilike(pattern, escape="\\"),
                    cast(Job.must_have_skills, String).ilike(pattern, escape="\\"),
                    Job.description_text.ilike(pattern, escape="\\"),
                )
            )
        jobs = list(ctx.session.scalars(stmt.order_by(Job.requisition_code)).all())
    if _bool(args, "needs_review"):
        jobs = [job for job in jobs if job.needs_review]
    if _bool(args, "missing_description"):
        jobs = [job for job in jobs if not (job.description_text or "").strip()]
    counts = _submission_counts(ctx.session, [job.id for job in jobs])
    rows = [_job_row(job, counts.get(job.id, 0)) for job in jobs]
    for row in rows:
        if row["code"] in evidence:
            row["evidence"] = evidence[row["code"]]
    label = f"“{query}”" if query else f"{status} jobs"
    return ToolResult(
        data={"total": len(rows), "status": status, "jobs": rows[:25]},
        summary=f"{len(rows)} job{'s' if len(rows) != 1 else ''} · {label}",
        block={"type": "jobs", "title": f"Jobs · {label}", "total": len(rows), "rows": rows[:BLOCK_ROWS]},
        codes={row["code"] for row in rows},
    )


def job_details(ctx: ToolContext, args: dict) -> ToolResult:
    job = _job(ctx.session, _str(args, "code"))
    out = _job_out(job)
    submissions = list_submissions(ctx.session, stage=None, scope="all", code=job.requisition_code, candidate_id=None, q="")
    data = {
        "code": out["requisition_code"],
        "title": out["title"],
        "location": out["location"],
        "status": out["status"],
        "close_note": out["close_note"],
        "needs_review": out["needs_review"],
        "must_have_skills": out["must_have_skills"],
        "nice_to_have_skills": out["nice_to_have_skills"],
        "clearance_required": out["clearance_required"],
        "polygraph_required": out["polygraph_required"],
        "summary": out["summary"],
        "description_excerpt": (out["description_text"] or "")[:1500] or None,
        "posting_url": out["source_url"],
        "submissions": [
            {"id": str(row.id), "candidate": row.candidate.full_name or row.candidate.original_filename, "stage": row.stage, "salary_usd": row.salary_usd}
            for row in submissions
        ],
    }
    return ToolResult(
        data=data,
        summary=f"{job.requisition_code} · {job.title}",
        block={"type": "job", "job": {key: value for key, value in data.items() if key != "description_excerpt"}},
        codes={job.requisition_code},
    )


def job_candidates(ctx: ToolContext, args: dict) -> ToolResult:
    job = _job(ctx.session, _str(args, "code"))
    limit = _int(args, "limit", 10, 1, 50)
    ranked = _job_candidates(job.requisition_code, ctx.session)["candidates"]
    if _bool(args, "meets_bar_only"):
        ranked = [item for item in ranked if item["meets_bar"]]
    rows = [
        {
            "id": item["id"],
            "name": item["full_name"] or item["original_filename"],
            "email": item["email"],
            "location": item["location"],
            "mandatory_pct": round(item["mandatory_pct"] * 100) if item["mandatory_pct"] is not None else None,
            "mandatory": f"{item['mandatory_hit']}/{item['mandatory_total']}",
            "desired": f"{item['desired_hit']}/{item['desired_total']}",
            "meets_bar": item["meets_bar"],
        }
        for item in ranked
    ]
    meets = sum(1 for row in rows if row["meets_bar"])
    return ToolResult(
        data={
            "code": job.requisition_code,
            "title": job.title,
            "total_ranked": len(rows),
            "meets_bar": meets,
            "candidates": rows[:limit],
        },
        summary=f"{len(rows)} ranked for {job.requisition_code} · {meets} meet the bar",
        block={
            "type": "ranked",
            "title": f"Best fits · {job.requisition_code} {job.title}",
            "code": job.requisition_code,
            "total": len(rows),
            "rows": rows[:BLOCK_ROWS],
        },
        codes={job.requisition_code},
    )


def check_fit(ctx: ToolContext, args: dict) -> ToolResult:
    job = _job(ctx.session, _str(args, "code"))
    candidate = _one_candidate(ctx.session, args)
    try:
        review = _review_pair(job.requisition_code, candidate.id, ctx.session)
    except HTTPException as exc:
        raise ToolError(_detail_message(exc)) from exc
    pct = review["mandatory_pct"]
    data = {
        "code": job.requisition_code,
        "title": job.title,
        "candidate_id": str(candidate.id),
        "candidate": review["candidate"]["full_name"] or candidate.original_filename,
        "mandatory_pct": None if pct is None else round(pct * 100),
        "mandatory": f"{review['mandatory_hit']}/{review['mandatory_total']}",
        "desired": f"{review['desired_hit']}/{review['desired_total']}",
        "meets_bar": review["meets_bar"],
        "mandatory_matched": review["mandatory_matched"],
        "mandatory_missing": review["mandatory_missing"],
        "desired_matched": review["desired_matched"],
        "desired_missing": review["desired_missing"],
        "title_tools_missing": review["title_missing"],
        "role_conflict": review["role_missing"],
    }
    return ToolResult(
        data=data,
        summary=f"{data['candidate']} vs {job.requisition_code} · {data['mandatory']} mandatory",
        block={"type": "fit", "fit": data},
        codes={job.requisition_code},
    )


def pipeline(ctx: ToolContext, args: dict) -> ToolResult:
    stage = _str(args, "stage").lower() or None
    if stage and stage not in STAGE_BY_KEY:
        raise ToolError(f"Stage must be one of {', '.join(STAGE_BY_KEY)}.")
    scope = _str(args, "scope").lower() or ("all" if stage else "active")
    if scope not in {"active", "all", "closed"}:
        scope = "active"
    code = _str(args, "code").upper() or None
    candidate_id = None
    if _str(args, "candidate_id") or _str(args, "candidate_name"):
        candidate_id = _one_candidate(ctx.session, args).id
    try:
        rows = list_submissions(ctx.session, stage=stage, scope=scope, code=code, candidate_id=candidate_id, q=_str(args, "text"))
    except HTTPException as exc:
        raise ToolError(_detail_message(exc)) from exc
    cards = [_card(row) for row in rows]
    counts = counts_by_stage(ctx.session)
    out = [
        {
            "id": card["id"],
            "candidate": card["candidate"]["full_name"] or card["candidate"]["original_filename"],
            "candidate_id": card["candidate"]["id"],
            "code": card["job"]["requisition_code"],
            "title": card["job"]["title"],
            "stage": card["stage_label"],
            "stage_key": card["stage"],
            "salary_usd": card["salary_usd"],
            "updated_at": (card["updated_at"] or "")[:10],
        }
        for card in cards
    ]
    label = STAGE_BY_KEY[stage].label if stage else scope
    return ToolResult(
        data={
            "total": len(out),
            "filter": {"stage": stage, "scope": scope, "code": code},
            "desk_counts_by_stage": {s.label: counts.get(s.key, 0) for s in STAGES},
            "submissions": out[:25],
        },
        summary=f"{len(out)} submission{'s' if len(out) != 1 else ''} · {label}",
        block={"type": "submissions", "title": f"Pipeline · {label}" + (f" · {code}" if code else ""), "total": len(out), "rows": out[:BLOCK_ROWS]},
        codes={row["code"] for row in out},
    )


def submission_details(ctx: ToolContext, args: dict) -> ToolResult:
    raw = _str(args, "submission_id")
    try:
        row = ctx.session.get(Submission, uuid.UUID(raw))
    except ValueError:
        row = None
    if row is None or row.candidate is None or row.job is None:
        raise ToolError("That submission is not on file.")
    detail = _detail(row)
    data = {
        "id": detail["id"],
        "candidate": detail["candidate"]["full_name"] or detail["candidate"]["original_filename"],
        "candidate_id": detail["candidate"]["id"],
        "code": detail["job"]["requisition_code"],
        "title": detail["job"]["title"],
        "stage": detail["stage_label"],
        "salary_usd": detail["salary_usd"],
        "salary_note": detail["salary_note"],
        "created_at": (detail["created_at"] or "")[:10],
        "history": [
            {"at": (event["at"] or "")[:10], "kind": event["kind"], "from": event["from_label"], "to": event["to_label"], "note": (event["body"] or "")[:200]}
            for event in detail["events"][-10:]
        ],
        "recent_comments": [
            {"at": (comment["created_at"] or "")[:10], "body": comment["body"][:300]} for comment in detail["comments"][:5]
        ],
    }
    return ToolResult(
        data=data,
        summary=f"Submission · {data['candidate']} for {data['code']}",
        block={"type": "submission", "submission": data},
        codes={data["code"]},
    )


def desk_stats(ctx: ToolContext, args: dict) -> ToolResult:
    data = _overview(ctx.session)
    counts = counts_by_stage(ctx.session)
    stats = {
        "jobs": data["jobs"],
        "candidates": data["candidates"],
        "pipeline_by_stage": {stage.label: counts.get(stage.key, 0) for stage in STAGES},
        "top_skills": data["top_skills"][:10],
        "top_states": data["top_states"][:6],
        "last_crawl": {"ok": data["crawl"]["last_ok"], "finished_at": data["crawl"]["last_finished_at"], "error": data["crawl"]["last_error"]},
    }
    items = [
        {"label": "Open jobs", "value": data["jobs"]["open"], "href": "/admin/jobs"},
        {"label": "Jobs needing review", "value": data["jobs"]["needs_review"], "href": "/admin/jobs"},
        {"label": "Candidates", "value": data["candidates"]["total"], "href": "/admin/candidates"},
        {"label": "Added this week", "value": data["candidates"]["added_this_week"], "href": "/admin/candidates"},
        {"label": "Active submissions", "value": data["pipeline"]["active"], "href": "/admin/pipeline"},
        {"label": "Selected", "value": data["pipeline"]["selected"], "href": "/admin/pipeline"},
    ]
    return ToolResult(data=stats, summary="Desk totals", block={"type": "stats", "title": "Desk at a glance", "items": items})


def _day(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return fallback


def report(ctx: ToolContext, args: dict) -> ToolResult:
    end_day = _day(_str(args, "end_date"), ctx.today)
    start_day = _day(_str(args, "start_date"), end_day - timedelta(days=29))
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    start = datetime.combine(start_day, time.min, ctx.zone)
    end = datetime.combine(end_day + timedelta(days=1), time.min, ctx.zone)
    salary = args.get("salary_above")
    try:
        salary_gt = int(salary) if salary not in (None, "") else None
    except (TypeError, ValueError):
        salary_gt = None
    clearance = _str(args, "clearance").lower()
    poly = _str(args, "polygraph").lower()
    try:
        data = build_report(
            ctx.session,
            start=start,
            end=end,
            zone=ctx.zone,
            poly=poly if poly in {"full_scope", "ci", "any", "missing"} else "",
            clearance=clearance if clearance in {"ts_sci", "ts", "secret", "public_trust", "any", "missing"} else "",
            salary_gt=salary_gt,
            salary_scope="range",
            clearance_scope="all",
            limit=50,
        )
    except HTTPException as exc:
        raise ToolError(_detail_message(exc)) from exc

    def person(row: dict) -> str:
        return row.get("full_name") or row.get("original_filename") or "Unnamed"

    summary = {
        "range": f"{start_day.isoformat()} to {end_day.isoformat()}",
        "resumes_ingested": data["ingested"]["total"],
        "ingested_and_submitted": data["ingested"]["also_submitted"],
        "submissions_created": data["submitted"]["total"],
        "submissions_by_stage": {row["label"]: row["count"] for row in data["submitted"]["by_stage"] if row["count"]},
        "top_jobs_by_submissions": data["submitted"]["by_job"][:5],
        "outcomes": {key: data["outcomes"][key] for key in ("selected", "rejected", "withdrawn")},
        "salaries_on_record": data["salary"]["with_salary"],
        "salary_buckets": {row["label"]: row["count"] for row in data["salary"]["buckets"] if row["count"]},
        "recent_ingested": [person(row) for row in data["ingested"]["candidates"][:8]],
        "recent_submissions": [
            {"candidate": person(row["candidate"]), "code": row["job"]["requisition_code"], "stage": row["stage_label"], "salary_usd": row["salary_usd"]}
            for row in data["submitted"]["rows"][:10]
        ],
    }
    if salary_gt is not None:
        summary["salary_above"] = {
            "line": salary_gt,
            "count": data["salary"]["above"],
            "rows": [
                {"candidate": person(row["candidate"]), "code": row["job"]["requisition_code"], "salary_usd": row["salary_usd"]}
                for row in data["salary"]["rows"][:10]
            ],
        }
    if clearance or poly:
        summary["clearance_filter"] = {
            "count": data["clearance"]["total"],
            "candidates": [person(row) for row in data["clearance"]["candidates"][:15]],
        }
    items = [
        {"label": "Résumés ingested", "value": summary["resumes_ingested"]},
        {"label": "Submissions", "value": summary["submissions_created"]},
        {"label": "Selected", "value": summary["outcomes"]["selected"]},
        {"label": "Rejected", "value": summary["outcomes"]["rejected"]},
    ]
    if salary_gt is not None:
        items.append({"label": f"Salary over ${salary_gt:,}", "value": data["salary"]["above"]})
    codes = {row["code"] for row in summary["recent_submissions"]} | {row["requisition_code"] for row in summary["top_jobs_by_submissions"]}
    return ToolResult(
        data=summary,
        summary=f"Report {summary['range']}",
        block={
            "type": "stats",
            "title": f"Report · {summary['range']}",
            "items": items,
            "href": "/admin/reports",
            "series": data["submitted"]["by_day"],
        },
        codes=codes,
    )


_STRINGS = {"type": "array", "items": {"type": "string"}}

TOOLS: list[Tool] = [
    Tool(
        "find_candidates",
        "Search the résumé library. Use for questions like 'Java developers in Maryland', 'who has ServiceNow', "
        "'TS/SCI with full scope poly', or a person's name. Put each skill, state, role, or clearance the recruiter "
        "named into its own field. Only use words the recruiter said.",
        {
            "type": "object",
            "properties": {
                "skills": {**_STRINGS, "description": "Tools, platforms, or languages, e.g. ['Java', 'AWS']."},
                "roles": {**_STRINGS, "description": "Job roles named, e.g. ['Software Tester']. Only when a role word is used."},
                "states": {**_STRINGS, "description": "US states the person must live in, as 2-letter codes."},
                "exclude_states": {**_STRINGS, "description": "US states to exclude ('outside Virginia')."},
                "cities": {"type": "array", "items": {"type": "object", "properties": {"city": {"type": "string"}, "state": {"type": "string"}}}},
                "keywords": {**_STRINGS, "description": "Other phrases the résumé must contain. Usually empty."},
                "clearance": {"type": "string", "enum": ["ts_sci", "ts", "secret", "public_trust", "any"], "description": "Minimum clearance on file."},
                "polygraph": {"type": "string", "enum": ["full_scope", "ci", "any"]},
                "name": {"type": "string", "description": "Look up candidates by name or email instead of filters."},
            },
        },
        find_candidates,
        "Searching candidates",
    ),
    Tool(
        "candidate_profile",
        "One candidate's profile: contact, skills, clearance, best matching jobs, and submissions.",
        {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string", "description": "Candidate UUID, when known from the page or a prior result."},
                "candidate_name": {"type": "string"},
            },
        },
        candidate_profile,
        "Opening profile",
    ),
    Tool(
        "find_jobs",
        "List or search job requisitions. query is skills, a title, or a city ('Java Chantilly'); leave it empty to "
        "list jobs. status defaults to open.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "closed", "all"]},
                "needs_review": {"type": "boolean", "description": "Only jobs flagged for review."},
                "missing_description": {"type": "boolean", "description": "Only jobs without a full description."},
            },
        },
        find_jobs,
        "Searching jobs",
    ),
    Tool(
        "job_details",
        "Full details of one job by requisition code: skills, clearance, summary, posting link, submissions.",
        {"type": "object", "properties": {"code": {"type": "string", "description": "Requisition code such as A1001."}}, "required": ["code"]},
        job_details,
        "Reading job",
    ),
    Tool(
        "job_candidates",
        "Rank the résumé library against one job by mandatory and desired skill coverage. Use for 'who fits A1001' "
        "or 'best candidates for this job'.",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "limit": {"type": "integer", "description": "How many to return to you, default 10."},
                "meets_bar_only": {"type": "boolean"},
            },
            "required": ["code"],
        },
        job_candidates,
        "Ranking candidates",
    ),
    Tool(
        "check_fit",
        "Compare one candidate with one job: matched and missing mandatory and desired skills.",
        {
            "type": "object",
            "properties": {"code": {"type": "string"}, "candidate_id": {"type": "string"}, "candidate_name": {"type": "string"}},
            "required": ["code"],
        },
        check_fit,
        "Checking fit",
    ),
    Tool(
        "pipeline",
        "Submissions on the pipeline board. Filter by stage (submitted, salary, interviewed, offer, selected, "
        "rejected, withdrawn), scope (active, closed, all), job code, candidate, or text.",
        {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": [stage.key for stage in STAGES]},
                "scope": {"type": "string", "enum": ["active", "closed", "all"]},
                "code": {"type": "string"},
                "candidate_id": {"type": "string"},
                "candidate_name": {"type": "string"},
                "text": {"type": "string"},
            },
        },
        pipeline,
        "Reading pipeline",
    ),
    Tool(
        "submission_details",
        "One submission's stage, salary, history, and recent comments.",
        {"type": "object", "properties": {"submission_id": {"type": "string"}}, "required": ["submission_id"]},
        submission_details,
        "Reading submission",
    ),
    Tool(
        "desk_stats",
        "Totals for the whole desk: open jobs, candidates, pipeline by stage, top skills and states, last crawl.",
        {"type": "object", "properties": {}},
        desk_stats,
        "Counting",
    ),
    Tool(
        "report",
        "Activity over a date range: résumés ingested, submissions, outcomes, salaries, clearance counts. Dates are "
        "YYYY-MM-DD and inclusive. Use for 'this week', 'last month', 'salaries over 150k'.",
        {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "salary_above": {"type": "integer"},
                "clearance": {"type": "string", "enum": ["ts_sci", "ts", "secret", "public_trust", "any", "missing"]},
                "polygraph": {"type": "string", "enum": ["full_scope", "ci", "any", "missing"]},
            },
        },
        report,
        "Building report",
    ),
]

TOOL_BY_NAME = {tool.name: tool for tool in TOOLS}


def run_tool(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    tool = TOOL_BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"There is no tool named {name}.")
    try:
        return tool.handler(ctx, args or {})
    except HTTPException as exc:
        raise ToolError(_detail_message(exc)) from exc
