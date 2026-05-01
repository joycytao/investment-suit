"""
Day Trading screener module.
Screens for high-demand, low-supply stocks with positive news sentiment.
Uses FinViz for screener data and Gemini for news sentiment analysis.
"""
import logging
import yfinance as yf
from datetime import datetime, timedelta
from finvizfinance.screener.overview import Overview
from google import genai
import os

logger = logging.getLogger(__name__)

def get_morning_scan():
    """
    Screen for high-demand, low-supply stocks.
    Filters:
    - Price: $1-$20
    - Float: < 5M shares
    - Relative Volume: > 5x
    - Change: Up
    
    Returns list of tickers matching criteria
    """
    try:
        logger.info("Screening for high-demand, low-supply stocks...")
        
        filters_dict = {
            'Price': '$1 to $20',
            'Float': 'Under 5M',
            'Relative Volume': 'Over 5',
            'Change': 'Up'
        }
        
        foverview = Overview()
        foverview.set_filter(filters_dict=filters_dict)
        screener_df = foverview.screener_view()
        
        if screener_df.empty:
            logger.warning("FinViz screener returned no results")
            return []
        
        ticker_list = screener_df['Ticker'].tolist()
        logger.info(f"Found {len(ticker_list)} stocks matching criteria")
        
        return ticker_list[:20]  # Limit to first 20 to avoid API overload
    
    except Exception as e:
        logger.error(f"Error screening with FinViz: {str(e)}")
        return []


def get_stock_info(ticker):
    """
    Get stock information including price and change.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        return {
            'price': info.get('currentPrice', 0),
            'change': info.get('regularMarketChangePercent', 0),
            'float': info.get('floatShares', 0),
        }
    except Exception as e:
        logger.error(f"Error getting info for {ticker}: {str(e)}")
        return None


def get_stock_news(ticker):
    """
    Get today's news for a stock using yfinance.
    
    Returns list of news headlines and the full news data
    """
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        
        if not news:
            logger.debug(f"No news found for {ticker}")
            return [], []
        
        # Filter news from today (last 24 hours)
        today = datetime.now() - timedelta(days=1)
        today_news = []
        
        for item in news:
            try:
                # Get publish date from the news item
                pub_date = item.get('providerPublishTime')
                if isinstance(pub_date, int):
                    pub_datetime = datetime.fromtimestamp(pub_date)
                    if pub_datetime > today:
                        today_news.append(item)
            except:
                pass
        
        logger.info(f"Found {len(today_news)} news articles for {ticker} from today")
        
        headlines = [item.get('title', '') for item in today_news[:5]]
        
        return headlines, today_news
    
    except Exception as e:
        logger.error(f"Error getting news for {ticker}: {str(e)}")
        return [], []


def analyze_news_sentiment(ticker, headlines, news_items):
    """
    Use Gemini API to analyze sentiment of news headlines.
    Returns sentiment classification and confidence.
    Defaults to Neutral if no headlines or API unavailable.
    """
    if not headlines:
        return "Neutral", 0
    
    try:
        from backend.config import GEMINI_API_KEY
        
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set, skipping sentiment analysis")
            return "Unknown", 0
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Create prompt for sentiment analysis
        news_text = "\n".join(headlines[:3])  # Use top 3 headlines
        
        prompt = f"""Analyze the sentiment of these news headlines for stock ticker {ticker}.
        
Headlines:
{news_text}

Provide a brief sentiment analysis. Respond with ONLY one of these sentiments followed by a confidence score 0-100:
- Positive
- Neutral  
- Negative

