# CCC News V1

Optional content ingestion for Chuyện Chợ Chứng. This service is deliberately isolated from SSI canonical market data and signal calculations.

## NEWS-01 scope

- Direct official RSS only: CafeF + Vietstock.
- Normalize title, summary, outbound URL, publication time, category and image metadata.
- One broken feed is fail-open; other feeds continue.
- NEWS-02 adds an isolated optional SQLite store (`ccc_news.db`) with persistent URL dedupe.
- No symbol mapping, AI sentiment or frontend integration yet.
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
