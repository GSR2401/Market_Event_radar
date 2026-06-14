import os
import time
from datetime import date
from typing import Optional

import requests

from src.types import SourceResult

_BASE = "https://finnhub.io/api/v1"


class FinnhubClient:
    def __init__(self):
        self.api_key = os.environ.get("FINNHUB_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({"X-Finnhub-Token": self.api_key})

    def _get(self, endpoint: str, params: Optional[dict] = None) -> SourceResult:
        if not self.api_key:
            return SourceResult(ok=False, data=None, error="FINNHUB_API_KEY not set", source="finnhub")
        for attempt in range(3):
            try:
                r = self.session.get(f"{_BASE}/{endpoint}", params=params, timeout=15)
                r.raise_for_status()
                time.sleep(1.1)
                return SourceResult(ok=True, data=r.json(), source="finnhub")
            except Exception as exc:
                if attempt == 2:
                    return SourceResult(ok=False, data=None, error=str(exc), source="finnhub")
                time.sleep(2 ** attempt)
        return SourceResult(ok=False, data=None, error="max retries", source="finnhub")

    def get_earnings_calendar(self, start: date, end: date) -> SourceResult:
        result = self._get("calendar/earnings", {"from": start.isoformat(), "to": end.isoformat()})
        if result.ok and isinstance(result.data, dict):
            return SourceResult(ok=True, data=result.data.get("earningsCalendar", []), source="finnhub")
        return result

    def get_ipo_calendar(self, start: date, end: date) -> SourceResult:
        result = self._get("calendar/ipo", {"from": start.isoformat(), "to": end.isoformat()})
        if result.ok and isinstance(result.data, dict):
            return SourceResult(ok=True, data=result.data.get("ipoCalendar", []), source="finnhub")
        return result

    def get_company_news(self, symbol: str, start: date, end: date) -> SourceResult:
        return self._get("company-news", {
            "symbol": symbol, "from": start.isoformat(), "to": end.isoformat()
        })

    def get_company_profile(self, symbol: str) -> SourceResult:
        return self._get("stock/profile2", {"symbol": symbol})

    def get_filings(self, symbol: str) -> SourceResult:
        return self._get("stock/filings", {"symbol": symbol, "form": "8-K"})
