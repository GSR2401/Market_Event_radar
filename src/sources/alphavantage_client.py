import os
import time
from datetime import date
from typing import Optional

import requests

from src.types import SourceResult

_BASE = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    def __init__(self):
        self.api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        self.session = requests.Session()
        self._calls_today = 0
        self._daily_limit = 490  # stay under 500/day hard limit

    def _get(self, params: dict) -> SourceResult:
        if not self.api_key:
            return SourceResult(ok=False, data=None, error="ALPHA_VANTAGE_API_KEY not set", source="alphavantage")
        if self._calls_today >= self._daily_limit:
            return SourceResult(ok=False, data=None, error="daily quota reached", source="alphavantage")
        params["apikey"] = self.api_key
        for attempt in range(2):
            try:
                r = self.session.get(_BASE, params=params, timeout=15)
                r.raise_for_status()
                self._calls_today += 1
                time.sleep(12.5)  # 5 calls/min
                data = r.json()
                if "Information" in data:  # rate limit message
                    return SourceResult(ok=False, data=None, error=data["Information"], source="alphavantage")
                return SourceResult(ok=True, data=data, source="alphavantage")
            except Exception as exc:
                if attempt == 1:
                    return SourceResult(ok=False, data=None, error=str(exc), source="alphavantage")
                time.sleep(15)
        return SourceResult(ok=False, data=None, error="max retries", source="alphavantage")

    def get_news(self, tickers: list[str], limit: int = 20) -> SourceResult:
        ticker_str = ",".join(tickers[:5])  # API limit
        return self._get({"function": "NEWS_SENTIMENT", "tickers": ticker_str, "limit": limit})
