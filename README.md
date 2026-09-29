# Janus Soft recruiting assistant

This repository is the recruiting assistant for [Janus Soft Inc.](https://www.janus-soft.com): a public job chat and a recruiter desk. Phase 1 runs on an NVIDIA DGX Spark with Docker Compose. Google Drive ingest, email, and the AWS deployment are later phases and are not in this build.

| File | What it is |
| --- | --- |
| [README.md](README.md) | How to run Phase 1, and how the recruiter screens score a résumé. |
| [SPEC.md](SPEC.md) | Product specification. Section 5 records both the stored rank score and the line coverage the recruiter sees. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the pieces fit, including the Review screen. |
| [postgres.md](postgres.md) | Database setup: connect, read, purge, and troubleshoot `talent`. |
| [llm.md](llm.md) | The chat model (`qwen3.6` on Ollama) and the FastEmbed embedding model. |
| [workflow.md](workflow.md) | How `/chat` and `/admin` reach each API, and which container handles the call. |
| [deploy.md](deploy.md) | Phase 1.5: the public instance, Bedrock, private S3, Caddy, and backup restore. |
| [aws_deploy.md](aws_deploy.md) | AWS resources in the CloudFormation stack, and the request flow through them. |
| [PROMPT.md](PROMPT.md) | The original Phase 1 kickoff. The application is already in this repository. |
| `docs/diagrams/` | Diagram sources (`.mmd`) and rendered PNGs. Re-render with `scripts/render-diagrams.sh`. |
| `tests/fixtures/careers/` | Snapshot of the live listing and detail pages (2026-09-27), used as parser fixtures. |

## Recruiter desk

Sign in at `/admin`. The header links are Jobs, Match, and Review.

- **Jobs.** Open postings from the careers crawl. A row that leaves the careers page is closed, not deleted, and listed under “No longer on the careers page.” Each job page shows the full description, the mandatory and desired lines from the posting, and résumés that cover at least 50% of the mandatory lines.
- **Match.** Upload a PDF, DOCX, or TXT, or open a résumé already on file. Skills on the profile are tools and languages. Confirming ranks the résumé against open jobs. A card appears only when mandatory coverage is at least 50%. A strong match is at least 90%. Desired coverage is a separate percent and does not lower the mandatory score.
- **Review.** Pick one job and one résumé. The screen shows the mandatory and desired percents, the posting lines the résumé covers, and the lines it is still missing.

A tool named in the job title has to be on the résumé. A Salesforce Developer posting does not list a résumé that never names Salesforce.

## How a posting line is scored

The percentages on Jobs, Match, and Review are line coverage, computed when the page loads. They are not the stored blend of skill overlap and embedding similarity. That blend is still saved on the match row for a later outreach phase.

A mandatory or desired line counts when:

- The résumé has that line’s own tools. A vendor word repeated on every line, such as Oracle on an Exadata posting, does not by itself satisfy Oracle Linux or Exadata.
- The line offers alternatives (“such as Selenium, Cypress”, “Solr or Elasticsearch”, “Solr/Elastic”). Any one of those tools is enough.
- Words after “excluding”, “except”, or “other than” are not requirements. “Java, excluding JavaScript and Spring Boot” requires Java only.
- The line names no tool, and the résumé uses the same work words. “B.S.” counts as a bachelor’s degree when the field of study also matches.
- The line is about tuning a search cluster, and the résumé describes an Elasticsearch or Solr cluster.

Clearance wording is never a skill and never a reason to reject a file. Kubernetes and Docker are their own skills. A posting that only says “DevOps” does not match Kubernetes. CI/CD still maps to DevOps. Public chat search uses the same synonym table.

## What the original request got wrong

The product is right. The first write-up would have missed the budget, leaked candidate data, and failed skill search.

1. **Use the live careers pages, including detail pages.** `https://www.janus-soft.com/careers` returns 404. The live page is [`https://www.janus-soft.com/career`](https://www.janus-soft.com/career). Each opening links to `/jobs/NNNN`. The crawler re-reads the listing and every detail page. An admin description replaces the careers-page text and is not overwritten.
2. **Public search and admin matching are separate.** Visitors search open jobs. Recruiters upload résumés. The public assistant has no path that reads candidates: a separate Postgres role and an import-boundary test.
3. **PostgreSQL is the search index.** pgvector plus full-text search. No Elasticsearch, OpenSearch, Pinecone, or Redis.
4. **The DGX Spark builds and batches.** Production, later, is one small always-on instance in `us-east-1`. Keyword search still returns job cards when the language model is down.
5. **Résumés are PII.** Clearance text is parsed into admin-only fields. Social Security numbers are redacted before storage, logs, model calls, and embeddings. Do not upload classified documents or CUI.
6. **Email is a later phase.** Phase 1 does not send mail.
7. **Build in phases.** Phase 1 is this repository. Phase 1.5 is AWS. Drive ingest is Phase 2. The email queue is Phase 3.

## Budget

Aim for about **$50–90 per month** after the AWS move. Hard ceiling **$300**. The figures below are planning numbers, not a quote.

| Piece | Planning cost | Why it is here |
| --- | ---: | --- |
| One `t4g.medium` (web, API, worker, Postgres) | ~$25–35 | Always-on public chat |
| 30 GB gp3 disk | ~$3 | Database and app |
| S3 for résumé files and nightly `pg_dump` | ~$1–5 | Original files stay out of the database |
| Amazon SES | under $1 at this volume | Approved outreach only, Phase 3 |
| Amazon Bedrock, Nova Micro or Nova Lite class | ~$10–40 | Chat answers and document structuring |
| Route 53 | ~$1 | DNS for the chat host |
| Application Load Balancer, OpenSearch, Elastic Cloud, Pinecone, Redis, Cognito | $0 | Leave them out of v1 |

Embeddings run in-process with `nomic-ai/nomic-embed-text-v1.5` via FastEmbed, 768 dimensions. Do not mix embedding models.

## Run Phase 1 on the DGX Spark

The Compose stack is `web`, `api`, and `postgres` (`pgvector/pgvector:pg16`). Images are built for `linux/arm64`.

1. Copy the environment file and set a session secret:

   ```bash
   cp .env.example .env
   ```

   Set `SESSION_SECRET` to a long random string. Leave `ADMIN_PASSWORD_HASH` blank if you use the hash file below.

2. Create the admin password hash (argon2id). The hash contains `$` characters. Docker Compose expands `$` in the project `.env`, so either write each `$` as `$$` in `ADMIN_PASSWORD_HASH`, or store the raw hash in a file and set `ADMIN_PASSWORD_HASH_FILE`:

   ```bash
   cd api
   printf '%s\n' 'your-password' | uv run python -m app.hashpw > ../secrets/admin_password_hash
   ```

   `docker-compose.yml` mounts `secrets/admin_password_hash` at `/run/secrets/admin_password_hash` and sets `ADMIN_PASSWORD_HASH_FILE` to that path. `secrets/` and `.env` are gitignored.

3. Point the language model at the server already running on the Spark (Ollama, NIM, or vLLM):

   ```bash
   LLM_BASE_URL=http://host.docker.internal:11434/v1
   LLM_MODEL=qwen3.6:latest
   ```

   Compose adds `host.docker.internal` so the API container can reach a model server on the host. Keyword search and résumé line coverage still work when that server is stopped. Explanations then say they are unavailable.

4. Start the stack from the repository root:

   ```bash
   docker compose up -d --build
   ```

   Day-to-day start, restart, and stop commands are in [Start, restart, and stop on the DGX Spark](#start-restart-and-stop-on-the-dgx-spark).

   Public chat: [http://localhost:3000/chat](http://localhost:3000/chat)

   Recruiter sign-in: [http://localhost:3000/admin](http://localhost:3000/admin)

   `WEB_PORT` defaults to 3000. If that host port is taken, set `WEB_PORT` in `.env` and open `http://localhost:<WEB_PORT>/chat`.

   Postgres is published only on `127.0.0.1:5432`. The API port stays on the Compose network. The first start crawls `https://www.janus-soft.com/career` when `CRAWL_ON_START` is true.

## Start, restart, and stop on the DGX Spark

Run every command from the repository root (`~/spark-dev-workspace/projects/talent-chat`). The stack has four containers: `postgres`, `api`, `web`, and `ollama-bridge`. Ollama is not part of Compose. It runs on the Spark as a systemd service.

### Start

1. Make sure Ollama is up and the chat model is present:

   ```bash
   systemctl status ollama --no-pager   # start it with: sudo systemctl start ollama
   ollama list | grep qwen3.6
   ```

   If Ollama is down, the stack still starts. Keyword search and line coverage work, and chat explanations say they are unavailable.

2. Start the stack in the background:

   ```bash
   docker compose up -d --build
   ```

   `-d` returns the prompt. Without it the stack stops when you close the terminal. The first build takes several minutes. Later starts reuse the images.

   On a fresh machine, `ollama-bridge` uses the `talent-chat-api` image. If Compose tries to pull that image and fails, build it first with `docker compose build api`, then run the `up` command again.

3. Check that it is healthy:

   ```bash
   docker compose ps
   ```

   `postgres` and `api` should show `(healthy)`. `web` waits for `api` to become healthy, which can take up to a minute on the first start while the careers crawl runs.

4. Open the app. The host port comes from `WEB_PORT` in `.env` (this Spark uses `3010`; the default is `3000`):

   - Public chat: `http://localhost:3010/chat`
   - Recruiter desk: `http://localhost:3010/admin`

   From your laptop over Tailscale, use the Spark's Tailscale address instead of `localhost`, for example `http://100.65.241.97:3010/chat`. The web port listens on all interfaces. Postgres stays on `127.0.0.1` only.

### Restart

Choose the restart based on what changed.

| What changed | Command |
| --- | --- |
| Nothing; a container is stuck | `docker compose restart api` (or `web`, `postgres`, `ollama-bridge`) |
| `.env` values | `docker compose up -d` — `restart` does not reload `.env`; `up -d` recreates only the containers whose settings changed |
| Code under `api/` or `web/` | `docker compose up -d --build api web` |
| Ollama itself | `sudo systemctl restart ollama`, then `docker compose restart ollama-bridge` if chat explanations stay unavailable |
| Everything | `docker compose down && docker compose up -d --build` |

Set `CRAWL_ON_START=false` in `.env` if you restart often and don't want the API to re-crawl the careers page on each start.

### Stop

```bash
docker compose stop    # stop containers, keep them for a fast start later
docker compose down    # stop and remove containers and the network
```

Both keep your data. Jobs, matches, and admin sessions live in the `talent-chat_pgdata` volume. Uploaded résumés live in `talent-chat_uploads`.

`docker compose down -v` also deletes both volumes. That erases the database and every uploaded résumé. Use it only when you mean to start from an empty database.

### Logs and quick checks

```bash
docker compose logs -f api                  # follow API logs (Ctrl+C to stop following)
docker compose logs web --tail 50
docker compose logs ollama-bridge --tail 20 # should show the 172.17.0.1:11434 listen line
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3010/chat   # expect 200
```

If port `3010` is already taken, change `WEB_PORT` in `.env` and run `docker compose up -d`.

Do not commit real résumés, `.env`, or `secrets/`. Use synthetic résumés in git. Drive sync is not part of this build.

The public site is a separate machine. [deploy.md](deploy.md) covers the `t4g.medium`, Bedrock, the private bucket, and Caddy. Do not point the Spark compose file at that bucket.
