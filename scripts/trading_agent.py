import os
import asyncio
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from finvizfinance.screener.overview import Overview
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient, NewsClient
from alpaca.data.requests import StockBarsRequest, NewsRequest
from alpaca.data.timeframe import TimeFrame

from google import genai

try:
    from scripts.trading_agent_env import load_runtime_config
except ModuleNotFoundError:
    from trading_agent_env import load_runtime_config

FMP_API_KEY = None
trading_client = None
data_client = None
news_client = None
ai_client = None

MIN_PRICE = 3
MAX_PRICE = 20
MAX_FLOAT_SHARES = 10_000_000
MIN_RELATIVE_VOLUME = 5
MIN_CURRENT_VOLUME = 1_000_000
MIN_PRICE_CHANGE_PERCENT = 10
MAX_PRICE_CHANGE_PERCENT = 20
CENTRAL_TZ = ZoneInfo("America/Chicago")
DEFAULT_EXECUTION_DURATION_MINUTES = 90
NEWS_LOOKUP_LIMIT = 5
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def bootstrap_runtime():
    global FMP_API_KEY, trading_client, data_client, news_client, ai_client

    config = load_runtime_config()
    FMP_API_KEY = config.fmp_api_key
    trading_client = TradingClient(config.alpaca_api_key, config.alpaca_secret_key, paper=True)
    data_client = StockHistoricalDataClient(config.alpaca_api_key, config.alpaca_secret_key)
    news_client = NewsClient(config.alpaca_api_key, config.alpaca_secret_key)

    google_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not google_api_key:
        ai_client = None
        return

    try:
        ai_client = genai.Client(api_key=google_api_key)
    except Exception as exc:
        ai_client = None
        print(f"⚠️ AI client initialization failed: {exc}. Skipping AI news filtering.")


async def validate_news_with_ai(symbol):
    if news_client is None:
        print(f"⚠️ News client unavailable for {symbol}. Rejecting symbol until news validation recovers.")
        return False

    try:
        request_params = NewsRequest(symbols=symbol, limit=NEWS_LOOKUP_LIMIT)
        news = news_client.get_news(request_params)
    except Exception as exc:
        print(f"⚠️ {symbol} 新聞取得失敗: {exc}。本輪拒絕監控，直到新聞驗證恢復。")
        return False

    news_items = getattr(news, "news", [])
    if not news_items:
        print(f"⚠️ {symbol} 沒有即時新聞，小心是純籌碼炒作。")
        return False

    for n in news_items:
        print(f"🕒 {n.created_at} | 📰 {n.headline}")

    headlines_text = "\n\n".join(
        "\n".join(
            part
            for part in (
                f"Headline: {item.headline}",
                f"Summary: {getattr(item, 'summary', '')}" if getattr(item, "summary", "") else "",
            )
            if part
        )
        for item in news_items
    )
    print(f"🤖 正在請 AI 評估 {symbol} 的新聞品質...")
    ai_opinion = await ask_ai_sentiment(symbol, headlines_text)
    if ai_opinion is None:
        print(f"⚠️ AI 無法評估 {symbol}，本輪拒絕監控。")
        return False

    print(f"📊 AI 評估結果：\n{ai_opinion}")
    return is_positive_ai_verdict(ai_opinion)


async def filter_watchlist_by_news(watchlist):
    approved_watchlist = []
    for symbol in watchlist:
        is_news_positive = await validate_news_with_ai(symbol)
        if not is_news_positive:
            print(f"⚠️ {symbol} 的新聞評估不佳，跳過監控。")
            continue
        approved_watchlist.append(symbol)

    return approved_watchlist


def is_positive_ai_verdict(ai_opinion):
    normalized_verdict = (ai_opinion or "").strip().upper()
    return normalized_verdict.startswith("[YES]") or normalized_verdict.startswith("YES")



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
            f"⚠️ EXECUTION_DURATION_MINUTES must be greater than 0. "
            f"Using default {DEFAULT_EXECUTION_DURATION_MINUTES} minutes."
        )
        return DEFAULT_EXECUTION_DURATION_MINUTES

    return duration_minutes


def get_execution_window(reference_time=None):
    current_time = reference_time.astimezone(CENTRAL_TZ) if reference_time else get_current_central_time()
    market_open = current_time.replace(hour=8, minute=15, second=0, microsecond=0)
    market_close = market_open + timedelta(minutes=get_execution_duration_minutes())
    return market_open, market_close


