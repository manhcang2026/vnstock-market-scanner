# CCC News V1 — Staging/Production Runbook

Status: **backend running on `ccc-webhosting-01`; HTTP exposure is staging-only
on `beta.chuyenchochung.com` until the V4 production cutover.**

As-built documentation date: **2026-10-04**.

This file is the canonical operations reference for CCC News V1.

## 1. Deployment boundary

News runs on:

```text
ccc-webhosting-01
Ubuntu 24.04 LTS
Python 3.12
```

It does **not** run on `ccc-realtime-01` and does not use Supabase.

Existing market routing is a separate system:

```text
/api/v2/live  -> 10.0.0.226:8790
/api/v2/*     -> 10.0.0.226:8787
```

Do not change those routes as part of News maintenance.

## 2. Security/network contract

- VPS administration uses the existing Tailscale path.
- Do not open a new public firewall/security-list port for News.
- News API must bind only to `127.0.0.1:8795`.
- Never bind News to `0.0.0.0:8795`.
- `/health` is local/private and must not be exposed by Nginx.
- Collector requires outbound DNS/HTTPS access to CafeF and Vietstock.
- Existing VPS firewall/security rules remain untouched by News.

Audit:

```bash
sudo ss -lntp | grep ':8795'
```

Expected listener:

```text
127.0.0.1:8795
```

## 3. Filesystem and ownership

Canonical layout:

```text
/opt/ccc-news/
  app/                  # Git checkout
  venv/                 # Python virtual environment
  data/
    ccc_news.db          # persistent SQLite data

/etc/ccc-news/
  ccc-news.env
```

Ownership:

```text
root:root       /opt/ccc-news
root:root       /opt/ccc-news/app
root:root       /opt/ccc-news/venv
cccnews:cccnews /opt/ccc-news/data
root:cccnews    /etc/ccc-news
root:cccnews    /etc/ccc-news/ccc-news.env
```

The `cccnews` account is a system account with no interactive shell.

It is normal for the `ubuntu` SSH user to receive `Permission denied` when
listing `/opt/ccc-news/data` without `sudo`.

The database lives outside the Git checkout so a code deployment cannot
overwrite it.

## 4. Environment

Runtime file:

```text
/etc/ccc-news/ccc-news.env
```

Expected values:

```bash
NEWS_ENABLED=true
NEWS_DB_PATH=/opt/ccc-news/data/ccc_news.db
NEWS_API_HOST=127.0.0.1
NEWS_API_PORT=8795
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

Expected permissions:

```text
root:cccnews
0640
```

## 5. systemd units

Installed units:

```text
/etc/systemd/system/ccc-news-api.service
/etc/systemd/system/ccc-news-collect.service
/etc/systemd/system/ccc-news-collect.timer
```

Responsibilities:

- `ccc-news-api.service`: long-running localhost API;
- `ccc-news-collect.service`: one RSS collection pass (`Type=oneshot`);
- `ccc-news-collect.timer`: scheduled collection.

A successfully completed oneshot collector normally becomes:

```text
inactive (dead)
```

That is expected. Check the journal for `Deactivated successfully` and
`Finished ...`.

## 6. Resource limits

News is deliberately low-priority on the webhosting VPS.

### API

```text
CPUQuota   = 30%
MemoryMax  = 256 MB
Nice       = 5
IOWeight   = 50
```

### Collector

```text
CPUQuota   = 20%
MemoryMax  = 256 MB
Nice       = 10
IOWeight   = 20
Timeout    = 5 minutes
```

Audit:

```bash
systemctl show ccc-news-api.service \
  -p MemoryCurrent -p MemoryMax -p CPUQuotaPerSecUSec -p Nice -p IOWeight

systemctl show ccc-news-collect.service \
  -p MemoryMax -p CPUQuotaPerSecUSec -p Nice -p IOWeight
```

## 7. Collection schedule

Timezone: `Asia/Ho_Chi_Minh`.

Schedule:

```text
07:00 through 21:45  every 15 minutes
22:00                one run
00:15                late-night catch-up
00:16 through 06:59  no scheduled polling
```

systemd calendar:

```text
*-*-* 07..21:00,15,30,45:00 Asia/Ho_Chi_Minh
*-*-* 22:00:00 Asia/Ho_Chi_Minh
*-*-* 00:15:00 Asia/Ho_Chi_Minh
```

The host may display `NEXT/LAST` in UTC. Example: `00:00 UTC` equals `07:00`
Vietnam time.

Audit:

```bash
systemctl status ccc-news-collect.timer --no-pager -l
systemctl list-timers --all | grep ccc-news
sudo journalctl -u ccc-news-collect.service -n 50 --no-pager
```

At the time of this as-built update, manual collection and systemd-triggered
oneshot execution have passed. The first naturally scheduled 07:00 run remains
a post-documentation audit checkpoint.

## 8. Private API smoke tests

Run on `ccc-webhosting-01`:

```bash
curl -s http://127.0.0.1:8795/health
curl -s 'http://127.0.0.1:8795/v1/news?limit=3'
curl -s 'http://127.0.0.1:8795/v1/news/HPG?limit=3'
```

Expected health:

```text
ok=true
service=ccc-news-api
enabled=true
database_available=true
```

## 9. Nginx / staging-first rule

### Current staging state

News is exposed through:

```text
beta.chuyenchochung.com
```

Active beta vhost:

```text
/etc/nginx/sites-enabled/beta.chuyenchochung.com.conf
```

Beta webroot:

```text
/home/ccc-beta/htdocs/beta.chuyenchochung.com
```

Beta News routes:

```text
/api/v2/news
/api/v2/news/<SYMBOL>
```

They reverse proxy to:

```text
127.0.0.1:8795/v1/news
127.0.0.1:8795/v1/news/<SYMBOL>
```

The News locations must remain more specific than the generic `/api/v2/` market
location.

After any vhost edit:

```bash
sudo nginx -t
```

Reload only when the test succeeds:

```bash
sudo systemctl reload nginx
```

Do not expose `/health`.

### MAIN DOMAIN FREEZE

`chuyenchochung.com` is still serving the existing public version with real
users.

Main vhost:

```text
/etc/nginx/sites-enabled/chuyenchochung.com.conf
```

Main webroot:

```text
/home/ccc-main/htdocs/chuyenchochung.com
```

**Do not add News routes and do not deploy the V4 frontend to the main domain
during staging.**

Normal workflow:

```text
development
    -> beta.chuyenchochung.com
    -> functional/mobile/realtime/news testing
    -> product-owner approval
    -> one controlled production cutover
    -> chuyenchochung.com
