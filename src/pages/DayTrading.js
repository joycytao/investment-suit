import React, { useState, useEffect } from 'react';
import { AlertCircle, TrendingUp, Clock, Zap, RefreshCw, TrendingDown } from 'lucide-react';

const DayTrading = () => {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [lastScanTime, setLastScanTime] = useState(null);
  const [message, setMessage] = useState(null);
  const [marketStatus, setMarketStatus] = useState('closed');
  const [timeToOpen, setTimeToOpen] = useState(null);

  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5001';

  // Check market status and time to open
  useEffect(() => {
    const checkMarketStatus = () => {
      const now = new Date();
      const estTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      
      const dayOfWeek = estTime.getDay();
      const hour = estTime.getHours();
      const minutes = estTime.getMinutes();
      
      // Market is open Monday-Friday, 9:30 AM - 4:00 PM EST
      const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
      const isMarketHours = hour >= 9 && hour < 16;
      const isPremarketHours = hour >= 4 && hour < 9;
      
      if (isWeekday && isMarketHours) {
        setMarketStatus('open');
        setTimeToOpen(null);
      } else if (isWeekday && isPremarketHours) {
        setMarketStatus('premarket');
        const minutesUntilOpen = 9 * 60 + 30 - (hour * 60 + minutes);
        setTimeToOpen(minutesUntilOpen);
      } else if (isWeekday) {
        setMarketStatus('closed');
        // Calculate time to next open
        const nextOpen = new Date(estTime);
        if (hour >= 16 || dayOfWeek === 5) {
          nextOpen.setDate(nextOpen.getDate() + (dayOfWeek === 5 ? 3 : 1));
        }
        nextOpen.setHours(9, 30, 0);
        const minutesUntilOpen = Math.round((nextOpen - estTime) / 60000);
        setTimeToOpen(minutesUntilOpen);
      } else {
        setMarketStatus('closed');
      }
    };

    checkMarketStatus();
    const interval = setInterval(checkMarketStatus, 60000); // Check every minute
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setScanning(true);
    setMessage({ type: 'info', text: 'Scanning for High Demand Low Supply stocks with positive news sentiment...' });

    try {
      const response = await fetch(`${backendUrl}/api/day-trading-scan`, {
        method: 'POST',
      });

      const data = await response.json();

      if (data.status === 'success') {
        setCandidates(data.candidates || []);
        setLastScanTime(new Date());
        setMessage(data.message ? { type: 'success', text: data.message } : null);
      } else {
        setMessage({ type: 'error', text: data.message || 'Scan failed' });
      }
    } catch (error) {
      console.error('Scan error:', error);
      setMessage({ type: 'error', text: 'Failed to scan. Backend may be unavailable.' });
    } finally {
      setScanning(false);
    }
  };

  const getSentimentColor = (sentiment) => {
    if (!sentiment) return 'text-slate-400';
    const lower = sentiment.toLowerCase();
    if (lower.includes('positive') || lower.includes('bullish') || lower.includes('strong buy')) {
      return 'text-green-400';
    } else if (lower.includes('negative') || lower.includes('bearish') || lower.includes('sell')) {
      return 'text-red-400';
    } else {
      return 'text-yellow-400';
    }
  };

  const getSentimentBgColor = (sentiment) => {
    if (!sentiment) return 'bg-slate-800';
    const lower = sentiment.toLowerCase();
    if (lower.includes('positive') || lower.includes('bullish') || lower.includes('strong buy')) {
      return 'bg-green-900/30 border border-green-700';
    } else if (lower.includes('negative') || lower.includes('bearish') || lower.includes('sell')) {
      return 'bg-red-900/30 border border-red-700';
    } else {
      return 'bg-yellow-900/30 border border-yellow-700';
    }
  };

  const formatTimeToOpen = (minutes) => {
    if (!minutes) return 'Now';
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-850">
      {/* Header */}
      <div className="bg-slate-900/80 border-b border-slate-700 sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-start justify-between gap-6">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Zap className="w-8 h-8 text-amber-400" />
                <h1 className="text-4xl font-black text-white">⚡ Day Trading</h1>
              </div>
              <p className="text-slate-400">High Demand Low Supply Stocks (excluding Negative news sentiment)</p>
            </div>
            
            <div className="text-right">
              <div className="inline-block px-4 py-2 rounded-lg bg-slate-800 border border-slate-700">
                <p className="text-xs text-slate-400 mb-1">Market Status</p>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    marketStatus === 'open' ? 'bg-green-500' : 
                    marketStatus === 'premarket' ? 'bg-yellow-500' : 
                    'bg-red-500'
                  }`}></div>
                  <p className="font-semibold text-white capitalize">{marketStatus === 'premarket' ? 'Pre-Market' : marketStatus}</p>
                </div>
                {timeToOpen && (
                  <p className="text-xs text-slate-400 mt-1">
                    {marketStatus === 'premarket' ? 'Opens in' : 'Next open'}: {formatTimeToOpen(timeToOpen)}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Controls */}
        <div className="mb-8">
          <button
            onClick={handleScan}
            disabled={scanning}
            className={`px-6 py-3 rounded-lg font-semibold transition-all flex items-center gap-2 ${
              scanning
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                : 'bg-amber-600 hover:bg-amber-700 text-white'
            }`}
          >
            <RefreshCw className={`w-5 h-5 ${scanning ? 'animate-spin' : ''}`} />
            {scanning ? 'Scanning...' : 'Scan Now'}
          </button>

          {lastScanTime && (
            <p className="text-xs text-slate-400 mt-2">
              Last scan: {lastScanTime.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit',
                timeZone: 'America/New_York'
              })} EST
            </p>
          )}
        </div>

        {/* Message */}
        {message && (
          <div className={`p-4 rounded-lg mb-6 flex gap-3 ${
            message.type === 'success' ? 'bg-green-900/30 border border-green-700' :
            message.type === 'error' ? 'bg-red-900/30 border border-red-700' :
            'bg-blue-900/30 border border-blue-700'
          }`}>
            <AlertCircle className={`w-5 h-5 flex-shrink-0 ${
              message.type === 'success' ? 'text-green-400' :
              message.type === 'error' ? 'text-red-400' :
              'text-blue-400'
            }`} />
            <p className={`${
              message.type === 'success' ? 'text-green-200' :
              message.type === 'error' ? 'text-red-200' :
              'text-blue-200'
            }`}>{message.text}</p>
          </div>
        )}

        {/* Filters Info */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-1">Price Range</p>
            <p className="text-lg font-bold text-white">$1 - $20</p>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-1">Float</p>
            <p className="text-lg font-bold text-white">&lt; 5M</p>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-1">Rel. Volume</p>
            <p className="text-lg font-bold text-white">&gt; 5x</p>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-1">Change</p>
            <p className="text-lg font-bold text-green-400">↑ Up</p>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-1">News Sentiment</p>
              <p className="text-lg font-bold text-slate-300">Positive or Neutral or None</p>
          </div>
        </div>

        {/* Candidates List */}
        {candidates.length === 0 ? (
          <div className="text-center py-16">
            <Zap className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 text-lg mb-4">No opportunities found yet</p>
            <p className="text-slate-500 text-sm max-w-md mx-auto">
              Click "Scan Now" to find high-demand, low-supply stocks, excluding those with negative sentiment. Includes stocks with Positive, Neutral, or no recent news. Best to scan 9:35 AM EST (5 minutes after market open).
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-white mb-4">
              {candidates.length} Opportunity{candidates.length !== 1 ? 's' : ''} Found
            </h2>
            
            {candidates.map((candidate, idx) => (
              <div
                key={idx}
                className={`rounded-lg p-4 border transition-all hover:shadow-lg ${getSentimentBgColor(candidate.news_sentiment)}`}
              >
                <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
                  {/* Ticker */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Ticker</p>
                    <p className="text-2xl font-black text-white">{candidate.ticker}</p>
                    <p className="text-xs text-slate-400 mt-1">${candidate.price?.toFixed(2)}</p>
                  </div>

                  {/* Change */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Change</p>
                    <div className="flex items-center gap-2">
                      <TrendingUp className={`w-5 h-5 ${
                        (candidate.change || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`} />
                      <p className={`text-lg font-bold ${
                        (candidate.change || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {(candidate.change || 0).toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  {/* Relative Volume */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Rel. Volume</p>
                    <p className="text-lg font-bold text-amber-400">{candidate.relative_volume?.toFixed(1)}x</p>
                  </div>

                  {/* Float */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Float</p>
                    <p className="text-lg font-bold text-blue-400">
                      {(candidate.float / 1000000).toFixed(1)}M
                    </p>
                  </div>

                  {/* News Count */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">News Today</p>
                    <p className="text-lg font-bold text-purple-400">{candidate.news_count || 0}</p>
                  </div>

                  {/* Sentiment */}
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Sentiment</p>
                    <p className={`text-sm font-semibold ${getSentimentColor(candidate.news_sentiment)}`}>
                      {candidate.news_sentiment || 'No news'}
                    </p>
                  </div>
                </div>

                {/* News Headlines */}
                {candidate.news_headlines && candidate.news_headlines.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-current opacity-50">
                    <p className="text-xs text-slate-400 mb-2">Latest News Headlines:</p>
                    <div className="space-y-1">
                      {candidate.news_headlines.slice(0, 2).map((headline, i) => (
                        <p key={i} className="text-xs text-slate-300 line-clamp-1">
                          • {headline}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info Section */}
      <div className="max-w-7xl mx-auto px-6 py-8 border-t border-slate-700">
        <div className="bg-slate-800/50 rounded-lg p-6">
          <h3 className="text-lg font-bold text-white mb-4">ℹ️ Day Trading Strategy</h3>
          <ul className="space-y-2 text-slate-300 text-sm">
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>Timing:</strong> Scan 9:35 AM EST (5 minutes after market open at 9:30 AM)</span>
            </li>
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>Price Range:</strong> $1-$20 (micro-cap volatility sweet spot)</span>
            </li>
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>Float:</strong> &lt; 5M shares (tight float = more explosive moves)</span>
            </li>
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>Relative Volume:</strong> &gt; 5x average (strong buying pressure)</span>
            </li>
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>News Sentiment:</strong> Exclude Negative (includes Positive, Neutral, or no news)</span>
            </li>
            <li className="flex gap-3">
              <span className="text-amber-400 font-bold">•</span>
              <span><strong>Monitoring Window:</strong> Watch for first hour after market open for peak volatility</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default DayTrading;
