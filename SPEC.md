# Specification — Janus Soft recruiting assistant

Status: source of truth for implementation.
Owner: Janus Soft Inc., Ashburn, Virginia.
Public careers page: `https://www.janus-soft.com/career` (the `/careers` path 404s).
Budget ceiling: $300 per month all-in for the Janus Soft production deployment.
Development machine: NVIDIA DGX Spark, Cursor IDE.
Revision: 2026-09-27. Amended after the architecture review in [ARCHITECTURE.md](ARCHITECTURE.md): the careers site has job detail pages, résumés are never rejected for clearance wording, the embedding model changed to `nomic-ai/nomic-embed-text-v1.5`, and the review fixes (crawl guard, public DB role, polygraph level, per-IP lockout, Phase 1.5 deploy) are part of this spec.

This document is written so a coding agent can implement it without inventing a platform. Phases are sequential. A chat implements one phase.

## 1. Product

Recruiters at a small consultancy need two things:

- A public link on the company website where anyone can search open jobs by skill, city, or keywords.
- A private way to drop in a candidate résumé and see which open jobs fit, with the reason.

Later, the same system notices new résumés in a Google Drive folder and, on a schedule, drafts emails to candidates who already agreed to be contacted.

The first customer is Janus Soft. The code is white-label so it can later be sold. Version 1 is one tenant, configured by environment variables. Multi-tenant billing, AWS Marketplace metering, and FedRAMP are out of scope.

### Users

| User | Enters through | Can do | Cannot do |
| --- | --- | --- | --- |
| Visitor | `/chat`, linked or iframed from the company site | Search open jobs by skills, city, keywords, requisition code | See candidates, emails, phones, clearance, citizenship, or match history |
| Admin | `/admin`, password | Upload a résumé, edit the parsed profile, rank jobs, edit job descriptions, see ingest status in later phases | Send email in Phase 1 |
| Candidate | Nowhere in v1 | Receive an approved email in Phase 3, and unsubscribe | Log in, upload their own résumé, or chat about other people |

There is no public résumé upload. Candidates keep applying through the existing company process. The Drive folder is an admin inbox.

## 2. Operating constraints

### Data that may be stored

Candidate PII that recruiters already keep: name, email, phone, work history, skills, city, citizenship claim, and clearance claim as written by the candidate. Job descriptions the company is allowed to store internally.

### Clearance wording never blocks an upload

Almost every Janus Soft candidate lists an active Top Secret, TS/SCI, or polygraph clearance. That is expected résumé data, not a reason to refuse a file. There is **no** keyword, banner, or classification check that rejects a résumé or a job description. Words such as TOP SECRET, SECRET, TS/SCI, or CLASSIFIED are parsed into the admin-only `clearance` and `polygraph` fields (section 5) and otherwise treated as ordinary text.

Operators remain responsible for not uploading actual classified documents or CUI. The system does not try to detect them, and the admin UI footer says so in one sentence.

### Data that must not be stored

- Social Security numbers, passport numbers, and bank account numbers. Detect and redact SSN patterns (`###-##-####` and 9 digits labeled SSN) before the text is written to the database, logs, a language-model request, or an embedding request. Keep the original file in private storage the admin can delete.
- Health information, beyond what a résumé happens to contain. Do not add fields for it.

Candidate clearance, polygraph, and citizenship are admin-only columns. They never appear in public API responses, public prompts, or outreach email.

### Where data lives

Production region is `us-east-1` only.

| Path | Destination |
| --- | --- |
| Production chat and one-time document structuring | Amazon Bedrock in `us-east-1`, a Nova Micro or Nova Lite class model for chat. A stronger Bedrock model is allowed only for the one-time structuring pass, and only if the monthly cap allows it. |
| Development chat on the DGX Spark | OpenAI-compatible server on that machine (NVIDIA NIM, vLLM, or Ollama). Use synthetic résumés. |
| Embeddings, dev and prod | In-process FastEmbed, model `nomic-ai/nomic-embed-text-v1.5`, 768 dimensions, 8,192-token context, cosine. Prefix stored text with `search_document: ` and queries with `search_query: `. The model id is an env var defaulting to that value. Changing it requires a full re-embed. Token sizes are in section 4. |
| Files | S3 bucket, SSE-S3, block public access. Local disk in development. |
| Secrets | Environment variables or a local `.env` that is gitignored. No credentials in the repo. |

Do not configure the OpenAI API, Azure OpenAI outside this AWS account, Google Gemini, or a consumer Anthropic account for production. Bedrock is the production model path because the text stays in-region and is not used to train the base model.

Language-model access goes through one `LLMClient` interface with two backends selected by `LLM_BACKEND`:

- `openai_compat` for the DGX (Ollama, vLLM, or NIM `/v1/chat/completions`). Phase 1 implements this one.
- `bedrock` for production, using the Bedrock Converse API, because Nova models are not reachable through the OpenAI wire format. Phase 1.5 implements this one.

Both backends strip `<think>…</think>` blocks and Markdown code fences before JSON validation, use a 30-second timeout, and retry once. Tests use a stub backend.

