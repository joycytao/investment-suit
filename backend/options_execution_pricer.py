from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


FORWARD_FILL_WINDOW = timedelta(minutes=2)


def _is_usable_quote(quote: pd.Series) -> bool:
    return pd.notna(quote.get("bid_price")) and pd.notna(quote.get("ask_price"))


def get_quote_with_fallback(quotes: pd.DataFrame, timestamp: datetime) -> pd.Series | None:
    if quotes.empty:
        return None

    if timestamp in quotes.index:
        exact = quotes.loc[timestamp]
        if isinstance(exact, pd.DataFrame):
            exact = exact.iloc[0]
        if _is_usable_quote(exact):
            return exact

    window_quotes = quotes[(quotes.index >= timestamp) & (quotes.index <= timestamp + FORWARD_FILL_WINDOW)]
    if window_quotes.empty:
        return None

    for _, quote in window_quotes.iterrows():
        if _is_usable_quote(quote):
            return quote

    return None


def get_entry_price(quote: pd.Series | dict) -> float | None:
    ask_price = quote.get("ask_price") if quote is not None else None
    return None if pd.isna(ask_price) else float(ask_price)


def get_exit_price(quote: pd.Series | dict) -> float | None:
    bid_price = quote.get("bid_price") if quote is not None else None
    return None if pd.isna(bid_price) else float(bid_price)