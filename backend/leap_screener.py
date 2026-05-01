"""
LEAP Calls screener module.
Finds S&P 500 / Nasdaq 100 stocks meeting growth criteria, 
then identifies sweet spot LEAP call options.
"""
import logging
import json
import os
import yfinance as yf
import pandas as pd
from datetime import datetime
import time

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

# S&P 500 and Nasdaq 100 tickers (top movers by market cap for quick testing)
SP500_SAMPLE = [
    "MSFT", "AAPL", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK.B", "JNJ", "V",
    "WMT", "MA", "PG", "COST", "AVGO", "NVO", "LLY", "NFLX", "ASML", "CRM",
    "SCHW", "AXP", "QCOM", "AMD", "MU", "INTU", "GS", "CMG", "PYPL", "SNPS"
]

NASDAQ100_SAMPLE = [
    "QQQ", "MSFT", "AAPL", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AMD",
    "ADBE", "INTC", "MRNA", "ABNB", "CRWD", "MDB", "SPLK", "DDOG", "NET", "SNOW"
]

LEAP_CANDIDATES_FILE = os.path.join(DATA_DIR, "leap_candidates.json")


def get_sp500_nasdaq100_tickers():
    """Get combined list of S&P 500 and Nasdaq 100 tickers."""
    return list(set(SP500_SAMPLE + NASDAQ100_SAMPLE))


def get_stock_fundamentals(ticker_symbol):
    """
    Get fundamental data for a stock from yfinance.
    Returns dict or None if data unavailable.
    """
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        # Extract required fields
        revenue_growth = info.get('revenueGrowth')
        profit_margin = info.get('profitMargins')
        target_price = info.get('targetMeanPrice')
        current_price = info.get('currentPrice')
        iv_rank = info.get('impliedVolatilityRank')
        
        # Try fallback: use latest price if currentPrice not available
        if current_price is None:
            hist = stock.history(period="1d")
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
        
        return {
            'ticker': ticker_symbol,
            'revenue_growth': revenue_growth,
            'profit_margin': profit_margin,
            'target_price': target_price,
            'current_price': current_price,
            'iv_rank': iv_rank
        }
    except Exception as e:
        logger.debug("Failed to get fundamentals for %s: %s", ticker_symbol, e)
        return None


def filter_by_fundamentals(tickers, limit=20):
    """
    Filter tickers by fundamental criteria:
    - Revenue Growth (YoY) > 15%
    - Net Margin > 10%
    - (Current Price / Analyst Target Price) < 0.8
    - IV Rank < 30%
    
    Returns list of filtered ticker dicts, up to limit.
    """
    candidates = []
    
    logger.info("Screening %d tickers for fundamental criteria...", len(tickers))
    
    for ticker in tickers:
        try:
            fundamentals = get_stock_fundamentals(ticker)
            if fundamentals is None:
                continue
            
            revenue_growth = fundamentals.get('revenue_growth') or 0
            profit_margin = fundamentals.get('profit_margin') or 0
            current_price = fundamentals.get('current_price')
            target_price = fundamentals.get('target_price')
            iv_rank = fundamentals.get('iv_rank')
            
            # Check criteria
            revenue_ok = revenue_growth > 0.15
            margin_ok = profit_margin > 0.10
            
            price_ratio_ok = False
            if current_price and target_price and target_price > 0:
                price_ratio = current_price / target_price
                price_ratio_ok = price_ratio < 0.8
            
            iv_ok = (iv_rank is None) or (iv_rank < 0.30)  # None = assume OK
            
            # All criteria must pass
            if revenue_ok and margin_ok and price_ratio_ok and iv_ok:
                candidates.append({
                    'ticker': ticker,
                    'revenue_growth': revenue_growth,
                    'profit_margin': profit_margin,
                    'current_price': current_price,
                    'target_price': target_price,
                    'iv_rank': iv_rank,
                    'upside_potential': (target_price / current_price - 1) if current_price else 0
                })
                logger.info("✓ Qualified: %s (RG: %.1f%%, PM: %.1f%%)", 
                           ticker, revenue_growth * 100, profit_margin * 100)
            
            # Rate limit yfinance calls
            time.sleep(0.2)
            
            if len(candidates) >= limit:
                break
                
        except Exception as e:
            logger.debug("Error screening %s: %s", ticker, e)
            continue
    
    logger.info("Found %d qualified candidates", len(candidates))
    return candidates[:limit]


