"""Count careers-site visits without storing anything that identifies a person.

The browser keeps a random visitor id in local storage and sends one beacon per page,
posting, or apply view. No IP address, user agent, or full referrer URL is stored:
only the visitor id, what was viewed, a short traffic source, and the device type.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import re
import threading
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.client_ip import client_ip
from app.db import admin_session
from app.models import Job, SiteVisit

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("talent")

KINDS = ("page", "posting", "apply")
HOURLY_LIMIT = 240
# A reload or a double-mounted page sends the same beacon twice within moments; count it once.
REPEAT_WINDOW = timedelta(seconds=10)

_PAGE = re.compile(r"^/jobs(?:/[a-z0-9-]{1,40}){0,2}$")
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
_CAMPAIGN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
_BOT = re.compile(
    r"bot|crawl|spider|slurp|preview|headless|lighthouse|pingdom|uptime|monitor|scanner|curl|wget|python-|httpclient"
    r"|java/|go-http|okhttp|facebookexternalhit|embedly|whatsapp|skypeuripreview|bitlybot|vercel|playwright|puppeteer",
    re.IGNORECASE,
)
# Hosts that mean the same source, so the chart shows "LinkedIn" once, not five domains.
_SOURCES = (
    (re.compile(r"(^|\.)(mail\.google\.com|outlook\.(live|office|office365)\.com|mail\.yahoo\.com)$"), "email"),
    (re.compile(r"(^|\.)google\.[a-z.]+$"), "google"),
    (re.compile(r"(^|\.)bing\.com$"), "bing"),
    (re.compile(r"(^|\.)duckduckgo\.com$"), "duckduckgo"),
    (re.compile(r"(^|\.)(linkedin\.com|lnkd\.in)$"), "linkedin"),
    (re.compile(r"(^|\.)(facebook\.com|fb\.com|fb\.me)$"), "facebook"),
    (re.compile(r"(^|\.)(t\.co|x\.com|twitter\.com)$"), "x"),
    (re.compile(r"(^|\.)indeed\.[a-z.]+$"), "indeed"),
    (re.compile(r"(^|\.)glassdoor\.[a-z.]+$"), "glassdoor"),
    (re.compile(r"(^|\.)(clearancejobs\.com)$"), "clearancejobs"),
)

_LOCK = threading.Lock()
_HITS: dict[str, list[datetime]] = defaultdict(list)


class VisitIn(BaseModel):
    visitor: uuid.UUID
    kind: str = Field(pattern="^(page|posting|apply)$")
    path: str = Field(min_length=1, max_length=200)
    referrer: str | None = Field(default=None, max_length=1000)
    campaign: str | None = Field(default=None, max_length=80)


def reset_rate_limit() -> None:
    with _LOCK:
        _HITS.clear()


def _limited(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    window = now - timedelta(hours=1)
    with _LOCK:
        recent = [stamp for stamp in _HITS[ip] if stamp > window]
        if len(recent) >= HOURLY_LIMIT:
            _HITS[ip] = recent
            return True
        recent.append(now)
        _HITS[ip] = recent
        return False


def is_bot(user_agent: str | None) -> bool:
    agent = (user_agent or "").strip()
    return not agent or bool(_BOT.search(agent))


def device_of(user_agent: str | None) -> str:
    agent = (user_agent or "").lower()
    if "ipad" in agent or "tablet" in agent or ("android" in agent and "mobile" not in agent):
        return "tablet"
    if "mobi" in agent or "iphone" in agent or "ipod" in agent or "android" in agent:
        return "mobile"
    return "desktop"


def normal_path(kind: str, path: str) -> str | None:
    """A page path such as /jobs/benefits, or a job code for posting and apply views."""
    text = path.strip()
    if kind == "page":
        text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower() or "/"
        return text if _PAGE.match(text) else None
    return text if _CODE.match(text) else None


def source_of(referrer: str | None, campaign: str | None, own_hosts: set[str]) -> str:
    """utm_source when the link carried one, else the referring site, else direct."""
    tag = (campaign or "").strip().lower()
    if _CAMPAIGN.match(tag):
        return tag
    raw = (referrer or "").strip()
    if not raw:
        return "direct"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "direct"
    host = parsed.hostname.lower().removeprefix("www.")
    if host in own_hosts:
        return "direct"
    for pattern, name in _SOURCES:
        if pattern.search(host):
            return name
    return host[:80]


def _own_hosts(request: Request) -> set[str]:
    hosts = set()
    for header in ("host", "x-forwarded-host"):
        for value in (request.headers.get(header) or "").split(","):
            name = value.strip().split(":", 1)[0].lower().removeprefix("www.")
            if name:
                hosts.add(name)
    return hosts


def record_visit(body: VisitIn, *, user_agent: str | None, own_hosts: set[str]) -> bool:
    """Save one view. False when it was dropped: a bot, a path that is not ours, or an unknown job."""
    if is_bot(user_agent):
        return False
    path = normal_path(body.kind, body.path)
    if path is None:
        return False
    session = admin_session()
    try:
        if body.kind != "page" and session.scalar(select(Job.id).where(Job.requisition_code == path)) is None:
            return False
        repeat = session.scalar(
            select(SiteVisit.id)
            .where(
                SiteVisit.visitor == body.visitor,
                SiteVisit.kind == body.kind,
                SiteVisit.path == path,
                SiteVisit.at > func.now() - REPEAT_WINDOW,
            )
            .limit(1)
        )
        if repeat is not None:
            return False
        session.add(
            SiteVisit(
                visitor=body.visitor,
                kind=body.kind,
                path=path,
                source=source_of(body.referrer, body.campaign, own_hosts),
                device=device_of(user_agent),
            )
        )
        session.commit()
        return True
    finally:
        session.close()


@router.post("/visit", status_code=204)
def visit(body: VisitIn, request: Request):
    """Always 204, so the careers page never waits on or reacts to analytics."""
    if _limited(client_ip(request, get_settings())):
        return Response(status_code=204)
    try:
        record_visit(body, user_agent=request.headers.get("user-agent"), own_hosts=_own_hosts(request))
    except SQLAlchemyError:
        logger.exception("visit was not recorded")
    return Response(status_code=204)
