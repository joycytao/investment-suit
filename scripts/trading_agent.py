import os
import asyncio
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from finvizfinance.screener.overview import Overview
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

try:
    from scripts.trading_agent_env import load_runtime_config
except ModuleNotFoundError:
    from trading_agent_env import load_runtime_config

FMP_API_KEY = None
trading_client = None
data_client = None

MIN_PRICE = 3
MAX_PRICE = 20
MAX_FLOAT_SHARES = 10_000_000
MIN_RELATIVE_VOLUME = 5
MIN_CURRENT_VOLUME = 1_000_000
MIN_PRICE_CHANGE_PERCENT = 10
MAX_PRICE_CHANGE_PERCENT = 20


def bootstrap_runtime():
    global FMP_API_KEY, trading_client, data_client

    config = load_runtime_config()
    FMP_API_KEY = config.fmp_api_key
    trading_client = TradingClient(config.alpaca_api_key, config.alpaca_secret_key, paper=True)
    data_client = StockHistoricalDataClient(config.alpaca_api_key, config.alpaca_secret_key)


def get_finviz_candidates():
    filters = {
        "Price": "$1 to $20",
        "Float": "Under 10M",
        "Relative Volume": "Over 5",
        "Current Volume": "Over 1M",
        "Change": "Up 10%",
    }

    overview = Overview()
    overview.set_filter(filters_dict=filters)
    screener_df = overview.screener_view()
    if screener_df.empty:
        return []

    candidates = []
    for row in screener_df.to_dict("records"):
        candidates.append(
            {
                "symbol": row.get("Ticker"),
                "price": float(row.get("Price") or 0),
                "volume": float(row.get("Volume") or 0),
                "changePercentage": float(row.get("Change") or 0) * 100,
            }
        )

    return candidates

# --- 2. FMP 篩選邏輯 ---
def get_fmp_watchlist():
    print("🔍 正在從 FinViz 獲取今日 Low Float 清單...")
    try:
        stocks = get_finviz_candidates()

        watchlist = []
        for s in stocks:
            symbol = s["symbol"]
            current_price = s.get("price", 0) or 0
            current_volume = s.get("volume", 0) or 0
            price_change = s.get("changePercentage", 0) or 0

            if not (MIN_PRICE <= current_price <= MAX_PRICE):
                continue
            if current_volume < MIN_CURRENT_VOLUME:
                continue
            if not (MIN_PRICE_CHANGE_PERCENT <= price_change <= MAX_PRICE_CHANGE_PERCENT):
                continue

            watchlist.append(symbol)

        return watchlist
    except Exception as e:
        print(f"❌ 篩選失敗: {e}")
        return []

