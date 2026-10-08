"""One LLM client. openai_compat talks to the DGX. bedrock talks to Amazon Bedrock.

complete() is one prompt in, one text out. stream_chat() is the recruiter
assistant's turn: a message list plus tool specs in, a stream of text deltas
and tool calls out. Both backends emit the same ChatEvent shapes.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol
import json
import re
import uuid

import httpx

_THINK = re.compile(r"(?is)<think>.*?</think>")
_THINK_OPEN = re.compile(r"(?is)<think>.*\Z")
_FENCE = re.compile(r"(?is)^```(?:json)?\s*|\s*```$")


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        """Return assistant text. JSON callers strip think-blocks and fences before parsing."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ChatEvent:
    """kind is "text" (delta in text), "tool_call" (call set), or "done" (usage set)."""

    kind: str
    text: str = ""
    call: ToolCall | None = None
    usage: dict = field(default_factory=dict)


class ChatClient(Protocol):
    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        require_tool: bool = False,
    ) -> Iterator[ChatEvent]:
        """messages use roles system, user, assistant (optional tool_calls), and tool (tool_call_id).

        tools are {"name", "description", "parameters"} with a JSON Schema object.
        require_tool asks the server to force a tool call. Ollama ignores it, so callers still check.
        """


def _arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


class _ThinkFilter:
    """Drops <think>…</think> spans from streamed text, even when tags split across deltas."""

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, text: str) -> str:
        self._buffer += text
        out = []
        while self._buffer:
            if self._inside:
                end = self._buffer.find("</think>")
                if end < 0:
                    self._buffer = self._buffer[-8:]
                    return "".join(out)
                self._buffer = self._buffer[end + len("</think>") :]
                self._inside = False
                continue
            start = self._buffer.find("<think>")
            if start < 0:
                # Hold back a possible partial tag.
                keep = next((n for n in range(min(7, len(self._buffer)), 0, -1) if "<think>".startswith(self._buffer[-n:])), 0)
                out.append(self._buffer[: len(self._buffer) - keep])
                self._buffer = self._buffer[len(self._buffer) - keep :]
                return "".join(out)
            out.append(self._buffer[:start])
            self._buffer = self._buffer[start + len("<think>") :]
            self._inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._buffer
        self._buffer = ""
        return rest


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

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 90.0,
        reasoning_effort: str = "none",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _base_payload(self, temperature: float) -> dict:
        # Ollama's /v1 ignores "think"; reasoning_effort "none" is what turns thinking off.
        payload: dict = {"model": self.model, "temperature": temperature, "think": False}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        payload = self._base_payload(temperature)
        payload["messages"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        headers = self._headers()
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

    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        require_tool: bool = False,
    ) -> Iterator[ChatEvent]:
        payload = self._base_payload(temperature)
        payload.update(
            {
                "stream": True,
                "stream_options": {"include_usage": True},
                "max_tokens": max_tokens,
                "messages": [_openai_message(m) for m in messages],
            }
        )
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
                }
                for t in tools
            ]
            if require_tool:
                payload["tool_choice"] = "required"
        last_error: Exception | None = None
        for _attempt in range(2):
            emitted = False
            try:
                for event in self._stream_once(payload):
                    emitted = True
                    yield event
                return
            except (httpx.HTTPError, ValueError) as exc:
                # Retrying after text reached the user would duplicate it.
                if emitted:
                    raise LLMError(f"openai_compat stream broke: {exc}") from exc
                last_error = exc
        raise LLMError(f"openai_compat request failed: {last_error}")

    def _stream_once(self, payload: dict) -> Iterator[ChatEvent]:
        think = _ThinkFilter()
        pending: dict[int, dict] = {}
        usage: dict = {}
        timeout = httpx.Timeout(self.timeout, connect=5.0)
        with httpx.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise httpx.HTTPStatusError(
                    f"{response.status_code}: {response.text[:300]}",
                    request=response.request,
                    response=response,
                )
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    text = think.feed(delta.get("content") or "")
                    if text:
                        yield ChatEvent("text", text=text)
                    for piece in delta.get("tool_calls") or []:
                        slot = pending.setdefault(piece.get("index", len(pending)), {"id": "", "name": "", "args": ""})
                        slot["id"] = piece.get("id") or slot["id"]
                        function = piece.get("function") or {}
                        slot["name"] = function.get("name") or slot["name"]
                        slot["args"] += function.get("arguments") or ""
        rest = think.flush()
        if rest:
            yield ChatEvent("text", text=rest)
        for index in sorted(pending):
            slot = pending[index]
            if slot["name"]:
                yield ChatEvent(
                    "tool_call",
                    call=ToolCall(slot["id"] or f"call_{uuid.uuid4().hex[:8]}", slot["name"], _arguments(slot["args"])),
                )
        yield ChatEvent("done", usage=usage)


def _openai_message(message: dict) -> dict:
    role = message["role"]
    if role == "tool":
        return {"role": "tool", "tool_call_id": message["tool_call_id"], "content": message.get("content", "")}
    out: dict = {"role": role, "content": message.get("content") or ""}
    if role == "assistant" and message.get("tool_calls"):
        out["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments") or {})},
            }
            for call in message["tool_calls"]
        ]
    return out


