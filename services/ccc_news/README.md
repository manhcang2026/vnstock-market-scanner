# CCC News V1

Optional content ingestion for Chuyện Chợ Chứng. This service is deliberately isolated from SSI canonical market data and signal calculations.

## NEWS-01 scope

- Direct official RSS only: CafeF + Vietstock.
- Normalize title, summary, outbound URL, publication time, category and image metadata.
- One broken feed is fail-open; other feeds continue.
- NEWS-02 adds an isolated optional SQLite store (`ccc_news.db`) with persistent URL dedupe.
- NEWS-03 adds conservative deterministic symbol mapping from `config/watchlist.csv`.
- No AI sentiment or frontend integration yet.
- Image discovery does **not** imply reuse permission. Every discovered source image starts as `UNREVIEWED`.

## Live smoke test

From repository root:

```bash
python -m services.ccc_news.collector --source all --limit 20
```

JSON output:

```bash
python -m services.ccc_news.collector --source all --limit 20 --json
```

The live smoke test needs internet access. Unit tests do not.

## Failure semantics

If CafeF fails, Vietstock is still collected, and vice versa. The CLI exits non-zero only when no usable news item was collected at all.

## Optional local storage

Collection stays read-only unless `--db` is supplied:

```bash
python -m services.ccc_news.collector --source all --limit 20 --db data/ccc_news.db
```

Repeated runs update `last_fetched_at` and do not create duplicate rows for the same outbound URL.
The news database is independent from every SSI/canonical market database.

`CafeF/BUSINESS` is intentionally collected at provider level even though the feed contains broad business/lifestyle items. NEWS-03 symbol mapping will decide which company-specific items are eligible for stock pages; broad unmatched BUSINESS items must not be surfaced there.


## Symbol mapping (NEWS-03)

When `--db` is supplied and `config/watchlist.csv` exists, every fetched article is mapped to listed symbols conservatively:

- unique company-name aliases may map in any category;
- bare ticker tokens map only in market/event categories when explicit stock context such as `cổ phiếu`, `cổ tức`, `chốt quyền` or insider-trading language is present;
- ambiguous company aliases are discarded;
- unmatched broad business stories remain stored but are not eligible for a stock-detail news query.

This is intentionally precision-first. Missing a weak relation is preferable to attaching an unrelated article to a stock.

## Standalone public API (NEWS-04)

News API is a separate process from SSI/realtime and reads only the isolated
`ccc_news.db`. Production target is `ccc-webhosting-01`; market/realtime services
do not import or depend on this package.

Run locally from repository root:

```bash
python -m services.ccc_news.api --db data/ccc_news.db --host 127.0.0.1 --port 8795
```

Public contract:

- `GET /v1/news?limit=20`
- `GET /v1/news/HPG?limit=10`
- private health probe: `GET /health`

Missing/disabled/corrupt news fails open with HTTP 200, `available=false` and an
empty item list. It must never affect chart, scanner, signals or market data.

Overview relevance is intentionally conservative:

- market/finance/event categories may appear without a symbol;
- broad `BUSINESS` and `SMART_MONEY` items appear only when deterministic mapping
  links them to at least one listed symbol.

Thumbnail projection never exposes an unreviewed source image. It falls back to
`SYMBOL` when the article maps to a ticker and `CATEGORY` otherwise.
