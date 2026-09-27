"""Detail-page parser. Title and city stay on the listing line."""

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re

from app.core.clearance import map_clearance_text

# Exact heading text only. "Mandatory Skills & Qualifications" is not one of these,
# so /jobs/2008 is kept whole and flagged needs_review.
_HEADINGS = {
    "job description": "description",
    "mandatory skills": "must",
    "required skills": "must",
    "qualifications": "must",
    "desired skills": "nice",
    "preferred skills": "nice",
    "optional skills": "nice",
    "responsibilities": "description",
}

_NAV = {
    "home",
    "about us",
    "clients",
    "contact us",
    "benefits",
    "capability",
    "more",
    "morehome",
    "apply",
    "janus soft inc.",
    "page details",
    "page updated",
    "report abuse",
    "embedded files",
    "search this site",
}

_GLUED_DESCRIPTION = re.compile(r"(?i)^job description\b[:\s-]+(.+)$")
_CLEARANCE_ITEM = re.compile(r"(?i)^(security\s+)?clearance\s*:")
_MUST_HOLD = re.compile(r"(?i)must hold an active\b")
_WHY_JOIN = re.compile(r"(?i)^why should you join\b")

_CLEARANCE_RANK = {"unknown": 0, "none": 1, "public_trust": 2, "secret": 3, "ts": 4, "ts_sci": 5}
_POLY_RANK = {"unknown": 0, "none": 1, "ci": 2, "full_scope": 3}


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.capture: str | None = None
        self.buf: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"p", "li", "h1", "h2", "h3", "h4"} and self.capture is None:
            self.capture = tag
            self.buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
            return
        if self.capture == tag:
            text = unescape(re.sub(r"\s+", " ", "".join(self.buf))).strip()
            if text:
                self.blocks.append(text)
            self.capture = None
            self.buf = []

    def handle_data(self, data: str) -> None:
        if self.skip or self.capture is None:
            return
        self.buf.append(data)


def extract_blocks(html: str) -> list[str]:
    parser = _Blocks()
    parser.feed(html)
    content: list[str] = []
    started = False
    for block in parser.blocks:
        low = block.lower().strip()
        if "google sites" in low or low == "report abuse":
            if started:
                break
            continue
        if low in _NAV:
            continue
        started = True
        if _WHY_JOIN.match(block):
            break
        content.append(block)
    return content


def _heading_kind(text: str) -> str | None:
    key = text.lower().strip().rstrip(":").strip()
    return _HEADINGS.get(key)


def _is_clearance_item(text: str) -> bool:
    return bool(_CLEARANCE_ITEM.match(text) or _MUST_HOLD.search(text))


def _is_title_line(text: str) -> bool:
    if len(text) > 90:
        return False
    if text.endswith("."):
        return False
    return True


@dataclass
class DetailParse:
    description_text: str
    must_have_quotes: list[str] = field(default_factory=list)
    nice_to_have_quotes: list[str] = field(default_factory=list)
    clearance_required: str | None = None
    polygraph_required: str | None = None
    needs_review: bool = False
    clearance_quote: str | None = None


def _prefer(current: str | None, new: str | None, rank: dict[str, int]) -> str | None:
    if new is None:
        return current
    if current is None:
        return new
    if rank.get(new, -1) >= rank.get(current, -1):
        return new
    return current


def _apply_clearance(parsed: DetailParse, snippet: str) -> None:
    clearance, poly = map_clearance_text(snippet)
    parsed.clearance_required = _prefer(parsed.clearance_required, clearance, _CLEARANCE_RANK)
    parsed.polygraph_required = _prefer(parsed.polygraph_required, poly, _POLY_RANK)
    if parsed.clearance_quote is None and (clearance or poly or _is_clearance_item(snippet)):
        parsed.clearance_quote = snippet


def parse_detail_html(html: str) -> DetailParse:
    blocks = extract_blocks(html)
    parsed = DetailParse(description_text="")
    recognized = False
    section = "preamble"
    description_parts: list[str] = []

    for block in blocks:
        kind = _heading_kind(block)
        if kind:
            section = kind
            recognized = True
            continue
        glued = _GLUED_DESCRIPTION.match(block)
        if glued:
            section = "description"
            recognized = True
            prose = glued.group(1).strip()
            if prose:
                description_parts.append(prose)
            continue
        if section in {"preamble", "description"}:
            if section == "preamble" and _is_title_line(block):
                continue
            description_parts.append(block)
        elif section == "must":
            if _is_clearance_item(block):
                _apply_clearance(parsed, block)
            else:
                parsed.must_have_quotes.append(block)
        elif section == "nice":
            if _is_clearance_item(block):
                _apply_clearance(parsed, block)
            else:
                parsed.nice_to_have_quotes.append(block)

    if not recognized:
        parsed.needs_review = True
        parsed.must_have_quotes = []
        parsed.nice_to_have_quotes = []
        parsed.description_text = "\n\n".join(blocks).strip()
        for block in blocks:
            if _is_clearance_item(block):
                _apply_clearance(parsed, block)
        return parsed

    parsed.description_text = "\n\n".join(description_parts).strip()
    if not parsed.description_text:
        # Headings exist but the page has no prose before the skill lists.
        fallback = parsed.must_have_quotes + parsed.nice_to_have_quotes
        parsed.description_text = "\n\n".join(fallback).strip()
        parsed.needs_review = True
    return parsed
