import os
import re
import signal
import time
from io import StringIO
import pandas as pd
import pandas_ta as ta
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone

# Alpaca 相關套件
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, OptionChainRequest, OptionSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import ContractType, OrderSide, TimeInForce


# --- 全域參數設定 ---
API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
BASE_URL = "https://paper-api.alpaca.markets"

MAX_TOTAL_POSITIONS = 5  # 最大持倉標的數
PROFIT_TARGET = 0.50     # 50% 止盈
EXIT_DTE = 21            # 21天硬性離場
RSI_THRESHOLD = 35       # RSI 超賣門檻
DTE_RANGE = (30, 45)     # 目標到期日範圍
TARGET_DELTA = -0.18     # 目標 Delta

MONITOR_INTERVAL = 600   # 監控任務的循環間隔（秒），預設 10 分鐘
HTTP_REQUEST_TIMEOUT_SECONDS = 10
YFINANCE_TIMEOUT_SECONDS = 10

stock_client = None
option_client = None
trading_client = None
ALPACA_RETRY_ATTEMPTS = 3
ALPACA_RETRY_DELAY_SECONDS = 2


def _require_credentials():
    if not API_KEY or not SECRET_KEY:
        raise ValueError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY environment variables")


def get_stock_client():
    global stock_client
    if stock_client is None:
        _require_credentials()
        stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    return stock_client


def get_option_client():
    global option_client
    if option_client is None:
        _require_credentials()
        option_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    return option_client


def get_trading_client():
    global trading_client
    if trading_client is None:
        _require_credentials()
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
    return trading_client


