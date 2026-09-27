# Postgres

The recruiting assistant stores jobs, résumés, and match scores in one Postgres database named `talent`. Docker Compose runs `pgvector/pgvector:pg16` as the `postgres` service. The data directory is the `talent-chat_pgdata` volume. The port is published only on `127.0.0.1:5432`.

The API applies migrations on startup (`alembic upgrade head`, revision `0001_phase1`) and then sets the `app_admin` and `app_public` passwords from `.env`.

## Connect

From the repository root, open a shell in the running container:

```bash
docker exec -it talent-chat-postgres-1 psql -U postgres -d talent
```

From the host, if `psql` is installed:

```bash
psql "postgresql://postgres:postgres@127.0.0.1:5432/talent"
```

`POSTGRES_PASSWORD` in `.env` is the `postgres` role password. The example file uses `postgres`.

Inside `psql`:

| Command | What it does |
| --- | --- |
| `\dt` | List tables |
| `\d jobs` | Columns, indexes, and foreign keys for one table |
| `\du` | List roles |
| `\dx` | List extensions (`vector` should be present) |
| `\x auto` | Turn expanded rows on when a row is wide |
| `\q` | Quit |

The API container reaches the database at host `postgres`, not `127.0.0.1`. Host tools use `127.0.0.1`.

### Roles

| Role | Used by | Password variable | Access |
| --- | --- | --- | --- |
| `postgres` | Migrations (`DATABASE_MIGRATE_URL`) | `POSTGRES_PASSWORD` | Superuser |
| `app_admin` | Recruiter API (`DATABASE_URL`) | `APP_ADMIN_DB_PASSWORD` (default `admin`) | All tables |
| `app_public` | Public chat (`DATABASE_PUBLIC_URL`) | `APP_PUBLIC_DB_PASSWORD` (default `public`) | `SELECT` on `jobs`, `job_chunks`, `skill_synonyms`, and `settings` |

`app_public` cannot read `candidates`, `matches`, or the session tables. That split is what keeps résumé rows off the public chat.

Connect as the admin role when you want to see what the recruiter API sees:

```bash
psql "postgresql://app_admin:admin@127.0.0.1:5432/talent"
```

Pytest uses a separate database, `talent_test`, on the same server. Commands in this guide target `talent`.

## Tables

Four foreign keys tie the recruiting data together. Each one deletes the child rows when the parent row is deleted. The pictures are PNG files, so they show in the Cursor preview and on GitHub. Sources are [`docs/diagrams/13-talent-tables.mmd`](docs/diagrams/13-talent-tables.mmd) and [`docs/diagrams/14-standalone-tables.mmd`](docs/diagrams/14-standalone-tables.mmd).

![Jobs, résumés, and matches](docs/diagrams/13-talent-tables.png)

`matches` is one score row for a résumé against a job. `job_chunks` and `candidate_chunks` are the smaller text pieces used for search.

These tables have no foreign keys:

![Tables with no foreign keys](docs/diagrams/14-standalone-tables.png)


| Table | Primary key | What it holds |
| --- | --- | --- |
| `skill_synonyms` | `alias`, `canonical` | Alias mapped to a canonical skill |
| `settings` | `key` | Company name and careers URL |
| `crawl_state` | `id` | Last careers crawl. One row, `id = 1` |
| `audit_log` | `id` | Admin actions. `subject_id` is a UUID with no foreign key |
| `admin_sessions` | `id` | Signed-in admin sessions |
| `login_attempts` | `id` | Failed logins by IP |
| `alembic_version` | `version_num` | Current schema migration |

`jobs.embedding` and the chunk embeddings are `vector(768)`, from `nomic-ai/nomic-embed-text-v1.5`. `jobs.tsv` and `candidates.tsv` are generated full-text columns.

## Read

Row counts:

```sql
SELECT 'jobs' AS tbl, count(*) FROM jobs
UNION ALL SELECT 'job_chunks', count(*) FROM job_chunks
UNION ALL SELECT 'candidates', count(*) FROM candidates
UNION ALL SELECT 'candidate_chunks', count(*) FROM candidate_chunks
UNION ALL SELECT 'matches', count(*) FROM matches
UNION ALL SELECT 'skill_synonyms', count(*) FROM skill_synonyms;
```

