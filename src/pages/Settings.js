import React, { useState, useEffect } from 'react';
import { Settings, Plus, Trash2, Check, X, Save } from 'lucide-react';

const SettingsPage = () => {
  const [symbols, setSymbols] = useState([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5001';

  // Load symbols on mount
  useEffect(() => {
    fetchSymbols();
  }, []);

  const fetchSymbols = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/symbols`);
      const data = await response.json();
      
      if (data.status === 'success') {
        setSymbols(data.symbols || []);
        setMessage(null);
      }
    } catch (error) {
      console.error('Failed to fetch symbols:', error);
      setMessage({ type: 'error', text: 'Failed to load symbols' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddSymbol = () => {
    const upperSymbol = newSymbol.trim().toUpperCase();
    
    if (!upperSymbol) {
      setMessage({ type: 'error', text: 'Please enter a symbol' });
      return;
    }
    
    if (symbols.includes(upperSymbol)) {
      setMessage({ type: 'error', text: `${upperSymbol} is already tracked` });
      return;
    }
    
    setSymbols([...symbols, upperSymbol]);
    setNewSymbol('');
    setMessage({ type: 'success', text: `Added ${upperSymbol}` });
  };

  const handleRemoveSymbol = (symbol) => {
    setSymbols(symbols.filter(s => s !== symbol));
    setMessage({ type: 'success', text: `Removed ${symbol}` });
  };

  const handleSave = async () => {
    if (symbols.length === 0) {
      setMessage({ type: 'error', text: 'At least one symbol is required' });
      return;
    }

    setSaving(true);
    try {
      const response = await fetch(`${backendUrl}/api/symbols`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        setMessage({ type: 'success', text: 'Symbols updated successfully!' });
      } else {
        setMessage({ type: 'error', text: data.message || 'Failed to update symbols' });
      }
    } catch (error) {
      console.error('Failed to save symbols:', error);
      setMessage({ type: 'error', text: 'Failed to save symbols' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <nav className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-700 shadow-xl">
        <div className="max-w-4xl mx-auto px-4 py-6 flex items-center gap-4">
          <div className="bg-gradient-to-br from-purple-500 to-pink-400 p-3 rounded-xl shadow-lg">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-white">Settings</h1>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
              Manage Tracked Symbols
            </p>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Message Alert */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${
              message.type === 'success'
                ? 'bg-emerald-900/30 border border-emerald-700/50 text-emerald-300'
                : 'bg-rose-900/30 border border-rose-700/50 text-rose-300'
            }`}
          >
            {message.type === 'success' ? (
              <Check className="w-5 h-5 flex-shrink-0" />
            ) : (
              <X className="w-5 h-5 flex-shrink-0" />
            )}
            <span className="font-semibold">{message.text}</span>
          </div>
        )}

        {loading ? (
          <div className="text-center py-20">
            <p className="text-slate-400 font-semibold">Loading symbols...</p>
          </div>
        ) : (
          <>
            {/* Add Symbol Section */}
            <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-6 mb-8">
              <h2 className="text-lg font-bold text-white mb-4">Add New Symbol</h2>
              <div className="flex gap-3">
                <input
                  type="text"
                  placeholder="e.g., TSLA, AAPL, BRK.B"
                  value={newSymbol}
                  onChange={(e) => setNewSymbol(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleAddSymbol()}
                  className="flex-1 px-4 py-3 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-purple-500 focus:outline-none transition-colors"
                />
                <button
                  onClick={handleAddSymbol}
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-lg flex items-center gap-2 transition-all shadow-lg"
                >
                  <Plus className="w-5 h-5" />
                  Add
                </button>
              </div>
            </div>

            {/* Tracked Symbols Section */}
            <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-6 mb-8">
              <h2 className="text-lg font-bold text-white mb-4">
                Currently Tracked Symbols ({symbols.length})
              </h2>

              {symbols.length === 0 ? (
                <p className="text-slate-400 text-center py-8">No symbols tracked yet</p>
              ) : (
                <div className="space-y-2">
                  {symbols.map((symbol) => (
                    <div
                      key={symbol}
                      className="flex items-center justify-between p-4 bg-slate-900/50 rounded-lg border border-slate-700/50 hover:border-slate-600 transition-colors"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-gradient-to-br from-purple-600 to-pink-500 rounded-lg flex items-center justify-center font-bold text-sm">
                          {symbol[0]}
                        </div>
                        <div>
                          <p className="font-bold text-white text-lg">{symbol}</p>
                          <p className="text-xs text-slate-400">Analyzed in hourly runs</p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleRemoveSymbol(symbol)}
                        className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-900/20 rounded-lg transition-colors"
                        title="Remove symbol"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Save Button */}
            <div className="flex gap-4">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 px-8 py-4 bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-700 hover:to-cyan-700 text-white font-bold rounded-lg flex items-center justify-center gap-2 transition-all shadow-lg disabled:opacity-50"
              >
                <Save className="w-5 h-5" />
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
              <button
                onClick={fetchSymbols}
                className="px-8 py-4 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg transition-all"
              >
                Reset
              </button>
            </div>

            {/* Info Box */}
            <div className="mt-8 p-4 bg-blue-900/20 border border-blue-700/50 rounded-lg text-blue-300 text-sm">
              <p className="font-semibold mb-2">ℹ️ How It Works</p>
              <ul className="space-y-1 text-xs">
                <li>• Your tracked symbols will be analyzed during hourly runs (9:45 AM - 3:45 PM ET, weekdays)</li>
                <li>• Signals are generated when RSI hits overbought (&gt;70) or oversold (&lt;30) levels</li>
                <li>• Each symbol must be 1-5 characters (e.g., QQQ, AAPL, BRK.B)</li>
                <li>• Changes take effect immediately on the next scheduled run</li>
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
};

export default SettingsPage;