This deployment is a commercial tool for candidate PII. It is not authorized for classified processing and it is not a FedRAMP package. Say that in the admin UI footer in one sentence so operators are not misled.

### Reliability

- Skill, city, and requisition search run as SQL. They return results when the language model is down, with a short notice that explanations are unavailable.
- The public site must not depend on the DGX Spark being powered on.
- Job ids in any answer must exist in the `jobs` table at answer time. If the model mentions an id that was not retrieved, drop it and do not display it.

### Money

Stay inside the cost table in `README.md`. Do not add an Application Load Balancer, a managed vector database, Redis, a GPU instance, or Cognito in order to finish a phase. TLS can be Caddy on the instance or a Cloudflare proxy in front of one origin port.

## 3. What the careers page actually is

The site has two kinds of page, and the crawler reads both.

1. **Listing page** `https://www.janus-soft.com/career` (Google Sites). A flat list under “Open Positions,” grouped by dashed separator lines. Each line is a link to its detail page. Janus Soft posts new jobs here regularly and edits or removes old ones, so the crawler treats the page as a live inventory, not as a fixture.
2. **Detail pages** `https://www.janus-soft.com/jobs/NNNN`, one per listing line (`A1001` links to `/jobs/1001`, `N3011` to `/jobs/3011`). Each has the published job description, usually under the headings **Job Description**, **Mandatory Skills**, and **Desired Skills**, with items written as `Label:` followed by prose. The clearance requirement appears as a `Clearance:` or `Security Clearance:` item under Mandatory Skills (for example “Active TS/SCI with Full Scope Polygraph.”).

Snapshot of 2026-09-27: 19 open positions, 19 detail pages; 15 have all three headings, 3 lack the Job Description heading, and 1 (`/jobs/2008`) has no headings at all. HTML snapshots of the listing and every detail page are in `tests/fixtures/careers/`. Use them as parser fixtures; never hit the live site in unit tests.

Listing lines as of 2026-09-27 (parser fixtures, store them as tests):

```
A1001 - UI/UX Developer - Chantilly VA
A1002 - Senior Infrastructure Engineer - Chantilly VA
A1003 - Software Developer - Herndon VA
A1004 - Mid Level Systems Engineer - UUE - Tysons VA
A1005 - Platform Engineer - Herndon VA
A1006 - Infrastructure Engineer - Herndon VA
A1007 -Palantir Data Engineer - Chantilly VA
G2001 - Salesforce Developer - Mclean VA (MOON1136-08)
G2002 - Data Scientist - Mclean VA (STAR 2330-04)
G2003 - AWS Cloud Engineer - Mclean VA (STAR 1435-02)
G2004 -Software Engineer - Mclean VA (STAR 234-01)
G2005 -Systems / Oracle Administrator - Mclean VA (STAR 2439-01)
G2008 - Senior Software Developer - Mclean VA (STAR -1466-02)
G2010 - Systems Engineer - Chantilly VA (STAR 1326-01)
N3001 -Data Architect - Mclean VA (23-39311)
N3010 -Multi Cloud Engineer - Chantilly VA (RV-003678-Open)
N3011 Full Stack Software / Big Data Engineer (424c)- Chantilly VA
N3012 Software Quality Assurance Tester (RAP-047)- Chantilly VA
L4001 - Cyber Security Engineer - Herndon VA
```

Listing parser rules:

- Primary key is the leading requisition code matching `^[A-Z][0-9]{3,5}$` when present. `N3011` has no hyphen after the code; still capture it.
- A leading status word before the code (`Proposal - G2001 - …`, `Upcoming - …`) sets status `proposal` or `upcoming` and is removed before parsing the rest. Lines containing `upcoming` anywhere are status `upcoming`. Everything else seen on the page is `open`.
- A parenthetical is `external_req` wherever it sits (end of line, or before the city as in `N3011 … (424c)- Chantilly VA`). Examples: `MOON1136-08`, `MOON 1150`, `STAR 2330-04`, `STAR -1466-02`, `23-39311`, `RV-003678-Open`, `424c`, `RAP-047`. Store it as an opaque string. It may contain spaces. Do not infer a customer from it. It is admin-only.
- A short all-caps token that is not a city (example: `UUE`) is `program_tag`. Admin-only.
- The city segment is the last segment that matches the known-location list. Normalize `Mclean` to `McLean, VA`, and the others to `Chantilly, VA`, `Herndon, VA`, `Tysons, VA`, `Dulles, VA`, `Ashburn, VA`. The list is configuration (`configs/locations.yaml`), not code scattered through the parser.
- `site_job_id` is the number from the line's `/jobs/NNNN` link. If a line has no link, fall back to the digits of the requisition code and flag `needs_review`.
- Dashed separator lines and blank lines are ignored.
- Keep the raw line in `source_line`. When parsing is ambiguous, still save the raw line and flag `needs_review` for the admin. Never drop a line because the parser is unsure.
- The listing line is authoritative for title and city. Some detail pages still carry a stale heading from an earlier posting (for example `/jobs/1001` shows an old “Mid Level Software Engineer - Tysons VA” heading above the current “UI/UX Developer - Chantilly VA”). Ignore detail-page headings for title and city.

