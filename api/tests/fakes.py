"""Test doubles for the language model and embedder."""

import hashlib
import math

from app.core.llm import ChatEvent, LLMError, ToolCall


def unit_vector(text: str) -> list[float]:
    block = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < 768:
        block = hashlib.sha256(block).digest()
        values.extend((byte / 127.5) - 1.0 for byte in block)
    values = values[:768]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


class RecordingEmbedder:
    def __init__(self) -> None:
        self.documents: list[str] = []
        self.queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documents.extend(texts)
        return [unit_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return unit_vector(text)


class RecordingLLM:
    def __init__(self, text: str = "These open roles match the search.", fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.prompts: list[dict] = []

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        self.prompts.append({"system": system, "user": user, "temperature": temperature, "json_mode": json_mode})
        if self.fail:
            raise LLMError("model endpoint stopped")
        if json_mode:
            return "{}"
        return self.text


def say(text: str) -> list[ChatEvent]:
    """A scripted model reply made of text, streamed in two pieces."""
    half = len(text) // 2
    return [ChatEvent("text", text=text[:half]), ChatEvent("text", text=text[half:]), ChatEvent("done", usage={"prompt_tokens": 10, "completion_tokens": 5})]


def call(name: str, arguments: dict | None = None, call_id: str | None = None) -> list[ChatEvent]:
    return [
        ChatEvent("tool_call", call=ToolCall(call_id or f"call_{name}", name, arguments or {})),
        ChatEvent("done", usage={"prompt_tokens": 10, "completion_tokens": 5}),
    ]


class ScriptedChatLLM(RecordingLLM):
    """Plays back one scripted reply per stream_chat call. A reply of None raises LLMError."""

    def __init__(self, replies: list[list[ChatEvent] | None]) -> None:
        super().__init__()
        self.replies = list(replies)
        self.chats: list[dict] = []

    def stream_chat(self, messages, tools, *, temperature=0.1, max_tokens=1200, require_tool=False):
        self.chats.append(
            {"messages": [dict(m) for m in messages], "tools": [t["name"] for t in tools], "require_tool": require_tool}
        )
        if not self.replies:
            raise AssertionError("the model was called more times than scripted")
        reply = self.replies.pop(0)
        if reply is None:
            raise LLMError("model endpoint stopped")
        yield from reply
