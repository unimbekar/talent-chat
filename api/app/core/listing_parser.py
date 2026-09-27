"""Listing-page parser. The listing line is authoritative for title and city."""

from dataclasses import dataclass
import re
from html import unescape

from app.core.locations import Location, load_locations, match_location_segment

_CODE = re.compile(r"^([A-Z][0-9]{3,5})(?:\s*-\s*|\s+)(.*)$")
_STATUS_PREFIX = re.compile(r"(?i)^(proposal|upcoming)\s*-\s*")
_SEPARATOR = re.compile(r"^[-\s]+$")
_PROGRAM = re.compile(r"^[A-Z]{2,6}$")
_SITE_ID = re.compile(r"/jobs/(\d+)")


@dataclass
class ListingRow:
    requisition_code: str | None
    title: str | None
    location: str | None
    program_tag: str | None
    external_req: str | None
    status: str
    source_line: str
    site_job_id: str | None
    source_url: str | None
    needs_review: bool


def parse_listing_line(
    line: str,
    href: str | None = None,
    locations: tuple[Location, ...] | None = None,
) -> ListingRow | None:
    raw = re.sub(r"\s+", " ", line).strip()
    if not raw or _SEPARATOR.fullmatch(raw):
        return None
    locations = locations if locations is not None else load_locations()
    status = "open"
    work = raw
    prefix = _STATUS_PREFIX.match(work)
    if prefix:
        status = prefix.group(1).lower()
        work = work[prefix.end() :]
    if re.search(r"(?i)upcoming", raw):
        status = "upcoming"

    code_match = _CODE.match(work.strip())
    needs_review = False
    if not code_match:
        return ListingRow(
            requisition_code=None,
            title=work.strip() or None,
            location=None,
            program_tag=None,
            external_req=None,
            status=status,
            source_line=raw,
            site_job_id=None,
            source_url=href,
            needs_review=True,
        )

    code = code_match.group(1)
    rest = code_match.group(2).strip()
    parens = [p.strip() for p in re.findall(r"\(([^)]*)\)", rest)]
    external = "; ".join(parens) if parens else None
    rest = re.sub(r"\([^)]*\)", " ", rest)
    rest = re.sub(r"\s*-\s*", "\x1f", rest)
    parts = [p.strip() for p in rest.split("\x1f") if p.strip()]

    city = None
    city_idx = None
    for i in range(len(parts) - 1, -1, -1):
        matched = match_location_segment(parts[i], locations)
        if matched:
            city = matched
            city_idx = i
            break

    program = None
    title_parts: list[str] = []
    for i, part in enumerate(parts):
        if i == city_idx:
            continue
        if _PROGRAM.fullmatch(part) and match_location_segment(part, locations) is None:
            program = part
            continue
        title_parts.append(part)
    title = " - ".join(title_parts).strip() or None
    if city is None or title is None:
        needs_review = True

    site_job_id = None
    if href:
        found = _SITE_ID.search(href)
        if found:
            site_job_id = found.group(1)
    if site_job_id is None:
        digits = re.search(r"(\d+)", code)
        site_job_id = digits.group(1) if digits else None
        needs_review = True

    return ListingRow(
        requisition_code=code,
        title=title,
        location=city,
        program_tag=program,
        external_req=external,
        status=status,
        source_line=raw,
        site_job_id=site_job_id,
        source_url=href,
        needs_review=needs_review,
    )


def _anchor_pairs(html: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
        href, inner = match.group(1), match.group(2)
        text = unescape(re.sub(r"<[^>]+>", " ", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pairs.append((text, href))
    return pairs


def _visible_lines(html: str) -> list[str]:
    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.I)
    stripped = re.sub(r"</(p|h1|h2|h3|li|div|tr)>", r"</\1>\n", stripped, flags=re.I)
    stripped = re.sub(r"<br\s*/?>", "\n", stripped, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", stripped))
    lines = []
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        if clean:
            lines.append(clean)
    return lines


def parse_listing_html(html: str, locations: tuple[Location, ...] | None = None) -> list[ListingRow]:
    """Parse a careers listing page. Linked lines win over a duplicate plain-text line."""
    locations = locations if locations is not None else load_locations()
    rows: list[ListingRow] = []
    seen: set[str] = set()
    for text, href in _anchor_pairs(html):
        row = parse_listing_line(text, href=href, locations=locations)
        if row is None or not row.requisition_code or row.requisition_code in seen:
            continue
        seen.add(row.requisition_code)
        rows.append(row)
    for line in _visible_lines(html):
        row = parse_listing_line(line, href=None, locations=locations)
        if row is None or not row.requisition_code or row.requisition_code in seen:
            continue
        seen.add(row.requisition_code)
        rows.append(row)
    return rows
