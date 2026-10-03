# Publish chat.janus-soft.com

CloudFormation creates the AWS resources. Google creates the OAuth client, because a Workspace account cannot be created from AWS. Recruiters then sign in with `@janus-soft.com` and import résumés from a Drive folder or from the S3 inbox.

The Spark stays the machine you build on. This stack is a separate checkout on one Graviton instance in `us-east-1`. The default size is `t4g.medium` (4 GB). `InstanceType` can be `t4g.large` (8 GB), `t4g.xlarge` (16 GB), or `t4g.2xlarge` (32 GB). The template is [deploy/cloudformation.yml](deploy/cloudformation.yml). Backup and restore stay in [deploy.md](deploy.md).

How the resources fit together, how a question becomes an answer, and what the bill includes:

- [docs/aws-resources.md](docs/aws-resources.md) — every resource the template creates, and the containers on the instance
- [docs/aws-flows.md](docs/aws-flows.md) — visitor question, Google sign-in, and the three import sources
- [docs/aws-cost.md](docs/aws-cost.md) — the monthly bill, and the load balancer, NAT gateway, and managed database that were left out

Do not paste an AWS access key, a Google client secret, or the recruiter password into chat or into git. The instance uses its IAM role. The Google secret lives in Secrets Manager.

## What you get

| Piece | Where it lives |
| --- | --- |
| Public chat | `https://chat.janus-soft.com/chat` |
| Recruiter desk | `https://chat.janus-soft.com/admin` |
| Sign-in | Google Workspace accounts at `@janus-soft.com`, plus the generated password as a break-glass |
| Drive import | Folders that signed-in account can already open. Read-only |
| S3 import | `s3://<bucket>/inbox/` only. `originals/` and `dumps/` are not an import source |
| Jobs | Crawled from `https://www.janus-soft.com/career` |
| Explanations | Amazon Bedrock Nova Lite in `us-east-1` |
| Mail and the public website | Unchanged. One new DNS A record |

Personal `@gmail.com` addresses cannot sign in. Putting a file in Drive does not email that person.

## 1. Create the Google OAuth client

Do this before the stack, so the redirect URL is registered on the first boot.

