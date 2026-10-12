"""Desk settings: theme, and the local model catalog.

Choosing a model writes it for the next process start. The running client stays
the one built when this process started.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.access import admin_only
from app.admin.routes import _audit
from app.config import get_settings
from app.desk_settings import (
    ASSISTANT_KEY,
    CHAT_KEY,
    THEME_KEY,
    add_model,
    catalog,
    read_theme,
    save_catalog,
    saved_assistant_model,
    saved_chat_model,
    valid_tag,
    with_running,
    write_setting,
)

router = APIRouter(prefix="/admin", tags=["settings"])


class SettingsIn(BaseModel):
    theme: str | None = None
    chat_model: str | None = None
    assistant_model: str | None = None


class ModelIn(BaseModel):
    tag: str = Field(min_length=1, max_length=80)
    label: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=200)


def _running(request: Request) -> tuple[str, str, str]:
    settings = get_settings()
    llm = getattr(request.app.state, "llm", None)
    running = getattr(llm, "model", None) or settings.llm_model
    assistant = getattr(request.app.state, "running_assistant_model", None) or running
    backend = settings.assistant_backend.strip() or settings.llm_backend
    return running, assistant, backend


def snapshot(request: Request, session: Session) -> dict:
    settings = get_settings()
    running, running_assistant, backend = _running(request)
    chat = saved_chat_model(session) or running
    assistant = saved_assistant_model(session) or chat
    return {
        "theme": read_theme(session),
        "models": with_running(session, running),
        "chat_model": chat,
        "assistant_model": assistant,
        "running_model": running,
        "running_assistant_model": running_assistant,
        "llm_backend": backend,
        "embedding_model": settings.embedding_model,
        "deploy_required": chat != running or assistant != running_assistant,
        "deploy_command": "docker compose up -d --build api",
    }


@router.get("/settings")
def get_settings_view(request: Request, session: Session = Depends(admin_only("settings"))):
    return snapshot(request, session)


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, session: Session = Depends(admin_only("settings"))):
    if body.theme is not None:
        if body.theme not in ("dark", "light"):
            raise HTTPException(status_code=422, detail="Theme is dark or light.")
        write_setting(session, THEME_KEY, body.theme, public=True)
        _audit(session, "settings", outcome=f"theme:{body.theme}")
    running, _assistant, _backend = _running(request)
    known = {row["tag"] for row in with_running(session, running)}
    if body.chat_model is not None:
        tag = body.chat_model.strip()
        if not valid_tag(tag) or tag not in known:
            raise HTTPException(status_code=400, detail="Choose a model from the catalog.")
        write_setting(session, CHAT_KEY, tag, public=False)
        _audit(session, "settings", outcome=f"chat_model:{tag}")
    if body.assistant_model is not None:
        tag = body.assistant_model.strip()
        if tag and (not valid_tag(tag) or tag not in known):
            raise HTTPException(status_code=400, detail="Choose a model from the catalog.")
        write_setting(session, ASSISTANT_KEY, tag, public=False)
        _audit(session, "settings", outcome=f"assistant_model:{tag or 'same'}")
    session.commit()
    return snapshot(request, session)


@router.post("/settings/models")
def create_model(body: ModelIn, request: Request, session: Session = Depends(admin_only("settings"))):
    try:
        row = add_model(session, body.tag, body.label, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(session, "settings", outcome=f"model_added:{row['tag']}")
    session.commit()
    return snapshot(request, session)


@router.delete("/settings/models")
def delete_model(tag: str, request: Request, session: Session = Depends(admin_only("settings"))):
    tag = tag.strip()
    running, running_assistant, _backend = _running(request)
    if tag == running or tag == running_assistant:
        raise HTTPException(status_code=409, detail="That model is running. Deploy a different model before removing it.")
    rows = [row for row in catalog(session) if row["tag"] != tag]
    if len(rows) == len(catalog(session)):
        raise HTTPException(status_code=404, detail="That model is not in the catalog.")
    save_catalog(session, rows)
    if saved_chat_model(session) == tag:
        write_setting(session, CHAT_KEY, running, public=False)
    if saved_assistant_model(session) == tag:
        write_setting(session, ASSISTANT_KEY, "", public=False)
    _audit(session, "settings", outcome=f"model_removed:{tag}")
    session.commit()
    return snapshot(request, session)
