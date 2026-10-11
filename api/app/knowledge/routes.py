"""Recruiter upload and edit for the knowledge base."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.auth import cookie_name, read_session
from app.db import get_admin_db
from app.knowledge.store import (
    KnowledgeError,
    create_document,
    delete_document,
    document_detail,
    list_documents,
    read_upload,
    update_document,
)

router = APIRouter(prefix="/admin/knowledge", tags=["knowledge"])


def _guard(request: Request, session: Session = Depends(get_admin_db)) -> Session:
    if read_session(session, request.cookies.get(cookie_name())) is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return session


def _fail(exc: KnowledgeError) -> None:
    raise HTTPException(status_code=exc.status, detail=exc.message) from exc


class KnowledgeEdit(BaseModel):
    title: str
    audience: str
    body: str | None = None


@router.get("")
def index(session: Session = Depends(_guard)):
    return {"documents": list_documents(session)}


@router.get("/{document_id}")
def read(document_id: uuid.UUID, session: Session = Depends(_guard)):
    try:
        return document_detail(session, document_id)
    except KnowledgeError as exc:
        _fail(exc)


@router.post("")
async def upload(
    request: Request,
    title: str = Form(""),
    audience: str = Form("public"),
    text: str = Form(""),
    file: UploadFile | None = File(None),
    session: Session = Depends(_guard),
):
    body = text
    source = "Pasted text"
    if file is not None and file.filename:
        data = await file.read()
        if data:
            try:
                body = read_upload(file.filename, data)
            except KnowledgeError as exc:
                _fail(exc)
            source = file.filename
    try:
        document = create_document(
            session,
            request.app.state.embedder,
            title=title,
            audience=audience,
            body=body,
            source_name=source,
        )
    except KnowledgeError as exc:
        _fail(exc)
    return document_detail(session, document.id)


@router.put("/{document_id}")
def edit(document_id: uuid.UUID, body: KnowledgeEdit, request: Request, session: Session = Depends(_guard)):
    try:
        document = update_document(
            session,
            request.app.state.embedder,
            document_id,
            title=body.title,
            audience=body.audience,
            body=body.body,
        )
    except KnowledgeError as exc:
        _fail(exc)
    return document_detail(session, document.id)


@router.delete("/{document_id}")
def remove(document_id: uuid.UUID, session: Session = Depends(_guard)):
    try:
        delete_document(session, document_id)
    except KnowledgeError as exc:
        _fail(exc)
    return {"ok": True}
