# CCC News V1

Optional content ingestion for Chuyện Chợ Chứng. This service is deliberately isolated from SSI canonical market data and signal calculations.

## NEWS-01 scope

- Direct official RSS only: CafeF + Vietstock.
- Normalize title, summary, outbound URL, publication time, category and image metadata.
- One broken feed is fail-open; other feeds continue.
- No database, symbol mapping, AI sentiment or frontend integration in NEWS-01.
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
