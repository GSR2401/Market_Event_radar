from datetime import date
from typing import List

from src.types import MarketEvent

_EVENT_WEIGHTS = {
    "EARNINGS": 5,
    "IPO": 4,
    "8K": 3,
    "NEWS": 2,
}
_ACTIVITY_MULT = {"STRONG": 2.0, "MODERATE": 1.5, "NORMAL": 1.0}
_CAP_WEIGHTS = {"LARGE": 3, "MID": 2, "SMALL": 1}


def score(event: MarketEvent) -> float:
    today = date.today()
    days_away = max(0, min(9, (event.event_date - today).days))
    event_w = _EVENT_WEIGHTS.get(event.event_type, 1)
    activity_m = _ACTIVITY_MULT.get(event.activity_level, 1.0)
    cap_w = _CAP_WEIGHTS.get(event.cap_tier or "", 1)
    return (event_w * 10) + (activity_m * 5) + (10 - days_away) + (cap_w * 2)


def rank(events: List[MarketEvent]) -> List[MarketEvent]:
    for ev in events:
        ev.rank_score = score(ev)
    return sorted(events, key=lambda e: e.rank_score, reverse=True)
