import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

from backend.options_contract_selector import select_contract
from backend.options_market_data import fetch_option_chain_snapshot
from scripts.backtest.backtest_intraday_options import (
    EXIT_REASON_BOLLINGER_TARGET,
    EXIT_REASON_FORCE_CLOSE,
    EXIT_REASON_FULL_TARGET,
    EXIT_REASON_HARD_STOP,
    EXIT_REASON_TREND_BREAK,
    FORCE_EXIT_TIME,
    FULL_PROFIT_TARGET,
    HARD_STOP_LOSS,
    MARKET_TIMEZONE,
    MAX_POSITION_FRACTION,
    PARTIAL_PROFIT_TARGET,
    build_multitimeframe_frame,
    estimate_option_price,
    normalize_intraday_frame,
)


load_dotenv()


DEFAULT_SYMBOL = "QQQ"
DEFAULT_BUYING_POWER = 25_000.0
DEFAULT_EXECUTION_DURATION_MINUTES = 385
DEFAULT_EXECUTION_MODE = "signal"
LOOKBACK_MINUTES = 780
POLL_INTERVAL_SECONDS = 60
CENTRAL_TZ = ZoneInfo("America/Chicago")
MARKET_TZ = ZoneInfo(MARKET_TIMEZONE)

trading_client = None
data_client = None


@dataclass
class OptionTradePlan:
    side: int
    contract_type: str
    strike: int
    expiry: datetime
    contract_symbol: str
    contracts: int
    entry_option_price: float
    partial_target_price: float
    full_target_price: float
    stop_price: float


@dataclass
class OptionPositionState:
    symbol: str
    side: int
    contracts: int
    entry_time: datetime
    entry_spot: float
    entry_option_price: float
    strike: int
    expiry: datetime
    contract_symbol: str
    partial_exit_taken: bool


def get_runtime_symbol() -> str:
    return (os.getenv("SYMBOL") or DEFAULT_SYMBOL).strip().upper()


def get_execution_mode() -> str:
    mode = (os.getenv("OPTION_EXECUTION_MODE") or DEFAULT_EXECUTION_MODE).strip().lower()
    return mode or DEFAULT_EXECUTION_MODE


def get_strategy_buying_power() -> float:
    raw_value = (os.getenv("OPTION_BUYING_POWER") or "").strip()
    if not raw_value:
        return DEFAULT_BUYING_POWER

    try:
        buying_power = float(raw_value)
    except ValueError:
        print(f"⚠️ Invalid OPTION_BUYING_POWER={raw_value!r}. Using default {DEFAULT_BUYING_POWER}.")
        return DEFAULT_BUYING_POWER

    if buying_power <= 0:
        print(f"⚠️ OPTION_BUYING_POWER must be greater than 0. Using default {DEFAULT_BUYING_POWER}.")
        return DEFAULT_BUYING_POWER

    return buying_power


def get_alpaca_credentials() -> tuple[str, str]:
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


def build_data_client() -> StockHistoricalDataClient:
    api_key, secret_key = get_alpaca_credentials()
    return StockHistoricalDataClient(api_key, secret_key)


def build_trading_client() -> TradingClient:
    api_key, secret_key = get_alpaca_credentials()
    return TradingClient(api_key, secret_key, paper=True)


def bootstrap_runtime() -> None:
    global trading_client, data_client

    trading_client = build_trading_client()
    data_client = build_data_client()


def get_current_central_time() -> datetime:
    return datetime.now(CENTRAL_TZ)


def get_current_market_time() -> datetime:
    return get_current_central_time().astimezone(MARKET_TZ)


def get_execution_duration_minutes() -> int:
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


def get_execution_window(reference_time: datetime | None = None) -> tuple[datetime, datetime]:
    current_time = reference_time.astimezone(CENTRAL_TZ) if reference_time else get_current_central_time()
    market_open = current_time.replace(hour=8, minute=15, second=0, microsecond=0)
    market_close = market_open + timedelta(minutes=get_execution_duration_minutes())
    return market_open, market_close


def print_outside_execution_time(current_time: datetime, market_open: datetime, market_close: datetime) -> None:
    print(
        "⏰ Outside execution time. "
        f"Current time {current_time.strftime('%I:%M %p')} {current_time.tzinfo} "
        f"is outside the {market_open.strftime('%I:%M %p')}-{market_close.strftime('%I:%M %p')} {market_open.tzinfo} trading window."
    )


