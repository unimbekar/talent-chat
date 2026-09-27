"""Token counts use the nomic-embed-text-v1.5 tokenizer.json."""

from functools import lru_cache
from pathlib import Path

from tokenizers import Tokenizer

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
CHUNK_TOKENS = 512
CHUNK_OVERLAP = 64
JOB_VECTOR_TOKENS = 2048
CANDIDATE_VECTOR_TOKENS = 1024
QUERY_TOKENS = 256


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parents[2] / ".cache" / "tokenizer.json",
        Path("/opt/fastembed/tokenizer.json"),
        Path.home() / ".cache" / "talent-chat" / "tokenizer.json",
    ]


@lru_cache
def tokenizer() -> Tokenizer:
    for path in _candidate_paths():
        if path.exists():
            return Tokenizer.from_file(str(path))
    raise FileNotFoundError(
        "nomic-embed-text-v1.5 tokenizer.json is not in the image cache. "
        "Rebuild the API image so the embedding model is baked in."
    )


def encode_ids(text: str) -> list[int]:
    if not text:
        return []
    return tokenizer().encode(text, add_special_tokens=False).ids


def decode_ids(ids: list[int]) -> str:
    if not ids:
        return ""
    return tokenizer().decode(ids)


def count_tokens(text: str) -> int:
    return len(encode_ids(text))


def truncate_tokens(text: str, max_tokens: int) -> str:
    ids = encode_ids(text)
    if len(ids) <= max_tokens:
        return text
    return decode_ids(ids[:max_tokens])


def token_windows(text: str, size: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[list[int]]:
    ids = encode_ids(text)
    if not ids:
        return []
    if overlap >= size:
        raise ValueError("overlap must be smaller than the chunk size")
    step = size - overlap
    windows: list[list[int]] = []
    start = 0
    while start < len(ids):
        windows.append(ids[start : start + size])
        if start + size >= len(ids):
            break
        start += step
    return windows


def _split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in text.split("\n\n")]
    return [part for part in parts if part]


def chunk_text(text: str, size: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Chunk on paragraph boundaries first. Oversized paragraphs use a 512/64 token window."""
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = _split_paragraphs(text)
    if len(paragraphs) == 1 and count_tokens(paragraphs[0]) > size:
        return [decode_ids(window) for window in token_windows(paragraphs[0], size, overlap)]

    chunks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer.clear()

    for paragraph in paragraphs:
        if count_tokens(paragraph) > size:
            flush()
            chunks.extend(decode_ids(window) for window in token_windows(paragraph, size, overlap))
            continue
        trial = "\n\n".join(buffer + [paragraph])
        if buffer and count_tokens(trial) > size:
            flush()
            if chunks:
                tail = truncate_tail(chunks[-1], overlap)
                if tail:
                    buffer.append(tail)
        buffer.append(paragraph)
    flush()
    return [chunk for chunk in chunks if chunk]


def truncate_tail(text: str, n_tokens: int) -> str:
    ids = encode_ids(text)
    if not ids:
        return ""
    return decode_ids(ids[-n_tokens:])


def _with_prefix(prefix: str, body: str, max_tokens: int) -> str:
    """Keep the nomic prefix literal. Only the body is truncated to the token cap."""
    prefix_len = len(encode_ids(prefix))
    room = max(max_tokens - prefix_len, 0)
    body_ids = encode_ids(body)
    if prefix_len + len(body_ids) <= max_tokens:
        return prefix + body
    return prefix + decode_ids(body_ids[:room])


def job_vector_text(title: str, city: str, summary: str, description: str) -> str:
    body = "\n".join(part for part in (title, city, summary, description) if part)
    return _with_prefix(DOCUMENT_PREFIX, body, JOB_VECTOR_TOKENS)


def candidate_vector_text(summary: str, titles: list[str], skills: list[str]) -> str:
    body = "\n".join(
        part
        for part in (
            summary or "",
            ", ".join(titles or []),
            ", ".join(skills or []),
        )
        if part
    )
    return _with_prefix(DOCUMENT_PREFIX, body, CANDIDATE_VECTOR_TOKENS)


def query_vector_text(text: str) -> str:
    return _with_prefix(QUERY_PREFIX, text or "", QUERY_TOKENS)
