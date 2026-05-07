import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

BOLLINGER_LOWER_COLUMN = "BBL_20_2.0_2.0"
BOLLINGER_MIDDLE_COLUMN = "BBM_20_2.0_2.0"

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


def add_indicators(df):
    df = df.copy()
    df.ta.macd(append=True)
    df.ta.rsi(append=True)
    df.ta.bbands(length=20, std=2, append=True)
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
    df = pd.concat([df, stoch], axis=1)
    df["J"] = 3 * df["STOCHk_9_3_3"] - 2 * df["STOCHd_9_3_3"]
    return df

def run_qqq_backtest():
    symbol = "NVDA"
    client = build_data_client()
    print(f"正在獲取 {symbol} 歷史數據...")
    
    # 獲取過去 30 天的數據 (Alpaca 免費版通常可獲取近期數據)
    start_time = datetime.now() - timedelta(days=30)
    
    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute, 
        start=start_time
    )
    
    # 抓取數據並轉為 DataFrame
    bars = client.get_stock_bars(request_params).df.xs(symbol)
    
    # 將 1 分鐘線合成 5 分鐘線 (做 T 核心週期)
    df = bars.resample('5min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()

    # ==========================================
    # 2. 計算指標 (MACD, BOLL, RSI, KDJ)
    # ==========================================
    df = add_indicators(df)

    # ==========================================
    # 3. 定義你的做 T 邏輯 (買入信號)
    # ==========================================
    # 條件 1: MACD 綠柱縮短 (目前的柱值 > 前一根，且柱值為負)
    cond_macd = (df['MACDh_12_26_9'] > df['MACDh_12_26_9'].shift(1)) & (df['MACDh_12_26_9'] < 0)
    
    # 條件 2: 價格觸及或接近布林下軌 (低吸)
    # cond_boll = df['close'] <= df[BOLLINGER_LOWER_COLUMN]
    cond_boll = df['close'] < df[BOLLINGER_MIDDLE_COLUMN]
    
    # 條件 3: KDJ 的 J 線從低位(<25)向上拐頭
    cond_kdj = (df['J'] > df['J'].shift(1)) & (df['J'].shift(1) < 25)
    
    # 條件 4: RSI 處於相對低位 (<45)
    cond_rsi = df['RSI_14'] < 45

    cond_volume = df['volume'] > df['volume'].shift(1)

    # 綜合信號
    df['signal'] = 0
    df.loc[cond_macd & cond_boll & cond_kdj & cond_rsi & cond_volume, 'signal'] = 1

    # ==========================================
    # 4. 計算回測結果
    # ==========================================
    # 假設進場後，持倉 15 分鐘 (3 根 5min K線) 後平倉
    df['ret'] = df['close'].shift(-12) / df['close'] - 1
    
    trades = df[df['signal'] == 1].copy()
    
    if len(trades) == 0:
        print("未發現符合條件的交易信號，請嘗試放寬指標限制。")
        return

    win_rate = (trades['ret'] > 0).mean()
    avg_ret = trades['ret'].mean()
    total_ret = (1 + trades['ret']).prod() - 1

    print("-" * 30)
    print(f"回測結果報告 ({symbol})")
    print(f"總 K 線數: {len(df)}")
    print(f"觸發交易次數: {len(trades)}")
    print(f"勝率: {win_rate:.2%}")
    print(f"單筆平均收益: {avg_ret:.4%}")
    print(f"策略累計收益: {total_ret:.2%}")
    print("-" * 30)

if __name__ == "__main__":
    run_qqq_backtest()