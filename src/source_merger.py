import logging
from datetime import date, timedelta
from typing import List, Optional

from src.types import MarketEvent

log = logging.getLogger(__name__)

_DATE_WINDOW_DAYS = 2  # dates within 2 days are considered the same event


def _parse_date(s) -> Optional[date]:
    if not s:
        return None
    try:
        if isinstance(s, date):
            return s
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def merge_earnings(
    finnhub_entries: List[dict],
    yf_entry: Optional[dict],
    ticker: str,
    event_window_end: date,
) -> List[MarketEvent]:
    """
    Merge earnings data from Finnhub and yfinance for a single ticker.
    Returns a deduplicated list of MarketEvent objects for earnings in the window.
    """
    today = date.today()
    events: List[MarketEvent] = []
    seen_dates: List[date] = []

    def _add(event_date: date, sources: List[str], report_time: str,
             eps_est: Optional[float], rev_est: Optional[float],
             company_name: str, confirmed: bool) -> None:
        # dedup: if a date within ±2 days is already seen, merge sources
        for ev in events:
            if abs((ev.event_date - event_date).days) <= _DATE_WINDOW_DAYS:
                for s in sources:
                    if s not in ev.sources:
                        ev.sources.append(s)
                # keep earliest date
                if event_date < ev.event_date:
                    ev.event_date = event_date
                # if either source says CONFIRMED, mark confirmed
                if confirmed:
                    ev.confirmation = "CONFIRMED"
                return
        events.append(MarketEvent(
            ticker=ticker,
            company_name=company_name or ticker,
            event_type="EARNINGS",
            event_date=event_date,
            sources=sources[:],
            report_time=report_time,
            confirmation="CONFIRMED" if confirmed else "ESTIMATED",
            eps_estimate=eps_est,
            revenue_estimate=rev_est,
        ))

    # Finnhub entries
    for entry in finnhub_entries:
        if entry.get("symbol", "").upper() != ticker.upper():
            continue
        d = _parse_date(entry.get("date"))
        if not d or not (today <= d <= event_window_end):
            continue
        _add(
            event_date=d,
            sources=["finnhub"],
            report_time=_map_report_time(entry.get("hour", "")),
            eps_est=entry.get("epsEstimate"),
            rev_est=entry.get("revenueEstimate"),
            company_name=entry.get("symbol", ticker),
            confirmed=False,  # Finnhub free tier doesn't distinguish confirmed/estimated
        )

    # yfinance entry
    if yf_entry:
        for d_raw in yf_entry.get("dates", []):
            d = _parse_date(d_raw)
            if not d or not (today <= d <= event_window_end):
                continue
            _add(
                event_date=d,
                sources=["yfinance"],
                report_time=None,
                eps_est=None,
                rev_est=None,
                company_name=ticker,
                confirmed=True,  # yfinance usually reflects confirmed dates
            )

    return events


def _map_report_time(hour: str) -> Optional[str]:
    h = (hour or "").lower()
    if h in ("bmo", "before market open", "pre-market"):
        return "BMO"
    if h in ("amc", "after market close", "after-hours"):
        return "AMC"
    return None


def build_8k_events(filings: List[dict], cik_ticker_map: dict) -> List[MarketEvent]:
    events = []
    cik_to_ticker = {str(v): k for k, v in cik_ticker_map.items()}

    for filing in filings:
        accession = filing.get("accession_no", "")
        entity = filing.get("entity_name", "Unknown")
        file_date = _parse_date(filing.get("file_date"))
        if not file_date:
            continue

        # Try to resolve ticker
        parts = accession.replace("-", "").split()
        ticker = "UNKNOWN"
        if accession:
            cik_raw = accession.replace("-", "")[:10]
            ticker = cik_to_ticker.get(str(int(cik_raw or "0")), "UNKNOWN")

        events.append(MarketEvent(
            ticker=ticker,
            company_name=entity,
            event_type="8K",
            event_date=file_date,
            sources=["edgar"],
            confirmation="CONFIRMED",
            summary=f"SEC 8-K filing by {entity}",
            filing_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=&type=8-K&dateb=&owner=include&count=10&search_text=",
        ))

    return events
