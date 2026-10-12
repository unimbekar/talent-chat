"""Store uploaded documents as embedded chunks. Retrieval mixes word overlap with vectors."""

from datetime import datetime, timezone
import math
import re
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embed import Embedder, cosine
from app.core.extract import ExtractError, extract_text
from app.knowledge.sections import CHUNK_VERSION, Section, chunk_sections
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


_GENERIC = {
    "summarise", "summarize", "summary", "company", "benefit", "benefits",
    "employee", "employees", "please", "tell", "explain", "describe",
    "offer", "offered", "janus", "soft", "information", "detail", "details",
}
# A question about one benefit should not be answered from a neighboring section
# that merely shares the word "insurance" or "health".
_TOPIC_RULES: tuple[tuple[re.Pattern[str], set[str], set[str]], ...] = (
    (re.compile(r"401|retirement|\bmatch"), {"401k", "retirement", "match"}, set()),
    (re.compile(r"health insurance|medical|dental|vision"), {"medical", "dental", "vision", "premium"}, {"disability"}),
    (re.compile(r"life insurance|\bdisability\b"), {"disability", "life"}, set()),
    (re.compile(r"\bpto\b|time off|vacation"), {"unlimited", "pto", "time"}, set()),
    (re.compile(r"tuition|training"), {"tuition", "training"}, set()),
    (re.compile(r"referral"), {"referral"}, set()),
    (re.compile(r"stipend|technology|laptop|gym"), {"technology", "laptop", "gym", "tablet"}, set()),
)


def _fold(text: str) -> str:
    folded = (text or "").lower().replace("401(k)", "401k").replace("401 (k)", "401k")
    return re.sub(r"401\s*k\b", "401k", folded)


def _stem_token(token: str) -> str:
    if len(token) > 6 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _terms(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(_fold(text)) if token not in _STOP and len(token) > 1}


def _normalized(text: str) -> set[str]:
    return {_stem_token(token) for token in _terms(text)}


def _focus(question: str) -> set[str]:
    focused = {token for token in _normalized(question) if token not in _GENERIC}
    return focused or _normalized(question)


def _topic(question: str) -> tuple[set[str], set[str]]:
    folded = _fold(question)
    for pattern, preferred, avoided in _TOPIC_RULES:
        if pattern.search(folded):
            return preferred, avoided
    return set(), set()


def _overlap(needles: set[str], hay: set[str]) -> float:
    if not needles:
        return 0.0
    return len(needles & hay) / len(needles)


def _other_topics(preferred: set[str]) -> list[set[str]]:
    return [terms for _pattern, terms, _avoided in _TOPIC_RULES if terms and terms != preferred]