def print_outside_execution_time(current_time, market_open, market_close):
    formatted_current = current_time.strftime("%I:%M %p")
    formatted_open = market_open.strftime("%I:%M %p")
    formatted_close = market_close.strftime("%I:%M %p")
    print(
        "⏰ Outside execution time. "
        f"Current time {formatted_current} {current_time.tzinfo} "
        f"is outside the {formatted_open}-{formatted_close} {market_open.tzinfo} trading window."
    )


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
            df['EMA20'] = ta.ema(df.close, length=20)
            macd = df.ta.macd()
            df = pd.concat([df, macd], axis=1)
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            current_price = last['close']

            # --- 買入邏輯 ---
            if not in_position:
                if current_price > last['VWAP'] and current_price > last['EMA20']:
                    print(f"🎯 {symbol} 買入信號觸發！價格: {current_price}")
                    order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
                    trading_client.submit_order(order_data)
                    entry_price = current_price
                    in_position = True

            # --- 賣出邏輯 ---
            else:
                ct_timezone = pytz.timezone("US/Central")
                now_ct = datetime.datetime.now(ct_timezone)

                if now_ct.hour == 14 and now_ct.minute >= 55:
                    print(f"⏰ 當前時間 {now_ct.strftime('%H:%M')}，接近收盤！")
                    print(f"🚨 強制清倉所有標的，包含 {symbol}")
                    
                    # 呼叫 Alpaca API 清空所有倉位並取消掛單
                    trading_client.close_all_positions(cancel_orders=True)
                    
                    in_position = False
                    return # 結束此 Agent 任務


                profit_pct = (current_price - entry_price) / entry_price
                avg_vol = df['volume'].iloc[-6:-1].mean()
                
                vol_spike_sell = (last['volume'] > avg_vol * 3) and (last['close'] < last['open'])
                macd_dead_cross = last['MACDh_12_26_9'] < 0 and prev['MACDh_12_26_9'] >= 0
                is_doji = abs(last['open'] - last['close']) <= (last['high'] - last['low']) * 0.1
                doji_exit = is_doji and (profit_pct > 0.02) # 獲利 > 2% 才因十字星賣出
                break_vwap = last['close'] < last['VWAP'] and prev['close'] >= prev['VWAP']
                break_ema9 = last['close'] < last['EMA9'] and prev['close'] >= prev['EMA9']


                hard_stop = profit_pct <= -0.015
                if profit_pct < 0.05:
                    if hard_stop or break_vwap or vol_spike_sell:
                        reasons = []
                        if hard_stop: reasons.append(f"硬止損觸發({profit_pct:.2%})")
                        if break_vwap: reasons.append("向下突破VWAP")
                        if vol_spike_sell: reasons.append("放量下跌")
                        
                        print(f"🚨 {symbol} 保護性賣出！理由: {', '.join(reasons)}")
                        order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                        trading_client.submit_order(order_data)
                        
                        # 計算利潤並結束該筆交易
                        profit = (current_price - entry_price) * qty
                        daily_profit_tracker['profit'] += profit
                        in_position = False
                        print(f"💰 止損/保護完成！利潤: ${profit:.2f}，日累計: ${daily_profit_tracker['profit']:.2f}")
                        return
                else:
                    # A. 第一層賣出 (減倉 50%): 偵測趨勢走弱
                    doji_exit = is_doji # 此時已獲利 > 5%，不需額外 check 2%
                    profit_threshold_10 = profit_pct > 0.10
                    
                    if (break_ema9 or macd_dead_cross or doji_exit or profit_threshold_10):
                        reasons = []
                        if break_ema9: reasons.append("向下破9EMA")
                        if macd_dead_cross: reasons.append("MACD死叉")
                        if doji_exit: reasons.append("高位十字星")
                        if profit_threshold_10: reasons.append(f"達到10%目標")
                        
                        sell_qty = qty // 2
                        if sell_qty > 0:
                            print(f"💰 {symbol} 獲利入袋！理由: {', '.join(reasons)}，賣出50%({sell_qty}股)")
                            order_data = MarketOrderRequest(symbol=symbol, qty=sell_qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                            trading_client.submit_order(order_data)
                            
                            # 更新剩餘部位與利潤
                            profit = (current_price - entry_price) * sell_qty
                            daily_profit_tracker['profit'] += profit
                            qty -= sell_qty
                            print(f"💵 部分獲利累計: ${daily_profit_tracker['profit']:.2f}")

                    # B. 第二層全賣 (剩餘出清): 趨勢徹底反轉
                    # 即使獲利超過 5%，若跌回 VWAP 或出現極大量賣壓，則清倉
                    elif break_vwap or vol_spike_sell:
                        print(f"🚨 {symbol} 趨勢反轉清倉！理由: {'破VWAP' if break_vwap else '放量賣壓'}")
                        order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                        trading_client.submit_order(order_data)
                        
                        profit = (current_price - entry_price) * qty
                        daily_profit_tracker['profit'] += profit
                        in_position = False
                        print(f"💰 交易完整結束！日總利潤: ${daily_profit_tracker['profit']:.2f}")
                        return

        except Exception as e:
            print(f"⚠️ {symbol} 錯誤: {e}")
            
        await asyncio.sleep(30)
        

async def ask_ai_sentiment(symbol, all_headlines):
    if ai_client is None:
        return None

    prompt = f"""
    你現在是一位美股當沖專家。請分析股票 {symbol} 的以下新聞標題：
    
    {all_headlines}
    
    請幫我做三件事：
    1. 判斷這是不是強利多 (FDA、合約、併購、財報大好)？
    2. 有沒有看到 'Offering' 或 'Warrants' 等增發圈錢的陷阱？
    3. 最終決定：該股是否值得今天狙擊？(回答 YES 或 NO)
    
    格式請簡短，例如：[YES] 理由：FDA通過。
    """
    try:
        response = ai_client.models.generate_content(
            model=(os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
            contents=prompt,
        )
        return getattr(response, "text", None)
    except Exception as e:
        print(f"⚠️ AI 分析失敗: {e}")
        return None

# --- 4. 主程式入口 ---
async def main():
    bootstrap_runtime()

    current_time = get_current_central_time()
    market_open, market_close = get_execution_window(current_time)

    if current_time < market_open or current_time >= market_close:
        print_outside_execution_time(current_time, market_open, market_close)
        return
    
    daily_profit_tracker = {'profit': 0}
    
    while get_current_central_time() < market_close:
        watchlist = get_fmp_watchlist()
        if not watchlist:
            print("📭 目前無符合條件之標的。")
            await asyncio.sleep(60)
            continue

        watchlist = await filter_watchlist_by_news(watchlist)
        if not watchlist:
            print("📭 新聞篩選後無符合條件之標的。")
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