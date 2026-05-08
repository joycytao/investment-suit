from __future__ import annotations

from datetime import datetime

import pandas as pd
from alpaca.data.requests import OptionBarsRequest, OptionChainRequest
from alpaca.data.timeframe import TimeFrame


def _extract_attr(obj, attr, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _parse_occ_expiration(symbol: str):
    if len(symbol) < 9:
        return None
    date_part = symbol[-15:-9]
    try:
        return datetime.strptime(date_part, "%y%m%d").date()
    except ValueError:
        return None


def normalize_option_chain_snapshot(snapshots: dict, signal_time: datetime) -> pd.DataFrame:
    rows = []
    for symbol, snapshot in snapshots.items():
        greeks = _extract_attr(snapshot, "greeks")
        latest_quote = _extract_attr(snapshot, "latest_quote")
        latest_trade = _extract_attr(snapshot, "latest_trade")
        rows.append(
            {
                "symbol": symbol,
                "expiration_date": _parse_occ_expiration(symbol),
                "delta": _extract_attr(greeks, "delta"),
                "bid_price": _extract_attr(latest_quote, "bid_price"),
                "ask_price": _extract_attr(latest_quote, "ask_price"),
                "volume": _extract_attr(latest_trade, "size", 0),
                "open_interest": _extract_attr(snapshot, "open_interest", 0),
                "implied_volatility": _extract_attr(snapshot, "implied_volatility"),
                "snapshot_time": signal_time,
            }
        )

    return pd.DataFrame(rows)


def derive_exit_bid_price(option_close: float, spread_pct: float) -> float:
    return float(option_close) * (1 - (float(spread_pct) / 2))


def fetch_option_chain_snapshot(client, underlying_symbol: str, signal_time: datetime) -> pd.DataFrame:
    request = OptionChainRequest(
        underlying_symbol=underlying_symbol,
        expiration_date_gte=signal_time.date(),
    )
    snapshots = client.get_option_chain(request)
    return normalize_option_chain_snapshot(snapshots, signal_time)


def fetch_option_bars(
    client,
    contract_symbol: str,
    start_time: datetime,
    end_time: datetime,
) -> pd.DataFrame:
    request = OptionBarsRequest(
        symbol_or_symbols=[contract_symbol],
        timeframe=TimeFrame.Minute,
        start=start_time,
        end=end_time,
    )
    bars = client.get_option_bars(request)
    frame = getattr(bars, "df", pd.DataFrame())
    if frame.empty:
        return frame

    if isinstance(frame.index, pd.MultiIndex):
        try:
            frame = frame.xs(contract_symbol)
        except KeyError:
            frame = frame.droplevel(0)

    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index = frame.index.tz_convert("America/New_York")
    return frame.sort_index()