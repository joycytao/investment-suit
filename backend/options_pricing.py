"""
Black-Scholes option pricing and Greeks calculation.
"""
import math
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta
from backend.config import RISK_FREE_RATE, IMPLIED_VOL_PERCENTILE

import logging
logger = logging.getLogger(__name__)


def calculate_historical_volatility(prices, period=20):
    """
    Calculate historical volatility from price series.
    prices: list of prices (float)
    period: lookback period (default 20 days)
    Returns: annualized volatility (0-1 scale, e.g., 0.25 = 25%)
    """
    if len(prices) < period + 1:
        return 0.20  # Default 20% if insufficient data
    
    prices = np.array(prices[-period:])
    # Calculate log returns
    returns = np.diff(np.log(prices))
    # Calculate daily volatility
    daily_vol = np.std(returns)
    # Annualize (252 trading days)
    annual_vol = daily_vol * math.sqrt(252)
    
    return round(annual_vol, 4)


def estimate_implied_volatility(historical_vol):
    """
    Estimate implied volatility from historical volatility.
    In production, would fetch real IV from options market.
    For now, use percentile of historical vol.
    """
    # Simple estimate: use historical vol scaled by percentile
    # Could also use: IV ≈ 1.2 * HV (market tends to price higher than realized)
    return round(historical_vol * 1.2, 4)


def black_scholes_call(S, K, T, r, sigma):
    """
    Black-Scholes formula for European call option.
    S: current stock price
    K: strike price
    T: time to expiration (years)
    r: risk-free rate (annual)
    sigma: volatility (annual)
    Returns: call premium (float)
    """
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)  # Intrinsic value
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    call_price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return round(max(call_price, 0), 2)


def black_scholes_put(S, K, T, r, sigma):
    """
    Black-Scholes formula for European put option.
    S: current stock price
    K: strike price
    T: time to expiration (years)
    r: risk-free rate (annual)
    sigma: volatility (annual)
    Returns: put premium (float)
    """
    if T <= 0 or sigma <= 0:
        return max(K - S, 0)  # Intrinsic value
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    put_price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return round(max(put_price, 0), 2)


def calculate_call_greek_delta(S, K, T, r, sigma):
    """Calculate delta for call option."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return round(norm.cdf(d1), 4)


def calculate_put_greek_delta(S, K, T, r, sigma):
    """Calculate delta for put option."""
    if T <= 0 or sigma <= 0:
        return 0.0 if S > K else -1.0
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return round(norm.cdf(d1) - 1, 4)


def calculate_call_greek_theta(S, K, T, r, sigma):
    """
    Calculate theta (daily decay) for call option.
    Returns: daily theta (1/365 of annual theta)
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    # Annual theta for call
    theta_annual = (
        -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm.cdf(d2)
    )
    
    # Daily theta (divide by 365)
    return round(theta_annual / 365, 4)


