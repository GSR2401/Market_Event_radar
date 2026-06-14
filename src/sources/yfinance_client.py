import time
from datetime import date, timedelta
from typing import Optional

import yfinance as yf

from src.types import SourceResult


class YFinanceClient:
    def get_earnings_dates(self, ticker: str) -> SourceResult:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            time.sleep(0.5)
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                return SourceResult(ok=False, data=None, error="no calendar data", source="yfinance")
            # calendar is a dict with 'Earnings Date' key (list of dates)
            if isinstance(cal, dict):
                dates = cal.get("Earnings Date", [])
                if not dates:
                    return SourceResult(ok=False, data=None, error="no earnings dates", source="yfinance")
                return SourceResult(ok=True, data={"dates": dates, "ticker": ticker}, source="yfinance")
            return SourceResult(ok=False, data=None, error="unexpected calendar format", source="yfinance")
        except Exception as exc:
            return SourceResult(ok=False, data=None, error=str(exc), source="yfinance")

    def get_options_chain(self, ticker: str) -> SourceResult:
        try:
            t = yf.Ticker(ticker)
            expirations = t.options
            time.sleep(0.5)
            if not expirations:
                return SourceResult(ok=False, data=None, error="no options expirations", source="yfinance")

            total_oi = 0
            total_volume = 0
            total_calls = 0
            total_puts = 0

            for exp in expirations[:6]:  # sample first 6 expirations to stay fast
                try:
                    chain = t.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts
                    total_oi += int(calls["openInterest"].sum() + puts["openInterest"].sum())
                    total_volume += int(calls["volume"].fillna(0).sum() + puts["volume"].fillna(0).sum())
                    total_calls += int(calls["volume"].fillna(0).sum())
                    total_puts += int(puts["volume"].fillna(0).sum())
                    time.sleep(0.3)
                except Exception:
                    continue

            pc_ratio = round(total_puts / total_calls, 2) if total_calls > 0 else None
            return SourceResult(ok=True, data={
                "total_oi": total_oi,
                "current_volume": total_volume,
                "put_call_ratio": pc_ratio,
                "expirations_count": len(expirations),
            }, source="yfinance")
        except Exception as exc:
            return SourceResult(ok=False, data=None, error=str(exc), source="yfinance")

    def get_info(self, ticker: str) -> SourceResult:
        try:
            info = yf.Ticker(ticker).info
            time.sleep(0.5)
            if not info or info.get("regularMarketPrice") is None and info.get("marketCap") is None:
                return SourceResult(ok=False, data=None, error="empty info", source="yfinance")
            return SourceResult(ok=True, data=info, source="yfinance")
        except Exception as exc:
            return SourceResult(ok=False, data=None, error=str(exc), source="yfinance")

    def get_history(self, ticker: str, period: str = "1mo") -> SourceResult:
        try:
            hist = yf.Ticker(ticker).history(period=period)
            time.sleep(0.5)
            if hist.empty:
                return SourceResult(ok=False, data=None, error="empty history", source="yfinance")
            return SourceResult(ok=True, data=hist, source="yfinance")
        except Exception as exc:
            return SourceResult(ok=False, data=None, error=str(exc), source="yfinance")
