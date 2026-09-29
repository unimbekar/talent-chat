"""Pick the latest résumé for each person in a folder tree.

A person folder such as ``ArpanSoni`` keeps one file. A pile such as ``Non-FSP``
keeps one file per person named in the filenames. Offer letters, invoices, and
legacy ``.doc`` files are left out.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import threading

_RESUME_EXT = {".pdf": 3, ".docx": 2, ".txt": 1}
_SKIP_DIR = {
    "images",
    "image",
    "invoices",
    "invoice",
    "receipts",
    "receipt",
    "1099",
    "offerletter",
    "offers",
    "briefing",
    "taxes",
    "tax",
    "thumbs",
}
_SKIP_WORD = {
    "offer",
    "invoice",
    "receipt",
    "consent",
    "termination",
    "departure",
    "noncompete",
    "compete",
    "census",
    "letter",
    "intent",
    "nda",
    "briefing",
    "timesheet",
    "paystub",
    "template",
    "thumbnail",
    "thumbs",
    "form",
    "sf86",
    "w4",
    "lawsuit",
    "defamation",
    "continuation",
    "deposit",
    "w2",
    "i9",
}
_ROLE = {
    "developer",
    "engineer",
    "manager",
    "architect",
    "java",
    "software",
    "security",
    "cyber",
    "cybersecurity",
    "program",
    "leader",
    "analyst",
    "tester",
    "data",
    "scientist",
    "senior",
    "junior",
    "level",
    "fsp",
    "it",
    "cv",
    "phd",
    "resume",
    "curriculum",
    "vitae",
    "clearance",
    "latest",
    "signed",
    "final",
    "updated",
    "professional",
    "janus",
    "soft",
    "janussoft",
    "python",
    "aws",
    "devops",
    "network",
    "admin",
    "administrator",
    "consultant",
    "specialist",
    "technician",
    "support",
    "stack",
    "web",
    "qa",
    "scrum",
    "master",
    "owner",
    "product",
    "project",
    "technical",
    "tech",
    "lead",
    "principal",
    "staff",
    "oct",
    "nov",
    "dec",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "info",
    "profile",
    "candidate",
    "etl",
    "dba",
    "sql",
    "sap",
    "sme",
    "pmp",
}
_MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ChosenResume:
    key: str
    label: str
    path: Path
    modified: datetime
    older: tuple[str, ...]


@dataclass(frozen=True)
class FolderScan:
    chosen: tuple[ChosenResume, ...]
    ignored: int
    older: int


def person_key(label: str) -> str:
    tokens = _name_tokens(label)
    if len(tokens) >= 2:
        return tokens[0] + tokens[-1]
    if len(tokens) == 1:
        return tokens[0]
    return ""


def person_label(filename: str) -> str | None:
    """A readable name taken from the file, such as Kate Dribki."""
    tokens = _name_tokens(Path(filename).stem)
    if len(tokens) >= 2:
        shown = tokens if len(tokens) <= 3 else [tokens[0], tokens[-1]]
        return " ".join(part.capitalize() for part in shown)
    if len(tokens) == 1 and len(tokens[0]) >= 4:
        return tokens[0].capitalize()
    return None


_JUNK_NAMES = {
    "big ideas simple solutions",
    "career summary",
    "professional summary",
    "continuation sheet",
    "device automation system",
    "resume",
    "curriculum vitae",
}


def preferred_name(stored: str | None, filename: str | None) -> str | None:
    """Use the filename when the résumé text yielded a slogan, a city, or a title."""
    label = person_label(filename or "")
    text = (stored or "").strip()
    if not text or text.lower() in _JUNK_NAMES or "clearance" in text.lower():
        return label or text or None
    if label is None:
        return text
    stored_tokens = set(re.findall(r"[a-z]+", text.lower()))
    if stored_tokens.isdisjoint(set(label.lower().split())):
        return label
    return text


def filename_ignored(name: str) -> bool:
    if name.startswith("~$") or name.startswith(".") or name.startswith("_"):
        return True
    if Path(name).suffix.lower() not in _RESUME_EXT:
        return True
    if _skip_words(name) & _SKIP_WORD:
        return True
    compact = _compact(name)
    if "noncompete" in compact or "noncomplete" in compact:
        return True
    return bool(re.search(r"salary|defamation|sf\s*86", name, re.I))


def _name_tokens(label: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)
    text = text.lower().replace("janussoft", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens: list[str] = []
    for token in text.split():
        token = re.sub(r"(19|20)\d{2}", "", token)
        token = re.sub(r"resume|clearance|curriculum|vitae", "", token)
        token = re.sub(r"^\d+", "", token)
        if not token or token.isdigit() or len(token) == 1:
            continue
        if token in _ROLE or token in _SKIP_WORD:
            continue
        if token not in tokens:
            tokens.append(token)
    if len(tokens) > 1:
        trimmed = [token for token in tokens if token not in {"uue", "sw", "eh", "aw", "cd", "nmi", "afs"}]
        if trimmed:
            tokens = trimmed
    return tokens


def _skip_words(name: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return set(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def scan_resumes(root: Path) -> FolderScan:
    groups: dict[str, list[Path]] = {}
    ignored = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _ignore(path, root):
            ignored += 1
            continue
        groups.setdefault(_group_key(path, root), []).append(path)
    chosen: list[ChosenResume] = []
    older = 0
    for key, paths in groups.items():
        ranked = sorted(paths, key=lambda item: (item.stat().st_mtime, _RESUME_EXT.get(item.suffix.lower(), 0)), reverse=True)
        best = ranked[0]
        rest = ranked[1:]
        older += len(rest)
        stamp = datetime.fromtimestamp(best.stat().st_mtime, timezone.utc)
        chosen.append(
            ChosenResume(
                key=key,
                label=_label(paths, root, best),
                path=best,
                modified=stamp,
                older=tuple(str(path.relative_to(root)) for path in rest),
            )
        )
    chosen.sort(key=lambda item: item.label.lower())
    return FolderScan(chosen=tuple(chosen), ignored=ignored, older=older)


def _ignore(path: Path, root: Path) -> bool:
    name = path.name
    if name.startswith("~$") or name.startswith(".") or name.startswith("_"):
        return True
    if path.suffix.lower() not in _RESUME_EXT:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size < 200 or size > _MAX_BYTES:
        return True
    rel = path.relative_to(root)
    for part in rel.parts[:-1]:
        if _compact(part) in _SKIP_DIR:
            return True
    return filename_ignored(name)


def _group_key(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    file_key = person_key(path.stem)
    if len(rel.parts) == 1:
        return file_key or _compact(path.stem) or path.name.lower()
    folder_key = person_key(rel.parts[0])
    if not file_key:
        return folder_key or _compact(rel.parts[0]) or rel.parts[0].lower()
    if folder_key and _same_person(file_key, folder_key):
        return folder_key
    return file_key


def _same_person(left: str, right: str) -> bool:
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) >= 3 and long.startswith(short)


def _label(paths: list[Path], root: Path, best: Path) -> str:
    for path in paths:
        rel = path.relative_to(root)
        if len(rel.parts) > 1 and _same_person(person_key(best.stem) or person_key(rel.parts[0]), person_key(rel.parts[0]) or person_key(best.stem)):
            return rel.parts[0]
    return best.stem


def _prefer_named_resume(path: Path) -> int:
    compact = _compact(path.stem)
    if "resume" in compact or compact.endswith("cv") or "curriculumvitae" in compact:
        return 1
    return 0


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


_LOCK = threading.Lock()
_STATE: dict = {
    "running": False,
    "finished": False,
    "total": 0,
    "done": 0,
    "imported": 0,
    "already": 0,
    "failed": 0,
    "older": 0,
    "ignored": 0,
    "current": "",
    "errors": [],
}


def ingest_status() -> dict:
    with _LOCK:
        return dict(_STATE)


def start_ingest(root: Path, save) -> bool:
    """Start a background import. save(path) returns 'imported' or 'already', or raises."""
    with _LOCK:
        if _STATE["running"]:
            return False
        _STATE.update(
            running=True,
            finished=False,
            total=0,
            done=0,
            imported=0,
            already=0,
            failed=0,
            current="Reading the folder",
            errors=[],
        )

    def _run() -> None:
        try:
            scan = scan_resumes(root)
            with _LOCK:
                _STATE["total"] = len(scan.chosen)
                _STATE["older"] = scan.older
                _STATE["ignored"] = scan.ignored
            for item in scan.chosen:
                with _LOCK:
                    _STATE["current"] = item.label
                outcome = "failed"
                try:
                    outcome = save(item.path)
                except Exception as exc:
                    message = f"{item.path.name}: {exc}"
                    with _LOCK:
                        errors = list(_STATE["errors"])
                        errors.append(message)
                        _STATE["errors"] = errors[-8:]
                        _STATE["failed"] += 1
                        _STATE["done"] += 1
                    continue
                with _LOCK:
                    if outcome == "already":
                        _STATE["already"] += 1
                    else:
                        _STATE["imported"] += 1
                    _STATE["done"] += 1
        finally:
            with _LOCK:
                _STATE["running"] = False
                _STATE["finished"] = True
                _STATE["current"] = ""

    threading.Thread(target=_run, name="folder-ingest", daemon=True).start()
    return True
