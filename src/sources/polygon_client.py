import os
import time
from typing import Optional

import requests

from src.types import SourceResult

_BASE = "https://api.polygon.io/v3"


class PolygonClient:
    def __init__(self):
        self.api_key = os.environ.get("POLYGON_API_KEY", "")
        self.session = requests.Session()

    def _get(self, endpoint: str, params: Optional[dict] = None) -> SourceResult:
        if not self.api_key:
            return SourceResult(ok=False, data=None, error="POLYGON_API_KEY not set", source="polygon")
        p = params or {}
        p["apiKey"] = self.api_key
        for attempt in range(3):
            try:
                r = self.session.get(f"{_BASE}/{endpoint}", params=p, timeout=15)
                r.raise_for_status()
                time.sleep(12)  # 5 calls/min on free tier → 12s between calls
                return SourceResult(ok=True, data=r.json(), source="polygon")
            except Exception as exc:
                if attempt == 2:
                    return SourceResult(ok=False, data=None, error=str(exc), source="polygon")
                time.sleep(2 ** attempt)
        return SourceResult(ok=False, data=None, error="max retries", source="polygon")

    def get_options_snapshot(self, ticker: str) -> SourceResult:
        result = self._get(f"snapshot/options/{ticker}", {"limit": 50})
        if not result.ok:
            return result
        results = result.data.get("results", [])
        if not results:
            return SourceResult(ok=False, data=None, error="no options data", source="polygon")

        total_oi = sum(r.get("open_interest", 0) or 0 for r in results)
        total_vol = sum(r.get("day", {}).get("volume", 0) or 0 for r in results)
        call_vol = sum(
            r.get("day", {}).get("volume", 0) or 0
            for r in results if r.get("details", {}).get("contract_type") == "call"
        )
        put_vol = sum(
            r.get("day", {}).get("volume", 0) or 0
            for r in results if r.get("details", {}).get("contract_type") == "put"
        )
        pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else None
        return SourceResult(ok=True, data={
            "total_oi": total_oi,
            "current_volume": total_vol,
            "put_call_ratio": pc_ratio,
        }, source="polygon")
