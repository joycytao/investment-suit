"""
Configuration for trading signal agent
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "demo")
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# Trading Configuration
SYMBOLS = ["QQQ", "SPY", "DIA"]
INTERVAL = "daily"

# Technical Indicators Configuration
MA_PERIODS = {"MA20": 20, "MA200": 200}
BB_PERIOD = 20
BB_STDDEV = 2
RSI_PERIOD = 14

# Thresholds
RSI_OVERBOUGHT = 70  # Sell signal threshold
RSI_OVERSOLD = 30    # Buy signal threshold

# Options Configuration
TARGET_DTE = 30  # Days to expiration (30-35 range)
PROFIT_TARGET_PERCENT = 0.25  # 20-30% profit target
RISK_FREE_RATE = 0.05  # 5% annual risk-free rate for Black-Scholes
IMPLIED_VOL_PERCENTILE = 0.30  # Estimate IV as 30th percentile of historical vol

# Scheduler Configuration
SCHEDULE_TIMEZONE = "America/New_York"
SCHEDULE_TIMES = [
    "09:45",  # 15 min after market open (9:30 AM ET)
    "10:45",
    "11:45",
    "12:45",
    "13:45",
    "14:45",
    "15:45",  # 15 min before market close (4 PM ET)
]
SCHEDULE_WEEKDAYS = [0, 1, 2, 3, 4]  # Monday to Friday

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your-email@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-app-password")
EMAIL_FROM = os.getenv("EMAIL_FROM", "your-email@gmail.com")
EMAIL_TO = os.getenv("EMAIL_TO", "your-email@gmail.com").split(",")

# Storage Configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals_history.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
CACHE_TTL_SECONDS = 300  # 5 minute cache for API calls

# Flask Configuration
DEBUG = os.getenv("DEBUG", "False") == "True"
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
