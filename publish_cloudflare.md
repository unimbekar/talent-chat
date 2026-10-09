# Publish with Cloudflare

How to put Talent Chat on `https://talent.janus-soft.com` and add a button to it on `www.janus-soft.com`, using Cloudflare for DNS, TLS, and protection.

There are two ways to run it. Pick one.

| | Option A: Tunnel from the Spark | Option B: Small cloud server |
| --- | --- | --- |
| Monthly cost | $0 (Cloudflare Free) | $6–10 for the server |
| Where it runs | The Spark, as today. Ollama stays local | A 2 vCPU / 4 GB arm64 or x86 server |
| Open ports | None. `cloudflared` connects out to Cloudflare | 80 and 443, limited to Cloudflare IPs |
| Up when | The Spark is on and online | Always |
| Chat model | `qwen3.6` on the Spark | A hosted model (Bedrock, Vertex, or any OpenAI-compatible API) |
| Good for | Starting now, a pilot, demos | A site customers rely on |

Both options start with the same DNS step. Tailscale Funnel, below, is a third way to reach the Spark. It publishes a `*.ts.net` address. It does not serve `talent.janus-soft.com`.

## Tailscale Funnel

Funnel puts the app on the public internet at the Spark’s Tailscale name. On this machine that is `https://spark-42c4.tail55e197.ts.net/chat`. `tailscale funnel status` prints the name if the node is renamed.

`tailscale serve` is different. Serve is visible only to devices on the tailnet, and a foreground `sudo tailscale serve 3010` stops when that terminal closes. Funnel replaces it for a public address and keeps running after the terminal closes.

Stop a foreground `serve` with Ctrl+C, then:

```bash
sudo tailscale funnel --bg 3010
tailscale funnel status
```

The first run opens a Tailscale page to turn Funnel on for the tailnet. Approve it. Turn Funnel off with `sudo tailscale funnel reset`.

The web container is already published on host port 3010. Funnel proxies that port. Leave the command pointed at `3010`, not `3000`. Port 3000 inside the container is not what the host is listening on.