Detail parser rules:

- Page text runs from the job heading to the Google Sites footer (“Google Sites”, “Report abuse”). Navigation text is dropped.
- Split by the headings Job Description, Mandatory Skills, Desired Skills (case-insensitive; also accept Required Skills, Preferred Skills, Responsibilities, Qualifications). Text before the first skills heading is the description.
- Each `Label:` item under Mandatory Skills becomes a must-have entry; under Desired Skills a nice-to-have entry. The label plus its prose is kept as a quote for explanations.
- A `Clearance:` or `Security Clearance:` item (or a sentence such as “Must hold an active TS/SCI…”) goes to `clearance_required` and `polygraph_required` through the clearance synonym table (section 5). It is never stored as a skill and never shown as a skill chip.
- If no headings are found, keep the whole body as the description, flag `needs_review`, and let the model structuring pass extract skills.
- Store the result as `description_text` with `description_source = careers_page` and a `description_hash`.

Crawl behavior:

- Fetch the listing on a timer (`CRAWL_INTERVAL_HOURS`, default 6) and on demand from the admin jobs screen. New postings therefore appear within one interval, or immediately after “Recrawl now.”
- Fetch every detail page linked from the listing on each crawl (about 20 small pages). Send a descriptive `User-Agent`, wait about 1 second between requests, and time out after 20 seconds per page.
- Upsert by requisition code. Update `last_seen_at`. Re-structure and re-embed a job only when its `description_hash` changed.
- **Sanity guard.** If the listing fetch fails, or parses to 0 rows, or to fewer than 50% of the currently open rows, record a crawl error visible on the admin jobs screen and change nothing. Otherwise, codes missing from the latest fetch become `closed`. Do not delete the row. Match history points at the row. A closed code that reappears is reopened.
- A failed detail fetch keeps the previous description and flags the row; it does not blank it.
- The crawler writes title, location, tags, status, raw line, and the published description. It does not invent skills or a clearance requirement beyond what the page states.

### Job descriptions: two sources

1. **Careers page** (`description_source = careers_page`), captured by the crawler. This is the default and covers almost every job.
2. **Admin override** (`description_source = admin`). Admins can paste text or upload PDF/DOCX on the job row, for example a fuller internal description. An admin description wins over the careers-page text and is not overwritten by later crawls. Phase 2 also watches a Drive folder of descriptions named by requisition code (`A1001.pdf`), which count as admin descriptions.

When neither source has text:

- Public chat can still filter by title words, city, and requisition code.
- The job card shows “Full description not on file.”
- Ranked résumé match marks confidence `low` and explains that the score is title-only.
- The job is excluded from automatic outreach drafts in Phase 3.

Description structuring, once per change:

- Extract text.
- Redact SSNs (section 2). There is no classification check.
- Take the deterministic Mandatory/Desired/Clearance split from the detail parser. Ask the model for a JSON profile: `must_have_skills[]`, `nice_to_have_skills[]`, `clearance_required` (null if unstated), `polygraph_required` (null if unstated), `location`, `summary` (under 80 words, only facts present in the text). Pass the parser's split in the prompt so the model normalizes it rather than inventing.
- Validate JSON. On failure, keep the parser's split, store the raw text, and leave anything else empty rather than guessing.
- Normalize skills through the synonym table (section 6). Remove any clearance phrase that ended up in a skills list.
- Embed per section 4, "Token sizes."

`clearance_required` and `polygraph_required` are admin-only columns. The public chat may say a posting is open in a city. It does not volunteer clearance. The clearance sentence is part of the published posting, so if a visitor asks whether a job requires a clearance, answer by quoting that sentence from the description on file, and nothing else.

## 4. Résumé ingest (admin upload in Phase 1, Drive in Phase 2)

Accepted types in Phase 1: PDF, DOCX, TXT, up to 10 MB. Legacy `.doc` is rejected with the message “Save as DOCX or PDF and upload again” until a later phase adds `antiword` to the image. Also reject images, scanned PDFs with no text layer, and password-protected files, each with a clear message. **A résumé is never rejected because of clearance or classification wording** (section 2).

Pipeline, same for upload and later Drive sync:

1. Hash the bytes (SHA-256). If the hash matches an existing candidate file, report “already ingested” and do not duplicate.
2. Extract text. If extraction returns almost nothing (under about 200 characters), stop and tell the admin the file needs a text-based export.
3. Redact SSNs. Write an audit row (action and outcome only, never résumé text).
4. Store the original file privately. Store the redacted text.
5. Ask the model once, with the redacted text, for a JSON profile: `full_name`, `email`, `phone`, `location`, `skills[]` with a `years` number when the résumé supports it, `titles[]`, `clearance` (raw phrase, null if unstated), `polygraph` (raw phrase, null if unstated), `citizenship` (null if unstated), `summary` under 120 words using only résumé facts. Code then maps `clearance` and `polygraph` to levels with the section 5 synonym table.
6. Show the profile on a review screen. The admin can edit any field and must confirm before the match is saved. The confirmed profile is what gets embedded. The review screen also has **Delete**, which removes the file, text, chunks, embeddings, and matches.
7. Embed and chunk per "Token sizes" below. Matching uses the summary vector plus skill overlap. Explanations quote chunks.

