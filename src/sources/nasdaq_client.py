import time
from datetime import date, timedelta
from typing import List

import requests

from src.types import SourceResult

_BASE = "https://api.nasdaq.com/api/calendar/earnings"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _market_time(raw: str) -> str | None:
    r = (raw or "").lower()
    if "pre" in r or "before" in r or "bmo" in r:
        return "BMO"
    if "after" in r or "post" in r or "amc" in r:
        return "AMC"
    return None


class NasdaqClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    def _fetch_day(self, d: date) -> SourceResult:
        for attempt in range(3):
            try:
                r = self.session.get(_BASE, params={"date": d.isoformat()}, timeout=15)
                r.raise_for_status()
                time.sleep(0.5)
                data = r.json()
                rows = (data.get("data") or {}).get("rows") or []
                return SourceResult(ok=True, data=rows, source="nasdaq")
            except Exception as exc:
                if attempt == 2:
                    return SourceResult(ok=False, data=None, error=str(exc), source="nasdaq")
                time.sleep(2 ** attempt)
        return SourceResult(ok=False, data=None, error="max retries", source="nasdaq")

    def get_earnings_week(self, start: date, days: int = 7) -> SourceResult:
        """
        Fetches earnings for each trading day in [start, start+days).
        Returns a flat list of normalised entry dicts.
        """
        all_entries: List[dict] = []
        errors: List[str] = []

        current = start
        end = start + timedelta(days=days)
        while current < end:
            if current.weekday() < 5:  # Mon–Fri only
                result = self._fetch_day(current)
                if result.ok:
                    for row in (result.data or []):
                        symbol = (row.get("symbol") or "").strip().upper()
                        if not symbol:
                            continue
                        all_entries.append({
                            "symbol": symbol,
                            "name": row.get("name", ""),
                            "date": current.isoformat(),
                            "report_time": _market_time(row.get("time") or row.get("marketTime") or ""),
                            "eps_estimate": _safe_float(row.get("epsForecast")),
                            "source": "nasdaq",
                        })
                else:
                    errors.append(f"{current.isoformat()}: {result.error}")
            current += timedelta(days=1)

        if not all_entries and errors:
            return SourceResult(ok=False, data=None, error="; ".join(errors), source="nasdaq")

        return SourceResult(ok=True, data=all_entries, source="nasdaq",
                            error="; ".join(errors) if errors else None)


def _safe_float(val) -> float | None:
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except Exception:
        return None
