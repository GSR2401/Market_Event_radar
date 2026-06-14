import json
import tempfile
from datetime import date
from pathlib import Path

from src.types import MarketEvent
from src.dedup_store import DedupStore


def _ev(ticker="AAPL"):
    return MarketEvent(
        ticker=ticker,
        company_name="Apple Inc",
        event_type="EARNINGS",
        event_date=date.today(),
    )


def test_first_time_not_reported():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = DedupStore(f.name)
    ev = _ev()
    store.tag_and_update([ev])
    assert not ev.previously_reported


def test_second_time_is_reported():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    store = DedupStore(path)
    ev = _ev()
    store.tag_and_update([ev])
    ev2 = _ev()
    store.tag_and_update([ev2])
    assert ev2.previously_reported


def test_different_tickers_not_deduped():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = DedupStore(f.name)
    ev_a = _ev("AAPL")
    ev_b = _ev("MSFT")
    store.tag_and_update([ev_a, ev_b])
    assert not ev_a.previously_reported
    assert not ev_b.previously_reported