Anyone can open that address, including `/admin`. The app password is still required. Funnel does not add the Google sign-in from [Step 3](#step-3-protect-the-admin-screens-with-cloudflare-access).

Do not point `talent.janus-soft.com` at the `*.ts.net` name with a CNAME. Public DNS does not resolve that Tailscale name, so Windows reports that the site cannot be found. The certificate is also issued for the `*.ts.net` name, so the browser would reject `talent.janus-soft.com` even if the name resolved.

Use [Option A](#step-2-option-a-cloudflare-tunnel-from-the-spark) for `https://talent.janus-soft.com`. Funnel and the Cloudflare Tunnel can run at the same time. Funnel uses host port 3010. The tunnel uses `web:3000` inside Compose.

## Step 1: Move DNS for janus-soft.com to Cloudflare

Today `janus-soft.com` uses Google name servers (`ns-cloud-b1..b4.googledomains.com`). Cloudflare can only proxy a hostname whose DNS it serves. Moving the name servers does not move the domain registration, email, or the Google Site.

1. Write down every record first. Open Google Cloud DNS (or the Squarespace Domains panel that replaced Google Domains) and export or screenshot the zone. Look for these:
   - `MX` records for Google Workspace mail (`smtp.google.com`, or the older `aspmx.l.google.com` set).
   - `TXT` for SPF (`v=spf1 include:_spf.google.com ~all`), the `google-site-verification` value, and DMARC (`_dmarc`).
   - `TXT` for DKIM (`google._domainkey`).
   - `CNAME` `www` to `ghs.googlehosted.com` (the Google Site).
   - `A` records for the bare domain, if any.
2. Create a free Cloudflare account. Choose **Add a domain**, enter `janus-soft.com`, and pick the **Free** plan.
3. Cloudflare scans the zone. Compare its list with step 1 and add anything missing. Set these to **DNS only** (grey cloud):
   - All `MX` and `TXT` records (they cannot be proxied anyway).
   - `www` to `ghs.googlehosted.com`. Google Sites issues its own certificate and breaks behind Cloudflare's proxy.
4. Cloudflare shows two name servers, for example `ada.ns.cloudflare.com` and `bob.ns.cloudflare.com`. At the registrar, replace the four Google name servers with those two. If the zone has DNSSEC turned on, turn it off at the registrar first and turn it back on in Cloudflare afterwards.
5. Wait until Cloudflare says the zone is **Active** (usually under an hour). Send a test email to and from a Workspace address, and open `www.janus-soft.com`.

Do not move on until mail and the Google Site both work.

## Step 2, Option A: Cloudflare Tunnel from the Spark

`cloudflared` runs as one more container. It opens an outbound connection to Cloudflare, and Cloudflare sends traffic for `talent.janus-soft.com` down that connection to the `web` container. Nothing on the Spark is exposed to the internet.

1. In Cloudflare, open **Zero Trust**, then **Networks**, then **Tunnels**. Create a tunnel of type **Cloudflared** named `talent-spark`.
2. On the install screen, copy only the token (the long string after `--token`). Do not run the install command.
3. Under **Public hostname**, add:
   - Subdomain `talent`, domain `janus-soft.com`
   - Service `HTTP`, URL `web:3000`
   Cloudflare creates the proxied `talent` DNS record for you.
4. On the Spark, add the token to `.env`:

   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=eyJh...
   PUBLIC_FRAME_ANCESTOR=https://www.janus-soft.com
   CAREERS_URL=https://www.janus-soft.com/career
   ```

5. Start the stack with the overlay file:

   ```bash
   cd ~/spark-dev-workspace/projects/talent-chat
   docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
   docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml logs -f cloudflared
   ```

   Wait for `Registered tunnel connection` four times, then open `https://talent.janus-soft.com/chat`.

The overlay also sets two API settings:

- `TRUSTED_PROXY_HEADER=CF-Connecting-IP`: the rate limits count the visitor's real address, not Cloudflare's.
- `SESSION_SECURE=true`: the admin cookie is sent only over HTTPS. Sign in through `https://talent.janus-soft.com/admin` or `http://localhost:3010/admin`. A LAN address such as `http://192.168.x.x:3010` will no longer keep you signed in.

To stop publishing, run `docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml stop cloudflared`. The app keeps working locally.

## Step 2, Option B: A small cloud server

Use [`docker-compose.prod.yml`](docker-compose.prod.yml), which already runs Postgres, the API, the web app, and Caddy on one server. [deploy.md](deploy.md) covers the server set-up, S3, and backups. With Cloudflare in front, change these things:

1. In Cloudflare DNS, add `A talent <server IP>` with the orange cloud (**Proxied**).
2. Under **SSL/TLS**, set the mode to **Full (strict)**. Caddy still gets its own Let's Encrypt certificate over port 80.
3. In `.env` on the server, set `TRUSTED_PROXY_HEADER=CF-Connecting-IP`. Caddy forwards the header unchanged.
4. Allow ports 80 and 443 only from [Cloudflare's IP ranges](https://www.cloudflare.com/ips/), in the cloud firewall or security group. Visitors can then reach the server only through Cloudflare.

Alternatively, skip the open ports altogether: run the same `cloudflared` overlay on the server (`docker compose -f docker-compose.prod.yml -f docker-compose.cloudflare.yml up -d`), remove the `caddy` service, and point the tunnel's public hostname at `web:3000`.

## Step 3: Protect the admin screens with Cloudflare Access

The app has its own admin password. Cloudflare Access adds a Google sign-in in front of it, so only Janus staff can even reach the login page. It is free for up to 50 users.

1. In **Zero Trust**, open **Settings**, then **Authentication**. Add **Google Workspace** as a login method (or **One-time PIN** to start quickly).
2. Open **Access**, then **Applications**. Add a **Self-hosted** application:
   - Name: `Talent Chat admin`
   - Public hostnames: `talent.janus-soft.com` with path `admin`, and a second entry with path `api/admin`
   - Session duration: 24 hours
3. Add a policy: action **Allow**, include **Emails ending in** `@janus-soft.com`.

`/chat` and `/api/public/*` stay open to everyone. Test in a private browser window: `/chat` opens straight away, and `/admin` asks for a Google sign-in first.

## Step 4: Recommended Cloudflare settings

| Where | Setting | Why |
| --- | --- | --- |
| SSL/TLS, Edge Certificates | **Always Use HTTPS** on, minimum TLS 1.2 | No plain HTTP |
| Security, WAF | Turn on the **Cloudflare Free Managed Ruleset** | Blocks common attacks |
| Security, WAF, Rate limiting rules | `URI Path starts with /api/public/` , 30 requests per 10 seconds per IP, action **Block** for 1 minute | Stops scripted abuse of the chat before it reaches the model. The API has its own limits too |
| Security, Bots | **Bot Fight Mode** on | Cuts scrapers |
| Caching, Cache Rules | Bypass cache for `/api/*` and `/admin*` | Answers and admin pages are never cached |
| Caching | Leave defaults for `/_next/static/*` and `/brand/*` | Already sent with long cache headers |

Cloudflare closes a proxied request that runs longer than 100 seconds (error 524). Chat answers and saving a job description finish well inside that. A very large résumé upload on the Ingest page can take longer; use the folder import on the Spark for big batches.

## Step 5: Add the button on the Google Site

1. Open the site in Google Sites and go to the Careers page.
2. Choose **Insert**, then **Button**. Name it `Ask about our open jobs` and set the link to `https://talent.janus-soft.com/chat`.
3. Publish the site.

A button opens the chat in a full page, which works better on phones than an embedded frame. To embed instead, use **Insert**, then **Embed**, with the same URL. `PUBLIC_FRAME_ANCESTOR` must then include the frame origin Google Sites uses; check the browser console for a `frame-ancestors` error and add that origin, separated by spaces.

## Backups on the Spark

Option A keeps the database on the Spark, so back it up to the Synology every night. Run `crontab -e` and add:

```bash
15 2 * * * cd $HOME/spark-dev-workspace/projects/talent-chat && docker compose exec -T postgres pg_dump -U postgres -Fc talent > /mnt/synology/janus-soft/backups/talent-$(date +\%a).dump
```

This keeps one backup per weekday. To restore one: `docker compose exec -T postgres pg_restore -U postgres -d talent --clean < talent-Mon.dump`.

## Checklist

- [ ] Workspace mail and `www.janus-soft.com` still work after the name server change
- [ ] `https://talent.janus-soft.com/chat` loads, with a valid certificate
- [ ] `/admin` asks for a Google sign-in, then the app password
- [ ] Chat answers return in a few seconds
- [ ] The rate-limit rule is on
- [ ] The Careers page button opens the chat
- [ ] A nightly database backup runs (see [Backups on the Spark](#backups-on-the-spark), or [deploy.md](deploy.md) for Option B)
