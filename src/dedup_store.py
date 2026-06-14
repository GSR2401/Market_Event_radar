import hashlib
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List

from src.types import MarketEvent

log = logging.getLogger(__name__)
_EXPIRY_DAYS = 14
_STORE_FILE = "seen_events.json"


def _make_hash(event: MarketEvent) -> str:
    key = f"{event.ticker}|{event.event_type}|{event.event_date.isoformat()}"
    return hashlib.md5(key.encode()).hexdigest()


class DedupStore:
    def __init__(self, store_path: str = _STORE_FILE):
        self.path = Path(store_path)
        self._store: dict = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _purge_expired(self) -> None:
        cutoff = (date.today() - timedelta(days=_EXPIRY_DAYS)).isoformat()
        self._store = {k: v for k, v in self._store.items() if v >= cutoff}

    def tag_and_update(self, events: List[MarketEvent]) -> List[MarketEvent]:
        self._purge_expired()
        today_str = date.today().isoformat()
        for event in events:
            h = _make_hash(event)
            event.event_hash = h
            if h in self._store:
                event.previously_reported = True
                log.debug("%s %s: previously reported", event.ticker, event.event_type)
            else:
                event.previously_reported = False
                self._store[h] = today_str
        self.save()
        return events

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self._store, indent=2))
        except Exception as exc:
            log.warning("dedup store save failed: %s", exc)