# --- 3. 你提供的核心監控與賣出邏輯 ---
async def sniper_agent(symbol, daily_profit_tracker):
    in_position = False
    entry_price = 0  
    qty = 100 
    print(f"📡 啟動 {symbol} 監控循環...")
    
    while True:
        try:
            now = datetime.now()
            request_params = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,
                start=now - timedelta(minutes=100)
            )
            bars = data_client.get_stock_bars(request_params).df
            if bars.empty: continue
            df = bars.loc[symbol].copy()
            
            # 指標計算
            df['VWAP'] = ta.vwap(df.high, df.low, df.close, df.volume)
            df['EMA9'] = ta.ema(df.close, length=9)
            macd = df.ta.macd()
            df = pd.concat([df, macd], axis=1)
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            current_price = last['close']

            # --- 買入邏輯 ---
            if not in_position:
                if last['MACDh_12_26_9'] > 0 and prev['MACDh_12_26_9'] <= 0:
                    print(f"🎯 {symbol} 買入信號觸發！價格: {current_price}")
                    order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
                    trading_client.submit_order(order_data)
                    entry_price = current_price
                    in_position = True

            # --- 賣出邏輯 ---
            else:
                profit_pct = (current_price - entry_price) / entry_price
                avg_vol = df['volume'].iloc[-6:-1].mean()
                
                vol_spike_sell = (last['volume'] > avg_vol * 3) and (last['close'] < last['open'])
                macd_dead_cross = last['MACDh_12_26_9'] < 0 and prev['MACDh_12_26_9'] >= 0
                is_doji = abs(last['open'] - last['close']) <= (last['high'] - last['low']) * 0.1
                doji_exit = is_doji and (profit_pct > 0.02) # 獲利 > 2% 才因十字星賣出
                break_vwap = last['close'] < last['VWAP'] and prev['close'] >= prev['VWAP']
                break_ema9 = last['close'] < last['EMA9'] and prev['close'] >= prev['EMA9']

                # 第一層賣出: 向下破 9EMA, MACD 死叉, 出現十字星 (且獲利 > 2%), 獲利 > 10% -> sell 50%
                profit_threshold = profit_pct > 0.10
                if (break_ema9 or macd_dead_cross or doji_exit or profit_threshold):
                    reasons = []
                    if break_ema9: reasons.append("向下破9EMA")
                    if macd_dead_cross: reasons.append("MACD死叉")
                    if doji_exit: reasons.append(f"十字星(獲利>{profit_pct:.2%})")
                    if profit_threshold: reasons.append(f"獲利>{profit_pct:10%}")
                    
                    sell_qty = qty // 2
                    print(f"🚨 {symbol} 部分賣出觸發！理由: {', '.join(reasons)}，賣出50%({sell_qty}股)")
                    order_data = MarketOrderRequest(symbol=symbol, qty=sell_qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                    trading_client.submit_order(order_data)
                    qty = qty - sell_qty
                    
                    # 計算利潤並更新追蹤器
                    profit = (current_price - entry_price) * sell_qty
                    daily_profit_tracker['profit'] += profit
                    print(f"💰 部分交易完成！利潤: ${profit:.2f}，日累計利潤: ${daily_profit_tracker['profit']:.2f}")

                # 第二層賣出: 大量賣出, 向下突破 VWAP 剩下全賣
                elif vol_spike_sell or break_vwap:
                    reasons = []
                    if vol_spike_sell: reasons.append("大量賣出")
                    if break_vwap: reasons.append("向下突破VWAP")
                    
                    print(f"🚨 {symbol} 全部賣出觸發！理由: {', '.join(reasons)}")
                    order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                    trading_client.submit_order(order_data)
                    in_position = False
                    
                    # 計算利潤並更新追蹤器
                    profit = (current_price - entry_price) * qty
                    daily_profit_tracker['profit'] += profit
                    print(f"💰 交易完成！利潤: ${profit:.2f}，日累計利潤: ${daily_profit_tracker['profit']:.2f}")
                    
                    # 返回信號讓主程式知道這個標的已完成交易
                    return

        except Exception as e:
            print(f"⚠️ {symbol} 錯誤: {e}")
            
        await asyncio.sleep(30)

# --- 4. 主程式入口 ---
async def main():
    bootstrap_runtime()
    
    # 市場開盤時間 9:30 CST
    market_open = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = market_open + timedelta(hours=1)
    
    daily_profit_tracker = {'profit': 0}
    
    while datetime.now() < market_close:
        watchlist = get_fmp_watchlist()
        if not watchlist:
            print("📭 目前無符合條件之標的。")
            await asyncio.sleep(60)
            continue
            
        print(f"✅ 監控清單: {watchlist}，日累計利潤: ${daily_profit_tracker['profit']:.2f}")
        
        # 檢查是否已達到日利潤目標
        if daily_profit_tracker['profit'] >= 100:
            print(f"🎉 已達到日利潤目標 $100！結束交易。")
            return
        
        # 並行監控所有標的
        tasks = [sniper_agent(s, daily_profit_tracker) for s in watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 檢查是否已達到日利潤目標
        if daily_profit_tracker['profit'] >= 100:
            print(f"🎉 已達到日利潤目標 $100！結束交易。")
            return
        
        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(f"❌ {exc}")
        raise SystemExit(1) from exc