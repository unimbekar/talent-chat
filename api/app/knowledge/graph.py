"""LangGraph retrieval: find knowledge-base sections, then answer from those sections only.

The answer has two forms. The quoted form is built from the section text alone and is ready at
once. The written form asks the model to say the same thing in plain language, and is used only
when every figure in it appears in the sections or the question.
"""

from functools import lru_cache
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.embed import Embedder
from app.core.llm import LLMError, strip_model_text
from app.db import admin_session
from app.knowledge.sections import is_bullet, is_table_row, strip_bullet
from app.knowledge.store import search_passages

_MISSING = "That is not in the knowledge base on file."
# Visitors should not see which local model wrote the reply.
_MODEL_NAME = re.compile(
    r"(?i)\b(?:answered|powered|generated)\s+by\s+[A-Za-z0-9_.:/-]{2,40}\b|"
    r"\b(?:qwen|llama|mistral|mixtral|gemma|claude|ollama|gpt-[\d.]+)[\w.\-:]*\b|"
    r"\b(?:as an ai(?: language model)?|i am (?:an ai|a language model|qwen)[^.]{0,60})"
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def visitor_answer(text: str) -> str:
    """Drop thinking traces and any model name before a careers visitor sees the reply."""
    cleaned = strip_model_text(text or "")
    cleaned = _MODEL_NAME.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([,.])", r"\1", cleaned)
    return cleaned.strip()


def blocks(lines: list[str]) -> list[dict]:
    """Section lines as display blocks: a lead sentence, bullets, and tables with a header row."""
    out: list[dict] = []
    for line in lines:
        if is_table_row(line):
            cells = [cell.strip() for cell in line.split("|")]
            if out and out[-1]["kind"] == "table":
                out[-1]["rows"].append(cells)
            else:
                out.append({"kind": "table", "header": cells, "rows": []})
        elif is_bullet(line):
            out.append({"kind": "bullet", "text": strip_bullet(line)})
        else:
            out.append({"kind": "text", "text": line})
    for block in out:
        if block["kind"] == "table" and not block["rows"]:
            block["rows"], block["header"] = [block["header"]], []
    return out


def _row_sentence(header: list[str], row: list[str]) -> str:
    if not header or len(header) != len(row):
        return " · ".join(row)
    label, rest = row[0], [f"{name.lower()} {value}" for name, value in zip(header[1:], row[1:]) if value]
    return f"{label}: {', '.join(rest)}"


def readable(lines: list[str]) -> list[str]:
    """Section lines with each table row written out against its header, for the model and the quoted answer."""
    out: list[str] = []
    for block in blocks(lines):
        if block["kind"] == "table":
            out.extend(_row_sentence(block["header"], row) for row in block["rows"])
        else:
            out.append(block["text"])
    return out


@lru_cache(maxsize=1)
def _guide_anchors() -> dict[str, str]:
    """Section titles on the careers benefits page, so an answer can link to the full section."""
    try:
        from app.admin.benefits_routes import load_guide

        guide = load_guide()
    except Exception:
        return {}
    return {
        " ".join(str(item.get("title", "")).lower().split()): f"/jobs/benefits#{item['id']}"
        for item in guide.get("sections", [])
        if item.get("id") and item.get("title")
    }


def public_source(passage: dict) -> dict:
    section = passage.get("section")
    anchor = _guide_anchors().get(" ".join((section or "").lower().split())) if section else None
    return {
        "title": passage["title"],
        "section": section,
        "kicker": passage.get("kicker"),
        "excerpt": passage["excerpt"],
        "blocks": blocks(passage.get("lines") or passage["excerpt"].splitlines()),
        "anchor": anchor,
    }


def _lead_and_points(passage: dict) -> tuple[str, list[str]]:
    lines = readable(passage.get("lines") or passage["excerpt"].splitlines())
    if not lines:
        return "", []
    lead = lines[0] if not is_bullet(lines[0]) else ""
    points = lines[1:] if lead else lines
    return lead, points


def quoted_answer(passages: list[dict], *, overview: bool = False) -> str:
    """An answer made only of the section text. Used at once, and whenever the written answer fails a check."""
    if not passages:
        return _MISSING
    if overview:
        title = passages[0]["title"]
        rows = []
        for passage in passages:
            lead, _points = _lead_and_points(passage)
            rows.append(f"• {passage['section']}: {lead}" if lead else f"• {passage['section']}")
        return f"{title} covers {len(passages)} areas. Ask about any of them for the details.\n" + "\n".join(rows)
    parts = []
    for passage in passages:
        lead, points = _lead_and_points(passage)
        heading = passage.get("section")
        top = f"{heading}: {lead}" if heading and lead else (heading or lead)
        body = "\n".join(f"• {point}" for point in points[:8])
        parts.append("\n".join(part for part in (top, body) if part))
    return "\n\n".join(parts)


def _numbers(text: str) -> set[str]:
    found = set()
    for raw in _NUMBER.findall(text or ""):
        value = raw.replace(",", "").rstrip(".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        found.add(value)
    return found


def figures_match(answer: str, passages: list[dict], question: str, history: str = "") -> bool:
    """True when every number in the written answer is stated in the sections or the conversation."""
    allowed = _numbers(question) | _numbers(history)
    for passage in passages:
        allowed |= _numbers(passage["excerpt"]) | _numbers(passage.get("section") or "") | _numbers(passage.get("kicker") or "")
    return _numbers(answer) <= allowed


_UNSTATED = re.compile(
    r"(?i)\b(?:not|isn't|aren't)\s+(?:provided|specified|stated|mentioned|listed|given|included|detailed)\b|"
    r"\bno (?:details|information|specifics)\b|\b(?:text|excerpt|section)s? (?:does|do) not\b|\bin the (?:text|excerpts?)\b"
)


def _tidy(text: str) -> str:
    text = re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.M)
    text = re.sub(r"(?m)^\s*[-*]\s+", "• ", text)
    lines = text.split("\n")
    # The model sometimes adds "X is not specified in the text". The quoted sections already show what is there.
    kept = [line for line in lines if not _UNSTATED.search(line)]
    if any(line.strip() for line in kept):
        lines = kept
    lines = [line.strip() for line in lines if line.strip()]
    if lines:
        lines[0] = lines[0].lstrip("• ").strip()
    if len(lines) > 1:
        lines = [lines[0]] + [line if line.startswith("•") else f"• {line}" for line in lines[1:]]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def written_answer(llm, question: str, passages: list[dict], *, history: str = "", overview: bool = False, roles: str = "") -> str:
    """The model's plain-language answer, or the quoted answer when the model fails or adds a figure."""
    fallback = quoted_answer(passages, overview=overview)
    if not passages:
        return fallback
    excerpts = "\n\n".join(
        f"[{item['title']}{' › ' + item['section'] if item.get('section') else ''}]\n"
        + "\n".join(readable(item.get("lines") or item["excerpt"].splitlines()))
        for item in passages
    )
    system = (
        "You answer a careers visitor's question from the company knowledge base. "
        "Use only the sections given. Start with one direct sentence that answers the question. "
        "Then give the details as short lines that each start with '• ', at most 6 lines. "
        "When the question is about insurance coverage, say who is covered, what the employee pays, what the company pays, "
        "and when it starts, as far as the section states them. "
        "Copy every dollar amount, percent, and date exactly as the section writes it. "
        "Never write a line saying something is not specified or not stated; leave it out. "
        "Skip lines that only describe the document itself. "
        "For an overview, give one line per section with its main term. "
        "If the sections do not answer the question, say that it is not in the knowledge base. "
        "Plain text only: no markdown, no bold, no headings. "
        "Do not mention a language model, an AI, or your own name."
    )
    if roles:
        system += (
            " The visitor also asked about a role. The matching job cards are shown separately, so answer only the benefit part. "
            "The benefits apply to every role: do not say whether the sections list roles, and do not tie a benefit to one role."
        )
    earlier = f"Earlier conversation:\n{history}\n\n" if history else ""
    user = f"{earlier}Question: {question}\n\nSections:\n{excerpts}"
    try:
        text = visitor_answer(llm.complete(system=system, user=user, temperature=0.1, json_mode=False) or "")
    except LLMError:
        return fallback
    text = _tidy(text)
    if len(text) < 20 or not figures_match(text, passages, question, history):
        return fallback
    return text


class RagState(TypedDict, total=False):
    question: str
    context: str
    history: str
    roles: str
    use_model: bool
    passages: list[dict]
    answer: str


def build_rag_graph(session: Session, embedder: Embedder, llm, *, audience: str):
    def retrieve(state: RagState) -> dict:
        return {
            "passages": search_passages(
                session, embedder, state["question"], audience=audience, context=state.get("context", ""), limit=4
            )
        }

    def draft(state: RagState) -> dict:
        passages = state.get("passages") or []
        overview = _is_overview(passages)
        if not passages:
            return {"answer": _MISSING}
        if not state.get("use_model", True):
            return {"answer": quoted_answer(passages, overview=overview)}
        return {
            "answer": written_answer(
                llm,
                state["question"],
                passages,
                history=state.get("history", ""),
                overview=overview,
                roles=state.get("roles", ""),
            )
        }

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", END)
    return graph.compile()


def _is_overview(passages: list[dict]) -> bool:
    return bool(passages) and all(item.get("overview") for item in passages)


def run_rag(
    session: Session,
    embedder: Embedder,
    llm,
    question: str,
    *,
    audience: str = "public",
    context: str = "",
    history: str = "",
    roles: str = "",
    use_model: bool = True,
) -> dict:
    result = build_rag_graph(session, embedder, llm, audience=audience).invoke(
        {
            "question": question,
            "context": context,
            "history": history,
            "roles": roles,
            "use_model": use_model,
            "passages": [],
            "answer": "",
        }
    )
    passages = result.get("passages") or []
    return {
        "answer": result.get("answer") or _MISSING,
        "sources": [public_source(item) for item in passages],
        "passages": passages,
        "overview": _is_overview(passages),
    }


def answer_public(
    embedder, llm, question: str, *, context: str = "", history: str = "", roles: str = "", use_model: bool = True
) -> dict:
    """Careers visitors only see documents marked public. The public database role cannot read this table."""
    session = admin_session()
    try:
        return run_rag(
            session,
            embedder,
            llm,
            question,
            audience="public",
            context=context,
            history=history,
            roles=roles,
            use_model=use_model,
        )
    finally:
        session.close()


def public_excerpts(embedder, question: str, context: str = "") -> list[dict]:
    session = admin_session()
    try:
        return search_passages(session, embedder, question, audience="public", limit=3, context=context)
    finally:
        session.close()
