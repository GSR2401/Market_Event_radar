import logging
from datetime import date, timedelta
from typing import List, Tuple

from src.sources.edgar_client import EdgarClient, MONITORED_8K_ITEMS
from src.sources.finnhub_client import FinnhubClient
from src.sources.nasdaq_client import NasdaqClient
from src.sources.yfinance_client import YFinanceClient
from src.types import MarketEvent, SourceResult

log = logging.getLogger(__name__)


def fetch_earnings(
    nasdaq: NasdaqClient,
    finnhub: FinnhubClient,
    start: date,
    end: date,
) -> Tuple[List[dict], List[str]]:
    """
    Returns (merged_entries, diagnostics).

    Primary:   Nasdaq free calendar API — full market list, no key needed.
    Secondary: Finnhub earnings calendar — fills any gap on Nasdaq failure.

    Each entry dict has keys: symbol, name, date, report_time, eps_estimate, source.
    """
    diag: List[str] = []
    days = (end - start).days

    # ── Primary: Nasdaq ──────────────────────────────────────────────────
    nasdaq_result = nasdaq.get_earnings_week(start, days=days)
    nasdaq_entries: List[dict] = []

    if nasdaq_result.ok:
        nasdaq_entries = nasdaq_result.data or []
        log.info("nasdaq earnings: %d entries across %d days", len(nasdaq_entries), days)
        if nasdaq_result.error:
            # partial success — some days failed
            diag.append(f"Nasdaq partial: {nasdaq_result.error}")
    else:
        diag.append(f"Nasdaq earnings failed: {nasdaq_result.error}")
        log.warning("Nasdaq earnings failed: %s", nasdaq_result.error)

    # ── Secondary: Finnhub (fills gaps or acts as full fallback) ─────────
    fh_entries: List[dict] = []
    fh_result = finnhub.get_earnings_calendar(start, end)
    if fh_result.ok:
        for row in (fh_result.data or []):
            sym = (row.get("symbol") or "").upper()
            if sym:
                fh_entries.append({
                    "symbol": sym,
                    "name": row.get("symbol", sym),
                    "date": row.get("date", ""),
                    "report_time": _map_fh_time(row.get("hour", "")),
                    "eps_estimate": row.get("epsEstimate"),
                    "source": "finnhub",
                })
        log.info("finnhub earnings: %d entries", len(fh_entries))
    else:
        diag.append(f"Finnhub earnings failed: {fh_result.error}")
        log.warning("Finnhub earnings failed: %s", fh_result.error)

    # ── Merge: union by symbol, Nasdaq wins on conflict ──────────────────
    merged: dict[str, dict] = {}

    for entry in fh_entries:
        merged[entry["symbol"]] = entry

    for entry in nasdaq_entries:          # Nasdaq overwrites Finnhub
        sym = entry["symbol"]
        if sym in merged:
            entry["sources"] = ["nasdaq", "finnhub"]
        else:
            entry["sources"] = ["nasdaq"]
        merged[sym] = entry

    # Mark Finnhub-only entries
    for sym, entry in merged.items():
        if "sources" not in entry:
            entry["sources"] = ["finnhub"]

    result = list(merged.values())
    log.info("merged earnings universe: %d unique tickers", len(result))
    return result, diag


def _map_fh_time(hour: str) -> str | None:
    h = (hour or "").lower()
    if h in ("bmo", "before market open", "pre-market"):
        return "BMO"
    if h in ("amc", "after market close", "after-hours"):
        return "AMC"
    return None


def fetch_8k_filings(
    edgar: EdgarClient,
    finnhub: FinnhubClient,
) -> Tuple[List[dict], List[str]]:
    diag: List[str] = []

    edgar_result = edgar.get_recent_8k_filings(lookback_days=2)
    if edgar_result.ok:
        filings = edgar_result.data or []
        log.info("edgar 8-K filings: %d", len(filings))
        return filings, diag

    diag.append(f"EDGAR 8-K failed: {edgar_result.error}")
    log.warning("EDGAR 8-K failed — no fallback available on free tier")
    diag.append("8-K section unavailable today: EDGAR unreachable")
    return [], diag


def extract_8k_tickers(filings: List[dict], edgar: EdgarClient) -> List[str]:
    if not edgar._ticker_cik_map:
        edgar.load_ticker_cik_map()

    cik_to_ticker = {str(v): k for k, v in edgar._ticker_cik_map.items()}
    tickers = []
    for filing in filings:
        accession = filing.get("accession_no", "")
        if accession:
            cik_raw = accession.replace("-", "")[:10]
            try:
                ticker = cik_to_ticker.get(str(int(cik_raw)))
                if ticker:
                    tickers.append(ticker)
            except ValueError:
                continue
    return list(set(tickers))
