# Selling Talent Chat to other companies

Is Talent Chat a viable product, who would buy it, how to charge for it, and what to do first. [PRODUCT.md](PRODUCT.md) covers how a deployment is packaged, branded, and onboarded; this file covers the business.

Market figures below are rough estimates to check during validation, not researched numbers.

## Short answer

Yes, as a **niche product**, not as a general recruiting tool.

General applicant tracking and AI sourcing are crowded (Bullhorn, Ceipal, JobDiva, Loxo, Manatal, hireEZ, SeekOut, and every ATS adding a chatbot). Competing there means competing on features with funded companies.

The opening is **staffing firms and government contractors that place cleared people**, mostly around Washington DC, Northern Virginia, Maryland, Huntsville, San Antonio, and Colorado Springs. They:

- live on clearance level, polygraph, and labor category, which general tools treat as free text;
- often cannot or will not send résumés to a public AI service, and Talent Chat runs on a local model;
- are small (5–200 people), buy quickly, and are underserved by enterprise tools priced for 500-seat customers;
- spend real money per hire. A single placement is often worth $15,000–40,000 a year in margin to a staffing firm, so a tool that fills one extra role a quarter pays for itself many times.

The best route is to sell to a few of these firms as a managed service first, prove that it shortens time to submit, then turn what they pay for into the product.

## What you already have

| Asset | Why a buyer cares |
| --- | --- |
| Public job chat on their domain, fed from their careers page | Candidates find the right role without a recruiter; leads arrive pre-filtered |
| Résumé bench search by skill, clearance, polygraph, state, and labor category | The question cleared recruiters ask all day, answered in seconds |
| Line-by-line fit against a posting (mandatory and desired) | Explains a match instead of a black-box score; defensible to a hiring manager |
| Bulk folder import with one résumé per person | Years of résumés on a file share become searchable in an afternoon |
| Submission pipeline, salary, comments, and reports with Excel export | Replaces the spreadsheet most small firms track submissions in |
| Desk assistant on every page, grounded in the data, read-only | "Who fits A1001 with a TS/SCI in Virginia?" in plain words, with the rows behind the answer |
| Runs on a local model, or Bedrock in the customer's AWS account | Résumés never leave the customer's control; a real sales argument in this market |

## Who buys, and who does not

**Best first customers**

