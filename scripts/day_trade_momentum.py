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


DEFAULT_SYMBOL = "QQQ"
DEFAULT_ORDER_QTY = 100
POLL_INTERVAL_SECONDS = 60
LOOKBACK_MINUTES = 240
DEFAULT_EXECUTION_DURATION_MINUTES = 385
CENTRAL_TZ = ZoneInfo("America/Chicago")
ENTRY_CUTOFF_TIME = "09:00"
VWAP_CHASE_THRESHOLD = 1.01
ATR_STOP_MULTIPLIER = 1.5
ADX_THRESHOLD = 20
EXIT_REASON_ATR_STOP = "atr_stop"
EXIT_REASON_EMA_DEAD_CROSS = "ema_dead_cross"
EXIT_REASON_MARKET_CLOSE = "market_close"

trading_client = None
data_client = None


@dataclass
class PositionState:
    entry_price: float
    qty: int
    entry_time: datetime
    stop_loss_price: float


def get_runtime_symbol():
    return (os.getenv("SYMBOL") or DEFAULT_SYMBOL).strip().upper()


def get_order_quantity():
    raw_value = (os.getenv("ORDER_QTY") or "").strip()
    if not raw_value:
        return DEFAULT_ORDER_QTY

    try:
        quantity = int(raw_value)
    except ValueError:
        print(f"⚠️ Invalid ORDER_QTY={raw_value!r}. Using default {DEFAULT_ORDER_QTY}.")
        return DEFAULT_ORDER_QTY

    if quantity <= 0:
        print(f"⚠️ ORDER_QTY must be greater than 0. Using default {DEFAULT_ORDER_QTY}.")
        return DEFAULT_ORDER_QTY

    return quantity


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
    market_open = current_time.replace(hour=8, minute=15, second=0, microsecond=0)
    market_close = market_open + timedelta(minutes=get_execution_duration_minutes())
    return market_open, market_close


def print_outside_execution_time(current_time, market_open, market_close):
    print(
        "⏰ Outside execution time. "
        f"Current time {current_time.strftime('%I:%M %p')} {current_time.tzinfo} "
        f"is outside the {market_open.strftime('%I:%M %p')}-{market_close.strftime('%I:%M %p')} {market_open.tzinfo} trading window."
    )


def normalize_bar_index(index):
    if isinstance(index, pd.MultiIndex):
        index = index.get_level_values(-1)
    if index.tz is None:
        return index.tz_localize("UTC").tz_convert(CENTRAL_TZ)
    return index.tz_convert(CENTRAL_TZ)


def add_momentum_indicators(df):
    frame = df.copy()
    frame["session_date"] = frame.index.date
    frame["ema_9"] = ta.ema(frame["close"], length=9)
    frame["ema_21"] = ta.ema(frame["close"], length=21)
    frame["atr_14"] = ta.atr(frame["high"], frame["low"], frame["close"], length=14)

    typical_price = (frame["high"] + frame["low"] + frame["close"]) / 3
    weighted_price = typical_price * frame["volume"]
    frame["vwap"] = (
        weighted_price.groupby(frame["session_date"]).cumsum()
        / frame["volume"].groupby(frame["session_date"]).cumsum()
    )

    opening_range_high = (
        frame.between_time("08:30", "08:55")
        .groupby("session_date")["high"]
        .max()
    )
    frame["orb_high"] = frame["session_date"].map(opening_range_high)
    frame["stop_loss_price"] = frame["close"] - (frame["atr_14"] * ATR_STOP_MULTIPLIER)

    adx_frame = ta.adx(frame["high"], frame["low"], frame["close"], length=14)
    frame["adx"] = adx_frame["ADX_14"]
    return frame


def build_momentum_signal_series(df):
    # cond_ema = (
    #     (df["ema_9"] > df["ema_21"])
    #     & (df["ema_9"] > df["ema_9"].shift(1))
    #     & (df["ema_21"] > df["ema_21"].shift(1))
    # )
    cond_ema = (df["ema_9"] > df["ema_21"])
    cond_vwap = (
        (df["close"] > df["vwap"])
        & (df["close"] <= df["vwap"] * VWAP_CHASE_THRESHOLD)
    )
    cond_orb = (
        (df.index.strftime("%H:%M") >= ENTRY_CUTOFF_TIME)
        & (df["close"] > df["orb_high"])
    )
    cond_adx = df["adx"] > ADX_THRESHOLD

    return (cond_ema & cond_vwap & cond_orb & cond_adx).fillna(False)


