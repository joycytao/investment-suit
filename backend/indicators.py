"""
Technical indicators calculation: MA20, MA200, Bollinger Bands, RSI.
"""
import logging
import numpy as np
from backend.config import MA_PERIODS, BB_PERIOD, BB_STDDEV, RSI_PERIOD
from backend.data_fetcher import parse_time_series

logger = logging.getLogger(__name__)


def calculate_ma(prices, period):
    """
    Calculate simple moving average.
    prices: list of prices (float)
    period: window size (int)
    Returns: list of MA values or None if not enough data
    """
    if len(prices) < period:
        return None
    
    prices_array = np.array(prices[:period])
    return np.mean(prices_array)


def calculate_bollinger_bands(prices, period=20, stddev=2):
    """
    Calculate Bollinger Bands.
    prices: list of prices (float)
    period: window size (default 20)
    stddev: number of standard deviations (default 2)
    Returns: dict with 'middle', 'upper', 'lower' or None if insufficient data
    """
    if len(prices) < period:
        return None
    
    prices_array = np.array(prices[:period])
    middle = np.mean(prices_array)
    std = np.std(prices_array)
    
    return {
        "middle": round(middle, 4),
        "upper": round(middle + (stddev * std), 4),
        "lower": round(middle - (stddev * std), 4),
        "std_dev": round(std, 4)
    }


def calculate_rsi(prices, period=14):
    """
    Calculate Relative Strength Index (RSI).
    prices: list of prices (float), newest first
    period: window size (default 14)
    Returns: RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    # Reverse for easier indexing (oldest to newest)
    prices = list(reversed(prices))
    
    # Calculate gains and losses
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    # Calculate average gains and losses
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    # Calculate RS and RSI
    if avg_loss == 0:
        rsi = 100 if avg_gain > 0 else 50
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def calculate_indicators_for_symbol(raw_data):
    """
    Calculate all indicators for a single symbol.
    raw_data: AlphaVantage response dict
    Returns: dict with 'symbol', 'current_price', 'ma20', 'ma200', 'bollinger_bands', 'rsi', 'date'
    """
    if not raw_data or "Time Series (Daily)" not in raw_data:
        return None
    
    # Parse time series
    time_series = parse_time_series(raw_data)
    if not time_series:
        return None
    
    # Extract close prices (newest first)
    prices = [d["close"] for d in time_series]
    
    # Calculate indicators
    ma20 = calculate_ma(prices, MA_PERIODS["MA20"])
    ma200 = calculate_ma(prices, MA_PERIODS["MA200"])
    bb = calculate_bollinger_bands(prices, BB_PERIOD, BB_STDDEV)
    rsi = calculate_rsi(prices, RSI_PERIOD)
    
    current_price = prices[0]
    current_date = time_series[0]["date"]
    
    return {
        "date": current_date,
        "current_price": round(current_price, 2),
        "ma20": round(ma20, 2) if ma20 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "bollinger_bands": bb,
        "rsi": rsi,
        "price_history": time_series[:200]  # Keep 200 days for reference
    }


def calculate_all_indicators(market_data):
    """
    Calculate indicators for all symbols.
    market_data: dict {symbol: raw_api_data}
    Returns: dict {symbol: indicators}
    """
    indicators = {}
    
    for symbol, raw_data in market_data.items():
        logger.info("Calculating indicators for %s", symbol)
        try:
            indicator_data = calculate_indicators_for_symbol(raw_data)
            if indicator_data:
                indicators[symbol] = indicator_data
                logger.info("Indicators calculated for %s: RSI=%.2f, MA20=%.2f", 
                           symbol, indicator_data.get("rsi", 0), indicator_data.get("ma20", 0))
            else:
                logger.warning("Failed to calculate indicators for %s", symbol)
        except Exception as e:
            logger.error("Error calculating indicators for %s: %s", symbol, str(e), exc_info=True)
    
    return indicators