1. Small and mid-size cleared staffing firms (10–100 recruiters and account managers). Pain: thousands of résumés on a share drive, nobody can find the TS/SCI Java developer they spoke to last year.
2. Government contractors (prime or sub) with an in-house recruiting team of 2–20. Pain: winning a contract depends on naming qualified, cleared key personnel quickly.
3. Proposal and capture teams at those contractors. Pain: finding résumés that match each labor category in an RFP before the deadline. See [Proposal staffing](#idea-1-proposal-staffing-for-govcon-bids).

**Poor first customers**

- Large enterprises: long security reviews, SSO and SOC 2 required on day one, procurement cycles of 6–12 months.
- High-volume hourly hiring (retail, warehouse): needs scheduling and texting, not clearance-aware search.
- Agencies outside cleared work that already pay for Bullhorn plus an AI add-on, unless the local-AI angle matters to them.

## Competition

| Type | Examples | How Talent Chat differs |
| --- | --- | --- |
| Staffing ATS | Bullhorn, Ceipal, JobDiva, Avionté | Talent Chat is not a full ATS. Position it as the search and matching layer beside the ATS, and later push shortlisted candidates into it |
| AI sourcing | hireEZ, SeekOut, Gem, Juicebox | They search the open web. Talent Chat searches the résumés the firm already owns, privately |
| Cleared job boards | ClearanceJobs, ClearedJobs.Net | Boards sell access to candidates. Talent Chat makes the firm's own bench and careers page useful |
| Career-site chatbots | Paradox, Sense, ATS widgets | Generic. Talent Chat's chat only names real open jobs, with clearance and location filters |

The position in one line: **private AI search over the résumés and jobs you already have, built for cleared hiring.**

## Ways to make money

| Model | How it works | Good | Watch out |
| --- | --- | --- | --- |
| Hosted subscription (SaaS) | Monthly fee per firm, tiered by recruiters and résumés | Recurring, predictable, easy to sell | You run the servers, backups, and security |
| Private deployment | Annual license; runs in the customer's AWS/GovCloud account or office | Matches what security-minded buyers want; higher price | Each install is a little different; support costs more |
| Appliance | A small GPU box (DGX Spark class or a mini PC) preloaded, shipped, and managed remotely | Strongest "nothing leaves the building" story; hardware margin | Shipping, warranty, and support for hardware |
| Set-up fee | Branding, careers adapter, résumé import, training | Pays for onboarding; filters out tyre-kickers | One-time; keep it small enough not to block the sale |
| Usage add-on | Charge for heavy AI use: résumé imports over a quota, outreach emails, proposal matching | Grows with the customer | Customers dislike unpredictable bills; keep a generous base |
| Managed service | You (or a partner) run searches and shortlists for the firm on the tool | Revenue from day one; you learn exactly what customers need | Does not scale; use it to find the product, not as the business |
| White-label | IT consultancies or HR firms resell it under their brand | Others do the selling | Lower margin; brand control |

**Recommended mix:** hosted subscription for most customers, private deployment as the premium plan, and a set-up fee on both. Start with a managed pilot for the first two or three customers.

## Suggested prices

These refine the table in [PRODUCT.md](PRODUCT.md). Price on value (placements and contract wins), not on hosting cost.

| Plan | Includes | Price idea |
| --- | --- | --- |
| Pilot | 60 days, one firm, set-up included, weekly check-in | $1,000–2,500 total, credited toward the first year if they sign |
| Starter (hosted) | Up to 3 recruiters, 5,000 résumés, public chat, assistant, pipeline, reports | $399 per month, or $3,990 per year |
| Team (hosted) | Up to 15 recruiters, 25,000 résumés, named accounts and SSO, audit log, Excel export, priority support | $1,200 per month |
| Private | Runs in the customer's cloud account or appliance, local or Bedrock model, unlimited recruiters | $18,000–36,000 per year plus set-up |
| Set-up | Branding, careers adapter, first import, training | $1,500 (hosted), $5,000+ (private) |
| Add-ons | Proposal staffing, outreach, ATS sync | $200–600 per month each |

Offer annual billing with two months free; annual contracts reduce churn and fund the work.

## Rough unit economics

| Item | Hosted customer, per month |
| --- | --- |
| Server and database | $15–60 |
| Model (local or Bedrock, light use) | $5–50 |
| Backups, monitoring, email | $5–15 |
| **Cost** | **about $25–125** |
| **Price** | **$399–1,200** |

That is a 70–90% gross margin before support time. Support and onboarding are the real costs early on; keep them down with a clean import, good defaults, and the in-app assistant.

At $600 average per month, 20 customers is about $144,000 a year and 50 customers is about $360,000. That is enough for one or two people, which is the realistic first goal.

## Features that raise what customers will pay

Ordered by how directly they lead to money for the customer.

### Idea 1: Proposal staffing for GovCon bids

Upload an RFP or its labor category table. The tool lists each labor category (LCAT) with its required years, degree, clearance, and certifications. It ranks the firm's résumés against each one and exports résumés in the RFP's required format.

Why it pays: contractors win or lose bids on key personnel, deadlines are days, and capture teams have budget. This could be a product on its own, sold to the business-development team rather than to recruiters.

It reuses the posting-line scoring, clearance parsing, and labor categories that already exist.

### Idea 2: Talent rediscovery alerts

When a new job is crawled, tell the recruiter: "6 people already in your bench cover 90% of A1012; 2 have TS/SCI." The firm already paid to get these résumés; surfacing them is pure profit.

### Idea 3: Candidate outreach with consent

Email or text shortlisted candidates about a matching opening, with opt-out and a reply inbox. The settings are reserved already; [OUTREACH_AGENTS.md](OUTREACH_AGENTS.md) has the design.

### Idea 4: Apply from the chat

A job seeker uploads a résumé in the public chat, sees matching openings, and lands in the bench as a new candidate. The careers page becomes a lead source.

### Idea 5: ATS sync

Push a shortlisted candidate or submission to Bullhorn, Ceipal, or JobDiva, and read job orders back. Removes the main objection: "we already have an ATS."

### Idea 6: Bench insights for sales

Show which skills and clearances the bench is strong in, so account managers know which contracts to chase. It extends the reports page.

### Idea 7: Hiring-manager share links

A read-only link with a shortlist and the line-by-line fit for each person, no login needed. It removes copy-paste into email and makes the firm look sharp to its clients.

## How to find customers

1. **Your own network first.** Janus Soft's partners, primes, subs, and recruiters you know. Ask for a 20-minute call to show it on their own careers page. A demo on the prospect's real jobs is far more convincing than slides.
2. **Local GovCon communities.** NVTC, AFCEA chapters, PSC, NDIA, Small Business Administration and APEX Accelerator events, and teaming and "industry day" meetups. Recruiting and capture leaders attend.
3. **LinkedIn.** Short screen recordings: "find a TS/SCI Java developer in Virginia in 5 seconds from 10,000 résumés." Post weekly; message recruiting leads at cleared staffing firms directly.
4. **Free careers chat.** Offer the public job chat free for a firm's careers page. It shows the product to every visitor and leads to the paid recruiter desk.
5. **Partners.** IT managed-service providers serving small contractors, CMMC consultants, and ATS resellers; pay 15–20% referral or resell margin.
6. **Marketplaces later.** The Bullhorn Marketplace and AWS Marketplace (GovCloud buyers can pay from existing AWS budgets).

## Validate before building more

A 90-day plan.

| Weeks | Do | Done when |
| --- | --- | --- |
| 1–2 | Write a one-page offer and a 3-minute demo video. List 40 target firms. | Offer and list ready |
| 3–6 | 20 discovery calls. Ask how they search résumés today, how long a submission takes, and what they pay for tools. Demo on their careers page. | 3 firms agree to a paid pilot |
| 7–10 | Run the pilots as a managed service. Measure time from job opening to first submission, before and after. | One clear number, for example "first submission in 1 day instead of 4" |
| 11–13 | Convert pilots to annual plans. Build only what at least two pilots asked for. | 2 paying customers and a case study |

If firms will not pay even for a cheap pilot after 20 good conversations, change the audience (try proposal staffing) before writing more code.

## Engineering work before many customers

Current state, updating the gap list in [PRODUCT.md](PRODUCT.md):

| Area | Today | Needed to sell |
| --- | --- | --- |
| Accounts | One admin password; Google sign-in exists | Named users and roles (admin, recruiter, viewer); Microsoft sign-in |
| Tenancy | One deployment per firm; company name and careers URL in `.env` | Keep single-tenant for the first 10–20 customers. Add a deployment script that creates a new customer in minutes |
| Careers sources | Google Sites careers parser | Adapters for Workday, Greenhouse, Lever, Ceipal, JobDiva, plus a CSV/JSON upload |
| Résumé sources | Folder, upload, S3, Drive design | Google Drive and SharePoint/OneDrive import |
| Audit | Audit log of logins, assistant use, and résumé downloads | Per-user audit once accounts exist; an export for customers |
| Backups | Nightly `pg_dump` (cron) | Encrypted, off-site, restore tested monthly, per customer |
| Testing safety | Tests refuse a non-`_test` database | Same guard in deployment scripts; staging environment |
| Updates | Rebuild from source | Versioned images in a private registry; one-command upgrade; changelog |
| Monitoring | Health checks | Uptime and error alerts per customer |
| Model | Local Qwen; Bedrock supported | Default to Bedrock (or GovCloud) for hosted customers; local for appliance |

## Legal and business

- **Who owns the code.** If you built this as a Janus Soft employee, on its time or equipment, or for its use, Janus Soft may own it. Settle ownership in writing first: a license or assignment from Janus Soft, or a new company that Janus Soft co-owns. Do this before any sale.
- **Company.** An LLC, a business bank account, and a contract template (subscription agreement, order form).
- **Terms and privacy.** Terms of service, privacy policy, and a data processing agreement. Candidates' résumés are personal data; customers will ask where it lives and who can see it.
- **AI hiring rules.** Automated tools used in hiring are regulated in a growing number of places: New York City's AEDT law (bias audit and candidate notice), Colorado's AI Act, Illinois, and the EU AI Act, which treats hiring AI as high-risk. Keep the product as recruiter assistance: it ranks and explains, and a person decides. Keep the line-by-line reasons, never use protected traits, and record what was shown. Get a lawyer's review before selling outside Virginia and Maryland.
- **Security questionnaires.** Write a two-page security overview now (encryption, access control, local model option, backups, incident contact). SOC 2 can wait until larger customers require it; CMMC applies to the customer's CUI, so keep the product out of CUI scope and say so in the footer (it already warns users).
- **Insurance.** Cyber liability and errors and omissions insurance before handling other companies' candidate data.

## Risks

| Risk | Mitigation |
| --- | --- |
| ATS vendors add similar AI search | Stay specific: clearance, labor categories, proposals, private deployment. Integrate with ATSs instead of replacing them |
| Small firms churn | Annual plans; tie the product to placements and bids won; make the bench more valuable each month |
| Support load from many custom installs | Standard images, one deployment script, adapters for common boards, refuse heavy customization early |
| Data breach of candidate data | Single tenant, encryption, least privilege, audit log, insurance, tested backups |
| Model quality or cost changes | The model layer already switches between local, OpenAI-compatible, and Bedrock |
| Founder time | Start with a managed pilot and a part-time plan; hire or partner for sales once 5 customers pay |

## Numbers to track

- Pilots started, and pilots converted to paid
- Time from a new job to first submission, per customer
- Searches and assistant questions per recruiter per week (shows real use)
- Placements or bids where the tool found the candidate (ask customers monthly)
- Monthly recurring revenue, churn, and support hours per customer

## Next steps

1. Settle code ownership with Janus Soft.
2. Record a 3-minute demo on the Janus Soft desk and write the one-page offer.
3. Book 20 discovery calls with cleared staffing firms and GovCon recruiting leads.
4. Meanwhile, build named recruiter accounts and a one-command customer deployment, the two gaps every pilot will hit.
5. Prototype proposal staffing (LCAT matching) as the feature most likely to unlock budget.
