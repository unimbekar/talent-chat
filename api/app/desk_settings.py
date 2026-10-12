"""Desk preferences stored in the settings table.

Theme is public. Model names are not returned by the public config. The password
hash never lives here: the public database role can read this table.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Setting

THEME_KEY = "theme"
MODELS_KEY = "local_models"
CHAT_KEY = "llm_model"
ASSISTANT_KEY = "assistant_model"

THEMES = ("dark", "light")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
MAX_MODELS = 24


def _row(session: Session, key: str) -> Setting | None:
    return session.get(Setting, key)


def _value(session: Session, key: str) -> str:
    row = _row(session, key)
    return (row.value or "").strip() if row else ""


def write_setting(session: Session, key: str, value: str, public: bool) -> None:
    row = _row(session, key)
    if row is None:
        session.add(Setting(key=key, value=value, is_public=public))
    else:
        row.value = value
        row.is_public = public


def read_theme(session: Session) -> str:
    value = _value(session, THEME_KEY)
    return value if value in THEMES else "dark"


def valid_tag(tag: str) -> bool:
    if not TAG.fullmatch(tag):
        return False
    lowered = tag.lower()
    if "://" in tag or ".." in tag or lowered.startswith("http"):
        return False
    return True


def catalog(session: Session) -> list[dict]:
    raw = _value(session, MODELS_KEY)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        if not valid_tag(tag) or tag in seen:
            continue
        seen.add(tag)
        rows.append(
            {
                "tag": tag,
                "label": str(item.get("label") or tag)[:80],
                "note": str(item.get("note") or "")[:200],
                "added_at": str(item.get("added_at") or ""),
            }
        )
    return rows


def save_catalog(session: Session, rows: list[dict]) -> None:
    write_setting(session, MODELS_KEY, json.dumps(rows), public=False)


def with_running(session: Session, running: str) -> list[dict]:
    rows = catalog(session)
    if valid_tag(running) and not any(row["tag"] == running for row in rows):
        rows.insert(0, {"tag": running, "label": running, "note": "Started with the running process.", "added_at": ""})
    return rows


def saved_chat_model(session: Session) -> str:
    return _value(session, CHAT_KEY)


def saved_assistant_model(session: Session) -> str:
    return _value(session, ASSISTANT_KEY)


def resolved_chat_model(session: Session, fallback: str) -> str:
    return saved_chat_model(session) or fallback


def add_model(session: Session, tag: str, label: str, note: str) -> dict:
    tag = tag.strip()
    if not valid_tag(tag):
        raise ValueError("Use an Ollama tag such as qwen3.6:latest. Spaces and web addresses are not tags.")
    rows = catalog(session)
    if any(row["tag"] == tag for row in rows):
        raise ValueError("That model is already in the catalog.")
    if len(rows) >= MAX_MODELS:
        raise ValueError("The catalog is full. Remove a model before adding another.")
    row = {
        "tag": tag,
        "label": (label.strip() or tag)[:80],
        "note": note.strip()[:200],
        "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    rows.append(row)
    save_catalog(session, rows)
    return row