class BedrockClient:
    """Amazon Bedrock Converse API. Nova models are not on the OpenAI wire format."""

    def __init__(
        self,
        model: str,
        region: str = "us-east-1",
        timeout: float = 30.0,
        client=None,
    ) -> None:
        self.model = model
        self.region = region
        self.timeout = timeout
        self._client = client

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        if not self.model.strip():
            raise LLMError("LLM_MODEL is empty")
        runtime = self._runtime()
        payload = {
            "modelId": self.model,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": 4096, "temperature": temperature},
        }
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                body = runtime.converse(**payload)
                blocks = body["output"]["message"]["content"]
                return "".join(block.get("text", "") for block in blocks)
            except (KeyError, IndexError, TypeError) as exc:
                last_error = exc
            except Exception as exc:
                if not _bedrock_transport_error(exc):
                    raise
                last_error = exc
        raise LLMError(f"bedrock request failed: {last_error}")

    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        require_tool: bool = False,
    ) -> Iterator[ChatEvent]:
        if not self.model.strip():
            raise LLMError("LLM_MODEL is empty")
        # Converse rejects toolUse and toolResult blocks without a toolConfig.
        system, converse_messages = bedrock_messages(messages, flatten_tools=not tools)
        payload: dict = {
            "modelId": self.model,
            "messages": converse_messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if system:
            payload["system"] = [{"text": system}]
        if tools:
            payload["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["name"],
                            "description": t["description"],
                            "inputSchema": {"json": t["parameters"]},
                        }
                    }
                    for t in tools
                ]
            }
            if require_tool:
                payload["toolConfig"]["toolChoice"] = {"any": {}}
        try:
            response = self._runtime().converse_stream(**payload)
        except Exception as exc:
            if not _bedrock_transport_error(exc):
                raise
            raise LLMError(f"bedrock request failed: {exc}") from exc
        think = _ThinkFilter()
        blocks: dict[int, dict] = {}
        usage: dict = {}
        try:
            for event in response["stream"]:
                if "contentBlockStart" in event:
                    start = event["contentBlockStart"]
                    tool = (start.get("start") or {}).get("toolUse")
                    if tool:
                        blocks[start.get("contentBlockIndex", len(blocks))] = {
                            "id": tool.get("toolUseId", ""),
                            "name": tool.get("name", ""),
                            "args": "",
                        }
                elif "contentBlockDelta" in event:
                    body = event["contentBlockDelta"]
                    delta = body.get("delta") or {}
                    if "text" in delta:
                        text = think.feed(delta["text"])
                        if text:
                            yield ChatEvent("text", text=text)
                    elif "toolUse" in delta:
                        slot = blocks.get(body.get("contentBlockIndex", -1))
                        if slot is not None:
                            slot["args"] += delta["toolUse"].get("input", "")
                elif "metadata" in event:
                    raw = event["metadata"].get("usage") or {}
                    usage = {
                        "prompt_tokens": raw.get("inputTokens", 0),
                        "completion_tokens": raw.get("outputTokens", 0),
                        "total_tokens": raw.get("totalTokens", 0),
                    }
        except Exception as exc:
            if not _bedrock_transport_error(exc) and not isinstance(exc, (KeyError, TypeError)):
                raise
            raise LLMError(f"bedrock stream broke: {exc}") from exc
        rest = think.flush()
        if rest:
            yield ChatEvent("text", text=rest)
        for index in sorted(blocks):
            slot = blocks[index]
            if slot["name"]:
                yield ChatEvent(
                    "tool_call",
                    call=ToolCall(slot["id"] or f"tooluse_{uuid.uuid4().hex[:8]}", slot["name"], _arguments(slot["args"])),
                )
        yield ChatEvent("done", usage=usage)

    def _runtime(self):
        if self._client is not None:
            return self._client
        import boto3
        from botocore.config import Config

        return boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(
                connect_timeout=5,
                read_timeout=self.timeout,
                retries={"max_attempts": 1},
            ),
        )


def _bedrock_transport_error(exc: Exception) -> bool:
    name = type(exc).__name__
    return name in {"ClientError", "BotoCoreError", "EndpointConnectionError", "ReadTimeoutError", "ConnectTimeoutError"}


def bedrock_messages(messages: list[dict], flatten_tools: bool = False) -> tuple[str, list[dict]]:
    """Map chat messages to Converse: system apart, tool results as user turns, roles alternating.

    flatten_tools writes tool calls and results as plain text, for a request that sends no tools.
    """
    system_parts: list[str] = []
    out: list[dict] = []

    def push(role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})

    for message in messages:
        role = message["role"]
        content = message.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(content)
        elif role == "user":
            push("user", [{"text": content}] if content else [])
        elif role == "assistant":
            blocks: list[dict] = [{"text": content}] if content else []
            for call in message.get("tool_calls") or []:
                if flatten_tools:
                    blocks.append({"text": f"[called {call['name']} {json.dumps(call.get('arguments') or {})}]"})
                else:
                    blocks.append(
                        {"toolUse": {"toolUseId": call["id"], "name": call["name"], "input": call.get("arguments") or {}}}
                    )
            push("assistant", blocks)
        elif role == "tool":
            if flatten_tools:
                push("user", [{"text": f"[result of {message.get('name') or 'tool'}] {content or '{}'}"}])
            else:
                push(
                    "user",
                    [{"toolResult": {"toolUseId": message["tool_call_id"], "content": [{"text": content or "{}"}]}}],
                )
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"text": "(conversation continues)"}]})
    return "\n\n".join(system_parts), out


def build_llm_client(
    backend: str,
    base_url: str,
    model: str,
    api_key: str,
    region: str = "us-east-1",
    reasoning_effort: str | None = None,
) -> LLMClient:
    if backend == "bedrock":
        return BedrockClient(model, region=region)
    if backend != "openai_compat":
        raise LLMError(f"Unknown LLM_BACKEND {backend}")
    if reasoning_effort is None:
        from app.config import get_settings

        reasoning_effort = get_settings().llm_reasoning_effort
    return OpenAICompatClient(base_url, model, api_key, reasoning_effort=reasoning_effort)
