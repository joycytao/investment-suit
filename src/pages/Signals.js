import React, { useState, useEffect } from 'react';
import {
  TrendingUp, TrendingDown, AlertCircle, RefreshCw, Eye,
  Zap, Target, DollarSign, Percent, Clock, ArrowUpRight, ArrowDownLeft
} from 'lucide-react';

const Signals = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [filterType, setFilterType] = useState('all'); // all, overbought, oversold

  // Fetch signals from backend API
  const fetchSignals = async () => {
    setLoading(true);
    try {
      const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5001';
      const url = `${backendUrl}/api/signals`;
      console.log('🔄 Fetching signals from:', url);
      
      const response = await fetch(url);
      console.log('📡 Response status:', response.status);
      
      const data = await response.json();
      console.log('📊 Response data:', data);
      
      if (data.status === 'success' && data.signals) {
        // Sort by timestamp, newest first
        const sortedSignals = data.signals.sort(
          (a, b) => new Date(b.timestamp) - new Date(a.timestamp)
        );
        setSignals(sortedSignals);
        setLastUpdate(new Date());
        console.log('✅ Loaded', sortedSignals.length, 'signals');
      } else {
        console.warn('⚠️ Unexpected response format:', data);
        // Fall back to mock signals if no real data
        console.log('📌 Using mock signals as fallback');
        setSignals(generateMockSignals());
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('❌ Failed to fetch signals:', error);
      console.log('📌 Using mock signals as fallback due to error');
      // Fall back to mock signals on error
      setSignals(generateMockSignals());
      setLastUpdate(new Date());
    } finally {
      setLoading(false);
    }
  };

  // Generate mock signals for development/demo
  const generateMockSignals = () => {
    const now = new Date();
    return [
      {
        timestamp: now.toISOString(),
        symbol: 'QQQ',
        signal_type: 'oversold',
        current_price: 418.30,
        rsi: 27.8,
        ma20: 425.50,
        ma200: 430.00,
        bb_upper: 438.20,
        bb_middle: 425.50,
        bb_lower: 412.80,
        confidence: 'high',
        recommended_strategy: {
          type: 'put_credit_spread',
          sell_strike: 415.00,
          buy_strike: 410.00,
          sell_premium: 2.40,
          buy_premium: 0.65,
          net_premium_collected: 1.75,
          max_profit: 1.75,
          max_loss: 3.25,
          profit_percentage: 35.0,
          dte: 30
        },
        strategies: []
      },
      {
        timestamp: new Date(now.getTime() - 3600000).toISOString(),
        symbol: 'SPY',
        signal_type: 'oversold',
        current_price: 502.80,
        rsi: 28.3,
        ma20: 510.20,
        ma200: 515.00,
        bb_upper: 522.50,
        bb_middle: 510.20,
        bb_lower: 497.90,
        confidence: 'high',
        recommended_strategy: {
          type: 'put_credit_spread',
          sell_strike: 500.00,
          buy_strike: 495.00,
          sell_premium: 1.85,
          buy_premium: 0.40,
          net_premium_collected: 1.45,
          max_profit: 1.45,
          max_loss: 3.55,
          profit_percentage: 28.85,
          dte: 30
        },
        strategies: []
      },
      {
        timestamp: new Date(now.getTime() - 7200000).toISOString(),
        symbol: 'DIA',
        signal_type: 'overbought',
        current_price: 395.75,
        rsi: 74.2,
        ma20: 391.20,
        ma200: 388.50,
        bb_upper: 398.50,
        bb_middle: 391.20,
        bb_lower: 383.90,
        confidence: 'high',
        recommended_strategy: {
          type: 'call_credit_spread',
          sell_strike: 396.00,
          buy_strike: 400.00,
          sell_premium: 1.95,
          buy_premium: 0.45,
          net_premium_collected: 1.50,
          max_profit: 1.50,
          max_loss: 2.50,
          profit_percentage: 37.5,
          dte: 30
        },
        strategies: []
      }
    ];
  };

  useEffect(() => {
    fetchSignals();
    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchSignals, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // Filter signals
  const filteredSignals = signals.filter(s => 
    filterType === 'all' || s.signal_type === filterType
  );

  // Get summary stats
  const overboughtCount = signals.filter(s => s.signal_type === 'overbought').length;
  const oversoldCount = signals.filter(s => s.signal_type === 'oversold').length;
  const avgProfit = signals.length > 0 
    ? (signals.reduce((sum, s) => sum + (s.recommended_strategy?.max_profit || 0), 0) / signals.length).toFixed(2)
    : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <nav className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-700 shadow-xl">
        <div className="max-w-7xl mx-auto px-4 py-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-cyan-400 p-3 rounded-xl shadow-lg">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-white">🚀 Trading Signals</h1>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                Real-time Technical Analysis & Options Strategies
              </p>
            </div>
          </div>

          <button
            onClick={fetchSignals}
            disabled={loading}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-700 hover:to-cyan-600 text-white font-bold rounded-lg flex items-center gap-2 transition-all disabled:opacity-50 shadow-lg"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Stats Summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-10">
          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6 hover:border-slate-600 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Total Signals</p>
                <p className="text-4xl font-black text-white">{signals.length}</p>
              </div>
              <div className="bg-blue-500/20 p-3 rounded-lg">
                <AlertCircle className="w-8 h-8 text-blue-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6 hover:border-slate-600 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Overbought (Sell)</p>
                <p className="text-4xl font-black text-rose-400">{overboughtCount}</p>
              </div>
              <div className="bg-rose-500/20 p-3 rounded-lg">
                <TrendingUp className="w-8 h-8 text-rose-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6 hover:border-slate-600 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Oversold (Buy)</p>
                <p className="text-4xl font-black text-emerald-400">{oversoldCount}</p>
              </div>
              <div className="bg-emerald-500/20 p-3 rounded-lg">
                <TrendingDown className="w-8 h-8 text-emerald-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6 hover:border-slate-600 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm font-semibold mb-1">Avg. Max Profit</p>
                <p className="text-4xl font-black text-cyan-400">${avgProfit}</p>
              </div>
              <div className="bg-cyan-500/20 p-3 rounded-lg">
                <DollarSign className="w-8 h-8 text-cyan-400" />
              </div>
            </div>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-3 mb-8">
          {[
            { id: 'all', label: 'All Signals', icon: AlertCircle, color: 'blue' },
            { id: 'overbought', label: 'Overbought (SELL)', icon: TrendingUp, color: 'rose' },
            { id: 'oversold', label: 'Oversold (BUY)', icon: TrendingDown, color: 'emerald' }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setFilterType(tab.id)}
              className={`px-6 py-3 rounded-lg font-bold text-sm transition-all flex items-center gap-2 ${
                filterType === tab.id
                  ? `bg-${tab.color}-600 text-white shadow-lg`
                  : 'bg-slate-800/50 text-slate-300 border border-slate-700 hover:border-slate-600'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
              {tab.id === 'overbought' && overboughtCount > 0 && (
                <span className="ml-2 bg-white/20 px-2 py-0.5 rounded text-xs font-black">{overboughtCount}</span>
              )}
              {tab.id === 'oversold' && oversoldCount > 0 && (
                <span className="ml-2 bg-white/20 px-2 py-0.5 rounded text-xs font-black">{oversoldCount}</span>
              )}
            </button>
          ))}
        </div>

        {/* Signals Grid */}
        {filteredSignals.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {filteredSignals.map((signal, idx) => {
              const isOverbought = signal.signal_type === 'overbought';
              const strategy = signal.recommended_strategy;

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedSignal(selectedSignal?.timestamp === signal.timestamp ? null : signal)}
                  className="group bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl overflow-hidden hover:border-slate-600 hover:bg-slate-800/70 transition-all cursor-pointer shadow-xl hover:shadow-2xl"
                >
                  {/* Card Header */}
                  <div className={`px-6 py-4 border-b border-slate-700 bg-gradient-to-r ${
                    isOverbought 
                      ? 'from-rose-900/30 to-rose-800/20' 
                      : 'from-emerald-900/30 to-emerald-800/20'
                  }`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`w-14 h-14 rounded-xl flex items-center justify-center font-black text-xl ${
                          isOverbought 
                            ? 'bg-rose-900/50 text-rose-300' 
                            : 'bg-emerald-900/50 text-emerald-300'
                        }`}>
                          {signal.symbol[0]}
                        </div>
                        <div>
                          <h3 className="text-2xl font-black text-white">{signal.symbol}</h3>
                          <p className={`text-xs font-bold uppercase tracking-wide ${
                            isOverbought ? 'text-rose-300' : 'text-emerald-300'
                          }`}>
                            {isOverbought ? '📈 Overbought - SELL' : '📉 Oversold - BUY'}
                          </p>
                        </div>
                      </div>
                      <div className={`px-4 py-2 rounded-lg font-black text-xs uppercase tracking-widest ${
                        isOverbought
                          ? 'bg-rose-900/40 text-rose-300'
                          : 'bg-emerald-900/40 text-emerald-300'
                      }`}>
                        {signal.confidence}
                      </div>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="px-6 py-6 space-y-4">
                    {/* Price & Indicators */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-900/50 rounded-lg p-4">
                        <p className="text-slate-400 text-xs font-bold mb-1">Current Price</p>
                        <p className="text-2xl font-black text-white">${signal.current_price?.toFixed(2) || 'N/A'}</p>
                      </div>
                      <div className="bg-slate-900/50 rounded-lg p-4">
                        <p className="text-slate-400 text-xs font-bold mb-1">RSI (14)</p>
                        <p className={`text-2xl font-black ${
                          isOverbought ? 'text-rose-400' : 'text-emerald-400'
                        }`}>
                          {signal.rsi?.toFixed(2) || 'N/A'}
                        </p>
                      </div>
                      <div className="bg-slate-900/50 rounded-lg p-4">
                        <p className="text-slate-400 text-xs font-bold mb-1">MA20</p>
                        <p className="text-2xl font-black text-cyan-400">${signal.ma20?.toFixed(2) || 'N/A'}</p>
                      </div>
                      <div className="bg-slate-900/50 rounded-lg p-4">
                        <p className="text-slate-400 text-xs font-bold mb-1">MA200</p>
                        <p className="text-2xl font-black text-blue-400">${signal.ma200?.toFixed(2) || 'N/A'}</p>
                      </div>
                    </div>

                    {/* Bollinger Bands */}
                    <div className="bg-slate-900/50 rounded-lg p-4">
                      <p className="text-slate-400 text-xs font-bold mb-3">Bollinger Bands (20, 2)</p>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-slate-400">Upper Band</span>
                          <span className="font-bold text-rose-400">${signal.bb_upper?.toFixed(2) || 'N/A'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Middle (MA)</span>
                          <span className="font-bold text-white">${signal.bb_middle?.toFixed(2) || 'N/A'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Lower Band</span>
                          <span className="font-bold text-emerald-400">${signal.bb_lower?.toFixed(2) || 'N/A'}</span>
                        </div>
                      </div>
                    </div>

                    {/* Recommended Strategy */}
                    {strategy && (
                      <div className={`rounded-lg p-4 border ${
                        isOverbought
                          ? 'bg-rose-900/20 border-rose-700/50'
                          : 'bg-emerald-900/20 border-emerald-700/50'
                      }`}>
                        <div className="flex items-center justify-between mb-3">
                          <p className="text-xs font-bold uppercase tracking-wide text-slate-300">Recommended Strategy</p>
                          <Target className={`w-4 h-4 ${isOverbought ? 'text-rose-400' : 'text-emerald-400'}`} />
                        </div>
                        <p className="font-bold text-white mb-3 text-lg">{strategy.type?.replace('_', ' ').toUpperCase()}</p>

                        <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                          {isOverbought ? (
                            <>
                              <div>
                                <p className="text-slate-400 text-xs mb-1">Sell Call @ </p>
                                <p className="font-black text-white">${strategy.sell_strike?.toFixed(2)}</p>
                              </div>
                              <div>
                                <p className="text-slate-400 text-xs mb-1">Buy Call @ </p>
                                <p className="font-black text-white">${strategy.buy_strike?.toFixed(2)}</p>
                              </div>
                            </>
                          ) : (
                            <>
                              <div>
                                <p className="text-slate-400 text-xs mb-1">Sell Put @ </p>
                                <p className="font-black text-white">${strategy.sell_strike?.toFixed(2)}</p>
                              </div>
                              <div>
                                <p className="text-slate-400 text-xs mb-1">Buy Put @ </p>
                                <p className="font-black text-white">${strategy.buy_strike?.toFixed(2)}</p>
                              </div>
                            </>
                          )}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Net Premium</p>
                            <p className="font-black text-cyan-400">${strategy.net_premium_collected?.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Max Profit %</p>
                            <p className="font-black text-emerald-400">{strategy.profit_percentage?.toFixed(2)}%</p>
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 text-xs pt-3 border-t border-slate-700/50">
                          <div>
                            <p className="text-slate-400 mb-1">Max Profit</p>
                            <p className="font-black text-emerald-400">${strategy.max_profit?.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-slate-400 mb-1">Max Loss</p>
                            <p className="font-black text-rose-400">${strategy.max_loss?.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-slate-400 mb-1">DTE</p>
                            <p className="font-black text-blue-400">{strategy.dte} days</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Card Footer */}
                  <div className="px-6 py-4 bg-slate-900/50 border-t border-slate-700 flex items-center justify-between text-xs text-slate-400">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      {new Date(signal.timestamp).toLocaleString()}
                    </div>
                    <Eye className="w-4 h-4 group-hover:text-slate-300 transition-colors" />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-20">
            <AlertCircle className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 font-semibold mb-2">No signals available</p>
            <p className="text-slate-500 text-sm">Check back later or adjust your filters</p>
          </div>
        )}

        {/* Last Update Info */}
        {lastUpdate && (
          <div className="text-center text-slate-500 text-sm py-4 border-t border-slate-700 mt-8">
            Last updated: {lastUpdate.toLocaleString()}
            <p className="text-xs text-slate-600 mt-1">Auto-refreshes every 5 minutes</p>
          </div>
        )}
      </main>
    </div>
  );
};

export default Signals;