def calculate_put_greek_theta(S, K, T, r, sigma):
    """
    Calculate theta (daily decay) for put option.
    Returns: daily theta (1/365 of annual theta)
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    # Annual theta for put
    theta_annual = (
        -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm.cdf(-d2)
    )
    
    # Daily theta (divide by 365)
    return round(theta_annual / 365, 4)


def generate_option_strikes(current_price, direction="call", num_strikes=3):
    """
    Generate reasonable strike prices around current price.
    direction: 'call' (above current) or 'put' (below current)
    num_strikes: number of strikes to generate (default 3)
    Returns: list of strike prices
    """
    strikes = []
    
    if direction == "call":
        # For calls: 0.5%, 1%, 1.5% above current
        for i in range(1, num_strikes + 1):
            strike = current_price * (1 + 0.005 * i)
            strikes.append(round(strike, 2))
    else:  # put
        # For puts: 0.5%, 1%, 1.5% below current
        for i in range(1, num_strikes + 1):
            strike = current_price * (1 - 0.005 * i)
            strikes.append(round(strike, 2))
    
    return strikes


def calculate_strategy_profit(premium_collected, premium_paid, max_loss):
    """
    Calculate profit metrics for option strategies.
    Returns: dict with profit/loss scenarios
    """
    max_profit = premium_collected - premium_paid
    profit_percentage = (max_profit / max_loss * 100) if max_loss > 0 else 0
    
    return {
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "profit_percentage": round(profit_percentage, 2),
        "risk_reward_ratio": round(max_profit / max_loss, 2) if max_loss > 0 else 0
    }


def price_call_spread(symbol, current_price, price_history, target_dte=30):
    """
    Price a call credit spread (sell higher strike, buy lower strike).
    Used for overbought signals (RSI > 70).
    Returns: list of strategy scenarios
    """
    T = target_dte / 365  # Convert days to years
    sigma = estimate_implied_volatility(calculate_historical_volatility(price_history, 20))
    r = RISK_FREE_RATE
    
    strategies = []
    
    # Generate strikes: sell at-the-money or slightly out-of-money, buy further out
    sell_strikes = [round(current_price, 2), round(current_price * 1.005, 2)]
    
    for sell_strike in sell_strikes:
        buy_strike = round(sell_strike * 1.01, 2)  # 1% higher strike to buy
        
        sell_premium = black_scholes_call(current_price, sell_strike, T, r, sigma)
        buy_premium = black_scholes_call(current_price, buy_strike, T, r, sigma)
        net_premium = sell_premium - buy_premium
        max_loss = buy_strike - sell_strike - net_premium
        
        if net_premium > 0:
            profit_calc = calculate_strategy_profit(sell_premium, buy_premium, max_loss)
            
            strategies.append({
                "type": "call_credit_spread",
                "symbol": symbol,
                "direction": "bearish",
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "sell_premium": sell_premium,
                "buy_premium": buy_premium,
                "net_premium_collected": net_premium,
                "max_profit": profit_calc["max_profit"],
                "max_loss": profit_calc["max_loss"],
                "profit_percentage": profit_calc["profit_percentage"],
                "risk_reward_ratio": profit_calc["risk_reward_ratio"],
                "dte": target_dte,
                "iv": sigma
            })
    
    return strategies


def price_naked_call(symbol, current_price, price_history, target_dte=30):
    """
    Price a naked call (sell call only).
    Used for overbought signals (RSI > 70).
    Returns: strategy dict
    """
    T = target_dte / 365
    sigma = estimate_implied_volatility(calculate_historical_volatility(price_history, 20))
    r = RISK_FREE_RATE
    
    # Sell strike slightly out-of-money
    sell_strike = round(current_price * 1.01, 2)
    premium = black_scholes_call(current_price, sell_strike, T, r, sigma)
    max_loss = float('inf')  # Unlimited risk
    
    return {
        "type": "naked_call",
        "symbol": symbol,
        "direction": "bearish",
        "strike": sell_strike,
        "premium_collected": premium,
        "max_profit": round(premium, 2),
        "max_loss": "unlimited",
        "max_profit_percentage": 100.0,
        "dte": target_dte,
        "iv": sigma,
        "risk_level": "high"
    }


def price_put_spread(symbol, current_price, price_history, target_dte=30):
    """
    Price a put credit spread (sell lower strike, buy higher strike).
    Used for oversold signals (RSI < 30).
    Returns: list of strategy scenarios
    """
    T = target_dte / 365
    sigma = estimate_implied_volatility(calculate_historical_volatility(price_history, 20))
    r = RISK_FREE_RATE
    
    strategies = []
    
    # Generate strikes: sell at-the-money or slightly out-of-money, buy further out
    sell_strikes = [round(current_price, 2), round(current_price * 0.995, 2)]
    
    for sell_strike in sell_strikes:
        buy_strike = round(sell_strike * 0.99, 2)  # 1% lower strike to buy
        
        sell_premium = black_scholes_put(current_price, sell_strike, T, r, sigma)
        buy_premium = black_scholes_put(current_price, buy_strike, T, r, sigma)
        net_premium = sell_premium - buy_premium
        max_loss = sell_strike - buy_strike - net_premium
        
        if net_premium > 0:
            profit_calc = calculate_strategy_profit(sell_premium, buy_premium, max_loss)
            
            strategies.append({
                "type": "put_credit_spread",
                "symbol": symbol,
                "direction": "bullish",
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "sell_premium": sell_premium,
                "buy_premium": buy_premium,
                "net_premium_collected": net_premium,
                "max_profit": profit_calc["max_profit"],
                "max_loss": profit_calc["max_loss"],
                "profit_percentage": profit_calc["profit_percentage"],
                "risk_reward_ratio": profit_calc["risk_reward_ratio"],
                "dte": target_dte,
                "iv": sigma
            })
    
    return strategies


def price_naked_put(symbol, current_price, price_history, target_dte=30):
    """
    Price a naked put (sell put only).
    Used for oversold signals (RSI < 30).
    Returns: strategy dict
    """
    T = target_dte / 365
    sigma = estimate_implied_volatility(calculate_historical_volatility(price_history, 20))
    r = RISK_FREE_RATE
    
    # Sell strike slightly out-of-money
    sell_strike = round(current_price * 0.99, 2)
    premium = black_scholes_put(current_price, sell_strike, T, r, sigma)
    
    return {
        "type": "naked_put",
        "symbol": symbol,
        "direction": "bullish",
        "strike": sell_strike,
        "premium_collected": premium,
        "max_profit": round(premium, 2),
        "max_loss": round(sell_strike, 2),  # Can lose down to zero
        "max_profit_percentage": 100.0,
        "dte": target_dte,
        "iv": sigma,
        "risk_level": "high"
    }
