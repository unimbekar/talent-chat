# Janus Soft recruiting assistant

This repository is the recruiting assistant for [Janus Soft Inc.](https://www.janus-soft.com): a public job chat and a recruiter desk. Phase 1 runs on an NVIDIA DGX Spark with Docker Compose. Google Drive ingest, email, and the AWS deployment are later phases and are not in this build.

| File | What it is |
| --- | --- |
| [README.md](README.md) | How to run Phase 1, how Ingest reads a folder, and how the recruiter screens score a résumé. |
| [SPEC.md](SPEC.md) | Product specification. Section 5 records both the stored rank score and the line coverage the recruiter sees. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the pieces fit, including the Review screen. |
| [postgres.md](postgres.md) | Database setup: connect, read, purge, and troubleshoot `talent`. |
| [llm.md](llm.md) | The chat model (`qwen3.6` on Ollama) and the FastEmbed embedding model. |
| [workflow.md](workflow.md) | How `/chat` and `/admin` reach each API, and which container handles the call. |
| [deploy.md](deploy.md) | Phase 1.5: the public instance, Bedrock, private S3, Caddy, and backup restore. |
| [aws_deploy.md](aws_deploy.md) | AWS resources in the CloudFormation stack, and the request flow through them. |
| [google_deploy.md](google_deploy.md) | Proposed Google Cloud design: Cloud Run, Cloud SQL, Vertex AI, and automatic résumé import from a Shared Drive. |
| [publish_cloudflare.md](publish_cloudflare.md) | Publish at `talent.janus-soft.com` with Cloudflare: DNS move, Tunnel from the Spark or a small server, Access for `/admin`, and the Google Sites button. |
| [PRODUCT.md](PRODUCT.md) | Selling Talent Chat to other firms: features, branding settings, onboarding, gaps to close, pricing, and roadmap. |
| [PROMPT.md](PROMPT.md) | The original Phase 1 kickoff. The application is already in this repository. |
| `docs/diagrams/` | Diagram sources (`.mmd`) and rendered PNGs. Re-render with `scripts/render-diagrams.sh`. |
| `tests/fixtures/careers/` | Snapshot of the live listing and detail pages (2026-09-27), used as parser fixtures. |

## Recruiter desk

Sign in at `/admin`. The header links are Jobs, Candidates, Ingest, Find, Match, and Review. Find is described in [Find candidates](#find-candidates). Ingest is described in [Ingest résumés](#ingest-résumés).

- **Jobs.** Open postings from the careers crawl. Each job page shows the full description, the mandatory and desired lines from the posting, and résumés that cover at least 50% of the mandatory lines. Each matching candidate shows an email and a location, or “unknown” when either is missing. Check the people you want, then copy their addresses as a comma-separated list. Nothing is sent. Close a job with a note that explains why. Closed jobs stay closed when the careers page is crawled again, and the note stays with the job so you can read it later. Reopen puts the job back on the open list. A posting that disappears from the careers page is closed with the note “No longer listed on the careers page.”
- **Candidates.** The newest résumé on file for each person, with search and pages. Each row shows email and location, or “unknown”. Copy the addresses on the current page, copy every address in the desk as one comma-separated list, or check a few people and copy only those. Duplicate addresses are left out. Nothing is sent.
- **Ingest.** Point at a folder and import every résumé in it. See [Ingest résumés](#ingest-résumés).
- **Match.** Upload a PDF, DOC, DOCX, or TXT, or open a résumé already on file. An empty file, a wrong type, or a file with almost no text shows a colored message. While the résumé is ranking, a progress bar stays on the page. Skills on the profile are tools and languages. Confirming ranks the résumé against open jobs. A card appears only when mandatory coverage is at least 50%. A strong match is at least 90%. Desired coverage is a separate percent and does not lower the mandatory score.
- **Review.** Pick one job and one résumé. The screen shows the mandatory and desired percents, the posting lines the résumé covers, and the lines it is still missing. When the résumé’s role and the job’s role do not overlap, the screen says so and shared wording is not counted.

A tool named in the job title has to be on the résumé. A Salesforce Developer posting does not list a résumé that never names Salesforce. A cybersecurity résumé is not listed against a Data Scientist job on the strength of generic words such as analysis or systems.

## Ingest résumés

`/admin/ingest` reads a folder on the résumé library. The default folder is `/mnt/synology/janus-soft/Candidates`, mounted read-only at `/resumes`. The rest of `/mnt/synology/janus-soft` is mounted read-only at `/library`, so a path such as `/mnt/synology/janus-soft/Resume-Refined` or a short name such as `Upender` also works. A path outside that library is refused.

Check the folder first. The page reports how many people it found, how many older copies it will skip, and how many other files it will ignore. Then start the import.

The import keeps one résumé per person:

- It reads PDF, DOC, DOCX, and TXT, up to 10 MB. Word 97 `.doc` files are read with `antiword`. A `.doc` that is really a DOCX is read as DOCX.
- The newest file wins. When two files share a timestamp, PDF ranks above DOCX, then DOC, then TXT.
- Another spelling of the same person in that person’s folder, including `JCordoba.doc` and `JCordoba_December2022.doc`, stays one record. A folder that holds several different people, such as `Non-FSP`, keeps them separate.
- Offer letters, invoices, salary sheets, and lock files (`~$…`) stay out.

While the import runs, the progress bar shows the percent and the résumé it is reading, with the person’s name under the file. When it finishes, that file remains as the last résumé read. Imported, already on file, and unparsed counts sit under the bar.

**Unparsed résumés** lists each file that could not be read, once, with the reason. A scanned image or a corrupt Word file lands here. Save it as a text-based PDF or DOCX and import that folder again. The same person is updated in place, so a second import does not add a second candidate.

The Candidates page can start an import of the default folder. It uses the same progress bar and the same Unparsed résumés list. Nothing is emailed.

## Find candidates

`/admin/find` answers plain questions such as “Find me all candidates with ServiceNow experience who live in Maryland.”

The language model only reads the question. It turns the sentence into filters: skills, home states to include or exclude, cities, roles, and keywords. It never sees a résumé and never chooses who is listed. PostgreSQL applies the filters, so a Maryland search cannot return a Virginia résumé. The filters used are shown above the list.

Each filter the model returns is checked against the question before it is used:

- A state counts only when the question names it (“Maryland”, “MD”) or names a city in it (“near Baltimore”). A named state the model leaves out is still applied.
- A skill counts only when it is a known skill named in the question. Other phrases the question uses become keywords the résumé must contain.
- A role counts only when the question uses a role word such as “engineers” or “testers”. “ServiceNow experience” is the skill ServiceNow, not the Service Now Engineer category.
- “Outside Virginia” excludes Virginia and also leaves out résumés with no known home state.

When the model is down, a keyword parser reads the same skills, states, and roles. It does not understand negation, and the page says when it was used.

A skill matches when it is on the parsed skill list or the résumé text names it. Aliases shorter than three letters, such as Go or R, match only the skill list.

### Home state

Each candidate has a `state` column, the two-letter home state derived from `location`. It is recalculated whenever the location changes, including recruiter edits on the Match screen.

The location comes from the résumé header, the name and contact lines. The body is not read. A city there is usually an employer, school, or client site, and filing it as home puts people in the wrong state. `PAT, IP`, `CACI, VA`, and `Lotus Notes, MS` are not places. `, MS` counts as Mississippi only with a ZIP code.

Many résumés list no home address. Those candidates have no state and do not appear in a state search. The page reports how many résumés matched the other filters but have no known state. Add a location on the Match screen to include one.

After upgrading, or after a large import, re-file every unconfirmed candidate's location:

```bash
docker compose exec api /app/.venv/bin/python -m app.relocate --dry-run   # print changes, save nothing
docker compose exec api /app/.venv/bin/python -m app.relocate             # save
```

The command re-reads each header with the parser, then asks the model about rows that still have no state. It keeps the model's answer only when the city it gives appears in the lines it was shown. Confirmed profiles keep the recruiter's location. `--no-llm` skips the model pass. With `qwen3.6` on the Spark, the model pass takes about 15 seconds per candidate.

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