### Token sizes

Measured on the 2026-09-27 careers snapshot: the 19 job detail pages are 214–585 tokens each (median 363). A two-to-five-page résumé is typically 1,000–3,000 tokens. The previous default model, `BAAI/bge-base-en-v1.5`, reads only 512 tokens and silently drops the rest, which would cut the longest job descriptions and most of every résumé. The spec therefore uses `nomic-ai/nomic-embed-text-v1.5` (Apache-2.0, 137M parameters, 768 dimensions, 8,192-token context, supported by FastEmbed on CPU and arm64).

| Item | What is embedded | Max tokens | Chunking |
| --- | --- | ---: | --- |
| Job vector (`jobs.embedding`) | `search_document: ` + title + city + structured summary + full description | 2,048 | none; whole text in one vector |
| Job chunks (`job_chunks`) | description sections | 512 | 512 tokens, 64 overlap, split on section and paragraph boundaries first |
| Candidate vector (`candidates.embedding`) | `search_document: ` + confirmed summary + titles + skills | 1,024 | none |
| Candidate chunks (`candidate_chunks`) | redacted résumé text | 512 | 512 tokens, 64 overlap, split on section and paragraph boundaries first |
| Public query | `search_query: ` + visitor text | 256 | none |

Rules:

- Count tokens with the embedding model's own tokenizer (the `tokenizer.json` shipped with the model), not words or characters.
- Chunks stay at 512 even though the model reads 8,192: they are the evidence quoted to recruiters and to the model, and shorter chunks give precise quotes and cheaper CPU embedding on the production instance.
- The 2,048 and 1,024 caps bound CPU time on a `t4g.medium`. Text beyond the cap is dropped from the vector only; the full text stays in the database and in the chunks.
- Allowed alternatives, all FastEmbed-supported and 768-dimensional so the schema does not change: `jinaai/jina-embeddings-v2-base-en` (8,192 context), or `BAAI/bge-base-en-v1.5` (512 context; if chosen, set job and candidate vector caps to 512 and chunks to 400 tokens with 50 overlap). Switching models requires a full re-embed via `python -m app.reembed`.
- Do not use Ollama's `nomic-embed-text` for stored vectors. It is a different runtime and its vectors are not guaranteed to be identical to FastEmbed's. One runtime everywhere.

Drive import (Phase 2) sets `outreach_opt_in` to false. Uploading a file into a folder is not consent to be emailed. Drive-imported profiles have status `pending_review`: they can be found by keyword but join ranking only after an admin confirms them, the same as uploads.

Idempotency key for Drive is `google_file_id` plus content hash. A new revision updates the same candidate row and re-embeds. It does not create a second person.

### Google Drive (Phase 2)

- A Google Cloud service account, folder shared with that account. Folder id in `DRIVE_FOLDER_ID`.
- Poll `changes.list` with a stored page token every 10 minutes. Renew the start token when Google invalidates it.
- Process Google-native Docs by exporting to DOCX or text. Skip files not in the allowed types.
- A second folder, `JOB_DESCRIPTION_FOLDER_ID`, maps filenames to requisition codes.
- Push notifications (`changes.watch`) are optional later. They expire within seven days and need a verified HTTPS endpoint. Polling is the supported design.
- One-time backfill command walks the folder and runs the same pipeline. It is safe to re-run.

## 5. Matching

Hard filters and scores are code, not a prompt.

### Skill score

```
job_skills = must_have ∪ nice_to_have
overlap = |candidate.skills ∩ job_skills|
must_hit = |candidate.skills ∩ must_have| / max(|must_have|, 1)
skill_score = 0.7 * must_hit + 0.3 * (overlap / max(|job_skills|, 1))
```

If `job_skills` is empty, `skill_score` is null and confidence is `low`.

### Semantic score

Cosine similarity between the candidate summary embedding and the job summary embedding, mapped from `[-1, 1]` to `[0, 1]` by `(cosine + 1) / 2`. Persist the raw cosine as well. Real embedding cosines cluster in a narrow band, so mapped values bunch high; the Phase 3 `OUTREACH_MIN_SCORE` must be calibrated on real Phase 1 match data before drafts are enabled.

### Final score

When `skill_score` is present:

```
final = 0.55 * skill_score + 0.45 * semantic
```

When it is null:

```
final = semantic
confidence = low
```

Persist `skill_score`, `semantic`, `final`, `confidence`, and the overlapping skill names.

### Recruiter line coverage

Jobs, Match, and Review show a second pair of numbers, computed at read time from the posting’s mandatory and desired lines and the résumé text. These are the percentages on screen. `final` stays on the match row for a later outreach phase and is not the number on the card.

