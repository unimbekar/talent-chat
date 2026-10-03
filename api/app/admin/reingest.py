"""Refresh every candidate from the résumé folder. One row per person."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.admin.candidate_repository import delete_candidate
from app.admin.folder_ingest import scan_resumes
from app.admin.routes import _TextOnlyLLM, _store_resume
from app.config import get_settings
from app.core.extract import ExtractError, extract_text
from app.core.labor import labor_categories
from app.db import admin_session
from app.models import Candidate


_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _sibling_email(folder: Path, item) -> str | None:
    domain = get_settings().company_email_domain.strip().lower().lstrip("@")
    for relative in item.older:
        path = folder / relative
        text = _read_resume(path)
        for email in _EMAIL.findall(text):
            if not domain or not email.lower().endswith(f"@{domain}"):
                return email
    return None


def _read_resume(path: Path) -> str:
    if path.suffix.lower() not in {".pdf", ".doc", ".docx", ".txt"}:
        return ""
    try:
        return extract_text(path.name, path.read_bytes())
    except (ExtractError, OSError):
        return ""


def _sibling_categories(folder: Path, item) -> list[str]:
    """Roles named by the person's other résumés, such as a separate AI résumé."""
    found: list[str] = []
    for relative in item.older:
        path = folder / relative
        if path.suffix.lower() not in {".pdf", ".doc", ".docx", ".txt"}:
            continue
        text = _read_resume(path)
        for label in labor_categories(path.name, text):
            if label not in found:
                found.append(label)
    return found


def reingest_all(root: Path | None = None) -> dict:
    folder = root or Path(get_settings().resume_folder)
    scan = scan_resumes(folder)
    kept: set[str] = set()
    imported = 0
    refreshed = 0
    failed: list[str] = []
    for item in scan.chosen:
        data = item.path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        extras = _sibling_categories(folder, item)
        hint = _sibling_email(folder, item)
        db = admin_session()
        try:
            result = _store_resume(
                db,
                item.path.name,
                data,
                _TextOnlyLLM(),
                refresh=True,
                extra_categories=extras,
                email_hint=hint,
            )
            kept.add(digest)
            if result.get("already_ingested"):
                refreshed += 1
            else:
                imported += 1
        except HTTPException as exc:
            failed.append(f"{item.path.name}: {exc.detail}")
        except Exception as exc:
            failed.append(f"{item.path.name}: {exc}")
        finally:
            db.close()

    removed = 0
    db = admin_session()
    try:
        rows = db.scalars(select(Candidate)).all()
        for row in rows:
            if row.file_sha256 in kept or row.status == "confirmed":
                continue
            delete_candidate(db, row)
            removed += 1
        groups: dict[str, list[Candidate]] = defaultdict(list)
        for row in db.scalars(select(Candidate)).all():
            if row.full_name:
                groups[row.full_name.lower()].append(row)
        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda row: (row.file_sha256 in kept, len(row.titles or []), bool(row.email)), reverse=True)
            for extra in group[1:]:
                if extra.status == "confirmed":
                    continue
                delete_candidate(db, extra)
                removed += 1
        db.commit()
        on_file = len(db.scalars(select(Candidate.id)).all())
    finally:
        db.close()
    return {
        "people": len(scan.chosen),
        "older": scan.older,
        "ignored": scan.ignored,
        "imported": imported,
        "refreshed": refreshed,
        "failed": failed,
        "removed_stale": removed,
        "on_file": on_file,
    }


if __name__ == "__main__":
    outcome = reingest_all()
    print(
        f"People: {outcome['people']}\n"
        f"Imported: {outcome['imported']}\n"
        f"Refreshed: {outcome['refreshed']}\n"
        f"Removed stale: {outcome['removed_stale']}\n"
        f"On file: {outcome['on_file']}\n"
        f"Could not read: {len(outcome['failed'])}"
    )
    for line in outcome["failed"]:
        print(f"  {line}")