def fetch_signal_frame(symbol, reference_time=None):
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
    symbol_bars.index = normalize_bar_index(symbol_bars.index)
    frame = symbol_bars.between_time("08:30", "15:00").resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()
    if len(frame) < 21:
        return None

    frame = add_momentum_indicators(frame)
    required_columns = {
        "close",
        "low",
        "ema_9",
        "ema_21",
        "vwap",
        "orb_high",
        "stop_loss_price",
        "adx",
    }
    if not required_columns.issubset(frame.columns):
        return None

    return frame


def determine_exit_reason(position, current_bar, current_time, market_close_time):
    
    #05.08: exit 
    current_close = float(current_bar["close"])

    # 1. 動態更新停損 (Trailing Stop) - 永遠不往下調
    # 在你的 PositionState 中增加一個最高價紀錄或直接更新 stop_loss_price
    new_stop_loss = current_close - (float(current_bar["atr_14"]) * 2.0)
    if new_stop_loss > position.stop_loss_price:
        position.stop_loss_price = new_stop_loss # 鎖住利潤

    if float(current_bar["low"]) <= position.stop_loss_price:
        return EXIT_REASON_ATR_STOP
    # if float(current_bar["ema_9"]) <= float(current_bar["ema_21"]):
    # 05.08: 更靈敏的 EMA 離場 (例如：收盤價跌破 EMA 21)
    if current_close < float(current_bar["ema_21"]):
        return EXIT_REASON_EMA_DEAD_CROSS
    if current_time >= market_close_time - timedelta(minutes=5):
        return EXIT_REASON_MARKET_CLOSE
    return None


def submit_market_order(symbol, qty, side):
    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    trading_client.submit_order(order_data)


async def day_trade_momentum_agent(symbol=None, qty=None):
    runtime_symbol = symbol or get_runtime_symbol()
    order_qty = qty or get_order_quantity()
    position = None
    print(f"📡 啟動 {runtime_symbol} Momentum Breakout 日內監控循環...")

    while True:
        current_time = get_current_central_time()
        market_open, market_close = get_execution_window(current_time)
        if current_time < market_open:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        if current_time > market_close:
            print_outside_execution_time(current_time, market_open, market_close)
            return

        frame = fetch_signal_frame(symbol=runtime_symbol, reference_time=current_time)
        if frame is None or len(frame) < 3: 
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        latest = frame.iloc[-2] # 05.08 1 -> 2 使用倒數第二根 K 線作為最新數據，避免未完成的當前 K 線帶來的噪音
        latest_bar_time = frame.index[-2]
        # current_price = float(latest["close"])
        current_price = float(frame.iloc[-1]["close"]) # 05.08 2 -> 1 使用當前 K 線的價格作為最新價格，能更即時反映市場變化，但可能會有未完成 K 線的噪音

        if position is None:
            signal_series = build_momentum_signal_series(frame)
            if bool(signal_series.iloc[-2]): # 05.08 1 -> 2 使用倒數第二根 K 線的信號，避免未完成的當前 K 線帶來的噪音
                print(f"🎯 {runtime_symbol} Momentum 買入信號觸發！價格: {current_price:.2f}")
                submit_market_order(symbol=runtime_symbol, qty=order_qty, side=OrderSide.BUY)
                position = PositionState(
                    entry_price=current_price,
                    qty=order_qty,
                    entry_time=latest_bar_time,
                    stop_loss_price=float(latest["stop_loss_price"]),
                )
        else:
            exit_reason = determine_exit_reason(
                position=position,
                current_bar=latest,
                current_time=latest_bar_time,
                market_close_time=get_regular_market_close(latest_bar_time),
            )
            if exit_reason:
                print(f"🚪 {runtime_symbol} 觸發離場條件: {exit_reason}，價格: {current_price:.2f}")
                submit_market_order(symbol=runtime_symbol, qty=position.qty, side=OrderSide.SELL)
                position = None

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main():
    bootstrap_runtime()
    current_time = get_current_central_time()
    market_open, market_close = get_execution_window(current_time)
    if current_time < market_open or current_time > market_close:
        print_outside_execution_time(current_time, market_open, market_close)
        return

    await day_trade_momentum_agent(symbol=get_runtime_symbol(), qty=get_order_quantity())


if __name__ == "__main__":
    asyncio.run(main())