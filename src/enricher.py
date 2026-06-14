import logging
from datetime import date, timedelta
from typing import List, Optional

from src.cache import Cache
from src.sources.finnhub_client import FinnhubClient
from src.sources.newsdata_client import NewsdataClient
from src.sources.yfinance_client import YFinanceClient
from src.types import MarketEvent

log = logging.getLogger(__name__)

_CAP_LARGE = 10_000_000_000
_CAP_MID = 2_000_000_000
_CAP_SMALL = 300_000_000


def classify_cap(market_cap: Optional[float]) -> Optional[str]:
    if market_cap is None:
        return None
    if market_cap >= _CAP_LARGE:
        return "LARGE"
    if market_cap >= _CAP_MID:
        return "MID"
    if market_cap >= _CAP_SMALL:
        return "SMALL"
    return "MICRO"


class Enricher:
    def __init__(
        self,
        yf: YFinanceClient,
        finnhub: FinnhubClient,
        newsdata: NewsdataClient,
        cache: Cache,
    ):
        self.yf = yf
        self.finnhub = finnhub
        self.newsdata = newsdata
        self.cache = cache

    def enrich_market_cap(self, event: MarketEvent) -> None:
        ticker = event.ticker
        cached = self.cache.get_weekly(f"mcap_{ticker}")
        if cached is not None:
            event.market_cap = cached
            event.cap_tier = classify_cap(cached)
            return

        result = self.yf.get_info(ticker)
        mcap = None
        if result.ok and result.data:
            mcap = result.data.get("marketCap")
            sector = result.data.get("sector")
            if sector:
                event.sector = sector
            name = result.data.get("longName") or result.data.get("shortName")
            if name and event.company_name == ticker:
                event.company_name = name

        if not mcap:
            # fallback: Finnhub company profile
            fp = self.finnhub.get_company_profile(ticker)
            if fp.ok and fp.data:
                mcap = fp.data.get("marketCapitalization")
                if mcap:
                    mcap = mcap * 1_000_000  # Finnhub returns in millions
                name = fp.data.get("name")
                if name and event.company_name == ticker:
                    event.company_name = name

        event.market_cap = mcap
        event.cap_tier = classify_cap(mcap)
        if mcap:
            self.cache.set_weekly(f"mcap_{ticker}", mcap)

    def enrich_news(self, event: MarketEvent) -> None:
        if event.event_type not in ("NEWS", "8K"):
            return  # earnings/IPO have their own summaries
        result = self.newsdata.search_ticker_news(event.ticker)
        if not result.ok or not result.data:
            return

        articles = result.data
        scored = sorted(
            articles,
            key=lambda a: self.newsdata.keyword_score(
                (a.get("title") or "") + " " + (a.get("description") or "")
            ),
            reverse=True,
        )
        if scored:
            top = scored[0]
            title = top.get("title", "")
            desc = top.get("description", "") or ""
            event.summary = f"{title}. {desc[:120]}".strip()
            if "newsdata" not in event.sources:
                event.sources.append("newsdata")

    def enrich_all(self, events: List[MarketEvent]) -> None:
        for event in events:
            try:
                self.enrich_market_cap(event)
            except Exception as exc:
                log.warning("%s: market cap enrichment failed: %s", event.ticker, exc)
            try:
                self.enrich_news(event)
            except Exception as exc:
                log.warning("%s: news enrichment failed: %s", event.ticker, exc)
