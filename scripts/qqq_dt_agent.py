import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from dotenv import load_dotenv


load_dotenv()

SYMBOL = "QQQ"
DEFAULT_ORDER_QTY = 100
POLL_INTERVAL_SECONDS = 60
LOOKBACK_MINUTES = 240
DEFAULT_EXECUTION_DURATION_MINUTES = 385
CENTRAL_TZ = ZoneInfo("America/Chicago")
BOLLINGER_MIDDLE_COLUMN = "BBM_20_2.0_2.0"
EXIT_REASON_TAKE_PROFIT = "take_profit"
EXIT_REASON_STOP_LOSS = "stop_loss"
EXIT_REASON_MAX_HOLD = "max_hold"
EXIT_REASON_MARKET_CLOSE = "market_close"

trading_client = None
data_client = None


@dataclass
class PositionState:
    entry_price: float
    qty: int
    entry_time: datetime


def get_alpaca_credentials():
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

    return api_key, secret_key


def build_data_client():
    api_key, secret_key = get_alpaca_credentials()
    return StockHistoricalDataClient(api_key, secret_key)


def build_trading_client():
    api_key, secret_key = get_alpaca_credentials()
    return TradingClient(api_key, secret_key, paper=True)


def bootstrap_runtime():
    global trading_client, data_client

    trading_client = build_trading_client()
    data_client = build_data_client()


def add_indicators(df):
    df = df.copy()
    df.ta.macd(append=True)
    df.ta.rsi(append=True)
    df.ta.bbands(length=20, std=2, append=True)
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
    df = pd.concat([df, stoch], axis=1)
    df["J"] = 3 * df["STOCHk_9_3_3"] - 2 * df["STOCHd_9_3_3"]
    return df


def build_buy_signal_series(df):
    cond_macd = (df["MACDh_12_26_9"] > df["MACDh_12_26_9"].shift(1)) & (df["MACDh_12_26_9"] < 0)
    cond_boll = df["close"] < df[BOLLINGER_MIDDLE_COLUMN]
    cond_kdj = (df["J"] > df["J"].shift(1)) & (df["J"].shift(1) < 25)
    cond_rsi = df["RSI_14"] < 45
    cond_volume = df["volume"] > df["volume"].shift(1)
    return cond_macd & cond_boll & cond_kdj & cond_rsi & cond_volume


def determine_exit_reason(entry_price, current_price, entry_time, current_time, market_close_time):
    profit_pct = (current_price - entry_price) / entry_price
    if profit_pct >= 0.20 and current_time - entry_time <= timedelta(minutes=60):
        return EXIT_REASON_TAKE_PROFIT
    if profit_pct <= -0.002:
        return EXIT_REASON_STOP_LOSS
    if current_time - entry_time >= timedelta(minutes=60):
        return EXIT_REASON_MAX_HOLD
    if current_time >= market_close_time - timedelta(minutes=5):
        return EXIT_REASON_MARKET_CLOSE
    return None


def get_current_central_time():
    return datetime.now(CENTRAL_TZ)


def get_execution_duration_minutes():
    raw_value = (os.getenv("EXECUTION_DURATION_MINUTES") or "").strip()
    if not raw_value:
        return DEFAULT_EXECUTION_DURATION_MINUTES

    try:
        duration_minutes = int(raw_value)
    except ValueError:
        print(
            f"⚠️ Invalid EXECUTION_DURATION_MINUTES={raw_value!r}. "
            f"Using default {DEFAULT_EXECUTION_DURATION_MINUTES} minutes."
        )
        return DEFAULT_EXECUTION_DURATION_MINUTES

    if duration_minutes <= 0:
        print(
            "⚠️ EXECUTION_DURATION_MINUTES must be greater than 0. "
            f"Using default {DEFAULT_EXECUTION_DURATION_MINUTES} minutes."
        )
        return DEFAULT_EXECUTION_DURATION_MINUTES

    return duration_minutes