A line counts when the résumé has that line’s own tools. A vendor word shared by every line in the section does not satisfy a more specific tool on one line. Alternatives (“such as”, “or”, “Solr/Elastic”) count when any one named tool is present. Words after “excluding”, “except”, or “other than” are not requirements. A line with no tool counts when the résumé uses the same work words; “B.S.” counts as a bachelor’s degree when the field matches. A search-cluster line counts when the résumé describes an Elasticsearch or Solr cluster.

Mandatory coverage below 50% is hidden on Match and on the job’s candidate list. A strong match is at least 90% of the mandatory lines. Desired coverage is shown separately and does not lower the mandatory percent. If the job title names a tool the résumé does not have, the candidate list omits that résumé and Review says which title tool is missing.

### Clearance filter

Two ordered scales, lowest to highest:

- Clearance: `none`, `public_trust`, `secret`, `ts`, `ts_sci`.
- Polygraph: `none`, `ci`, `full_scope`.

Almost every Janus Soft job requires “Active TS/SCI with Full Scope Polygraph,” so the polygraph level matters as much as the clearance level.

Seed clearance synonyms (admins can add rows; matching is case-insensitive on word boundaries):

| Phrase contains | Clearance | Polygraph |
| --- | --- | --- |
| `TS/SCI`, `TS-SCI`, `Top Secret/SCI`, `TOP SECRET SCI` | `ts_sci` | — |
| `Top Secret`, `TS` (standalone, not followed by `/SCI`) | `ts` | — |
| `Secret` (not preceded by `Top`) | `secret` | — |
| `Public Trust` | `public_trust` | — |
| `Full Scope Poly`, `Full-Scope Polygraph`, `FSP`, `Lifestyle Poly` | — | `full_scope` |
| `CI Poly`, `Counterintelligence Polygraph` | — | `ci` |
| `Poly` or `Polygraph` alone | — | `unknown` |

- Unknown phrasing stays `unknown` and is shown to the admin for correction. Do not guess upward.
- For the ranked list, a job that requires a higher clearance or polygraph than the candidate holds is still visible, with reason `clearance_short`. It is excluded from Phase 3 drafts.
- `unknown` candidate clearance or polygraph versus a job that requires one is `clearance_unknown`: visible to admin, excluded from drafts.
- Public responses omit this filter entirely.

Location is a soft signal in Phase 1 (show it, do not drop the job). Phase 3 drafts require the candidate city to match the job city, or the candidate profile to say they will work that site, unless the admin overrides that job.

### Explanations

The model receives only the retrieved job fields the user is allowed to see, the overlapping skills, and up to four short quotes from the résumé and four from the description. It writes 2–4 sentences. It does not add skills that are absent from those quotes. Temperature 0.2. If the model call fails, show the scores and quotes without prose.

Public explanations use job quotes only. They do not receive résumé text, because there is no résumé.

## 6. Skill synonyms

Seed a table. Admins can add rows. Matching uses the canonical name.

| Canonical | Also matches |
| --- | --- |
| Java | Java, J2EE, Spring, Spring Boot |
| Python | Python, PySpark |
| JavaScript | JavaScript, TypeScript, Node.js, Node, React |
| AWS | AWS, Amazon Web Services, EC2, S3, Lambda |
| Palantir | Palantir, Foundry, Gotham |
| Salesforce | Salesforce, Apex |
| ServiceNow | ServiceNow, Service Now |
| Oracle | Oracle, Oracle DB |
| Spark | Spark, PySpark, Apache Spark |
| DevOps | DevOps, CI/CD |
| Kubernetes | Kubernetes |
| Docker | Docker |
| Cybersecurity | Cyber, Cybersecurity, Information Security |

A skill string that matches none of these is kept as a free tag, lowercased, and compared by equality. Do not let the model invent a taxonomy entry during a chat turn.

Matching rules:

- One alias may map to several canonical skills (`PySpark` gives both Python and Spark). Store the table as `(alias, canonical)` rows, not one canonical per alias.
- Match aliases on word boundaries, case-insensitively. `Spring` must not match “springboard”; `Node` must not match “nodes”; `S3` must not match “S30”.
- Clearance and polygraph phrases are never skills (section 5).

Public query parsing for “find jobs with Java, Python, and AWS in Chantilly”:

1. Detect known skills and cities with the synonym table and the location list. This step is deterministic.
2. Remaining words become a full-text query against title and description.
3. Retrieve with SQL (`skills &&`, location equality when a city was named, `tsvector` for the rest, status = `open`).
4. If a description embedding exists, rerank that SQL set by cosine similarity to the query embedding. Do not pull jobs the SQL filters excluded.
5. Pass the top 8 to the model for a short answer with requisition codes.

## 7. Public chat behavior

Example requests it must handle:

- “Jobs with Java, Python, and AWS.”
- “What is open in Chantilly?”
- “Tell me about A1007.”
- “Which of these is senior?”

Refusals, exact behavior:

