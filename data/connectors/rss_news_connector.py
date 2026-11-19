"""RSS news connector. Free public RSS feeds via feedparser.

Default source: Google News RSS search per company (public RSS endpoint).
Additional feeds can be configured with NEWS_RSS_FEEDS (comma-separated URLs).
Headlines are labelled unverified: a headline is not confirmed evidence.
"""
from __future__ import annotations

import os
from urllib.parse import quote_plus

import feedparser

from config import get_settings
from data.cache import cache_get, cache_set
from .base import BaseConnector, ConnectorResult

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"


class RSSNewsConnector(BaseConnector):
    name = "rss_news"
    type = "news"
    base_url = "https://news.google.com/rss"

    def _parse_feed(self, url: str) -> list[dict]:
        def _fetch():
            return feedparser.parse(url)

        feed = self._request_with_retry(_fetch, attempts=2, backoff_seconds=1.0)
        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError(f"feed parse failed: {getattr(feed, 'bozo_exception', 'unknown')}")
        items = []
        for entry in feed.entries[:40]:
            items.append(
                {
                    "headline": entry.get("title", "").strip(),
                    "url": entry.get("link", "").strip(),
                    "published": entry.get("published", ""),
                    "source": (entry.get("source", {}) or {}).get("title", "") or url,
                }
            )
        return [item for item in items if item["headline"] and item["url"]]

    def get_company_news(self, company_name: str, symbol: str) -> ConnectorResult:
        query = quote_plus(f'"{company_name}" stock')
        cache_key = f"rss:{symbol}"
        cached = cache_get(cache_key, get_settings().news_cache_ttl_minutes)
        if cached:
            payload, stored_at = cached
            return ConnectorResult(
                ok=True, source=self.name, data=payload, retrieved_at=stored_at, from_cache=True
            )
        try:
            items = self._parse_feed(GOOGLE_NEWS_RSS.format(query=query))
            cache_set(cache_key, items)
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=items)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_market_news(self) -> ConnectorResult:
        """Configured market feeds (NEWS_RSS_FEEDS env, comma separated)."""
        feeds = [f.strip() for f in os.environ.get("NEWS_RSS_FEEDS", "").split(",") if f.strip()]
        if not feeds:
            return ConnectorResult(
                ok=False, source=self.name,
                error="no market RSS feeds configured (set NEWS_RSS_FEEDS)",
            )
        all_items: list[dict] = []
        errors: list[str] = []
        for url in feeds:
            try:
                all_items.extend(self._parse_feed(url))
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        self.record_health(bool(all_items), "; ".join(errors) or None)
        return ConnectorResult(
            ok=bool(all_items), source=self.name, data=all_items,
            error="; ".join(errors) or None,
        )

    def health_check(self) -> ConnectorResult:
        try:
            items = self._parse_feed(GOOGLE_NEWS_RSS.format(query=quote_plus("NSE India")))
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=items[:5])
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))
