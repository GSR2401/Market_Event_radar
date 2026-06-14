import logging
from datetime import date, timedelta
from typing import List, Optional

from src.types import MarketEvent

log = logging.getLogger(__name__)

_DATE_WINDOW_DAYS = 2


def _parse_date(s) -> Optional[date]:
    if not s:
        return None
    try:
        if isinstance(s, date):
            return s
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def build_earnings_events(
    merged_entries: List[dict],
    yf_dates: dict,          # ticker → list of date objects from yfinance
    event_window_end: date,
) -> List[MarketEvent]:
    """
    Convert the merged Nasdaq+Finnhub entry list into MarketEvent objects,
    then cross-check against yfinance per-ticker dates to upgrade
    ESTIMATED → CONFIRMED and fill gaps.
    """
    today = date.today()
    events: List[MarketEvent] = []
    seen: dict[str, MarketEvent] = {}   # ticker → event (one per ticker for now)

    # ── Pass 1: entries from Nasdaq/Finnhub merge ─────────────────────
    for entry in merged_entries:
        ticker = entry.get("symbol", "").upper()
        d = _parse_date(entry.get("date"))
        if not ticker or not d:
            continue
        if not (today <= d <= event_window_end):
            continue

        sources = entry.get("sources", [entry.get("source", "unknown")])
        confirmed = "nasdaq" in sources   # Nasdaq data is confirmed-date quality

        ev = MarketEvent(
            ticker=ticker,
            company_name=entry.get("name") or ticker,
            event_type="EARNINGS",
            event_date=d,
            sources=sources[:],
            report_time=entry.get("report_time"),
            confirmation="CONFIRMED" if confirmed else "ESTIMATED",
            eps_estimate=entry.get("eps_estimate"),
        )
        seen[ticker] = ev
        events.append(ev)

    # ── Pass 2: yfinance cross-check ──────────────────────────────────
    for ticker, yf_date_list in yf_dates.items():
        for d_raw in yf_date_list:
            d = _parse_date(d_raw)
            if not d or not (today <= d <= event_window_end):
                continue

            if ticker in seen:
                existing = seen[ticker]
                # upgrade confidence if dates agree within window
                if abs((existing.event_date - d).days) <= _DATE_WINDOW_DAYS:
                    if "yfinance" not in existing.sources:
                        existing.sources.append("yfinance")
                    existing.confirmation = "CONFIRMED"
                else:
                    # dates disagree by >2 days: use earliest, flag ESTIMATED
                    if d < existing.event_date:
                        existing.event_date = d
                    existing.confirmation = "ESTIMATED"
                    if "yfinance" not in existing.sources:
                        existing.sources.append("yfinance")
            else:
                # yfinance found a ticker not in Nasdaq/Finnhub — add it
                ev = MarketEvent(
                    ticker=ticker,
                    company_name=ticker,
                    event_type="EARNINGS",
                    event_date=d,
                    sources=["yfinance"],
                    confirmation="CONFIRMED",
                )
                seen[ticker] = ev
                events.append(ev)

    log.info("earnings events built: %d", len(events))
    return events


def build_8k_events(filings: List[dict], cik_ticker_map: dict) -> List[MarketEvent]:
    cik_to_ticker = {str(v): k for k, v in cik_ticker_map.items()}
    events = []

    for filing in filings:
        accession = filing.get("accession_no", "")
        entity = filing.get("entity_name", "Unknown")
        file_date = _parse_date(filing.get("file_date"))
        if not file_date:
            continue

        ticker = "UNKNOWN"
        if accession:
            try:
                cik_raw = accession.replace("-", "")[:10]
                ticker = cik_to_ticker.get(str(int(cik_raw)), "UNKNOWN")
            except ValueError:
                pass

        events.append(MarketEvent(
            ticker=ticker,
            company_name=entity,
            event_type="8K",
            event_date=file_date,
            sources=["edgar"],
            confirmation="CONFIRMED",
            summary=f"SEC 8-K filing by {entity}",
            filing_url=(
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&company={entity.replace(' ', '+')}&type=8-K&dateb=&owner=include&count=10"
            ),
        ))

    return events