- Any ask for candidates, résumés, phone numbers, emails, who applied, clearance rosters, or “who do you have for this job” gets a single refusal: the assistant can search published jobs only. No tool call against candidate tables.
- Salary, benefits, and citizenship requirements are answered only by quoting the description on file. If absent: “That is not in the posting we have on file.” Do not recite the public benefits page from memory.
- The assistant does not claim Janus Soft can sponsor a clearance.

Conversation state:

- The server stores no chat history. Each request carries the visitor's message plus `prior_codes[]`, the requisition codes shown in the previous answer (at most 8). Follow-ups such as “Which of these is senior?” re-read those rows from `jobs` and answer over them only.
- Refusal detection runs before any database call.

UI:

- Standalone page and a layout that can be linked from `janus-soft.com`. Set `Content-Security-Policy: frame-ancestors` to the company origin from env, plus `'self'`.
- Job result as a card: requisition code, title, city, overlapping or matched skills, confidence, link anchor to the source line. Description quote expands on click.
- Empty state when the crawl has not run: “Job list has not been loaded yet.”
- Error state when the database is down, distinct from zero results.
- Works on a phone-width browser and on a desktop browser. The public page is the one visitors will actually use on a phone.
- Rate-limit the public chat by IP (for example 30 turns per hour). Return a plain message when limited. Behind Cloudflare or Caddy, take the client IP from the header named in `TRUSTED_PROXY_HEADER` (`CF-Connecting-IP` or `X-Forwarded-For`) only when the request comes from the proxy; otherwise use the socket address. An in-memory limiter is enough for one instance.

Suggested visual tone: a quiet recruiting desk for a consultancy that sells to the government. Off-white background, one dark green or navy accent, readable type, real requisition codes on the cards. No stock-photo hero, no “welcome to your AI assistant,” no gradient wallpaper.

## 8. Admin UI

Phase 1 screens:

1. **Sign in.** One shared admin password, argon2id hash in env, httpOnly session cookie, SameSite Lax, 12-hour expiry. Logout. Lock out **per client IP** for 15 minutes after 8 failures (a global lockout would let anyone lock the recruiter out). Ship `python -m app.hashpw` to generate the hash. Argon2 hashes contain `$`, so `.env.example` documents writing them as `$$` for Docker Compose, or use `ADMIN_PASSWORD_HASH_FILE`.
2. **Jobs.** Open rows from the crawl. Closed rows stay in the database and appear under “No longer on the careers page.” Each job page shows the full description, editable mandatory and desired lines taken from the posting, city, clearance, and an internal description that replaces the careers-page text. It also lists résumés at or above 50% mandatory coverage, with a link to Review for that pair.
3. **Match.** Upload PDF, DOCX, or TXT, or open a résumé already on file. A duplicate file opens the existing candidate. Review parsed fields. Skills are tools and languages. Confirm ranks open jobs. Each card shows mandatory coverage and desired coverage. Cards under 50% mandatory are hidden. A strong match covers at least 90% of the mandatory lines.
4. **Review.** Choose one job and one résumé. Show both percents, the posting lines covered, and the posting lines still missing.

Phase 2 adds:

5. **Ingest.** Last poll time, last error, files imported, files rejected, button to poll now, button to run backfill.
6. **Candidates.** Search by skill and name. Edit profile. Toggle `outreach_opt_in`. Delete a candidate, which deletes file, chunks, embeddings, and match rows.

Phase 3 adds:

7. **Outreach.** Draft queue, approve, skip, interval in days (default 7), per-job “allow send without per-message approval” defaulting off. Unsubscribe log.

Every admin mutation writes `audit_log` (who, action, candidate id or job id, timestamp). Do not write résumé text into the log.

## 9. Outreach agent (Phase 3)

This is one scheduled function in the worker process, not a multi-agent framework.

Every `outreach_interval_days` (default 7), and when an admin clicks “Run now”:

1. Consider jobs with status `open`, a non-empty description, and confidence not solely title-based.
2. For each job, take candidates with `outreach_opt_in = true`, email present, hard filters passed (clearance and polygraph known and sufficient, city compatible), `final` at or above `outreach_min_score` (default 0.62, recalibrated on Phase 1 data before first use), and no outreach row for that pair in the past 90 days.
3. Cap 25 new drafts per run.
4. Write status `draft` with subject and body from a template, not from an open-ended model generation. The template inserts title, city, up to five overlapping canonical skills, the careers URL, reply-to `contact@janus-soft.com`, and the company postal address: Janus Soft Inc., 43300 Southern Walk Plaza, Ashburn, VA 20148. Omit `external_req`, `program_tag`, customer names, and clearance.
5. Admin approves or skips. Approved rows send through Amazon SES. Set `List-Unsubscribe`. Sending flips status to `sent`.
6. A footer link hits a public tokenized unsubscribe route and sets `outreach_opt_in` false. Further drafts are not created.
7. The worker records `last_run_at` so a restart does not double-send.

Do not add SMS. Do not email a person because their résumé merely exists in Drive.

