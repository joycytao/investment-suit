import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import RISK_FREE_RATE
from backend.options_contract_selector import select_contract
from backend.options_execution_pricer import get_entry_price, get_exit_price
from backend.options_market_data import (
    derive_exit_bid_price,
    fetch_option_bars,
    fetch_option_chain_snapshot,
)
from backend.options_pricing import black_scholes_call, black_scholes_put


load_dotenv()


MARKET_TIMEZONE = "America/New_York"
DEFAULT_SYMBOL = "QQQ"
LOOKBACK_DAYS = 30
STARTING_CAPITAL = 100_000.0
MAX_POSITION_FRACTION = 0.20
IV_ENTRY_MAX_PERCENTILE = 0.40
IV_AVOID_PERCENTILE = 0.70
HARD_STOP_LOSS = -0.12
PARTIAL_PROFIT_TARGET = 0.30
FULL_PROFIT_TARGET = 0.50
FORCE_EXIT_TIME = "15:30"
NO_ENTRY_BEFORE = "09:50"
NO_ENTRY_AFTER = "14:00"
EXIT_REASON_HARD_STOP = "hard_stop"
EXIT_REASON_FULL_TARGET = "full_target"
EXIT_REASON_BOLLINGER_TARGET = "bollinger_target"
EXIT_REASON_FORCE_CLOSE = "force_close"
EXIT_REASON_TREND_BREAK = "trend_break"


