# Testing the project

Automated checks live in `api/tests`. They use the database `talent_test` on `127.0.0.1:5432`. They do not write to the live `talent` database. The script refuses to start if a database URL does not end in `_test`.

## Run everything

From the repository root, with Postgres up and `api/.venv` installed:

```bash
./scripts/test-project.sh
```

The script runs one group at a time and prints `PASS` or `FAIL` for each. The exit code is non-zero if any group fails. Public job chat is the one group with two older assertions that no longer match the page: a job that has posting text does not also say “Full description not on file.”, and a chat with `explain` false already includes the short sentence instead of an empty answer. The other checks in that group still run. A single group:

```bash
cd api
.venv/bin/pytest tests/test_knowledge.py -q
```

Postgres for the suite is the Compose database, published on the host at `127.0.0.1:5432`. Start it from the repository root with `docker compose up -d postgres` if it is not already running.

## What each group covers

| Group | Tests | Functionality |
| --- | --- | --- |
| Boundary | `test_boundary.py` | Public code does not import recruiter modules. The public database role cannot read candidates. A public search does not touch candidate rows. |
| Careers apply | `test_apply.py` | Open jobs on the public list. An application without a full-scope polygraph is refused and stored nowhere. A valid application creates a Submitted row. A second application updates salary and does not move an active stage backward. |
| Public job chat | `test_phase1_flows.py`, `test_public_explain.py`, `test_public_requirements.py` | Crawl fixtures, job chat, follow-ups, closed roles, lockout per IP, and the requirement matcher. |
| Knowledge base | `test_knowledge.py` | Sign-in required to upload. A benefits document answers a 401k question and hides an internal note. Edit and delete. A timesheet procedure answers “How do I submit a timesheet?” and is not used for “Java and AWS”. The public role cannot read the tables. |
| Admin sign-in | `test_password.py` | Local account `admin@janus-soft.com`. A wrong email is rejected. Password change replaces the hash. The public role cannot read the hash. |
| Submissions | `test_submissions.py` | Create, stage changes, salary, comments, and history for a candidate on a job. |
| Reports | `test_reports.py` | Date windows, ingest and submission counts, clearance and salary filters, CSV and Excel export. |
| Find and match | `test_find_candidates.py`, `test_score.py`, `test_labor.py` | Candidate search, mandatory-line coverage, and labor-category scoring. |
| Ingest | `test_folder_ingest.py`, `test_google_ingest.py`, `test_remote_ingest.py`, `test_files_and_backup.py` | Folder import, Drive and S3 materializing, file storage, and backup. |
| Jobs and résumés | `test_job_description_save.py`, `test_listing_parser.py`, `test_detail_parser.py`, `test_clearance.py` | Saving a job description, parsing the careers pages, and clearance wording. |
| Recruiter assistant | `test_assistant.py` | The desk assistant’s tools and scripted model replies. |
| Desk shell | `test_overview_and_brand.py`, `test_tokens_and_llm.py`, `test_redact_and_skills.py`, `test_resume_facts_cache.py` | Overview counts, brand settings, token limits, redaction, and résumé fact caching. |

## Check the running site

These steps use the Docker stack on port 3010. They are not a substitute for the script. Run the script first.

1. Open `http://192.168.1.189:3010/jobs` from the editor browser. `localhost` on that browser is refused. The page lists open jobs. `/chat` redirects to `/jobs`.
2. Ask the Desk “Jobs in Chantilly”. Cards name Chantilly roles. Ask “What is the 401k match?” before any document is uploaded. The answer says it is not in the knowledge base, and no job cards appear.
3. Sign in at `/admin` as `admin@janus-soft.com` with the desk password. Open **Knowledge**. Add a pasted document titled `Timesheet procedure`, audience **Careers visitors**, with a sentence that timesheets are due Friday at noon. Ask the Desk “How do I submit a timesheet?”. The answer names that document and the page shows the excerpt. “Java and AWS” still returns jobs, not the timesheet.
4. Edit the document, then delete it. Ask the timesheet question again. The answer says it is not in the knowledge base.
5. Add a second document with audience **Internal only**. Ask that question on `/jobs`. The public answer does not quote it.
6. On the desk, open Pipeline, Reports, and one job. A submission stage change and a report preset (Today) should load without an error banner. Export is covered by `test_reports.py`.

Do not leave sample documents in the live library after a check. Candidates can ask about them.
