import logging
from datetime import date, timedelta
from typing import List, Tuple

from src.sources.edgar_client import EdgarClient, MONITORED_8K_ITEMS
from src.sources.finnhub_client import FinnhubClient
from src.sources.yfinance_client import YFinanceClient
from src.types import MarketEvent, SourceResult

log = logging.getLogger(__name__)


def fetch_earnings(
    finnhub: FinnhubClient,
    yf: YFinanceClient,
    start: date,
    end: date,
) -> Tuple[List[dict], List[dict], List[str]]:
    """Returns (finnhub_entries, yf_entries, diagnostics)."""
    diag: List[str] = []

    fh_result = finnhub.get_earnings_calendar(start, end)
    fh_entries = []
    if fh_result.ok:
        fh_entries = fh_result.data or []
        log.info("finnhub earnings: %d entries", len(fh_entries))
    else:
        diag.append(f"Finnhub earnings failed: {fh_result.error}")
        log.warning("finnhub earnings failed: %s", fh_result.error)

    return fh_entries, [], diag  # yfinance earnings fetched per-ticker in enricher


def fetch_8k_filings(
    edgar: EdgarClient,
    finnhub: FinnhubClient,
) -> Tuple[List[dict], List[str]]:
    """Returns (filings, diagnostics)."""
    diag: List[str] = []

    edgar_result = edgar.get_recent_8k_filings(lookback_days=2)
    if edgar_result.ok:
        filings = edgar_result.data or []
        log.info("edgar 8-K filings: %d", len(filings))
        return filings, diag

    diag.append(f"EDGAR 8-K failed: {edgar_result.error}")
    log.warning("EDGAR 8-K failed, trying finnhub fallback")

    # Finnhub doesn't have a bulk 8-K endpoint on free tier; return empty with diagnostic
    diag.append("Finnhub 8-K fallback: not available on free tier — EDGAR outage means no 8-K section today")
    return [], diag


def extract_8k_tickers(filings: List[dict], edgar: EdgarClient) -> List[str]:
    """Pull ticker symbols from EDGAR 8-K filings via the CIK map."""
    if not edgar._ticker_cik_map:
        edgar.load_ticker_cik_map()

    cik_to_ticker = {str(v): k for k, v in edgar._ticker_cik_map.items()}
    tickers = []
    for filing in filings:
        # EDGAR search returns entity_name but not ticker directly
        # We match via CIK map if available; otherwise skip
        accession = filing.get("accession_no", "")
        if accession:
            # accession format: 0001234567-26-000001 → CIK is first 10 digits
            parts = accession.split("-")
            if parts:
                cik = str(int(parts[0]))
                ticker = cik_to_ticker.get(cik)
                if ticker:
                    tickers.append(ticker)
    return list(set(tickers))
