import os
import asyncio
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- 1. 從 GitHub Secrets 讀取環境變數 ---
FMP_API_KEY = os.getenv("FMP_API_KEY")
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")

# 初始化 Alpaca 客戶端
trading_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)
data_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)

# --- 2. FMP 篩選邏輯 ---
def get_fmp_watchlist():
    print("🔍 正在從 FMP 獲取今日 Low Float 清單...")
    url = f"https://financialmodelingprep.com/api/v3/stock-screener?priceMoreThan=3&priceLowerThan=20&volumeMoreThan=300000&isEtf=false&apikey={FMP_API_KEY}"
    try:
        stocks = requests.get(url).json()
        watchlist = []
        for s in stocks[:15]:
            symbol = s['symbol']
            p_url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={FMP_API_KEY}"
            p_data = requests.get(p_url).json()
            if p_data:
                mkt_cap = p_data[0].get('mktCap', 0)
                price = p_data[0].get('price', 1)
                if (mkt_cap / price) < 15000000: # Float < 15M
                    watchlist.append(symbol)
        return watchlist
    except Exception as e:
        print(f"❌ 篩選失敗: {e}")
        return []

# --- 3. 你提供的核心監控與賣出邏輯 ---
async def sniper_agent(symbol):
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

                if vol_spike_sell or macd_dead_cross or doji_exit or break_vwap or break_ema9:
                    reasons = []
                    if vol_spike_sell: reasons.append("大量賣出")
                    if macd_dead_cross: reasons.append("MACD死叉")
                    if doji_exit: reasons.append(f"獲利達標({profit_pct:.2%})十字星")
                    if break_vwap: reasons.append("破VWAP")
                    if break_ema9: reasons.append("破EMA9")
                    
                    print(f"🚨 {symbol} 賣出觸發！理由: {', '.join(reasons)}")
                    order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                    trading_client.submit_order(order_data)
                    in_position = False
                    break 

        except Exception as e:
            print(f"⚠️ {symbol} 錯誤: {e}")
            
        await asyncio.sleep(30)

# --- 4. 主程式入口 ---
async def main():
    watchlist = get_fmp_watchlist()
    if not watchlist:
        print("📭 今日無符合條件之標的。")
        return
        
    print(f"✅ 今日監控清單: {watchlist}")
    
    # 使用 wait_for 設定 GitHub Actions 的強制結束時間 (例如 90 分鐘)
    try:
        tasks = [sniper_agent(s) for s in watchlist]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5400) 
    except asyncio.TimeoutError:
        print("⏰ 交易時段結束，關閉程式。")

if __name__ == "__main__":
    asyncio.run(main())