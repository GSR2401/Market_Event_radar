#!/usr/bin/env python3
"""Market Event Radar — daily orchestrator."""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from src.cache import Cache
from src.dedup_store import DedupStore
from src.digest_writer import DigestWriter
from src.enricher import Enricher
from src.event_fetcher import fetch_8k_filings, fetch_earnings, extract_8k_tickers
from src.options_filter import OptionsFilter
from src.ranker import rank
from src.source_merger import merge_earnings, build_8k_events
from src.sources.alphavantage_client import AlphaVantageClient
from src.sources.edgar_client import EdgarClient
from src.sources.finnhub_client import FinnhubClient
from src.sources.newsdata_client import NewsdataClient
from src.sources.polygon_client import PolygonClient
from src.sources.yfinance_client import YFinanceClient
from src.types import MarketEvent
from src.universe import build_universe

# ── Logging ──────────────────────────────────────────────────────────────────
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)
run_date_str = date.today().isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(output_dir / f"run_{run_date_str}.log"),
    ],
)
log = logging.getLogger("run_daily")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> int:
    log.info("=== Market Event Radar starting — %s ===", run_date_str)
    cfg = load_config()

    today = date.today()
    window_end = today + timedelta(days=cfg["settings"]["event_window_days"])
    top_n = cfg["settings"]["top_n"]
    edgar_ua = cfg["edgar"]["user_agent"]

    cache = Cache(cfg["cache_dir"])
    dedup = DedupStore()
    section_errors: dict = {}
    unavailable_tickers: list = []
    all_events: list[MarketEvent] = []

    # ── Initialise clients ───────────────────────────────────────────────────
    finnhub = FinnhubClient()
    yf = YFinanceClient()
    edgar = EdgarClient(user_agent=edgar_ua)
    polygon = PolygonClient()
    alphavantage = AlphaVantageClient()
    newsdata = NewsdataClient()
    enricher = Enricher(yf=yf, finnhub=finnhub, newsdata=newsdata, cache=cache)
    options_filter = OptionsFilter(
        yf=yf, polygon=polygon, cache=cache,
        min_oi=cfg["options_filter"]["min_open_interest"],
        min_avg_options_vol=cfg["options_filter"]["min_avg_daily_options_volume"],
        min_avg_stock_vol=cfg["options_filter"]["min_avg_daily_stock_volume"],
    )

    # ── Step 1: Fetch raw events ─────────────────────────────────────────────
    log.info("Step 1: fetching raw events")
    fh_earnings, _, earn_diag = fetch_earnings(finnhub, yf, today, window_end)
    if earn_diag:
        section_errors["earnings"] = "; ".join(earn_diag)

    filings_8k, filings_diag = fetch_8k_filings(edgar, finnhub)
    if filings_diag:
        section_errors["8k"] = "; ".join(filings_diag)

    edgar_tickers = extract_8k_tickers(filings_8k, edgar)

    # ── Step 2: Build ticker universe ────────────────────────────────────────
    log.info("Step 2: building universe")
    universe = build_universe(
        watchlist_path=cfg["watchlist_path"],
        finnhub_earnings=fh_earnings,
        yf_earnings=[],
        edgar_8k_tickers=edgar_tickers,
        top_n=top_n,
    )
    log.info("Universe: %d tickers", len(universe))

    # ── Step 3: Per-ticker: earnings merge ───────────────────────────────────
    log.info("Step 3: merging earnings per ticker")
    for ticker in universe:
        yf_cal = yf.get_earnings_dates(ticker)
        yf_entry = yf_cal.data if yf_cal.ok else None

        events = merge_earnings(
            finnhub_entries=fh_earnings,
            yf_entry=yf_entry,
            ticker=ticker,
            event_window_end=window_end,
        )
        all_events.extend(events)

    log.info("Earnings events after merge: %d", len(all_events))

    # ── Step 4: 8-K events ───────────────────────────────────────────────────
    log.info("Step 4: building 8-K events")
    eightk_events = build_8k_events(filings_8k, edgar._ticker_cik_map)
    all_events.extend(eightk_events)

    # ── Step 5: Options filter ───────────────────────────────────────────────
    log.info("Step 5: options filter (%d candidates)", len(all_events))
    passed: list[MarketEvent] = []
    for ev in all_events:
        if options_filter.evaluate(ev):
            passed.append(ev)
        elif not ev.data_available:
            unavailable_tickers.append(ev.ticker)

    log.info("Passed options gate: %d events", len(passed))

    if not passed and all_events:
        section_errors.setdefault(
            "options",
            "All tickers failed the options gate — thresholds may be too high for today's universe."
        )
        passed = all_events  # graceful: show everything with a warning

    # ── Step 6: Enrich ───────────────────────────────────────────────────────
    log.info("Step 6: enriching %d events", len(passed))
    try:
        enricher.enrich_all(passed)
    except Exception as exc:
        log.error("enrichment error: %s", exc)
        section_errors["enrichment"] = str(exc)

    # ── Step 7: Dedup ────────────────────────────────────────────────────────
    log.info("Step 7: dedup")
    passed = dedup.tag_and_update(passed)
    dedup_mode = cfg["settings"]["dedup_mode"]
    if dedup_mode == "suppress":
        passed = [e for e in passed if not e.previously_reported]

    # ── Step 8: Rank ─────────────────────────────────────────────────────────
    log.info("Step 8: ranking")
    ranked = rank(passed)

    # ── Step 9: Write digest ─────────────────────────────────────────────────
    log.info("Step 9: writing digest")
    writer = DigestWriter(template_dir="templates", output_dir=cfg["output_dir"])
    out_path = writer.write(
        events=ranked,
        unavailable_tickers=list(set(unavailable_tickers)),
        section_errors=section_errors,
        run_date=today,
    )
    log.info("=== Done: %s ===", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
