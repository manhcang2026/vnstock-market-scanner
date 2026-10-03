# CCC News production operations

This directory contains the deployment contract for **NEWS-05**.

The production target is `ccc-webhosting-01`. News is intentionally isolated
from SSI/realtime and from Supabase.

## Network contract

- Administration: SSH only through the existing Tailscale path.
- Public traffic: existing HTTPS website only.
- News API: `127.0.0.1:8795` only. Never bind it to `0.0.0.0`.
- Existing inter-VPS market/chart/WebSocket routes are out of scope and must not
  be modified by the News deployment.
- Collector needs outbound HTTPS/DNS access to CafeF and Vietstock.

## Filesystem contract

```text
/opt/ccc-news/app
/opt/ccc-news/venv
/opt/ccc-news/data/ccc_news.db
/etc/ccc-news/ccc-news.env
```

The database lives outside the Git checkout so code deployments cannot overwrite
it.

Recommended ownership:

```text
root:root       /opt/ccc-news
root:root       /opt/ccc-news/app
root:root       /opt/ccc-news/venv
cccnews:cccnews /opt/ccc-news/data
root:cccnews    /etc/ccc-news
root:cccnews    /etc/ccc-news/ccc-news.env
```

The service account should have no interactive login.

## Environment

Copy `ccc-news.env.example` to `/etc/ccc-news/ccc-news.env`.

The environment file contains no feed/API secret today, but keep it non-public
so future configuration can be added safely.

## Collection schedule

The collector is deliberately not realtime. It runs on Vietnam time:

- every 15 minutes from `07:00` through `21:45`;
- once at `22:00`;
- once at `00:15` as a late-night catch-up;
- no scheduled polling from `00:16` through `06:59`.

A full RSS pass deduplicates into the same SQLite database, so articles published
while the collector is sleeping are picked up on the next run.

The collector has explicit CPU, memory, I/O priority and runtime limits so a
provider anomaly cannot compete aggressively with the web workload.

## systemd

Install these units under `/etc/systemd/system/` only after validating production
paths:

- `ccc-news-api.service`
- `ccc-news-collect.service`
- `ccc-news-collect.timer`

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ccc-news-api.service
sudo systemctl enable --now ccc-news-collect.timer
```

Run one initial collection manually before public routing:

```bash
sudo systemctl start ccc-news-collect.service
sudo systemctl status ccc-news-collect.service --no-pager
```

Private smoke tests on the webhosting VPS:

```bash
curl -fsS http://127.0.0.1:8795/health
curl -fsS 'http://127.0.0.1:8795/v1/news?limit=3'
curl -fsS 'http://127.0.0.1:8795/v1/news/HPG?limit=3'
```

## Nginx / CloudPanel

Do **not** paste the snippet blindly. First inspect the active CloudPanel vhost.

The two News locations must appear before the existing generic `/api/v2/`
market route:

```nginx
location = /api/v2/news {
    proxy_pass http://127.0.0.1:8795/v1/news;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
}

location /api/v2/news/ {
    proxy_pass http://127.0.0.1:8795/v1/news/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
}
```

Do not proxy `/health` publicly.

After editing the real vhost:

```bash
sudo nginx -t
```

Reload only after the config test passes.

## Fail-open behavior

If the database is missing, disabled or unreadable, the public News API returns
HTTP 200 with `available=false` and an empty item list.

Stopping News must not require stopping or restarting the market/chart backend.

Emergency disable:

```bash
sudo systemctl stop ccc-news-api.service
```

or set `NEWS_ENABLED=false` in `/etc/ccc-news/ccc-news.env` and restart only the
News API.

## Logs and timer audit

```bash
journalctl -u ccc-news-api.service -n 100 --no-pager
journalctl -u ccc-news-collect.service -n 100 --no-pager
systemctl list-timers ccc-news-collect.timer
systemd-analyze calendar '*-*-* 07..21:00,15,30,45:00 Asia/Ho_Chi_Minh'
systemd-analyze calendar '*-*-* 22:00:00 Asia/Ho_Chi_Minh'
systemd-analyze calendar '*-*-* 00:15:00 Asia/Ho_Chi_Minh'
```
