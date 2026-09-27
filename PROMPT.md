# Cursor kickoff — Phase 1 only

Phase 1 is already built in this repository. Do not paste the text below into a chat that should keep the current recruiter matching. Later rules (line coverage, the 50% floor, the 90% strong match, and the Review screen) are in `SPEC.md` section 5 and `ARCHITECTURE.md` sections 4.3 and 4.5.

Paste everything below the line into a new Cursor agent chat only when starting Phase 1 from an empty tree. The agent works in this repository. It reads `SPEC.md` and `ARCHITECTURE.md` and implements Phase 1. It does not start Google Drive ingest, email, AWS deployment, or Marketplace packaging.

---

You are building Phase 1 of a recruiting assistant for Janus Soft Inc. Read `SPEC.md` (revision 2026-09-27) and `ARCHITECTURE.md` in this repository and follow them. `SPEC.md` wins if anything here is less specific. Start by stating that you are building Phase 1 and listing the Phase 1 acceptance checks from `SPEC.md` section 11.

## Outcome of this chat

Ship a Docker Compose stack a recruiter can run on an NVIDIA DGX Spark (arm64) and later on one small AWS Graviton instance:

1. A public page at `/chat` that searches **open jobs only**. A visitor can ask things like “jobs with Java, Python, and AWS” or “jobs in Chantilly.” Answers list real requisitions and quote the job description on file. If the description is missing, say so.
2. An admin area where a signed-in recruiter uploads one résumé (PDF, DOCX, or TXT), corrects the parsed profile, and sees ranked open jobs with a numeric score and the evidence for that score.
3. A crawler that refreshes the open-job inventory from `https://www.janus-soft.com/career` **and every `/jobs/NNNN` detail page it links to**, on a timer and on demand, with the sanity guard from `SPEC.md` section 3. Janus Soft posts new jobs regularly; new codes must appear without code changes.
4. An admin form to override a job's description with an internal one.

Public `/chat` has no code path that reads candidate records. Enforce it with a separate read-only Postgres role and an import-boundary test, and prove it with a test.

## Locked decisions

Do not revisit these.

- PostgreSQL 16 with pgvector and full-text search. No Elasticsearch, OpenSearch, Pinecone, or Redis in this phase.
- One embedding model everywhere: `nomic-ai/nomic-embed-text-v1.5` through FastEmbed, 768 dimensions, cosine distance, `search_document: ` / `search_query: ` prefixes. Token sizes exactly as in `SPEC.md` section 4 (“Token sizes”): chunks of 512 tokens with 64 overlap, whole-document vectors capped at 2,048 tokens for jobs and 1,024 for candidates, counted with the model's own tokenizer. Bake the model into the API image.
- Language-model access goes through one `LLMClient` interface. Phase 1 implements the `openai_compat` backend aimed at the DGX (`LLM_BASE_URL`, e.g. Ollama at `http://host.docker.internal:11434/v1`). Leave a `bedrock` backend stub for Phase 1.5. Strip `<think>` blocks and code fences before JSON validation. Do not call OpenAI, Google AI Studio, or a direct Anthropic API.
- Keyword and structured filters run in SQL. The model explains a retrieved set. It does not invent job ids; drop any id not retrieved.
- **Never reject a résumé or job description because of clearance or classification wording.** Nearly every résumé says TOP SECRET or TS/SCI. Parse it into admin-only `clearance` and `polygraph` levels with the synonym table in `SPEC.md` section 5. Clearance phrases are never skills.
- Redact Social Security numbers before storing text, before any LLM request, and before embedding.
- Listing line is authoritative for title and city; detail pages supply the description, mandatory/desired skills, and clearance.
- Single admin login from an environment argon2id hash, lockout per client IP. No Cognito, no public résumé upload, no email sending.
- White-label settings live in the environment (company name, careers URL). Business logic stays free of hardcoded copy where a setting exists.

## Stack

- Python 3.12, uv, FastAPI, SQLAlchemy 2 + psycopg 3, Alembic, for the API, crawler, parser, and matcher.
- Next.js (current stable, App Router), TypeScript, Tailwind, shadcn/ui, for the public chat and admin UI. Next.js rewrites `/api/*` to the API service.
- Docker Compose: `web`, `api`, `postgres` (`pgvector/pgvector:pg16`). All images build for `linux/arm64`. One README section that runs it on the DGX Spark.
- Tests: listing parser on the fixture lines in `SPEC.md` section 3; detail parser on every file in `tests/fixtures/careers/`; crawl guard; score math; clearance and polygraph mapping; SSN redaction; “TOP SECRET résumé is accepted”; token sizes; and “public client cannot query candidates” (SQL log, DB role, and import boundary). Model calls are stubbed.

## Stop condition

Stop when every Phase 1 acceptance check in `SPEC.md` section 11 passes. Report each check as pass or fail with the command or screen that proves it. Do not add Drive sync, a scheduler worker, SES, the Bedrock backend, AWS resources, or a second vector database. Leave `SPEC.md`, `PROMPT.md`, `README.md`, `ARCHITECTURE.md`, `docs/diagrams/`, and `tests/fixtures/careers/` in place.