def get_next_weekly_expiry(current_time: datetime) -> datetime:
    days_until_friday = (4 - current_time.weekday()) % 7
    expiry_date = (current_time + timedelta(days=days_until_friday)).date()
    return datetime(
        expiry_date.year,
        expiry_date.month,
        expiry_date.day,
        16,
        0,
        tzinfo=MARKET_TZ,
    )


def format_occ_option_symbol(symbol: str, expiry: datetime, contract_type: str, strike: int) -> str:
    option_flag = "C" if contract_type == "call" else "P"
    return f"{symbol}{expiry.strftime('%y%m%d')}{option_flag}{strike * 1000:08d}"


def build_option_trade_plan(
    symbol: str,
    signal_side: int,
    spot_price: float,
    option_price: float,
    current_time: datetime,
    buying_power: float,
) -> OptionTradePlan:
    contract_type = "call" if signal_side == 1 else "put"
    strike = int(round(spot_price))
    expiry = get_next_weekly_expiry(current_time)
    contracts = max(1, int((buying_power * MAX_POSITION_FRACTION) // (option_price * 100)))
    return OptionTradePlan(
        side=signal_side,
        contract_type=contract_type,
        strike=strike,
        expiry=expiry,
        contract_symbol=format_occ_option_symbol(symbol, expiry, contract_type, strike),
        contracts=contracts,
        entry_option_price=option_price,
        partial_target_price=option_price * (1 + PARTIAL_PROFIT_TARGET),
        full_target_price=option_price * (1 + FULL_PROFIT_TARGET),
        stop_price=option_price * (1 + HARD_STOP_LOSS),
    )


def select_trade_plan_from_chain(
    symbol: str,
    signal_side: int,
    spot_price: float,
    current_time: datetime,
    buying_power: float,
    chain: pd.DataFrame,
) -> OptionTradePlan | None:
    contract = select_contract(
        chain=chain,
        signal_time=current_time,
        option_side=signal_side,
    )
    if contract is None:
        return None

    contract_type = "call" if signal_side == 1 else "put"
    return OptionTradePlan(
        side=signal_side,
        contract_type=contract_type,
        strike=int(round(spot_price)),
        expiry=pd.to_datetime(contract["expiration_date"]).to_pydatetime().replace(tzinfo=MARKET_TZ, hour=16, minute=0),
        contract_symbol=str(contract["symbol"]),
        contracts=max(1, int((buying_power * MAX_POSITION_FRACTION) // (float(contract["ask_price"]) * 100))),
        entry_option_price=float(contract["ask_price"]),
        partial_target_price=float(contract["ask_price"]) * (1 + PARTIAL_PROFIT_TARGET),
        full_target_price=float(contract["ask_price"]) * (1 + FULL_PROFIT_TARGET),
        stop_price=float(contract["ask_price"]) * (1 + HARD_STOP_LOSS),
    )


def fetch_signal_frame(symbol: str, reference_time: datetime | None = None):
    current_time = reference_time or get_current_market_time()
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

    normalized = normalize_intraday_frame(symbol_bars)
    frame = build_multitimeframe_frame(normalized)
    if len(frame) < 30:
        return None

    return frame


def get_option_mark(row: Mapping[str, object], side: int, strike: int, current_time: datetime) -> float:
    option_price = row.get("option_price")
    if option_price is not None:
        return float(option_price)
    return float(
        estimate_option_price(
            float(row["close"]),
            row.get("iv_proxy"),
            side,
            current_time,
            strike,
        )
    )


def determine_exit_reason(
    position: OptionPositionState,
    current_bar: Mapping[str, object],
    current_time: datetime,
) -> str | None:
    option_price = get_option_mark(current_bar, position.side, position.strike, current_time)
    option_return = (option_price / position.entry_option_price) - 1
    trend_break = (position.side == 1 and float(current_bar["close"]) < float(current_bar["ema_20_1m"])) or (
        position.side == -1 and float(current_bar["close"]) > float(current_bar["ema_20_1m"])
    )
    upper_band = current_bar.get("bb_upper_5m")
    lower_band = current_bar.get("bb_lower_5m")
    bollinger_hit = (
        position.side == 1 and upper_band is not None and float(current_bar["close"]) >= float(upper_band)
    ) or (
        position.side == -1 and lower_band is not None and float(current_bar["close"]) <= float(lower_band)
    )
    force_close = current_time.strftime("%H:%M") >= FORCE_EXIT_TIME

    if option_return <= HARD_STOP_LOSS:
        return EXIT_REASON_HARD_STOP
    if trend_break:
        return EXIT_REASON_TREND_BREAK
    if bollinger_hit:
        return EXIT_REASON_BOLLINGER_TARGET
    if option_return >= FULL_PROFIT_TARGET:
        return EXIT_REASON_FULL_TARGET
    if force_close:
        return EXIT_REASON_FORCE_CLOSE
    return None


async def day_trade_options_agent(symbol: str | None = None) -> None:
    runtime_symbol = symbol or get_runtime_symbol()
    execution_mode = get_execution_mode()
    buying_power = get_strategy_buying_power()
    position = None

    print(
        f"📡 啟動 {runtime_symbol} Intraday Options 監控循環... "
        f"mode={execution_mode}, buying_power={buying_power:.0f}"
    )
    if execution_mode != DEFAULT_EXECUTION_MODE:
        print(
            "⚠️ Repo 尚未接上已驗證的期權合約搜尋與真下單路徑。"
            "當前 runner 只支援 signal mode。"
        )

    while True:
        current_time = get_current_central_time()
        market_open, market_close = get_execution_window(current_time)
        if current_time < market_open:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        if current_time > market_close:
            print_outside_execution_time(current_time, market_open, market_close)
            return

        frame = fetch_signal_frame(runtime_symbol, get_current_market_time())
        if frame is None or len(frame) < 2:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        latest_bar_time = frame.index[-1]
        latest = frame.iloc[-1]
        latest_signal = int(latest.get("signal", 0))

        if position is None:
            if latest_signal == 0:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            trade_plan = None
            try:
                chain = fetch_option_chain_snapshot(data_client, runtime_symbol, latest_bar_time)
                if not chain.empty:
                    trade_plan = select_trade_plan_from_chain(
                        symbol=runtime_symbol,
                        signal_side=latest_signal,
                        spot_price=float(latest["close"]),
                        current_time=latest_bar_time,
                        buying_power=buying_power,
                        chain=chain,
                    )
            except Exception as exc:
                print(f"⚠️ 無法取得 {runtime_symbol} 期權鏈，退回 signal plan: {exc}")

            if trade_plan is None:
                option_price = get_option_mark(latest.to_dict(), latest_signal, int(round(float(latest["close"]))), latest_bar_time)
                trade_plan = build_option_trade_plan(
                    symbol=runtime_symbol,
                    signal_side=latest_signal,
                    spot_price=float(latest["close"]),
                    option_price=option_price,
                    current_time=latest_bar_time,
                    buying_power=buying_power,
                )
            print(
                f"🎯 {runtime_symbol} 期權信號觸發: {trade_plan.contract_symbol} x{trade_plan.contracts} "
                f"entry={trade_plan.entry_option_price:.2f}"
            )
            position = OptionPositionState(
                symbol=runtime_symbol,
                side=trade_plan.side,
                contracts=trade_plan.contracts,
                entry_time=latest_bar_time,
                entry_spot=float(latest["close"]),
                entry_option_price=trade_plan.entry_option_price,
                strike=trade_plan.strike,
                expiry=trade_plan.expiry,
                contract_symbol=trade_plan.contract_symbol,
                partial_exit_taken=False,
            )
        else:
            option_price = get_option_mark(latest.to_dict(), position.side, position.strike, latest_bar_time)
            option_return = (option_price / position.entry_option_price) - 1
            if (not position.partial_exit_taken) and option_return >= PARTIAL_PROFIT_TARGET:
                position.partial_exit_taken = True
                print(
                    f"✂️ {position.contract_symbol} 達成 partial target: {option_return:.2%}"
                )

            exit_reason = determine_exit_reason(position, latest.to_dict(), latest_bar_time)
            if exit_reason:
                print(
                    f"🚪 {position.contract_symbol} 觸發離場條件: {exit_reason}, "
                    f"mark={option_price:.2f}, pnl={(option_return):.2%}"
                )
                position = None

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    bootstrap_runtime()
    current_time = get_current_central_time()
    market_open, market_close = get_execution_window(current_time)
    if current_time < market_open or current_time > market_close:
        print_outside_execution_time(current_time, market_open, market_close)
        return

    await day_trade_options_agent(symbol=get_runtime_symbol())


if __name__ == "__main__":
    asyncio.run(main())