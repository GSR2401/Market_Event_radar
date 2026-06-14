import logging
from typing import Optional, Tuple

from src.cache import Cache
from src.sources.polygon_client import PolygonClient
from src.sources.yfinance_client import YFinanceClient
from src.types import MarketEvent

log = logging.getLogger(__name__)


class OptionsFilter:
    def __init__(
        self,
        yf: YFinanceClient,
        polygon: PolygonClient,
        cache: Cache,
        min_oi: int = 1000,
        min_avg_options_vol: int = 500,
        min_avg_stock_vol: int = 500_000,
    ):
        self.yf = yf
        self.polygon = polygon
        self.cache = cache
        self.min_oi = min_oi
        self.min_avg_options_vol = min_avg_options_vol
        self.min_avg_stock_vol = min_avg_stock_vol

    def _get_20d_avg_stock_volume(self, ticker: str) -> Optional[float]:
        cached = self.cache.get(f"stock_vol_20d_{ticker}")
        if cached is not None:
            return cached
        result = self.yf.get_history(ticker, period="1mo")
        if not result.ok:
            return None
        hist = result.data
        avg = float(hist["Volume"].mean()) if not hist.empty else None
        if avg is not None:
            self.cache.set(f"stock_vol_20d_{ticker}", avg)
        return avg

    def _get_options_data(self, ticker: str) -> Tuple[Optional[dict], str]:
        """Returns (data_dict, source_name). data_dict is None on failure."""
        cached = self.cache.get(f"options_{ticker}")
        if cached is not None:
            return cached, "cache"

        result = self.yf.get_options_chain(ticker)
        if result.ok and result.data:
            self.cache.set(f"options_{ticker}", result.data)
            return result.data, "yfinance"

        log.debug("%s: yfinance options failed (%s), trying polygon", ticker, result.error)
        fallback = self.polygon.get_options_snapshot(ticker)
        if fallback.ok and fallback.data:
            self.cache.set(f"options_{ticker}", fallback.data)
            return fallback.data, "polygon"

        return None, "none"

    def evaluate(self, event: MarketEvent) -> bool:
        """
        Returns True if the ticker passes the options gate.
        Mutates event with options metrics and activity_level.
        Marks event.data_available = False if both sources fail.
        """
        ticker = event.ticker

        # IPOs are exempt — they may not have a chain yet
        if event.event_type == "IPO":
            event.data_available = True
            return True

        stock_avg_vol = self._get_20d_avg_stock_volume(ticker)
        options_data, source = self._get_options_data(ticker)

        if options_data is None:
            log.warning("%s: options data unavailable from all sources", ticker)
            event.data_available = False
            return False  # exclude from digest, flagged in footer

        total_oi = options_data.get("total_oi", 0) or 0
        current_vol = options_data.get("current_volume", 0) or 0
        pc_ratio = options_data.get("put_call_ratio")

        # gate checks
        if total_oi < self.min_oi:
            log.debug("%s: failed OI gate (%d < %d)", ticker, total_oi, self.min_oi)
            return False
        if stock_avg_vol is not None and stock_avg_vol < self.min_avg_stock_vol:
            log.debug("%s: failed stock vol gate (%.0f)", ticker, stock_avg_vol)
            return False

        # compute 20d average options volume from cached history
        cached_20d = self.cache.get(f"options_avg_20d_{ticker}")
        avg_20d: Optional[float] = cached_20d

        if avg_20d is None:
            # use current_vol as a rough proxy on first run; we'll accumulate over days
            avg_20d = current_vol if current_vol > 0 else None
            if avg_20d:
                self.cache.set(f"options_avg_20d_{ticker}", avg_20d)

        if avg_20d is not None and avg_20d < self.min_avg_options_vol:
            log.debug("%s: failed avg options vol gate (%.0f)", ticker, avg_20d)
            return False

        # activity level
        if avg_20d and avg_20d > 0:
            ratio = current_vol / avg_20d
            if ratio >= 3.0:
                activity = "STRONG"
            elif ratio >= 1.5:
                activity = "MODERATE"
            else:
                activity = "NORMAL"
        else:
            activity = "NORMAL"

        # mutate event
        event.options_total_oi = total_oi
        event.options_current_volume = current_vol
        event.options_avg_volume_20d = avg_20d
        event.put_call_ratio = pc_ratio
        event.activity_level = activity
        event.stock_avg_volume_20d = stock_avg_vol
        if source not in event.sources:
            event.sources.append(source)

        return True
