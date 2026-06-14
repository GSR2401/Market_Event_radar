import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader

from src.types import MarketEvent

log = logging.getLogger(__name__)


class DigestWriter:
    def __init__(self, template_dir: str = "templates", output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )
        self.env.filters["fmt_num"] = _fmt_num
        self.env.filters["fmt_cap"] = _fmt_cap

    def write(
        self,
        events: List[MarketEvent],
        unavailable_tickers: List[str],
        section_errors: dict,
        run_date: Optional[date] = None,
    ) -> Path:
        run_date = run_date or date.today()

        earnings = _sorted_by_date([e for e in events if e.event_type == "EARNINGS"])
        ipos = _sorted_by_date([e for e in events if e.event_type == "IPO"])
        eightk = _sorted_by_score([e for e in events if e.event_type == "8K"])
        news = _sorted_by_score([e for e in events if e.event_type == "NEWS"])

        source_health = _source_health(events)

        tmpl = self.env.get_template("digest.html")
        html = tmpl.render(
            run_date=run_date,
            earnings=earnings,
            ipos=ipos,
            eightk=eightk,
            news=news,
            unavailable_tickers=unavailable_tickers,
            section_errors=section_errors,
            source_health=source_health,
            total_events=len(events),
        )

        out_path = self.output_dir / f"market_radar_{run_date.isoformat()}.html"
        out_path.write_text(html, encoding="utf-8")

        index_path = self.output_dir / "index.html"
        index_path.write_text(html, encoding="utf-8")

        self._write_archive(run_date)

        log.info("digest written: %s", out_path)
        return out_path

    def _write_archive(self, run_date: date) -> None:
        dated_files = sorted(self.output_dir.glob("market_radar_*.html"), reverse=True)
        items = []
        for f in dated_files:
            stem = f.stem.replace("market_radar_", "")
            items.append({"date": stem, "filename": f.name})

        archive_html = _ARCHIVE_TEMPLATE.format(
            run_date=run_date.isoformat(),
            rows="\n".join(
                f'<li><a href="{i["filename"]}">{i["date"]}</a></li>' for i in items
            ),
        )
        (self.output_dir / "archive.html").write_text(archive_html, encoding="utf-8")


def _sorted_by_date(events: List[MarketEvent]) -> List[MarketEvent]:
    return sorted(events, key=lambda e: (e.event_date, -e.rank_score))


def _sorted_by_score(events: List[MarketEvent]) -> List[MarketEvent]:
    return sorted(events, key=lambda e: -e.rank_score)


def _fmt_num(value, suffix="") -> str:
    if value is None:
        return "—"
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.1f}B{suffix}"
    if value >= 1_000_000:
        return f"${value/1_000_000:.0f}M{suffix}"
    if value >= 1_000:
        return f"{value/1_000:.1f}K{suffix}"
    return f"{value:,.0f}{suffix}"


def _fmt_cap(value) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value/1_000_000:.0f}M"
    return f"${value:,.0f}"


def _source_health(events: List[MarketEvent]) -> dict:
    sources = {}
    for e in events:
        for s in e.sources:
            sources[s] = sources.get(s, 0) + 1
    return sources


_ARCHIVE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Market Event Radar — Archive</title>
<style>body{{font-family:system-ui,sans-serif;max-width:600px;margin:40px auto;padding:0 20px;}}
a{{color:#1f3864;}} ul{{line-height:2;}}</style></head>
<body>
<h1>Market Event Radar</h1>
<p>Past digests — generated {run_date}</p>
<ul>{rows}</ul>
<p><a href="index.html">← Today's Digest</a></p>
</body></html>"""
