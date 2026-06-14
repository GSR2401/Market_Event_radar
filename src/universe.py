import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List, Set

log = logging.getLogger(__name__)

# NYSE and NASDAQ common stock exchange identifiers returned by yfinance/finnhub
_VALID_EXCHANGES = {"NYQ", "NMS", "NGM", "NCM", "NYSE", "NASDAQ", "NYSEArca"}
# ETF/Fund suffixes to exclude
_EXCLUDE_SUFFIXES = (" ETF", " Fund", " Trust", " LP ", " L.P.")


def _is_valid_ticker(ticker: str) -> bool:
    if not ticker or len(ticker) > 5:
        return False
    if any(c in ticker for c in (".", "-", "/")):
        return False
    return True


def build_universe(
    watchlist_path: str,
    finnhub_earnings: list,
    yf_earnings: list,
    edgar_8k_tickers: List[str],
    top_n: int = 25,
) -> List[str]:
    tickers: Set[str] = set()

    # always include watchlist
    wl_path = Path(watchlist_path)
    if wl_path.exists():
        for line in wl_path.read_text().splitlines():
            t = line.strip().upper()
            if _is_valid_ticker(t):
                tickers.add(t)
                log.debug("watchlist: %s", t)

    # earnings tickers from Finnhub
    for entry in finnhub_earnings:
        t = entry.get("symbol", "").upper()
        if _is_valid_ticker(t):
            tickers.add(t)

    # earnings tickers from yfinance (list of dicts with 'ticker' key)
    for entry in yf_earnings:
        t = entry.get("ticker", "").upper()
        if _is_valid_ticker(t):
            tickers.add(t)

    # 8-K filers from EDGAR
    for t in edgar_8k_tickers:
        t = t.upper()
        if _is_valid_ticker(t):
            tickers.add(t)

    # filter: restrict to top_n non-watchlist + all watchlist
    watchlist_set: Set[str] = set()
    if wl_path.exists():
        watchlist_set = {
            line.strip().upper()
            for line in wl_path.read_text().splitlines()
            if _is_valid_ticker(line.strip().upper())
        }

    non_watchlist = [t for t in tickers if t not in watchlist_set]
    result = list(watchlist_set) + non_watchlist[:top_n]

    log.info("universe: %d tickers (%d watchlist, %d discovered)",
             len(result), len(watchlist_set), len(result) - len(watchlist_set))
    return sorted(set(result))