1. In [Google Cloud Console](https://console.cloud.google.com/) for the Janus Soft Workspace, create a project or use an existing one. Enable the **Google Drive API**.
2. Open **Google Auth platform** (or **APIs & Services → OAuth consent screen**). Choose **Internal**, so only `@janus-soft.com` users can consent.
3. Add the scopes `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/drive.readonly`.
4. Create an **OAuth client ID** of type **Web application**.
   - Authorized JavaScript origin: `https://chat.janus-soft.com`
   - Authorized redirect URI, exactly: `https://chat.janus-soft.com/api/admin/login/google/callback`
5. Copy the client id and client secret into a password manager. You will pass them to CloudFormation once. They are stored in `talent-chat/<stack-name>/google` and are not written into the instance user data.

For a trial on the Spark, add a second redirect URI: `http://localhost:3010/api/admin/login/google/callback`. Put the same client id and secret in the Spark `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, and set `PUBLIC_BASE_URL=http://localhost:3010`.

## 2. Deploy the CloudFormation stack

Use an AWS CLI profile already on your machine (`aws configure`). Enable **Amazon Nova Lite** in the Bedrock console for `us-east-1` before you rely on the written explanations. Job cards still load if Bedrock is denied.

Push the branch the instance will clone (`GitRef`, default `main`) before you create the stack. A private repo needs `GitTokenSecretArn`: a Secrets Manager secret whose value is the raw GitHub token.

On **Configure stack options**, the **Permissions** field is the role CloudFormation assumes. Create it once in IAM, then select it there. The template still creates the EC2 instance role. On the review page, also check **I acknowledge that AWS CloudFormation might create IAM resources with custom names.**

In IAM, choose **Roles → Create role → Custom trust policy**. Name it `janus-soft-cloudformation`. Attach **AdministratorAccess** while you are on `DeployMode=dev`. That managed policy already includes the Git sync actions. The trust policy lets both a normal stack deploy and GitHub sync assume the role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StackDeploy",
      "Effect": "Allow",
      "Principal": { "Service": "cloudformation.amazonaws.com" },
      "Action": "sts:AssumeRole"
    },
    {
      "Sid": "CfnGitSyncTrustPolicy",
      "Effect": "Allow",
      "Principal": { "Service": "cloudformation.sync.codeconnections.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

On the Git sync page, choose **Existing IAM role** and select `janus-soft-cloudformation`. The dropdown stays empty until this trust policy is saved. Connect the GitHub repo in CodeConnections first, on branch `main`, with the template path `deploy/cloudformation.yml`.

For the CLI, add `--role-arn arn:aws:iam::ACCOUNT_ID:role/janus-soft-cloudformation` to the deploy command.

```bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name talent-chat \
  --template-file deploy/cloudformation.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    PublicHost=chat.janus-soft.com \
    AcmEmail=contact@janus-soft.com \
    BucketName=janus-soft-jobs-chat \
    DeployMode=dev \
    InstanceType=t4g.medium
```

In the CloudFormation console those values are already filled in, including `DeployMode=dev` and `InstanceType=t4g.medium`. Review the form and change a field only when you need a different value. Add `GoogleClientId` and `GoogleClientSecret` when the OAuth client exists. Leave both empty until then.

`DeployMode=dev` is the default. CloudFormation deletes the instance, the bucket, and both secrets with the stack, and the secrets are removed immediately. There is no 30-day recovery window. A non-empty bucket cannot be deleted; empty `inbox/`, `originals/`, and `dumps/` first.

Set `DeployMode=prod` only for the stack you intend to keep. Prod keeps the instance, the bucket, and both secrets if the stack is deleted. A secret that is deleted by hand can be restored for 30 days. The prod root disk is also kept if the instance is terminated.

`InstanceType` must stay in the `t4g` list. The machine image is arm64. Use `t4g.large` when a 4 GB machine runs out of memory during the image build. Changing the size later replaces the instance.

Leave `HostedZoneId` empty. `janus-soft.com` stays on its current name servers. The stack takes up to 60 minutes because the instance builds the images, then signals success.

If the client secret contains a double quote, leave `GoogleClientSecret` empty at deploy time and write the JSON into the secret afterward:

```bash
aws secretsmanager put-secret-value \
  --region us-east-1 \
  --secret-id talent-chat/talent-chat/google \
  --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET"}'
```

Then start a session on the instance and run `bash /opt/talent-chat/deploy/bootstrap.sh` again so `.env` picks up the secret.

## 3. Point DNS at the instance

```bash
aws cloudformation describe-stacks \
  --region us-east-1 \
  --stack-name talent-chat \
  --query "Stacks[0].Outputs" \
  --output table
```

In the existing DNS zone for `janus-soft.com` (Google Cloud DNS or Squarespace Domains), add one record:

| Type | Name | Value |
| --- | --- | --- |
| A | `chat` | the `PublicIp` output |

Leave every `MX`, SPF, DKIM, and DMARC record in place. Leave `www` pointed at the Google Site. Caddy requests the certificate after `chat.janus-soft.com` resolves to that address.

On the careers page, add a button **Ask about open jobs** that opens `https://chat.janus-soft.com/chat` in a new tab. Do not embed the desk inside the Google Site. The sign-in cookie does not work in that frame.

## 4. Sign in

Open `https://chat.janus-soft.com/admin`. Choose **Sign in with Google** and use a `@janus-soft.com` account. Google asks for read-only Drive access. That consent is what lets this person import a Drive folder. The app never edits or deletes Drive files.

The stack also writes a random password to `talent-chat/talent-chat`. Read it only if Google sign-in is down:

```bash
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id talent-chat/talent-chat \
  --query SecretString --output text
```

`admin_password` in that JSON is the break-glass password. A password session can use the server folder and the S3 inbox. It cannot read Drive, because Drive uses the Google token from the sign-in.

## 5. Import résumés

On **Ingest**, pick one source. Each import keeps the newest PDF, DOC, DOCX, or TXT per person. Offer letters and invoices stay out.

**Google Drive.** Sign in with Google first. Paste a folder link such as `https://drive.google.com/drive/folders/<id>`. The folder can be in My Drive or a Shared Drive, as long as that Google account can open it. Check the folder, then start the import.

**Amazon S3.** Upload files with your own AWS credentials, or from a machine that already has them. The instance role is the only key the app uses.

```bash
aws s3 cp ./one-resume.pdf s3://talent-chat-ACCOUNTID/inbox/one-resume.pdf
aws s3 sync ./Candidates s3://talent-chat-ACCOUNTID/inbox/Candidates --exclude "*" --include "*.pdf" --include "*.doc" --include "*.docx" --include "*.txt"
```

On the Ingest page choose **Amazon S3**, leave the prefix as `inbox/`, check it, then start the import. A prefix outside `inbox/` is rejected. Stored originals under `originals/` and database dumps under `dumps/` are not an import source.

**Server folder.** This remains the Spark path, a directory mounted into the API container. On the AWS instance that disk is empty unless you copy files onto it. Use Drive or S3 there.

## Resources the template creates

There is no load balancer and no NAT gateway. Caddy on the instance is the only published port.

| Name in the template | AWS type | What it is |
| --- | --- | --- |
| `Vpc` through `SubnetRouteAssociation` | VPC | `10.20.0.0/16`, one public subnet `10.20.1.0/24` |
| `AppSecurityGroup` | Security group | TCP 80 and 443 from the internet. 5432, 3000, and 8000 stay closed |
| `SshIngress` | Security group rule | TCP 22, only when `SshCidr` is set |
| `AppEip` | Elastic IP | The address for the `chat` A record |
| `AppInstance` | EC2 | `InstanceType`, default `t4g.medium`, Amazon Linux 2023 arm64, IMDSv2, hop limit 2, 30 GB gp3 encrypted. Deleted with the stack in dev. Kept in prod. A size change replaces it |
| `AppRole` | IAM role | Nova Lite, the app secret, the Google secret, and S3 under `originals/`, `dumps/`, and `inbox/` |
| `FilesBucket` | S3 | Private, SSE-S3, TLS required. `dumps/` expires after 14 days. Deleted with the stack in dev, if the bucket is empty. Kept in prod |
| `AppSecret` | Secrets Manager | Recruiter password and database passwords. Dev: deleted immediately. Prod: kept, and a manual delete has a 30-day recovery window |
| `GoogleOAuthSecret` | Secrets Manager | `client_id` and `client_secret`. Same dev and prod rules as `AppSecret` |
| `DnsRecord` | Route 53 A record | Only when `HostedZoneId` is set |

These are used and are not created by the template:

| Service | How it is used |
| --- | --- |
| Google OAuth and Drive | The client id is created in Google Cloud. Sign-in is limited to `@janus-soft.com` |
| Amazon Bedrock | Nova Lite, model id `amazon.nova-lite-v1:0`, in `us-east-1` |
| Systems Manager Session Manager | Shell on the instance while port 22 stays closed |
| Let's Encrypt | Caddy requests the certificate for `PublicHost` |
| The existing DNS zone | One A record. The template does not create a hosted zone |
| GitHub | First boot clones the repo |

## Request flow

Caddy is the only process with a published port. The browser calls `/api/...` on `chat.janus-soft.com`. Caddy removes the `/api` prefix, replaces `X-Forwarded-For` with the visitor address, and forwards to FastAPI.

| Who | Path | What happens |
| --- | --- | --- |
| Visitor | `/chat` | Job cards from published postings. The public role cannot read candidates |
| Recruiter | `/admin` | **Sign in with Google** sends the browser to Google and back to `/api/admin/login/google/callback`. The session cookie carries the Drive refresh token |
| Drive import | Ingest → Google Drive | The API lists and downloads that folder with the signed-in account, then runs the same newest-file import as a local folder |
| S3 import | Ingest → Amazon S3 | The API lists `inbox/` with the instance role, downloads into a temporary directory, and runs the same import |
| Careers crawl | timer inside `api` | Every 6 hours, and when a recruiter clicks Recrawl |
| Backup | cron on the instance, 07:00 UTC | `pg_dump`, then `dumps/talent-<timestamp>.dump` |
| First boot | user data | Clones the repo, writes `.env` from Secrets Manager, builds the images, starts Compose |

Postgres listens on `127.0.0.1:5432` on the instance. The security group does not allow it from the internet.

Bedrock errors still return job cards. The notice is “Explanations are unavailable right now.”
