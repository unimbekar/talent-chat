"""One LLM client. Phase 1 implements openai_compat. Bedrock is a Phase 1.5 stub."""

from typing import Protocol
import json
import re

import httpx

_THINK = re.compile(r"(?is)<think>.*?</think>")
_THINK_OPEN = re.compile(r"(?is)<think>.*\Z")
_FENCE = re.compile(r"(?is)^```(?:json)?\s*|\s*```$")


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        """Return assistant text. JSON callers strip think-blocks and fences before parsing."""


def strip_model_text(text: str) -> str:
    cleaned = _THINK.sub("", text or "")
    cleaned = _THINK_OPEN.sub("", cleaned)
    cleaned = cleaned.strip()
    cleaned = _FENCE.sub("", cleaned).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"(?is)^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def parse_json_content(text: str) -> dict:
    cleaned = strip_model_text(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise LLMError("model JSON was not an object")
    return data


class OpenAICompatClient:
    """OpenAI-compatible chat completions, aimed at the DGX (Ollama, vLLM, or NIM)."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        payload: dict = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
                return body["choices"][0]["message"]["content"] or ""
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = exc
        raise LLMError(f"openai_compat request failed: {last_error}")


class BedrockClient:
    """Phase 1.5 implements the Bedrock Converse API. This stub does not call AWS."""

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        raise LLMError("The bedrock backend is implemented in Phase 1.5 and is not available in Phase 1.")


def build_llm_client(backend: str, base_url: str, model: str, api_key: str) -> LLMClient:
    if backend == "bedrock":
        return BedrockClient()
    if backend != "openai_compat":
        raise LLMError(f"Unknown LLM_BACKEND {backend}")
    return OpenAICompatClient(base_url, model, api_key)