## 10. Architecture

```
janus-soft.com/career  --->  crawler (every 6h)
Google Drive folder    --->  poller (every 10m, Phase 2)
                                      |
                                      v
Visitor --> /chat --> web (Next.js) --> api (FastAPI) --> Postgres + pgvector
Admin   --> /admin                      |
                                        +--> local files or S3
                                        +--> LLM client (DGX in dev, Bedrock in prod)
                                        +--> FastEmbed (same model everywhere)
worker: crawl timer, Drive poller (Phase 2), outreach timer (Phase 3)
```

Compose services in Phase 1: `web`, `api`, `postgres`. The worker can be a command in the `api` image (`python -m app.worker`) started as a second service when Phase 2 begins. Phase 1 can trigger crawl from the API process on a timer so the demo stays one container plus Postgres, plus the web container.

Implementation conventions:

- The browser talks only to `web`. Next.js rewrites `/api/*` to the `api` service, so the admin cookie is same-origin and the API port is not published in production.
- SQLAlchemy 2 with psycopg 3, Alembic migrations. The first migration creates the `vector` extension, both database roles, and HNSW cosine indexes on the embedding columns.
- **Public/admin boundary is enforced, not just tested.** Two Postgres roles: `app_public` can `SELECT` only `jobs`, `job_chunks`, `skill_synonyms`, and public `settings`; `app_admin` owns everything. Public routes use `DATABASE_PUBLIC_URL` (the `app_public` role). Code under `app/public/` must not import `app/admin/` or the candidate repository, and a test fails the build if it does.
- Images are built for `linux/arm64` (DGX Spark and AWS Graviton). The Next.js bundle is built during the image build, not on the instance.
- The FastEmbed model is downloaded at image build time into the image, so a container start does not depend on Hugging Face being reachable.

### Environment

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres, `app_admin` role |
| `DATABASE_PUBLIC_URL` | Postgres, `app_public` role, used by public routes |
| `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD_HASH_FILE` | Admin session (argon2id) |
| `SESSION_SECRET` | Cookie signing |
| `COMPANY_NAME` | Default `Janus Soft Inc.` |
| `CAREERS_URL` | Default `https://www.janus-soft.com/career` |
| `CRAWL_INTERVAL_HOURS` | Default 6 |
| `PUBLIC_FRAME_ANCESTOR` | Origin allowed to iframe `/chat` |
| `TRUSTED_PROXY_HEADER` | Blank locally; `CF-Connecting-IP` or `X-Forwarded-For` behind a proxy |
| `LLM_BACKEND` | `openai_compat` (DGX, Phase 1) or `bedrock` (production, Phase 1.5) |
| `LLM_BASE_URL` | DGX OpenAI-compatible endpoint, e.g. `http://host.docker.internal:11434/v1` for Ollama |
| `LLM_MODEL` | Chat model name, e.g. `qwen3.6:latest` on the DGX, a Nova Lite model id on Bedrock |
| `LLM_API_KEY` | Blank on a local server that does not require one |
| `AWS_REGION` | `us-east-1` (Phase 1.5) |
| `EMBEDDING_MODEL` | Default `nomic-ai/nomic-embed-text-v1.5` |
| `FILE_DIR` or `S3_BUCKET` | Original uploads |
| `DRIVE_FOLDER_ID` | Phase 2 |
| `JOB_DESCRIPTION_FOLDER_ID` | Phase 2 |
| `SES_FROM_ADDRESS` | Phase 3 |
| `OUTREACH_INTERVAL_DAYS` | Phase 3, default 7 |
| `OUTREACH_MIN_SCORE` | Phase 3, default 0.62 |

### Suggested tables

`jobs`, `job_chunks`, `candidates`, `candidate_chunks`, `skill_synonyms`, `matches`, `outreach`, `ingest_events`, `audit_log`, `settings`, `admin_sessions`.

`jobs.embedding` and `candidates.embedding` are `vector(768)`. Full-text uses `tsvector` on title + description, and on the redacted résumé. Index the filters you actually query: status, location, requisition code, skills array, `outreach_opt_in`.

## 11. Phases and acceptance

### Phase 1 — public search and admin match

Build the stack, schema, career parser, crawler, description upload, public `/chat`, admin login, résumé upload, review screen, and ranker.

Done when:

