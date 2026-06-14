import tempfile
from pathlib import Path
from src.universe import build_universe


def test_watchlist_always_included():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("AAPL\nMSFT\n")
        wl_path = f.name

    result = build_universe(
        watchlist_path=wl_path,
        finnhub_earnings=[{"symbol": "NVDA"}],
        yf_earnings=[],
        edgar_8k_tickers=[],
        top_n=5,
    )
    assert "AAPL" in result
    assert "MSFT" in result


def test_invalid_tickers_excluded():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("AAPL\nBRK.B\n")  # BRK.B has a dot — should be filtered
        wl_path = f.name

    result = build_universe(wl_path, [], [], [], top_n=25)
    assert "AAPL" in result
    assert "BRK.B" not in result


def test_dedup_in_universe():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("AAPL\n")
        wl_path = f.name

    result = build_universe(
        wl_path,
        finnhub_earnings=[{"symbol": "AAPL"}],  # duplicate
        yf_earnings=[],
        edgar_8k_tickers=["AAPL"],  # duplicate again
        top_n=25,
    )
    assert result.count("AAPL") == 1
