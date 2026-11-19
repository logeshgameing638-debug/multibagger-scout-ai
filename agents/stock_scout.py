"""Agent 1 - Stock Scout: discover and shortlist Indian listed companies.

Discovery sources are real provider files (NSE index constituent CSVs) or a
user-supplied custom list. Prices/liquidity come from the yfinance connector.
A listing or symbol is never invented: everything traces to a source.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from data.connectors import default_registry
from data.validation import validate_bse_symbol, validate_nse_symbol
from .base import AgentResult

AGENT_NAME = "stock_scout"


def _enrich_with_price(connector, candidate: dict) -> dict:
    symbol = candidate["symbol"]
    exchange = candidate.get("exchange", "NSE")
    enriched = dict(candidate)
    price_result = connector.get_price(symbol, exchange)
    if price_result.ok:
        enriched["price"] = price_result.data["close"]
        enriched["volume"] = price_result.data["volume"]
        enriched["price_as_of"] = price_result.data["as_of"]
        enriched["data_available"] = True
        enriched["delayed"] = price_result.delayed
    else:
        enriched["price"] = None
        enriched["volume"] = None
        enriched["data_available"] = False
        enriched["price_error"] = price_result.error
    return enriched


def _liquidity_score(price: float | None, volume: float | None) -> float | None:
    """Daily traded value in INR (price x volume). None when unknown."""
    if price is None or volume is None:
        return None
    return price * volume


def discover(
    index: str = "NIFTY 50",
    limit: int = 50,
    custom_symbols: list[tuple[str, str]] | None = None,
    sector_filter: str | None = None,
    min_market_cap: float | None = None,
    max_market_cap: float | None = None,
    max_workers: int = 8,
) -> AgentResult:
    """Discover and rank research candidates.

    custom_symbols: list of (symbol, exchange) tuples. When provided, only
    validated symbols from the list are used.
    """
    started = datetime.now(timezone.utc)
    result = AgentResult(agent_name=AGENT_NAME, status="success", started_at=started)
    registry = default_registry()
    yf = registry.get("yahoo_finance")

    candidates: list[dict] = []
    if custom_symbols:
        for symbol, exchange in custom_symbols:
            symbol = symbol.strip().upper()
            exchange = exchange.strip().upper()
            valid = validate_nse_symbol(symbol) if exchange == "NSE" else validate_bse_symbol(symbol)
            if not valid:
                result.warnings.append(f"rejected invalid {exchange} symbol: {symbol}")
                continue
            candidates.append({"symbol": symbol, "exchange": exchange, "name": symbol, "source": "user"})
        result.sources.append("user_supplied_list")
    else:
        nse = registry.get("nse_archives")
        listing = nse.get_index_constituents(index)
        if not listing.ok:
            result.status = "failed"
            result.error = f"NSE discovery failed: {listing.error}"
            return result.finish()
        candidates = [
            {**row, "source": f"nse_archives:{index}"} for row in listing.data[: max(limit, 1)]
        ]
        result.sources.append("nse_archives")

    # Enrich with prices in parallel; failures stay visible per candidate.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_enrich_with_price, yf, c): c for c in candidates}
        enriched: list[dict] = []
        for future in as_completed(futures):
            try:
                enriched.append(future.result())
            except Exception as exc:
                original = futures[future]
                original["data_available"] = False
                original["price_error"] = str(exc)
                enriched.append(original)

    # Optional info enrichment for sector / market-cap filtering.
    if sector_filter or min_market_cap is not None or max_market_cap is not None:
        for candidate in enriched:
            info = yf.get_info(candidate["symbol"], candidate.get("exchange", "NSE"))
            if info.ok:
                candidate["sector"] = info.data.get("sector")
                candidate["industry"] = info.data.get("industry") or candidate.get("industry")
                candidate["market_cap"] = info.data.get("marketCap")
        if sector_filter:
            wanted = sector_filter.strip().lower()
            enriched = [c for c in enriched if (c.get("sector") or "").lower() == wanted]
        if min_market_cap is not None:
            enriched = [c for c in enriched if (c.get("market_cap") or 0) >= min_market_cap]
        if max_market_cap is not None:
            enriched = [c for c in enriched if (c.get("market_cap") or 0) <= max_market_cap]

    for candidate in enriched:
        candidate["daily_traded_value"] = _liquidity_score(
            candidate.get("price"), candidate.get("volume")
        )

    # Rank: data availability first, then traded value (liquidity), unknowns last.
    enriched.sort(
        key=lambda c: (
            not c.get("data_available", False),
            -(c.get("daily_traded_value") or 0),
        )
    )
    for rank, candidate in enumerate(enriched, start=1):
        candidate["rank"] = rank

    unavailable = [c["symbol"] for c in enriched if not c.get("data_available")]
    if unavailable:
        result.missing.append(f"no price data for: {', '.join(unavailable)}")
        if len(unavailable) == len(enriched) and enriched:
            result.status = "failed"
            result.error = "price provider unavailable for every candidate"
        elif unavailable:
            result.status = "partial"

    result.data = {"candidates": enriched, "count": len(enriched), "index": index}
    return result.finish()
