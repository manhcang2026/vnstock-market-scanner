from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Callable, Iterable

from .models import FeedSpec, NewsItem
from .providers import ALL_FEEDS, CAFEF_FEEDS, VIETSTOCK_FEEDS
from .rss import fetch_feed
from .store import NewsStore
from .symbols import SymbolMapper

Fetcher = Callable[[FeedSpec], list[NewsItem]]


def _dedupe(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    output: list[NewsItem] = []
    for item in items:
        key = item.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def collect(
    feeds: Iterable[FeedSpec],
    *,
    timeout: float = 15.0,
    fetcher: Callable[..., list[NewsItem]] = fetch_feed,
) -> tuple[list[NewsItem], list[str]]:
    items: list[NewsItem] = []
    errors: list[str] = []
    for spec in feeds:
        try:
            items.extend(fetcher(spec, timeout=timeout))
        except Exception as exc:  # one bad feed must never block other providers
            errors.append(f"{spec.source}/{spec.category}: {type(exc).__name__}: {exc}")

    deduped = _dedupe(items)
    deduped.sort(key=lambda item: item.published_at or "", reverse=True)
    return deduped, errors


def _feeds_for(source: str) -> tuple[FeedSpec, ...]:
    if source == "cafef":
        return CAFEF_FEEDS
    if source == "vietstock":
        return VIETSTOCK_FEEDS
    return ALL_FEEDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and normalize CCC News RSS feeds")
    parser.add_argument("--source", choices=("all", "cafef", "vietstock"), default="all")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--db",
        type=Path,
        help="Optional isolated SQLite path. When omitted, collection is read-only.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("config/watchlist.csv"),
        help="Stock identity CSV used for deterministic symbol mapping.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    items, errors = collect(_feeds_for(args.source), timeout=args.timeout)

    if args.db is not None and items:
        mapper = None
        if args.metadata.exists():
            mapper = SymbolMapper.from_csv(args.metadata)
        else:
            print(f"WARN symbol metadata not found: {args.metadata}", file=sys.stderr)
        with NewsStore(args.db) as store:
            stats = store.upsert_many(items)
            mapped_articles = mapped_links = 0
            if mapper is not None:
                for item in items:
                    matches = mapper.match(item)
                    links = store.replace_symbols_for_url(item.url, matches)
                    if links:
                        mapped_articles += 1
                        mapped_links += links
            print(
                f"STORE db={args.db} inserted={stats.inserted} "
                f"updated={stats.updated} unchanged={stats.unchanged} total={store.count()}",
                file=sys.stderr,
            )
            if mapper is not None:
                print(
                    f"SYMBOLS identities={len(mapper.identities)} "
                    f"mapped_articles={mapped_articles} links={mapped_links}",
                    file=sys.stderr,
                )

    for error in errors:
        print(f"WARN {error}", file=sys.stderr)

    limit = max(0, args.limit)
    selected = items[:limit]
    if args.json:
        print(json.dumps([item.to_dict() for item in selected], ensure_ascii=False, indent=2))
    else:
        for item in selected:
            when = item.published_at or "NO_DATE"
            image = f" image={item.image_origin}" if item.image_url else ""
            print(f"[{item.source}/{item.category}] {when}{image}")
            print(item.title)
            if item.summary:
                print(item.summary[:240])
            print(item.url)
            print()

    # Partial provider failure is fail-open. A total provider outage is visible
    # to schedulers/ops through a non-zero exit status.
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
