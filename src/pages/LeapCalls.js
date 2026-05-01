import React, { useState, useEffect } from 'react';
import { RefreshCw, Zap, TrendingUp, DollarSign, Activity, AlertCircle } from 'lucide-react';

const LeapCalls = () => {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [message, setMessage] = useState(null);
  const [maxMonths, setMaxMonths] = useState(24);

  const MIN_MONTHS = 6; // Fixed minimum (6 months = ~180 days)
  const DAYS_PER_MONTH = 30; // Conversion factor
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5001';

  // Load candidates on mount
  useEffect(() => {
    fetchCandidates();
    // Auto-refresh every 30 minutes
    const interval = setInterval(fetchCandidates, 30 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/leap-candidates`);
      const data = await response.json();

      if (data.status === 'success') {
        setCandidates(data.candidates || []);
        setLastUpdate(new Date());
        setMessage(null);
      }
    } catch (error) {
      console.error('Failed to fetch LEAP candidates:', error);
      setMessage({ type: 'error', text: 'Failed to load LEAP candidates' });
    } finally {
      setLoading(false);
    }
  };

  const handleManualScan = async () => {
    setScanning(true);
    
    // Convert months to DTE (days)
    const minDTE = Math.round(MIN_MONTHS * DAYS_PER_MONTH);
    const maxDTE = Math.round(maxMonths * DAYS_PER_MONTH);
    
    setMessage({ type: 'info', text: `Scanning S&P 500 / Nasdaq 100 for LEAP opportunities (${MIN_MONTHS}-${maxMonths} months)...` });

    try {
      const response = await fetch(`${backendUrl}/api/leap-scan?minDTE=${minDTE}&maxDTE=${maxDTE}`, {
        method: 'POST',
      });

      const data = await response.json();

      if (data.status === 'success') {
        setCandidates(data.candidates || []);
        setLastUpdate(new Date());
        setMessage({ 
          type: 'success', 
          text: `Scan complete! Found ${data.count} LEAP opportunities (${MIN_MONTHS}-${maxMonths} months).` 
        });
      } else {
        setMessage({ type: 'error', text: data.message || 'Scan failed' });
      }
    } catch (error) {
      console.error('Scan error:', error);
      setMessage({ type: 'error', text: 'Scan failed: ' + error.message });
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <nav className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-700 shadow-xl">
        <div className="max-w-7xl mx-auto px-4 py-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-purple-500 to-pink-400 p-3 rounded-xl shadow-lg">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-white">⚡ LEAP Calls</h1>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                Deep ITM 2027-2028 Expiration Opportunities
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleManualScan}
              disabled={scanning}
              className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-lg flex items-center gap-2 transition-all disabled:opacity-50 shadow-lg"
            >
              <RefreshCw className={`w-5 h-5 ${scanning ? 'animate-spin' : ''}`} />
              {scanning ? 'Scanning...' : 'Scan Now'}
            </button>
            <button
              onClick={fetchCandidates}
              disabled={loading}
              className="px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Message Alert */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${
              message.type === 'success'
                ? 'bg-emerald-900/30 border border-emerald-700/50 text-emerald-300'
                : message.type === 'error'
                ? 'bg-rose-900/30 border border-rose-700/50 text-rose-300'
                : 'bg-blue-900/30 border border-blue-700/50 text-blue-300'
            }`}
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="font-semibold">{message.text}</span>
          </div>
        )}

        {/* Expiration Duration Filter */}
        <div className="mb-8 bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
          <div className="mb-4">
            <h3 className="text-lg font-bold text-white mb-2">⏳ Expiration Duration Filter</h3>
            <p className="text-sm text-slate-400">Adjust the maximum expiration date (LEAP options are 6-24 months)</p>
          </div>
          
          <div className="space-y-4">
            <div>
              {/* Max Months Slider */}
              <label className="text-sm font-semibold text-slate-300 mb-3 block">
                Maximum Duration: <span className="text-purple-400 text-lg">{maxMonths}</span> months 
                <span className="text-slate-500 ml-2">({(maxMonths / 12).toFixed(1)} years)</span>
              </label>
              <input
                type="range"
                min="6"
                max="24"
                value={maxMonths}
                onChange={(e) => setMaxMonths(parseInt(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <div className="flex justify-between text-xs text-slate-500 mt-2 px-1">
                <span>6 months</span>
                <span>24 months</span>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-700">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-400">
                  <span className="font-semibold text-white">Range:</span> {MIN_MONTHS} - {maxMonths} months 
                  <span className="text-slate-500 ml-2">({(MIN_MONTHS / 12).toFixed(1)} - {(maxMonths / 12).toFixed(1)} years)</span>
                </p>
                <button
                  onClick={() => setMaxMonths(24)}
                  className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                >
                  Reset to Default
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Message Alert */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${
              message.type === 'success'
                ? 'bg-emerald-900/30 border border-emerald-700/50 text-emerald-300'
                : message.type === 'error'
                ? 'bg-rose-900/30 border border-rose-700/50 text-rose-300'
                : 'bg-blue-900/30 border border-blue-700/50 text-blue-300'
            }`}
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="font-semibold">{message.text}</span>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">LEAP Candidates</p>
                <p className="text-4xl font-black text-white">{candidates.length}</p>
              </div>
              <div className="bg-purple-500/20 p-3 rounded-lg">
                <TrendingUp className="w-8 h-8 text-purple-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Avg Revenue Growth</p>
                <p className="text-4xl font-black text-cyan-400">
                  {candidates.length > 0
                    ? (candidates.reduce((sum, c) => sum + (c.revenue_growth || 0), 0) / candidates.length * 100).toFixed(0)
                    : 0}
                  %
                </p>
              </div>
              <div className="bg-cyan-500/20 p-3 rounded-lg">
                <Activity className="w-8 h-8 text-cyan-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Avg Upside</p>
                <p className="text-4xl font-black text-emerald-400">
                  {candidates.length > 0
                    ? (candidates.reduce((sum, c) => sum + (c.upside_potential || 0), 0) / candidates.length * 100).toFixed(0)
                    : 0}
                  %
                </p>
              </div>
              <div className="bg-emerald-500/20 p-3 rounded-lg">
                <DollarSign className="w-8 h-8 text-emerald-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
            <div>
              <p className="text-slate-400 text-sm font-semibold mb-1">Last Scan</p>
              <p className="text-lg font-black text-slate-300">
                {lastUpdate ? lastUpdate.toLocaleTimeString() : 'Never'}
              </p>
              <p className="text-xs text-slate-500 mt-2">
                {lastUpdate ? lastUpdate.toLocaleDateString() : 'No scan yet'}
              </p>
            </div>
          </div>
        </div>

        {/* Candidates Grid */}
        {candidates.length > 0 ? (
          <div className="space-y-6">
            {candidates.map((candidate, idx) => (
              <div
                key={idx}
                className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl overflow-hidden hover:border-slate-600 transition-all shadow-xl"
              >
                {/* Candidate Header */}
                <div className="bg-gradient-to-r from-purple-900/30 to-pink-800/20 px-6 py-4 border-b border-slate-700">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-gradient-to-br from-purple-600 to-pink-500 rounded-lg flex items-center justify-center font-bold text-lg">
                        {candidate.ticker[0]}
                      </div>
                      <div>
                        <h3 className="text-2xl font-black text-white">{candidate.ticker}</h3>
                        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                          LEAP Call Sweet Spot Analysis
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-black text-cyan-400">${candidate.current_price?.toFixed(2) || 'N/A'}</p>
                      <p className="text-xs text-slate-400">Current Price</p>
                    </div>
                  </div>
                </div>

                {/* Fundamentals Grid */}
                <div className="px-6 py-4 border-b border-slate-700">
                  <p className="text-xs font-bold text-slate-400 uppercase mb-3 tracking-wide">Fundamental Metrics</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-slate-900/50 rounded-lg p-3">
                      <p className="text-slate-400 text-xs mb-1">Revenue Growth</p>
                      <p className="text-xl font-black text-emerald-400">
                        {(candidate.revenue_growth * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="bg-slate-900/50 rounded-lg p-3">
                      <p className="text-slate-400 text-xs mb-1">Profit Margin</p>
                      <p className="text-xl font-black text-blue-400">
                        {(candidate.profit_margin * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="bg-slate-900/50 rounded-lg p-3">
                      <p className="text-slate-400 text-xs mb-1">Analyst Target</p>
                      <p className="text-xl font-black text-purple-400">
                        ${candidate.target_price?.toFixed(2) || 'N/A'}
                      </p>
                    </div>
                    <div className="bg-slate-900/50 rounded-lg p-3">
                      <p className="text-slate-400 text-xs mb-1">Upside Potential</p>
                      <p className="text-xl font-black text-pink-400">
                        {(candidate.upside_potential * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>

                {/* LEAP Sweet Spots */}
                {candidate.leap_sweet_spots && candidate.leap_sweet_spots.length > 0 ? (
                  <div className="px-6 py-4">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">
                      LEAP Call Options (Delta 0.75-0.85, Optimized Theta/Delta)
                    </p>
                    <div className="space-y-2">
                      {candidate.leap_sweet_spots.map((spot, spotIdx) => (
                        <div
                          key={spotIdx}
                          className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/50 hover:border-purple-600/50 transition-colors"
                        >
                          <div className="grid grid-cols-2 md:grid-cols-7 gap-3">
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Expires</p>
                              <p className="text-sm font-black text-orange-400 mb-1">
                                {spot.expiration_date}
                              </p>
                              <p className="text-xs text-slate-500">
                                {spot.dte} days
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Strike</p>
                              <p className="text-lg font-black text-white">
                                ${spot.strike?.toFixed(2) || 'N/A'}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Delta</p>
                              <p className="text-lg font-black text-cyan-400">
                                {(spot.delta * 100).toFixed(1)}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Theta (Daily)</p>
                              <p className="text-lg font-black text-emerald-400">
                                ${Math.abs(spot.theta?.toFixed(4) || 0)}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Theta/Delta</p>
                              <p className="text-lg font-black text-purple-400">
                                {(spot.theta_delta_ratio?.toFixed(4) || 0)}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Cost</p>
                              <p className="text-lg font-black text-pink-400">
                                ${spot.lastPrice?.toFixed(2) || 'N/A'}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-400 text-xs mb-1">Open Interest</p>
                              <p className="text-lg font-black text-blue-400">
                                {spot.openInterest || 0}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="px-6 py-4 text-center text-slate-400">
                    No sweet spot opportunities found for this candidate
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-20 bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl">
            <AlertCircle className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 font-semibold mb-2">No LEAP candidates available</p>
            <p className="text-slate-500 text-sm mb-6">
              Click "Scan Now" to find LEAP call opportunities from S&P 500 & Nasdaq 100
            </p>
            <button
              onClick={handleManualScan}
              className="px-6 py-2 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-lg transition-all inline-flex items-center gap-2"
            >
              <Zap className="w-4 h-4" />
              Start Scanning
            </button>
          </div>
        )}

        {/* Info Box */}
        <div className="mt-8 p-4 bg-blue-900/20 border border-blue-700/50 rounded-lg text-blue-300 text-sm">
          <p className="font-semibold mb-2">ℹ️ LEAP Call Screening Criteria</p>
          <ul className="space-y-1 text-xs">
            <li>• <strong>Fundamentals:</strong> Revenue Growth &gt; 15%, Profit Margin &gt; 10%, Price/Target &lt; 0.8</li>
            <li>• <strong>Delta Filter:</strong> 0.75-0.85 (realistic ITM, ~80% probability of expiring ITM)</li>
            <li>• <strong>Theta/Delta Ratio:</strong> Optimized for best time decay efficiency (lower = better)</li>
            <li>• <strong>Cost Efficiency:</strong> Option premium &lt; 40% of buying 100 shares cost</li>
            <li>• <strong>Liquidity:</strong> Open Interest &gt; 50 contracts for adequate trading volume</li>
            <li>• <strong>Time Decay (Theta):</strong> Daily decay in $ per day per 1-point delta move</li>
          </ul>
        </div>
      </main>
    </div>
  );
};

export default LeapCalls;
