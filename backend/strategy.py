"""
Trading strategy logic: generate signals based on RSI and Bollinger Bands.
"""
import logging
from datetime import datetime
import pytz
from backend.config import RSI_OVERBOUGHT, RSI_OVERSOLD, TARGET_DTE
from backend.options_pricing import (
    price_call_spread, price_naked_call,
    price_put_spread, price_naked_put
)

logger = logging.getLogger(__name__)


def is_at_resistance(current_price, bb_upper, bb_lower):
    """
    Check if price is near resistance (upper Bollinger Band).
    Resistance: price >= BB upper - 0.5% buffer
    """
    if not bb_upper:
        return False
    buffer = bb_upper * 0.005
    return current_price >= (bb_upper - buffer)


def is_at_support(current_price, bb_lower, bb_upper):
    """
    Check if price is near support (lower Bollinger Band).
    Support: price <= BB lower + 0.5% buffer
    """
    if not bb_lower:
        return False
    buffer = bb_lower * 0.005
    return current_price <= (bb_lower + buffer)


def generate_overbought_signal(symbol, current_price, indicators):
    """
    Generate overbought signal (RSI > 70 AND price at BB upper).
    Returns: signal dict or None
    """
    rsi = indicators.get("rsi")
    bb = indicators.get("bollinger_bands")
    price_history = indicators.get("price_history", [])
    
    if not (rsi and bb and rsi > RSI_OVERBOUGHT):
        return None
    
    if not is_at_resistance(current_price, bb.get("upper"), bb.get("lower")):
        return None
    
    # Generate option strategies
    call_spreads = price_call_spread(symbol, current_price, [p["close"] for p in price_history], TARGET_DTE)
    naked_call = price_naked_call(symbol, current_price, [p["close"] for p in price_history], TARGET_DTE)
    
    # Select best strategy by risk/reward
    strategies = call_spreads + [naked_call]
    best_strategy = max(
        strategies,
        key=lambda s: s.get("risk_reward_ratio", 0) if s.get("risk_reward_ratio") != "unlimited" else 0,
        default=None
    )
    
    return {
        "symbol": symbol,
        "signal_type": "overbought",
        "current_price": current_price,
        "rsi": rsi,
        "ma20": indicators.get("ma20"),
        "ma200": indicators.get("ma200"),
        "bb_upper": bb.get("upper"),
        "bb_middle": bb.get("middle"),
        "bb_lower": bb.get("lower"),
        "strategies": strategies,
        "recommended_strategy": best_strategy,
        "confidence": "high" if (rsi > 75 and is_at_resistance(current_price, bb.get("upper"), bb.get("lower"))) else "medium"
    }


def generate_oversold_signal(symbol, current_price, indicators):
    """
    Generate oversold signal (RSI < 30 AND price at BB lower).
    Returns: signal dict or None
    """
    rsi = indicators.get("rsi")
    bb = indicators.get("bollinger_bands")
    price_history = indicators.get("price_history", [])
    
    if not (rsi and bb and rsi < RSI_OVERSOLD):
        return None
    
    if not is_at_support(current_price, bb.get("lower"), bb.get("upper")):
        return None
    
    # Generate option strategies
    put_spreads = price_put_spread(symbol, current_price, [p["close"] for p in price_history], TARGET_DTE)
    naked_put = price_naked_put(symbol, current_price, [p["close"] for p in price_history], TARGET_DTE)
    
    # Select best strategy by risk/reward
    strategies = put_spreads + [naked_put]
    best_strategy = max(
        strategies,
        key=lambda s: s.get("risk_reward_ratio", 0) if s.get("risk_reward_ratio") != "unlimited" else 0,
        default=None
    )
    
    return {
        "symbol": symbol,
        "signal_type": "oversold",
        "current_price": current_price,
        "rsi": rsi,
        "ma20": indicators.get("ma20"),
        "ma200": indicators.get("ma200"),
        "bb_upper": bb.get("upper"),
        "bb_middle": bb.get("middle"),
        "bb_lower": bb.get("lower"),
        "strategies": strategies,
        "recommended_strategy": best_strategy,
        "confidence": "high" if (rsi < 25 and is_at_support(current_price, bb.get("lower"), bb.get("upper"))) else "medium"
    }


def generate_signals(market_data, indicators_data):
    """
    Generate trading signals for all symbols.
    market_data: dict {symbol: raw_api_data}
    indicators_data: dict {symbol: indicators}
    Returns: list of signal dicts
    """
    signals = []
    
    for symbol, indicators in indicators_data.items():
        try:
            # Get current price from market data
            if symbol not in market_data:
                logger.warning("No market data for %s, skipping signal generation", symbol)
                continue
            
            # Get current price (most recent close)
            if "Time Series (Daily)" not in market_data[symbol]:
                logger.warning("Invalid market data for %s", symbol)
                continue
            
            time_series = market_data[symbol]["Time Series (Daily)"]
            latest_date = list(time_series.keys())[0]
            current_price = float(time_series[latest_date]["4. close"])
            
            # Check for overbought condition
            overbought_signal = generate_overbought_signal(symbol, current_price, indicators)
            if overbought_signal:
                overbought_signal["timestamp"] = datetime.now(pytz.UTC).isoformat()
                signals.append(overbought_signal)
                logger.info("Generated OVERBOUGHT signal for %s: RSI=%.2f", symbol, indicators.get("rsi", 0))
            
            # Check for oversold condition
            oversold_signal = generate_oversold_signal(symbol, current_price, indicators)
            if oversold_signal:
                oversold_signal["timestamp"] = datetime.now(pytz.UTC).isoformat()
                signals.append(oversold_signal)
                logger.info("Generated OVERSOLD signal for %s: RSI=%.2f", symbol, indicators.get("rsi", 0))
        
        except Exception as e:
            logger.error("Error generating signals for %s: %s", symbol, str(e), exc_info=True)
    
    return signals
