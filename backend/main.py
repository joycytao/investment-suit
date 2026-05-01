"""
Main entry point for the trading signal agent backend.
Flask app with integrated APScheduler for hourly signal generation.
"""
import os
import logging
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import (
    FLASK_HOST, FLASK_PORT, DEBUG, SCHEDULE_TIMEZONE, SCHEDULE_TIMES,
    SCHEDULE_WEEKDAYS, DATA_DIR, CACHE_DIR, SYMBOLS
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# Ensure data and cache directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# Initialize scheduler
scheduler = BackgroundScheduler(timezone=SCHEDULE_TIMEZONE)
scheduler_running = False

# Symbols file for persistence
SYMBOLS_FILE = os.path.join(DATA_DIR, "symbols.json")

def load_tracked_symbols():
    """Load tracked symbols from file, fallback to config defaults."""
    try:
        if os.path.exists(SYMBOLS_FILE):
            with open(SYMBOLS_FILE, 'r') as f:
                data = json.load(f)
                return data.get('symbols', SYMBOLS)
    except Exception as e:
        logger.warning("Failed to load symbols from file: %s", e)
    return SYMBOLS

def save_tracked_symbols(symbols):
    """Save tracked symbols to file."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SYMBOLS_FILE, 'w') as f:
            json.dump({'symbols': symbols}, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save symbols to file: %s", e)
        return False

# Load symbols at startup
CURRENT_SYMBOLS = load_tracked_symbols()


def analyze_and_generate_signals():
    """
    Main analysis job: fetch data, calculate indicators, generate signals.
    Will be called hourly by scheduler and on-demand via API.
    """
    try:
        logger.info("=" * 60)
        logger.info("Starting analysis run at %s", datetime.now(pytz.timezone(SCHEDULE_TIMEZONE)))
        logger.info("=" * 60)
        
        # Import here to avoid circular imports and allow lazy initialization
        from backend.data_fetcher import fetch_all_symbols
        from backend.indicators import calculate_all_indicators
        from backend.strategy import generate_signals
        from backend.signal_store import save_signals
        from backend.email_service import send_signal_report
        
        # Step 1: Fetch data
        logger.info("Step 1: Fetching stock data from AlphaVantage...")
        market_data = fetch_all_symbols(CURRENT_SYMBOLS)
        if not market_data:
            logger.warning("No market data retrieved. Skipping analysis.")
            return {"status": "error", "message": "No market data retrieved"}
        
        # Step 2: Calculate indicators
        logger.info("Step 2: Calculating technical indicators...")
        indicators_data = calculate_all_indicators(market_data)
        
        # Step 3: Generate trading signals
        logger.info("Step 3: Generating trading signals...")
        signals = generate_signals(market_data, indicators_data)
        
        # Step 4: Store signals
        logger.info("Step 4: Storing signals...")
        save_signals(signals)
        
        # Step 5: Send email report
        if signals:
            logger.info("Step 5: Sending email report...")
            send_signal_report(signals)
        else:
            logger.info("Step 5: No signals generated, skipping email.")
        
        logger.info("Analysis run completed successfully.")
        return {"status": "success", "signals_count": len(signals), "timestamp": datetime.now().isoformat()}
    
    except Exception as e:
        logger.error("Error during analysis run: %s", str(e), exc_info=True)
        return {"status": "error", "message": str(e)}


def schedule_analysis_jobs():
    """Set up hourly analysis jobs using APScheduler."""
    try:
        logger.info("Setting up scheduler with times: %s", SCHEDULE_TIMES)
        
        # Add jobs for each scheduled time
        for time_str in SCHEDULE_TIMES:
            hour, minute = map(int, time_str.split(":"))
            job_id = f"analyze_{time_str.replace(':', '')}"
            
            # Schedule job to run at specific time on weekdays
            scheduler.add_job(
                analyze_and_generate_signals,
                'cron',
                hour=hour,
                minute=minute,
                day_of_week=','.join(map(str, SCHEDULE_WEEKDAYS)),
                id=job_id,
                name=f"Analysis at {time_str} ET"
            )
            logger.info("Scheduled job '%s' at %s", job_id, time_str)
        
        scheduler.start()
        logger.info("Scheduler started successfully.")
        return True
    except Exception as e:
        logger.error("Failed to set up scheduler: %s", str(e), exc_info=True)
        return False


# ==================== API Routes ====================

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "trading-signal-agent",
        "timestamp": datetime.now().isoformat(),
        "scheduler_running": scheduler.running if scheduler else False
    }), 200


@app.route("/api/analyze", methods=["POST"])
def manual_analyze():
    """
    Manual trigger for analysis (on-demand).
    Useful for testing and one-off analysis runs.
    """
    logger.info("Manual analysis trigger received from %s", request.remote_addr)
    result = analyze_and_generate_signals()
    status_code = 200 if result["status"] == "success" else 500
    return jsonify(result), status_code


@app.route("/api/signals", methods=["GET"])
def get_signals():
    """
    Retrieve stored signals.
    Optional query params: 
    - symbol: filter by symbol (QQQ, SPY, DIA)
    - limit: max number of signals to return (default 100)
    """
    try:
        from backend.signal_store import load_signals
        
        symbol_filter = request.args.get("symbol", None)
        limit = int(request.args.get("limit", 100))
        
        all_signals = load_signals()
        
        # Filter by symbol if provided
        if symbol_filter:
            all_signals = [s for s in all_signals if s.get("symbol") == symbol_filter.upper()]
        
        # Return latest N signals
        signals = sorted(all_signals, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        
        return jsonify({
            "status": "success",
            "count": len(signals),
            "signals": signals,
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error("Error retrieving signals: %s", str(e), exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/signals/<symbol>", methods=["GET"])
def get_signals_by_symbol(symbol):
    """Retrieve signals for a specific symbol."""
    try:
        from backend.signal_store import load_signals
        
        all_signals = load_signals()
        symbol_signals = [s for s in all_signals if s.get("symbol") == symbol.upper()]
        
        return jsonify({
            "status": "success",
            "symbol": symbol.upper(),
            "count": len(symbol_signals),
            "signals": symbol_signals,
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error("Error retrieving signals for %s: %s", symbol, str(e), exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/scheduler/status", methods=["GET"])
def scheduler_status():
    """Check scheduler status and list active jobs."""
    if not scheduler:
        return jsonify({"status": "error", "message": "Scheduler not initialized"}), 500
    
    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time)
        })
    
    return jsonify({
        "status": "success",
        "scheduler_running": scheduler.running,
        "jobs_count": len(jobs_info),
        "jobs": jobs_info,
        "timestamp": datetime.now().isoformat()
    }), 200


# ==================== Symbol Management ====================

@app.route("/api/symbols", methods=["GET"])
def get_symbols():
    """Get currently tracked symbols."""
    return jsonify({
        "status": "success",
        "symbols": CURRENT_SYMBOLS,
        "count": len(CURRENT_SYMBOLS),
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/api/symbols", methods=["PUT"])
def update_symbols():
    """Update tracked symbols."""
    global CURRENT_SYMBOLS
    
    try:
        data = request.get_json()
        if not data or 'symbols' not in data:
            return jsonify({"status": "error", "message": "Missing 'symbols' field"}), 400
        
        symbols = data['symbols']
        
        # Validate input
        if not isinstance(symbols, list) or len(symbols) == 0:
            return jsonify({"status": "error", "message": "Symbols must be a non-empty list"}), 400
        
        # Validate each symbol is a string
        if not all(isinstance(s, str) and len(s) > 0 for s in symbols):
            return jsonify({"status": "error", "message": "All symbols must be non-empty strings"}), 400
        
        # Convert to uppercase and remove duplicates
        symbols = list(set(s.upper().strip() for s in symbols))
        
        # Save to file
        if not save_tracked_symbols(symbols):
            return jsonify({"status": "error", "message": "Failed to save symbols"}), 500
        
        # Update in-memory variable
        CURRENT_SYMBOLS = symbols
        logger.info("Updated tracked symbols: %s", symbols)
        
        return jsonify({
            "status": "success",
            "message": "Symbols updated successfully",
            "symbols": CURRENT_SYMBOLS,
            "count": len(CURRENT_SYMBOLS),
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error("Error updating symbols: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== LEAP Calls Management ====================

@app.route("/api/leap-candidates", methods=["GET"])
def get_leap_candidates():
    """Get latest LEAP candidates from last scan."""
    try:
        from backend.leap_screener import load_leap_candidates
        candidates = load_leap_candidates()
        return jsonify(candidates), 200
    except Exception as e:
        logger.error("Error loading LEAP candidates: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/leap-scan", methods=["POST"])
def trigger_leap_scan():
    """Manually trigger LEAP candidates scan with optional DTE range parameters."""
    try:
        from backend.leap_screener import scan_leap_candidates
        from flask import request
        
        # Get DTE range parameters from query string
        min_dte = request.args.get('minDTE', default=365, type=int)
        max_dte = request.args.get('maxDTE', default=720, type=int)
        
        logger.info("Manual LEAP scan triggered with DTE range: %d-%d days", min_dte, max_dte)
        result = scan_leap_candidates(min_dte=min_dte, max_dte=max_dte)
        return jsonify(result), 200
    except Exception as e:
        logger.error("Error during LEAP scan: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== Day Trading Screening ====================

@app.route("/api/day-trading-scan", methods=["POST"])
def trigger_day_trading_scan():
    """Manually trigger day trading candidate scan.
    
    Screens for:
    - Price: $1-$20
    - Float: < 5M shares
    - Relative Volume: > 5x
    - Change: Up
    - Excluding negative news sentiment (includes Positive, Neutral, or None)
    """
    try:
        from backend.day_trading_screener import scan_day_trading_candidates
        
        logger.info("Manual day trading scan triggered")
        result = scan_day_trading_candidates()
        return jsonify(result), 200
    except Exception as e:
        logger.error("Error during day trading scan: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== App Startup ====================

@app.before_request
def log_request():
    """Log incoming requests (optional)."""
    if request.method == "GET" and "/api/signals" in request.path:
        logger.debug("API request: %s %s", request.method, request.path)


if __name__ == "__main__":
    logger.info("Starting Trading Signal Agent Backend")
    logger.info("Configuration: HOST=%s, PORT=%s, DEBUG=%s", FLASK_HOST, FLASK_PORT, DEBUG)
    
    # Set up and start scheduler
    if schedule_analysis_jobs():
        scheduler_running = True
        logger.info("Scheduler initialized and started.")
    else:
        logger.warning("Scheduler failed to start. Manual API calls only.")
    
    # Start Flask app
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=DEBUG,
        use_reloader=False  # Disable reloader to prevent scheduler conflicts
    )
