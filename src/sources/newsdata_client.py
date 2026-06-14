import os
import time
from typing import Optional

import requests

from src.types import SourceResult

_BASE = "https://newsdata.io/api/1/news"

NEWS_KEYWORDS = [
    "merger", "acquisition", "ruling", "settlement", "approval", "award",
    "verdict", "contract", "FDA", "regulatory", "earnings", "guidance",
    "lawsuit", "investigation", "bankruptcy", "deal", "buyout",
]


class NewsdataClient:
    def __init__(self):
        self.api_key = os.environ.get("NEWSDATA_API_KEY", "")
        self.session = requests.Session()

    def _get(self, params: dict) -> SourceResult:
        if not self.api_key:
            return SourceResult(ok=False, data=None, error="NEWSDATA_API_KEY not set", source="newsdata")
        params["apikey"] = self.api_key
        for attempt in range(2):
            try:
                r = self.session.get(_BASE, params=params, timeout=15)
                r.raise_for_status()
                time.sleep(1)
                data = r.json()
                if data.get("status") != "success":
                    return SourceResult(ok=False, data=None, error=data.get("message", "API error"), source="newsdata")
                return SourceResult(ok=True, data=data.get("results", []), source="newsdata")
            except Exception as exc:
                if attempt == 1:
                    return SourceResult(ok=False, data=None, error=str(exc), source="newsdata")
                time.sleep(5)
        return SourceResult(ok=False, data=None, error="max retries", source="newsdata")

    def search_ticker_news(self, ticker: str) -> SourceResult:
        return self._get({
            "q": ticker,
            "language": "en",
            "category": "business",
            "size": 10,
        })

    def keyword_score(self, text: str) -> int:
        text_lower = text.lower()
        return sum(1 for kw in NEWS_KEYWORDS if kw in text_lower)
