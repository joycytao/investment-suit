import os
from datetime import datetime, timedelta

import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv


load_dotenv()


MARKET_TIMEZONE = "America/New_York"
ENTRY_CUTOFF_TIME = "10:00"
VWAP_CHASE_THRESHOLD = 1.005
ATR_STOP_MULTIPLIER = 1.5
EXIT_REASON_ATR_STOP = "atr_stop"
EXIT_REASON_EMA_DEAD_CROSS = "ema_dead_cross"
EXIT_REASON_END_OF_DATA = "end_of_data"


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


def normalize_intraday_frame(df):
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(MARKET_TIMEZONE)

    intraday = df.between_time("09:30", "16:00").copy()
    intraday["session_date"] = intraday.index.date
    return intraday


def add_momentum_indicators(df):
    df = df.copy()
    df["ema_9"] = ta.ema(df["close"], length=9)
    df["ema_21"] = ta.ema(df["close"], length=21)
    df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    weighted_price = typical_price * df["volume"]
    df["vwap"] = (
        weighted_price.groupby(df["session_date"]).cumsum()
        / df["volume"].groupby(df["session_date"]).cumsum()
    )

    opening_range_high = (
        df.between_time("09:30", "09:55")
        .groupby("session_date")["high"]
        .max()
    )
    df["orb_high"] = df["session_date"].map(opening_range_high)
    df["stop_loss_price"] = df["close"] - (df["atr_14"] * ATR_STOP_MULTIPLIER)
    return df


def build_momentum_signal_series(df):
    cond_ema = (
        (df["ema_9"] > df["ema_21"])
        & (df["ema_9"] > df["ema_9"].shift(1))
        & (df["ema_21"] > df["ema_21"].shift(1))
    )
    cond_vwap = (
        (df["close"] > df["vwap"])
        & (df["close"] <= df["vwap"] * VWAP_CHASE_THRESHOLD)
    )
    cond_orb = (
        (df.index.strftime("%H:%M") >= ENTRY_CUTOFF_TIME)
        & (df["close"] > df["orb_high"])
    )

    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx'] = adx_df['ADX_14']
    cond_trend_strong = df['adx'] > 25

    if "gamma_high" in df.columns:
        cond_gamma = df["close"] > df["gamma_high"]
    else:
        cond_gamma = pd.Series(True, index=df.index)

    # cond_time_window = (df.index.strftime("%H:%M") >= "10:00") & \
    #                (df.index.strftime("%H:%M") <= "12:00") # 12點後不再開新倉

    return (cond_ema & cond_vwap & cond_orb & cond_gamma & cond_trend_strong).fillna(False)


def simulate_momentum_trades(df):
    trades = []
    entry_row = None

    for timestamp, row in df.iterrows():
        if entry_row is None:
            if bool(row.get("signal", 0)):
                entry_row = {
                    "entry_time": timestamp,
                    "entry_price": float(row["close"]),
                    "stop_loss_price": float(row["stop_loss_price"]),
                }
            continue

        exit_price = None
        exit_reason = None

        if float(row["low"]) <= entry_row["stop_loss_price"]:
            exit_price = entry_row["stop_loss_price"]
            exit_reason = EXIT_REASON_ATR_STOP
        elif float(row["ema_9"]) <= float(row["ema_21"]):
            exit_price = float(row["close"])
            exit_reason = EXIT_REASON_EMA_DEAD_CROSS

        if exit_reason is None:
            continue

        trades.append(
            {
                "entry_time": entry_row["entry_time"],
                "exit_time": timestamp,
                "entry_price": entry_row["entry_price"],
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "ret": (exit_price / entry_row["entry_price"]) - 1,
            }
        )
        entry_row = None

    if entry_row is not None:
        last_timestamp = df.index[-1]
        last_close = float(df.iloc[-1]["close"])
        trades.append(
            {
                "entry_time": entry_row["entry_time"],
                "exit_time": last_timestamp,
                "entry_price": entry_row["entry_price"],
                "exit_price": last_close,
                "exit_reason": EXIT_REASON_END_OF_DATA,
                "ret": (last_close / entry_row["entry_price"]) - 1,
            }
        )

    return pd.DataFrame(trades)


# # --- 日內期權核心參數 ---
# OPTION_LEVERAGE = 10          # 降低槓桿：讓 QQQ 的小回撤不會瞬間觸發 20% 止損
# THETA_DECAY_5MIN = 0.0004     # 降低損耗預估：模擬 1-2 天到期（1DTE）的期權，而非末日 0DTE
# OPTION_STOP_LOSS = -0.25     # 放寬止損：給予 30% 空間，容忍 QQQ 約 3% 的反向波動
# OPTION_TAKE_PROFIT = 0.70    # 止盈設為 50%：確保贏的時候能覆蓋兩次輸的成本
# TIME_STOP_STEPS = 12         # 延長時間止損：給趨勢 60 分鐘（12 * 5min）去跑出來
# TIME_STOP_THRESHOLD = 0.02   # 只要沒虧錢（保本以上）就繼續持有

