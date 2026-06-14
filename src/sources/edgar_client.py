import time
from datetime import date, timedelta

import requests

from src.types import SourceResult

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

MONITORED_8K_ITEMS = {"1.01", "1.02", "1.03", "2.01", "5.02", "8.01"}


class EdgarClient:
    def __init__(self, user_agent: str):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self._ticker_cik_map: dict = {}

    def _get(self, url: str, params: dict = None) -> SourceResult:
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=15)
                r.raise_for_status()
                time.sleep(0.15)  # stay well under 10 req/sec
                return SourceResult(ok=True, data=r.json(), source="edgar")
            except Exception as exc:
                if attempt == 2:
                    return SourceResult(ok=False, data=None, error=str(exc), source="edgar")
                time.sleep(2 ** attempt)
        return SourceResult(ok=False, data=None, error="max retries", source="edgar")

    def load_ticker_cik_map(self) -> bool:
        result = self._get(_COMPANY_TICKERS_URL)
        if not result.ok:
            return False
        for entry in result.data.values():
            self._ticker_cik_map[entry["ticker"].upper()] = entry["cik_str"]
        return True

    def get_cik(self, ticker: str) -> int | None:
        return self._ticker_cik_map.get(ticker.upper())

    def get_recent_8k_filings(self, lookback_days: int = 2) -> SourceResult:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        end = date.today().isoformat()
        result = self._get(_SEARCH_URL, params={
            "q": '""',
            "forms": "8-K",
            "dateRange": "custom",
            "startdt": start,
            "enddt": end,
            "_source": "hits.hits._source.period_of_report,hits.hits._source.file_date,"
                       "hits.hits._source.entity_name,hits.hits._source.file_num,"
                       "hits.hits._source.form_type",
            "from": 0,
            "size": 50,
        })
        if not result.ok:
            return result
        hits = result.data.get("hits", {}).get("hits", [])
        filings = []
        for h in hits:
            src = h.get("_source", {})
            filings.append({
                "entity_name": src.get("entity_name", ""),
                "file_date": src.get("file_date", ""),
                "period_of_report": src.get("period_of_report", ""),
                "accession_no": h.get("_id", "").replace(":", "-"),
            })
        return SourceResult(ok=True, data=filings, source="edgar")

    def get_8k_items_for_filing(self, accession_no: str, cik: int) -> SourceResult:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no.replace('-', '')}/{accession_no}-index.json"
        return self._get(url)