def find_leap_sweet_spot(ticker_symbol, min_dte=365, max_dte=720):
    """
    Find BEST sweet spot LEAP call options for each expiration using Greeks-based criteria:
    
    REQUIREMENTS:
    1. Only consider expirations within min_dte to max_dte days out
    2. For each qualifying expiration: show best option
    3. Delta 0.75-0.85 (around 0.8, ITM with high assignment probability)
    4. Lowest Theta/Delta ratio (best time decay efficiency)
    5. Cost < 40% of buying 100 shares (capital efficiency)
    
    Returns list of best options per expiration, sorted by Theta/Delta ratio.
    """
    try:
        from backend.options_pricing import (
            calculate_historical_volatility, estimate_implied_volatility,
            calculate_call_greek_delta, calculate_call_greek_theta
        )
        from backend.config import RISK_FREE_RATE
        
        stock = yf.Ticker(ticker_symbol)
        
        # Get price history for volatility calculation
        hist = stock.history(period="252d")  # 1 year of data for vol
        if len(hist) == 0:
            logger.warning("No price data for %s", ticker_symbol)
            return None
        
        prices = hist['Close'].tolist()
        current_price = prices[-1]
        
        # Get ALL expirations
        try:
            all_expirations = stock.options
        except Exception as e:
            logger.warning("No options data for %s: %s", ticker_symbol, e)
            return None
        
        if not all_expirations:
            return None
        
        # Calculate days to expiration and FILTER for min_dte to max_dte days
        today = pd.to_datetime(datetime.now().date())
        exp_list = []
        for exp_date_str in all_expirations:
            try:
                exp_date = pd.to_datetime(exp_date_str)
                days_out = (exp_date - today).days
                # Only consider expirations within specified range
                if min_dte <= days_out <= max_dte:
                    exp_list.append((exp_date_str, days_out))
            except:
                pass
        
        if not exp_list:
            logger.debug("No expirations in %d-%d day range for %s", min_dte, max_dte, ticker_symbol)
            return None
        
        # Sort by days out (furthest first)
        exp_list.sort(key=lambda x: x[1], reverse=True)
        logger.info("Found %d expirations in %d-%d day range for %s", len(exp_list), min_dte, max_dte, ticker_symbol)
        
        # Calculate volatility once for all options
        historical_vol = calculate_historical_volatility(prices, period=252)
        implied_vol = estimate_implied_volatility(historical_vol)
        r = RISK_FREE_RATE
        
        # Collect best option FROM EACH qualifying expiration
        all_sweet_spots = []
        stock_100_cost = current_price * 100
        
        for target_date, days_to_exp in exp_list:
            try:
                opt_chain = stock.option_chain(target_date).calls
            except Exception as e:
                logger.debug("Failed to get options chain for %s on %s: %s", ticker_symbol, target_date, e)
                continue
            
            if opt_chain is None or len(opt_chain) == 0:
                continue
            
            # Parse expiration date and calculate T (time to expiration in years)
            T = max(days_to_exp / 365, 0.01)
            
            # Calculate Greeks for each option on this expiration
            opt_chain = opt_chain.copy()
            opt_chain['delta'] = opt_chain['strike'].apply(
                lambda K: calculate_call_greek_delta(current_price, K, T, r, implied_vol)
            )
            opt_chain['theta'] = opt_chain['strike'].apply(
                lambda K: calculate_call_greek_theta(current_price, K, T, r, implied_vol)
            )
            
            # Filter for Delta in range 0.75-0.85 (around 0.8)
            delta_filtered = opt_chain[
                (opt_chain['delta'] >= 0.75) & 
                (opt_chain['delta'] <= 0.85) &
                (opt_chain['openInterest'] > 50) &
                (opt_chain['lastPrice'] > 0)
            ].copy()
            
            if len(delta_filtered) == 0:
                logger.debug("No Delta 0.75-0.85 options for %s on %s", ticker_symbol, target_date)
                continue
            
            # Calculate Theta/Delta ratio
            delta_filtered['theta_delta_ratio'] = delta_filtered.apply(
                lambda row: abs(row['theta'] / row['delta']) if row['delta'] != 0 else float('inf'),
                axis=1
            )
            
            # Cost efficiency check: cost < 40% of 100 shares
            delta_filtered['cost_efficient'] = delta_filtered['lastPrice'] < (stock_100_cost * 0.4)
            
            # Filter for cost-efficient options
            cost_filtered = delta_filtered[delta_filtered['cost_efficient']]
            
            if len(cost_filtered) == 0:
                logger.debug("No cost-efficient options (<40%%) for %s on %s", ticker_symbol, target_date)
                continue
            
            # Get the BEST from this expiration (lowest Theta/Delta)
            best_from_exp = cost_filtered.nsmallest(1, 'theta_delta_ratio')
            
            if len(best_from_exp) > 0:
                # Add expiration info
                best_from_exp = best_from_exp.copy()
                best_from_exp['expiration_date'] = target_date
                best_from_exp['dte'] = days_to_exp
                all_sweet_spots.append(best_from_exp)
                logger.debug("✓ Best option for %s on %s: Strike %.1f, Theta/Delta: %.4f, Cost: $%.2f", 
                           ticker_symbol, target_date, best_from_exp.iloc[0]['strike'], 
                           best_from_exp.iloc[0]['theta_delta_ratio'], best_from_exp.iloc[0]['lastPrice'])
        
        if not all_sweet_spots:
            logger.debug("No cost-efficient sweet spots found for %s in 365-720 day range", ticker_symbol)
            return None
        
        # Combine all expirations (one best per expiration)
        combined = pd.concat(all_sweet_spots, ignore_index=True)
        
        # Sort by Theta/Delta ratio overall (best first)
        combined = combined.sort_values('theta_delta_ratio')
        
        # Format output
        result = combined[[
            'strike', 'lastPrice', 'delta', 'theta', 'theta_delta_ratio', 
            'openInterest', 'bid', 'ask', 'expiration_date', 'dte'
        ]].to_dict('records')
        
        logger.info("✓ Found %d best sweet spots for %s (1 best per expiration in 365-720 day range)", 
                   len(result), ticker_symbol)
        
        return result
    
    except Exception as e:
        logger.error("Error finding sweet spot for %s: %s", ticker_symbol, e)
        import traceback
        logger.error(traceback.format_exc())
        return None