Open postings:

```sql
SELECT requisition_code, title, location, status
FROM jobs
WHERE status = 'open'
ORDER BY requisition_code;
```

Résumés on file. `candidates` holds names, emails, and phones. `redacted_text` is the stored résumé body.

```sql
SELECT id, full_name, original_filename, status, created_at
FROM candidates
ORDER BY created_at;
```

Stored match scores. The percents on the Jobs, Match, and Review screens are computed when the page loads. They are not these columns. `final` is the stored blend of skill overlap and embedding similarity.

```sql
SELECT j.requisition_code, c.full_name, m.skill_score, m.semantic, m.final
FROM matches m
JOIN jobs j ON j.id = m.job_id
JOIN candidates c ON c.id = m.candidate_id
ORDER BY m.final DESC NULLS LAST;
```

Synonyms and settings:

```sql
SELECT alias, canonical FROM skill_synonyms ORDER BY canonical, alias;
SELECT key, value, is_public FROM settings ORDER BY key;
SELECT * FROM crawl_state;
SELECT version_num FROM alembic_version;
```

## Purge

These statements delete data. Run them as `postgres` or `app_admin` while you are connected to `talent`.

Résumés, their chunks, and their match rows:

```sql
TRUNCATE candidates CASCADE;
```

Crawled jobs, job chunks, and match rows. The next careers crawl fills `jobs` again. Restart the API, or use Recrawl in the admin UI, so you do not wait for `CRAWL_INTERVAL_HOURS`.

```sql
TRUNCATE jobs CASCADE;
```

Recruiting rows plus login and audit history. Synonyms, settings, the crawl-state row, and the schema stay.

```sql
TRUNCATE matches, candidate_chunks, job_chunks, candidates, jobs,
         audit_log, admin_sessions, login_attempts
RESTART IDENTITY CASCADE;
```

Uploaded résumé files live in the `talent-chat_uploads` volume, not in these tables. Truncating `candidates` leaves the files on disk.

To wipe the database and let the API migrate and crawl from scratch:

```bash
docker compose down
docker volume rm talent-chat_pgdata
docker compose up --build
```

That removes every table, role password change, and crawl. It leaves `talent-chat_uploads` in place.

## Troubleshooting

**Container is not accepting connections.** Confirm it is healthy, then check the log:

```bash
docker compose ps
docker compose logs postgres --tail 50
docker exec talent-chat-postgres-1 pg_isready -U postgres -d talent
```

**`connection refused` on 5432.** The port is bound to `127.0.0.1` only. Use `127.0.0.1`, or `docker exec` into `talent-chat-postgres-1`. Another Postgres on the host can already own 5432; `ss -ltnp | grep 5432` shows which process has it.

**`password authentication failed`.** The password in the URL has to match `.env`: `POSTGRES_PASSWORD` for `postgres`, `APP_ADMIN_DB_PASSWORD` for `app_admin`, `APP_PUBLIC_DB_PASSWORD` for `app_public`. Role passwords are applied when the API container starts. Restart `api` after changing them:

```bash
docker compose up -d api
```

**`permission denied` on `candidates`.** The session is `app_public`. Public chat is limited to job search tables. Reconnect as `postgres` or `app_admin`.

**Tables are missing.** The API creates them on startup. Check the migration and the API log:

```sql
SELECT version_num FROM alembic_version;
```

```bash
docker compose logs api --tail 80
```

A healthy database reports `0001_phase1`. If `alembic_version` itself is missing, the migrate step did not finish.

**`vector` type is unknown.** The image is `pgvector/pgvector:pg16` and the migration runs `CREATE EXTENSION vector`. `\dx` should list `vector`. A different Postgres image will not have the type.

**Crawl looks stuck.** `crawl_state` is a single row:

```sql
SELECT last_started_at, last_finished_at, last_ok, last_error, last_rows
FROM crawl_state;
```

`last_ok = false` means the last crawl recorded `last_error`. The API also logs `scheduled crawl failed`.
