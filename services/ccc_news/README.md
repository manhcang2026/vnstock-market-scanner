# CCC News V1 — Architecture & Data Contract

Status: **running on CCC staging infrastructure**.
As-built documentation date: **2026-10-04**.

CCC News V1 is an optional content layer for Chuyện Chợ Chứng. It enriches the
website with market/company news while remaining deliberately isolated from SSI
canonical market data, chart, scanner and signal calculations.

News is **not** a realtime trading-signal source. Market price/volume remains the
authoritative layer. News may arrive later and must never block, alter or become
a dependency of market data.

## 1. Architecture

```text
CafeF RSS ─────┐
               ├─> collector ─> normalize/dedupe/map ─> ccc_news.db
Vietstock RSS ─┘                                      │
                                                      ▼
                                             standalone News API
                                             127.0.0.1:8795
                                                      │
                                                      ▼
                                        Nginx on ccc-webhosting-01
                                                      │
                                              beta /api/v2/news
```

News runs on `ccc-webhosting-01`. It does not run on `ccc-realtime-01` and does
not use Supabase.

The existing market path remains separate:

```text
webhosting Nginx
  ├─ market HTTP  -> 10.0.0.226:8787
  └─ market WS    -> 10.0.0.226:8790
```

No News module is imported by `services/ssi_realtime_shadow`.

## 2. Sources and collection

V1 uses direct official RSS only:

- CafeF
- Vietstock

The collector stores normalized:

- source and category;
- title and RSS summary;
- canonical outbound article URL;
- publication time;
- feed URL/GUID;
- discovered image metadata;
- deterministic stock-symbol links.

One broken feed is fail-open: other feeds continue. The collector returns a
non-zero exit status only when no usable item is collected at all.

Full article crawling, AI sentiment and price/news reaction analysis are
intentionally out of scope for V1.

## 3. Storage

News has its own SQLite database:

```text
/opt/ccc-news/data/ccc_news.db
```

Primary tables:

### `news_articles`

Stores normalized article metadata. Canonical outbound `url` is unique and is
the persistent dedupe key.

Important fields include:

- `source`
- `category`
- `title`
- `summary`
- `url`
- `published_at`
- `guid`
- `image_url`
- `image_origin`
- `image_usage_status`
- `content_hash`
- fetch/create/update timestamps

### `news_article_symbols`

Stores deterministic article-to-stock relations:

- `article_id`
- `symbol`
- `match_type` (`TICKER` or `NAME`)
- `matched_text`

Repeated collection is idempotent: an already-known URL is updated/marked
unchanged rather than inserted as a duplicate.

The News database is independent from all SSI/canonical market databases.

## 4. Symbol mapping

Stock identities come from:

```text
config/watchlist.csv
```

Mapping is intentionally **precision-first**. Missing a weak relationship is
preferable to attaching unrelated news to a stock.

Rules:

- unique strong company-name aliases may map in any category;
- bare tickers are accepted conservatively only in market/event contexts;
- ambiguous company-name aliases are discarded;
- broad unmatched `BUSINESS`/`SMART_MONEY` stories remain stored but are not
  eligible for stock-detail news.

Important Vietnamese false-positive rule:

Ticker detection must use uppercase ASCII tokens from the **original source
text**, not the accent-stripped normalized text. Otherwise common Vietnamese
words such as `vừa` and `trả` can normalize to real listed tickers such as
`VUA` and `TRA`.

Generic ambiguous uppercase tokens such as `CEO`, `API` and `NET` are blocked
from bare-ticker inference.

## 5. Image policy

RSS image discovery is metadata discovery only; it does **not** imply permission
to reuse an image.

Every discovered source image starts as:

```text
image_usage_status = UNREVIEWED
```

The public API exposes a source image only when its usage status is explicitly
approved. Otherwise the frontend receives a safe fallback projection:

- `thumbnail_mode=SYMBOL` for symbol-linked news;
- `thumbnail_mode=CATEGORY` when no stock logo is available.

This lets News cards have a visual fallback without assuming third-party image
rights.

## 6. Standalone API contract

Local process:

```bash
python -m services.ccc_news.api \
  --db /opt/ccc-news/data/ccc_news.db \
  --host 127.0.0.1 \
  --port 8795
```

Routes:

```text
GET /v1/news?limit=20
GET /v1/news/HPG?limit=10
GET /health
```

Public payload contract:

```text
contract_version = ccc-news-v1
available
count
items
symbol                  # stock-specific route only
reason                  # DISABLED / UNAVAILABLE when applicable
```

Article items expose normalized content plus:

```text
symbols
thumbnail_mode
thumbnail_url
thumbnail_symbol
thumbnail_category
```

`limit` is clamped to `1..50`.

## 7. Failure semantics

News is optional. Missing, disabled or unreadable News data must never affect the
market application.

When News is disabled/unavailable, public News endpoints fail open with:

```text
HTTP 200
available=false
count=0
items=[]
```

No market/chart/scanner/SSI service needs to restart when News is stopped.

## 8. Overview relevance

The generic `/v1/news` feed is conservative.

Market/event categories may appear without a symbol. Broad categories such as
`BUSINESS` and `SMART_MONEY` are eligible only when deterministic symbol mapping
links the article to at least one listed stock.

Stock-specific `/v1/news/<SYMBOL>` uses `news_article_symbols`; the frontend does
not need to perform fuzzy symbol matching.

## 9. Current staging state

The News backend is installed and running on `ccc-webhosting-01`.

Current staging HTTP contract:

```text
https://beta.chuyenchochung.com/api/v2/news
https://beta.chuyenchochung.com/api/v2/news/HPG
```

The main public domain `chuyenchochung.com` remains on the existing public
version and **must not expose News until the controlled V4 production cutover**.

Frontend News integration is intentionally deferred until the V4 Overview layout
is stable.

See `services/ccc_news/ops/README.md` for the live operating runbook.
