#!/bin/bash
# Runs on the EC2 instance after git clone. Reads TALENT_* from the environment.
# Generates passwords, stores them in Secrets Manager, builds the stack, installs the backup cron.
set -euo pipefail
cd /opt/talent-chat
umask 077

python3 - << 'PY'
import json
import os
import pathlib
import secrets
import subprocess

region = os.environ["TALENT_REGION"]
secret_id = os.environ["TALENT_SECRET_ID"]
payload = {
    "admin_password": secrets.token_urlsafe(18),
    "session_secret": secrets.token_urlsafe(48),
    "postgres_password": secrets.token_urlsafe(24),
    "app_admin_db_password": secrets.token_urlsafe(24),
    "app_public_db_password": secrets.token_urlsafe(24),
}
subprocess.run(
    [
        "aws",
        "secretsmanager",
        "put-secret-value",
        "--region",
        region,
        "--secret-id",
        secret_id,
        "--secret-string",
        json.dumps(payload),
    ],
    check=True,
)
lines = [
    f"POSTGRES_PASSWORD={payload['postgres_password']}",
    f"APP_ADMIN_DB_PASSWORD={payload['app_admin_db_password']}",
    f"APP_PUBLIC_DB_PASSWORD={payload['app_public_db_password']}",
    f"SESSION_SECRET={payload['session_secret']}",
    f"S3_BUCKET={os.environ['TALENT_BUCKET']}",
    f"PUBLIC_HOST={os.environ['TALENT_HOST']}",
    f"ACME_EMAIL={os.environ['TALENT_EMAIL']}",
    f"PUBLIC_FRAME_ANCESTOR={os.environ['TALENT_FRAME']}",
    f"BEDROCK_MODEL={os.environ['TALENT_MODEL']}",
    "CRAWL_ON_START=true",
    "COMPANY_NAME=Janus Soft Inc.",
    "CAREERS_URL=https://www.janus-soft.com/career",
    "",
]
pathlib.Path(".env").write_text("\n".join(lines))
pathlib.Path(".env").chmod(0o600)
secret_dir = pathlib.Path("secrets")
secret_dir.mkdir(mode=0o700, exist_ok=True)
password_file = secret_dir / ".admin_password"
password_file.write_text(payload["admin_password"] + "\n")
password_file.chmod(0o600)
PY

docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run -T --rm --no-deps \
  --entrypoint /app/.venv/bin/python api -m app.hashpw \
  < secrets/.admin_password > secrets/admin_password_hash
rm -f secrets/.admin_password
python3 - << 'PY'
import pathlib
text = pathlib.Path("secrets/admin_password_hash").read_text()
line = next(item for item in text.splitlines() if item.startswith("$argon2"))
path = pathlib.Path("secrets/admin_password_hash")
path.write_text(line + "\n")
path.chmod(0o600)
PY

docker compose -f docker-compose.prod.yml up -d --build

cat > /etc/cron.d/talent-backup << 'EOF'
SHELL=/bin/bash
0 7 * * * root cd /opt/talent-chat && docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U postgres -Fc talent | docker compose -f docker-compose.prod.yml exec -T api python -m app.backup >> /var/log/talent-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/talent-backup