def get_regular_market_close(reference_time=None):
    current_time = reference_time.astimezone(CENTRAL_TZ) if reference_time else get_current_central_time()
    return current_time.replace(hour=15, minute=0, second=0, microsecond=0)


def get_execution_window(reference_time=None):
    current_time = reference_time.astimezone(CENTRAL_TZ) if reference_time else get_current_central_time()
    market_open = current_time.replace(hour=8, minute=30, second=0, microsecond=0)
    market_close = market_open + timedelta(minutes=get_execution_duration_minutes())
    return market_open, market_close


def print_outside_execution_time(current_time, market_open, market_close):
    print(
        "⏰ Outside execution time. "
        f"Current time {current_time.strftime('%I:%M %p')} {current_time.tzinfo} "
        f"is outside the {market_open.strftime('%I:%M %p')}-{market_close.strftime('%I:%M %p')} {market_open.tzinfo} trading window."
    )


def normalize_bar_index(df):
    if df.index.tz is None:
        return df.tz_localize("UTC").tz_convert(CENTRAL_TZ)
    return df.tz_convert(CENTRAL_TZ)


def fetch_signal_frame(symbol=SYMBOL, reference_time=None):
    current_time = reference_time or get_current_central_time()
    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=current_time - timedelta(minutes=LOOKBACK_MINUTES),
    )
    bars = data_client.get_stock_bars(request_params).df
    if bars.empty:
        return None

    try:
        symbol_bars = bars.xs(symbol)
    except KeyError:
        return None

    symbol_bars = symbol_bars.copy()
    symbol_bars.index = normalize_bar_index(symbol_bars)
    frame = symbol_bars.resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()
    if len(frame) < 20:
        return None

    frame = add_indicators(frame)
    required_columns = {
        "MACDh_12_26_9",
        BOLLINGER_MIDDLE_COLUMN,
        "J",
        "RSI_14",
        "volume",
        "close",
    }
    if not required_columns.issubset(frame.columns):
        return None

    return frame


def submit_market_order(symbol, qty, side):
    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    trading_client.submit_order(order_data)


async def qqq_day_trade_agent(symbol=SYMBOL, qty=DEFAULT_ORDER_QTY):
    position = None
    print(f"📡 啟動 {symbol} 日內監控循環...")

    while True:
        current_time = get_current_central_time()
        market_open, market_close = get_execution_window(current_time)
        if current_time < market_open:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        if current_time > market_close:
            print_outside_execution_time(current_time, market_open, market_close)
            return

        frame = fetch_signal_frame(symbol=symbol, reference_time=current_time)
        if frame is None or len(frame) < 2:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        latest = frame.iloc[-1]
        latest_bar_time = frame.index[-1]
        current_price = float(latest["close"])

        if position is None:
            signal_series = build_buy_signal_series(frame)
            if bool(signal_series.iloc[-1]):
                print(f"🎯 {symbol} 買入信號觸發！價格: {current_price:.2f}")
                submit_market_order(symbol=symbol, qty=qty, side=OrderSide.BUY)
                position = PositionState(
                    entry_price=current_price,
                    qty=qty,
                    entry_time=latest_bar_time,
                )
        else:
            exit_reason = determine_exit_reason(
                entry_price=position.entry_price,
                current_price=current_price,
                entry_time=position.entry_time,
                current_time=latest_bar_time,
                market_close_time=get_regular_market_close(latest_bar_time),
            )
            if exit_reason:
                print(f"🚪 {symbol} 觸發離場條件: {exit_reason}，價格: {current_price:.2f}")
                submit_market_order(symbol=symbol, qty=position.qty, side=OrderSide.SELL)
                position = None

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main():
    bootstrap_runtime()
    current_time = get_current_central_time()
    market_open, market_close = get_execution_window(current_time)
    if current_time < market_open or current_time > market_close:
        print_outside_execution_time(current_time, market_open, market_close)
        return

    await qqq_day_trade_agent()


if __name__ == "__main__":
    asyncio.run(main())