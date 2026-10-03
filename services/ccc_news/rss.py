from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import FeedSpec, NewsItem

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = "CCC-News/1.0 (+https://chuyenchochung.com)"
_WS_RE = re.compile(r"\s+")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.first_image: str | None = None

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "img" or self.first_image:
            return
        values = {str(key).lower(): value for key, value in attrs}
        src = values.get("src") or values.get("data-src") or values.get("data-original")
        if src:
            self.first_image = html.unescape(str(src)).strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in node:
        if _local_name(child.tag) not in wanted:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(html.unescape(value))
    parser.close()
    return _WS_RE.sub(" ", " ".join(parser.parts)).strip()


def _description_image(value: str | None) -> str | None:
    if not value:
        return None
    parser = _HTMLTextExtractor()
    parser.feed(html.unescape(value))
    parser.close()
    return parser.first_image


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        parsed = None

    if parsed is None:
        candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.isoformat()


def _entry_link(node: ET.Element) -> str:
    direct = _child_text(node, "link")
    if direct:
        return html.unescape(direct).strip()

    # Atom feeds carry URLs in link[href]. Supporting this costs almost nothing
    # and makes the parser resilient if a provider changes feed format later.
    for child in node:
        if _local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return html.unescape(href).strip()
    return ""


def _entry_image(node: ET.Element, description: str | None) -> tuple[str | None, str | None]:
    for child in node:
        name = _local_name(child.tag)
        url = child.attrib.get("url") or child.attrib.get("href")
        if not url:
            continue

        if name == "enclosure":
            media_type = (child.attrib.get("type") or "").lower()
            if not media_type or media_type.startswith("image/"):
                return html.unescape(url).strip(), "RSS_ENCLOSURE"

        if name in {"thumbnail", "content"}:
            medium = (child.attrib.get("medium") or "").lower()
            media_type = (child.attrib.get("type") or "").lower()
            if name == "thumbnail" or medium == "image" or media_type.startswith("image/"):
                return html.unescape(url).strip(), "RSS_MEDIA"

    discovered = _description_image(description)
    if discovered:
        return discovered, "DESCRIPTION_HTML"
    return None, None


def _iter_entries(root: ET.Element) -> Iterable[ET.Element]:
    rss_items = [node for node in root.iter() if _local_name(node.tag) == "item"]
    if rss_items:
        return rss_items
    return [node for node in root.iter() if _local_name(node.tag) == "entry"]


def parse_feed(xml_bytes: bytes, spec: FeedSpec) -> list[NewsItem]:
    root = ET.fromstring(xml_bytes)
    output: list[NewsItem] = []

    for node in _iter_entries(root):
        title = _clean_text(_child_text(node, "title"))
        link = _entry_link(node)
        if not title or not link:
            # A news card without a title or canonical outbound link has no value
            # to CCC and cannot satisfy the source-attribution contract.
            continue

        description = _child_text(node, "description", "summary", "content", "encoded")
        summary = _clean_text(description)
        image_url, image_origin = _entry_image(node, description)
        published_at = _normalize_date(
            _child_text(node, "pubdate", "published", "updated", "date")
        )
        guid = _child_text(node, "guid", "id")

        output.append(
            NewsItem(
                source=spec.source,
                category=spec.category,
                feed_url=spec.url,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                guid=guid,
                image_url=image_url,
                image_origin=image_origin,
            )
        )

    return output


def fetch_feed(spec: FeedSpec, *, timeout: float = 15.0) -> list[NewsItem]:
    request = urllib.request.Request(
        spec.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return parse_feed(payload, spec)