- Parser tests pass on every fixture line in section 3, including `A1007 -Palantir…`, `N3011` without a hyphen, `(STAR -1466-02)`, a `Proposal - …` prefix, and `(MOON 1150)` with a space.
- Detail-parser tests pass on every HTML file in `tests/fixtures/careers/`: the description is captured; the clearance item lands in `clearance_required` = `ts_sci` and `polygraph_required` = `full_scope`, and never in a skills list; `/jobs/1001` keeps the listing title “UI/UX Developer” despite the stale heading; `/jobs/2008` (no headings) is kept whole and flagged `needs_review`.
- A live crawl of `https://www.janus-soft.com/career` loads every current listing line with its detail description. Re-running the crawl does not duplicate codes. A code removed from a fixture listing becomes `closed`; a new code added to it appears as `open`.
- Crawl guard: a fixture listing that parses to 0 rows, or an HTTP error, closes nothing and shows the error on the admin jobs screen.
- “Jobs in Chantilly” returns only Chantilly rows from the database.
- “Java and AWS” returns only jobs whose stored skills or description text contain those skills after synonym normalization. A job with no description from either source is labeled “Full description not on file” and low confidence.
- Uploading a synthetic résumé that says Java, Python, AWS, and Chantilly ranks a job with those skills above an unrelated network-engineer title. The screen shows both score components.
- **A synthetic résumé containing “Active TOP SECRET/SCI with Full Scope Polygraph” and a separate line reading `TOP SECRET` is accepted**, stored, and parsed as clearance `ts_sci`, polygraph `full_scope`.
- SSN in a synthetic résumé is absent from the database text, the LLM request, and the embedding input.
- A 3,000-token synthetic résumé produces one candidate vector and 512-token chunks with 64 overlap, counted with the embedding model's tokenizer.
- An automated test calls the public search function and HTTP route with SQL logging on and asserts no statement touches `candidates`; the `app_public` role gets “permission denied” on `SELECT * FROM candidates`; the import-boundary test passes.
- A public prompt “list the candidates who know Java” returns the refusal and does not include fixture candidate names.
- With the LLM endpoint stopped, public search still returns job cards with “Explanations are unavailable right now.”
- `/chat` is usable at 375px width and at 1280px width.
- `docker compose up` on the DGX Spark starts the stack. The README states the local URL, how to create the admin password hash, and how to point `LLM_BASE_URL` at the local model server.

### Phase 1.5 — AWS deploy (before the public link goes live)

Build the `bedrock` LLM backend, an S3 file adapter (SSE-S3, public access blocked), Caddy or Cloudflare TLS in front of `web`, `PUBLIC_FRAME_ANCESTOR` set to `https://www.janus-soft.com`, and a nightly `pg_dump` to S3 with 14-day retention.

Done when:

- The stack runs on one `t4g.medium` in `us-east-1` from the same arm64 images used on the DGX.
- `/chat` answers from Bedrock; stopping Bedrock access still returns SQL results with the unavailable notice.
- A restore of last night's dump into a scratch database succeeds and is documented.
- The DGX Spark can be powered off without affecting the public URL.

### Phase 2 — Drive folder

Done when:

- Dropping a new PDF into the configured folder creates one candidate within two poll intervals, without a duplicate on the next poll.
- Replacing the file content updates the same candidate.
- A rejected file (unsupported type, no text layer, password-protected) appears on the ingest screen with a reason. Files are never rejected for clearance wording.
- Drive imports land as `pending_review` and do not appear in rankings until confirmed.
- Backfill of a folder is safe to run twice.
- `outreach_opt_in` is false for every Drive import until an admin changes it.

### Phase 3 — scheduled drafts and email

Prerequisites: SES out of sandbox for production, `janus-soft.com` verified in SES with SPF, DKIM, and DMARC, bounce and complaint notifications that set `outreach_opt_in` false, unsubscribe tokens signed with HMAC, and `OUTREACH_MIN_SCORE` recalibrated on Phase 1 match data.

Done when:

- A run creates drafts only for opted-in candidates above the score, with a real description, and not contacted for that pair in 90 days.
- Draft body contains title, city, and skills, and does not contain the fixture `external_req` or the word clearance.
- Approve sends one SES message in a sandbox test, or writes the MIME to a local outbox when `SES_FROM_ADDRESS` is unset.
- Unsubscribe link stops further drafts for that candidate.
- A second scheduler tick inside the same interval does not create a second draft for the same pair.

### Phase 4 — later, do not build from this spec

AWS Marketplace listing, per-tenant isolation, metering, SSO, an OpenSearch adapter behind the same repository interface, and any compliance program beyond the controls in section 2.

## 12. Out of scope for the whole v1

- Replacing the company website. The chat is a URL the existing site links to.
- Applicant tracking, interview scheduling, payroll, benefits enrollment.
- Fine-tuning or training a model on résumés.
- A multi-agent framework (CrewAI, AutoGen, LangGraph swarms). Tool use is two functions on the public side (`search_jobs`, `get_job`) and two on the admin side (`parse_resume` preview, `rank_jobs`).
- Scraping job boards other than the configured careers URL.
- Elasticsearch operations console. Search and edit happen in `/admin`.
- Mobile native apps.
- Guessing clearance, customer, salary, or visa sponsorship.

## 13. Development practice

- Synthetic fixtures live in `tests/fixtures`. No real résumé in git.
- `.env.example` lists every variable and leaves secrets blank.
- Parser, redaction, scoring, and the public/admin query boundary are unit-tested without a GPU and without Bedrock. Model calls are behind the client interface and stubbed in tests.
- The chat path that needs a live model is covered by one stubbed test that checks “only retrieved requisition codes are returned.”
- Log request ids and errors. Do not log résumé bodies, phones, or emails.
