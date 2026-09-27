"""Test doubles for the language model and embedder."""

import hashlib
import math

from app.core.llm import LLMError


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
