"""
Data fetching from AlphaVantage API with caching.
"""
import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from backend.config import (
    ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_BASE_URL, SYMBOLS, INTERVAL,
    CACHE_DIR, CACHE_TTL_SECONDS
)

logger = logging.getLogger(__name__)


def get_cache_path(symbol):
    """Get cache file path for a symbol."""
    return os.path.join(CACHE_DIR, f"{symbol}_{INTERVAL}.json")


def is_cache_valid(symbol):
    """Check if cached data is still valid."""
    cache_path = get_cache_path(symbol)
    if not os.path.exists(cache_path):
        return False
    
    file_age = time.time() - os.path.getmtime(cache_path)
    return file_age < CACHE_TTL_SECONDS


def load_from_cache(symbol):
    """Load data from cache."""
    cache_path = get_cache_path(symbol)
    try:
        with open(cache_path, 'r') as f:
            data = json.load(f)
            logger.info("Loaded %s from cache", symbol)
            return data
    except Exception as e:
        logger.warning("Failed to load cache for %s: %s", symbol, str(e))
        return None


def save_to_cache(symbol, data):
    """Save data to cache."""
    cache_path = get_cache_path(symbol)
    try:
        with open(cache_path, 'w') as f:
            json.dump(data, f)
            logger.info("Cached data for %s", symbol)
    except Exception as e:
        logger.warning("Failed to cache data for %s: %s", symbol, str(e))


def fetch_daily_data(symbol, use_cache=True):
    """
    Fetch daily OHLC data from AlphaVantage API.
    Returns dict with structure: {symbol: data, metadata: ..., time_series: {...}}
    """
    # Check cache first
    if use_cache and is_cache_valid(symbol):
        return load_from_cache(symbol)
    
    logger.info("Fetching daily data for %s from AlphaVantage", symbol)
    
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY,
        "outputsize": "full"  # Get full 20+ years of data
    }
    
    try:
        response = requests.get(ALPHAVANTAGE_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for API errors
        if "Error Message" in data:
            logger.error("AlphaVantage API error for %s: %s", symbol, data["Error Message"])
            return None
        
        if "Note" in data:
            logger.warning("AlphaVantage rate limit warning: %s", data["Note"])
            return None
        
        if "Time Series (Daily)" not in data:
            logger.error("Unexpected response format for %s", symbol)
            logger.debug("Response: %s", data)
            return None
        
        # Cache the data
        save_to_cache(symbol, data)
        return data
    
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch data for %s: %s", symbol, str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error fetching data for %s: %s", symbol, str(e))
        return None


def fetch_all_symbols(symbols=None):
    """
    Fetch daily data for all configured symbols.
    Args:
        symbols: Optional list of symbols. If None, uses default from config.
    Returns dict: {symbol: data}
    """
    if symbols is None:
        symbols = SYMBOLS
    
    all_data = {}
    
    for symbol in symbols:
        data = fetch_daily_data(symbol)
        if data:
            all_data[symbol] = data
            # Respect rate limit: 5 requests per minute
            time.sleep(0.2)  # 200ms between requests (allows ~5 req/sec bursts)
        else:
            logger.warning("Failed to fetch data for %s", symbol)
    
    return all_data


def parse_time_series(data):
    """
    Extract and parse time series data from AlphaVantage response.
    Returns list of dicts: [{'date': '2024-01-01', 'open': ..., 'high': ..., 'low': ..., 'close': ...}, ...]
    Sorted by date (newest first).
    """
    if not data or "Time Series (Daily)" not in data:
        return []
    
    time_series = data["Time Series (Daily)"]
    parsed = []
    
    for date_str, ohlc in time_series.items():
        try:
            parsed.append({
                "date": date_str,
                "open": float(ohlc["1. open"]),
                "high": float(ohlc["2. high"]),
                "low": float(ohlc["3. low"]),
                "close": float(ohlc["4. close"]),
                "volume": int(ohlc["5. volume"])
            })
        except (KeyError, ValueError) as e:
            logger.warning("Failed to parse OHLC for %s: %s", date_str, str(e))
    
    # Sort by date descending (newest first)
    parsed.sort(key=lambda x: x["date"], reverse=True)
    return parsed