Format: [SENTIMENT] [SCORE]
Example: Positive 85"""

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            generation_config={
                "temperature": 0.3,  # Lower temperature for more consistent results
                "max_output_tokens": 50,
            }
        )
        
        result_text = response.text.strip()
        logger.info(f"Gemini sentiment for {ticker}: {result_text}")
        
        # Parse response
        parts = result_text.split()
        if len(parts) >= 2:
            sentiment = parts[0]
            try:
                confidence = int(parts[1])
            except:
                confidence = 50
        else:
            sentiment = "Neutral"
            confidence = 50
        
        return sentiment, confidence
    
    except Exception as e:
        logger.error(f"Error analyzing sentiment for {ticker}: {str(e)}")
        return "Neutral", 0


def get_relative_volume(ticker):
    """
    Get relative volume (current volume vs average).
    Uses yfinance historical data.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Get last 20 days of data
        hist = stock.history(period="1mo")
        
        if hist.empty or len(hist) < 5:
            return 0
        
        # Get average volume over last 20 days (excluding today)
        avg_volume = hist['Volume'][:-1].tail(20).mean()
        
        # Get today's volume
        today_volume = hist['Volume'].iloc[-1]
        
        if avg_volume == 0:
            return 0
        
        relative_vol = today_volume / avg_volume
        logger.info(f"{ticker}: Relative volume = {relative_vol:.2f}x")
        
        return relative_vol
    
    except Exception as e:
        logger.error(f"Error getting relative volume for {ticker}: {str(e)}")
        return 0


def scan_day_trading_candidates():
    """
    Main function to scan for day trading candidates.
    
    Process:
    1. Use FinViz to screen for high-demand, low-supply stocks
    2. For each stock, get news from yfinance
    3. Use Gemini to analyze news sentiment (if available)
    4. Filter for non-negative sentiment (Positive, Neutral, or None)
    5. Return final list with all data
    """
    logger.info("=" * 60)
    logger.info("Starting Day Trading candidate scan")
    logger.info("=" * 60)
    
    try:
        # Step 1: Get screened stocks from FinViz
        screened_tickers = get_morning_scan()
        
        if not screened_tickers:
            logger.warning("No stocks passed FinViz screening")
            return {
                "status": "warning",
                "message": "No stocks matched FinViz criteria (Price $3-20, Float <5M, Rel. Volume >5x, Change Up)",
                "candidates": []
            }
        
        logger.info(f"Processing {len(screened_tickers)} candidates for news sentiment...")
        
        candidates = []
        positive_count = 0
        
        for ticker in screened_tickers:
            logger.info(f"Processing {ticker}...")
            
            try:
                # Get stock info
                info = get_stock_info(ticker)
                if not info:
                    continue
                
                # Get news
                headlines, news_items = get_stock_news(ticker)
                
                # Analyze sentiment if news available, otherwise treat as None
                if headlines:
                    sentiment, confidence = analyze_news_sentiment(ticker, headlines, news_items)
                else:
                    sentiment, confidence = "None", 0
                
                # Include if sentiment is NOT negative (accept Positive, Neutral, or None)
                if sentiment.lower() != "negative":
                    positive_count += 1
                    
                    # Calculate relative volume
                    rel_volume = get_relative_volume(ticker)
                    
                    candidates.append({
                        'ticker': ticker,
                        'price': round(info['price'], 2),
                        'change': round(info['change'], 2),
                        'float': info['float'],
                        'relative_volume': rel_volume,
                        'news_count': len(headlines),
                        'news_headlines': headlines,
                        'news_sentiment': sentiment,
                        'sentiment_confidence': confidence,
                        'scan_time': datetime.now().isoformat()
                    })
                    
                    logger.info(f"✓ {ticker}: {sentiment} sentiment ({confidence}%), {len(headlines)} articles")
                else:
                    logger.info(f"✗ {ticker}: {sentiment} sentiment ({confidence}%), skipping")
            
            except Exception as e:
                logger.error(f"Error processing {ticker}: {str(e)}")
                continue
        
        # Sort by sentiment confidence (highest first)
        candidates.sort(key=lambda x: x['sentiment_confidence'], reverse=True)
        
        logger.info("=" * 60)
        logger.info(f"Scan complete: {positive_count} candidates with positive sentiment")
        logger.info("=" * 60)
        
        return {
            "status": "success",
            "message": f"Found {positive_count} stocks with positive news sentiment",
            "candidates": candidates,
            "scan_time": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Fatal error in scan_day_trading_candidates: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Scan failed: {str(e)}",
            "candidates": []
        }
