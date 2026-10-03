# Phase 1.5 — public site

The public chat runs on one `t4g.medium` in `us-east-1`. The DGX Spark can be off. This file is the instance setup, the nightly backup, and the restore drill. Create the stack, the DNS record, Google sign-in, and the two import paths by following [aws_deploy.md](aws_deploy.md).

The Spark stack does not change. Keep using `docker compose up` and `LLM_BACKEND=openai_compat` there. Production is a separate checkout and `docker-compose.prod.yml`.

Out of scope: an Application Load Balancer, a GPU, Redis, OpenSearch, Cognito, and email. Drive import uses the recruiter's Google sign-in. S3 import reads the `inbox/` prefix. Both are in [aws_deploy.md](aws_deploy.md).

## What talks to what

```
browser  -- 443 -->  caddy  -- /api/* -->  api  -->  postgres
                         |                  |  -->  Bedrock Nova Lite (us-east-1)
                         +---- pages ---->  web     S3 originals + dumps
```

Caddy is the only published service. It obtains a certificate for `PUBLIC_HOST`. Postgres is bound to `127.0.0.1:5432` on the instance. The API port is not published. The browser still calls `/api/...` on the public host. Caddy removes the `/api` prefix and forwards to FastAPI, and it replaces `X-Forwarded-For` with the visitor address so the 30-per-hour limit is per visitor.

| Concern | What happens |
| --- | --- |
| Bedrock is denied, throttled, or times out | Public search still returns job cards and the notice “Explanations are unavailable right now.” |
| A résumé is uploaded | The bytes go to `s3://$S3_BUCKET/originals/<sha256>` with SSE-S3. The object is not public. |
| `S3_BUCKET` is empty | Production compose refuses to start. On the Spark, files stay on the local uploads volume. |
| Spark database restored onto AWS | Job rows come back. `original_path` values from the Spark point at local disk, not S3. Start production empty and let the crawler fill jobs. Upload résumés again after S3 is set. |
| Recrawl from the browser | Caddy waits up to 10 minutes. A full careers pass can take longer than a minute. |
| Admin cookie | `SESSION_SECURE=true`. Sign-in works on `https://` only. |
| Someone sends a fake `X-Forwarded-For` | Caddy overwrites it. The API trusts that header only when the TCP peer is a private address, which Caddy is. |
| Container cannot see the instance role | Set the instance metadata hop limit to 2. The default of 1 blocks Docker. |
| Nova access is not enabled | Chat cards still load. Explanations stay on the unavailable notice until Nova Lite is enabled in `us-east-1`. |
| Model id `us.amazon.nova-lite-v1:0` | That is a US geo profile. AWS may run it outside `us-east-1`. Use `amazon.nova-lite-v1:0`. |

Embeddings stay in-process FastEmbed. They do not move to Bedrock.

## Deploy with CloudFormation

[deploy/cloudformation.yml](deploy/cloudformation.yml) creates the network, the private bucket, the instance role, a Secrets Manager secret, and one `t4g.medium`. On first boot the instance clones the git repo and runs [deploy/bootstrap.sh](deploy/bootstrap.sh), which writes `.env`, builds the images, and installs the nightly backup cron.

Use an AWS CLI profile on your own machine (`aws configure`, or a profile you already trust). Do not paste an access key, secret key, or session token into chat, into `.env`, or into the template. The instance uses its IAM role. There is no long-lived key on the box.

Push this Phase 1.5 code to `main` before you create the stack. The instance clones `RepoUrl` at `GitRef` (default `https://github.com/unimbekar/talent-chat.git`, branch `main`). A private repo needs `GitTokenSecretArn`: a Secrets Manager secret whose value is the raw GitHub token, not JSON.

In the Bedrock console for `us-east-1`, enable Amazon Nova Lite before you rely on explanations. The template allows `bedrock:InvokeModel` on `amazon.nova-lite-v1:0`. It cannot click the model-access button for you.

```bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name talent-chat \
  --template-file deploy/cloudformation.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    PublicHost=chat.janus-soft.com \
    GoogleClientId=YOUR_CLIENT_ID.apps.googleusercontent.com \
    GoogleClientSecret=YOUR_CLIENT_SECRET \
    AcmEmail=you@janus-soft.com \
    BucketName=talent-chat-ACCOUNTID \
    HostedZoneId=ZXXXXXXXX
```

Leave `HostedZoneId` out if the DNS zone is not in this account. After the stack finishes, point an A record at the `PublicIp` output. Leave `www.janus-soft.com` on Google Sites. Caddy obtains the certificate once that name resolves to the instance. The stack waits up to 60 minutes for the image build, then signals success.

The bucket blocks public access, denies non-TLS requests, encrypts with SSE-S3, and expires `dumps/` after 14 days. Résumé objects under `originals/` stay until a recruiter deletes the candidate. Deleting the stack keeps the bucket and the secret.

Recruiter password, after `CREATE_COMPLETE`:

```bash
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id talent-chat/talent-chat \
  --query SecretString --output text
```

`admin_password` in that JSON is the `/admin` password. It is not printed in the stack outputs.

Open `https://chat.janus-soft.com/chat`. Ask for AWS jobs in McLean. The paragraph comes from Nova Lite. Removing the role’s Bedrock permission still returns cards, with the unavailable notice.

Recruiter sign-in is `https://chat.janus-soft.com/admin`. Use the `@janus-soft.com` Google account when Drive import is needed. The generated password in Secrets Manager remains the break-glass sign-in. Do not link the admin URL from the careers page. Connect with Session Manager if you need a shell. Port 22 stays closed unless you pass `SshCidr`.

On the [careers page](https://www.janus-soft.com/career), add a button **Ask about open jobs** to `https://chat.janus-soft.com/chat`, opening in a new tab. `FrameAncestor` (default `https://www.janus-soft.com`) is what allows an iframe later. The button does not need one.

## Backup

Nightly, from the instance (07:00 UTC):

```bash
0 7 * * * cd /opt/talent-chat && \
  docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U postgres -Fc talent | \
  docker compose -f docker-compose.prod.yml exec -T api \
    python -m app.backup >> /var/log/talent-backup.log 2>&1
```

`python -m app.backup` reads a custom-format dump on stdin and writes `dumps/talent-YYYYMMDDTHHMMSSZ.dump` with SSE-S3. It refuses anything that is not a `pg_dump -Fc` archive.

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.backup --list
```

The dump contains résumé text, names, and email addresses. It lives only in the private bucket.

## Restore drill

Roles `app_admin` and `app_public` are cluster-wide. A dump of database `talent` does not create them. On a new instance, start compose once so the entrypoint runs migrations and creates the roles, then restore into a scratch database.

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U postgres -c 'CREATE DATABASE talent_scratch'
docker compose -f docker-compose.prod.yml exec -T api \
  python -m app.backup --fetch dumps/talent-YYYYMMDDTHHMMSSZ.dump | \
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U postgres -d talent_scratch --no-owner --exit-on-error
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U postgres -d talent_scratch -c 'SELECT count(*) FROM jobs'
```

`--no-owner` matters because the objects were owned by the `postgres` role inside the container. After the row count looks right, drop the scratch database. Restoring over the live `talent` database is a maintenance window: stop `api` first so it is not writing, restore, then start it.

A local proof of the same dump and restore, without S3, is `pg_dump -Fc` piped to `pg_restore` into `talent_scratch` on the Spark. That checks the archive shape. The S3 upload is covered by `api/tests/test_files_and_backup.py`.
