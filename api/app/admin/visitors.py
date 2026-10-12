"""Careers-site visitors for admins: per day, all time, and where they came from.

Days are local calendar days in the timezone the browser sends, like the reports page.
A visitor is one browser (a random id in local storage), so one person on a phone and a
laptop counts twice, and clearing site data starts a new visitor.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.admin.access import admin_only
from app.admin.reports import RANGE_CAP_DAYS, _fail, _zone
from app.models import Job, JobApplication, SiteVisit

router = APIRouter(prefix="/admin", tags=["visitors"])

TOP = 8
LIVE_MINUTES = 15
PAGE_LABELS = {"/jobs": "Open jobs", "/jobs/benefits": "Benefits"}
SOURCE_LABELS = {
    "direct": "Direct or bookmark",
    "email": "Email",
    "google": "Google",
    "bing": "Bing",
    "duckduckgo": "DuckDuckGo",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "x": "X (Twitter)",
    "indeed": "Indeed",
    "glassdoor": "Glassdoor",
    "clearancejobs": "ClearanceJobs",
}
DEVICE_LABELS = {"desktop": "Desktop", "mobile": "Phone", "tablet": "Tablet"}


def _local_day(zone_name: str, column):
    return cast(func.timezone(zone_name, column), Date)


def _days(start: datetime, end: datetime, zone) -> list[date]:
    first = start.astimezone(zone).date()
    last = (end - timedelta(microseconds=1)).astimezone(zone).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _distinct(session: Session, start: datetime, end: datetime, *where) -> int:
    return session.scalar(
        select(func.count(func.distinct(SiteVisit.visitor))).where(SiteVisit.at >= start, SiteVisit.at < end, *where)
    ) or 0


def _views(session: Session, start: datetime, end: datetime) -> int:
    return session.scalar(
        select(func.count()).select_from(SiteVisit).where(SiteVisit.at >= start, SiteVisit.at < end, SiteVisit.kind == "page")
    ) or 0


def _change(now: int, before: int) -> float | None:
    """Percent change from the previous period of the same length, or None with nothing to compare."""
    if before == 0:
        return None
    return round((now - before) / before * 100, 1)


def summary(session: Session, start: datetime, end: datetime, zone_name: str, now: datetime | None = None) -> dict:
    zone = _zone(zone_name)
    now = now or datetime.now(timezone.utc)
    day = _local_day(zone_name, SiteVisit.at)
    in_range = (SiteVisit.at >= start, SiteVisit.at < end)

    per_day = {
        row.day: row
        for row in session.execute(
            select(
                day.label("day"),
                func.count(func.distinct(SiteVisit.visitor)).label("visitors"),
                func.count().filter(SiteVisit.kind == "page").label("views"),
                func.count().filter(SiteVisit.kind == "posting").label("postings"),
            )
            .where(*in_range)
            .group_by("day")
        )
    }

    first_seen = select(SiteVisit.visitor, func.min(SiteVisit.at).label("first_at")).group_by(SiteVisit.visitor).subquery()
    first_day = _local_day(zone_name, first_seen.c.first_at).label("day")
    new_per_day = dict(
        session.execute(
            select(first_day, func.count())
            .where(first_seen.c.first_at >= start, first_seen.c.first_at < end)
            .group_by("day")
        ).all()
    )
    before_range = session.scalar(select(func.count()).select_from(first_seen).where(first_seen.c.first_at < start)) or 0
    all_time, first_visit = session.execute(select(func.count(), func.min(first_seen.c.first_at)).select_from(first_seen)).one()

    app_day = _local_day(zone_name, JobApplication.created_at).label("day")
    applications_per_day = dict(
        session.execute(
            select(app_day, func.count())
            .where(JobApplication.created_at >= start, JobApplication.created_at < end)
            .group_by("day")
        ).all()
    )

    days = []
    running = before_range
    for current in _days(start, end, zone):
        row = per_day.get(current)
        new = new_per_day.get(current, 0)
        running += new
        days.append(
            {
                "date": current.isoformat(),
                "visitors": row.visitors if row else 0,
                "views": row.views if row else 0,
                "postings": row.postings if row else 0,
                "new": new,
                "applications": applications_per_day.get(current, 0),
                "total": running,
            }
        )

    visitors = _distinct(session, start, end)
    views = _views(session, start, end)
    new_visitors = sum(new_per_day.values())
    length = end - start
    previous_visitors = _distinct(session, start - length, start)
    previous_views = _views(session, start - length, start)
    peak = max(days, key=lambda item: item["visitors"], default=None)
    applications = sum(applications_per_day.values())

    today = now.astimezone(zone).date()
    today_start = datetime.combine(today, datetime.min.time(), zone).astimezone(timezone.utc)
    today_end = datetime.combine(today + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)

    viewed_posting = _distinct(session, start, end, SiteVisit.kind == "posting")
    started_apply = _distinct(session, start, end, SiteVisit.kind == "apply")

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": zone_name,
        "all_time": {
            "visitors": all_time or 0,
            "views": session.scalar(select(func.count()).select_from(SiteVisit).where(SiteVisit.kind == "page")) or 0,
            "since": first_visit.astimezone(zone).date().isoformat() if first_visit else None,
        },
        "today": {"visitors": _distinct(session, today_start, today_end), "views": _views(session, today_start, today_end)},
        "live": _distinct(session, now - timedelta(minutes=LIVE_MINUTES), now + timedelta(minutes=1)),
        "live_minutes": LIVE_MINUTES,
        "range": {
            "visitors": visitors,
            "views": views,
            "new": new_visitors,
            "returning": max(0, visitors - new_visitors),
            "views_per_visitor": round(views / visitors, 1) if visitors else 0,
            "daily_average": round(sum(item["visitors"] for item in days) / len(days), 1) if days else 0,
            "peak": {"date": peak["date"], "visitors": peak["visitors"]} if peak and peak["visitors"] else None,
            "applications": applications,
            "visitors_change": _change(visitors, previous_visitors),
            "views_change": _change(views, previous_views),
        },
        "days": days,
        "funnel": [
            {"key": "visited", "label": "Visited the site", "count": visitors},
            {"key": "posting", "label": "Opened a posting", "count": viewed_posting},
            {"key": "apply", "label": "Started an application", "count": started_apply},
        ],
        "pages": _pages(session, start, end),
        "postings": _postings(session, start, end),
        "sources": _grouped(session, start, end, SiteVisit.source, SOURCE_LABELS),
        "devices": _grouped(session, start, end, SiteVisit.device, DEVICE_LABELS),
    }


def _pages(session: Session, start: datetime, end: datetime) -> list[dict]:
    rows = session.execute(
        select(SiteVisit.path, func.count(), func.count(func.distinct(SiteVisit.visitor)))
        .where(SiteVisit.at >= start, SiteVisit.at < end, SiteVisit.kind == "page")
        .group_by(SiteVisit.path)
        .order_by(func.count().desc(), SiteVisit.path)
        .limit(TOP)
    ).all()
    return [{"key": path, "label": PAGE_LABELS.get(path, path), "views": views, "visitors": people} for path, views, people in rows]


def _postings(session: Session, start: datetime, end: datetime) -> list[dict]:
    views = func.count().filter(SiteVisit.kind == "posting")
    rows = session.execute(
        select(
            SiteVisit.path,
            views,
            func.count(func.distinct(SiteVisit.visitor)).filter(SiteVisit.kind == "posting"),
            func.count(func.distinct(SiteVisit.visitor)).filter(SiteVisit.kind == "apply"),
        )
        .where(SiteVisit.at >= start, SiteVisit.at < end, SiteVisit.kind.in_(("posting", "apply")))
        .group_by(SiteVisit.path)
        .order_by(views.desc(), SiteVisit.path)
        .limit(TOP)
    ).all()
    titles = dict(session.execute(select(Job.requisition_code, Job.title).where(Job.requisition_code.in_([row[0] for row in rows]))).all())
    return [
        {"code": code, "title": titles.get(code) or "", "views": count, "visitors": people, "applying": applying}
        for code, count, people, applying in rows
        if count
    ]


def _grouped(session: Session, start: datetime, end: datetime, column, labels: dict[str, str]) -> list[dict]:
    rows = session.execute(
        select(column, func.count(func.distinct(SiteVisit.visitor)))
        .where(SiteVisit.at >= start, SiteVisit.at < end)
        .group_by(column)
        .order_by(func.count(func.distinct(SiteVisit.visitor)).desc(), column)
        .limit(TOP)
    ).all()
    return [{"key": key, "label": labels.get(key, key), "count": count} for key, count in rows]


def _window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        _fail(400, "Send the start and end with a timezone.")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if end <= start:
        _fail(400, "The end of the range has to be after the start.")
    if end - start > timedelta(days=RANGE_CAP_DAYS):
        _fail(400, "Choose a range of a year or less. The all-time total still counts every visitor.")
    return start, end


@router.get("/visitors")
def visitors(start: datetime, end: datetime, tz: str = "UTC", session: Session = Depends(admin_only("visitors"))):
    _zone(tz)
    start, end = _window(start, end)
    return summary(session, start, end, tz)
