"""
Signal storage: save and load signals from JSON file.
"""
import os
import json
import logging
from datetime import datetime
from backend.config import SIGNALS_FILE

logger = logging.getLogger(__name__)


def save_signals(signals):
    """
    Append new signals to signals_history.json.
    Keeps all historical signals for tracking.
    """
    if not signals:
        logger.info("No signals to save")
        return
    
    try:
        # Load existing signals
        existing_signals = load_signals()
        
        # Append new signals
        all_signals = existing_signals + signals
        
        # Write back to file
        os.makedirs(os.path.dirname(SIGNALS_FILE), exist_ok=True)
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(all_signals, f, indent=2)
        
        logger.info("Saved %d new signals (total: %d)", len(signals), len(all_signals))
    
    except Exception as e:
        logger.error("Failed to save signals: %s", str(e), exc_info=True)


def load_signals():
    """
    Load all historical signals from JSON file.
    Returns: list of signal dicts
    """
    if not os.path.exists(SIGNALS_FILE):
        return []
    
    try:
        with open(SIGNALS_FILE, 'r') as f:
            signals = json.load(f)
        logger.info("Loaded %d signals from file", len(signals))
        return signals
    
    except Exception as e:
        logger.error("Failed to load signals: %s", str(e), exc_info=True)
        return []


def get_latest_signal_by_symbol(symbol):
    """Get the most recent signal for a symbol."""
    signals = load_signals()
    symbol_signals = [s for s in signals if s.get("symbol") == symbol]
    
    if not symbol_signals:
        return None
    
    # Sort by timestamp, return most recent
    symbol_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return symbol_signals[0]


def get_signals_today():
    """Get all signals generated today."""
    signals = load_signals()
    today = datetime.now().date().isoformat()
    
    return [s for s in signals if s.get("timestamp", "").startswith(today)]


def clear_old_signals(days_old=90):
    """
    Remove signals older than specified days (for archival/cleanup).
    """
    from datetime import timedelta
    
    signals = load_signals()
    cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
    
    recent_signals = [s for s in signals if s.get("timestamp", "") >= cutoff_date]
    
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(recent_signals, f, indent=2)
        
        logger.info("Cleared %d old signals, keeping %d recent", 
                   len(signals) - len(recent_signals), len(recent_signals))
    
    except Exception as e:
        logger.error("Failed to clear old signals: %s", str(e), exc_info=True)
