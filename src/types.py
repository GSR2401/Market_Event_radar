from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Optional


@dataclass
class SourceResult:
    ok: bool
    data: Any
    error: Optional[str] = None
    source: str = ""


@dataclass
class MarketEvent:
    ticker: str
    company_name: str
    event_type: str        # EARNINGS | IPO | 8K | NEWS
    event_date: date
    sources: List[str] = field(default_factory=list)
    report_time: Optional[str] = None      # BMO | AMC | None
    confirmation: str = "ESTIMATED"        # CONFIRMED | ESTIMATED
    eps_estimate: Optional[float] = None
    revenue_estimate: Optional[float] = None
    summary: str = ""
    # enriched
    market_cap: Optional[float] = None
    cap_tier: Optional[str] = None         # LARGE | MID | SMALL
    sector: Optional[str] = None
    # options
    options_total_oi: Optional[int] = None
    options_avg_volume_20d: Optional[float] = None
    options_current_volume: Optional[int] = None
    put_call_ratio: Optional[float] = None
    activity_level: str = "NORMAL"         # NORMAL | MODERATE | STRONG
    stock_avg_volume_20d: Optional[float] = None
    # meta
    rank_score: float = 0.0
    previously_reported: bool = False
    data_available: bool = True
    event_hash: str = ""
    # 8-K specific
    item_codes: List[str] = field(default_factory=list)
    filing_url: Optional[str] = None
