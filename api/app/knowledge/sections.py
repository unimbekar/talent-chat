"""Split a document into titled sections.

A question about dental coverage should be answered from the whole "Medical, dental, and vision"
section, table included, not from a 900-character window that cuts the table in half and carries
the page header. Headings are found in this order, and the first kind a document uses at least
twice wins:

1. Numbered markers such as "01 · Care", followed by the section title on the next line.
2. Markdown headings ("## Retirement").
3. ALL CAPS lines ("HEALTH INSURANCE").
4. Short title lines that sit after a blank line and before a paragraph or a list.

A document with none of these is split by length, as before.
"""

from collections import Counter
from dataclasses import dataclass, field
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_VERSION = 3
SECTION_LIMIT = 1600

_PAGE = re.compile(r"(?i)(?:^|\s)page\s+\d+(?:\s+of\s+\d+)?\s*$")
_KICKER = re.compile(r"^\d{1,2}\s*[·•.)–—-]\s*[A-Za-z][\w &/'’-]{0,38}$")
_MARKDOWN = re.compile(r"^#{1,4}\s+(\S.{0,90})$")
_BULLET = re.compile(r"^(?:[-–—•*▪●◦]|\d{1,2}[.)])\s+")
_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120, separators=["\n\n", "\n", ". ", " "])


@dataclass
class Section:
    heading: str | None
    kicker: str | None = None
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.lines).strip()


def is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line or ""))


def strip_bullet(line: str) -> str:
    return _BULLET.sub("", line or "").strip()


def is_table_row(line: str) -> bool:
    return (line or "").count(" | ") >= 1


def clean_lines(text: str) -> list[str]:
    """Normalize spacing and drop page chrome: page numbers and the header repeated on every page."""
    raw = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in (text or "").replace("\r", "").split("\n")]
    counts = Counter(line.lower() for line in raw if line)
    opening = {line.lower() for line in raw[:12] if line}
    repeated = {
        index
        for index, line in enumerate(raw)
        if line and len(line) < 120 and counts[line.lower()] >= 2 and line.lower() in opening and not is_table_row(line)
    }

    def chrome(index: int) -> bool:
        # A page header repeats as a block (company, title, address). A lone repeated phrase is content.
        if index not in repeated:
            return False
        neighbors = [step for step in (index - 1, index + 1) if 0 <= step < len(raw)]
        return any(step in repeated and raw[step].lower() != raw[index].lower() for step in neighbors)

    kept: list[str] = []
    for index, line in enumerate(raw):
        if line and len(line) < 120 and _PAGE.search(line):
            continue
        if chrome(index):
            continue
        if not line and (not kept or not kept[-1]):
            continue
        if line and kept and kept[-1] and line[0].islower() and not is_table_row(kept[-1]):
            # A PDF wraps a sentence onto the next line. The continuation starts in lower case.
            kept[-1] = f"{kept[-1]} {line}"
            continue
        kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return kept


def _is_caps(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    return 4 <= len(letters) and line.upper() == line and len(line) <= 60 and not is_table_row(line)


def _is_title(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line or len(line) > 70 or is_bullet(line) or is_table_row(line):
        return False
    if re.search(r"[.,;!?]$", line) or not line[0].isupper() or len(line.split()) > 9:
        return False
    if sum(char.isalpha() for char in line) < 3:
        return False
    before = lines[index - 1] if index > 0 else ""
    after = next((item for item in lines[index + 1 :] if item), "")
    return not before and bool(after) and (len(after) >= 40 or is_bullet(after) or is_table_row(after))


def _starts(lines: list[str]) -> tuple[str, list[int]]:
    kickers = [index for index, line in enumerate(lines) if _KICKER.match(line)]
    if len(kickers) >= 2:
        return "kicker", kickers
    marks = [index for index, line in enumerate(lines) if _MARKDOWN.match(line)]
    if len(marks) >= 2:
        return "markdown", marks
    caps = [index for index, line in enumerate(lines) if _is_caps(line)]
    if len(caps) >= 2:
        return "caps", caps
    titles = [index for index in range(len(lines)) if _is_title(lines, index)]
    if len(titles) >= 2:
        return "title", titles
    return "none", []


def split_sections(text: str) -> list[Section]:
    lines = clean_lines(text)
    kind, starts = _starts(lines)
    if not starts:
        body = [line for line in lines if line]
        return [Section(heading=None, lines=body)] if body else []
    sections: list[Section] = []
    preamble = [line for line in lines[: starts[0]] if line]
    if sum(len(line) for line in preamble) >= 40:
        sections.append(Section(heading=None, lines=preamble))
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = lines[start:end]
        kicker = None
        if kind == "kicker":
            kicker = re.sub(r"\s+", " ", block[0])
            rest = block[1:]
            title_at = next((index for index, line in enumerate(rest) if line), None)
            heading = rest[title_at] if title_at is not None and len(rest[title_at]) <= 90 else kicker
            body = rest[title_at + 1 :] if title_at is not None and heading != kicker else rest
        elif kind == "markdown":
            heading = _MARKDOWN.match(block[0]).group(1).strip()  # type: ignore[union-attr]
            body = block[1:]
        elif kind == "caps":
            heading = block[0].title() if block[0].isupper() else block[0]
            body = block[1:]
        else:
            heading = block[0].rstrip(":")
            body = block[1:]
        sections.append(Section(heading=heading, kicker=kicker, lines=[line for line in body if line]))
    last = sections[-1] if sections else None
    if last and last.heading and len(last.lines) >= 3 and not is_bullet(last.lines[-1]) and not is_table_row(last.lines[-1]):
        if is_bullet(last.lines[-2]) or is_table_row(last.lines[-2]):
            # A closing note after the last list belongs to the whole document, not to the last section.
            sections.append(Section(heading=None, lines=[last.lines.pop()]))
    return [section for section in sections if section.lines or section.heading]


def chunk_sections(text: str) -> list[Section]:
    """Sections ready to store. A long section is split by length and each part keeps its heading."""
    sections = split_sections(text)
    if len(sections) <= 1 and (not sections or sections[0].heading is None):
        parts = [part.strip() for part in _SPLITTER.split_text("\n".join(clean_lines(text))) if part.strip()]
        return [Section(heading=None, lines=part.splitlines()) for part in parts]
    chunks: list[Section] = []
    for section in sections:
        if len(section.body) <= SECTION_LIMIT:
            chunks.append(section)
            continue
        for part in _SPLITTER.split_text(section.body):
            if part.strip():
                chunks.append(Section(heading=section.heading, kicker=section.kicker, lines=part.strip().splitlines()))
    return chunks
