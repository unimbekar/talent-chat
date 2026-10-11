"""Store uploaded documents as embedded chunks. Retrieval mixes word overlap with vectors."""

from datetime import datetime, timezone
import re
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embed import Embedder, cosine
from app.core.extract import ExtractError, extract_text
from app.models import KnowledgeChunk, KnowledgeDocument

AUDIENCES = ("public", "internal")
_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=900,
    chunk_overlap=120,
    separators=["\n\n", "\n", ". ", " "],
)
_STOP = {
    "what", "whats", "is", "the", "a", "an", "do", "does", "you", "your", "our", "of", "for",
    "and", "to", "how", "many", "can", "we", "are", "there", "any", "about", "me", "my", "in",
    "on", "with", "that", "this", "it", "or", "be", "if", "from",
}
_TOKEN = re.compile(r"[a-z0-9]+(?:\([a-z0-9]+\))?")


class KnowledgeError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def read_upload(filename: str, data: bytes) -> str:
    try:
        return extract_text(filename, data).strip()
    except ExtractError as exc:
        if filename.lower().endswith(".txt") and "Almost no text" in exc.message:
            text = data.decode("utf-8", errors="replace").strip()
            if len(text) >= 40:
                return text
        raise KnowledgeError(400, exc.message) from exc


def _clean_title(title: str) -> str:
    text = " ".join((title or "").split())
    if len(text) < 2 or len(text) > 200:
        raise KnowledgeError(400, "Enter a title of 2 to 200 characters.")
    return text


def _clean_audience(audience: str) -> str:
    value = (audience or "").strip().lower()
    if value not in AUDIENCES:
        raise KnowledgeError(400, "Choose careers visitors or internal.")
    return value


def _clean_body(body: str) -> str:
    text = (body or "").strip()
    if len(text) < 40:
        raise KnowledgeError(400, "The document needs at least a short paragraph.")
    if len(text) > 200_000:
        raise KnowledgeError(400, "That document is too long to store.")
    return text


def _terms(text: str) -> set[str]:
    folded = text.lower().replace("401(k)", "401k").replace("401 (k)", "401k")
    return {token for token in _TOKEN.findall(folded) if token not in _STOP and len(token) > 1}


def split_text(body: str) -> list[str]:
    parts = [part.strip() for part in _SPLITTER.split_text(body) if part.strip()]
    return parts or [body.strip()]


def _write_chunks(session: Session, document: KnowledgeDocument, embedder: Embedder) -> None:
    document.chunks.clear()
    session.flush()
    parts = split_text(document.body)
    vectors = embedder.embed_documents(parts)
    for index, (part, vector) in enumerate(zip(parts, vectors)):
        document.chunks.append(KnowledgeChunk(ord=index, text=part, embedding=vector))


def create_document(
    session: Session,
    embedder: Embedder,
    *,
    title: str,
    audience: str,
    body: str,
    source_name: str,
) -> KnowledgeDocument:
    document = KnowledgeDocument(
        title=_clean_title(title),
        audience=_clean_audience(audience),
        source_name=(source_name or "Pasted text")[:200],
        body=_clean_body(body),
    )
    session.add(document)
    _write_chunks(session, document, embedder)
    session.commit()
    session.refresh(document)
    return document


def update_document(
    session: Session,
    embedder: Embedder,
    document_id: uuid.UUID,
    *,
    title: str,
    audience: str,
    body: str | None,
) -> KnowledgeDocument:
    document = session.get(KnowledgeDocument, document_id)
    if document is None:
        raise KnowledgeError(404, "That document was not found.")
    document.title = _clean_title(title)
    document.audience = _clean_audience(audience)
    document.updated_at = datetime.now(timezone.utc)
    if body is not None:
        document.body = _clean_body(body)
        _write_chunks(session, document, embedder)
    session.commit()
    session.refresh(document)
    return document


def delete_document(session: Session, document_id: uuid.UUID) -> None:
    document = session.get(KnowledgeDocument, document_id)
    if document is None:
        raise KnowledgeError(404, "That document was not found.")
    session.delete(document)
    session.commit()


def list_documents(session: Session) -> list[dict]:
    rows = session.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc())).all()
    return [_summary(row) for row in rows]


def document_detail(session: Session, document_id: uuid.UUID) -> dict:
    document = session.get(KnowledgeDocument, document_id)
    if document is None:
        raise KnowledgeError(404, "That document was not found.")
    payload = _summary(document)
    payload["body"] = document.body
    return payload


def _summary(document: KnowledgeDocument) -> dict:
    return {
        "id": str(document.id),
        "title": document.title,
        "audience": document.audience,
        "source_name": document.source_name,
        "chunks": len(document.chunks),
        "characters": len(document.body or ""),
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def search_passages(session: Session, embedder: Embedder, question: str, *, audience: str, limit: int = 4) -> list[dict]:
    rows = session.scalars(
        select(KnowledgeChunk)
        .join(KnowledgeDocument)
        .where(KnowledgeDocument.audience == audience)
    ).all()
    if not rows:
        return []
    query_vector = embedder.embed_query(question)
    asked = _terms(question)
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in rows:
        lexical = 0.0
        if asked:
            lexical = len(asked & _terms(chunk.text)) / len(asked)
        vector = cosine(list(chunk.embedding) if chunk.embedding is not None else None, query_vector)
        score = (0.55 * lexical) + (0.45 * max(vector, 0.0))
        if lexical >= 0.34 or vector >= 0.45:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen: list[dict] = []
    seen: set[uuid.UUID] = set()
    for score, chunk in scored:
        if chunk.document_id in seen:
            continue
        seen.add(chunk.document_id)
        chosen.append(
            {
                "title": chunk.document.title,
                "excerpt": chunk.text.strip()[:500],
                "score": round(score, 3),
            }
        )
        if len(chosen) >= limit:
            break
    return chosen
