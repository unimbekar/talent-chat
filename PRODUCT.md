# Talent Chat as a product

How to package Talent Chat for other staffing firms and government contractors, what it already does, what must be added before charging for it, and a starting price list. Market, pricing, and sales plan: [GO_TO_MARKET.md](GO_TO_MARKET.md).

## What a customer gets

**For job seekers** (public, no login)

- A chat page on the customer's own domain. Visitors ask in plain words ("Java and AWS jobs near Chantilly", "Which roles need a clearance?") and get matching openings as cards in under a second, followed by a short written summary.
- Every card links to the posting on the customer's careers site. The model may only name jobs that exist; unknown codes are removed before the answer is shown.
- Open jobs are read from the customer's careers page every 6 hours. Nothing is entered twice.

**For recruiters** (password protected)

- **Dashboard**: open jobs, jobs missing a description, candidates added this week, top skills and states in the bench, careers sync status.
- **Jobs**: every opening with its ranked candidates. Paste or upload a full description and it is saved instantly; the skills are read in the background.
- **Candidates, Find, Match**: search the résumé bench by skill, clearance, and location; match one résumé against all jobs.
- **Review**: pick a job and several candidates and see, line by line, which requirements each résumé covers. Copy emails or export CSV.
- **Ingest**: bulk import a résumé folder, keeping only the latest résumé per person and skipping offer letters and invoices.

**Why customers care**

- Runs on hardware they control, with a local model, so résumés never leave the building. Option to use Bedrock or Vertex in their own cloud account instead.
- Built for cleared-workforce firms: clearance levels are parsed and filterable, and the footer warns users not to upload CUI.

## How it is packaged

One deployment per customer (single tenant). Each customer gets their own database, their own files, and their own domain. This is the simplest model to sell to security-minded buyers and needs no code changes.

| Customer size | Where it runs | Notes |
| --- | --- | --- |
| Small firm, wants local AI | A mini PC or GPU workstation at the customer, published with a Cloudflare Tunnel | See [publish_cloudflare.md](publish_cloudflare.md), Option A |
| Most customers | One cloud server in their account or yours, with a hosted model | `docker-compose.prod.yml`, see [deploy.md](deploy.md) |
| Google Workspace shops | Cloud Run and Cloud SQL, résumés from a Shared Drive | See [google_deploy.md](google_deploy.md) |

## Branding a deployment

Every customer-facing word, color, and image comes from `.env`. Change the values and run `docker compose up -d`. The pages pick them up within 5 minutes.

| Setting | Example | Where it shows |
| --- | --- | --- |
| `COMPANY_NAME` | `Acme Staffing` | Page titles, nav, chat header, login |
| `CAREERS_URL` | `https://acme.com/careers` | Crawled for jobs; "View posting" links |
| `BRAND_TAGLINE` | `Find your next mission` | Chat page headline |
| `BRAND_ACCENT` | `#0b6e4f` | Buttons, links, highlights (any 6-digit hex) |
| `BRAND_LOGO_URL` | `/brand/logo.svg` or a full `https://` URL | Nav and login |
| `BRAND_HERO_URL` | `/brand/hero.webp` or a full URL | Chat and login background |
| `BRAND_FOOTER` | Compliance notice | Footer on every page |
| `CHAT_EXAMPLES` | `Nurse jobs in Dallas\|Remote roles` | Example buttons under the chat box, separated by `\|` |
| `COMPANY_EMAIL_DOMAIN` | `acme.com` | Staff addresses in résumés are ignored when picking the candidate's email |
| `RESUME_LIBRARY_HOST` | `/srv/resumes` | Folder offered on the Ingest page |

To ship a customer's own images inside the image instead of linking to them, put them in `web/public/brand/` and rebuild `web`. A hero image of 1280×720 WebP under 100 KB keeps the page fast.

## Onboarding a customer

1. Get their careers URL, logo, colors, compliance text, and the domain to use (for example `jobs.acme.com`).
2. Check that their careers page parses. The crawler was written for Google Sites careers pages; other job boards need a small adapter (see [Before you sell](#before-you-sell)).
3. Create the server or appliance. Copy `.env.example` to `.env`, set the branding values, generate a new `SESSION_SECRET` (`openssl rand -hex 32`) and an admin password hash.
4. Start the stack, publish it with Cloudflare, and put Cloudflare Access in front of `/admin`.
5. Import their résumé folder from the Ingest page. A model pass over each résumé takes about 15 seconds on a local GPU, so plan an overnight run for a few thousand files.
6. Walk the recruiters through Dashboard, Jobs, and Review. Hand over the backup and restore steps.

## Before you sell

The app works well for one firm run by its owner. These gaps matter to a paying customer, roughly in order:

| Gap | Today | Needed |
| --- | --- | --- |
| Recruiter accounts | One shared admin password | Named users, roles (admin, recruiter, read-only), and sign-in with Google or Microsoft (OIDC). Cloudflare Access covers part of this meanwhile |
| Audit log | None | Who viewed, exported, or edited which candidate, and when |
| Careers sources | One parser for Google Sites careers pages | Adapters for common boards (Workday, Greenhouse, Lever, BambooHR, JazzHR, Ceipal) or a CSV/JSON feed |
| Résumé sources | Folder import and upload | Google Drive and SharePoint/OneDrive import (design in [google_deploy.md](google_deploy.md)) |
| Data retention | Kept until deleted | A retention period per customer, candidate delete on request (GDPR/CCPA), and a purge report |
| Backups | Manual `pg_dump` | Scheduled, encrypted, off-site, and a tested restore |
| Updates | `git pull` and rebuild | Versioned images in a registry, a changelog, and a one-command upgrade |
| Monitoring | Container health checks | Uptime checks and error alerts per customer |
| Legal | None | Terms of service, privacy policy, data processing agreement, and a security overview for questionnaires |
| License | Unlicensed source | A commercial license; ship images rather than source |

Sell to the first two or three customers as a managed pilot while the first four rows are built.

## Pricing ideas

Price on value: a recruiter who finds a qualified candidate a day sooner is worth far more than the hosting.

| Plan | For | Price idea |
| --- | --- | --- |
| Starter | Up to 3 recruiters, 2,000 résumés, public chat, hosted by you | $299–499 per month |
| Professional | Up to 15 recruiters, 20,000 résumés, SSO, audit log, CSV export | $899–1,499 per month |
| On-prem / GovCon | Runs in the customer's environment or appliance, local model, annual support | $12,000–25,000 per year plus set-up |
| Set-up | Branding, careers adapter, first résumé import, training | $1,500–5,000 one time |

Hosting cost per customer is about $10–75 a month (see the cost comparison in [google_deploy.md](google_deploy.md) and [README.md](README.md)), so gross margins stay high.

## Roadmap

1. Named recruiter accounts with Google/Microsoft sign-in, and an audit log.
2. Careers adapters for the common job boards; a JSON feed endpoint.
3. Automatic résumé import from Google Drive and SharePoint.
4. Candidate outreach: email shortlisted candidates about a new opening, with opt-out (`SES_FROM_ADDRESS` and `OUTREACH_*` settings are already reserved).
5. Job-seeker apply flow: upload a résumé from the chat and see matching jobs.
6. ATS push: send a shortlisted candidate to Bullhorn, Ceipal, or JobDiver.
7. Multi-tenant hosting (one deployment, many customers) once there are more than about 20 customers.