```

Keep `beta.chuyenchochung.com` as the long-term staging environment after launch.

## 10. Beta smoke tests

From the webhosting VPS, bypass external DNS/CDN when needed:

```bash
curl -sk \
  --resolve beta.chuyenchochung.com:443:127.0.0.1 \
  'https://beta.chuyenchochung.com/api/v2/news?limit=2'

curl -sk \
  --resolve beta.chuyenchochung.com:443:127.0.0.1 \
  'https://beta.chuyenchochung.com/api/v2/news/HPG?limit=2'
```

Regression check for the existing market path:

```bash
curl -sk \
  --resolve beta.chuyenchochung.com:443:127.0.0.1 \
  -o /dev/null \
  -w 'quote HPG HTTP %{http_code}\n' \
  'https://beta.chuyenchochung.com/api/v2/quote/HPG'
```

Expected market regression result: HTTP `200`.

## 11. Manual collection and DB audit

Manual collector:

```bash
cd /opt/ccc-news/app

sudo -u cccnews \
  /opt/ccc-news/venv/bin/python \
  -m services.ccc_news.collector \
  --source all \
  --limit 0 \
  --db /opt/ccc-news/data/ccc_news.db \
  --metadata /opt/ccc-news/app/config/watchlist.csv
```

Repeated runs should normally show mostly/all `unchanged`. New inserts are
expected when providers publish new articles.

Quick DB counts:

```bash
sudo -u cccnews /opt/ccc-news/venv/bin/python - <<'PY'
import sqlite3
db = "/opt/ccc-news/data/ccc_news.db"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print("articles =", con.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0])
print("symbol_links =", con.execute("SELECT COUNT(*) FROM news_article_symbols").fetchone()[0])
con.close()
PY
```

## 12. Updating News code

Do not update the app by changing ownership to the SSH user.

Recommended controlled update:

```bash
sudo git -C /opt/ccc-news/app fetch origin
sudo git -C /opt/ccc-news/app checkout feat/ccc-news-v1
sudo git -C /opt/ccc-news/app pull --ff-only origin feat/ccc-news-v1
```

Then restart **only News** if runtime code changed:

```bash
sudo systemctl restart ccc-news-api.service
```

A News update must not restart SSI, chart, websocket or the market backend.

## 13. Logs and troubleshooting

API:

```bash
sudo systemctl status ccc-news-api.service --no-pager -l
sudo journalctl -u ccc-news-api.service -n 100 --no-pager
```

Collector:

```bash
sudo systemctl status ccc-news-collect.service --no-pager -l
sudo journalctl -u ccc-news-collect.service -n 100 --no-pager
```

Timer:

```bash
sudo systemctl status ccc-news-collect.timer --no-pager -l
systemctl list-timers --all | grep ccc-news
```

Nginx:

```bash
sudo nginx -t
sudo systemctl is-active nginx
```

The existing `ssl_stapling ignored, no OCSP responder URL` warnings are unrelated
to News unless accompanied by an actual Nginx syntax/configuration failure.

## 14. Emergency disable / rollback

Disable public staging News without touching market data:

1. restore/remove only the News block in the **beta** vhost;
2. run `sudo nginx -t`;
3. run `sudo systemctl reload nginx`.

Stop News API:

```bash
sudo systemctl stop ccc-news-api.service
```

Stop scheduled collection:

```bash
sudo systemctl stop ccc-news-collect.timer
```

Logical disable while keeping the service installed:

```text
NEWS_ENABLED=false
```

Then restart only:

```bash
sudo systemctl restart ccc-news-api.service
```

News failure must remain isolated from chart, scanner, signals and realtime.

## 15. Production cutover checklist

Only after the full V4 beta build is approved:

1. back up the current main frontend and main vhost;
2. deploy the exact approved V4 build to the main webroot;
3. add the two already-tested News locations to the main vhost;
4. run `sudo nginx -t`;
5. reload Nginx;
6. smoke-test News, quote/chart and WebSocket on the main domain;
7. keep beta available as staging.

Until that cutover, **the main domain is frozen for News/V4 changes**.