# def simulate_option_trades(df):
#     trades = []
#     entry_row = None
#     current_day = None
#     daily_trade_count = 0 
#     last_exit_time = None
    
#     # --- 放寬次數與縮短冷卻 ---
#     MAX_TRADES_PER_DAY = 3      # 從 1 次放寬到 3 次
#     COOLDOWN_MINUTES = 30       # 出場後冷卻 30 分鐘即可再戰 (原為 60)

#     for timestamp, row in df.iterrows():
#         # 換日重置
#         if current_day != timestamp.date():
#             current_day = timestamp.date()
#             daily_trade_count = 0
#             last_exit_time = None

#         # --- A. 持倉邏輯 (保持不變) ---
#         if entry_row is not None:
#             entry_row["steps"] += 1
#             stock_ret = (row["close"] / entry_row["entry_price"]) - 1
#             opt_ret = (stock_ret * OPTION_LEVERAGE) - (entry_row["steps"] * THETA_DECAY_5MIN)

#             exit_reason = None
#             if opt_ret >= OPTION_TAKE_PROFIT: exit_reason = "Quick_Profit"
#             elif opt_ret <= OPTION_STOP_LOSS: exit_reason = "Hard_Stop"
#             elif entry_row["steps"] == TIME_STOP_STEPS and opt_ret < TIME_STOP_THRESHOLD: exit_reason = "Time_Exhausted"
#             elif row["ema_9"] < row["ema_21"]: exit_reason = "Trend_Change"
#             elif timestamp.strftime("%H:%M") >= "15:55": exit_reason = "EOD_Force_Close"

#             if exit_reason:
#                 trades.append({
#                     "entry": entry_row["time"],
#                     "exit": timestamp,
#                     "ret": opt_ret,
#                     "reason": exit_reason,
#                     "duration": entry_row["steps"] * 5
#                 })
#                 entry_row = None
#                 daily_trade_count += 1
#                 last_exit_time = timestamp 
#             continue

#         # --- B. 進場檢查 (放寬條件) ---
#         # 1. 檢查信號 2. 檢查當日次數 3. 檢查冷卻
#         if row["signal"] == 1 and daily_trade_count < MAX_TRADES_PER_DAY:
#             if last_exit_time:
#                 wait_time = (timestamp - last_exit_time).total_seconds() / 60
#                 if wait_time < COOLDOWN_MINUTES:
#                     continue
            
#             entry_row = {
#                 "time": timestamp,
#                 "entry_price": row["close"],
#                 "steps": 0
#             }

#     return pd.DataFrame(trades)


def calculate_performance_metrics(trades):
    if trades.empty:
        return None

    returns = trades["ret"].astype(float)
    equity_curve = (1 + returns).cumprod()
    drawdown = equity_curve / equity_curve.cummax() - 1
    std = returns.std(ddof=1)
    sharpe = 0.0 if pd.isna(std) or std == 0 else (returns.mean() / std) * (len(returns) ** 0.5)

    return {
        "total_return": equity_curve.iloc[-1] - 1,
        "sharpe_ratio": sharpe,
        "max_drawdown": drawdown.min(),
        "win_rate": (returns > 0).mean(),
        "total_trades": int(len(trades)),
    }


def run_qqq_momentum_backtest():
    symbol = "NVDA"
    client = build_data_client()
    print(f"正在獲取 {symbol} 歷史數據...")

    start_time = datetime.now() - timedelta(days=30)

    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_time,
    )

    bars = client.get_stock_bars(request_params).df.xs(symbol)
    normalized = normalize_intraday_frame(bars)

    df = normalized.resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "session_date": "last",
        }
    ).dropna()
    df = add_momentum_indicators(df)
    df["signal"] = build_momentum_signal_series(df).astype(int)

    trades = simulate_momentum_trades(df)
    # trades = simulate_option_trades(df)
    if trades.empty:
        print("未發現符合條件的交易信號，請嘗試放寬指標限制。")
        return

    metrics = calculate_performance_metrics(trades)

    print("-" * 30)
    print(f"回測結果報告 ({symbol}) - Momentum Breakout")
    print(f"總 K 線數: {len(df)}")
    print(f"觸發交易次數: {metrics['total_trades']}")
    print(f"勝率: {metrics['win_rate']:.2%}")
    print(f"總報酬: {metrics['total_return']:.2%}")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"最大回撤: {metrics['max_drawdown']:.2%}")
    print(f"最近三筆交易:\n{trades.tail(3).to_string(index=False)}")
    print("-" * 30)


if __name__ == "__main__":
    run_qqq_momentum_backtest()