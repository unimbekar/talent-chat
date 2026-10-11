#!/usr/bin/env bash
# Run the API test suite one functionality at a time.
# Uses talent_test on 127.0.0.1:5432. Does not touch the live talent database.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/api"

if [[ ! -x .venv/bin/pytest ]]; then
  echo "Missing api/.venv. From api/, create it with: uv sync --group dev" >&2
  exit 1
fi

fail=0

run() {
  local name="$1"
  shift
  echo
  echo "======== ${name} ========"
  if .venv/bin/pytest "$@" -q --tb=line; then
    echo "PASS  ${name}"
  else
    echo "FAIL  ${name}"
    fail=1
  fi
}

run "Boundary" tests/test_boundary.py
run "Careers apply" tests/test_apply.py
run "Public job chat" tests/test_phase1_flows.py tests/test_public_explain.py tests/test_public_requirements.py
run "Knowledge base" tests/test_knowledge.py
run "Admin sign-in" tests/test_password.py
run "Submissions" tests/test_submissions.py
run "Reports" tests/test_reports.py
run "Find and match" tests/test_find_candidates.py tests/test_score.py tests/test_labor.py
run "Ingest" tests/test_folder_ingest.py tests/test_google_ingest.py tests/test_remote_ingest.py tests/test_files_and_backup.py
run "Jobs and résumés" tests/test_job_description_save.py tests/test_listing_parser.py tests/test_detail_parser.py tests/test_clearance.py
run "Recruiter assistant" tests/test_assistant.py
run "Desk shell" tests/test_overview_and_brand.py tests/test_tokens_and_llm.py tests/test_redact_and_skills.py tests/test_resume_facts_cache.py

echo
if [[ "$fail" -eq 0 ]]; then
  echo "All groups passed."
else
  echo "One or more groups failed."
fi
exit "$fail"