def _excerpt(text: str, focus: set[str], preferred: set[str] | None = None, limit: int = 900) -> str:
    """Keep the lines that answer the question, including the table rows that follow them.

    A neighboring benefit named on the same page, such as the 401(k) line under a health
    question, is left out so the answer stays on the topic that was asked.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1 or not focus:
        return "\n".join(lines)[:limit]
    hits = [index for index, line in enumerate(lines) if _normalized(line) & focus]
    if not hits:
        return "\n".join(lines)[:limit]
    others = _other_topics(preferred or set())
    on_topic = focus | (preferred or set())

    def on_this_topic(line: str) -> bool:
        terms = _normalized(line)
        if not terms or not others:
            return True
        if terms & on_topic:
            return True
        return not any(terms & other for other in others)

    keep: set[int] = set()
    for index in hits:
        keep.add(index)
        if index > 0 and on_this_topic(lines[index - 1]):
            keep.add(index - 1)
        for follow in range(index + 1, min(len(lines), index + 10)):
            if not on_this_topic(lines[follow]):
                break
            # A bare amount such as "$10,000" belongs to the next card when that card is a different benefit.
            nxt = lines[follow + 1] if follow + 1 < len(lines) else ""
            if nxt and not on_this_topic(nxt) and not (_normalized(lines[follow]) & on_topic):
                break
            keep.add(follow)
    chosen = [lines[index] for index in sorted(keep)]
    return "\n".join(chosen)[:limit]


def split_text(body: str) -> list[str]:
    parts = [part.strip() for part in _SPLITTER.split_text(body) if part.strip()]
    return parts or [body.strip()]


def _write_chunks(session: Session, document: KnowledgeDocument, embedder: Embedder) -> None:
    document.chunks.clear()
    session.flush()
    sections = chunk_sections(document.body) or [Section(heading=None, lines=[document.body.strip()])]
    texts = [section.body for section in sections]
    vectors = embedder.embed_documents(
        [f"{document.title}. {section.heading}\n{section.body}" if section.heading else section.body for section in sections]
    )
    for index, (section, text, vector) in enumerate(zip(sections, texts, vectors)):
        document.chunks.append(
            KnowledgeChunk(ord=index, text=text, heading=section.heading, kicker=section.kicker, embedding=vector)
        )
    document.chunk_version = CHUNK_VERSION


def rechunk_stale(session: Session, embedder: Embedder) -> int:
    """Split documents stored before sections existed. Returns how many were rewritten."""
    stale = session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.chunk_version < CHUNK_VERSION)).all()
    for document in stale:
        _write_chunks(session, document, embedder)
    if stale:
        session.commit()
    return len(stale)


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


# Words a visitor uses for a benefit that the document may name differently. Keys and values are stemmed.
_SYNONYMS: dict[str, set[str]] = {
    "health": {"medical", "dental", "vision", "insurance", "premium", "coverage"},
    "healthcare": {"medical", "dental", "vision", "insurance", "premium", "coverage"},
    "insurance": {"medical", "dental", "vision", "coverage", "premium"},
    "medical": {"health", "coverage", "premium", "insurance"},
    "dental": {"medical", "vision", "coverage", "premium"},
    "vision": {"medical", "dental", "coverage", "premium"},
    "doctor": {"medical", "health"},
    "family": {"spouse", "children", "child", "dependent"},
    "dependent": {"spouse", "children", "child", "family"},
    "spouse": {"family", "children", "dependent"},
    "kid": {"children", "child", "family"},
    "wife": {"spouse", "family"},
    "husband": {"spouse", "family"},
    "pto": {"paid", "time", "off", "vacation", "leave", "unlimited"},
    "vacation": {"pto", "time", "off", "leave"},
    "leave": {"time", "off", "pto"},
    "holiday": {"time", "off", "pto"},
    "sick": {"time", "off", "pto", "leave"},
    "401k": {"retirement", "match", "safe", "harbor"},
    "retirement": {"401k", "match"},
    "pension": {"401k", "retirement"},
    "pay": {"salary", "compensation", "contribution", "premium"},
    "cost": {"contribution", "premium"},
    "start": {"effective", "date", "hire"},
    "begin": {"effective", "date", "hire"},
    "eligible": {"effective", "covered", "coverage"},
    "covered": {"insurance", "medical", "premium"},
    "salary": {"compensation", "pay", "bonus"},
    "compensation": {"salary", "pay", "bonus"},
    "raise": {"salary", "compensation", "bonus"},
    "tuition": {"training", "education", "certification", "skill"},
    "training": {"tuition", "certification", "course", "skill"},
    "education": {"tuition", "training"},
    "certification": {"training", "tuition"},
    "learning": {"training", "tuition", "skill"},
    "disability": {"life", "insurance"},
    "life": {"disability", "insurance"},
    "gym": {"health", "technology", "fitness", "wellness"},
    "fitness": {"gym", "health", "wellness"},
    "wellness": {"health", "gym", "fitness"},
    "laptop": {"technology", "computer", "phone", "tablet"},
    "computer": {"technology", "laptop"},
    "phone": {"technology"},
    "tech": {"technology"},
    "stipend": {"allowance", "reimburse"},
    "allowance": {"reimburse", "stipend"},
    "refer": {"referral"},
    "referral": {"refer", "bonus"},
}
# Words that only ask for a list of benefits. A question made of these gets every section.
_OVERVIEW = re.compile(r"(?i)\b(benefits?|perks?|package|overview|everything|offer(?:ed|s)?|all)\b")
_ASK_WORDS = {
    "show", "give", "list", "perk", "package", "know", "want", "see", "need", "would", "like", "could",
    "get", "more", "have", "ha", "provide", "info", "overview", "all", "which", "who", "when", "where",
    "why", "will", "should", "they", "them", "their", "am", "was", "were", "available", "everything",
    "some", "these", "those", "please", "thank", "thanks", "hi", "hello", "there", "here", "also",
    "what", "about", "include", "included", "includ", "come", "with", "much",
}
_FOLLOW_UP = re.compile(
    r"(?i)^\s*(and|also|what about|how about|for|what if|is that|does that|does it|is it|how much|who|when|"
    r"same|then|so|ok(?:ay)?)\b|\b(it|that|this|those|them|they|these)\b"
)


# Words that ask about a detail of the topic already being discussed rather than naming a new one.
_DETAIL_WORDS = {
    "start", "begin", "kick", "effective", "eligible", "eligibility", "wait", "long", "cost", "price",
    "amount", "limit", "max", "maximum", "pay", "paid", "contribute", "contribution", "share", "date",
    "day", "month", "year", "percent", "much", "many", "who", "spouse", "children", "child", "kid", "family",
}


def is_follow_up(question: str) -> bool:
    return len((question or "").split()) <= 10 and bool(_FOLLOW_UP.search(question or ""))


def topic_terms(question: str) -> set[str]:
    """Question words that name a subject, not a detail such as when it starts or what it costs."""
    return ask_terms(question) - _DETAIL_WORDS


def ask_terms(question: str) -> set[str]:
    """The words of a question that name a topic, without asking words such as "show" or "benefits"."""
    return {token for token in _normalized(question) if token not in _GENERIC and token not in _ASK_WORDS}


# "Health benefits" means medical coverage to most people, so these count as the word itself.
_EQUIVALENT: dict[str, set[str]] = {
    "health": {"medical", "dental", "vision"},
    "healthcare": {"medical", "dental", "vision"},
    "pto": {"time", "vacation"},
    "401k": {"retirement"},
    "retirement": {"401k"},
    "salary": {"compensation"},
    "covered": {"coverage"},
    "cover": {"coverage"},
    "tuition": {"training"},
    "training": {"tuition"},
}


def _weights(question: str, context: str = "") -> list[dict[str, float]]:
    """One group per question word: the word, its equivalents, and its synonyms at half weight.

    A section scores each group once, by its best match, so a word with many synonyms cannot
    outweigh a section whose heading names the word itself. A follow-up adds the earlier question.
    """
    groups: list[dict[str, float]] = []
    own = ask_terms(question)
    terms = [(term, 1.0) for term in sorted(own)]
    if context and (not own or is_follow_up(question)):
        terms.extend((term, 0.7) for term in sorted(ask_terms(context) - own))
    for term, weight in terms:
        group = {term: weight}
        for other in _EQUIVALENT.get(term, ()):
            group.setdefault(other, weight)
        for other in _SYNONYMS.get(term, ()):
            group.setdefault(other, weight * 0.5)
        groups.append(group)
    return groups


def _is_overview(question: str, weights: list[dict[str, float]]) -> bool:
    return not weights and bool(_OVERVIEW.search(question or ""))


def _chunk_terms(chunk: KnowledgeChunk) -> tuple[set[str], set[str]]:
    heading = _normalized(f"{chunk.heading or ''} {chunk.kicker or ''}")
    return heading, _normalized(chunk.text)


def _passage(chunk: KnowledgeChunk, excerpt: str, score: float) -> dict:
    return {
        "title": chunk.document.title,
        "section": chunk.heading,
        "kicker": chunk.kicker,
        "excerpt": excerpt,
        "lines": [line.strip() for line in excerpt.splitlines() if line.strip()],
        "score": round(score, 3),
        "document_id": str(chunk.document_id),
        "ord": chunk.ord,
    }


def _overview(rows: list[KnowledgeChunk], question: str, limit: int) -> list[dict]:
    """Every titled section of the document the question names, in document order."""
    by_document: dict[uuid.UUID, list[KnowledgeChunk]] = {}
    for chunk in rows:
        by_document.setdefault(chunk.document_id, []).append(chunk)
    asked = _normalized(question)

    def rank(chunks: list[KnowledgeChunk]) -> tuple[int, int]:
        document = chunks[0].document
        names = _normalized(document.title + " " + " ".join(chunk.heading or "" for chunk in chunks))
        return (len(asked & names), sum(1 for chunk in chunks if chunk.heading))

    best = max(by_document.values(), key=rank)
    titled = sorted((chunk for chunk in best if chunk.heading), key=lambda chunk: chunk.ord)
    if not titled:
        return []
    seen: set[str] = set()
    chosen = []
    for chunk in titled:
        if chunk.heading in seen:
            continue
        seen.add(chunk.heading)
        chosen.append({**_passage(chunk, chunk.text, 1.0), "overview": True})
    return chosen[: max(limit, 12)]


def search_passages(
    session: Session,
    embedder: Embedder,
    question: str,
    *,
    audience: str,
    limit: int = 4,
    context: str = "",
) -> list[dict]:
    """Sections that answer the question. Documents without headings fall back to line excerpts."""
    rows = session.scalars(
        select(KnowledgeChunk)
        .join(KnowledgeDocument)
        .where(KnowledgeDocument.audience == audience)
    ).all()
    if not rows:
        return []
    titled = [chunk for chunk in rows if chunk.heading]
    plain = [chunk for chunk in rows if not chunk.heading and not any(
        other.heading for other in rows if other.document_id == chunk.document_id
    )]
    weights = _weights(question, context)
    if titled and _is_overview(question, weights):
        return _overview(titled, question, limit)
    query_vector = embedder.embed_query(question if not context or not is_follow_up(question) else f"{context}\n{question}")
    results = _search_sections([chunk for chunk in rows if chunk not in plain], weights, query_vector, limit)
    if plain:
        results.extend(_search_plain(plain, question, query_vector, limit))
        results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def _search_sections(rows: list[KnowledgeChunk], weights: list[dict[str, float]], query_vector, limit: int) -> list[dict]:
    if not rows or not weights:
        return []
    terms = {chunk.id: _chunk_terms(chunk) for chunk in rows}
    count = len(rows)
    frequency: dict[str, int] = {}
    for heading, body in terms.values():
        for term in heading | body:
            frequency[term] = frequency.get(term, 0) + 1

    def idf(term: str) -> float:
        seen = frequency.get(term, 0)
        return math.log(1 + (count - seen + 0.5) / (seen + 0.5))

    ceiling = sum(max(weight * idf(term) * 2 for term, weight in group.items()) for group in weights) or 1.0
    scored: list[tuple[float, float, KnowledgeChunk]] = []
    for chunk in rows:
        heading, body = terms[chunk.id]
        lexical = 0.0
        for group in weights:
            best = 0.0
            for term, weight in group.items():
                if term in heading:
                    best = max(best, weight * idf(term) * 2)
                elif term in body:
                    best = max(best, weight * idf(term))
            lexical += best
        vector = cosine(list(chunk.embedding) if chunk.embedding is not None else None, query_vector)
        scored.append((lexical / ceiling, vector, chunk))
    has_titles = {chunk.document_id for chunk in rows if chunk.heading}
    lexical_hits = [item for item in scored if item[0] > 0]
    if not lexical_hits:
        # Wording the document never uses. Only a very close meaning match is allowed through.
        lexical_hits = [item for item in scored if item[1] >= 0.72]
        if not lexical_hits:
            return []
    top_lexical = max(item[0] for item in lexical_hits) or 1.0
    vectors = [item[1] for item in lexical_hits]
    low, high = min(vectors), max(vectors)
    spread = (high - low) or 1.0
    ranked: list[tuple[float, KnowledgeChunk]] = []
    for lexical, vector, chunk in lexical_hits:
        score = 0.7 * (lexical / top_lexical) + 0.3 * ((vector - low) / spread if high > low else 1.0)
        if not chunk.heading and chunk.document_id in has_titles:
            score *= 0.5
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    best = ranked[0][0]
    chosen: list[dict] = []
    seen: set[tuple[uuid.UUID, str | None]] = set()
    for score, chunk in ranked:
        if score < best * 0.65 or len(chosen) >= min(limit, 3):
            break
        key = (chunk.document_id, chunk.heading)
        if chunk.heading and key in seen:
            continue
        seen.add(key)
        chosen.append(_passage(chunk, chunk.text, score))
    return chosen


def _search_plain(rows: list[KnowledgeChunk], question: str, query_vector, limit: int) -> list[dict]:
    focus = _focus(question)
    preferred, avoided = _topic(question)
    scored: list[tuple[float, float, KnowledgeChunk]] = []
    for chunk in rows:
        terms = _normalized(chunk.text)
        lexical = _overlap(focus, terms)
        vector = cosine(list(chunk.embedding) if chunk.embedding is not None else None, query_vector)
        topical = _overlap(preferred, terms) if preferred else 0.0
        penalty = 0.12 if avoided and (avoided & terms) and topical == 0 else 0.0
        score = (0.5 * lexical) + (0.35 * max(vector, 0.0)) + (0.15 * topical) - penalty
        if lexical >= 0.34 or vector >= 0.45 or topical > 0:
            scored.append((score, topical, chunk))
    if preferred:
        on_topic = [item for item in scored if item[1] > 0]
        if on_topic:
            scored = on_topic
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen: list[dict] = []
    per_document: dict[uuid.UUID, int] = {}
    seen_excerpt: set[str] = set()
    for score, _topical, chunk in scored:
        if per_document.get(chunk.document_id, 0) >= 3:
            continue
        excerpt = _excerpt(chunk.text, focus or preferred, preferred)
        signature = " ".join(excerpt.split())[:160]
        if not signature or signature in seen_excerpt:
            continue
        seen_excerpt.add(signature)
        per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1
        chosen.append(_passage(chunk, excerpt, score))
        if len(chosen) >= limit:
            break
    return chosen
