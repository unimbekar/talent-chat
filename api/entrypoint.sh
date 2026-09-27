#!/bin/sh
set -eu
cd /app
/app/.venv/bin/python - << 'PY'
import os
import time
import psycopg

url = os.environ["DATABASE_MIGRATE_URL"].replace("postgresql+psycopg://", "postgresql://")
last = None
for _ in range(60):
    try:
        conn = psycopg.connect(url, connect_timeout=3)
        conn.close()
        break
    except Exception as exc:
        last = exc
        time.sleep(1)
else:
    raise SystemExit(f"postgres did not become ready: {last}")
PY
/app/.venv/bin/alembic upgrade head
/app/.venv/bin/python - << 'PY'
import os
import psycopg
from psycopg import sql

url = os.environ["DATABASE_MIGRATE_URL"].replace("postgresql+psycopg://", "postgresql://")
conn = psycopg.connect(url, autocommit=True)
conn.execute(
    sql.SQL("ALTER ROLE app_admin PASSWORD {}").format(
        sql.Literal(os.environ.get("APP_ADMIN_DB_PASSWORD", "admin"))
    )
)
conn.execute(
    sql.SQL("ALTER ROLE app_public PASSWORD {}").format(
        sql.Literal(os.environ.get("APP_PUBLIC_DB_PASSWORD", "public"))
    )
)
conn.execute(
    "UPDATE settings SET value = %s WHERE key = 'company_name'",
    (os.environ.get("COMPANY_NAME", "Janus Soft Inc."),),
)
conn.execute(
    "UPDATE settings SET value = %s WHERE key = 'careers_url'",
    (os.environ.get("CAREERS_URL", "https://www.janus-soft.com/career"),),
)
PY
exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