def scan_leap_candidates(min_dte=365, max_dte=720):
    """
    Main scanning function:
    1. Get S&P 500 + Nasdaq 100 stocks
    2. Filter by fundamentals (top 20)
    3. Find LEAP sweet spots for each
    4. Save results to JSON file
    
    Args:
        min_dte: Minimum days to expiration (default: 365)
        max_dte: Maximum days to expiration (default: 720)
    
    Returns list of candidates with sweet spots.
    """
    logger.info("=" * 60)
    logger.info("Starting LEAP Calls screening scan (DTE range: %d-%d days)", min_dte, max_dte)
    logger.info("=" * 60)
    
    # Step 1: Get tickers
    all_tickers = get_sp500_nasdaq100_tickers()
    logger.info("Screening from %d tickers", len(all_tickers))
    
    # Step 2: Filter by fundamentals
    candidates = filter_by_fundamentals(all_tickers, limit=20)
    
    if not candidates:
        logger.warning("No candidates met fundamental criteria")
        return {"status": "success", "candidates": [], "count": 0, "timestamp": datetime.now().isoformat()}
    
    # Step 3: Find LEAP sweet spots for each candidate
    results = []
    for candidate in candidates:
        ticker = candidate['ticker']
        logger.info("Finding LEAP sweet spots for %s...", ticker)
        
        sweet_spots = find_leap_sweet_spot(ticker, min_dte=min_dte, max_dte=max_dte)
        
        if sweet_spots is not None and len(sweet_spots) > 0:
            # sweet_spots is already a list of dicts from the updated function
            candidate['leap_sweet_spots'] = sweet_spots
            results.append(candidate)
            logger.info("✓ Found %d sweet spots for %s", len(sweet_spots), ticker)
        else:
            logger.info("✗ No sweet spots for %s", ticker)
    
    # Step 4: Save results
    scan_result = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "candidates": results,
        "count": len(results)
    }
    
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LEAP_CANDIDATES_FILE, 'w') as f:
            json.dump(scan_result, f, indent=2)
        logger.info("Saved %d LEAP candidates to %s", len(results), LEAP_CANDIDATES_FILE)
    except Exception as e:
        logger.error("Failed to save LEAP candidates: %s", e)
    
    logger.info("LEAP scan complete. Found %d candidates with sweet spots", len(results))
    logger.info("=" * 60)
    
    return scan_result


def load_leap_candidates():
    """Load previously saved LEAP candidates from JSON file."""
    try:
        if os.path.exists(LEAP_CANDIDATES_FILE):
            with open(LEAP_CANDIDATES_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error("Failed to load LEAP candidates: %s", e)
    
    return {"status": "success", "candidates": [], "count": 0}
