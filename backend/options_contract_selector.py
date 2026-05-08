from __future__ import annotations

from datetime import datetime

import pandas as pd


MIN_DTE = 0
MAX_DTE = 5
MIN_DELTA = 0.40
MAX_DELTA = 0.60
MIN_VOLUME = 100
MIN_OPEN_INTEREST = 500
MAX_SPREAD_PCT = 0.08
TARGET_DELTA = 0.50


def _normalize_chain_frame(chain: pd.DataFrame) -> pd.DataFrame:
    frame = chain.copy()
    frame["expiration_date"] = pd.to_datetime(frame["expiration_date"]).dt.date
    frame["dte"] = (
        pd.to_datetime(frame["expiration_date"]) - pd.to_datetime(frame["snapshot_date"])
    ).dt.days
    frame["delta_abs_distance"] = (frame["delta"].abs() - TARGET_DELTA).abs()
    frame["spread_pct"] = (frame["ask_price"] - frame["bid_price"]) / frame["ask_price"]
    return frame


def select_contract(
    chain: pd.DataFrame,
    signal_time: datetime,
    option_side: int,
) -> pd.Series | None:
    if chain.empty:
        return None

    frame = chain.copy()
    frame["snapshot_date"] = signal_time.date()
    frame = _normalize_chain_frame(frame)

    filtered = frame[
        (frame["dte"] >= MIN_DTE)
        & (frame["dte"] <= MAX_DTE)
        & (frame["delta"].abs() >= MIN_DELTA)
        & (frame["delta"].abs() <= MAX_DELTA)
        & (frame["volume"] >= MIN_VOLUME)
        & (frame["spread_pct"] <= MAX_SPREAD_PCT)
    ].copy()

    liquid_with_open_interest = filtered[filtered["open_interest"] >= MIN_OPEN_INTEREST].copy()
    if not liquid_with_open_interest.empty:
        filtered = liquid_with_open_interest

    if filtered.empty:
        return None

    # Keep directional consistency when delta sign is available.
    if option_side == 1:
        signed = filtered[filtered["delta"] > 0]
    else:
        signed = filtered[filtered["delta"] < 0]
    if not signed.empty:
        filtered = signed

    ranked = filtered.sort_values(
        by=["delta_abs_distance", "spread_pct", "volume"],
        ascending=[True, True, False],
    )
    return ranked.iloc[0]