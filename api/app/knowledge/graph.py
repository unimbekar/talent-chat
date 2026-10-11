"""LangGraph retrieval: find knowledge-base passages, then draft an answer from those passages only."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.embed import Embedder
from app.core.llm import LLMError
from app.db import admin_session
from app.knowledge.store import search_passages

_MISSING = "That is not in the knowledge base on file."


class RagState(TypedDict):
    question: str
    passages: list[dict]
    answer: str


def build_rag_graph(session: Session, embedder: Embedder, llm, *, audience: str):
    def retrieve(state: RagState) -> dict:
        return {"passages": search_passages(session, embedder, state["question"], audience=audience)}

    def draft(state: RagState) -> dict:
        passages = state.get("passages") or []
        if not passages:
            return {"answer": _MISSING}
        excerpts = "\n\n".join(f"{item['title']}: {item['excerpt']}" for item in passages)
        system = (
            "You answer a question from the company knowledge base. "
            "The documents may be benefits, policies, onboarding, procedures, or other uploaded material. "
            "Use only the excerpts. Write 2 to 4 sentences. "
            "Name the document title you used. "
            "If the excerpts do not state the answer, say that it is not in the knowledge base. "
            "Do not invent numbers, dates, or rules."
        )
        user = f"Question: {state['question']}\n\nKnowledge base excerpts:\n{excerpts}"
        try:
            text = (llm.complete(system=system, user=user, temperature=0.1, json_mode=False) or "").strip()
        except LLMError:
            text = ""
        if not text:
            text = " ".join(f"From {item['title']}: {item['excerpt'][:240]}" for item in passages[:2])
        return {"answer": text}

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", END)
    return graph.compile()


def run_rag(session: Session, embedder: Embedder, llm, question: str, *, audience: str = "public") -> dict:
    result = build_rag_graph(session, embedder, llm, audience=audience).invoke(
        {"question": question, "passages": [], "answer": ""}
    )
    passages = result.get("passages") or []
    return {
        "answer": result.get("answer") or _MISSING,
        "sources": [{"title": item["title"], "excerpt": item["excerpt"]} for item in passages],
    }


def answer_public(embedder, llm, question: str) -> dict:
    """Careers visitors only see documents marked public. The public database role cannot read this table."""
    session = admin_session()
    try:
        return run_rag(session, embedder, llm, question, audience="public")
    finally:
        session.close()


def public_excerpts(embedder, question: str) -> list[dict]:
    session = admin_session()
    try:
        return search_passages(session, embedder, question, audience="public", limit=3)
    finally:
        session.close()
