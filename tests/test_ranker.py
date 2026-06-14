from datetime import date, timedelta
from src.types import MarketEvent
from src.ranker import score, rank


def _ev(event_type="EARNINGS", days_away=2, activity="NORMAL", cap="LARGE"):
    return MarketEvent(
        ticker="TEST",
        company_name="Test Corp",
        event_type=event_type,
        event_date=date.today() + timedelta(days=days_away),
        activity_level=activity,
        cap_tier=cap,
    )


def test_earnings_scores_higher_than_news():
    assert score(_ev("EARNINGS")) > score(_ev("NEWS"))


def test_closer_event_scores_higher():
    assert score(_ev(days_away=1)) > score(_ev(days_away=5))


def test_strong_activity_boosts_score():
    assert score(_ev(activity="STRONG")) > score(_ev(activity="NORMAL"))


def test_rank_returns_sorted_descending():
    events = [_ev("NEWS", days_away=1), _ev("EARNINGS", days_away=3)]
    ranked = rank(events)
    assert ranked[0].rank_score >= ranked[1].rank_score


def test_large_cap_scores_higher_than_small():
    assert score(_ev(cap="LARGE")) > score(_ev(cap="SMALL"))
