"""Token sizes use the nomic tokenizer. Model JSON stripping."""

from app.core.llm import BedrockClient, LLMError, parse_json_content, strip_model_text
from app.core.tokens import (
    CANDIDATE_VECTOR_TOKENS,
    CHUNK_OVERLAP,
    CHUNK_TOKENS,
    candidate_vector_text,
    chunk_text,
    count_tokens,
    decode_ids,
    encode_ids,
    token_windows,
)


def test_strip_think_blocks_and_fences():
    raw = "<think>secret plan</think>\n```json\n{\"ok\": true}\n```"
    assert parse_json_content(raw) == {"ok": True}
    assert "<think>" not in strip_model_text(raw)


def test_bedrock_stub_is_not_implemented():
    try:
        BedrockClient().complete(system="s", user="u", temperature=0, json_mode=True)
    except LLMError as exc:
        assert "Phase 1.5" in str(exc)
    else:
        raise AssertionError("bedrock stub should not call AWS")


def test_three_thousand_token_resume_chunks_and_vector_cap():
    sentence = "Designed Java services on AWS using Python and PostgreSQL for a federal program in Chantilly. "
    text = ""
    while count_tokens(text) < 3000:
        text += sentence
    assert count_tokens(text) >= 3000
    windows = token_windows(text, CHUNK_TOKENS, CHUNK_OVERLAP)
    chunks = chunk_text(text, CHUNK_TOKENS, CHUNK_OVERLAP)
    assert chunks == [decode_ids(window) for window in windows]
    assert all(len(window) == CHUNK_TOKENS for window in windows[:-1])
    assert 0 < len(windows[-1]) <= CHUNK_TOKENS
    for previous, nxt in zip(windows, windows[1:]):
        assert len(previous) == CHUNK_TOKENS
        assert previous[-CHUNK_OVERLAP:] == nxt[:CHUNK_OVERLAP]
    assert count_tokens(text) == len(encode_ids(text))
    long_summary = text
    vector = candidate_vector_text(long_summary, ["Engineer"], ["Java", "Python", "AWS"])
    assert vector.startswith("search_document: ")
    assert count_tokens(vector) <= CANDIDATE_VECTOR_TOKENS
    assert count_tokens(vector) >= CANDIDATE_VECTOR_TOKENS - 8