def build_data_client():
    api_key = (os.getenv("ALPACA_API_KEY") or "").strip()
    secret_key = (os.getenv("ALPACA_SECRET_KEY") or "").strip()
    missing = [
        name
        for name, value in {
            "ALPACA_API_KEY": api_key,
            "ALPACA_SECRET_KEY": secret_key,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return StockHistoricalDataClient(api_key, secret_key)


def build_option_data_client():
    api_key = (os.getenv("ALPACA_API_KEY") or "").strip()
    secret_key = (os.getenv("ALPACA_SECRET_KEY") or "").strip()
    missing = [
        name
        for name, value in {
            "ALPACA_API_KEY": api_key,
            "ALPACA_SECRET_KEY": secret_key,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return OptionHistoricalDataClient(api_key, secret_key)


def normalize_intraday_frame(df):
    frame = df.copy()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index = frame.index.tz_convert(MARKET_TIMEZONE)
    frame = frame.between_time("09:30", "16:00").copy()
    frame["session_date"] = frame.index.date
    return frame


def rolling_percentile_rank(series, window):
    def percentile(values):
        ranked = pd.Series(values).rank(pct=True)
        return ranked.iloc[-1]

    return series.rolling(window, min_periods=max(20, window // 4)).apply(percentile, raw=False)


def build_support_resistance_levels(frame_1m):
    structure = pd.DataFrame(index=frame_1m.index)

    opening_range = frame_1m.between_time("09:30", "09:49")
    opening_high = opening_range.groupby(frame_1m.loc[opening_range.index, "session_date"])["high"].max()
    opening_low = opening_range.groupby(frame_1m.loc[opening_range.index, "session_date"])["low"].min()
    structure["opening_high"] = frame_1m["session_date"].map(opening_high)
    structure["opening_low"] = frame_1m["session_date"].map(opening_low)

    confirmed_swing_high = frame_1m["high"].shift(1).where(
        (frame_1m["high"].shift(1) > frame_1m["high"].shift(2))
        & (frame_1m["high"].shift(1) >= frame_1m["high"])
    )
    confirmed_swing_low = frame_1m["low"].shift(1).where(
        (frame_1m["low"].shift(1) < frame_1m["low"].shift(2))
        & (frame_1m["low"].shift(1) <= frame_1m["low"])
    )

    structure["swing_high_level"] = confirmed_swing_high.groupby(frame_1m["session_date"]).ffill()
    structure["swing_low_level"] = confirmed_swing_low.groupby(frame_1m["session_date"]).ffill()
    structure["breaks_opening_range_up"] = frame_1m["close"] > structure["opening_high"]
    structure["breaks_opening_range_down"] = frame_1m["close"] < structure["opening_low"]
    structure["breaks_swing_high_up"] = frame_1m["close"] > structure["swing_high_level"]
    structure["breaks_swing_low_down"] = frame_1m["close"] < structure["swing_low_level"]
    structure["breaks_resistance"] = (
        structure["breaks_opening_range_up"] & structure["breaks_swing_high_up"].fillna(False)
    )
    structure["breaks_support"] = (
        structure["breaks_opening_range_down"] & structure["breaks_swing_low_down"].fillna(False)
    )
    return structure


def build_multitimeframe_frame(one_minute):
    frame_1m = one_minute.copy()
    frame_1m["ma_20_1m"] = frame_1m["close"].rolling(20).mean()
    frame_1m["ema_20_1m"] = ta.ema(frame_1m["close"], length=20)
    frame_1m["rsi_1m"] = ta.rsi(frame_1m["close"], length=14)
    frame_1m["volume_sma_20"] = frame_1m["volume"].rolling(20).mean()
    frame_1m["dollar_volume_sma_20"] = (frame_1m["close"] * frame_1m["volume"]).rolling(20).mean()

    log_returns = pd.Series(
        [math.log(current / previous) if previous > 0 and current > 0 else 0.0 for previous, current in zip(frame_1m["close"].shift(1).fillna(frame_1m["close"]), frame_1m["close"])],
        index=frame_1m.index,
    )
    frame_1m["hv_proxy"] = log_returns.rolling(60).std() * math.sqrt(252 * 390)
    frame_1m["iv_proxy"] = frame_1m["hv_proxy"].ewm(span=120, min_periods=20).mean() * 0.9
    frame_1m["iv_percentile"] = rolling_percentile_rank(frame_1m["iv_proxy"].ffill(), 390)

    structure_levels = build_support_resistance_levels(frame_1m)

    frame_5m = frame_1m.resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "session_date": "last",
        }
    ).dropna()
    frame_5m["ema_5_5m"] = ta.ema(frame_5m["close"], length=5)
    frame_5m["ema_20_5m"] = ta.ema(frame_5m["close"], length=20)
    frame_5m["ma_20_5m"] = frame_5m["close"].rolling(20).mean()
    frame_5m.ta.macd(append=True)
    frame_5m.ta.rsi(append=True)
    frame_5m.ta.bbands(length=20, std=2, append=True)

    aligned_5m = frame_5m.reindex(frame_1m.index, method="ffill")

    signal_frame = frame_1m.copy()
    signal_frame["ema_5_5m"] = aligned_5m["ema_5_5m"]
    signal_frame["ema_20_5m"] = aligned_5m["ema_20_5m"]
    signal_frame["ma_20_5m"] = aligned_5m["ma_20_5m"]
    signal_frame["macd_hist_5m"] = aligned_5m["MACDh_12_26_9"]
    signal_frame["macd_line_5m"] = aligned_5m["MACD_12_26_9"]
    signal_frame["macd_signal_5m"] = aligned_5m["MACDs_12_26_9"]
    signal_frame["rsi_5m"] = aligned_5m["RSI_14"]
    signal_frame["bb_upper_5m"] = aligned_5m.get("BBU_20_2.0")
    signal_frame["bb_lower_5m"] = aligned_5m.get("BBL_20_2.0")

    signal_frame["entry_window_open"] = (
        (signal_frame.index.strftime("%H:%M") >= NO_ENTRY_BEFORE)
        & (signal_frame.index.strftime("%H:%M") <= NO_ENTRY_AFTER)
    )
    signal_frame["liquidity_ok"] = (
        (signal_frame["volume_sma_20"] >= 50_000)
        & (signal_frame["dollar_volume_sma_20"] >= 5_000_000)
    )
    signal_frame["opening_high"] = structure_levels["opening_high"]
    signal_frame["opening_low"] = structure_levels["opening_low"]
    signal_frame["swing_high_level"] = structure_levels["swing_high_level"]
    signal_frame["swing_low_level"] = structure_levels["swing_low_level"]
    signal_frame["breaks_opening_range_high"] = structure_levels["breaks_opening_range_up"]
    signal_frame["breaks_opening_range_low"] = structure_levels["breaks_opening_range_down"]
    signal_frame["breaks_swing_high"] = structure_levels["breaks_swing_high_up"]
    signal_frame["breaks_swing_low"] = structure_levels["breaks_swing_low_down"]
    signal_frame["breaks_resistance"] = structure_levels["breaks_resistance"]
    signal_frame["breaks_support"] = structure_levels["breaks_support"]
    signal_frame["volume_breakout_up"] = (
        (signal_frame["volume"] > signal_frame["volume_sma_20"] * 1.5)
        & (signal_frame["close"] > signal_frame["open"])
        & (signal_frame["close"] > signal_frame["close"].shift(1))
    )
    signal_frame["volume_breakout_down"] = (
        (signal_frame["volume"] > signal_frame["volume_sma_20"] * 1.5)
        & (signal_frame["close"] < signal_frame["open"])
        & (signal_frame["close"] < signal_frame["close"].shift(1))
    )
    signal_frame["breaks_resistance"] = signal_frame["close"] > signal_frame["resistance_level"]
    signal_frame["breaks_support"] = signal_frame["close"] < signal_frame["support_level"]
    signal_frame["ma_turn_bull"] = (
        (signal_frame["ma_20_1m"] > signal_frame["ma_20_1m"].shift(1))
        & (signal_frame["ma_20_1m"].shift(1) <= signal_frame["ma_20_1m"].shift(2))
    )
    signal_frame["ma_turn_bear"] = (
        (signal_frame["ma_20_1m"] < signal_frame["ma_20_1m"].shift(1))
        & (signal_frame["ma_20_1m"].shift(1) >= signal_frame["ma_20_1m"].shift(2))
    )
    signal_frame["ma_trend_bull"] = (
        (signal_frame["ma_20_1m"] > signal_frame["ma_20_1m"].shift(1))
        & (signal_frame["close"] > signal_frame["ma_20_1m"])
    )
    signal_frame["ma_trend_bear"] = (
        (signal_frame["ma_20_1m"] < signal_frame["ma_20_1m"].shift(1))
        & (signal_frame["close"] < signal_frame["ma_20_1m"])
    )
    signal_frame["macd_bull_confirm"] = (
        (signal_frame["macd_line_5m"] > signal_frame["macd_signal_5m"])
        & (signal_frame["macd_line_5m"].shift(1) <= signal_frame["macd_signal_5m"].shift(1))
    )
    signal_frame["macd_bear_confirm"] = (
        (signal_frame["macd_line_5m"] < signal_frame["macd_signal_5m"])
        & (signal_frame["macd_line_5m"].shift(1) >= signal_frame["macd_signal_5m"].shift(1))
    )
    signal_frame["macd_bull_bias"] = signal_frame["macd_line_5m"] > signal_frame["macd_signal_5m"]
    signal_frame["macd_bear_bias"] = signal_frame["macd_line_5m"] < signal_frame["macd_signal_5m"]
    signal_frame["rsi_bull_filter_ok"] = (
        signal_frame["rsi_1m"].between(45, 78, inclusive="both")
        & signal_frame["rsi_5m"].between(45, 75, inclusive="both")
    )
    signal_frame["rsi_bear_filter_ok"] = (
        signal_frame["rsi_1m"].between(22, 55, inclusive="both")
        & signal_frame["rsi_5m"].between(25, 55, inclusive="both")
    )

    signal_frame["signal"] = build_entry_signal_series(signal_frame)
    signal_frame["signal_side"] = signal_frame["signal"]
    return signal_frame


def build_entry_signal_series(df):
    ma_trend_bull = df.get("ma_trend_bull", df.get("ma_turn_bull"))
    ma_trend_bear = df.get("ma_trend_bear", df.get("ma_turn_bear"))
    macd_bull_bias = df.get("macd_bull_bias", df.get("macd_bull_confirm"))
    macd_bear_bias = df.get("macd_bear_bias", df.get("macd_bear_confirm"))
    breaks_resistance = df.get(
        "breaks_resistance",
        df.get("breaks_opening_range_high", False) & df.get("breaks_swing_high", False),
    )
    breaks_support = df.get(
        "breaks_support",
        df.get("breaks_opening_range_low", False) & df.get("breaks_swing_low", False),
    )
    rsi_bull_filter_ok = df.get("rsi_bull_filter_ok", df.get("rsi_long_filter_ok", df.get("rsi_bull_confirm")))
    rsi_bear_filter_ok = df.get("rsi_bear_filter_ok", df.get("rsi_short_filter_ok", df.get("rsi_bear_confirm")))

    long_signal = (
        df["entry_window_open"]
        & df["liquidity_ok"]
        & df["volume_breakout_up"]
        & breaks_resistance
        & ma_trend_bull
        & macd_bull_bias
        & rsi_bull_filter_ok
    )
    short_signal = (
        df["entry_window_open"]
        & df["liquidity_ok"]
        & df["volume_breakout_down"]
        & breaks_support
        & ma_trend_bear
        & macd_bear_bias
        & rsi_bear_filter_ok
    )

    signal = pd.Series(0, index=df.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def estimate_option_price(spot_price, sigma, option_side, current_time, strike=None):
    strike_price = strike or round(spot_price)
    minutes_left_today = max(1, ((16 - current_time.hour) * 60) + (0 - current_time.minute))
    total_minutes_to_expiry = minutes_left_today + 390
    time_to_expiry = total_minutes_to_expiry / (390 * 252)
    annual_vol = max(0.05, float(sigma) if pd.notna(sigma) else 0.20)

    if option_side == 1:
        return max(0.05, black_scholes_call(spot_price, strike_price, time_to_expiry, RISK_FREE_RATE, annual_vol))
    return max(0.05, black_scholes_put(spot_price, strike_price, time_to_expiry, RISK_FREE_RATE, annual_vol))


def resolve_entry_option_price(row, timestamp):
    if "entry_ask" in row or "ask_price" in row:
        quote_price = row.get("entry_ask")
        if pd.notna(quote_price):
            return float(quote_price)
        quote_price = get_entry_price(row)
        if quote_price is not None:
            return quote_price
        return None

    option_price = row.get("option_price")
    if option_price is not None:
        return float(option_price)

    return float(
        estimate_option_price(
            row["close"],
            row.get("iv_proxy"),
            int(row["signal_side"]),
            timestamp,
            round(row["close"]),
        )
    )


def resolve_exit_option_price(row, timestamp, position):
    option_bars = position.get("option_bars")
    if option_bars is not None and not option_bars.empty:
        option_close = option_bars["close"].asof(timestamp)
        if pd.notna(option_close):
            return derive_exit_bid_price(option_close, position["spread_pct"])

    if "exit_bid" in row or "bid_price" in row:
        quote_price = row.get("exit_bid")
        if pd.notna(quote_price):
            return float(quote_price)
        quote_price = get_exit_price(row)
        if quote_price is not None:
            return quote_price
        return None

    option_price = row.get("option_price")
    if option_price is not None:
        return float(option_price)

    return float(
        estimate_option_price(
            row["close"],
            row.get("iv_proxy"),
            position["side"],
            timestamp,
            position["strike"],
        )
    )


def simulate_option_trades(
    df,
    starting_capital=STARTING_CAPITAL,
    option_data_client=None,
    underlying_symbol=None,
):
    capital = starting_capital
    trades = []
    position = None

    for timestamp, row in df.iterrows():
        if position is None:
            if int(row.get("signal", 0)) == 0:
                continue

            position_contract_symbol = None
            position_option_bars = None
            position_spread_pct = None
            strike = round(float(row["close"]))

            if option_data_client is not None and underlying_symbol:
                chain = fetch_option_chain_snapshot(option_data_client, underlying_symbol, timestamp)
                contract = select_contract(
                    chain=chain,
                    signal_time=timestamp,
                    option_side=int(row["signal_side"]),
                )
                if contract is None:
                    continue

                option_price = get_entry_price(contract)
                if option_price is None:
                    continue

                session_end = timestamp.replace(hour=16, minute=0, second=0, microsecond=0)
                position_contract_symbol = str(contract["symbol"])
                position_spread_pct = float(contract["spread_pct"])
                position_option_bars = fetch_option_bars(
                    option_data_client,
                    position_contract_symbol,
                    start_time=timestamp,
                    end_time=session_end,
                )
                if position_option_bars.empty:
                    continue
            else:
                option_price = resolve_entry_option_price(row, timestamp)
                if option_price is None:
                    continue

            allocation = capital * MAX_POSITION_FRACTION
            contracts = max(1, int(allocation // (option_price * 100)))
            position = {
                "entry_time": timestamp,
                "entry_spot": float(row["close"]),
                "entry_option_price": option_price,
                "side": int(row["signal_side"]),
                "strike": strike,
                "contracts": contracts,
                "remaining_contracts": contracts,
                "partials_taken": 0,
                "realized_pnl": 0.0,
                "entry_cost": option_price * contracts * 100,
                "contract_symbol": position_contract_symbol,
                "spread_pct": position_spread_pct,
                "option_bars": position_option_bars,
            }
            continue

        option_price = resolve_exit_option_price(row, timestamp, position)
        if option_price is None:
            continue
        option_return = (option_price / position["entry_option_price"]) - 1
        trend_break = (position["side"] == 1 and row["close"] < row["ema_20_1m"]) or (
            position["side"] == -1 and row["close"] > row["ema_20_1m"]
        )
        upper_band = row.get("bb_upper_5m")
        lower_band = row.get("bb_lower_5m")
        bollinger_hit = (
            position["side"] == 1 and pd.notna(upper_band) and row["close"] >= upper_band
        ) or (
            position["side"] == -1 and pd.notna(lower_band) and row["close"] <= lower_band
        )
        force_close = timestamp.strftime("%H:%M") >= FORCE_EXIT_TIME

        if position["partials_taken"] == 0 and option_return >= PARTIAL_PROFIT_TARGET:
            partial_contracts = max(1, position["contracts"] // 2)
            target_price = position["entry_option_price"] * (1 + PARTIAL_PROFIT_TARGET)
            position["realized_pnl"] += (target_price - position["entry_option_price"]) * partial_contracts * 100
            position["remaining_contracts"] -= partial_contracts
            position["partials_taken"] = 1

        exit_reason = None
        if option_return <= HARD_STOP_LOSS:
            exit_reason = EXIT_REASON_HARD_STOP
        elif trend_break:
            exit_reason = EXIT_REASON_TREND_BREAK
        elif bollinger_hit:
            exit_reason = EXIT_REASON_BOLLINGER_TARGET
        elif option_return >= FULL_PROFIT_TARGET:
            exit_reason = EXIT_REASON_FULL_TARGET
        elif force_close:
            exit_reason = EXIT_REASON_FORCE_CLOSE

        if exit_reason is None:
            continue

        position["realized_pnl"] += (option_price - position["entry_option_price"]) * position["remaining_contracts"] * 100
        realized_return = position["realized_pnl"] / position["entry_cost"]
        capital_return = position["realized_pnl"] / capital
        capital += position["realized_pnl"]
        trades.append(
            {
                "entry_time": position["entry_time"],
                "exit_time": timestamp,
                "side": position["side"],
                "contract_symbol": position.get("contract_symbol"),
                "entry_spot": position["entry_spot"],
                "exit_spot": float(row["close"]),
                "entry_option_price": position["entry_option_price"],
                "exit_option_price": option_price,
                "partials_taken": position["partials_taken"],
                "realized_pnl": position["realized_pnl"],
                "realized_return": realized_return,
                "capital_return": capital_return,
                "exit_reason": exit_reason,
            }
        )
        position = None

    return pd.DataFrame(trades)


def calculate_performance_metrics(trades):
    if trades.empty:
        return None

    returns = trades["capital_return"].astype(float)
    equity_curve = (1 + returns).cumprod()
    drawdown = equity_curve / equity_curve.cummax() - 1
    std = returns.std(ddof=1)
    sharpe = 0.0 if pd.isna(std) or std == 0 else (returns.mean() / std) * math.sqrt(len(returns))

    return {
        "total_return": equity_curve.iloc[-1] - 1,
        "sharpe_ratio": sharpe,
        "max_drawdown": drawdown.min(),
        "win_rate": (trades["realized_pnl"] > 0).mean(),
        "total_trades": int(len(trades)),
    }


def run_intraday_options_backtest(symbol=DEFAULT_SYMBOL):
    client = build_data_client()
    option_client = build_option_data_client()
    print(f"正在獲取 {symbol} 歷史數據...")

    start_time = datetime.now() - timedelta(days=LOOKBACK_DAYS)
    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_time,
    )

    bars = client.get_stock_bars(request_params).df.xs(symbol)
    normalized = normalize_intraday_frame(bars)
    signal_frame = build_multitimeframe_frame(normalized)
    trades = simulate_option_trades(
        signal_frame,
        option_data_client=option_client,
        underlying_symbol=symbol,
    )

    if trades.empty:
        print("未發現符合條件的期權交易信號，請嘗試放寬條件。")
        return

    metrics = calculate_performance_metrics(trades)
    print("-" * 30)
    print(f"回測結果報告 ({symbol}) - Intraday Options Strategy")
    print(f"總 K 線數: {len(signal_frame)}")
    print(f"觸發交易次數: {metrics['total_trades']}")
    print(f"勝率: {metrics['win_rate']:.2%}")
    print(f"總報酬: {metrics['total_return']:.2%}")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"最大回撤: {metrics['max_drawdown']:.2%}")
    print(f"最近三筆交易:\n{trades.tail(3).to_string(index=False)}")
    print("-" * 30)


if __name__ == "__main__":
    run_intraday_options_backtest(symbol=(os.getenv("SYMBOL") or DEFAULT_SYMBOL).strip().upper())