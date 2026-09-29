# Language model

The chat model on this machine is **`qwen3.6:latest`**, served by Ollama on the DGX Spark. The API talks to it through an OpenAI-compatible chat endpoint. Embeddings are a separate model and do not go through Ollama.

| Setting | Value on this Spark |
| --- | --- |
| `LLM_BACKEND` | `openai_compat` |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` |
| `LLM_MODEL` | `qwen3.6:latest` |
| `LLM_API_KEY` | blank (this Ollama server does not require one) |

Ollama reports that tag as a GGUF **Qwen 3.5 MoE** (`qwen35moe`), **36.0B** parameters, **Q4_K_M**, about **23 GB** on disk. Its context length is 262,144 tokens. The tag supports completion and thinking. The running API container is pointed at this tag.

Two other models are installed in Ollama and are not selected:

| Tag | What it is |
| --- | --- |
| `nemotron-3.5-lightning:latest` | NVIDIA Nemotron 3.5, 32.9B, Q4_K_M, about 25 GB |
| `nomic-embed-text:latest` | An embedding model. Stored vectors do not use it |

## What the chat model does

Every call goes through `LLMClient` in `api/app/core/llm.py`. Phase 1 posts to `{LLM_BASE_URL}/chat/completions` with a system message and a user message. Thinking is turned off so a short answer finishes inside the timeout. The timeout is 90 seconds, and a failed request is tried once more. `<think>` blocks and Markdown code fences are stripped before JSON is parsed.

A follow-up that says “these”, “those”, “them”, or “which of” stays on the jobs from the previous answer. So does a distance question such as “closest to Bethesda within 20”. Miles are computed from city coordinates and sent to the model with the jobs. The model uses those miles. Words such as Java in a “these” question do not drop jobs from the set. If the postings never mention what was asked, the answer says so.

| When | Temperature | What comes back |
| --- | --- | --- |
| Careers crawl structures a job | 0.0 | JSON: skills, clearance, polygraph, summary |
| A résumé is uploaded | 0.0 | JSON: name, contact, skills, titles, summary |
| A résumé is confirmed and ranked | 0.2 | Two to four sentences, stored on `matches.explanation` |
| A visitor question on `/chat`, including a follow-up about “these” jobs | 0.2 | Two to four sentences answering that question from the retrieved postings |

Job text sent to the model is capped at 6,000 characters. Résumé text is capped at 12,000 characters. Social Security numbers are redacted before that request. The model may only add skills that already appear in the posting or résumé text. If the call fails, the parser fills the job or résumé profile from the text, and the review screen still opens.

Line coverage on Jobs, Match, and Review does not call the model. Those percents come from the posting lines and the résumé text.

When Ollama is down, public search still returns job cards and sets the notice “Explanations are unavailable right now.” Ranked matches are still saved, with an empty explanation.

## Embeddings

Search vectors are computed inside the API process with FastEmbed, not by Ollama.

| Setting | Value |
| --- | --- |
| `EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` |
| Dimensions | 768 |
| Runtime | FastEmbed, CPU, baked into the API image |
| Distance | cosine |

Stored document text is prefixed with `search_document: `. A visitor query is prefixed with `search_query: `. Job vectors are capped at 2,048 tokens, candidate vectors at 1,024, chunks at 512 tokens with 64 overlap, and a visitor query at 256. Changing `EMBEDDING_MODEL` requires a full re-embed (`python -m app.reembed`). Leave Ollama’s `nomic-embed-text` out of that path so every stored vector comes from the same runtime.

## Change the chat model

Put another Ollama tag in `.env` and restart the API. The model has to already be pulled.

```bash
ollama pull qwen3.6:latest
```

```bash
LLM_BACKEND=openai_compat
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3.6:latest
```

```bash
docker compose up -d api
```

`host.docker.internal` is how the API container reaches Ollama on the host. From the host itself the same server is `http://127.0.0.1:11434`.

Production uses `LLM_BACKEND=bedrock` and Amazon Bedrock in `us-east-1`. The model id is `amazon.nova-lite-v1:0` (Nova Lite, on-demand in that region). The client calls the Converse API, times out after 30 seconds, and tries once more. A Bedrock error becomes the same “Explanations are unavailable right now” notice the Spark shows when Ollama is down. Job cards still return. Leave this Spark on `openai_compat`. Do not point production at the OpenAI API, Google Gemini, or a consumer Anthropic account. The instance setup is in [deploy.md](deploy.md).

## Check

Models installed in Ollama, and whether one is loaded:

```bash
ollama list
ollama ps
curl -sS http://127.0.0.1:11434/api/tags
```

What the API container is using:

```bash
docker exec talent-chat-api-1 printenv LLM_BACKEND LLM_BASE_URL LLM_MODEL EMBEDDING_MODEL
```

A one-line completion against the same endpoint the API uses:

```bash
curl -sS http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.6:latest","messages":[{"role":"user","content":"Reply with the word ok."}],"temperature":0}'
```

The first call after a cold start can take a while while Ollama loads the 23 GB model.

## Troubleshooting

**Chat cards appear and the answer is empty.** The page notice says explanations are unavailable. Ollama is stopped, the tag is missing, the bridge is down, or the request timed out at 90 seconds. `ollama ps` shows a loaded model after a successful call. `docker compose logs api --tail 80` shows `public chat explanation failed` when both attempts fail.

**`model 'qwen3.6:latest' not found`.** The tag is not pulled. Run `ollama pull qwen3.6:latest`, or set `LLM_MODEL` to a tag that `ollama list` already shows, then restart `api`.

**The API cannot reach the host.** Inside the container the host is `host.docker.internal` (`172.17.0.1`), port `11434`. Ollama’s own process listens on `127.0.0.1:11434` only, so the container gets connection refused and the chat shows “Explanations are unavailable right now.” The `ollama-bridge` Compose service listens on `172.17.0.1:11434` and forwards to that local port. `docker compose logs ollama-bridge --tail 20` should show the listen line.

**JSON from a crawl or résumé looks empty.** The model returned prose or an unfinished `<think>` block. The client strips think blocks and fences and then reads the outermost `{...}`. A still-invalid body is discarded and the text parser fills the profile. Rank and chat explanations are prose, so they are stored or shown as the model wrote them after the same stripping.

**Embeddings look unrelated to `qwen3.6`.** They are. `jobs.embedding` and `candidates.embedding` are 768-dimensional FastEmbed vectors. Qwen’s own embedding width is 2,048 and is not written to Postgres.