def call_alpaca_with_retries(operation, description):
    last_error = None
    for attempt in range(1, ALPACA_RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            last_error = error
            print(f"{description} 失敗，第 {attempt}/{ALPACA_RETRY_ATTEMPTS} 次: {error}")
            if attempt < ALPACA_RETRY_ATTEMPTS and ALPACA_RETRY_DELAY_SECONDS > 0:
                time.sleep(ALPACA_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error

    raise RuntimeError(f"{description} 未執行")


def resolve_underlying_symbol(position):
    underlying_symbol = getattr(position, "underlying_symbol", None)
    if underlying_symbol:
        return underlying_symbol

    symbol = getattr(position, "symbol", "") or ""
    match = re.match(r"^([A-Z-]+?)(\d{6}[CP]\d{8})$", symbol)
    if match:
        return match.group(1)

    return symbol


def _raise_timeout(_signum, _frame):
    raise TimeoutError()


def get_earnings_calendar(symbol, timeout_seconds=YFINANCE_TIMEOUT_SECONDS):
    alarm_armed = False
    previous_handler = None

    if hasattr(signal, "SIGALRM"):
        try:
            previous_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, _raise_timeout)
            signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
            alarm_armed = True
        except ValueError:
            alarm_armed = False

    try:
        return yf.Ticker(symbol).calendar
    except TimeoutError:
        print(f"⚠️ {symbol} 財報查詢逾時 {timeout_seconds} 秒，略過財報檢查。")
        return None
    except Exception as error:
        print(f"⚠️ {symbol} 財報查詢失敗，略過財報檢查: {error}")
        return None
    finally:
        if alarm_armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

def is_earnings_approaching(symbol):
    """ 使用 yfinance 檢查未來 7 天內是否有財報 """
    try:
        calendar = get_earnings_calendar(symbol)
        if calendar is not None and 'Earnings Date' in calendar:
            earnings_dates = calendar['Earnings Date']
            if not earnings_dates: return False
            next_earnings = earnings_dates[0].replace(tzinfo=None)
            today = datetime.now().replace(tzinfo=None)
            days_to_earnings = (next_earnings - today).days
            if 0 <= days_to_earnings <= 7:
                print(f"!!! {symbol} 財報警告：{days_to_earnings} 天後發布，跳過。")
                return True
        return False
    except:
        return False

def get_sp100_tickers():
    """ 獲取 S&P 100 成分股清單 """
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P_100'
        response = requests.get(url, timeout=HTTP_REQUEST_TIMEOUT_SECONDS)
        print(f"成功獲取 S&P 100 成分股清單 (HTTP {response.status_code})")
        df = pd.read_html(StringIO(response.text))[2]
        return df['Symbol'].tolist()
    except Exception as e:
        print(f"⚠️ 無法獲取 S&P 100 成分股清單，使用預設清單: {e}")
        return ["MSFT", "AAPL", "GOOGL", "AMZN", "META", "NVDA", "JPM", "XOM", "V", "PG"]

def run_monitor_and_check_risk():
    """ 監控現有部位並返回當前持倉數 """
    try:
        client = get_trading_client()
        positions = call_alpaca_with_retries(client.get_all_positions, "讀取持倉")
        account = call_alpaca_with_retries(client.get_account, "讀取帳戶")
        print(f"當前持倉數: {len(positions)} with account {account.account_number}")
        active_underlyings = set()
        
        for pos in positions:
            if pos.asset_class != "us_option": continue
            
            symbol = pos.symbol
            underlying = resolve_underlying_symbol(pos)
            active_underlyings.add(underlying)
            
            # 1. 50% 止盈檢查
            plpc = float(pos.unrealized_plpc)
            if plpc >= PROFIT_TARGET:
                print(f"【止盈】{symbol} 獲利 {plpc*100:.1f}%，執行平倉。")
                client.close_position(pos.asset_id)
                active_underlyings.discard(underlying)
                continue

            # 2. 21 DTE 硬性離場檢查
            match = re.search(r"(\d{6})", symbol)
            if match:
                date_str = match.group(1)
                expiry_date = datetime.strptime(date_str, "%y%m%d").replace(tzinfo=timezone.utc)
                dte = (expiry_date - datetime.now(timezone.utc)).days
                if dte <= EXIT_DTE:
                    print(f"【時間止損】{symbol} 剩餘 {dte} 天，執行離場。")
                    client.close_position(pos.asset_id)
                    active_underlyings.discard(underlying)
                    
        return len(active_underlyings)
    except Exception as e:
        print(f"監控錯誤: {e}")
        return 999

def find_and_trade_put(symbol):
    """ 尋找最佳 Delta 的 Put 並下單 """
    try:
        options_client = get_option_client()
        client = get_trading_client()
        now = datetime.now()
        min_expiry = (now + timedelta(days=DTE_RANGE[0])).date()
        max_expiry = (now + timedelta(days=DTE_RANGE[1])).date()
        
        # 搜尋期權鏈
        req = OptionChainRequest(
            underlying_symbol=symbol,
            expiration_date_gte=min_expiry,
            expiration_date_lte=max_expiry,
            type=ContractType.PUT,
        )
        chain = options_client.get_option_chain(req)
        contract_symbols = list(chain.keys())
        if not contract_symbols: return

        # 獲取快照以分析 Delta
        snapshots = options_client.get_option_snapshots(OptionSnapshotRequest(symbol_or_symbols=contract_symbols))
        
        best_contract = None
        smallest_diff = float('inf')
        
        for name, snap in snapshots.items():
            if snap.greeks and snap.greeks.delta is not None:
                delta = snap.greeks.delta
                if -0.20 <= delta <= -0.15:
                    diff = abs(delta - TARGET_DELTA)
                    if diff < smallest_diff:
                        smallest_diff = diff
                        best_contract = name
        
        if best_contract:
            print(f">>> 執行交易: 賣出 {best_contract} (Delta: {snapshots[best_contract].greeks.delta})")
            client.submit_order(MarketOrderRequest(
                symbol=best_contract, qty=1, side=OrderSide.SELL, time_in_force=TimeInForce.DAY
            ))
    except Exception as e:
        current_count -= 1  # 回退計數以允許下一個機會
        print(f"下單失敗 {symbol}: {e}")

def main():
    print(f"--- 啟動交易系統: {datetime.now()} ---")
    stock_data_client = get_stock_client()
    
    # 1. 執行監控並檢查風控
    current_count = run_monitor_and_check_risk()
    if current_count >= MAX_TOTAL_POSITIONS:
        print(f"持倉已滿 ({current_count})，停止掃描新機會。")
        return

    # 2. 獲取候選標的
    print("開始抓候選清單...")
    tickers = get_sp100_tickers()
    print(f"候選清單數量: {len(tickers)}")
    for symbol in tickers:
        print(f"掃描 {symbol}... (當前持倉數: {current_count})")
        
        if current_count >= MAX_TOTAL_POSITIONS: break
        
        symbol = symbol.replace('.', '-')
        
        # 財報避險
        if is_earnings_approaching(symbol): continue
        
        # RSI 動能掃描
        try:
            bars = stock_data_client.get_stock_bars(StockBarsRequest(
                symbol_or_symbols=symbol, timeframe=TimeFrame.Day, 
                start=datetime.now() - timedelta(days=60)
            )).df
            rsi = ta.rsi(bars['close'], length=14).iloc[-1]
            
            if rsi < RSI_THRESHOLD:
                print(f"觸發訊號: {symbol} RSI={rsi:.2f}")
                find_and_trade_put(symbol)
                current_count += 1 # 更新計數避免超買
        except Exception as e:
            continue

if __name__ == "__main__":
    job_type = os.getenv("JOB_TYPE", "MAIN").upper()
    if job_type == "MONITOR":
        # 監控模式：每 10 分鐘執行一次，持續運行直至 GitHub Actions 強制結束 (預設 360 分鐘或自訂)
        # 為了安全起見，我們讓它運行一小時 (6 次循環) 後正常退出，讓下一個 Cron 接棒
         for i in range(6):
            run_monitor_and_check_risk()
            if i < 5:  # 最後一次不需要等待
                print(f"等待 {MONITOR_INTERVAL} 秒後進行下一次掃描...")
                time.sleep(MONITOR_INTERVAL)
    else:
        print("執行主要交易任務...")
        main()
