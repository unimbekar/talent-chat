"""Recruiter reports: ingest, submissions, clearance, salary, and outcomes.

Dates are an inclusive local calendar range. The browser sends the start of the
first day and the start of the day after the last day, in UTC, plus the IANA
timezone used to draw the daily bars.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.admin.pipeline import STAGES, require_admin
from app.admin.xlsx import workbook
from app.models import Candidate, Job, Submission, SubmissionEvent

router = APIRouter(prefix="/admin", tags=["reports"])

LIST_CAP = 500
EXPORT_CAP = 5000
RANGE_CAP_DAYS = 366
OUTCOMES = ("selected", "rejected", "withdrawn")
CLEARANCE_LEVELS = ("ts_sci", "ts", "secret", "public_trust")
POLY_LEVELS = ("full_scope", "ci", "unknown")
CLEARANCE_LABELS = {
    "ts_sci": "TS/SCI",
    "ts": "Top Secret",
    "secret": "Secret",
    "public_trust": "Public Trust",
    "unknown": "Unparsed",
    None: "Not on file",
}
POLY_LABELS = {
    "full_scope": "Full scope (FSP)",
    "ci": "CI polygraph",
    "unknown": "Polygraph, scope not stated",
    None: "Not on file",
}
STAGE_LABELS = {stage.key: stage.label for stage in STAGES}


def _fail(status: int, message: str) -> None:
    raise HTTPException(status_code=status, detail={"message": message})


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        _fail(400, "That timezone is not recognized.")
        raise AssertionError("unreachable")


def _window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        _fail(400, "Send the start and end with a timezone.")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if end <= start:
        _fail(400, "The end of the range has to be after the start.")
    if end - start > timedelta(days=RANGE_CAP_DAYS):
        _fail(400, "Choose a range of a year or less. The clearance and salary lists can still cover the whole desk.")
    return start, end


def _name(candidate: Candidate) -> str:
    return (candidate.full_name or candidate.original_filename or "Unnamed résumé").strip()


def _when(moment: datetime | None, zone: ZoneInfo) -> str | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).isoformat(timespec="minutes")


def _person(candidate: Candidate) -> dict:
    return {
        "id": str(candidate.id),
        "full_name": _name(candidate),
        "email": candidate.email,
        "location": candidate.location,
        "state": candidate.state,
        "clearance": candidate.clearance,
        "clearance_label": CLEARANCE_LABELS.get(candidate.clearance, candidate.clearance or "Not on file"),
        "polygraph": candidate.polygraph,
        "polygraph_label": POLY_LABELS.get(candidate.polygraph, candidate.polygraph or "Not on file"),
        "original_filename": candidate.original_filename,
    }


def _day_counts(session: Session, column, start: datetime, end: datetime, zone: ZoneInfo, *wheres) -> dict[str, int]:
    day = cast(func.timezone(zone.key, column), Date)
    stmt = select(day, func.count()).where(column >= start, column < end)
    for clause in wheres:
        stmt = stmt.where(clause)
    rows = session.execute(stmt.group_by(day)).all()
    return {value.isoformat(): total for value, total in rows if value is not None}


def _series(counts: dict[str, int], start: datetime, end: datetime, zone: ZoneInfo) -> list[dict]:
    first = start.astimezone(zone).date()
    last = (end - timedelta(microseconds=1)).astimezone(zone).date()
    days: list[tuple[str, int]] = []
    cursor = first
    while cursor <= last and len(days) <= RANGE_CAP_DAYS:
        key = cursor.isoformat()
        days.append((key, counts.get(key, 0)))
        cursor += timedelta(days=1)
    if len(days) <= 45:
        return [{"label": key[5:], "date": key, "count": total} for key, total in days]
    weeks: list[dict] = []
    bucket_start = ""
    bucket_total = 0
    for index, (key, total) in enumerate(days):
        if index % 7 == 0:
            if bucket_start:
                weeks.append({"label": bucket_start[5:], "date": bucket_start, "count": bucket_total})
            bucket_start = key
            bucket_total = 0
        bucket_total += total
    if bucket_start:
        weeks.append({"label": bucket_start[5:], "date": bucket_start, "count": bucket_total})
    return weeks


def _submission_row(row: Submission, zone: ZoneInfo) -> dict:
    return {
        "id": str(row.id),
        "stage": row.stage,
        "stage_label": STAGE_LABELS.get(row.stage, row.stage),
        "salary_usd": row.salary_usd,
        "salary_note": row.salary_note,
        "created_at": _when(row.created_at, zone),
        "updated_at": _when(row.updated_at, zone),
        "candidate": _person(row.candidate),
        "job": {
            "requisition_code": row.job.requisition_code,
            "title": row.job.title,
            "location": row.job.location,
            "status": row.job.status,
        },
    }


def _clearance_filters(poly: str, clearance: str):
    clauses = []
    if poly == "full_scope":
        clauses.append(Candidate.polygraph == "full_scope")
    elif poly == "ci":
        clauses.append(Candidate.polygraph == "ci")
    elif poly == "any":
        clauses.append(Candidate.polygraph.is_not(None))
    elif poly == "missing":
        clauses.append(Candidate.polygraph.is_(None))
    elif poly:
        _fail(400, "Polygraph filter must be full scope, CI, any, missing, or blank.")
    if clearance in CLEARANCE_LEVELS:
        clauses.append(Candidate.clearance == clearance)
    elif clearance == "any":
        clauses.append(Candidate.clearance.is_not(None))
    elif clearance == "missing":
        clauses.append(Candidate.clearance.is_(None))
    elif clearance:
        _fail(400, "Clearance filter must be a known level, any, missing, or blank.")
    return clauses


def build_report(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    zone: ZoneInfo,
    poly: str,
    clearance: str,
    salary_gt: int | None,
    salary_scope: str,
    clearance_scope: str,
    limit: int,
) -> dict:
    start, end = _window(start, end)
    if salary_scope not in {"range", "all"} or clearance_scope not in {"range", "all"}:
        _fail(400, "Scope must be range or all.")
    if salary_gt is not None and (salary_gt < 0 or salary_gt > 5_000_000):
        _fail(400, "The salary line has to be between 0 and 5,000,000.")

    ingested_rows = session.scalars(
        select(Candidate)
        .where(Candidate.created_at >= start, Candidate.created_at < end)
        .order_by(Candidate.created_at.desc())
        .limit(limit)
    ).all()
    ingested_total = session.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.created_at >= start, Candidate.created_at < end)
    ) or 0
    ingested_days = _series(_day_counts(session, Candidate.created_at, start, end, zone), start, end, zone)
    submitted_people = session.scalar(
        select(func.count(func.distinct(Submission.candidate_id)))
        .select_from(Submission)
        .join(Candidate, Submission.candidate_id == Candidate.id)
        .where(Candidate.created_at >= start, Candidate.created_at < end)
    ) or 0

    submissions = session.scalars(
        select(Submission)
        .join(Candidate, Submission.candidate_id == Candidate.id)
        .join(Job, Submission.job_id == Job.id)
        .where(Submission.created_at >= start, Submission.created_at < end)
        .order_by(Submission.created_at.desc())
        .limit(limit)
    ).all()
    submitted_total = session.scalar(
        select(func.count()).select_from(Submission).where(Submission.created_at >= start, Submission.created_at < end)
    ) or 0
    submitted_days = _series(_day_counts(session, Submission.created_at, start, end, zone), start, end, zone)
    stage_rows = session.execute(
        select(Submission.stage, func.count())
        .where(Submission.created_at >= start, Submission.created_at < end)
        .group_by(Submission.stage)
    ).all()
    stage_counts = {stage: total for stage, total in stage_rows}
    job_rows = session.execute(
        select(Job.requisition_code, Job.title, func.count())
        .join(Submission, Submission.job_id == Job.id)
        .where(Submission.created_at >= start, Submission.created_at < end)
        .group_by(Job.requisition_code, Job.title)
        .order_by(func.count().desc())
        .limit(8)
    ).all()

    outcome_events = session.scalars(
        select(SubmissionEvent)
        .join(Submission, SubmissionEvent.submission_id == Submission.id)
        .where(
            SubmissionEvent.kind == "stage",
            SubmissionEvent.to_stage.in_(OUTCOMES),
            SubmissionEvent.at >= start,
            SubmissionEvent.at < end,
        )
        .order_by(SubmissionEvent.at.desc())
        .limit(limit)
    ).all()
    outcome_counts = {key: 0 for key in OUTCOMES}
    for key, total in session.execute(
        select(SubmissionEvent.to_stage, func.count()).where(
            SubmissionEvent.kind == "stage",
            SubmissionEvent.to_stage.in_(OUTCOMES),
            SubmissionEvent.at >= start,
            SubmissionEvent.at < end,
        ).group_by(SubmissionEvent.to_stage)
    ).all():
        outcome_counts[key] = total

    clearance_stmt = select(Candidate)
    if clearance_scope == "range":
        clearance_stmt = clearance_stmt.where(Candidate.created_at >= start, Candidate.created_at < end)
    for clause in _clearance_filters(poly, clearance):
        clearance_stmt = clearance_stmt.where(clause)
    clearance_total = session.scalar(select(func.count()).select_from(clearance_stmt.subquery())) or 0
    clearance_rows = session.scalars(
        clearance_stmt.order_by(func.lower(Candidate.full_name), Candidate.original_filename).limit(limit)
    ).all()
    poly_mix = [
        {"key": key or "missing", "label": POLY_LABELS.get(key, "Not on file"), "count": total}
        for key, total in session.execute(
            select(Candidate.polygraph, func.count()).group_by(Candidate.polygraph).order_by(func.count().desc())
        ).all()
    ]
    clearance_mix = [
        {"key": key or "missing", "label": CLEARANCE_LABELS.get(key, key or "Not on file"), "count": total}
        for key, total in session.execute(
            select(Candidate.clearance, func.count()).group_by(Candidate.clearance).order_by(func.count().desc())
        ).all()
    ]

    salary_stmt = (
        select(Submission)
        .join(Candidate, Submission.candidate_id == Candidate.id)
        .join(Job, Submission.job_id == Job.id)
        .where(Submission.salary_usd.is_not(None))
    )
    if salary_scope == "range":
        salary_stmt = salary_stmt.where(Submission.created_at >= start, Submission.created_at < end)
    salaried = session.scalars(salary_stmt).all()
    buckets = [
        {"label": "Under $100k", "min": 0, "max": 100_000, "count": 0},
        {"label": "$100–150k", "min": 100_000, "max": 150_000, "count": 0},
        {"label": "$150–180k", "min": 150_000, "max": 180_000, "count": 0},
        {"label": "$180–220k", "min": 180_000, "max": 220_000, "count": 0},
        {"label": "$220k and up", "min": 220_000, "max": None, "count": 0},
    ]
    above = []
    for row in salaried:
        amount = row.salary_usd or 0
        for bucket in buckets:
            ceiling = bucket["max"]
            if amount >= bucket["min"] and (ceiling is None or amount < ceiling):
                bucket["count"] += 1
                break
        if salary_gt is not None and amount > salary_gt:
            above.append(row)
    above.sort(key=lambda row: row.salary_usd or 0, reverse=True)
    above_total = len(above)
    above = above[:limit]

    pipeline_rows = session.execute(select(Submission.stage, func.count()).group_by(Submission.stage)).all()
    pipeline_counts = {stage: total for stage, total in pipeline_rows}

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": zone.key,
        "ingested": {
            "total": ingested_total,
            "shown": len(ingested_rows),
            "also_submitted": submitted_people,
            "by_day": ingested_days,
            "candidates": [{**_person(row), "created_at": _when(row.created_at, zone)} for row in ingested_rows],
        },
        "submitted": {
            "total": submitted_total,
            "shown": len(submissions),
            "by_day": submitted_days,
            "by_stage": [
                {"key": stage.key, "label": stage.label, "count": stage_counts.get(stage.key, 0)} for stage in STAGES
            ],
            "by_job": [
                {"requisition_code": code, "title": title, "count": total} for code, title, total in job_rows
            ],
            "rows": [_submission_row(row, zone) for row in submissions],
        },
        "outcomes": {
            "selected": outcome_counts["selected"],
            "rejected": outcome_counts["rejected"],
            "withdrawn": outcome_counts["withdrawn"],
            "rows": [
                {
                    "at": _when(event.at, zone),
                    "to_stage": event.to_stage,
                    "to_label": STAGE_LABELS.get(event.to_stage or "", event.to_stage),
                    "from_label": STAGE_LABELS.get(event.from_stage or "", event.from_stage),
                    "submission_id": str(event.submission_id),
                    "candidate": _person(event.submission.candidate),
                    "job": {
                        "requisition_code": event.submission.job.requisition_code,
                        "title": event.submission.job.title,
                    },
                }
                for event in outcome_events
            ],
        },
        "clearance": {
            "poly": poly or "",
            "clearance": clearance or "",
            "scope": clearance_scope,
            "total": clearance_total,
            "shown": len(clearance_rows),
            "poly_mix": poly_mix,
            "clearance_mix": clearance_mix,
            "candidates": [{**_person(row), "created_at": _when(row.created_at, zone)} for row in clearance_rows],
        },
        "salary": {
            "greater_than": salary_gt,
            "scope": salary_scope,
            "with_salary": len(salaried),
            "above": above_total,
            "shown": len(above),
            "buckets": buckets,
            "rows": [_submission_row(row, zone) for row in above],
        },
        "pipeline": [
            {"key": stage.key, "label": stage.label, "terminal": stage.terminal, "count": pipeline_counts.get(stage.key, 0)}
            for stage in STAGES
        ],
    }


def _csv_cell(value) -> str:
    text = "" if value is None else str(value)
    if text[:1] in "=+-@\t\r":
        text = "'" + text
    if any(mark in text for mark in '",\n\r'):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _csv(headers: list[str], rows: list[list]) -> bytes:
    lines = [",".join(_csv_cell(header) for header in headers)]
    lines.extend(",".join(_csv_cell(value) for value in row) for row in rows)
    return ("\ufeff" + "\r\n".join(lines) + "\r\n").encode("utf-8")


def _sheets(report: dict) -> dict[str, tuple[list[str], list[list]]]:
    ingested_header = ["Name", "Email", "Location", "Clearance", "Polygraph", "Ingested"]
    ingested_rows = [
        [row["full_name"], row["email"], row["location"], row["clearance_label"], row["polygraph_label"], row["created_at"]]
        for row in report["ingested"]["candidates"]
    ]
    submitted_header = ["Name", "Email", "Job", "Title", "Stage", "Salary", "Salary note", "Submitted"]
    submitted_rows = [
        [
            row["candidate"]["full_name"],
            row["candidate"]["email"],
            row["job"]["requisition_code"],
            row["job"]["title"],
            row["stage_label"],
            row["salary_usd"],
            row["salary_note"],
            row["created_at"],
        ]
        for row in report["submitted"]["rows"]
    ]
    clearance_header = ["Name", "Email", "Location", "State", "Clearance", "Polygraph", "Ingested"]
    clearance_rows = [
        [row["full_name"], row["email"], row["location"], row["state"], row["clearance_label"], row["polygraph_label"], row["created_at"]]
        for row in report["clearance"]["candidates"]
    ]
    salary_header = ["Name", "Email", "Job", "Title", "Stage", "Salary", "Salary note"]
    salary_rows = [
        [
            row["candidate"]["full_name"],
            row["candidate"]["email"],
            row["job"]["requisition_code"],
            row["job"]["title"],
            row["stage_label"],
            row["salary_usd"],
            row["salary_note"],
        ]
        for row in report["salary"]["rows"]
    ]
    outcome_header = ["When", "Outcome", "From", "Name", "Email", "Job", "Title"]
    outcome_rows = [
        [
            row["at"],
            row["to_label"],
            row["from_label"],
            row["candidate"]["full_name"],
            row["candidate"]["email"],
            row["job"]["requisition_code"],
            row["job"]["title"],
        ]
        for row in report["outcomes"]["rows"]
    ]
    summary = [
        ["From", report["start"]],
        ["Through (exclusive)", report["end"]],
        ["Timezone", report["timezone"]],
        ["Ingested", report["ingested"]["total"]],
        ["Of those, submitted for at least one job", report["ingested"]["also_submitted"]],
        ["Submissions opened", report["submitted"]["total"]],
        ["Selected", report["outcomes"]["selected"]],
        ["Rejected", report["outcomes"]["rejected"]],
        ["Withdrawn", report["outcomes"]["withdrawn"]],
        ["Clearance roster", report["clearance"]["total"]],
        ["Salary rows above the line", report["salary"]["above"]],
    ]
    return {
        "summary": (["Measure", "Count"], summary),
        "ingested": (ingested_header, ingested_rows),
        "submitted": (submitted_header, submitted_rows),
        "clearance": (clearance_header, clearance_rows),
        "salary": (salary_header, salary_rows),
        "outcomes": (outcome_header, outcome_rows),
    }


def _parse_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(400, "The start and end must be ISO dates, such as 2026-10-08T00:00:00-04:00.")
        raise AssertionError("unreachable")
    return parsed


@router.get("/reports")
def get_report(
    request: Request,
    start: str,
    end: str,
    tz: str = "UTC",
    poly: str = "full_scope",
    clearance: str = "",
    salary_gt: int | None = None,
    salary_scope: str = "all",
    clearance_scope: str = "all",
    session: Session = Depends(require_admin),
):
    del request
    return build_report(
        session,
        start=_parse_start(start),
        end=_parse_start(end),
        zone=_zone(tz),
        poly=poly,
        clearance=clearance,
        salary_gt=salary_gt,
        salary_scope=salary_scope,
        clearance_scope=clearance_scope,
        limit=LIST_CAP,
    )


@router.get("/reports/export")
def export_report(
    request: Request,
    start: str,
    end: str,
    format: str = "xlsx",
    sheet: str = "all",
    tz: str = "UTC",
    poly: str = "full_scope",
    clearance: str = "",
    salary_gt: int | None = None,
    salary_scope: str = "all",
    clearance_scope: str = "all",
    session: Session = Depends(require_admin),
):
    del request
    if format not in {"csv", "xlsx"}:
        _fail(400, "Export format must be csv or xlsx.")
    report = build_report(
        session,
        start=_parse_start(start),
        end=_parse_start(end),
        zone=_zone(tz),
        poly=poly,
        clearance=clearance,
        salary_gt=salary_gt,
        salary_scope=salary_scope,
        clearance_scope=clearance_scope,
        limit=EXPORT_CAP,
    )
    sheets = _sheets(report)
    if format == "csv":
        if sheet not in sheets or sheet == "summary":
            _fail(400, "Choose ingested, submitted, clearance, salary, or outcomes for a CSV file.")
        headers, rows = sheets[sheet]
        payload = _csv(headers, rows)
        filename = f"talent-{sheet}.csv"
        media = "text/csv; charset=utf-8"
    else:
        chosen = list(sheets.items()) if sheet == "all" else [(sheet, sheets[sheet])] if sheet in sheets else None
        if chosen is None:
            _fail(400, "That sheet is not part of the workbook.")
        payload = workbook([(name[:31], headers, rows) for name, (headers, rows) in chosen])
        filename = "talent-report.xlsx"
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content=payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
