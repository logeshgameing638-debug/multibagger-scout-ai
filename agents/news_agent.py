"""Agent 7 - News Intelligence.

Fetches public RSS items for a company, dedupes by URL (database uniqueness),
classifies with a transparent keyword model, and labels every item
'unverified': a headline is not confirmed financial evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from data.connectors import default_registry
from database.connection import session_scope
from database.models import NewsArticle
from .base import AgentResult

AGENT_NAME = "news_intelligence"

POSITIVE_KEYWORDS = {
    "profit rises", "profit jumps", "record profit", "beats estimates", "order win",
    "wins order", "new contract", "expansion", "capacity addition", "acquisition",
    "upgrade", "dividend", "buyback", "revenue growth", "all-time high", "surges",
    "partnership", "approval", "wins bid", "mou signed",
}
NEGATIVE_KEYWORDS = {
    "loss", "fraud", "declines", "falls", "downgrade", "penalty", "fine",
    "investigation", "resigns", "default", "pledge", "sell-off", "crashes",
    "warning", "lawsuit", "raid", "misses estimates", "slumps", "debt concern",
}
MATERIAL_KEYWORDS = {
    "results", "earnings", "contract", "order", "merger", "acquisition", "expansion",
    "management", "regulatory", "legal", "dividend", "buyback", "capacity",
}


def _classify_sentiment(headline: str) -> str:
    text = headline.lower()
    pos = sum(1 for k in POSITIVE_KEYWORDS if k in text)
    neg = sum(1 for k in NEGATIVE_KEYWORDS if k in text)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _relevance(headline: str, company_name: str) -> str:
    text = headline.lower()
    name_hit = company_name.lower().split()[0] in text if company_name else False
    material = any(k in text for k in MATERIAL_KEYWORDS)
    if name_hit and material:
        return "high"
    if name_hit or material:
        return "medium"
    return "low"


def analyze(company_name: str, symbol: str, company_id: int | None = None) -> AgentResult:
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    registry = default_registry()
    rss = registry.get("rss_news")
    fetched = rss.get_company_news(company_name or symbol, symbol)
    if not fetched.ok:
        result.status = "failed"
        result.error = f"news fetch failed: {fetched.error}"
        return result.finish()

    items = []
    stored = 0
    duplicates = 0
    with session_scope() as session:
        for item in fetched.data:
            existing = session.scalar(select(NewsArticle).where(NewsArticle.url == item["url"]))
            if existing:
                duplicates += 1
                continue
            published_at = None
            if item.get("published"):
                try:
                    from email.utils import parsedate_to_datetime

                    published_at = parsedate_to_datetime(item["published"])
                except (TypeError, ValueError):
                    published_at = None
            article = NewsArticle(
                company_id=company_id,
                headline=item["headline"],
                source=item.get("source") or fetched.source,
                url=item["url"],
                published_at=published_at,
                sentiment=_classify_sentiment(item["headline"]),
                relevance=_relevance(item["headline"], company_name or symbol),
                verification_status="unverified",
            )
            session.add(article)
            stored += 1
            items.append(
                {
                    "headline": item["headline"],
                    "source": article.source,
                    "published": item.get("published"),
                    "url": item["url"],
                    "sentiment": article.sentiment,
                    "relevance": article.relevance,
                    "verification_status": "unverified",
                }
            )

    result.data = {
        "items": items,
        "stored_new": stored,
        "duplicates_skipped": duplicates,
        "note": "headlines are unverified signals, not confirmed financial evidence",
    }
    result.sources.append("rss_news")
    return result.finish()
